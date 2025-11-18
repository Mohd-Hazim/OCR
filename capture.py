import ctypes
import logging
from PIL import Image
from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import QPoint

logger = logging.getLogger(__name__)


def debug_monitor_setup():
    """Print detailed information about all monitors."""
    print("\n" + "=" * 80)
    print("MONITOR CONFIGURATION DEBUG")
    print("=" * 80)
    
    # Qt screens
    screens = QGuiApplication.screens()
    print(f"\nQt detected {len(screens)} screen(s):")
    for i, screen in enumerate(screens):
        geo = screen.geometry()
        dpr = screen.devicePixelRatio()
        phys_size = screen.physicalSize()
        print(f"\n  Screen {i} ({screen.name()}):")
        print(f"    Logical:  ({geo.x():>5}, {geo.y():>5}) → ({geo.x()+geo.width():>5}, {geo.y()+geo.height():>5})")
        print(f"    Size:     {geo.width()} x {geo.height()} (logical pixels)")
        print(f"    DPR:      {dpr}")
        print(f"    Physical: {phys_size.width():.1f} x {phys_size.height():.1f} mm")
    
    # Windows virtual screen
    try:
        user32 = ctypes.windll.user32
        virt_left = user32.GetSystemMetrics(76)
        virt_top = user32.GetSystemMetrics(77)
        virt_width = user32.GetSystemMetrics(78)
        virt_height = user32.GetSystemMetrics(79)
        print(f"\nWindows Virtual Screen:")
        print(f"  Position: ({virt_left}, {virt_top})")
        print(f"  Size:     {virt_width} x {virt_height}")
    except:
        print("\n  (Windows metrics unavailable)")
    
    # MSS monitors
    try:
        import mss
        with mss.mss() as sct:
            print(f"\nMSS detected {len(sct.monitors)-1} monitor(s):")
            for i, mon in enumerate(sct.monitors):
                if i == 0:
                    print(f"  Monitor {i} (ALL): {mon}")
                else:
                    print(f"  Monitor {i}: {mon}")
    except ImportError:
        print("\n  MSS not installed")
    except Exception as e:
        print(f"\n  MSS error: {e}")
    
    print("=" * 80 + "\n")


def test_point_detection(x, y):
    """Test which monitor a point is detected on."""
    print(f"\nTesting point ({x}, {y}):")
    
    point = QPoint(int(x), int(y))
    screen = QGuiApplication.screenAt(point)
    
    if screen:
        screens = QGuiApplication.screens()
        idx = screens.index(screen)
        geo = screen.geometry()
        print(f"  Qt detected: Monitor {idx} ({screen.name()})")
        print(f"  Screen bounds: ({geo.x()}, {geo.y()}) to ({geo.x()+geo.width()}, {geo.y()+geo.height()})")
        print(f"  Point is at: ({x - geo.x()}, {y - geo.y()}) relative to screen")
        return idx, screen, geo
    else:
        print(f"  Qt could NOT detect screen for this point!")
        return None, None, None


def capture_region(x, y, w, h):
    """
    Debug version of capture_region with extensive logging.
    """
    print("\n" + "=" * 80)
    print("CAPTURE REQUEST")
    print("=" * 80)
    print(f"Input coordinates: x={x}, y={y}, w={w}, h={h}")
    
    # Validate input
    if w <= 0 or h <= 0:
        print(f"ERROR: Invalid dimensions {w}x{h}")
        return None
    
    # Test point detection
    idx, screen, screen_geo = test_point_detection(x, y)
    
    if not screen or not screen_geo:
        print("ERROR: Could not determine screen")
        return None
    
    dpr = screen.devicePixelRatio()
    print(f"\nCapture plan:")
    print(f"  Target monitor: {idx}")
    print(f"  DPR: {dpr}")
    print(f"  Logical coords: ({x}, {y}) {w}x{h}")
    print(f"  Physical coords: ({int(x*dpr)}, {int(y*dpr)}) {int(w*dpr)}x{int(h*dpr)}")
    
    # Try each method with detailed logging
    print("\n" + "-" * 80)
    img = _try_mss_capture_debug(x, y, w, h, idx, screen_geo, dpr)
    if img:
        print("=" * 80 + "\n")
        return img
    
    print("\n" + "-" * 80)
    # DISABLE DXCAM (GPU) FOR CPU-ONLY MODE
    img = None
    img = _try_dxcam_capture_debug(x, y, w, h, idx, dpr)
    
    print("\n" + "-" * 80)
    img = _try_qt_capture_debug(x, y, w, h, screen, screen_geo)
    if img:
        print("=" * 80 + "\n")
        return img
    
    print("\n❌ ALL CAPTURE METHODS FAILED")
    print("=" * 80 + "\n")
    return None


