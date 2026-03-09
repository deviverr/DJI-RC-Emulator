"""
Input processing: raw RC values → normalized → expo → gamepad range.
Handles axis remapping, inversion, deadzones, expo/rates curves,
EMA smoothing, and trigger axis mapping.
"""
import math

from src.duml import RAW_MIN, RAW_CENTER, RAW_MAX

# Output range for Xbox 360 gamepad axes
GAMEPAD_MIN = -32768
GAMEPAD_MAX = 32767
GAMEPAD_CENTER = 0

# Axis identifiers
AXIS_RIGHT_H = 'right_h'
AXIS_RIGHT_V = 'right_v'
AXIS_LEFT_H = 'left_h'
AXIS_LEFT_V = 'left_v'
AXIS_CAMERA = 'camera'

ALL_AXES = [AXIS_RIGHT_H, AXIS_RIGHT_V, AXIS_LEFT_H, AXIS_LEFT_V, AXIS_CAMERA]
STICK_AXES = [AXIS_RIGHT_H, AXIS_RIGHT_V, AXIS_LEFT_H, AXIS_LEFT_V]

# Axes that can be mapped to triggers
TRIGGER_SOURCE_AXES = ['right_h', 'right_v', 'left_h', 'left_v', 'camera', 'scroll']


def normalize_raw(raw_value: int) -> float:
    """
    Convert raw RC stick value (364-1684) to normalized range (-1.0 to +1.0).
    Center (1024) maps to 0.0.
    """
    normalized = (raw_value - RAW_CENTER) / (RAW_MAX - RAW_CENTER)
    return max(-1.0, min(1.0, normalized))


def apply_deadzone(value: float, deadzone: float) -> float:
    """
    Apply deadzone to a normalized value (-1.0 to +1.0).
    Values within the deadzone are snapped to 0.
    Values outside are rescaled to use the full range.
    """
    if deadzone <= 0.0:
        return value
    if deadzone >= 1.0:
        return 0.0

    abs_val = abs(value)
    if abs_val < deadzone:
        return 0.0

    # Rescale remaining range to 0.0-1.0
    sign = 1.0 if value >= 0 else -1.0
    rescaled = (abs_val - deadzone) / (1.0 - deadzone)
    return sign * rescaled


def apply_expo(value: float, expo: float) -> float:
    """
    Apply expo curve to a normalized value (-1.0 to +1.0).

    Expo controls the response curve:
      0.0 = fully linear
      1.0 = maximum exponential (fine center control, aggressive edges)

    Formula: output = value * (expo * value^2 + (1 - expo))
    This gives a smooth S-curve that passes through -1, 0, and +1.
    """
    if expo <= 0.0:
        return value
    expo = min(1.0, expo)
    return value * (expo * value * value + (1.0 - expo))


def apply_rate(value: float, rate: float) -> float:
    """
    Apply rate (max output multiplier) to a normalized value.
    Rate 1.0 = full range, 0.5 = half range, etc.
    """
    return max(-1.0, min(1.0, value * rate))


def to_gamepad_range(normalized: float) -> int:
    """Convert normalized (-1.0 to +1.0) to gamepad range (-32768 to +32767)."""
    val = int(normalized * 32767)
    return max(GAMEPAD_MIN, min(GAMEPAD_MAX, val))


