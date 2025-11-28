# core/ocr_engine.py - FIXED VERSION
"""
Unified OCR Engine with proper bilingual support.

Key improvements:
- Proper language mapping (eng+hin → multilingual)
- Support for multiple language modes
- Better error handling
"""

import logging
from PIL import Image
from core.paddle_client import run_paddle_ocr, run_paddle_ocr_multi_lang

logger = logging.getLogger(__name__)


def run_ocr(
    pil_image: Image.Image,
    langs: str = "eng+hin",
    psm: int = 6,
    layout_type: str = None,
    layout_confidence: float = None,
    model_override: str = None,
    api_key: str = None
) -> tuple:
    """
    Run OCR using PaddleOCR with proper bilingual support.
    
    Args:
        pil_image: Image to process
        langs: Language preference
            - "eng" or "en" → English only
            - "hin" or "hindi" → Hindi only
            - "eng+hin" or "multilingual" → Hindi+English (default)
        psm: Kept for compatibility (not used by PaddleOCR)
        layout_type: Kept for compatibility
        layout_confidence: Kept for compatibility
        model_override: Kept for compatibility
        api_key: Kept for compatibility
        
    Returns:
        tuple: (extracted_text, confidence_score)
    """
    if pil_image is None:
        logger.error("run_ocr called with None image")
        return "", 0.0
    
    # Map language codes to PaddleOCR format
    lang_map = {
        'eng': 'en',
        'en': 'en',
        'hin': 'hindi',
        'hindi': 'hindi',
        'hi': 'hindi',
        'eng+hin': 'multilingual',
        'hin+eng': 'multilingual',
        'bilingual': 'multilingual',
        'multilingual': 'multilingual',
    }
    
    # Normalize language code
    paddle_lang = lang_map.get(langs.lower(), 'multilingual')
    
    logger.info(f"Starting OCR: input_lang='{langs}' → paddle_lang='{paddle_lang}'")
    
    try:
        # Run PaddleOCR
        text, confidence = run_paddle_ocr(pil_image, lang=paddle_lang)
        
        if not text or not text.strip():
            logger.warning(f"PaddleOCR returned empty text for lang={paddle_lang}")
            
            # Try multi-language fallback for better results
            if paddle_lang == 'multilingual':
                logger.info("Trying multi-language fallback...")
                text, confidence = run_paddle_ocr_multi_lang(pil_image)
        
        return text, confidence
        
    except Exception as e:
        logger.exception(f"OCR failed: {e}")
        return "", 0.0


def run_ocr_auto(pil_image: Image.Image) -> tuple:
    """
    Run OCR with automatic language detection.
    
    Tries multiple language models and returns the best result.
    Useful when you don't know the language in advance.
    
    Args:
        pil_image: Image to process
        
    Returns:
        tuple: (extracted_text, confidence_score)
    """
    if pil_image is None:
        logger.error("run_ocr_auto called with None image")
        return "", 0.0
    
    logger.info("Running OCR with automatic language detection...")
    
    return run_paddle_ocr_multi_lang(pil_image)