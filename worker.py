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


class OCRWorker(QObject):
    # ... (rest unchanged) ...

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

            # --- Step 2: Run Gemini OCR ---
            self.progress.emit(25)
            text, conf = run_ocr(
                self.image,
                langs=self.langs,
                psm=6,
                layout_type=self.layout_type,
                layout_confidence=self.layout_confidence,
                model_override=model_override
            )

            if not text:
                logger.warning("Gemini OCR returned empty text.")

            # --- NEW: Mode-specific postprocessing (text/table/math) ---
            try:
                if self.layout_type == "text":
                    logger.debug("Postprocess: applying TEXT mode pipeline")
                    text = clean_text_mode_output(text)
                elif self.layout_type == "table":
                    logger.debug("Postprocess: applying TABLE mode pipeline")
                    text = clean_table_mode_output(text)
                elif self.layout_type == "math":
                    logger.debug("Postprocess: applying MATH mode pipeline")
                    # produce MathML+HTML for display
                    text = clean_math_mode_output(text, for_display=True)
                else:
                    logger.debug("Postprocess: unknown layout_type, skipping mode-specific processing")
            except Exception as e:
                logger.exception(f"Mode-specific postprocessing failed: {e}")

            # --- Step 3: Translation (optional) ---
            translated = ""
            if self.do_translate and self.dest_lang:
                logger.debug(f"Starting translation to {self.dest_lang}...")
                translated = translate_text(text, dest_lang=self.dest_lang)
                if translated.strip():
                    logger.info(f"Translation success: → {self.dest_lang}")
                else:
                    logger.warning("Translation returned empty text.")
                self.progress.emit(95)
            else:
                self.progress.emit(90)

            # --- Step 4: Finish ---
            self.progress.emit(100)
            self.finished.emit(text, translated)

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
