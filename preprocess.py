# core/preprocess.py
"""
Image preprocessing for OCR (DPI-aware).

Behavior:
- If OpenCV (cv2) + numpy are available, use an OpenCV path:
    - convert to grayscale
    - normalize to 300 DPI equivalent (rescale if needed)
    - denoise (median or bilateral)
    - adaptive thresholding
    - morphological close (optional, for Hindi/Devanagari)
    - return PIL.Image (RGB) tagged with 300 DPI

- If OpenCV is not available, fall back to PIL pipeline:
    grayscale → autocontrast → sharpen → tag 300 DPI

Compatible with previous function signature:
    preprocess_image(pil_image)
"""
from typing import Optional
from PIL import Image, ImageOps, ImageFilter
import logging

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False
    cv2 = None  # type: ignore
    np = None  # type: ignore


# ---------------- DPI-Aware Scaling ----------------
def _ensure_dpi(pil_img: Image.Image, target_dpi: int = 300, min_side: int = 1000) -> Image.Image:
    """Return image scaled to roughly target_dpi and at least min_side pixels."""
    if pil_img is None:
        return None

    dpi_info = pil_img.info.get("dpi", (72, 72))
    try:
        src_dpi = float(dpi_info[0]) if dpi_info and dpi_info[0] > 0 else 72.0
    except Exception:
        src_dpi = 72.0

    scale = target_dpi / src_dpi
    w, h = pil_img.size
    if min(w, h) * scale < min_side:
        scale = max(scale, min_side / min(w, h))

    if scale > 1.0:
        new_w, new_h = int(w * scale), int(h * scale)
        try:
            resample = Image.Resampling.LANCZOS
        except Exception:
            resample = Image.LANCZOS
        pil_img = pil_img.resize((new_w, new_h), resample=resample)
        logger.debug(f"Upscaled for DPI: {w}x{h} → {new_w}x{new_h} (scale={scale:.2f})")

    try:
        pil_img.info["dpi"] = (target_dpi, target_dpi)
    except Exception:
        pass

    return pil_img


def _pil_to_cv_gray(pil_img: Image.Image) -> "np.ndarray":
    """Convert PIL image to OpenCV grayscale numpy array."""
    arr = np.array(pil_img.convert("RGB"))
    arr = arr[..., ::-1]  # RGB → BGR
    return cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)


def _cv_to_pil(gray_arr: "np.ndarray") -> Image.Image:
    """Convert single-channel OpenCV image to PIL Image (RGB)."""
    img = Image.fromarray(gray_arr).convert("RGB")
    img.info["dpi"] = (300, 300)
    return img


# ---------------- Main Entry ----------------
def preprocess_image(
    pil_image: Optional[Image.Image],
    use_opencv: bool = True,
    upscale: float = 1.5,
    denoise_ksize: int = 3,
    adaptive_thresh_block: int = 11,
    adaptive_thresh_C: int = 2,
) -> Optional[Image.Image]:
    """Preprocess a PIL image for OCR with DPI normalization."""
    if pil_image is None:
        logger.warning("preprocess_image called with None image.")
        return None

    # Normalize DPI first (affects both OpenCV and PIL paths)
    pil_image = _ensure_dpi(pil_image, target_dpi=300, min_side=1000)

    if use_opencv and _HAS_CV2:
        try:
            logger.debug("Preprocessing with OpenCV path (DPI-aware).")
            gray = _pil_to_cv_gray(pil_image)

            # Extra upscale if user requests beyond DPI normalization
            if upscale and upscale > 1.0:
                new_w, new_h = int(gray.shape[1] * upscale), int(gray.shape[0] * upscale)
                gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
                logger.debug("Additional upscale to %dx%d", new_w, new_h)

            # Denoise: bilateral preferred, fallback to median
            try:
                gray = cv2.bilateralFilter(gray, 5, 75, 75)
                logger.debug("Applied bilateral filter.")
            except Exception:
                if denoise_ksize > 1:
                    k = denoise_ksize if denoise_ksize % 2 == 1 else denoise_ksize + 1
                    gray = cv2.medianBlur(gray, k)
                    logger.debug("Applied median blur k=%d", k)

            # Morphological close (connect Hindi glyphs)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)

            # Adaptive threshold
            block = adaptive_thresh_block if adaptive_thresh_block % 2 == 1 else adaptive_thresh_block + 1
            block = max(block, 3)
            thresh = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, adaptive_thresh_C
            )

            pil_out = _cv_to_pil(thresh)
            logger.info(f"Preprocessed image (OpenCV) size={pil_out.size}, mode={pil_out.mode}")
            return pil_out

        except Exception as e:
            logger.warning("OpenCV preprocessing failed (%s): %s", type(e).__name__, e)

    # -------- PIL fallback --------
    try:
        logger.debug("Preprocessing with PIL fallback (DPI-aware).")
        img = pil_image.convert("L")
        img = ImageOps.autocontrast(img)
        img = img.filter(ImageFilter.SHARPEN)
        img.info["dpi"] = (300, 300)
        img_rgb = img.convert("RGB")
        logger.info(f"Preprocessed image (PIL fallback) size={img_rgb.size}, mode={img_rgb.mode}")
        return img_rgb
    except Exception as e:
        logger.error("Preprocessing failed: %s", e)
        return pil_image
