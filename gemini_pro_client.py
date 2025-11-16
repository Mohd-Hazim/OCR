# gemini_pro_client.py - FULLY DEBUGGED VERSION
import io, base64, logging
from PIL import Image
import google.generativeai as genai
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# =====================================================================
# === COMPLETELY REWRITTEN MERGED CELL NORMALIZER =====================
# =====================================================================

def get_next_api_key():
    """
    Rotate API keys in round-robin fashion.
    Uses config.json → gemini_api_keys[] and gemini_api_key.
    """
    from utils.config import load_config, save_config

    cfg = load_config()
    keys = cfg.get("gemini_api_keys", [])
    if not keys:
        return cfg.get("gemini_api_key", "")

    # If no active key → start with first
    active = cfg.get("gemini_api_key", "")
    if active not in keys:
        next_key = keys[0]
    else:
        idx = keys.index(active)
        next_key = keys[(idx + 1) % len(keys)]  # rotate

    # Save new active key
    cfg["gemini_api_key"] = next_key
    save_config(cfg)

    return next_key

def infer_missing_rowspans(html: str) -> str:
    """
    Post-process HTML to infer missing rowspan attributes.
    
    Heuristic: If consecutive rows have the same structure where:
    - Row N has cells with colspan
    - Row N+1 has more cells that align with the colspan breakdown
    Then Row N likely should have had rowspan as well.
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    
    for table in tables:
        rows = table.find_all("tr")
        
        for i in range(len(rows) - 1):
            current_row = rows[i]
            next_row = rows[i + 1]
            
            current_cells = current_row.find_all(["td", "th"])
            next_cells = next_row.find_all(["td", "th"])
            
            # Check if current row has fewer cells with colspan
            # and next row has more cells
            if len(current_cells) < len(next_cells):
                # Calculate expected columns in current row
                current_cols = sum(int(cell.get("colspan", 1)) for cell in current_cells)
                
                # If current row spans same width as next row,
                # likely needs rowspan
                if current_cols == len(next_cells):
                    logger.info(f"Inferred rowspan: Row {i} cells should span to row {i+1}")
                    
                    # Add rowspan to current row cells
                    for cell in current_cells:
                        if not cell.get("rowspan"):
                            cell["rowspan"] = "2"
                            logger.info(f"  Added rowspan=2 to: {cell.get_text(strip=True)[:20]}")
    
    return str(soup)


def normalize_merged_cells(html: str) -> str:
    """
    COMPLETELY REWRITTEN: Handle rowspan/colspan properly.
    
    The key insight: We need to build the table cell-by-cell, tracking
    which positions are already "claimed" by spans from previous rows.
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    
    for table in tables:
        logger.info("=" * 60)
        logger.info("PROCESSING TABLE")
        logger.info("=" * 60)
        
        rows = table.find_all("tr")
        
        # We'll build a complete grid: grid[row][col] = text
        grid = []
        
        # Track which cells are "blocked" by spans
        blocked = set()  # Set of (row, col) tuples
        
        # ===================================================================
        # STEP 1: Parse each row and handle spans
        # ===================================================================
        for r_idx, tr in enumerate(rows):
            logger.info(f"\n--- Processing Row {r_idx} ---")
            
            cells = tr.find_all(["td", "th"])
            logger.info(f"Found {len(cells)} cells in HTML")
            
            # Ensure we have enough rows in grid
            while len(grid) <= r_idx:
                grid.append([])
            
            col_idx = 0  # Logical column position
            
            for cell_num, cell in enumerate(cells):
                # Skip blocked columns
                while (r_idx, col_idx) in blocked:
                    logger.info(f"  Col {col_idx}: BLOCKED (skipping)")
                    # Ensure this column exists in current row
                    while len(grid[r_idx]) <= col_idx:
                        grid[r_idx].append("")
                    col_idx += 1
                
                # Get cell content
                text = cell.get_text(strip=True)
                
                # Get span attributes
                try:
                    rowspan = int(cell.get("rowspan", 1))
                except:
                    rowspan = 1
                
                try:
                    colspan = int(cell.get("colspan", 1))
                except:
                    colspan = 1
                
                logger.info(f"  Cell {cell_num} at col {col_idx}: '{text}' (rowspan={rowspan}, colspan={colspan})")
                
                # ===================================================================
                # Place this cell and mark blocked regions
                # ===================================================================
                for dr in range(rowspan):
                    for dc in range(colspan):
                        target_r = r_idx + dr
                        target_c = col_idx + dc
                        
                        # Ensure target row exists
                        while len(grid) <= target_r:
                            grid.append([])
                        
                        # Ensure target column exists in target row
                        while len(grid[target_r]) <= target_c:
                            grid[target_r].append("")
                        
                        # First cell gets text, others get blank
                        if dr == 0 and dc == 0:
                            grid[target_r][target_c] = text
                            logger.info(f"    -> Placed at ({target_r}, {target_c}): '{text}'")
                        else:
                            grid[target_r][target_c] = ""
                            blocked.add((target_r, target_c))
                            logger.info(f"    -> Blank at ({target_r}, {target_c}), marked blocked")
                
                # Move to next column
                col_idx += colspan
        
        # ===================================================================
        # STEP 2: Ensure all rows have same column count
        # ===================================================================
        max_cols = max(len(row) for row in grid) if grid else 0
        logger.info(f"\nMax columns: {max_cols}")
        
        for r_idx, row in enumerate(grid):
            while len(row) < max_cols:
                row.append("")
            logger.info(f"Row {r_idx}: {len(row)} columns -> {row}")
        
        # ===================================================================
        # STEP 3: Build new HTML table
        # ===================================================================
        new_table = soup.new_tag("table")
        
        for r_idx, row in enumerate(grid):
            tr_new = soup.new_tag("tr")
            
            for c_idx, cell_text in enumerate(row):
                td_new = soup.new_tag("td")
                td_new.string = cell_text if cell_text else ""
                tr_new.append(td_new)
            
            new_table.append(tr_new)
        
        logger.info("=" * 60)
        logger.info(f"FINAL TABLE: {len(grid)} rows × {max_cols} columns")
        logger.info("=" * 60)
        
        # Replace original
        table.replace_with(new_table)
    
    return str(soup)


