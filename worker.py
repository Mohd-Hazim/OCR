# core/worker.py (updated - only small changes)
"""
core/worker.py
----------------
Background worker for OCR operations.
"""
import logging
import tempfile
import os
from PySide6.QtCore import QObject, Signal, Slot

from core.ocr_engine import run_ocr
from core.ocr_translate import translate_text
from utils.config import load_config, get_config_value

# NEW imports for mode-specific postprocessing
from core.postprocess import (
    clean_text_mode_output,
    clean_table_mode_output,
    clean_math_mode_output,
)

logger = logging.getLogger(__name__)


# core/worker.py - Add this __init__ method to OCRWorker class

class OCRWorker(QObject):
    """
    Worker thread for OCR processing.
    Emits signals for progress updates, completion, and errors.
    """
    
    # Signals
    progress = Signal(int)  # Progress percentage (0-100)
    finished = Signal(str, str)  # (extracted_text, translated_text)
    failed = Signal(str)  # Error message
    
    def __init__(self, image_path, config, do_translate=False, dest_lang="en"):
        """
        Initialize OCR worker.
        
        Args:
            image_path: Path to image file or PIL Image object
            config: Configuration dictionary
            do_translate: Whether to translate the extracted text
            dest_lang: Target language for translation (e.g., "hi", "en")
        """
        super().__init__()
        
        # Load image
        if isinstance(image_path, str):
            try:
                from PIL import Image
                self.image = Image.open(image_path)
            except Exception as e:
                logger.error(f"Failed to load image from {image_path}: {e}")
                self.image = None
        elif hasattr(image_path, 'mode'):  # PIL Image check
            self.image = image_path
        else:
            logger.error(f"Invalid image_path type: {type(image_path)}")
            self.image = None
        
        self.config = config
        self.do_translate = do_translate
        self.dest_lang = dest_lang
        
        # OCR settings from config
        self.langs = config.get("languages", ["eng", "hin"])
        if isinstance(self.langs, list):
            self.langs = "+".join(self.langs)
        
        # Layout detection settings (initialized with safe defaults)
        self.layout_type = "text"  # Default: text mode
        self.layout_confidence = 1.0
        self.override_table_model = False

    # Then add the run() method from the previous artifact...

    @Slot()
    def run(self):
        """
        Perform OCR and (optionally) translation, emitting progress updates.
        Gemini-only version: No Tesseract fallback.
        """
        tmp_file = None
        try:
            if self.image is None:
                self.failed.emit("No image provided for OCR.")
                return

            # --- Step 1: Save temp file ---
            self.progress.emit(5)
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp_file = tmp.name
            self.image.save(tmp_file)
            tmp.close()
            logger.debug(f"Temporary image saved to {tmp_file}")

            # --- Step 2: Determine model override ---
            model_override = None
            if hasattr(self, 'override_table_model') and self.override_table_model:
                model_override = "gemini-2.5-pro"
                logger.info("Table mode: forcing Gemini 2.5 Pro")

            # --- Step 3: Run Gemini OCR ---
            self.progress.emit(25)
            logger.info(f"Starting OCR: langs={self.langs}, layout={self.layout_type}")
            
            text, conf = run_ocr(
                self.image,
                langs=self.langs,
                psm=6,
                layout_type=self.layout_type,
                layout_confidence=self.layout_confidence,
                model_override=model_override  # ✅ NOW DEFINED
            )

            if not text or not text.strip():
                logger.warning("Gemini OCR returned empty text")
                text = ""
            else:
                logger.info(f"OCR extracted {len(text)} characters")

            self.progress.emit(60)

            # --- Step 4: Mode-specific postprocessing ---
            try:
                if self.layout_type == "table":
                    logger.debug("Postprocess: TABLE mode pipeline")
                    text = clean_table_mode_output(text)

                else:
                    # DEFAULT = TEXT + MATH merged mode
                    logger.debug("Postprocess: merged TEXT+MATH pipeline")
                    from core.postprocess import process_ocr_text_with_math
                    text = process_ocr_text_with_math(text, for_display=True)
                    text = clean_text_mode_output(text)
                    
            except Exception as e:
                logger.exception(f"Mode-specific postprocessing failed: {e}")

            self.progress.emit(75)

            # --- Step 5: Translation (optional) ---
            translated = ""
            if self.do_translate and self.dest_lang and text.strip():
                logger.debug(f"Starting translation to {self.dest_lang}")
                try:
                    translated = translate_text(text, dest_lang=self.dest_lang)
                    if translated and translated.strip():
                        logger.info(f"Translation completed: {len(translated)} characters")
                    else:
                        logger.warning("Translation returned empty text")
                except Exception as e:
                    logger.error(f"Translation failed: {e}")
                    translated = ""
                
                self.progress.emit(95)
            else:
                self.progress.emit(90)

            # --- Step 6: Complete ---
            self.progress.emit(100)
            self.finished.emit(text, translated)
            logger.info("OCR worker completed successfully")

        except Exception as e:
            logger.exception(f"OCR worker failed: {e}")
            self.failed.emit(str(e))

        finally:
            if tmp_file and os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                    logger.debug(f"Deleted temp file: {tmp_file}")
                except Exception as cleanup_err:
                    logger.warning(f"Failed to delete temp file: {cleanup_err}")