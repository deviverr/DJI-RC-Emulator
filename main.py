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
        self._icon_path: str | None = None

    def run(self) -> int:
        # Set Windows App User Model ID so the taskbar shows the correct icon
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                'deviver.DJIRCEmulator.1'
            )
        except Exception:
            pass

        app = QApplication(sys.argv)
        app.setApplicationName(__app_name__)
        app.setApplicationVersion(__version__)

        # Set application icon (prefer PNG — more reliable with Qt)
        if getattr(sys, 'frozen', False):
            # PyInstaller puts data files in sys._MEIPASS (_internal dir)
            app_dirs = [getattr(sys, '_MEIPASS', ''), os.path.dirname(sys.executable)]
        else:
            app_dirs = [os.path.dirname(os.path.abspath(__file__))]
        for app_dir in app_dirs:
            found = False
            for icon_name in ("DJI_RC_Icon_12x12.png", "icon.ico"):
                candidate = os.path.join(app_dir, icon_name)
                if os.path.exists(candidate):
                    icon = QIcon(candidate)
                    if not icon.isNull():
                        app.setWindowIcon(icon)
                        self._icon_path = candidate
                        found = True
                        break
            if found:
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
        else:
            self.window.set_gamepad_status("Failed to initialize")

        # Stats timer — update stats bar once per second
        self._stats_timer = QTimer()
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(1000)

        # Make sure we clean up on exit
        app.aboutToQuit.connect(self._cleanup)

        self.window.show()

        # Force-set Win32 HICON on the HWND (ensures taskbar + title bar icon)
        self._force_win32_icon()

        return app.exec()

    def _force_win32_icon(self):
        """Use Win32 API to set the icon directly on the HWND — ensures taskbar icon."""
        if sys.platform != 'win32' or not self._icon_path or not self.window:
            return
        # Win32 needs .ico for HICON; if we only have .png, skip (Qt handles it)
        ico_path = None
        if getattr(sys, 'frozen', False):
            search_dirs = [getattr(sys, '_MEIPASS', ''), os.path.dirname(sys.executable)]
        else:
            search_dirs = [os.path.dirname(os.path.abspath(__file__))]
        for d in search_dirs:
            candidate = os.path.join(d, "icon.ico")
            if os.path.exists(candidate):
                ico_path = candidate
                break
        if not ico_path:
            return
        try:
            import ctypes
            hwnd = int(self.window.winId())
            # LoadImageW: type=1 (IMAGE_ICON), flags=0x10 (LR_LOADFROMFILE)
            hicon = ctypes.windll.user32.LoadImageW(None, ico_path, 1, 0, 0, 0x00000010)
            if hicon:
                WM_SETICON = 0x0080
                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 1, hicon)  # ICON_BIG
                ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 0, hicon)  # ICON_SMALL
        except Exception:
            pass

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
        """Called from RC thread with raw stick data. Process and push to gamepad."""
        processed = self.input_proc.process(raw_data)

        # Push directly to ViGEm — no background thread, no lock contention
        if self.gamepad.is_initialized:
            self.gamepad.push(processed)

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
