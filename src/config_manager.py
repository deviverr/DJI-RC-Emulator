"""
Configuration manager for DJI RC Emulator.
Loads/saves settings as JSON. Provides defaults for all values.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "port_override": None,
    "poll_interval_ms": 5,
    "reconnect_interval_s": 2.0,
    "gamepad_update_rate_hz": 125,
    "rc_model_override": None,          # None | "38-byte" | "32-byte"
    "custom_usb_pids": [],              # list of hex-string or int PIDs
    "axes": {
        "right_h": {"expo": 0.0, "rate": 1.0, "deadzone": 0.02, "inverted": False},
        "right_v": {"expo": 0.0, "rate": 1.0, "deadzone": 0.02, "inverted": False},
        "left_h":  {"expo": 0.0, "rate": 1.0, "deadzone": 0.02, "inverted": False},
        "left_v":  {"expo": 0.0, "rate": 1.0, "deadzone": 0.02, "inverted": False},
    },
    "smoothing": {
        "right_h": 0.0,
        "right_v": 0.0,
        "left_h": 0.0,
        "left_v": 0.0,
    },
    "trigger_mapping": {
        "lt_axis": None,                # None | axis name string
        "rt_axis": None,
    },
    "axis_mapping": {
        "gamepad_left_x": "left_h",
        "gamepad_left_y": "left_v",
        "gamepad_right_x": "right_h",
        "gamepad_right_y": "right_v",
    },
    "button_mapping": {
        "camera_up": "Y",
        "camera_down": "B",
    },
    "camera_button_threshold": 0.8,
    "profiles": {},                     # name -> config snapshot
    "active_profile": "default",
    "window": {
        "width": 780,
        "height": 580,
        "x": None,
        "y": None,
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigManager:
    """
    Manages application configuration with JSON persistence.
    Missing keys get filled with defaults on load.
    """

    def __init__(self, config_path: str = None):
        if config_path is None:
            # Default config path next to the main script
            app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(app_dir, "config.json")
        self._path = config_path
        self._config = dict(DEFAULT_CONFIG)

    @property
    def path(self) -> str:
        return self._path

    @property
    def config(self) -> dict:
        return self._config

    def load(self) -> dict:
        """Load config from disk, merging with defaults for missing keys."""
        if os.path.exists(self._path):
            try:
                with open(self._path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                self._config = deep_merge(DEFAULT_CONFIG, loaded)
                logger.info("Config loaded from %s", self._path)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load config (%s), using defaults", e)
                self._config = dict(DEFAULT_CONFIG)
        else:
            logger.info("No config file found, using defaults")
            self._config = dict(DEFAULT_CONFIG)
            self.save()  # Create the default config file
        return self._config

    def save(self):
        """Save current config to disk."""
        try:
            os.makedirs(os.path.dirname(self._path) or '.', exist_ok=True)
            with open(self._path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2)
            logger.debug("Config saved to %s", self._path)
        except IOError as e:
            logger.error("Failed to save config: %s", e)

    def get(self, key: str, default=None):
        """Get a top-level config value."""
        return self._config.get(key, default)

    def set(self, key: str, value):
        """Set a top-level config value and save."""
        self._config[key] = value
        self.save()

    def update(self, updates: dict):
        """Merge updates into config and save."""
        self._config = deep_merge(self._config, updates)
        self.save()

    def reset(self):
        """Reset config to defaults and save."""
        self._config = dict(DEFAULT_CONFIG)
        self.save()
