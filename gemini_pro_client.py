import io, base64, logging
from PIL import Image
import google.generativeai as genai

logger = logging.getLogger(__name__)

# =====================================================================
# === MERGED CELL NORMALIZER (FINAL, FIXED ROWSPAN + COLSPAN) =========
# =====================================================================
from bs4 import BeautifulSoup

def normalize_merged_cells(html: str) -> str:
    """
    Fully robust rowspan/colspan expander.
    Produces a PERFECT rectangular table:
        - Top-left cell keeps text
        - All covered cells become blank
    """

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        occ = {}       # (r,c) → text
        max_row = 0
        max_col = 0

        for r, tr in enumerate(rows):
            cells = tr.find_all(["td", "th"])
            c = 0

            for cell in cells:

                # find next empty col
                while (r, c) in occ:
                    c += 1

                txt = cell.get_text(strip=True)

                try:
                    rowspan = int(cell.get("rowspan", 1))
                except:
                    rowspan = 1

                try:
                    colspan = int(cell.get("colspan", 1))
                except:
                    colspan = 1

                # place text in the main cell
                occ[(r, c)] = txt

                # fill merged region with blanks
                for rr in range(r, r + rowspan):
                    for cc in range(c, c + colspan):
                        if (rr, cc) not in occ:
                            # blank for merged
                            occ[(rr, cc)] = ""  
                        max_row = max(max_row, rr)
                        max_col = max(max_col, cc)

                c += colspan

        # Build new normalized table
        new_table = soup.new_tag("table")

        for r in range(max_row + 1):
            tr_new = soup.new_tag("tr")
            for c in range(max_col + 1):
                td_new = soup.new_tag("td")
                td_new.string = occ.get((r, c), "")
                tr_new.append(td_new)
            new_table.append(tr_new)

        table.replace_with(new_table)

    return str(soup)


# =====================================================================
# === GEMINI 2.5 PRO - COMPLETE FORMATTED CONTENT EXTRACTOR ===========
# =====================================================================
def extract_complete_content(pil_image: Image.Image, api_key: str):
    """
    Extract table EXACTLY with rowspan/colspan from Gemini.
    Then normalize it to a perfect rectangular table.
    """

    if not api_key:
        raise ValueError("Gemini 2.5 Pro requires a valid API key.")

    genai.configure(api_key=api_key)

    # Convert image → base64
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    model = genai.GenerativeModel("gemini-2.5-pro",
                                  generation_config={"temperature": 0.0})

    logger.info("🔹 Gemini 2.5 Pro table extraction starting")

    # ------------------------------------------------------------------
    # *** MOST IMPORTANT PART: STRICT TABLE HTML OUTPUT PROMPT ***
    # ------------------------------------------------------------------
    prompt = """
Extract ONLY the table from the image as STRICT HTML.

RULES YOU MUST FOLLOW:
1. Output ONLY these tags:
   <table>, <tr>, <td>, <th> WITH correct rowspan/colspan.

2. Represent merged cells EXACTLY as in the image:
   - vertically merged → use rowspan="X"
   - horizontally merged → use colspan="X"

3. DO NOT output plain text.
   DO NOT output markdown.
   DO NOT wrap in ```html code fences.
   DO NOT add explanations.
   DO NOT add <div>, <p>, <span>, <br>, <style>.

4. Preserve ALL Hindi + English text exactly.

5. The HTML MUST start with <table> and end with </table>.

Extract the table EXACTLY as seen inside the image.
"""

    try:
        resp = model.generate_content([
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": img_b64}},
        ])

        text = getattr(resp, "text", "").strip()

        # Remove accidental markdown formatting
        if text.startswith("```html"):
            text = text[7:].strip()
        if text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()

        # ------------------------------------------------------------------
        # STEP 1 — FIRST normalize merged rows/columns
        # ------------------------------------------------------------------
        if "<table" in text.lower():
            text = normalize_merged_cells(text)

        # ------------------------------------------------------------------
        # STEP 2 — THEN formatting cleanup
        # ------------------------------------------------------------------
        text = _enhance_formatting(text)

        # Logging summary
        logger.info(
            f"✅ Table Extracted | rows/cols normalized | length={len(text)}"
        )

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
