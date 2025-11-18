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

# 🔥 ADDED — round-robin key provider
from core.gemini_pro_client import get_next_api_key


logger = logging.getLogger(__name__)


class OCRWorker(QObject):
    """
    Worker thread for OCR processing.
    Emits signals for progress updates, completion, and errors.
    """
    
    # Signals
    progress = Signal(int)          # Progress percentage (0-100)
    finished = Signal(str, str)     # (extracted_text, translated_text)
    failed = Signal(str)            # Error message
    
    def __init__(self, image_path, config, do_translate=False, dest_lang="en"):
        super().__init__()
        
        # Load image
        if isinstance(image_path, str):
            try:
                from PIL import Image
                self.image = Image.open(image_path)
            except Exception as e:
                logger.error(f"Failed to load image from {image_path}: {e}")
                self.image = None
        elif hasattr(image_path, 'mode'):
            self.image = image_path
        else:
            logger.error(f"Invalid image_path type: {type(image_path)}")
            self.image = None
        
        self.config = config
        self.do_translate = do_translate
        self.dest_lang = dest_lang
        
        # OCR languages
        self.langs = config.get("languages", ["eng", "hin"])
        if isinstance(self.langs, list):
            self.langs = "+".join(self.langs)
        
        # Layout detection
        self.layout_type = "text"
        self.layout_confidence = 1.0
        self.override_table_model = False

        # 🔥 ADDED — Always rotate API keys (text & table)
        self.api_key = get_next_api_key()
        logger.info(f"[API-KEY ROTATION] Selected key: {self.api_key[:6]}…")


    @Slot()
    def run(self):
        """
        Perform OCR and (optionally) translation.
        """
        tmp_file = None
        try:
            if self.image is None:
                self.failed.emit("No image provided for OCR.")
                return

            # Step 1: Save temporary file
            self.progress.emit(5)
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp_file = tmp.name
            self.image.save(tmp_file)
            tmp.close()

            # Step 2: Determine model override
            model_override = None
            if self.override_table_model:
                model_override = "gemini-2.5-pro"

            # Step 3: Run OCR
            self.progress.emit(25)

            text, conf = run_ocr(
                self.image,
                langs=self.langs,
                psm=6,
                layout_type=self.layout_type,
                layout_confidence=self.layout_confidence,
                model_override=model_override,

                # 🔥 ADDED — pass the round-robin key
                api_key=self.api_key
            )

            if not text or not text.strip():
                text = ""

            self.progress.emit(60)

            # Step 4: Postprocessing
            try:
                if self.layout_type == "table":
                    text = clean_table_mode_output(text)
                else:
                    from core.postprocess import process_ocr_text_with_math
                    text = process_ocr_text_with_math(text, for_display=True)
                    text = clean_text_mode_output(text)
            except Exception as e:
                logger.exception(f"Postprocess failed: {e}")

            self.progress.emit(75)

            # Step 5: Translation
            translated = ""
            if self.do_translate and self.dest_lang and text.strip():
                try:
                    translated = translate_text(text, dest_lang=self.dest_lang)
                except Exception as e:
                    logger.error(f"Translation failed: {e}")
                    translated = ""
                self.progress.emit(95)
            else:
                self.progress.emit(90)

            # Step 6: Done
            self.progress.emit(100)
            self.finished.emit(text, translated)

        except Exception as e:
            logger.exception(f"OCR worker failed: {e}")
            self.failed.emit(str(e))

        finally:
            if tmp_file and os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass
