import io, base64, logging
from PIL import Image
import google.generativeai as genai

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------
# === GEMINI 2.5 PRO - COMPLETE FORMATTED CONTENT EXTRACTOR ==========
# --------------------------------------------------------------------
def extract_complete_content(pil_image: Image.Image, api_key: str):
    """
    Extract ALL content from image with PROPER FORMATTING.

    Features:
    - Preserves bullet points (◆, •, ○, -)
    - Preserves numbering (1., 2., etc.)
    - Maintains hierarchical structure
    - Converts tables to HTML
    - Preserves Hindi + English text
    - Maintains original layout flow
    - Improves readability when needed
    """

    if not api_key:
        raise ValueError("Gemini 2.5 Pro requires a valid API key.")

    genai.configure(api_key=api_key)

    # Convert image to base64
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    model_name = "gemini-2.5-pro"
    model = genai.GenerativeModel(model_name, generation_config={"temperature": 0.0})

    logger.info("🔹 Running Gemini 2.5 Pro for formatted content extraction")

    # Enhanced prompt for formatting preservation
    prompt = """Extract ALL visible content from this image with PROPER FORMATTING.

CRITICAL FORMATTING RULES:

1. **Bullet Points & Lists**:
   - Preserve ALL bullet symbols: ◆, •, ○, -, ▸, etc.
   - Maintain indentation levels
   - Keep numbered lists: 1., 2., 3., etc.
   - Use HTML lists when appropriate: <ul>, <ol>

2. **Structure & Hierarchy**:
   - Preserve headings and titles
   - Maintain parent-child relationships in lists
   - Keep proper spacing between sections
   - Preserve alignment (left, center, right)

3. **Tables**:
   - Convert to clean HTML <table> with proper headers
   - Preserve all rows and columns
   - Maintain cell alignment

4. **Text Content**:
   - Extract EXACT Hindi and English text
   - Preserve special characters and diacritics
   - Keep numbers and units together
   - Maintain date formats

5. **Layout Flow**:
   - Extract content in reading order (top to bottom)
   - Preserve line breaks
   - Keep related content grouped

NOW EXTRACT ALL CONTENT WITH PROPER FORMATTING:"""

    try:
        resp = model.generate_content([
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": img_b64}},
        ])

        text = getattr(resp, "text", "").strip()

        # Cleanup markdown fences
        if text.startswith("```html"):
            text = text[len("```html"):].strip()
        elif text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()

        # Post-processing
        text = _enhance_formatting(text)

        # Logging summary
        has_bullets = any(symbol in text for symbol in ["◆", "•", "○", "▸", "◾"])
        has_numbers = any(f"{i}." in text for i in range(1, 10))
        has_table = "<table" in text.lower()
        has_list = "<ul>" in text.lower() or "<ol>" in text.lower()

        logger.info(
            f"✅ Extracted: bullets={has_bullets}, numbers={has_numbers}, "
            f"table={has_table}, html_lists={has_list}, length={len(text)} chars"
        )

        return text or ""

    except Exception as e:
        logger.exception(f"Gemini 2.5 Pro extraction failed: {e}")
        return ""


# --------------------------------------------------------------------
def _enhance_formatting(text: str) -> str:
    """
    Post-process extracted text to improve formatting:
    - spacing around bullets
    - indentation cleanup
    - whitespace cleanup
    """
    if not text:
        return text

    import re

    lines = text.split('\n')
    enhanced = []

    for line in lines:
        line = line.strip()
        if not line:
            enhanced.append('')
            continue

        bullet_symbols = ['◆', '•', '○', '▸', '◾', '▪', '–', '—']
        for symbol in bullet_symbols:
            if symbol in line:
                line = re.sub(rf'{symbol}([^\s])', rf'{symbol} \1', line)

        line = re.sub(r'(\d+\.)([^\s])', r'\1 \2', line)
        line = re.sub(r'([^\s])–([^\s])', r'\1 – \2', line)

        enhanced.append(line)

    result = '\n'.join(enhanced)

    if '<table' not in result and '<ul>' not in result:
        result = re.sub(r'\n([^◆•○▸◾\d<\s])', r'\n\n\1', result)

    result = re.sub(r'\n{3,}', '\n\n', result)

    return result.strip()


# --------------------------------------------------------------------
# BACKWARD COMPATIBILITY ALIAS
# --------------------------------------------------------------------
def extract_table_text(pil_image: Image.Image, api_key: str):
    """
    Legacy function name - still returns gemini-pro content.
    """
    return extract_complete_content(pil_image, api_key)
