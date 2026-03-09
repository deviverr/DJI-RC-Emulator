"""
Main application window for DJI RC Emulator.
Shows connection status, stick visualizers, axis values, and settings access.
"""
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QRectF
from PySide6.QtGui import QFont, QColor, QIcon, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QGroupBox, QFrame, QStatusBar,
    QMessageBox, QSplitter, QProgressBar, QSizePolicy,
)

from src.version import __version__, __app_name__, __author__, __website__, __kofi__, __description__
from src.gui.stick_widget import StickWidget
from src.rc_connection import list_all_ports, scan_all_devices
from src.usb_transport import is_usb_available


class StatusIndicator(QWidget):
    """Small colored circle indicating connection status with pulsing animation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self._connected = False
        self._connecting = False
        self._pulse_on = True

        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._toggle_pulse)

    def set_connected(self, connected: bool):
        self._connected = connected
        if connected:
            self.set_connecting(False)
        self.update()

    def set_connecting(self, connecting: bool):
        self._connecting = connecting
        if connecting:
            self._pulse_on = True
            self._pulse_timer.start(400)
        else:
            self._pulse_timer.stop()
        self.update()

    def _toggle_pulse(self):
        self._pulse_on = not self._pulse_on
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._connected:
            color = QColor(0, 200, 80)
        elif self._connecting:
            color = QColor(200, 150, 0) if self._pulse_on else QColor(100, 75, 0)
        else:
            color = QColor(200, 50, 50)
        painter.setPen(QPen(color.darker(150), 1))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(1, 1, 12, 12)
        painter.end()


class LEDIndicator(QWidget):
    """Small LED indicator with label for button states."""

    def __init__(self, label: str, color=QColor(0, 200, 80), parent=None):
        super().__init__(parent)
        self.setFixedSize(52, 20)
        self._label = label
        self._active = False
        self._active_color = color
        self._inactive_color = QColor(50, 50, 60)

    def set_active(self, active: bool):
        if self._active != active:
            self._active = active
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self._active_color if self._active else self._inactive_color
        painter.setPen(QPen(color.darker(130), 1))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(2, 4, 10, 10)
        painter.setPen(QColor(160, 160, 170) if not self._active else QColor(240, 240, 250))
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        painter.drawText(QRectF(14, 0, 36, 20), Qt.AlignmentFlag.AlignVCenter, self._label)
        painter.end()


class MainWindow(QMainWindow):
    """Main application window."""

    # Signals for thread-safe UI updates
    stick_data_received = Signal(dict)
    connection_changed = Signal(bool, str)
    error_received = Signal(str)
    raw_packet_received = Signal(bytes)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__app_name__} v{__version__} — FPV Sim Controller")
        self.setMinimumSize(750, 560)
        self._is_connected = False

        # Set window icon (PNG first — more reliable with Qt on Windows)
        import os, sys
        if getattr(sys, 'frozen', False):
            app_dirs = [getattr(sys, '_MEIPASS', ''), os.path.dirname(sys.executable)]
        else:
            app_dirs = [os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))]
        for app_dir in app_dirs:
            found = False
            for icon_name in ("DJI_RC_Icon_12x12.png", "icon.ico"):
                icon_path = os.path.join(app_dir, icon_name)
                if os.path.exists(icon_path):
                    icon = QIcon(icon_path)
                    if not icon.isNull():
                        self.setWindowIcon(icon)
                        found = True
                        break
            if found:
                break

        self._setup_style()
        self._build_ui()
        self._connect_signals()

        # Refresh timer for port list
        self._port_timer = QTimer()
        self._port_timer.timeout.connect(self._refresh_ports)
        self._port_timer.start(3000)

        # Callbacks set by main.py
        self.on_connect_clicked = None
        self.on_disconnect_clicked = None
        self.on_settings_clicked = None
        self.on_port_selected = None

    def _setup_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a20;
            }
            QWidget {
                color: #d0d0d8;
                font-family: 'Segoe UI', sans-serif;
            }
            QGroupBox {
                background-color: #22222a;
                border: 1px solid #3a3a45;
                border-radius: 8px;
                margin-top: 16px;
                padding-top: 20px;
                font-weight: bold;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #a0a0b0;
            }
            QPushButton {
                background-color: #2d5aa0;
                border: none;
                border-radius: 6px;
                color: white;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 11px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #3568b8;
            }
            QPushButton:pressed {
                background-color: #244a88;
            }
            QPushButton:disabled {
                background-color: #3a3a45;
                color: #666;
            }
            QPushButton#disconnectBtn {
                background-color: #9a3030;
            }
            QPushButton#disconnectBtn:hover {
                background-color: #b04040;
            }
            QPushButton#settingsBtn {
                background-color: #404050;
            }
            QPushButton#settingsBtn:hover {
                background-color: #505068;
            }
            QComboBox {
                background-color: #2a2a35;
                border: 1px solid #3a3a45;
                border-radius: 5px;
                padding: 5px 10px;
                min-width: 200px;
                font-size: 11px;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a35;
                border: 1px solid #3a3a45;
                selection-background-color: #2d5aa0;
            }
            QLabel#valueLabel {
                font-family: 'Consolas', monospace;
                font-size: 12px;
                color: #b0b0c0;
                background-color: #22222a;
                border: 1px solid #3a3a45;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QLabel#statusLabel {
                font-size: 12px;
                font-weight: bold;
            }
            QLabel#headerLabel {
                font-size: 16px;
                font-weight: bold;
                color: #e0e0e8;
            }
            QLabel#statsLabel {
                font-family: 'Consolas', monospace;
                font-size: 10px;
                color: #808090;
            }
            QStatusBar {
                background-color: #18181e;
                border-top: 1px solid #2a2a35;
                color: #808090;
                font-size: 10px;
            }
        """)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 12, 16, 8)
        main_layout.setSpacing(10)

        # -- Header --
        header_layout = QHBoxLayout()
        title = QLabel(f"{__app_name__}  v{__version__}")
        title.setObjectName("headerLabel")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self._about_btn = QPushButton("About")
        self._about_btn.setObjectName("settingsBtn")
        self._about_btn.clicked.connect(self._show_about)
        header_layout.addWidget(self._about_btn)

        self._settings_btn = QPushButton("Settings")
        self._settings_btn.setObjectName("settingsBtn")
        self._settings_btn.clicked.connect(self._on_settings)
        header_layout.addWidget(self._settings_btn)
        main_layout.addLayout(header_layout)

        # -- Connection Panel --
        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout(conn_group)
        conn_layout.setSpacing(10)

        self._status_indicator = StatusIndicator()
        conn_layout.addWidget(self._status_indicator)

        self._status_label = QLabel("Disconnected")
        self._status_label.setObjectName("statusLabel")
        self._status_label.setStyleSheet("color: #cc4444;")
        conn_layout.addWidget(self._status_label)

        conn_layout.addStretch()

        conn_layout.addWidget(QLabel("Device:"))
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(280)
        self._port_combo.addItem("Auto-detect", None)
        conn_layout.addWidget(self._port_combo)

        self._scan_btn = QPushButton("Scan")
        self._scan_btn.setObjectName("settingsBtn")
        self._scan_btn.setMinimumWidth(50)
        self._scan_btn.clicked.connect(self._refresh_ports)
        conn_layout.addWidget(self._scan_btn)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._on_connect)
        conn_layout.addWidget(self._connect_btn)

        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setObjectName("disconnectBtn")
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        self._disconnect_btn.setEnabled(False)
        conn_layout.addWidget(self._disconnect_btn)

        main_layout.addWidget(conn_group)

        # -- Zadig Warning Banner (hidden by default) --
        self._zadig_banner = QFrame()
        self._zadig_banner.setStyleSheet(
            "QFrame { background-color: #3d2a00; border: 1px solid #886600; "
            "border-radius: 6px; padding: 8px; }"
        )
        zadig_layout = QHBoxLayout(self._zadig_banner)
        zadig_layout.setContentsMargins(10, 6, 10, 6)
        zadig_text = QLabel(
            "DJI RC detected via USB but needs WinUSB driver.  "
            "Click 'Setup Driver' for instructions."
        )
        zadig_text.setStyleSheet("color: #ffcc00; font-size: 11px;")
        zadig_text.setWordWrap(True)
        zadig_layout.addWidget(zadig_text, stretch=1)
        self._zadig_btn = QPushButton("Setup Driver")
        self._zadig_btn.setStyleSheet(
            "background-color: #886600; color: white; font-weight: bold; "
            "padding: 6px 14px; border-radius: 5px;"
        )
        self._zadig_btn.clicked.connect(self._show_zadig_instructions)
        zadig_layout.addWidget(self._zadig_btn)
        self._zadig_banner.setVisible(False)
        main_layout.addWidget(self._zadig_banner)

        self._refresh_ports()

        # -- Sticks Display --
        sticks_group = QGroupBox("Stick Positions")
        sticks_layout = QHBoxLayout(sticks_group)
        sticks_layout.setSpacing(20)

        # Left stick
        left_container = QVBoxLayout()
        self._left_stick = StickWidget("Left Stick (Throttle / Yaw)")
        left_container.addWidget(self._left_stick)
        sticks_layout.addLayout(left_container)

        # Right stick
        right_container = QVBoxLayout()
        self._right_stick = StickWidget("Right Stick (Pitch / Roll)")
        right_container.addWidget(self._right_stick)
        sticks_layout.addLayout(right_container)

        # Wheels (Camera + Scroll) — vertical bars
        wheels_container = QVBoxLayout()
        wheels_container.setSpacing(10)

        cam_label = QLabel("Camera")
        cam_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cam_label.setStyleSheet("font-size: 11px;")
        wheels_container.addWidget(cam_label)
        self._cam_bar = QProgressBar()
        self._cam_bar.setOrientation(Qt.Orientation.Vertical)
        self._cam_bar.setRange(-100, 100)
        self._cam_bar.setValue(0)
        self._cam_bar.setTextVisible(False)
        self._cam_bar.setFixedWidth(28)
        self._cam_bar.setStyleSheet(
            "QProgressBar { background-color: #2a2a35; border: 1px solid #444; border-radius: 4px; }"
            "QProgressBar::chunk { background-color: #44aaff; border-radius: 3px; }"
        )
        wheels_container.addWidget(self._cam_bar, stretch=1, alignment=Qt.AlignmentFlag.AlignHCenter)

        scroll_label = QLabel("Scroll")
        scroll_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_label.setStyleSheet("font-size: 11px;")
        wheels_container.addWidget(scroll_label)
        self._scroll_bar = QProgressBar()
        self._scroll_bar.setOrientation(Qt.Orientation.Vertical)
        self._scroll_bar.setRange(-100, 100)
        self._scroll_bar.setValue(0)
        self._scroll_bar.setTextVisible(False)
        self._scroll_bar.setFixedWidth(28)
        self._scroll_bar.setStyleSheet(
            "QProgressBar { background-color: #2a2a35; border: 1px solid #444; border-radius: 4px; }"
            "QProgressBar::chunk { background-color: #ffaa44; border-radius: 3px; }"
        )
        wheels_container.addWidget(self._scroll_bar, stretch=1, alignment=Qt.AlignmentFlag.AlignHCenter)

        sticks_layout.addLayout(wheels_container)

        main_layout.addWidget(sticks_group, stretch=1)

        # -- Values & Buttons Panel --
        info_group = QGroupBox("Input Values")
        info_layout = QGridLayout(info_group)
        info_layout.setSpacing(8)

        axis_names = [
            ("Left X:", "lx_val"), ("Left Y:", "ly_val"),
            ("Right X:", "rx_val"), ("Right Y:", "ry_val"),
            ("Camera:", "cam_val"), ("Scroll:", "scr_val"),
        ]
        self._value_labels = {}
        for i, (name, key) in enumerate(axis_names):
            row = i // 3
            col = (i % 3) * 2
            label = QLabel(name)
            info_layout.addWidget(label, row, col)
            val = QLabel("0")
            val.setObjectName("valueLabel")
            val.setMinimumWidth(80)
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._value_labels[key] = val
            info_layout.addWidget(val, row, col + 1)

        # Button LED indicators
        info_layout.addWidget(QLabel("Buttons:"), 2, 0)
        btn_led_layout = QHBoxLayout()
        btn_led_layout.setSpacing(2)
        self._led_indicators = {}
        btn_defs = [
            ('c1', 'C1', QColor(0, 200, 80)),
            ('c2', 'C2', QColor(0, 200, 80)),
            ('photo', 'PHO', QColor(60, 160, 255)),
            ('video', 'VID', QColor(255, 80, 80)),
            ('fn', 'FN', QColor(200, 160, 0)),
            ('camera_up', 'CM+', QColor(100, 200, 255)),
            ('camera_down', 'CM-', QColor(100, 200, 255)),
        ]
        for key, label, color in btn_defs:
            led = LEDIndicator(label, color)
            self._led_indicators[key] = led
            btn_led_layout.addWidget(led)
        btn_led_layout.addStretch()
        info_layout.addLayout(btn_led_layout, 2, 1, 1, 5)

        # Gamepad status
        info_layout.addWidget(QLabel("Gamepad:"), 3, 0)
        self._gamepad_label = QLabel("Not initialized")
        self._gamepad_label.setObjectName("valueLabel")
        self._gamepad_label.setMinimumWidth(100)
        info_layout.addWidget(self._gamepad_label, 3, 1, 1, 2)

        # Trigger values
        info_layout.addWidget(QLabel("Triggers:"), 3, 3)
        self._trigger_label = QLabel("LT: 0  RT: 0")
        self._trigger_label.setObjectName("valueLabel")
        self._trigger_label.setMinimumWidth(100)
        info_layout.addWidget(self._trigger_label, 3, 4, 1, 2)

        main_layout.addWidget(info_group)

        # -- Status Bar --
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self._statusbar_label = QLabel("Ready — Connect your DJI RC via USB-C")
        status_bar.addWidget(self._statusbar_label, stretch=1)

        # Stats labels in status bar
        self._stats_pps = QLabel("")
        self._stats_pps.setObjectName("statsLabel")
        status_bar.addPermanentWidget(self._stats_pps)

        self._stats_model = QLabel("")
        self._stats_model.setObjectName("statsLabel")
        status_bar.addPermanentWidget(self._stats_model)

        self._stats_elapsed = QLabel("")
        self._stats_elapsed.setObjectName("statsLabel")
        status_bar.addPermanentWidget(self._stats_elapsed)

    def _connect_signals(self):
        self.stick_data_received.connect(self._update_sticks)
        self.connection_changed.connect(self._update_connection)
        self.error_received.connect(self._show_error)

    # -- Public Methods (called from main.py) --

    def set_gamepad_status(self, status: str):
        self._gamepad_label.setText(status)

    def set_statusbar(self, text: str):
        self._statusbar_label.setText(text)

    def set_connecting(self, connecting: bool):
        """Show pulsing amber indicator while connecting."""
        self._status_indicator.set_connecting(connecting)

    def update_stats(self, pps: float, model: str, elapsed: float):
        """Update stats bar with connection statistics."""
        self._stats_pps.setText(f"{pps:.0f} pkt/s")
        self._stats_model.setText(model)
        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        self._stats_elapsed.setText(f"{mins:02d}:{secs:02d}")

    def update_deadzones(self, config: dict):
        """Update deadzone display on stick widgets from config."""
        axes_cfg = config.get('axes', {})
        left_dz = max(
            axes_cfg.get('left_h', {}).get('deadzone', 0.02),
            axes_cfg.get('left_v', {}).get('deadzone', 0.02),
        )
        right_dz = max(
            axes_cfg.get('right_h', {}).get('deadzone', 0.02),
            axes_cfg.get('right_v', {}).get('deadzone', 0.02),
        )
        self._left_stick.set_deadzone(left_dz)
        self._right_stick.set_deadzone(right_dz)

    # -- Slots --

    @Slot(dict)
    def _update_sticks(self, data: dict):
        """Update stick visualizers and value labels from processed data."""
        lx = data.get('gamepad_left_x', 0) / 32767.0
        ly = data.get('gamepad_left_y', 0) / 32767.0
        rx = data.get('gamepad_right_x', 0) / 32767.0
        ry = data.get('gamepad_right_y', 0) / 32767.0
        cam = data.get('camera', 0.0)

        self._left_stick.set_position(lx, ly)
        self._right_stick.set_position(rx, ry)

        self._value_labels['lx_val'].setText(f"{data.get('gamepad_left_x', 0):+6d}")
        self._value_labels['ly_val'].setText(f"{data.get('gamepad_left_y', 0):+6d}")
        self._value_labels['rx_val'].setText(f"{data.get('gamepad_right_x', 0):+6d}")
        self._value_labels['ry_val'].setText(f"{data.get('gamepad_right_y', 0):+6d}")
        self._value_labels['cam_val'].setText(f"{cam:+.2f}")

        scr = data.get('scroll', 0.0)
        self._value_labels['scr_val'].setText(f"{scr:+.2f}")

        # Update wheel bars
        self._cam_bar.setValue(int(cam * 100))
        self._scroll_bar.setValue(int(scr * 100))

        # Button LED indicators
        for key, led in self._led_indicators.items():
            led.set_active(bool(data.get(key, False)))

        # Trigger values
        lt = data.get('left_trigger', 0)
        rt = data.get('right_trigger', 0)
        self._trigger_label.setText(f"LT: {lt:3d}  RT: {rt:3d}")

    @Slot(bool, str)
    def _update_connection(self, connected: bool, port: str):
        self._is_connected = connected
        self._status_indicator.set_connected(connected)
        if connected:
            self._zadig_banner.setVisible(False)
            self._status_label.setText(f"Connected ({port})")
            self._status_label.setStyleSheet("color: #44cc44;")
            self._connect_btn.setEnabled(False)
            self._disconnect_btn.setEnabled(True)
            self._port_combo.setEnabled(False)
            self._statusbar_label.setText(f"Connected to {port} — Move sticks to verify")
        else:
            self._status_label.setText("Disconnected")
            self._status_label.setStyleSheet("color: #cc4444;")
            self._connect_btn.setEnabled(True)
            self._disconnect_btn.setEnabled(False)
            self._port_combo.setEnabled(True)
            self._statusbar_label.setText("Disconnected — Connect your DJI RC via USB-C")
            self._stats_pps.setText("")
            self._stats_model.setText("")
            self._stats_elapsed.setText("")
            # Reset stick positions
            self._left_stick.set_position(0, 0)
            self._right_stick.set_position(0, 0)

    @Slot(str)
    def _show_error(self, message: str):
        self._statusbar_label.setText(f"Error: {message}")

    # -- Internal --

    def _refresh_ports(self):
        """Refresh device dropdown with serial ports and USB devices."""
        current = self._port_combo.currentData()
        self._port_combo.blockSignals(True)
        self._port_combo.clear()
        self._port_combo.addItem("Auto-detect", None)

        has_zadig_device = False

        for dev in scan_all_devices():
            if dev['type'] == 'serial':
                display = f"{dev['device']} \u2014 {dev['description']}"
                data = {"type": "serial", "port": dev['device']}
                self._port_combo.addItem(display, data)
            elif dev['type'] == 'usb':
                if dev.get('needs_zadig'):
                    display = f"\u26A0 {dev['description']} (USB \u2014 needs driver setup)"
                    data = {"type": "usb_zadig", "pid": dev['pid']}
                    has_zadig_device = True
                else:
                    sn = dev.get('serial_short', '')
                    sn_part = f" S/N:{sn}" if sn else ""
                    display = f"\u2713 {dev['description']} (USB{sn_part})"
                    data = {"type": "usb", "pid": dev['pid']}
                self._port_combo.addItem(display, data)

        # Show/hide Zadig banner — hide when already connected
        self._zadig_banner.setVisible(has_zadig_device and not self._is_connected)

        # Restore selection
        if current:
            for i in range(self._port_combo.count()):
                item_data = self._port_combo.itemData(i)
                if item_data == current:
                    self._port_combo.setCurrentIndex(i)
                    break
        self._port_combo.blockSignals(False)

    def _show_zadig_instructions(self):
        """Show Zadig driver installation instructions."""
        msg = QMessageBox(self)
        msg.setWindowTitle("WinUSB Driver Setup — Zadig")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            "Your DJI RC is detected but needs the WinUSB driver to communicate.\n"
            "This is a one-time setup step."
        )
        msg.setInformativeText(
            "Steps:\n\n"
            "1. Download Zadig from: https://zadig.akeo.ie/\n\n"
            "2. Run Zadig as Administrator\n\n"
            "3. Menu: Options \u2192 List All Devices\n\n"
            "4. In the dropdown, select:\n"
            "   'BULK Interface (Interface 1)' or '1023_MI01'\n"
            "   (Make sure it says Interface 1, NOT Interface 0 or 2)\n\n"
            "5. Set the target driver (right side) to 'WinUSB'\n\n"
            "6. Click 'Replace Driver' and wait for it to finish\n\n"
            "7. Unplug and replug the RC\n\n"
            "8. Click 'Scan' in this app to re-detect the device"
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def _on_connect(self):
        device_info = self._port_combo.currentData()  # None or dict
        if isinstance(device_info, dict) and device_info.get('type') == 'usb_zadig':
            self._show_zadig_instructions()
            return
        if self.on_connect_clicked:
            self.on_connect_clicked(device_info)

    def _on_disconnect(self):
        if self.on_disconnect_clicked:
            self.on_disconnect_clicked()

    def _on_settings(self):
        if self.on_settings_clicked:
            self.on_settings_clicked()

    def _show_about(self):
        msg = QMessageBox(self)
        msg.setWindowTitle(f"About {__app_name__}")
        msg.setWindowIcon(self.windowIcon())
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            f"<h2>{__app_name__}</h2>"
            f"<p>Version {__version__}</p>"
        )
        msg.setInformativeText(
            f"{__description__}\n\n"
            f"Author: {__author__}\n"
            f"Website: {__website__}\n"
            f"Support: {__kofi__}\n\n"
            "Protocol based on DJI_RC-N1_SIMULATOR_FLY_DCL by Ivan Yakymenko.\n"
            "Virtual gamepad via ViGEm and vgamepad."
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def closeEvent(self, event):
        """Save window geometry on close."""
        event.accept()

    def get_window_geometry(self) -> dict:
        geo = self.geometry()
        return {
            'x': geo.x(),
            'y': geo.y(),
            'width': geo.width(),
            'height': geo.height(),
        }

    def restore_window_geometry(self, config: dict):
        w = config.get('width', 780)
        h = config.get('height', 580)
        x = config.get('x')
        y = config.get('y')
        self.resize(w, h)
        if x is not None and y is not None:
            self.move(x, y)
