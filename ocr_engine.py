# core/ocr_engine.py (GEMINI-ONLY BUILD)
import logging
from PIL import Image
from utils.config import get_config_value

logger = logging.getLogger(__name__)

# --- Optional imports ---
try:
    from core.ocr_engine_gemini import run_gemini_ocr
except ImportError:
    run_gemini_ocr = None

try:
    from core.gemini_pro_client import extract_complete_content
except ImportError:
    extract_complete_content = None

try:
    from utils.config import get_force_gemini
except ImportError:
    def get_force_gemini(): return False


# ===================================================================
# MODEL SELECTION (Simplified)
# ===================================================================
def select_model_for_region(image=None, layout_hint=None, layout_confidence=None):
    """
    Behavior (unchanged):
    - If manual override enabled → Always Gemini Pro (skip detection)
    - Else:
        * If use_gemini_api=True → Use Gemini Flash/Lite
        * If use_gemini_api=False → USED TO fall back to Tesseract, now always Gemini
    """
    try:
        # 1️⃣ Manual override
        if get_force_gemini():
            logger.info("⚙️ Manual override enabled → Using Gemini Pro (auto-detection disabled).")
            return "gemini-2.5-pro", {"src": "manual_override", "mode": "complete"}

        # 2️⃣ Default user preference
        use_gemini = get_config_value("use_gemini_api", False)
        gemini_model = get_config_value("gemini_model", "gemini-2.5-flash-lite")

        logger.info(f"🔧 Config: use_gemini_api={use_gemini}, gemini_model={gemini_model}")

        # ALWAYS GEMINI
        logger.info(f"✅ Using Gemini model: {gemini_model}")
        return gemini_model, {"src": "user_selection", "mode": "text"}

    except Exception as e:
        logger.exception(f"Model selection failed: {e}")
        # fallback → still Gemini
        return "gemini-2.5-flash-lite", {"src": "error", "mode": "fallback"}


# ===================================================================
# DPI helper (kept for compatibility with your pipeline)
# ===================================================================
def _get_resample_filter():
    try:
        return Image.Resampling.LANCZOS
    except Exception:
        return Image.LANCZOS


def ensure_dpi(pil_img: Image.Image, target_dpi: int = 300, min_size: int = 1000) -> Image.Image:
    """KEEPING this unchanged because Gemini Pro extraction benefits from it."""
    if pil_img is None:
        return pil_img

    dpi_info = pil_img.info.get("dpi")
    if isinstance(dpi_info, (tuple, list)) and len(dpi_info) >= 2:
        src_dpi_x, src_dpi_y = float(dpi_info[0]), float(dpi_info[1])
    else:
        src_dpi_x = src_dpi_y = 72.0

    src_dpi = max(src_dpi_x, src_dpi_y) if src_dpi_x > 0 else 72.0
    scale = target_dpi / src_dpi

    w, h = pil_img.size
    min_side = min(w, h)
    if min_side * scale < min_size:
        scale = max(scale, min_size / min_side)

    if scale > 1.0:
        try:
            resample = _get_resample_filter()
            pil_img = pil_img.resize((int(w * scale), int(h * scale)), resample=resample)
            logger.debug(f"Scaled image {w}x{h} → {pil_img.size} (scale={scale:.2f})")
        except Exception as e:
            logger.warning(f"Failed DPI scaling: {e}")

    try:
        pil_img.info["dpi"] = (target_dpi, target_dpi)
    except Exception:
        pass

    if pil_img.mode != "RGB":
        try:
            pil_img = pil_img.convert("RGB")
        except Exception:
            pass

    return pil_img


# ===================================================================
# MAIN OCR (Gemini Only)
# ===================================================================
def run_ocr(pil_image: Image.Image, langs: str = "eng+hin", psm: int = 6,
            layout_type: str = None, layout_confidence: float = None,
            model_override: str = None):
    """
    Unified OCR Pipeline — *GEMINI ONLY*.

    ALL TESSERACT MODES REMOVED.
    """
    if pil_image is None:
        logger.error("run_ocr called with None image.")
        return "", 0.0

    # Step 1: pick active model
    if model_override:
        active_model = model_override
        meta = {"src": "mode_override"}
    else:
        active_model, meta = select_model_for_region(
            image=pil_image,
            layout_hint=layout_type,
            layout_confidence=layout_confidence
    )

    logger.info(f"[OCR] Model: {active_model} | Mode: {meta.get('mode', 'unknown')} | Language: {langs}")

    api_key = get_config_value("gemini_api_key", "")

    # ===================================================================
    # ROUTE 1: GEMINI 2.5 PRO (Manual Override) — unchanged
    # ===================================================================
    if active_model == "gemini-2.5-pro" and extract_complete_content:
        if not api_key:
            logger.error("Gemini 2.5 Pro requires API key.")
        else:
            try:
                logger.info("⚙️ Running Gemini 2.5 Pro (manual override).")
                text = extract_complete_content(pil_image, api_key)
                if text and text.strip():
                    logger.info(f"✅ Gemini Pro extraction succeeded ({len(text)} chars).")
                    return text, 0.0
                else:
                    logger.warning("Gemini Pro returned empty output.")
            except Exception as e:
                logger.exception(f"Gemini Pro failed: {e}")

    # ===================================================================
    # ROUTE 2: GEMINI FLASH/LITE — unchanged
    # ===================================================================
    if active_model.startswith("gemini-"):
        if not api_key:
            logger.error("Gemini API key missing.")
            return "", 0.0

        if run_gemini_ocr:
            try:
                logger.info(f"⚙️ Running Gemini OCR: {active_model} for {langs}")
                result = run_gemini_ocr(pil_image, api_key, active_model)

                # Normalize output (dict or tuple)
                if isinstance(result, dict):
                    text = result.get("text", "")
                    conf = result.get("confidence", 0.95)
                else:
                    text, conf = result

                if text and not text.startswith("[Gemini OCR ERROR]"):
                    logger.info(f"✅ Gemini OCR succeeded ({len(text)} chars)")
                    return text, conf if conf else 0.0
                else:
                    logger.warning("Gemini OCR returned empty/error")
            except Exception as e:
                logger.exception(f"Gemini OCR failed: {e}")

    # ===================================================================
    # END — No more Tesseract fallback
    # ===================================================================
    logger.error("❌ No valid Gemini OCR output. Returning empty text.")
    return "", 0.0
