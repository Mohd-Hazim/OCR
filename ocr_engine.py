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

# 🔥 NEW: round-robin API key provider
try:
    from core.gemini_pro_client import get_next_api_key
except ImportError:
    def get_next_api_key():
        return None


# ===================================================================
# MODEL SELECTION (Unchanged)
# ===================================================================
def select_model_for_region(image=None, layout_hint=None, layout_confidence=None):
    try:
        if get_force_gemini():
            logger.info("⚙️ Manual override → Gemini Pro")
            return "gemini-2.5-pro", {"src": "manual_override", "mode": "complete"}

        use_gemini = get_config_value("use_gemini_api", False)
        gemini_model = get_config_value("gemini_model", "gemini-2.5-flash-lite")

        logger.info(f"🔧 use_gemini_api={use_gemini}, gemini_model={gemini_model}")

        return gemini_model, {"src": "user_selection", "mode": "text"}

    except Exception as e:
        logger.exception(f"Model selection failed: {e}")
        return "gemini-2.5-flash-lite", {"src": "error", "mode": "fallback"}


# ===================================================================
# DPI helper (Unchanged)
# ===================================================================
def _get_resample_filter():
    try:
        return Image.Resampling.LANCZOS
    except Exception:
        return Image.LANCZOS


def ensure_dpi(pil_img: Image.Image, target_dpi: int = 300, min_size: int = 1000):
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
            logger.debug(f"Scaled {w}x{h} → {pil_img.size} (scale={scale:.2f})")
        except Exception as e:
            logger.warning(f"DPI scaling failed: {e}")

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
# MAIN OCR (Gemini Only) — MODIFIED FOR ROUND-ROBIN KEYS
# ===================================================================
def run_ocr(pil_image: Image.Image, langs: str = "eng+hin", psm: int = 6,
            layout_type: str = None, layout_confidence: float = None,
            model_override: str = None, api_key: str = None):
    """
    Unified OCR Pipeline — GEMINI ONLY.
    """

    if pil_image is None:
        logger.error("run_ocr called with None image.")
        return "", 0.0

    # Step 1 — model selection (unchanged)
    if model_override:
        active_model = model_override
        meta = {"src": "mode_override"}
    else:
        active_model, meta = select_model_for_region(
            image=pil_image,
            layout_hint=layout_type,
            layout_confidence=layout_confidence
        )

    logger.info(f"[OCR] Model: {active_model} | Mode: {meta.get('mode')} | Lang={langs}")

    # 🔥 NEW — Always use round-robin API key
    if api_key:
        # Worker explicitly passed a key → use it
        selected_api_key = api_key
    else:
        # Worker DIDN'T pass → rotate now
        selected_api_key = get_next_api_key()

    if not selected_api_key:
        logger.error("❌ No API key available from round-robin provider.")
        return "", 0.0

    logger.info(f"🔑 Using API key: {selected_api_key[:6]}… (round-robin)")


    # ===================================================================
    # ROUTE 1: GEMINI 2.5 PRO — unchanged except key source
    # ===================================================================
    if active_model == "gemini-2.5-pro" and extract_complete_content:
        try:
            logger.info("⚙️ Running Gemini 2.5 Pro Complete Extraction")
            text = extract_complete_content(pil_image, selected_api_key)
            if text and text.strip():
                logger.info(f"✅ Gemini Pro extracted {len(text)} chars")
                return text, 0.0
            logger.warning("Gemini Pro returned empty text")
        except Exception as e:
            logger.exception(f"Gemini 2.5 Pro failed: {e}")

    # ===================================================================
    # ROUTE 2: GEMINI FLASH/LITE — unchanged except key source
    # ===================================================================
    if active_model.startswith("gemini-") and run_gemini_ocr:
        try:
            logger.info(f"⚙️ Running Gemini OCR ({active_model}) for languages: {langs}")

            result = run_gemini_ocr(pil_image, selected_api_key, active_model)

            # Normalize output
            if isinstance(result, dict):
                text = result.get("text", "")
                conf = result.get("confidence", 0.95)
            else:
                text, conf = result

            if text and not text.startswith("[Gemini OCR ERROR]"):
                logger.info(f"✅ Gemini OCR OK ({len(text)} chars)")
                return text, conf if conf else 0.0

            logger.warning("Gemini OCR returned empty/error")

        except Exception as e:
            logger.exception(f"Gemini Flash/Lite OCR failed: {e}")

    # ===================================================================
    # END — NO FALLBACK
    # ===================================================================
    logger.error("❌ No valid OCR output from Gemini.")
    return "", 0.0
