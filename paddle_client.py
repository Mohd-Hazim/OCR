# core/paddle_client.py - DEBUG VERSION (Fixed for dict results)
"""
PaddleOCR Client with extensive debugging - handles both list and dict formats.
"""
import os
import logging
import numpy as np
from paddleocr import PaddleOCR
from PIL import Image

logger = logging.getLogger(__name__)

os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"


class PaddleOCRClient:
    """Singleton PaddleOCR client with bilingual support."""
    
    _instance = None
    _lang_instances = {}

    @classmethod
    def get_instance(cls, lang='en'):
        if lang in ['hin', 'hindi', 'hi']:
            lang = 'hindi'
        elif lang in ['eng+hin', 'hin+eng', 'bilingual', 'multilingual']:
            lang = 'multilingual'
        elif lang in ['eng', 'en']:
            lang = 'en'
        
        if lang in cls._lang_instances:
            logger.debug(f"Using cached PaddleOCR instance for lang={lang}")
            return cls._lang_instances[lang]
        
        logger.info(f"Initializing PaddleOCR for language: {lang}")
        
        try:
            try:
                import paddle
                if hasattr(paddle, 'set_flags'):
                    paddle.set_flags({'FLAGS_use_mkldnn': False})
            except Exception as e:
                logger.warning(f"Could not set paddle flags: {e}")
            
            # Advanced arguments for MAXIMUM accuracy on complex/rotated text
            ocr_args = {
                'use_angle_cls': True,
                'det_db_thresh': 0.2,       # Even lower threshold to detect very faint text
                'det_db_box_thresh': 0.5,   # Threshold for text box confidence
                'det_db_unclip_ratio': 2.0, # Aggressively expand boxes to catch all Hindi matras
                'enable_mkldnn': False      # Ensure stable execution
            }

            if lang == 'multilingual':
                # Use Hindi model for multilingual as it supports both Hindi and English
                ocr = PaddleOCR(lang='hi', **ocr_args)
                logger.info("✅ PaddleOCR initialized for multilingual (using 'hi' model)")
            elif lang == 'hindi':
                ocr = PaddleOCR(lang='hi', **ocr_args)
                logger.info("✅ PaddleOCR initialized for Hindi")
            else:
                ocr = PaddleOCR(lang='en', **ocr_args)
                logger.info("✅ PaddleOCR initialized for English")
            
            cls._lang_instances[lang] = ocr
            return ocr
            
        except Exception as e:
            logger.error(f"Failed to initialize PaddleOCR: {e}")
            raise