# =====================================================================
# === GEMINI 2.5 PRO WITH ENHANCED DEBUGGING ==========================
# =====================================================================
def extract_complete_content(pil_image: Image.Image, api_key: str):
    """
    Extract table with detailed logging to debug merged cell issues.
    """
    # --- KEY ROTATION ONLY FOR TABLE EXTRACTION ---
    api_key = get_next_api_key()
    genai.configure(api_key=api_key)

    logger.info(f"🔑 Using API key (rotated): {api_key[:8]}******")

    # Convert image → base64
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    model = genai.GenerativeModel("gemini-2.5-pro",
                                  generation_config={"temperature": 0.0})

    logger.info("🔹 Gemini 2.5 Pro table extraction starting")

    prompt = """
Extract the table from the image as HTML with ACCURATE rowspan and colspan attributes.

CRITICAL INSTRUCTIONS FOR MERGED CELLS:

1. **Vertical Merges (VERY IMPORTANT):**
   - If a cell in the image spans DOWN across multiple rows, use rowspan="N"
   - Look carefully at cell borders - if a cell has NO bottom border but cells beside it do, that cell continues down
   - Example: If "गोखुर झील" in row 0 has no bottom border but extends to row 1, use rowspan="2"

2. **Horizontal Merges:**
   - If a cell spans across multiple columns, use colspan="N"
   - Look for cells that are wider than others in the same row

3. **Combined Merges:**
   - A cell can have BOTH rowspan AND colspan if it spans down AND across
   - Example: <td rowspan="2" colspan="2">Cell Text</td>

4. **HTML Structure Rules:**
   - When a cell has rowspan="2", the next row should have FEWER cells in that column position
   - Use only: <table>, <tr>, <td>, <th>
   - NO markdown, NO code fences, NO explanations

5. **Example of CORRECT rowspan usage:**
   ```
   <tr>
     <td rowspan="2">Header A</td>
     <td>Header B</td>
   </tr>
   <tr>
     <!-- Header A continues here, so NO cell in column 0 -->
     <td>Data B</td>
   </tr>
   ```

PAY SPECIAL ATTENTION to the first few rows - they often contain headers that span multiple rows.

Output MUST start with <table> and end with </table>.
"""

    try:
        resp = model.generate_content([
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": img_b64}},
        ])

        text = getattr(resp, "text", "").strip()

        # Remove markdown formatting
        if text.startswith("```html"):
            text = text[7:].strip()
        if text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()

        # Log raw HTML from Gemini
        logger.info("\n" + "=" * 80)
        logger.info("RAW HTML FROM GEMINI:")
        logger.info("=" * 80)
        logger.info(text[:1000])  # First 1000 chars
        logger.info("=" * 80)

        # Normalize merged cells
        if "<table" in text.lower():
            logger.info("📊 Starting merged cell normalization...")
            text = normalize_merged_cells(text)
            logger.info("✅ Normalization complete")

        # Basic formatting
        text = _enhance_formatting(text)

        logger.info(f"✅ Final table length: {len(text)} characters")

        return text or ""

    except Exception as e:
        logger.exception(f"Gemini 2.5 Pro extraction failed: {e}")
        return ""


# =====================================================================
# === FORMATTING ENHANCER ============================================
# =====================================================================
def _enhance_formatting(text: str) -> str:
    """Basic cleanup after extraction."""
    if not text:
        return text

    import re

    lines = text.split("\n")
    cleaned = []

    for line in lines:
        line = line.strip()
        if not line:
            cleaned.append("")
            continue

        bullets = ['◆', '•', '○', '▸', '◾', '▪', '–', '—']
        for b in bullets:
            line = re.sub(rf"{b}([^\s])", rf"{b} \1", line)

        line = re.sub(r"(\d+\.)([^\s])", r"\1 \2", line)
        line = re.sub(r"([^\s])–([^\s])", r"\1 – \2", line)

        cleaned.append(line)

    result = "\n".join(cleaned)
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


# =====================================================================
# BACKWARD COMPATIBILITY
# =====================================================================
def extract_table_text(pil_image: Image.Image, api_key: str):
    return extract_complete_content(pil_image, api_key)