# core/ocr_translate.py (GEMINI-ONLY BUILD)
"""
OCR text extraction and translation (online only).

✔ Tesseract fully removed
✔ Uses Gemini OCR through core.ocr_engine.run_ocr
✔ Translation still uses Google Translate (same as before)
"""

import logging
from PIL import Image

logger = logging.getLogger(__name__)

# Import Gemini-driven OCR
try:
    from core.ocr_engine import run_ocr
except Exception:
    run_ocr = None


# -------------------------------------------------------------------------
def extract_text(image: Image.Image, lang: str = "eng+hin") -> str:
    """
    Extract text using GEMINI ONLY (calls run_ocr).
    Tesseract has been fully removed.
    """
    if image is None:
        logger.error("extract_text called with None image.")
        return ""

    if not run_ocr:
        logger.error("run_ocr not available — Gemini OCR module missing.")
        return ""

    try:
        text, _ = run_ocr(image, langs=lang)
        if not text:
            logger.warning("Gemini OCR returned empty text.")
            return ""
        logger.info(f"OCR extracted {len(text)} characters using Gemini OCR.")
        return text.strip()
    except Exception as e:
        logger.error(f"Gemini OCR failed inside extract_text: {e}")
        return ""


# -------------------------------------------------------------------------
# Google Translate support remains unchanged
# -------------------------------------------------------------------------
try:
    from googletrans import Translator as GoogleTranslator
    _HAS_GOOGLETRANS = True
except Exception:
    _HAS_GOOGLETRANS = False
    logger.warning("googletrans not available. Translation will be disabled.")


def translate_text(text: str, dest_lang: str = "en", mode: str = "auto") -> str:
    """
    Translate text using Google Translate only.
    Reads 'translation_mode' from config.json if available.
    """
    if not text:
        logger.warning("translate_text called with empty text.")
        return ""

    # --- Read mode from config if available ---
    if mode == "auto":
        try:
            from utils.config import load_config
            cfg = load_config()
            mode = cfg.get("translation_mode", "online")
        except Exception:
            mode = "online"

    if mode != "online":
        logger.warning("Offline translation is disabled. Forcing mode=online.")

    if not _HAS_GOOGLETRANS:
        logger.error("Google Translate not available. Install 'googletrans==4.0.0-rc1'.")
        return ""

    try:
        translator = GoogleTranslator()
        translated = translator.translate(text, dest=dest_lang)
        translated_text = translated.text
        logger.info(f"Translation success (Google): {translated.src} → {dest_lang}")
        return translated_text
    except Exception as e:
        logger.error(f"Google Translate failed: {e}")
        return ""
