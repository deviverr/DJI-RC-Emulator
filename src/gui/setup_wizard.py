"""
First-run setup wizard and tutorial cards for DJI RC Emulator.
Shows step-by-step setup guidance on first launch.
"""
import os
import sys
import subprocess

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QPixmap, QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QWidget, QFrame, QSizePolicy, QMessageBox,
)

# Resolved at import time
_ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "icon.ico")
_PNG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "DJI_RC_Icon_12x12.png")


def _icon_pixmap(size: int = 64) -> QPixmap | None:
    for path in (_PNG_PATH, _ICON_PATH):
        if os.path.exists(path):
            px = QPixmap(path)
            if not px.isNull():
                return px.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    return None


def _card(title: str, body: str, highlight_color: str = "#44aaff") -> QFrame:
    """Create a styled tutorial card widget."""
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background-color: #22222a; border: 1px solid #3a3a45; "
        f"border-radius: 10px; border-left: 4px solid {highlight_color}; }}"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 14, 18, 14)
    layout.setSpacing(8)

    t = QLabel(title)
    t.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {highlight_color}; border: none;")
    layout.addWidget(t)

    b = QLabel(body)
    b.setWordWrap(True)
    b.setStyleSheet("font-size: 12px; color: #c0c0cc; line-height: 1.5; border: none;")
    layout.addWidget(b)

    return frame