def run_paddle_ocr(pil_image: Image.Image, lang: str = 'multilingual') -> tuple:
    """
    Run PaddleOCR with extensive debugging.
    """
    if pil_image is None:
        logger.error("run_paddle_ocr called with None image")
        return "", 0.0

    try:
        ocr = PaddleOCRClient.get_instance(lang)
        
        if pil_image.mode not in ('RGB', 'L'):
            pil_image = pil_image.convert('RGB')
        
        from PIL import ImageOps
        pil_image = ImageOps.expand(pil_image, border=10, fill='white')
        
        img_array = np.array(pil_image)
        
        logger.info(f"Running PaddleOCR with lang={lang}, image size={pil_image.size}")
        result = ocr.ocr(img_array)
        
        # ============ EXTENSIVE DEBUG LOGGING ============
        logger.info(f"🔍 DEBUG: result type = {type(result)}")
        logger.info(f"🔍 DEBUG: result = {result}")
        
        if result:
            logger.info(f"🔍 DEBUG: result is not None/empty")
            logger.info(f"🔍 DEBUG: len(result) = {len(result) if hasattr(result, '__len__') else 'N/A'}")
            
            # Check what result[0] is
            try:
                first_item = result[0]
                logger.info(f"🔍 DEBUG: result[0] type = {type(first_item)}")
                logger.info(f"🔍 DEBUG: result[0] = {first_item}")
                
                # If it's a dict, show keys
                if isinstance(first_item, dict):
                    logger.info(f"🔍 DEBUG: result[0] is a DICT with keys: {list(first_item.keys())}")
                    for key, value in first_item.items():
                        logger.info(f"🔍 DEBUG: result[0]['{key}'] type = {type(value)}")
                        logger.info(f"🔍 DEBUG: result[0]['{key}'] = {value}")
                
                # If it's a list/tuple, show first few items
                elif isinstance(first_item, (list, tuple)):
                    logger.info(f"🔍 DEBUG: result[0] is a LIST/TUPLE with {len(first_item)} items")
                    for i in range(min(3, len(first_item))):
                        logger.info(f"🔍 DEBUG: result[0][{i}] type = {type(first_item[i])}")
                        logger.info(f"🔍 DEBUG: result[0][{i}] = {first_item[i]}")
                
                # If it's something else
                else:
                    logger.info(f"🔍 DEBUG: result[0] is {type(first_item)}")
                    
            except Exception as e:
                logger.error(f"❌ Error accessing result[0]: {e}")
        # =================================================
        
        if not result:
            logger.warning("PaddleOCR returned None result")
            return "", 0.0
        
        # Check if result[0] exists and is not None
        if not result[0]:
            logger.warning("PaddleOCR result[0] is empty")
            return "", 0.0
        
        text_lines = []
        confidences = []
        
        # Try different parsing strategies based on the format
        first_item = result[0]
        
        # Strategy 1: If result[0] is a dict (new PaddleOCR format?)
        if isinstance(first_item, dict):
            logger.info("📋 Parsing as DICTIONARY format")
            
            # Try common keys
            for possible_key in ['text', 'texts', 'rec_text', 'rec_texts', 'results']:
                if possible_key in first_item:
                    data = first_item[possible_key]
                    logger.info(f"🔑 Found key '{possible_key}' with data: {data}")
                    
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, str):
                                text_lines.append(item)
                                confidences.append(1.0)
                            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                                text_lines.append(str(item[0]))
                                confidences.append(float(item[1]))
                    elif isinstance(data, str):
                        text_lines.append(data)
                        confidences.append(1.0)
                    break
        
        # Strategy 2: If result[0] is a list (traditional format)
        elif isinstance(first_item, (list, tuple)):
            logger.info("📋 Parsing as LIST/TUPLE format")
            
            for idx, line in enumerate(first_item):
                try:
                    logger.info(f"🔍 Line {idx}: type={type(line)}, value={line}")
                    
                    if not line:
                        continue
                    
                    # Traditional format: [bbox, (text, confidence)]
                    if isinstance(line, (list, tuple)) and len(line) >= 2:
                        bbox = line[0]
                        text_data = line[1]
                        
                        if isinstance(text_data, (tuple, list)) and len(text_data) >= 2:
                            text = str(text_data[0])
                            conf = float(text_data[1])
                        elif isinstance(text_data, (tuple, list)) and len(text_data) >= 2:
                            text = str(text_data[0])
                            conf = float(text_data[1])
                        elif isinstance(text_data, str):
                            text = text_data
                            conf = 1.0
                        else:
                            logger.warning(f"❌ Line {idx}: Cannot parse text_data: {text_data}")
                            continue
                        
                        if text and text.strip():
                            text_lines.append(text)
                            confidences.append(conf)
                            logger.info(f"✅ Line {idx}: '{text}' (conf={conf:.2f})")
                    
                except Exception as e:
                    logger.exception(f"❌ Error parsing line {idx}: {e}")
                    continue
        
        else:
            logger.error(f"❌ Unknown result format: {type(first_item)}")
            return "", 0.0
        
        if not text_lines:
            logger.warning("No valid text extracted after parsing")
            return "", 0.0
        
        full_text = "\n".join(text_lines)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        
        logger.info(f"✅ PaddleOCR extracted {len(text_lines)} lines, "
                   f"{len(full_text)} chars, avg confidence: {avg_conf:.2f}")
        logger.info(f"📄 Full text:\n{full_text}")
        
        return full_text, avg_conf

    except Exception as e:
        logger.exception(f"PaddleOCR failed: {e}")
        return "", 0.0


def run_paddle_ocr_multi_lang(pil_image: Image.Image, langs: list = None) -> tuple:
    """Run PaddleOCR with multiple language attempts."""
    if langs is None:
        langs = ['hindi', 'multilingual', 'en']
    
    best_text = ""
    best_conf = 0.0
    
    for lang in langs:
        try:
            text, conf = run_paddle_ocr(pil_image, lang=lang)
            
            if conf > best_conf and text.strip():
                best_text = text
                best_conf = conf
                logger.info(f"Best result so far from lang={lang}: conf={conf:.2f}")
                
        except Exception as e:
            logger.warning(f"Failed to run OCR with lang={lang}: {e}")
            continue
    
    if best_text:
        logger.info(f"✅ Multi-lang OCR complete. Best: conf={best_conf:.2f}")
    else:
        logger.warning("⚠️ Multi-lang OCR found no text")
    
    return best_text, best_conf
