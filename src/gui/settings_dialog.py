"""
Settings dialog for DJI RC Emulator.
Provides controls for expo/rates, axis mapping, button mapping, deadzones,
smoothing, triggers, device settings, and profiles.
"""
import copy
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget,
    QWidget, QLabel, QSlider, QComboBox, QCheckBox, QGroupBox,
    QPushButton, QSpinBox, QDoubleSpinBox, QFormLayout, QScrollArea,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
)

from src.gui.stick_widget import ExpoPreviewWidget
from src.input_processor import STICK_AXES, TRIGGER_SOURCE_AXES, AXIS_RIGHT_H, AXIS_RIGHT_V, AXIS_LEFT_H, AXIS_LEFT_V
from src.gamepad import XBOX_BUTTONS, RC_BUTTON_SOURCES

# Friendly names for axes
AXIS_DISPLAY_NAMES = {
    AXIS_RIGHT_H: "Right Horizontal (Roll)",
    AXIS_RIGHT_V: "Right Vertical (Pitch)",
    AXIS_LEFT_H: "Left Horizontal (Yaw)",
    AXIS_LEFT_V: "Left Vertical (Throttle)",
}

GAMEPAD_AXIS_NAMES = {
    'gamepad_left_x': "Gamepad Left X",
    'gamepad_left_y': "Gamepad Left Y",
    'gamepad_right_x': "Gamepad Right X",
    'gamepad_right_y': "Gamepad Right Y",
}

TRIGGER_AXIS_DISPLAY = {
    'right_h': "Right Horizontal",
    'right_v': "Right Vertical",
    'left_h': "Left Horizontal",
    'left_v': "Left Vertical",
    'camera': "Camera Wheel",
    'scroll': "Scroll Wheel",
}