def _try_mss_capture_debug(x, y, w, h, monitor_idx, screen_geo, dpr):
    """MSS capture with detailed logging and robust global-coords-first strategy."""
    print("METHOD 1: MSS (global-first)")
    try:
        import mss
    except ImportError:
        print("  ❌ MSS not installed (pip install mss)")
        return None

    try:
        with mss.mss() as sct:
            # Show monitors for debugging
            print(f"  MSS monitors available: {len(sct.monitors)-1}")
            for i, mon in enumerate(sct.monitors):
                if i == 0:
                    print(f"    Monitor {i} (ALL): {mon}")
                else:
                    print(f"    Monitor {i}: {mon}")

            # Ensure ints
            x_i = int(round(x))
            y_i = int(round(y))
            w_i = max(1, int(round(w)))
            h_i = max(1, int(round(h)))

            # First, try a GLOBAL grab using the coordinates as-is.
            # MSS accepts a region anywhere on the virtual desktop.
            global_region = {"left": x_i, "top": y_i, "width": w_i, "height": h_i}
            print(f"  Attempting MSS global grab: {global_region}")
            try:
                sct_img = sct.grab(global_region)
                if sct_img and sct_img.size[0] == w_i and sct_img.size[1] == h_i:
                    print(f"  ✅ MSS GLOBAL SUCCESS: {sct_img.size}")
                    img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                    return img
                else:
                    # If sizes mismatch (possible DPR differences), still convert what we got
                    if sct_img:
                        print(f"  ⚠️ MSS global returned different size: {sct_img.size}")
                        img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                        return img
            except Exception as e:
                print(f"  ⚠️ MSS global grab failed: {e}")

            # ---- Fallback: per-monitor mapping (defensive) ----
            print("  Falling back to per-monitor mapping...")

            # Find the MSS monitor that contains the point (x,y) in global coords
            chosen_idx = None
            for i, mon in enumerate(sct.monitors):
                if i == 0:
                    continue
                # Accept coordinates in same coordinate space as MSS monitor dict
                if (mon["left"] <= x_i < mon["left"] + mon["width"] and
                        mon["top"] <= y_i < mon["top"] + mon["height"]):
                    chosen_idx = i
                    break

            if chosen_idx is None:
                print("  ⚠️ Could not find a per-monitor match; using primary monitor (1) as fallback")
                chosen_idx = 1 if len(sct.monitors) > 1 else 0

            mon = sct.monitors[chosen_idx]
            print(f"  Using MSS monitor {chosen_idx}: {mon}")

            # Compute capture using global coords relative to the MSS monitor
            rel_x = x_i - mon["left"]
            rel_y = y_i - mon["top"]

            capture_region = {
                "left": mon["left"] + rel_x,
                "top": mon["top"] + rel_y,
                "width": w_i,
                "height": h_i,
            }

            # This is basically the same as global_region, kept for clarity and diagnostics.
            print(f"  MSS per-monitor capture region: {capture_region}")

            # Sanity checks
            if capture_region["left"] < mon["left"] or capture_region["top"] < mon["top"]:
                print("  ⚠️ Capture region starts before monitor bounds!")
            if (capture_region["left"] + capture_region["width"] > mon["left"] + mon["width"] or
                capture_region["top"] + capture_region["height"] > mon["top"] + mon["height"]):
                print("  ⚠️ Capture region extends beyond monitor bounds!")

            # Final attempt
            try:
                sct_img = sct.grab(capture_region)
                if not sct_img:
                    print("  ❌ MSS grab returned None in fallback")
                    return None
                print(f"  MSS grabbed: {sct_img.size}")
                img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                print(f"  ✅ MSS SUCCESS (fallback): {img.size}")
                return img
            except Exception as e:
                print(f"  ❌ MSS exception in fallback: {e}")
                import traceback
                traceback.print_exc()
                return None

    except Exception as e:
        print(f"  ❌ MSS outer exception: {e}")
        import traceback
        traceback.print_exc()

    return None

