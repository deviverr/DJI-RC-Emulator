# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for DJI RC Emulator.
Bundles libusb and vgamepad DLLs alongside the application.

Usage:
    pyinstaller DJI_RC_Emulator.spec --noconfirm
    or
    build.bat
"""
import os
import sys
from pathlib import Path

block_cipher = None


# ── Locate libusb DLL ──────────────────────────────────────────────────────────
def find_libusb_dll():
    """Find libusb-1.0.dll from the libusb Python package."""
    try:
        import libusb as _lb
        pkg_dir = Path(_lb.__file__).parent
        for arch in ['x86_64', 'x86', 'arm64']:
            candidate = pkg_dir / '_platform' / 'windows' / arch / 'libusb-1.0.dll'
            if candidate.exists():
                return str(candidate)
    except ImportError:
        pass
    return None


# ── Locate vgamepad DLLs ──────────────────────────────────────────────────────
def find_vgamepad_dlls():
    """Find ViGEmClient DLL matching current architecture from vgamepad package."""
    import platform
    arch = "x64" if platform.architecture()[0] == "64bit" else "x86"
    dlls = []
    try:
        import vgamepad as vg
        pkg_dir = Path(vg.__file__).parent
        candidate = pkg_dir / 'win' / 'vigem' / 'client' / arch / 'ViGEmClient.dll'
        if candidate.exists():
            # Preserve directory structure so vgamepad can find it at runtime
            rel_dest = str(Path('vgamepad') / 'win' / 'vigem' / 'client' / arch)
            dlls.append((str(candidate), rel_dest))
    except ImportError:
        pass
    return dlls


# ── Collect binaries ──────────────────────────────────────────────────────────
binaries = []

libusb_dll = find_libusb_dll()
if libusb_dll:
    print(f"Found libusb DLL: {libusb_dll}")
    binaries.append((libusb_dll, '.'))

for dll_path, dll_dest in find_vgamepad_dlls():
    print(f"Found vgamepad DLL: {dll_path} -> {dll_dest}")
    binaries.append((dll_path, dll_dest))


# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=[
        ('icon.ico', '.'),
        ('DJI_RC_Icon_12x12.png', '.'),
    ] + ([('ViGEmBus_Setup_x64.msi', '.')] if os.path.exists('ViGEmBus_Setup_x64.msi') else []),
    hiddenimports=[
        'usb.backend.libusb1',
        'usb.backend.libusb0',
        'usb.core',
        'usb.util',
        'serial.tools.list_ports',
        'serial.tools.list_ports_windows',
        'vgamepad',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'PIL',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DJI RC Emulator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon='icon.ico',
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DJI RC Emulator',
)
