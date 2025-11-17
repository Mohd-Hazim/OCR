# test_fixes.py - Run this to verify all fixes work correctly
"""
Diagnostic tool to test:
1. ESC button instant response
2. Multi-monitor mode selector positioning
3. Shortcut key handling
"""

import sys
import time
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QTextEdit
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication


class DiagnosticWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OCR App Diagnostics")
        self.setGeometry(100, 100, 600, 500)
        
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("🔧 OCR App Diagnostics")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # Test buttons
        self.btn_test_esc = QPushButton("Test 1: ESC Response Time")
        self.btn_test_monitors = QPushButton("Test 2: Multi-Monitor Detection")
        self.btn_test_shortcuts = QPushButton("Test 3: Shortcut Keys")
        
        self.btn_test_esc.clicked.connect(self.test_esc_response)
        self.btn_test_monitors.clicked.connect(self.test_monitors)
        self.btn_test_shortcuts.clicked.connect(self.test_shortcuts)
        
        layout.addWidget(self.btn_test_esc)
        layout.addWidget(self.btn_test_monitors)
        layout.addWidget(self.btn_test_shortcuts)
        
        # Results display
        self.results = QTextEdit()
        self.results.setReadOnly(True)
        self.results.setStyleSheet("background: #1E1E1E; color: #D4D4D4; font-family: monospace; padding: 10px;")
        layout.addWidget(self.results)
        
        self.log("✅ Diagnostics ready. Click a test button to begin.")
    
    def log(self, message):
        """Add message to results display."""
        self.results.append(message)
        self.results.verticalScrollBar().setValue(
            self.results.verticalScrollBar().maximum()
        )
    
    def test_esc_response(self):
        """Test ESC key response time."""
        self.log("\n" + "="*60)
        self.log("TEST 1: ESC RESPONSE TIME")
        self.log("="*60)
        
        self.log("Instructions:")
        self.log("1. Overlay will appear in 2 seconds")
        self.log("2. Press ESC immediately when you see it")
        self.log("3. We'll measure response time")
        self.log("\nPreparing test...")
        
        QTimer.singleShot(2000, self._show_test_overlay)
    
    def _show_test_overlay(self):
        """Show test overlay for ESC timing."""
        from gui.overlay import SelectionOverlay
        
        self.log("✅ Overlay shown - Press ESC now!")
        self.overlay_start_time = time.time()
        
        # Create test overlay
        self.test_overlay = SelectionOverlay(self)
        self.test_overlay.parent_window = self
        
        # Override keyPressEvent to measure timing
        original_key_event = self.test_overlay.keyPressEvent
        
        def timed_key_event(event):
            if event.key() == Qt.Key_Escape:
                response_time = (time.time() - self.overlay_start_time) * 1000
                self.log(f"\n⏱️  ESC Response Time: {response_time:.1f}ms")
                
                if response_time < 100:
                    self.log("✅ EXCELLENT: Instant response (<100ms)")
                elif response_time < 250:
                    self.log("✅ GOOD: Fast response (<250ms)")
                elif response_time < 500:
                    self.log("⚠️  ACCEPTABLE: Noticeable delay (<500ms)")
                else:
                    self.log("❌ SLOW: Needs optimization (>500ms)")
            
            original_key_event(event)
        
        self.test_overlay.keyPressEvent = timed_key_event
        self.test_overlay.showFullDesktop()
    
    def test_monitors(self):
        """Test multi-monitor detection."""
        self.log("\n" + "="*60)
        self.log("TEST 2: MULTI-MONITOR DETECTION")
        self.log("="*60)
        
        screens = QGuiApplication.screens()
        self.log(f"\n📺 Detected {len(screens)} screen(s):\n")
        
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            dpr = screen.devicePixelRatio()
            
            self.log(f"Screen {i}: {screen.name()}")
            self.log(f"  Position: ({geo.x()}, {geo.y()})")
            self.log(f"  Size: {geo.width()} x {geo.height()}")
            self.log(f"  DPR: {dpr}")
            self.log(f"  Primary: {'Yes' if screen == QGuiApplication.primaryScreen() else 'No'}")
            self.log("")
        
        # Test cursor position detection
        from PySide6.QtGui import QCursor
        cursor_pos = QCursor.pos()
        current_screen = QGuiApplication.screenAt(cursor_pos)
        
        if current_screen:
            self.log(f"🖱️  Mouse is currently on: {current_screen.name()}")
            screens_list = QGuiApplication.screens()
            screen_index = screens_list.index(current_screen)
            self.log(f"   Screen index: {screen_index}")
        else:
            self.log("⚠️  Could not detect current screen")
        
        self.log("\nInstructions for live test:")
        self.log("1. Move this window to different monitors")
        self.log("2. Trigger capture from each screen")
        self.log("3. Verify mode selector appears on THAT screen")
        self.log("4. Check the main app logs for: 'Overlay triggered on screen: ...'")
        
        if len(screens) == 1:
            self.log("\n✅ Single monitor setup - no issues expected")
        else:
            self.log("\n✅ Multi-monitor detected - verify selector follows mouse")
    
    def test_shortcuts(self):
        """Test shortcut key configuration."""
        self.log("\n" + "="*60)
        self.log("TEST 3: SHORTCUT KEY TESTING")
        self.log("="*60)
        
        # Load config
        try:
            from utils.config import load_config
            config = load_config()
            
            text_sc = config.get("shortcut_text", "alt+t+1")
            table_sc = config.get("shortcut_table", "alt+t+2")
            popup_sc = config.get("shortcut_popup", "alt+t+p")
            
            self.log(f"\n⌨️  Current shortcuts:")
            self.log(f"  Text capture:  {text_sc}")
            self.log(f"  Table capture: {table_sc}")
            self.log(f"  Mode popup:    {popup_sc}")
            
            self.log("\n📋 Testing shortcut format:")
            
            def test_shortcut(name, shortcut):
                parts = shortcut.split("+")
                if len(parts) < 2:
                    self.log(f"  ❌ {name}: Invalid format (too short)")
                    return False
                
                if "alt" not in parts:
                    self.log(f"  ⚠️  {name}: No Alt modifier")
                    return False
                
                non_mod_keys = [k for k in parts if k not in ("alt", "ctrl", "shift")]
                if len(non_mod_keys) < 1:
                    self.log(f"  ❌ {name}: No actual keys")
                    return False
                
                self.log(f"  ✅ {name}: Valid ({len(non_mod_keys)} key(s))")
                return True
            
            text_ok = test_shortcut("Text", text_sc)
            table_ok = test_shortcut("Table", table_sc)
            popup_ok = test_shortcut("Popup", popup_sc)
            
            if text_ok and table_ok and popup_ok:
                self.log("\n✅ All shortcuts configured correctly")
            else:
                self.log("\n⚠️  Some shortcuts need fixing")
            
            self.log("\n📝 Manual test instructions:")
            self.log("1. Ensure main app is running")
            self.log("2. Try each shortcut:")
            self.log(f"   - Press {text_sc} (should open TEXT overlay)")
            self.log(f"   - Press {table_sc} (should open TABLE overlay)")
            self.log(f"   - Press {popup_sc} (should show mode menu)")
            self.log("3. Check app logs for 'Key buffer: ...' messages")
            self.log("4. If shortcuts don't work, check:")
            self.log("   - Alt key is being held while typing")
            self.log("   - Keys are pressed within 800ms window")
            self.log("   - No other app is capturing global hotkeys")
            
        except Exception as e:
            self.log(f"❌ Failed to load config: {e}")
    
    def on_selection_made(self, rect):
        """Handle overlay selection (for ESC test)."""
        self.log(f"✅ Selection made (test completed)")


def main():
    """Run diagnostic tests."""
    app = QApplication(sys.argv)
    
    window = DiagnosticWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()