class SetupWizard(QDialog):
    """Multi-page setup wizard shown on first run."""

    def __init__(self, missing: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DJI RC Emulator — Setup")
        self.setMinimumSize(560, 480)
        self.setStyleSheet("""
            QDialog { background-color: #1a1a20; }
            QLabel { color: #d0d0d8; font-family: 'Segoe UI', sans-serif; }
            QPushButton {
                background-color: #2d5aa0; border: none; border-radius: 6px;
                color: white; padding: 10px 28px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background-color: #3568b8; }
            QPushButton#skipBtn {
                background-color: transparent; color: #808090; font-size: 11px;
            }
            QPushButton#skipBtn:hover { color: #b0b0c0; }
            QPushButton#installBtn {
                background-color: #2a8a40; font-size: 12px;
            }
            QPushButton#installBtn:hover { background-color: #35a050; }
        """)

        icon_px = _icon_pixmap(48)
        if icon_px:
            self.setWindowIcon(QIcon(icon_px))

        self._missing = missing
        self._stack = QStackedWidget()
        self._pages = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 16)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._stack, stretch=1)

        # Navigation
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(0, 12, 0, 0)

        self._skip_btn = QPushButton("Skip setup")
        self._skip_btn.setObjectName("skipBtn")
        self._skip_btn.clicked.connect(self.accept)
        nav_layout.addWidget(self._skip_btn)

        nav_layout.addStretch()

        self._page_label = QLabel("1 / 3")
        self._page_label.setStyleSheet("color: #606070; font-size: 11px;")
        nav_layout.addWidget(self._page_label)

        nav_layout.addStretch()

        self._back_btn = QPushButton("Back")
        self._back_btn.setStyleSheet("background-color: #404050;")
        self._back_btn.clicked.connect(self._go_back)
        nav_layout.addWidget(self._back_btn)

        self._next_btn = QPushButton("Next →")
        self._next_btn.clicked.connect(self._go_next)
        nav_layout.addWidget(self._next_btn)

        main_layout.addLayout(nav_layout)

        self._build_pages()
        self._update_nav()

    def _build_pages(self):
        # Page 1: Welcome
        self._add_page(self._welcome_page())
        # Page 2: Dependencies
        self._add_page(self._deps_page())
        # Page 3: USB connection guide
        self._add_page(self._connect_page())

    def _add_page(self, widget: QWidget):
        self._pages.append(widget)
        self._stack.addWidget(widget)

    def _welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        # Icon + title
        header = QHBoxLayout()
        px = _icon_pixmap(72)
        if px:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(px)
            header.addWidget(icon_lbl)
        title = QLabel("Welcome to DJI RC Emulator")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #e0e0e8;")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        layout.addWidget(_card(
            "🎮  What does this do?",
            "Turns your DJI RC controller into an Xbox 360 gamepad for FPV simulators "
            "like Liftoff, VelociDrone, DCL, and any PC game.\n\n"
            "Your RC connects via USB-C and this app reads its sticks and buttons, "
            "then emulates a virtual Xbox 360 controller.",
            "#44aaff"
        ))

        layout.addWidget(_card(
            "📋  Quick overview",
            "1. Install required drivers (next page)\n"
            "2. Plug in your DJI RC via USB-C (bottom port)\n"
            "3. Click Connect — sticks should move on screen\n"
            "4. Open your simulator and select Xbox 360 controller",
            "#ffaa44"
        ))

        layout.addStretch()
        return page

    def _deps_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        title = QLabel("Setup Requirements")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e0e0e8;")
        layout.addWidget(title)

        # ViGEm
        vigem_ok = not self._missing.get('vigem')
        status = "✅ Installed" if vigem_ok else "❌ Not found"
        color = "#44cc44" if vigem_ok else "#ff6666"
        vigem_card = _card(
            f"ViGEm Bus Driver — {status}",
            "Required for virtual Xbox 360 gamepad emulation.\n\n"
            "Download from: github.com/nefarius/ViGEmBus/releases\n"
            "Install ViGEmBus_Setup_x64.msi and reboot.",
            color
        )
        layout.addWidget(vigem_card)

        if not vigem_ok:
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            open_btn = QPushButton("Open ViGEm Download Page")
            open_btn.setObjectName("installBtn")
            open_btn.clicked.connect(lambda: os.startfile("https://github.com/nefarius/ViGEmBus/releases"))
            btn_layout.addWidget(open_btn)
            layout.addLayout(btn_layout)

        # Python packages
        pkgs_ok = not self._missing.get('packages')
        status = "✅ All installed" if pkgs_ok else "⚠️ Some missing"
        color = "#44cc44" if pkgs_ok else "#ffaa44"
        pkg_card = _card(
            f"Python Packages — {status}",
            "PySide6, vgamepad, pyserial, pyusb, libusb\n\n"
            + ("All dependencies are installed and ready." if pkgs_ok else
               f"Missing: {', '.join(self._missing.get('packages', []))}"),
            color
        )
        layout.addWidget(pkg_card)

        if not pkgs_ok:
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            install_btn = QPushButton("Install Missing Packages")
            install_btn.setObjectName("installBtn")
            install_btn.clicked.connect(self._install_packages)
            self._install_btn = install_btn
            btn_layout.addWidget(install_btn)
            layout.addLayout(btn_layout)

        # WinUSB / Zadig
        layout.addWidget(_card(
            "🔌  WinUSB Driver (for smart RCs like RM330)",
            "If you have a DJI RC with a touchscreen (RM330, RC 2), "
            "you may need to install the WinUSB driver via Zadig.\n\n"
            "The app will prompt you if this is needed — no action required now.",
            "#808090"
        ))

        layout.addStretch()
        return page

    def _connect_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        title = QLabel("How to Connect")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e0e0e8;")
        layout.addWidget(title)

        layout.addWidget(_card(
            "Step 1 — Plug in your DJI RC",
            "Connect a USB-C cable to the BOTTOM port of your RC controller.\n"
            "(Not the side/top port — that's usually for charging only.)\n\n"
            "Turn on the RC if it doesn't power on automatically.",
            "#44aaff"
        ))

        layout.addWidget(_card(
            "Step 2 — Click Connect",
            "The app will auto-detect your RC.\n"
            "If it's not found, click 'Scan' and select it from the dropdown.\n\n"
            "For RM330/RC2: the app may ask you to install WinUSB driver (one-time).",
            "#ffaa44"
        ))

        layout.addWidget(_card(
            "Step 3 — Open your simulator",
            "Once sticks are moving on screen, open Liftoff (or your sim).\n"
            "Go to Controller settings and select 'Xbox 360 Controller'.\n\n"
            "Tip: Click Settings in this app to adjust expo, rates, and button mapping.",
            "#44cc44"
        ))

        layout.addStretch()

        done_note = QLabel("You're all set! Click 'Finish' to start using the app.")
        done_note.setStyleSheet("font-size: 12px; color: #a0a0b0; font-style: italic;")
        done_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(done_note)

        return page

    def _install_packages(self):
        """Attempt to install missing Python packages."""
        self._install_btn.setEnabled(False)
        self._install_btn.setText("Installing...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                QMessageBox.information(self, "Success", "All packages installed successfully!")
                self._install_btn.setText("✅ Installed")
            else:
                QMessageBox.warning(self, "Warning",
                    f"Some packages may have failed:\n\n{result.stderr[:500]}")
                self._install_btn.setText("Retry Install")
                self._install_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Install failed: {e}")
            self._install_btn.setText("Retry Install")
            self._install_btn.setEnabled(True)

    def _go_next(self):
        idx = self._stack.currentIndex()
        if idx < len(self._pages) - 1:
            self._stack.setCurrentIndex(idx + 1)
        else:
            self.accept()
        self._update_nav()

    def _go_back(self):
        idx = self._stack.currentIndex()
        if idx > 0:
            self._stack.setCurrentIndex(idx - 1)
        self._update_nav()

    def _update_nav(self):
        idx = self._stack.currentIndex()
        total = len(self._pages)
        self._page_label.setText(f"{idx + 1} / {total}")
        self._back_btn.setVisible(idx > 0)
        self._next_btn.setText("Finish ✓" if idx == total - 1 else "Next →")


def check_missing_deps() -> dict:
    """Check for missing dependencies. Returns dict of what's missing."""
    missing = {}

    # Check Python packages
    missing_pkgs = []
    for pkg, import_name in [
        ("PySide6", "PySide6"),
        ("vgamepad", "vgamepad"),
        ("pyserial", "serial"),
        ("pyusb", "usb"),
        ("libusb", "libusb"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing_pkgs.append(pkg)
    if missing_pkgs:
        missing['packages'] = missing_pkgs

    # Check ViGEm
    try:
        import vgamepad
        vgamepad.VX360Gamepad()
    except Exception:
        missing['vigem'] = True

    return missing


def should_show_wizard() -> bool:
    """Check if this is the first run (no config.json yet or flag file)."""
    flag = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".setup_done")
    return not os.path.exists(flag)


def mark_setup_done():
    """Mark setup as complete so wizard doesn't show again."""
    flag = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".setup_done")
    with open(flag, 'w') as f:
        f.write("1")
