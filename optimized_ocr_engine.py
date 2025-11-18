# core/optimized_ocr_engine.py - PERFORMANCE VERSION
"""
High-performance OCR engine with:
- Smart DPI handling (only when needed)
- Cached model selection
- Parallel processing support
- Reduced overhead
"""
import logging
from PIL import Image
from functools import lru_cache
from utils.config import get_config_value
from core.table_prompt import TABLE_EXTRACTION_PROMPT

# Correct optimized client
from core.optimized_gemini_client import (
    extract_complete_content,
    extract_text_async,
    optimize_image_for_api,
    get_next_api_key
)
logger = logging.getLogger(__name__)
# Gemini OCR engine for text
from core.ocr_engine_gemini import run_gemini_ocr

try:
    from core.ocr_engine_gemini import run_gemini_ocr
except ImportError:
    run_gemini_ocr = None

try:
    from core.optimized_gemini_client import get_next_api_key
except ImportError:
    def get_next_api_key():
        return None


# ==========================================================
# ASYNC SUPPORT FOR THREADS
# ==========================================================
import asyncio

def await_in_thread(coro):
    """
    Run an async coroutine inside a worker thread safely.
    Needed because Gemini Flash models return async coroutines.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.close()
        except:
            pass

# =====================================================================
# OPTIMIZED MODEL SELECTION (cached)
# =====================================================================

@lru_cache(maxsize=8)
def select_model_cached(layout_hint: str, force_gemini: bool) -> tuple:
    """
    Cached model selection to avoid repeated config reads.
    Returns: (model_name, metadata_dict)
    """
    if force_gemini:
        logger.debug("Using cached Gemini Pro selection")
        return "gemini-2.5-pro", {"src": "manual_override", "mode": "complete"}
    
    gemini_model = get_config_value("gemini_model", "gemini-2.5-flash-lite")
    
    if layout_hint == "table":
        return "gemini-2.5-pro", {"src": "table_mode", "mode": "complete"}
    
    return gemini_model, {"src": "user_selection", "mode": "text"}


def select_model_for_region(image=None, layout_hint=None, layout_confidence=None):
    """Public wrapper for backward compatibility."""
    try:
        from utils.config import get_force_gemini
        force_gemini = get_force_gemini()
    except:
        force_gemini = False
    
    return select_model_cached(layout_hint or "text", force_gemini)


# =====================================================================
# SMART DPI HANDLING (only upscale when needed)
# =====================================================================

def ensure_dpi_smart(pil_img: Image.Image, target_dpi: int = 300, min_size: int = 800) -> Image.Image:
    """
    Optimized DPI handling:
    - Only upscale if image is too small
    - Skip if already high resolution
    - Use faster resampling
    """
    if pil_img is None:
        return pil_img
    
    w, h = pil_img.size
    min_side = min(w, h)
    
    # Skip if already large enough
    if min_side >= min_size:
        logger.debug(f"Image size OK ({w}x{h}), skipping DPI scaling")
        return pil_img
    
    # Calculate minimal scale needed
    scale = min_size / min_side
    
    # Only scale if significant improvement (avoid 1.05x scaling)
    if scale < 1.2:
        logger.debug(f"Scale {scale:.2f}x too small, skipping")
        return pil_img
    
    # Fast upscale
    try:
        new_w, new_h = int(w * scale), int(h * scale)
        pil_img = pil_img.resize(
            (new_w, new_h), 
            Image.BILINEAR  # Faster than LANCZOS, good enough for OCR
        )
        logger.debug(f"Quick upscale: {w}x{h} → {new_w}x{new_h}")
    except Exception as e:
        logger.warning(f"DPI scaling failed: {e}")
    
    return pil_img


# =====================================================================
# MAIN OCR FUNCTION (optimized)
# =====================================================================

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
    Optimized OCR pipeline.
    
    Improvements:
    - Smart DPI handling (only when needed)
    - Cached model selection
    - Reduced logging overhead
    - Fast path for tables
    """
    
    if pil_image is None:
        logger.error("run_ocr called with None image")
        return "", 0.0
    
    # 1. Model selection (cached)
    if model_override:
        active_model = model_override
        meta = {"src": "mode_override"}
    else:
        active_model, meta = select_model_for_region(
            image=pil_image,
            layout_hint=layout_type,
            layout_confidence=layout_confidence
        )
    
    # 2. Get API key (round-robin)
    if not api_key:
        api_key = get_next_api_key()
    
    if not api_key:
        logger.error("No API key available")
        return "", 0.0
    
    if api_key == "NO_KEYS":
        return (
            "❗ API key required.\n"
            "Please add a Gemini API key in Settings.",
            0.0
        )

    if api_key == "ALL_KEYS_EXHAUSTED":
        return (
            "⛔ Daily table extraction limit reached for all API keys.\n"
            "Add another account key or please try again tomorrow.",
            0.0
        )

    logger.info(f"[OCR] Model={active_model} | Mode={meta.get('mode')}")
    
    # 3. Smart DPI handling (only if needed)
    if meta.get('mode') == 'complete':
        # Tables need higher resolution
        pil_image = ensure_dpi_smart(pil_image, target_dpi=300, min_size=1200)
    else:
        # Text can work with lower resolution
        pil_image = ensure_dpi_smart(pil_image, target_dpi=300, min_size=800)
    
    # ===================================================================
    # ROUTE 1: GEMINI PRO (Tables) - Fast path
    # ===================================================================
    if active_model == "gemini-2.5-pro" and extract_complete_content:
        try:
            logger.info("⚡ Fast table extraction (STRICT HTML MODE)")
            
            text = extract_complete_content(
                pil_image,
                api_key,
                prompt=TABLE_EXTRACTION_PROMPT   # ← STRICT PROMPT HERE
            )

            if text == "KEY_DAILY_EXHAUSTED":
                return (
                    "⚠️ This API key has exhausted its daily quota.\n"
                    "Try another key or switch model.",
                    0.0
    )

            if text and "<table" in text.lower():
                logger.info(f"✅ Strict table extracted ({len(text)} chars)")
                return text, 0.0

            logger.warning("⚠ Strict mode returned no table or empty")
        
        except Exception as e:
            logger.exception(f"Table extraction failed: {e}")
    
    # ===================================================================
    # ROUTE 2: GEMINI FLASH/LITE (Text) - Optimized
    # ===================================================================
    if active_model.startswith("gemini-") and run_gemini_ocr:
        try:
            logger.info(f"⚡ Fast text extraction ({active_model})")
            
            # Use async version if available (non-blocking)
            if meta.get("mode") == "text":
                # Always use flash-lite style extraction
                result = extract_text_async(pil_image, api_key)

                # If async coroutine → await
                if asyncio.iscoroutine(result):
                    result = await_in_thread(result)

            else:
                # TABLE mode → keep Pro model
                result = run_gemini_ocr(pil_image, api_key, active_model)

                # If coroutine → await
                if asyncio.iscoroutine(result):
                    result = await_in_thread(result)
            
            # Normalize output
            if isinstance(result, dict):
                text = result.get("text", "")
                conf = result.get("confidence", 0.95)
            else:
                text, conf = result if isinstance(result, tuple) else (result, 0.95)
            
            if text and not text.startswith("[Gemini OCR ERROR]"):
                logger.info(f"✅ Text OK ({len(text)} chars)")
                return text, conf if conf else 0.0
            
            logger.warning("Empty text result")
        
        except Exception as e:
            logger.exception(f"Text extraction failed: {e}")
    
    # ===================================================================
    # FALLBACK
    # ===================================================================
    logger.error("No valid OCR output")
    return "", 0.0


# =====================================================================
# CACHE MANAGEMENT
# =====================================================================

def clear_model_cache():
    """Clear cached model selections."""
    select_model_cached.cache_clear()
    logger.info("Cleared model selection cache")