def _try_dxcam_capture_debug(x, y, w, h, monitor_idx, dpr):
    """dxcam capture with detailed logging."""
    print("METHOD 2: DXCAM")
    
    try:
        import dxcam
    except ImportError:
        print("  ❌ dxcam not installed (pip install dxcam)")
        return None
    
    try:
        # Physical coordinates
        phys_x = int(x * dpr)
        phys_y = int(y * dpr)
        phys_w = int(w * dpr)
        phys_h = int(h * dpr)
        
        print(f"  Creating camera for monitor {monitor_idx}")
        cam = dxcam.create(output_idx=monitor_idx, output_color="BGR")
        
        if not cam:
            print(f"  ❌ Failed to create dxcam camera")
            return None
        
        print(f"  Camera created successfully")
        print(f"  Logical coords: ({x}, {y}) {w}x{h}")
        print(f"  Physical coords: ({phys_x}, {phys_y}) {phys_w}x{phys_h}")
        
        region = (phys_x, phys_y, phys_x + phys_w, phys_y + phys_h)
        print(f"  dxcam region: {region}")
        
        print(f"  Attempting dxcam grab...")
        frame = cam.grab(region=region)
        
        if frame is None:
            print(f"  ❌ dxcam grab returned None")
            return None
        
        print(f"  dxcam grabbed: {frame.shape}")
        
        # Convert to PIL
        import cv2
        scale = 1.8
        h_frame, w_frame = frame.shape[:2]
        frame_up = cv2.resize(frame, (int(w_frame * scale), int(h_frame * scale)), 
                              interpolation=cv2.INTER_CUBIC)
        img = Image.fromarray(frame_up[..., ::-1])
        
        print(f"  ✅ DXCAM SUCCESS: {img.size} (upscaled {scale}x)")
        return img
        
    except Exception as e:
        print(f"  ❌ dxcam exception: {e}")
        import traceback
        traceback.print_exc()
    
    return None


def _try_qt_capture_debug(x, y, w, h, screen, screen_geo):
    """Qt capture with detailed logging."""
    print("METHOD 3: QT SCREEN GRAB")
    
    try:
        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import QBuffer
        from io import BytesIO
        
        # Calculate screen-relative coordinates
        local_x = x - screen_geo.x()
        local_y = y - screen_geo.y()
        
        print(f"  Screen geometry: ({screen_geo.x()}, {screen_geo.y()}) {screen_geo.width()}x{screen_geo.height()}")
        print(f"  Global coords: ({x}, {y})")
        print(f"  Local coords: ({local_x}, {local_y})")
        
        # Clamp to bounds
        if local_x < 0:
            print(f"  ⚠️  local_x={local_x} < 0, clamping")
            adj = -local_x
            local_x = 0
            w = max(0, w - adj)
        
        if local_y < 0:
            print(f"  ⚠️  local_y={local_y} < 0, clamping")
            adj = -local_y
            local_y = 0
            h = max(0, h - adj)
        
        w = min(w, screen_geo.width() - local_x)
        h = min(h, screen_geo.height() - local_y)
        
        print(f"  Clamped dimensions: ({local_x}, {local_y}) {w}x{h}")
        
        if w <= 0 or h <= 0:
            print(f"  ❌ Invalid dimensions after clamp")
            return None
        
        print(f"  Attempting Qt grabWindow...")
        qpix = screen.grabWindow(0, local_x, local_y, w, h)
        
        if qpix.isNull():
            print(f"  ❌ grabWindow returned null pixmap")
            return None
        
        print(f"  Qt grabbed: {qpix.width()}x{qpix.height()}")
        
        # Convert to PIL
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        qpix.save(buffer, "PNG")
        
        pil_img = Image.open(BytesIO(buffer.data()))
        pil_img = pil_img.convert("RGB")
        
        print(f"  ✅ QT SUCCESS: {pil_img.size}")
        return pil_img
        
    except Exception as e:
        print(f"  ❌ Qt exception: {e}")
        import traceback
        traceback.print_exc()
    
    return None


# Call this at app startup to see your monitor configuration
def initialize_capture_debug():
    """Call this once at startup to see monitor configuration."""
    debug_monitor_setup()