class InputProcessor:
    """
    Processes raw RC stick data into gamepad-ready values.

    Supports per-axis:
      - Deadzone
      - Expo curve
      - Rate limiting
      - Inversion
      - EMA smoothing
      - Remapping (which physical axis drives which virtual axis)
      - Trigger axis mapping (RC axis → LT/RT)
    """

    def __init__(self):
        # Per-axis settings (keyed by physical axis name)
        self.expo = {axis: 0.0 for axis in STICK_AXES}
        self.rate = {axis: 1.0 for axis in STICK_AXES}
        self.deadzone = {axis: 0.02 for axis in STICK_AXES}
        self.inverted = {axis: False for axis in STICK_AXES}

        # EMA smoothing: alpha per axis (0.0 = off, higher = more smoothing)
        self.smoothing = {axis: 0.0 for axis in STICK_AXES}
        self._smoothed = {}     # axis -> last smoothed value
        self._smooth_init = set()  # axes that have been initialized

        # Axis remapping: virtual_axis -> physical_axis
        # Default: 1:1 mapping
        self.axis_map = {
            'gamepad_left_x': AXIS_LEFT_H,
            'gamepad_left_y': AXIS_LEFT_V,
            'gamepad_right_x': AXIS_RIGHT_H,
            'gamepad_right_y': AXIS_RIGHT_V,
        }

        # Trigger mapping: which RC axis drives LT/RT (None = disabled)
        self.trigger_lt_axis: str | None = None
        self.trigger_rt_axis: str | None = None

        # Camera wheel thresholds for button mapping
        self.camera_button_threshold = 0.8

        # Previous scroll value for edge-triggered detection
        self._prev_scroll = 0.0

    def _apply_smoothing(self, axis: str, value: float) -> float:
        """Apply exponential moving average smoothing to an axis value."""
        alpha = self.smoothing.get(axis, 0.0)
        if alpha <= 0.0:
            self._smoothed[axis] = value
            return value

        if axis not in self._smooth_init:
            self._smoothed[axis] = value
            self._smooth_init.add(axis)
            return value

        prev = self._smoothed.get(axis, value)
        smoothed = alpha * prev + (1.0 - alpha) * value
        self._smoothed[axis] = smoothed
        return smoothed

    def process(self, raw_data: dict) -> dict:
        """
        Process raw stick data into gamepad-ready values.

        Args:
            raw_data: Dict from duml.parse_stick_data() with keys:
                      'right_h', 'right_v', 'left_v', 'left_h', 'camera'

        Returns:
            Dict with gamepad axes, triggers, camera, buttons.
        """
        # Normalize all stick axes
        normalized = {}
        for axis in STICK_AXES:
            raw = raw_data.get(axis, RAW_CENTER)
            val = normalize_raw(raw)

            # Apply inversion
            if self.inverted.get(axis, False):
                val = -val

            # Apply deadzone
            val = apply_deadzone(val, self.deadzone.get(axis, 0.0))

            # Apply expo
            val = apply_expo(val, self.expo.get(axis, 0.0))

            # Apply rate
            val = apply_rate(val, self.rate.get(axis, 1.0))

            # Apply smoothing
            val = self._apply_smoothing(axis, val)

            normalized[axis] = val

        # Apply axis remapping and convert to gamepad range
        result = {}
        for gamepad_axis, physical_axis in self.axis_map.items():
            val = normalized.get(physical_axis, 0.0)
            result[gamepad_axis] = to_gamepad_range(val)

        # Camera wheel
        raw_camera = raw_data.get('camera', RAW_CENTER)
        camera_norm = normalize_raw(raw_camera)
        normalized['camera'] = camera_norm
        result['camera'] = camera_norm
        result['camera_up'] = camera_norm > self.camera_button_threshold
        result['camera_down'] = camera_norm < -self.camera_button_threshold

        # Scroll wheel (6th channel) — edge-triggered detection
        raw_scroll = raw_data.get('scroll', RAW_CENTER)
        scroll_norm = normalize_raw(raw_scroll)
        normalized['scroll'] = scroll_norm
        result['scroll'] = scroll_norm
        prev_scroll = self._prev_scroll
        self._prev_scroll = scroll_norm
        result['scroll_up'] = (scroll_norm > self.camera_button_threshold
                               and prev_scroll <= self.camera_button_threshold)
        result['scroll_down'] = (scroll_norm < -self.camera_button_threshold
                                 and prev_scroll >= -self.camera_button_threshold)

        # Trigger mapping (RC axis positive range → 0..255)
        result['left_trigger'] = self._compute_trigger(self.trigger_lt_axis, normalized)
        result['right_trigger'] = self._compute_trigger(self.trigger_rt_axis, normalized)

        # Hardware buttons from RC (passed through from parser)
        for btn in ('c1', 'c2', 'photo', 'video', 'fn'):
            result[btn] = raw_data.get(btn, False)
        result['btn_raw'] = raw_data.get('btn_raw', 0)

        return result

    def _compute_trigger(self, axis_name: str | None, normalized: dict) -> int:
        """Convert positive range of an RC axis to 0-255 trigger value."""
        if axis_name is None:
            return 0
        val = normalized.get(axis_name, 0.0)
        val_clamped = max(0.0, min(1.0, val))
        return int(val_clamped * 255)

    def load_from_config(self, config: dict):
        """Load settings from config dict."""
        axes_cfg = config.get('axes', {})
        for axis in STICK_AXES:
            ax_cfg = axes_cfg.get(axis, {})
            self.expo[axis] = ax_cfg.get('expo', 0.0)
            self.rate[axis] = ax_cfg.get('rate', 1.0)
            self.deadzone[axis] = ax_cfg.get('deadzone', 0.02)
            self.inverted[axis] = ax_cfg.get('inverted', False)

        # Smoothing
        smooth_cfg = config.get('smoothing', {})
        for axis in STICK_AXES:
            self.smoothing[axis] = smooth_cfg.get(axis, 0.0)

        # Trigger mapping
        trig_cfg = config.get('trigger_mapping', {})
        self.trigger_lt_axis = trig_cfg.get('lt_axis')
        self.trigger_rt_axis = trig_cfg.get('rt_axis')

        mapping = config.get('axis_mapping', {})
        if mapping:
            self.axis_map.update(mapping)

        self.camera_button_threshold = config.get('camera_button_threshold', 0.8)

    def save_to_config(self) -> dict:
        """Export settings to a config dict."""
        axes_cfg = {}
        for axis in STICK_AXES:
            axes_cfg[axis] = {
                'expo': self.expo[axis],
                'rate': self.rate[axis],
                'deadzone': self.deadzone[axis],
                'inverted': self.inverted[axis],
            }
        return {
            'axes': axes_cfg,
            'smoothing': dict(self.smoothing),
            'trigger_mapping': {
                'lt_axis': self.trigger_lt_axis,
                'rt_axis': self.trigger_rt_axis,
            },
            'axis_mapping': dict(self.axis_map),
            'camera_button_threshold': self.camera_button_threshold,
        }
