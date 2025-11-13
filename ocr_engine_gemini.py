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

def run_gemini_ocr(pil_image: Image.Image, api_key: str, model_name: str):
    """
    Run OCR using Gemini API with enhanced math formula support.

    Args:
        pil_image (PIL.Image.Image): Input image for OCR.
        api_key (str): Google Gemini API key.
        model_name (str): Model name (gemini-2.5-flash-lite/flash/etc.)

    Returns:
        tuple: (extracted_text, confidence)
    """
    if not model_name:
        logger.error("Gemini OCR failed: model_name not provided.")
        return "[Model not specified]", 0.0

    try:
        genai.configure(api_key=api_key)

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
   - Inline formulas: wrap in single $ signs: $x^2 + y^2 = z^2$
   - Display formulas: wrap in double $$ signs: $$\\sum_{i=1}^{n}i^{3}=\\left(\\frac{n(n+1)}{2}\\right)^{2}$$

2. **Formula Components**:
   - Superscripts: use ^ (e.g., x^2, e^{-x})
   - Subscripts: use _ (e.g., a_i, x_{n+1})
   - Fractions: \\frac{numerator}{denominator}
   - Summation: \\sum_{lower}^{upper}
   - Integrals: \\int_{a}^{b}
   - Square roots: \\sqrt{x} or \\sqrt[n]{x}
   - Greek letters: \\alpha, \\beta, \\gamma, \\theta, \\pi, etc.
   - Parentheses: Use \\left( and \\right) for auto-sizing

3. **Text Content**:
   - Preserve bullet points exactly: •, -, *, numbers like 1., 2.
   - Keep Hindi and English text as-is
   - Maintain line breaks for lists

EXAMPLE INPUT IMAGE:
∑ᵢ₌₁ⁿ i³ = (n(n+1)/2)²

CORRECT OUTPUT:
$$\\sum_{i=1}^{n}i^{3}=\\left(\\frac{n(n+1)}{2}\\right)^{2}$$

NOW EXTRACT:"""

        response = model.generate_content([
            {"text": prompt},
            {"inline_data": {"mime_type": "image/png", "data": img_b64}},
        ])
        
        text = getattr(response, "text", "").strip()

        if not text:
            logger.warning("Gemini returned empty response")
            return "", 0.0

        # Post-processing
        if text:
            # Normalize bullets
            text = normalize_bullets(text)
            
            # Convert LaTeX to MathML
            text = convert_latex_to_mathml(text)
            from core.postprocess import render_latex_to_image, convert_mathml_to_omml
            import re, tempfile, os

            # If math is present, create image + OMML version
            if re.search(r'\$.*?\$', text):
                latex_exprs = re.findall(r'\$+([^$]+)\$+', text)
                images = []
                omml_versions = []
                for expr in latex_exprs:
                    temp_path = os.path.join(tempfile.gettempdir(), f"math_{hash(expr)}.png")
                    img_path = render_latex_to_image(expr, temp_path)
                    if img_path:
                        images.append(img_path)
                    omml_versions.append(convert_mathml_to_omml(latex_exprs[0]))

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