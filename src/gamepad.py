"""
Virtual Xbox 360 gamepad manager using vgamepad (ViGEm).
Receives processed stick/button values and feeds them to the virtual controller.
"""
import logging
import time

try:
    import vgamepad as vg
    VGAMEPAD_AVAILABLE = True
except ImportError:
    VGAMEPAD_AVAILABLE = False
except Exception:
    # ViGEm bus driver not installed
    VGAMEPAD_AVAILABLE = False

logger = logging.getLogger(__name__)

# Button mapping names used in config
XBOX_BUTTONS = {
    'A': 'XUSB_GAMEPAD_A',
    'B': 'XUSB_GAMEPAD_B',
    'X': 'XUSB_GAMEPAD_X',
    'Y': 'XUSB_GAMEPAD_Y',
    'LB': 'XUSB_GAMEPAD_LEFT_SHOULDER',
    'RB': 'XUSB_GAMEPAD_RIGHT_SHOULDER',
    'Back': 'XUSB_GAMEPAD_BACK',
    'Start': 'XUSB_GAMEPAD_START',
    'LS': 'XUSB_GAMEPAD_LEFT_THUMB',
    'RS': 'XUSB_GAMEPAD_RIGHT_THUMB',
    'DPad Up': 'XUSB_GAMEPAD_DPAD_UP',
    'DPad Down': 'XUSB_GAMEPAD_DPAD_DOWN',
    'DPad Left': 'XUSB_GAMEPAD_DPAD_LEFT',
    'DPad Right': 'XUSB_GAMEPAD_DPAD_RIGHT',
}

# RC inputs that can be mapped to buttons
RC_BUTTON_SOURCES = [
    'camera_up',      # Camera wheel pushed up
    'camera_down',    # Camera wheel pushed down
    'c1',             # C1 button
    'c2',             # C2 button
    'photo',          # Photo/shutter button
    'video',          # Video record button
    'fn',             # Function button
    'scroll_up',      # Scroll wheel up
    'scroll_down',    # Scroll wheel down
]


def get_vigem_button(name: str):
    """Get the vgamepad button constant by config name."""
    if not VGAMEPAD_AVAILABLE:
        return None
    attr_name = XBOX_BUTTONS.get(name)
    if attr_name:
        return getattr(vg.XUSB_BUTTON, attr_name, None)
    return None


class VirtualGamepad:
    """
    Manages a virtual Xbox 360 controller via ViGEm.

    No background threads — call push() directly from the RC data callback.
    This eliminates lock contention and ensures every RC packet reaches ViGEm.
    """

    def __init__(self):
        self._gamepad = None
        self._initialized = False

        # Button mapping: rc_source -> xbox_button_name
        self.button_map = {
            'camera_up': 'Y',
            'camera_down': 'B',
            'c1': 'LB',
            'c2': 'RB',
            'photo': 'A',
            'video': 'X',
            'fn': 'Back',
            'scroll_up': 'DPad Up',
            'scroll_down': 'DPad Down',
        }

        # Callback for gamepad status
        self.on_error = None

    @property
    def is_available(self) -> bool:
        return VGAMEPAD_AVAILABLE

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> bool:
        """Create the virtual gamepad. Returns True on success."""
        if not VGAMEPAD_AVAILABLE:
            if self.on_error:
                self.on_error(
                    "vgamepad not available. Please install ViGEm Bus Driver "
                    "from https://github.com/nefarius/ViGEmBus/releases "
                    "and run: pip install vgamepad"
                )
            return False

        try:
            self._gamepad = vg.VX360Gamepad()
            self._gamepad.reset()
            self._gamepad.update()
            time.sleep(0.5)  # Allow Windows to recognize the device
            self._initialized = True
            logger.info("Virtual Xbox 360 gamepad created")
            return True
        except Exception as e:
            if self.on_error:
                self.on_error(f"Failed to create virtual gamepad: {e}")
            return False

    def stop(self):
        """Reset the controller on shutdown."""
        if self._gamepad:
            try:
                self._gamepad.reset()
                self._gamepad.update()
            except Exception:
                pass

    def push(self, processed: dict):
        """
        Set axes + buttons from processed RC data and push to ViGEm immediately.

        Called directly from the RC data callback — no threading, no locks.
        """
        if not self._initialized or not self._gamepad:
            return
        try:
            # Axes
            self._gamepad.left_joystick(
                processed.get('gamepad_left_x', 0),
                processed.get('gamepad_left_y', 0),
            )
            self._gamepad.right_joystick(
                processed.get('gamepad_right_x', 0),
                processed.get('gamepad_right_y', 0),
            )
            self._gamepad.left_trigger(
                max(0, min(255, processed.get('left_trigger', 0)))
            )
            self._gamepad.right_trigger(
                max(0, min(255, processed.get('right_trigger', 0)))
            )

            # Buttons: release all, then press active ones
            for xbox_name in XBOX_BUTTONS:
                btn = get_vigem_button(xbox_name)
                if btn is not None:
                    self._gamepad.release_button(btn)

            for rc_source, xbox_name in self.button_map.items():
                if processed.get(rc_source, False):
                    btn = get_vigem_button(xbox_name)
                    if btn is not None:
                        self._gamepad.press_button(btn)

            self._gamepad.update()
        except Exception as e:
            logger.error("Gamepad push error: %s", e)

    def load_from_config(self, config: dict):
        """Load button mapping from config (merges with defaults so scroll etc. aren't lost)."""
        mapping = config.get('button_mapping', {})
        if mapping:
            merged = dict(self.button_map)
            merged.update(mapping)
            self.button_map = merged

    def save_to_config(self) -> dict:
        """Export button mapping to config dict."""
        return {
            'button_mapping': dict(self.button_map),
        }
