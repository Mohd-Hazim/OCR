"""
core/ocr_engine_gemini.py - ENHANCED MATH FORMULA SUPPORT
-------------------------
Gemini Flash OCR with proper LaTeX extraction for math formulas
"""

import io
import base64
import logging
from PIL import Image
import google.generativeai as genai
from core.postprocess import normalize_bullets, convert_latex_to_mathml

logger = logging.getLogger(__name__)

# 🔥 NEW: round-robin API key provider
try:
    from core.gemini_pro_client import get_next_api_key
except ImportError:
    def get_next_api_key():
        return None


def run_gemini_ocr(pil_image: Image.Image, api_key: str, model_name: str):
    """
    Run OCR using Gemini API with enhanced math formula support.

    NOTE:
        - The 'api_key' argument is intentionally ignored.
        - Instead, we ALWAYS use round-robin API rotation.
    """

    if not model_name:
        logger.error("Gemini OCR failed: model_name not provided.")
        return "[Model not specified]", 0.0

    # 🔥 ROUND-ROBIN API KEY — only source
    selected_key = get_next_api_key()
    if not selected_key:
        logger.error("❌ No API key available from round-robin provider.")
        return "[Gemini OCR ERROR: missing API key]", 0.0

    logger.info(f"🔑 Using API key (RR): {selected_key[:6]}…  model={model_name}")

    try:
        # Configure the Gemini client
        genai.configure(api_key=selected_key)

        # Convert image to Base64
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        logger.info(f"🔹 Gemini OCR started using model: {model_name}")

        model = genai.GenerativeModel(model_name)

        # ENHANCED PROMPT FOR MATH FORMULAS
        prompt = """Extract all text exactly as shown in the image, including mathematical formulas.

CRITICAL RULES FOR MATH FORMULAS:

1. **Mathematical Notation**: 
   - Use LaTeX notation for all math expressions
   - Inline: wrap in $...$
   - Display: wrap in $$...$$

2. **Formula Rules**:
   - Superscripts: x^2
   - Subscripts: a_i
   - Fractions: \\frac{a}{b}
   - Sums: \\sum_{i=1}^{n}
   - Integrals: \\int_{0}^{1}
   - Greek: \\alpha, \\beta, \\theta
   - Auto parentheses: \\left( ... \\right)

3. **Text**:
   - Preserve Hindi + English exactly
   - Preserve bullets • - *
   - Preserve line breaks

NOW EXTRACT:
"""

        response = model.generate_content([
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": img_b64}},
        ])

        text = getattr(response, "text", "").strip()

        if not text:
            logger.warning("Gemini returned empty response")
            return "", 0.0

        # ─────────────────────────────────────────────
        # POST-PROCESSING PIPELINE (unchanged)
        # ─────────────────────────────────────────────
        text = normalize_bullets(text)
        text = convert_latex_to_mathml(text)

        from core.postprocess import render_latex_to_image, convert_mathml_to_omml
        import re, tempfile, os

        # Math detection
        if re.search(r'\$.*?\$', text):
            latex_exprs = re.findall(r'\$+([^$]+)\$+', text)
            images = []
            omml_versions = []

            for expr in latex_exprs:
                temp_path = os.path.join(tempfile.gettempdir(), f"math_{hash(expr)}.png")
                img_path = render_latex_to_image(expr, temp_path)
                if img_path:
                    images.append(img_path)
                omml_versions.append(convert_mathml_to_omml(expr))

            logger.info(f"Generated {len(images)} math previews and OMML data")

            return {
                "text": text,
                "math_images": images,
                "math_omml": omml_versions
            }, None

        logger.info(f"✅ Gemini OCR completed ({len(text)} chars)")
        logger.debug(f"Math formulas detected: {text.count('<math')}")

        return text, None

    except Exception as e:
        logger.exception(f"Gemini OCR failed: {e}")
        return "[Gemini OCR ERROR]", 0.0
