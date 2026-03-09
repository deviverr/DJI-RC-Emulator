"""
Virtual Xbox 360 gamepad manager using vgamepad (ViGEm).
Receives processed stick/button values and feeds them to the virtual controller.
"""
import logging
import time
from threading import Thread, Event, Lock

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

    Updates stick axes and button states based on processed RC input.
    Runs its own update thread for consistent gamepad reporting.
    """

    def __init__(self):
        self._gamepad = None
        self._thread: Thread | None = None
        self._stop_event = Event()
        self._lock = Lock()
        self._update_interval = 0.002  # ~500 Hz gamepad update rate
        self._initialized = False

        # Current state
        self._left_x = 0
        self._left_y = 0
        self._right_x = 0
        self._right_y = 0
        self._left_trigger = 0
        self._right_trigger = 0
        self._pressed_buttons: set = set()

        # Button mapping: rc_source -> xbox_button_name
        self.button_map = {
            'camera_up': 'Y',       # Restart race
            'camera_down': 'B',     # Recover drone
            'c1': 'LB',            # C1 → Left Bumper
            'c2': 'RB',            # C2 → Right Bumper
            'photo': 'A',          # Photo → A
            'video': 'X',          # Video → X
            'fn': 'Back',          # Fn → Back/Select
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

    def set_update_rate(self, rate_hz: float):
        """Set gamepad update rate in Hz."""
        if rate_hz > 0:
            self._update_interval = 1.0 / rate_hz

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
            time.sleep(0.5)  # Allow Windows to recognize the device
            self._initialized = True
            logger.info("Virtual Xbox 360 gamepad created")
            return True
        except Exception as e:
            if self.on_error:
                self.on_error(f"Failed to create virtual gamepad: {e}")
            return False

    def start(self):
        """Start the gamepad update thread."""
        if not self._initialized:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._update_loop, daemon=True, name="Gamepad")
        self._thread.start()

    def stop(self):
        """Stop the gamepad update thread and reset the controller."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._gamepad:
            try:
                self._gamepad.reset()
                self._gamepad.update()
            except Exception:
                pass

    def update_sticks(self, left_x: int, left_y: int, right_x: int, right_y: int):
        """Update stick axis values (range: -32768 to 32767)."""
        with self._lock:
            self._left_x = left_x
            self._left_y = left_y
            self._right_x = right_x
            self._right_y = right_y

    def update_triggers(self, lt: int, rt: int):
        """Update trigger values (range: 0-255)."""
        with self._lock:
            self._left_trigger = max(0, min(255, lt))
            self._right_trigger = max(0, min(255, rt))

    def update_buttons(self, rc_states: dict):
        """
        Update button states based on RC input states.

        Args:
            rc_states: Dict with RC button source names as keys, bool as values.
                       e.g. {'camera_up': True, 'camera_down': False, ...}
        """
        with self._lock:
            new_pressed = set()
            for rc_source, xbox_name in self.button_map.items():
                if rc_states.get(rc_source, False):
                    btn = get_vigem_button(xbox_name)
                    if btn is not None:
                        new_pressed.add((xbox_name, btn))
            self._pressed_buttons = new_pressed

    def push_now(self):
        """Immediately push current state to the virtual gamepad (call from any thread)."""
        if not self._initialized or not self._gamepad:
            return
        try:
            with self._lock:
                lx, ly = self._left_x, self._left_y
                rx, ry = self._right_x, self._right_y
                lt, rt = self._left_trigger, self._right_trigger
                pressed = set(self._pressed_buttons)

            self._gamepad.left_joystick(lx, ly)
            self._gamepad.right_joystick(rx, ry)
            self._gamepad.left_trigger(byte_value=lt)
            self._gamepad.right_trigger(byte_value=rt)

            for xbox_name in XBOX_BUTTONS:
                btn = get_vigem_button(xbox_name)
                if btn is not None:
                    self._gamepad.release_button(btn)
            for xbox_name, btn in pressed:
                self._gamepad.press_button(btn)

            self._gamepad.update()
        except Exception:
            pass

    def update_from_processed(self, processed: dict):
        """
        Convenience: update everything from InputProcessor output.

        Args:
            processed: Dict from InputProcessor.process() with keys:
                       gamepad_left_x, gamepad_left_y, gamepad_right_x, gamepad_right_y,
                       camera_up, camera_down, etc.
        """
        self.update_sticks(
            processed.get('gamepad_left_x', 0),
            processed.get('gamepad_left_y', 0),
            processed.get('gamepad_right_x', 0),
            processed.get('gamepad_right_y', 0),
        )
        self.update_triggers(
            processed.get('left_trigger', 0),
            processed.get('right_trigger', 0),
        )
        self.update_buttons(processed)

    def _update_loop(self):
        """Continuously push current state to the virtual gamepad."""
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    lx, ly = self._left_x, self._left_y
                    rx, ry = self._right_x, self._right_y
                    lt, rt = self._left_trigger, self._right_trigger
                    pressed = set(self._pressed_buttons)

                self._gamepad.left_joystick(lx, ly)
                self._gamepad.right_joystick(rx, ry)
                self._gamepad.left_trigger(byte_value=lt)
                self._gamepad.right_trigger(byte_value=rt)

                # Release all buttons first, then press active ones
                for xbox_name in XBOX_BUTTONS:
                    btn = get_vigem_button(xbox_name)
                    if btn is not None:
                        self._gamepad.release_button(btn)

                for xbox_name, btn in pressed:
                    self._gamepad.press_button(btn)

                self._gamepad.update()

            except Exception as e:
                logger.error("Gamepad update error: %s", e)

            self._stop_event.wait(self._update_interval)

    def load_from_config(self, config: dict):
        """Load button mapping from config."""
        mapping = config.get('button_mapping', {})
        if mapping:
            self.button_map = dict(mapping)
        rate = config.get('gamepad_update_rate_hz', 125)
        self.set_update_rate(rate)

    def save_to_config(self) -> dict:
        """Export button mapping to config dict."""
        return {
            'button_mapping': dict(self.button_map),
            'gamepad_update_rate_hz': int(1.0 / self._update_interval) if self._update_interval > 0 else 125,
        }
