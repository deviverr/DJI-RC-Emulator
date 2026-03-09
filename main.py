"""
DJI RC Controller Emulator for FPV Simulators (Liftoff, etc.)
Main entry point — wires together serial connection, input processing,
virtual gamepad, and GUI.
"""
import sys
import os
import logging

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon
from PySide6.QtCore import QTimer

from src.version import __version__, __app_name__
from src.config_manager import ConfigManager
from src.rc_connection import RCConnection
from src.input_processor import InputProcessor
from src.gamepad import VirtualGamepad, VGAMEPAD_AVAILABLE
from src.usb_transport import load_custom_pids
from src.gui.main_window import MainWindow
from src.gui.settings_dialog import SettingsDialog
from src.gui.setup_wizard import (
    SetupWizard, check_missing_deps, should_show_wizard, mark_setup_done,
)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


class Application:
    """Ties together all components of the DJI RC Emulator."""

    def __init__(self):
        self.config_mgr = ConfigManager()
        self.config = self.config_mgr.load()

        # Load custom USB PIDs from config
        custom_pids = self.config.get('custom_usb_pids', [])
        if custom_pids:
            load_custom_pids(custom_pids)

        self.input_proc = InputProcessor()
        self.input_proc.load_from_config(self.config)

        self.gamepad = VirtualGamepad()
        self.gamepad.load_from_config(self.config)

        self.rc = RCConnection()
        self.rc.set_poll_interval(self.config.get('poll_interval_ms', 5))
        self.rc.set_format_override(self.config.get('rc_model_override'))
        self.rc.set_reconnect_interval(self.config.get('reconnect_interval_s', 2.0))

        self.window: MainWindow | None = None

    def run(self) -> int:
        app = QApplication(sys.argv)
        app.setApplicationName(__app_name__)
        app.setApplicationVersion(__version__)

        # Set application icon
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))
        for icon_name in ("icon.ico", "DJI_RC_Icon_12x12.png"):
            icon_path = os.path.join(app_dir, icon_name)
            if os.path.exists(icon_path):
                app.setWindowIcon(QIcon(icon_path))
                break

        # Show setup wizard on first run
        if should_show_wizard():
            missing = check_missing_deps()
            wizard = SetupWizard(missing)
            wizard.exec()
            mark_setup_done()

        # Create main window
        self.window = MainWindow()
        self.window.restore_window_geometry(self.config.get('window', {}))

        # Wire up callbacks
        self.window.on_connect_clicked = self._on_connect
        self.window.on_disconnect_clicked = self._on_disconnect
        self.window.on_settings_clicked = self._on_settings

        # Wire up RC connection callbacks (thread-safe via Qt signals)
        self.rc.on_stick_data = self._on_stick_data
        self.rc.on_connection_changed = self._on_connection_changed
        self.rc.on_error = self._on_error

        # Gamepad error callback
        self.gamepad.on_error = self._on_error

        # Initialize virtual gamepad
        if not VGAMEPAD_AVAILABLE:
            self.window.set_gamepad_status("MISSING: Install ViGEm")
            self.window.set_statusbar(
                "ViGEm Bus Driver not found — install from github.com/nefarius/ViGEmBus/releases"
            )
        elif self.gamepad.initialize():
            self.window.set_gamepad_status("Xbox 360 Controller ready")
            self.gamepad.start()
        else:
            self.window.set_gamepad_status("Failed to initialize")

        # Stats timer — update stats bar once per second
        self._stats_timer = QTimer()
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(1000)

        # Make sure we clean up on exit
        app.aboutToQuit.connect(self._cleanup)

        self.window.show()
        return app.exec()

    def _on_connect(self, device_info: dict | None):
        """Handle connect button click. device_info is None (auto) or a dict."""
        if device_info is None:
            self.rc.set_device_override(None)
        elif isinstance(device_info, dict):
            self.rc.set_device_override(device_info)
        else:
            # Legacy: plain string COM port
            self.rc.set_port_override(device_info)
        self.rc.start()
        if self.window:
            self.window.set_statusbar("Connecting...")
            self.window.set_connecting(True)

    def _on_disconnect(self):
        """Handle disconnect button click."""
        self.rc.stop()

    def _on_stick_data(self, raw_data: dict):
        """Called from RC thread with raw stick data. Process and forward."""
        processed = self.input_proc.process(raw_data)

        # Update virtual gamepad immediately
        if self.gamepad.is_initialized:
            self.gamepad.update_from_processed(processed)
            self.gamepad.push_now()

        # Update GUI (thread-safe via signal)
        if self.window:
            self.window.stick_data_received.emit(processed)

    def _on_connection_changed(self, connected: bool, port: str):
        """Called from RC thread on connect/disconnect."""
        if self.window:
            self.window.connection_changed.emit(connected, port)

    def _on_error(self, message: str):
        """Called from RC thread or gamepad on error."""
        logger.error(message)
        if self.window:
            self.window.error_received.emit(message)

    def _on_settings(self):
        """Open settings dialog."""
        dialog = SettingsDialog(self.config, self.window)
        dialog.settings_changed.connect(self._apply_settings)
        dialog.exec()

    def _apply_settings(self, new_settings: dict):
        """Apply changed settings from the dialog."""
        self.config_mgr.update(new_settings)
        self.config = self.config_mgr.config

        # Reload all components with new settings
        self.input_proc.load_from_config(self.config)
        self.gamepad.load_from_config(self.config)
        self.rc.set_poll_interval(self.config.get('poll_interval_ms', 5))
        self.rc.set_format_override(self.config.get('rc_model_override'))
        self.rc.set_reconnect_interval(self.config.get('reconnect_interval_s', 2.0))

        # Reload custom PIDs
        custom_pids = self.config.get('custom_usb_pids', [])
        if custom_pids:
            load_custom_pids(custom_pids)

        # Update deadzone display on stick widgets
        if self.window:
            self.window.update_deadzones(self.config)

        logger.info("Settings applied and saved")
        if self.window:
            self.window.set_statusbar("Settings updated")

    def _update_stats(self):
        """Push connection stats to the main window (called at 1 Hz)."""
        if self.window and self.rc.connected:
            self.window.update_stats(
                self.rc.packets_per_sec,
                self.rc.model_name,
                self.rc.connect_elapsed,
            )

    def _cleanup(self):
        """Clean shutdown of all components."""
        logger.info("Shutting down...")

        # Save window geometry
        if self.window:
            geo = self.window.get_window_geometry()
            self.config_mgr.update({'window': geo})

        self.rc.stop()
        self.gamepad.stop()
        logger.info("Shutdown complete")


def main():
    app = Application()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
