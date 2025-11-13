# utils/autostart.py
import os
import sys
import winreg
import logging

logger = logging.getLogger(__name__)

def is_auto_start_enabled(app_name="OCRApp"):
    """Check if auto-start is already enabled."""
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as reg_key:
            value, _ = winreg.QueryValueEx(reg_key, app_name)
            exe_path = os.path.abspath(sys.argv[0])
            return os.path.samefile(value, exe_path)
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.warning(f"Auto-start check failed: {e}")
        return False


def enable_auto_start(app_name="OCRApp"):
    """Add this app to Windows startup (current user)."""
    try:
        exe_path = os.path.abspath(sys.argv[0])
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as reg_key:
            winreg.SetValueEx(reg_key, app_name, 0, winreg.REG_SZ, exe_path)
        logger.info(f"Auto-start enabled for {app_name}: {exe_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to enable auto-start: {e}")
        return False


def disable_auto_start(app_name="OCRApp"):
    """Remove app from startup registry."""
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as reg_key:
            winreg.DeleteValue(reg_key, app_name)
        logger.info(f"Auto-start disabled for {app_name}")
        return True
    except FileNotFoundError:
        logger.warning("Auto-start entry not found.")
        return False
    except Exception as e:
        logger.error(f"Failed to disable auto-start: {e}")
        return False
