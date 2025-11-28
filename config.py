# utils/config.py
import os
import json
import logging

# -------------------------------------------------------------
# === LOGGING SETUP ===
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, 'app.log')

# Configure logging only once (avoid re-initialization in other modules)
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ],
    )

logger = logging.getLogger("ocr_app")

# -------------------------------------------------------------
# === CONFIGURATION SETUP ===
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')

default_config = {
    "languages": ["eng", "hin"],
    "save_screenshots": False,
    "theme": "light",
    "auto_copy": False,

    # Layout persistence
    "window_width": 440,
    "window_height": 560,
    "preview_height": 210,
    "extracted_height": 180,
    "translated_height": 180,
    "splitter_sizes": [],
}


# -------------------------------------------------------------
def load_config():
    """
    Load config.json from disk.
    If missing or invalid, recreate with defaults.
    """
    if not os.path.exists(CONFIG_PATH):
        save_config(default_config)
        logger.info("Created default config.json (missing).")

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)

        # Ensure all default keys exist (safe merge)
        updated = False
        for k, v in default_config.items():
            if k not in config:
                config[k] = v
                updated = True
        if updated:
            save_config(config)

        logger.info("Configuration loaded successfully.")
        return config

    except json.JSONDecodeError:
        logger.warning("Corrupted config.json; recreating defaults.")
        save_config(default_config)
        return default_config
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return default_config

# -------------------------------------------------------------
def save_config(cfg):
    """Save a configuration dictionary to config.json."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
        logger.info("Configuration saved successfully.")
    except Exception as e:
        logger.error(f"Failed to save configuration: {e}")

# -------------------------------------------------------------
def get_config_value(key, default=None):
    """Safely retrieve a config value."""
    cfg = load_config()
    return cfg.get(key, default)

# -------------------------------------------------------------
def set_config_value(key, value):
    """Safely update a single config value."""
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)
    logger.info(f"Config updated: {key} = {value}")
