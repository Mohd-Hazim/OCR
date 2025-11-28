# utils/layout_persistence.py
"""
Layout persistence manager for saving/restoring UI dimensions.
Handles window size and all resizable box heights.
"""
import logging
from utils.config import load_config, save_config

logger = logging.getLogger(__name__)


class LayoutManager:
    """Manages saving and restoring UI layout preferences."""
    
    @staticmethod
    def save_window_size(width: int, height: int):
        """Save main window dimensions."""
        config = load_config()
        config["window_width"] = width
        config["window_height"] = height
        save_config(config)
        logger.debug(f"Saved window size: {width}×{height}")
    
    @staticmethod
    def save_preview_height(height: int):
        """Save preview box height."""
        config = load_config()
        config["preview_height"] = height
        save_config(config)
        logger.debug(f"Saved preview height: {height}")
    
    @staticmethod
    def save_extracted_height(height: int):
        """Save extracted text box height."""
        config = load_config()
        config["extracted_height"] = height
        save_config(config)
        logger.debug(f"Saved extracted height: {height}")
    
    @staticmethod
    def save_translated_height(height: int):
        """Save translated text box height."""
        config = load_config()
        config["translated_height"] = height
        save_config(config)
        logger.debug(f"Saved translated height: {height}")
    
    @staticmethod
    def save_splitter_state(splitter_sizes: list):
        """Save QSplitter proportions."""
        config = load_config()
        config["splitter_sizes"] = splitter_sizes
        save_config(config)
        logger.debug(f"Saved splitter sizes: {splitter_sizes}")
    
    @staticmethod
    def get_window_size():
        """Retrieve saved window dimensions."""
        config = load_config()
        return (
            config.get("window_width", 440),
            config.get("window_height", 560)
        )
    
    @staticmethod
    def get_preview_height():
        """Retrieve saved preview height."""
        config = load_config()
        return config.get("preview_height", 210)
    
    @staticmethod
    def get_extracted_height():
        """Retrieve saved extracted text height."""
        config = load_config()
        return config.get("extracted_height", 180)
    
    @staticmethod
    def get_translated_height():
        """Retrieve saved translated text height."""
        config = load_config()
        return config.get("translated_height", 180)
    
    @staticmethod
    def get_splitter_state():
        """Retrieve saved splitter proportions."""
        config = load_config()
        return config.get("splitter_sizes", [])
    
    @staticmethod
    def save_all_sizes(window_w, window_h, preview_h, extracted_h, translated_h):
        """Batch save all sizes at once (performance optimization)."""
        config = load_config()
        config.update({
            "window_width": window_w,
            "window_height": window_h,
            "preview_height": preview_h,
            "extracted_height": extracted_h,
            "translated_height": translated_h
        })
        save_config(config)
        logger.info("✅ Saved all layout sizes in batch")