class SettingsDialog(QDialog):
    """Settings dialog with tabs for different config categories."""

    settings_changed = Signal(dict)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings — DJI RC Emulator")
        self.setMinimumSize(650, 540)
        self._config = config
        self._widgets = {}
        self._profiles = copy.deepcopy(config.get('profiles', {}))
        self._active_profile = config.get('active_profile', 'default')

        # Inherit application icon
        app_icon = QApplication.instance().windowIcon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

        self._setup_style()
        self._build_ui()
        self._load_values()

    def _setup_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e26;
                color: #d0d0d8;
            }
            QTabWidget::pane {
                border: 1px solid #3a3a45;
                border-radius: 4px;
                background-color: #22222a;
            }
            QTabBar::tab {
                background-color: #2a2a35;
                border: 1px solid #3a3a45;
                padding: 8px 14px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                color: #a0a0b0;
                font-weight: bold;
                font-size: 10px;
            }
            QTabBar::tab:selected {
                background-color: #22222a;
                border-bottom-color: #22222a;
                color: #e0e0e8;
            }
            QGroupBox {
                background-color: #26262e;
                border: 1px solid #3a3a45;
                border-radius: 6px;
                margin-top: 14px;
                padding-top: 18px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #a0a0b0;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background-color: #3a3a45;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 16px;
                height: 16px;
                margin: -5px 0;
                background-color: #2d5aa0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background-color: #3568b8;
            }
            QComboBox {
                background-color: #2a2a35;
                border: 1px solid #3a3a45;
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 140px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a35;
                border: 1px solid #3a3a45;
                selection-background-color: #2d5aa0;
            }
            QCheckBox {
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #3a3a45;
                border-radius: 3px;
                background-color: #2a2a35;
            }
            QCheckBox::indicator:checked {
                background-color: #2d5aa0;
                border-color: #2d5aa0;
            }
            QSpinBox, QDoubleSpinBox {
                background-color: #2a2a35;
                border: 1px solid #3a3a45;
                border-radius: 4px;
                padding: 3px 6px;
                min-width: 70px;
            }
            QLineEdit {
                background-color: #2a2a35;
                border: 1px solid #3a3a45;
                border-radius: 4px;
                padding: 4px 8px;
                color: #d0d0d8;
            }
            QListWidget {
                background-color: #2a2a35;
                border: 1px solid #3a3a45;
                border-radius: 4px;
                color: #d0d0d8;
            }
            QListWidget::item:selected {
                background-color: #2d5aa0;
            }
            QPushButton {
                background-color: #2d5aa0;
                border: none;
                border-radius: 5px;
                color: white;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3568b8;
            }
            QPushButton#resetBtn {
                background-color: #9a3030;
            }
            QPushButton#resetBtn:hover {
                background-color: #b04040;
            }
            QPushButton#smallBtn {
                padding: 6px 14px;
                font-size: 10px;
                min-width: 60px;
            }
        """)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        tabs = QTabWidget()
        tabs.addTab(self._build_expo_tab(), "Expo / Rates")
        tabs.addTab(self._build_mapping_tab(), "Axis Mapping")
        tabs.addTab(self._build_buttons_tab(), "Buttons")
        tabs.addTab(self._build_triggers_tab(), "Triggers")
        tabs.addTab(self._build_devices_tab(), "Devices")
        tabs.addTab(self._build_profiles_tab(), "Profiles")
        tabs.addTab(self._build_advanced_tab(), "Advanced")
        layout.addWidget(tabs)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setObjectName("resetBtn")
        reset_btn.clicked.connect(self._on_reset)
        btn_layout.addWidget(reset_btn)

        apply_btn = QPushButton("Apply && Close")
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)

        layout.addLayout(btn_layout)

    def _build_expo_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        for axis in STICK_AXES:
            group = QGroupBox(AXIS_DISPLAY_NAMES.get(axis, axis))
            grid = QGridLayout(group)
            grid.setSpacing(8)

            # Expo slider
            grid.addWidget(QLabel("Expo:"), 0, 0)
            expo_slider = QSlider(Qt.Orientation.Horizontal)
            expo_slider.setRange(0, 100)
            expo_slider.setTickInterval(10)
            expo_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            grid.addWidget(expo_slider, 0, 1)
            expo_val = QLabel("0.00")
            expo_val.setMinimumWidth(40)
            expo_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(expo_val, 0, 2)

            # Rate slider
            grid.addWidget(QLabel("Rate:"), 1, 0)
            rate_slider = QSlider(Qt.Orientation.Horizontal)
            rate_slider.setRange(10, 100)
            rate_slider.setTickInterval(10)
            rate_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            grid.addWidget(rate_slider, 1, 1)
            rate_val = QLabel("1.00")
            rate_val.setMinimumWidth(40)
            rate_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(rate_val, 1, 2)

            # Deadzone slider
            grid.addWidget(QLabel("Deadzone:"), 2, 0)
            dz_slider = QSlider(Qt.Orientation.Horizontal)
            dz_slider.setRange(0, 30)
            dz_slider.setTickInterval(5)
            dz_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            grid.addWidget(dz_slider, 2, 1)
            dz_val = QLabel("0.02")
            dz_val.setMinimumWidth(40)
            dz_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(dz_val, 2, 2)

            # Smoothing slider
            grid.addWidget(QLabel("Smoothing:"), 3, 0)
            smooth_slider = QSlider(Qt.Orientation.Horizontal)
            smooth_slider.setRange(0, 99)
            smooth_slider.setTickInterval(10)
            smooth_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            grid.addWidget(smooth_slider, 3, 1)
            smooth_val = QLabel("0.00")
            smooth_val.setMinimumWidth(40)
            smooth_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(smooth_val, 3, 2)

            # Invert checkbox
            invert_cb = QCheckBox("Invert")
            grid.addWidget(invert_cb, 4, 0, 1, 2)

            # Expo preview
            preview = ExpoPreviewWidget()
            grid.addWidget(preview, 0, 3, 5, 1)

            # Connect slider signals to update labels & preview
            def make_updater(es, ev, rs, rv, dzs, dzv, sms, smv, prev):
                def update():
                    e = es.value() / 100.0
                    r = rs.value() / 100.0
                    dz = dzs.value() / 100.0
                    sm = sms.value() / 100.0
                    ev.setText(f"{e:.2f}")
                    rv.setText(f"{r:.2f}")
                    dzv.setText(f"{dz:.2f}")
                    smv.setText(f"{sm:.2f}")
                    prev.set_curve(e, r)
                return update

            updater = make_updater(expo_slider, expo_val, rate_slider, rate_val,
                                   dz_slider, dz_val, smooth_slider, smooth_val, preview)
            expo_slider.valueChanged.connect(updater)
            rate_slider.valueChanged.connect(updater)
            dz_slider.valueChanged.connect(updater)
            smooth_slider.valueChanged.connect(updater)

            self._widgets[f"{axis}_expo"] = expo_slider
            self._widgets[f"{axis}_rate"] = rate_slider
            self._widgets[f"{axis}_deadzone"] = dz_slider
            self._widgets[f"{axis}_smooth"] = smooth_slider
            self._widgets[f"{axis}_inverted"] = invert_cb
            self._widgets[f"{axis}_preview"] = preview

            scroll_layout.addWidget(group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        return widget

    def _build_mapping_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("Axis Mapping (which physical stick drives which virtual axis)")
        form = QFormLayout(group)
        form.setSpacing(12)

        for gamepad_axis, display_name in GAMEPAD_AXIS_NAMES.items():
            combo = QComboBox()
            for phys_axis in STICK_AXES:
                combo.addItem(AXIS_DISPLAY_NAMES.get(phys_axis, phys_axis), phys_axis)
            form.addRow(display_name + ":", combo)
            self._widgets[f"map_{gamepad_axis}"] = combo

        layout.addWidget(group)

        # Preset buttons
        preset_group = QGroupBox("Quick Presets")
        preset_layout = QHBoxLayout(preset_group)

        mode1_btn = QPushButton("Mode 1 (JP)")
        mode1_btn.clicked.connect(lambda: self._apply_mode_preset(1))
        preset_layout.addWidget(mode1_btn)

        mode2_btn = QPushButton("Mode 2 (US) — Default")
        mode2_btn.clicked.connect(lambda: self._apply_mode_preset(2))
        preset_layout.addWidget(mode2_btn)

        mode3_btn = QPushButton("Mode 3")
        mode3_btn.clicked.connect(lambda: self._apply_mode_preset(3))
        preset_layout.addWidget(mode3_btn)

        mode4_btn = QPushButton("Mode 4")
        mode4_btn.clicked.connect(lambda: self._apply_mode_preset(4))
        preset_layout.addWidget(mode4_btn)

        layout.addWidget(preset_group)
        layout.addStretch()
        return widget

    def _build_buttons_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("Button Mapping (RC input \u2192 Xbox button)")
        grid = QGridLayout(group)
        grid.setSpacing(8)

        grid.addWidget(QLabel("RC Input"), 0, 0)
        grid.addWidget(QLabel("\u2192"), 0, 1)
        grid.addWidget(QLabel("Xbox Button"), 0, 2)

        row = 1
        for rc_source in RC_BUTTON_SOURCES:
            label = QLabel(rc_source.replace('_', ' ').title())
            grid.addWidget(label, row, 0)
            grid.addWidget(QLabel("\u2192"), row, 1)

            combo = QComboBox()
            combo.addItem("(none)", "")
            for xbox_name in XBOX_BUTTONS:
                combo.addItem(xbox_name, xbox_name)
            grid.addWidget(combo, row, 2)
            self._widgets[f"btn_{rc_source}"] = combo
            row += 1

        layout.addWidget(group)

        note = QLabel(
            "Note: Camera Up/Down are triggered by the camera wheel on your RC.\n"
            "C1, C2, Photo, Video, Fn buttons depend on your RC model — \n"
            "they may need firmware-level discovery (check Debug Raw Data in Advanced)."
        )
        note.setStyleSheet("color: #808090; font-size: 10px; padding: 8px;")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        return widget

    def _build_triggers_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("Trigger Axis Mapping")
        form = QFormLayout(group)
        form.setSpacing(12)

        # Left Trigger
        lt_combo = QComboBox()
        lt_combo.addItem("(none)", "")
        for axis_key in TRIGGER_SOURCE_AXES:
            lt_combo.addItem(TRIGGER_AXIS_DISPLAY.get(axis_key, axis_key), axis_key)
        form.addRow("Left Trigger (LT):", lt_combo)
        self._widgets['trigger_lt'] = lt_combo

        # Right Trigger
        rt_combo = QComboBox()
        rt_combo.addItem("(none)", "")
        for axis_key in TRIGGER_SOURCE_AXES:
            rt_combo.addItem(TRIGGER_AXIS_DISPLAY.get(axis_key, axis_key), axis_key)
        form.addRow("Right Trigger (RT):", rt_combo)
        self._widgets['trigger_rt'] = rt_combo

        layout.addWidget(group)

        info = QLabel(
            "Maps the positive range (0 to +1) of the selected RC axis\n"
            "to the Xbox trigger range (0 to 255).\n\n"
            "For throttle (left vertical), push stick up to activate the trigger.\n"
            "For camera/scroll wheel, push the wheel in the positive direction."
        )
        info.setStyleSheet("color: #808090; font-size: 10px; padding: 12px;")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addStretch()
        return widget

    def _build_devices_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # RC Model Override
        model_group = QGroupBox("RC Model / Packet Format")
        model_form = QFormLayout(model_group)

        model_combo = QComboBox()
        model_combo.addItem("Auto-detect", "")
        model_combo.addItem("38-byte (RC-N1 / Serial)", "38-byte")
        model_combo.addItem("32-byte (RM330 / RC 2 / USB)", "32-byte")
        model_form.addRow("Packet format:", model_combo)
        self._widgets['rc_model_override'] = model_combo

        layout.addWidget(model_group)

        # Custom USB PID
        pid_group = QGroupBox("Custom USB Device PID")
        pid_layout = QVBoxLayout(pid_group)

        pid_row = QHBoxLayout()
        pid_entry = QLineEdit()
        pid_entry.setPlaceholderText("e.g. 0x1234")
        pid_entry.setMaximumWidth(150)
        self._widgets['custom_pid_entry'] = pid_entry
        pid_row.addWidget(pid_entry)

        add_pid_btn = QPushButton("Add PID")
        add_pid_btn.setObjectName("smallBtn")
        add_pid_btn.clicked.connect(self._add_custom_pid)
        pid_row.addWidget(add_pid_btn)
        pid_row.addStretch()
        pid_layout.addLayout(pid_row)

        self._pid_list_label = QLabel("")
        self._pid_list_label.setStyleSheet("color: #808090; font-size: 10px;")
        self._pid_list_label.setWordWrap(True)
        pid_layout.addWidget(self._pid_list_label)

        pid_note = QLabel(
            "Add USB Product IDs for unsupported DJI controllers.\n"
            "Connect the RC, check Device Manager for the PID, and enter it above.\n"
            "The PID will be remembered across sessions."
        )
        pid_note.setStyleSheet("color: #606070; font-size: 9px; padding-top: 4px;")
        pid_note.setWordWrap(True)
        pid_layout.addWidget(pid_note)

        layout.addWidget(pid_group)

        # Reconnect interval
        reconnect_group = QGroupBox("Connection")
        reconnect_form = QFormLayout(reconnect_group)

        reconnect_spin = QDoubleSpinBox()
        reconnect_spin.setRange(0.5, 30.0)
        reconnect_spin.setSingleStep(0.5)
        reconnect_spin.setDecimals(1)
        reconnect_spin.setSuffix(" s")
        reconnect_form.addRow("Reconnect interval:", reconnect_spin)
        self._widgets['reconnect_interval'] = reconnect_spin

        layout.addWidget(reconnect_group)
        layout.addStretch()
        return widget

    def _build_profiles_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("Saved Profiles")
        group_layout = QVBoxLayout(group)

        self._profile_list = QListWidget()
        self._profile_list.setMaximumHeight(180)
        group_layout.addWidget(self._profile_list)

        name_row = QHBoxLayout()
        self._profile_name = QLineEdit()
        self._profile_name.setPlaceholderText("Profile name...")
        name_row.addWidget(self._profile_name)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("smallBtn")
        save_btn.clicked.connect(self._save_profile)
        name_row.addWidget(save_btn)

        load_btn = QPushButton("Load")
        load_btn.setObjectName("smallBtn")
        load_btn.clicked.connect(self._load_profile)
        name_row.addWidget(load_btn)

        del_btn = QPushButton("Delete")
        del_btn.setObjectName("smallBtn")
        del_btn.setStyleSheet("background-color: #9a3030;")
        del_btn.clicked.connect(self._delete_profile)
        name_row.addWidget(del_btn)

        group_layout.addLayout(name_row)
        layout.addWidget(group)

        info = QLabel(
            "Profiles save your current expo, rate, deadzone, smoothing,\n"
            "axis mapping, button mapping, and trigger settings.\n"
            "Use different profiles for different simulators or flight styles."
        )
        info.setStyleSheet("color: #808090; font-size: 10px; padding: 8px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()
        return widget

    def _build_advanced_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Polling / Update rates
        rate_group = QGroupBox("Performance")
        form = QFormLayout(rate_group)

        poll_spin = QSpinBox()
        poll_spin.setRange(1, 100)
        poll_spin.setSuffix(" ms")
        form.addRow("Serial poll interval:", poll_spin)
        self._widgets['poll_interval'] = poll_spin

        cam_thresh = QDoubleSpinBox()
        cam_thresh.setRange(0.1, 1.0)
        cam_thresh.setSingleStep(0.05)
        cam_thresh.setDecimals(2)
        form.addRow("Camera button threshold:", cam_thresh)
        self._widgets['camera_threshold'] = cam_thresh

        layout.addWidget(rate_group)
        layout.addStretch()
        return widget

    def _load_values(self):
        """Populate widgets from config."""
        axes_cfg = self._config.get('axes', {})
        smooth_cfg = self._config.get('smoothing', {})
        for axis in STICK_AXES:
            ax = axes_cfg.get(axis, {})
            self._widgets[f"{axis}_expo"].setValue(int(ax.get('expo', 0.0) * 100))
            self._widgets[f"{axis}_rate"].setValue(int(ax.get('rate', 1.0) * 100))
            self._widgets[f"{axis}_deadzone"].setValue(int(ax.get('deadzone', 0.02) * 100))
            self._widgets[f"{axis}_smooth"].setValue(int(smooth_cfg.get(axis, 0.0) * 100))
            self._widgets[f"{axis}_inverted"].setChecked(ax.get('inverted', False))
            preview = self._widgets[f"{axis}_preview"]
            preview.set_curve(ax.get('expo', 0.0), ax.get('rate', 1.0))

        # Axis mapping
        mapping = self._config.get('axis_mapping', {})
        for gamepad_axis in GAMEPAD_AXIS_NAMES:
            combo = self._widgets.get(f"map_{gamepad_axis}")
            if combo:
                phys = mapping.get(gamepad_axis, gamepad_axis.replace('gamepad_', ''))
                idx = combo.findData(phys)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

        # Button mapping
        btn_map = self._config.get('button_mapping', {})
        for rc_source in RC_BUTTON_SOURCES:
            combo = self._widgets.get(f"btn_{rc_source}")
            if combo:
                xbox_name = btn_map.get(rc_source, "")
                idx = combo.findData(xbox_name)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

        # Trigger mapping
        trig = self._config.get('trigger_mapping', {})
        lt_combo = self._widgets.get('trigger_lt')
        if lt_combo:
            lt_val = trig.get('lt_axis') or ""
            idx = lt_combo.findData(lt_val)
            if idx >= 0:
                lt_combo.setCurrentIndex(idx)
        rt_combo = self._widgets.get('trigger_rt')
        if rt_combo:
            rt_val = trig.get('rt_axis') or ""
            idx = rt_combo.findData(rt_val)
            if idx >= 0:
                rt_combo.setCurrentIndex(idx)

        # Devices
        model_override = self._config.get('rc_model_override') or ""
        model_combo = self._widgets.get('rc_model_override')
        if model_combo:
            idx = model_combo.findData(model_override)
            if idx >= 0:
                model_combo.setCurrentIndex(idx)

        reconnect = self._widgets.get('reconnect_interval')
        if reconnect:
            reconnect.setValue(self._config.get('reconnect_interval_s', 2.0))

        # Custom PIDs display
        pids = self._config.get('custom_usb_pids', [])
        if pids:
            self._pid_list_label.setText(f"Current custom PIDs: {', '.join(str(p) for p in pids)}")
        else:
            self._pid_list_label.setText("No custom PIDs configured.")

        # Advanced
        self._widgets['poll_interval'].setValue(self._config.get('poll_interval_ms', 5))
        self._widgets['camera_threshold'].setValue(self._config.get('camera_button_threshold', 0.8))

        # Profiles list
        self._refresh_profile_list()

    def _gather_values(self) -> dict:
        """Collect current widget values into a config dict."""
        axes = {}
        for axis in STICK_AXES:
            axes[axis] = {
                'expo': self._widgets[f"{axis}_expo"].value() / 100.0,
                'rate': self._widgets[f"{axis}_rate"].value() / 100.0,
                'deadzone': self._widgets[f"{axis}_deadzone"].value() / 100.0,
                'inverted': self._widgets[f"{axis}_inverted"].isChecked(),
            }

        smoothing = {}
        for axis in STICK_AXES:
            smoothing[axis] = self._widgets[f"{axis}_smooth"].value() / 100.0

        mapping = {}
        for gamepad_axis in GAMEPAD_AXIS_NAMES:
            combo = self._widgets.get(f"map_{gamepad_axis}")
            if combo:
                mapping[gamepad_axis] = combo.currentData()

        btn_map = {}
        for rc_source in RC_BUTTON_SOURCES:
            combo = self._widgets.get(f"btn_{rc_source}")
            if combo:
                val = combo.currentData()
                if val:
                    btn_map[rc_source] = val

        # Trigger mapping
        lt_val = self._widgets['trigger_lt'].currentData() or None
        rt_val = self._widgets['trigger_rt'].currentData() or None

        # RC model override
        model_data = self._widgets['rc_model_override'].currentData()
        rc_model = model_data if model_data else None

        result = {
            'axes': axes,
            'smoothing': smoothing,
            'axis_mapping': mapping,
            'button_mapping': btn_map,
            'trigger_mapping': {
                'lt_axis': lt_val,
                'rt_axis': rt_val,
            },
            'rc_model_override': rc_model,
            'reconnect_interval_s': self._widgets['reconnect_interval'].value(),
            'poll_interval_ms': self._widgets['poll_interval'].value(),
            'camera_button_threshold': self._widgets['camera_threshold'].value(),
            'profiles': self._profiles,
            'active_profile': self._active_profile,
        }

        return result

    def _apply_mode_preset(self, mode: int):
        """Apply standard RC transmitter mode presets."""
        presets = {
            1: {
                'gamepad_left_x': AXIS_LEFT_H,
                'gamepad_left_y': AXIS_RIGHT_V,
                'gamepad_right_x': AXIS_RIGHT_H,
                'gamepad_right_y': AXIS_LEFT_V,
            },
            2: {
                'gamepad_left_x': AXIS_LEFT_H,
                'gamepad_left_y': AXIS_LEFT_V,
                'gamepad_right_x': AXIS_RIGHT_H,
                'gamepad_right_y': AXIS_RIGHT_V,
            },
            3: {
                'gamepad_left_x': AXIS_RIGHT_H,
                'gamepad_left_y': AXIS_LEFT_V,
                'gamepad_right_x': AXIS_LEFT_H,
                'gamepad_right_y': AXIS_RIGHT_V,
            },
            4: {
                'gamepad_left_x': AXIS_RIGHT_H,
                'gamepad_left_y': AXIS_RIGHT_V,
                'gamepad_right_x': AXIS_LEFT_H,
                'gamepad_right_y': AXIS_LEFT_V,
            },
        }
        preset = presets.get(mode, presets[2])
        for gamepad_axis, phys_axis in preset.items():
            combo = self._widgets.get(f"map_{gamepad_axis}")
            if combo:
                idx = combo.findData(phys_axis)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

    def _add_custom_pid(self):
        """Add a custom USB PID from the text entry."""
        text = self._widgets['custom_pid_entry'].text().strip()
        if not text:
            return
        try:
            if text.startswith("0x") or text.startswith("0X"):
                pid = int(text, 16)
            else:
                pid = int(text)
        except ValueError:
            QMessageBox.warning(self, "Invalid PID", f"'{text}' is not a valid hex number.\nUse format like 0x1234.")
            return

        pids = list(self._config.get('custom_usb_pids', []))
        hex_str = f"0x{pid:04X}"
        if pid not in pids and hex_str not in pids:
            pids.append(hex_str)
            self._config['custom_usb_pids'] = pids
            self._pid_list_label.setText(f"Current custom PIDs: {', '.join(str(p) for p in pids)}")
            self._widgets['custom_pid_entry'].clear()

    def _refresh_profile_list(self):
        """Refresh the profile list widget."""
        self._profile_list.clear()
        for name in sorted(self._profiles.keys()):
            self._profile_list.addItem(name)

    def _save_profile(self):
        """Save current settings as a named profile."""
        name = self._profile_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Profile Name", "Enter a name for the profile.")
            return
        snapshot = self._gather_values()
        # Remove profiles/active_profile from snapshot to avoid recursion
        snapshot.pop('profiles', None)
        snapshot.pop('active_profile', None)
        self._profiles[name] = copy.deepcopy(snapshot)
        self._active_profile = name
        self._refresh_profile_list()
        self._profile_name.clear()

    def _load_profile(self):
        """Load the selected profile."""
        item = self._profile_list.currentItem()
        if not item:
            return
        name = item.text()
        snapshot = self._profiles.get(name)
        if not snapshot:
            return
        # Temporarily replace config with profile snapshot and reload widgets
        old_config = self._config
        self._config = copy.deepcopy(snapshot)
        self._load_values()
        self._config = old_config
        self._active_profile = name

    def _delete_profile(self):
        """Delete the selected profile."""
        item = self._profile_list.currentItem()
        if not item:
            return
        name = item.text()
        self._profiles.pop(name, None)
        self._refresh_profile_list()

    def _on_apply(self):
        values = self._gather_values()
        # Include custom PIDs (they may have been added via the Devices tab)
        values['custom_usb_pids'] = self._config.get('custom_usb_pids', [])
        self.settings_changed.emit(values)
        self.accept()

    def _on_reset(self):
        from src.config_manager import DEFAULT_CONFIG
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        self._load_values()
