# DJI RC Emulator for FPV Simulators

Use your **DJI RC** (RM330, RC-N1, RC-N2, RC231, etc.) as a standard Xbox 360 controller in FPV simulators like **Liftoff**, **DCL - The Game**, **VelociDrone**, or any PC game.

The RC connects via **USB-C** and this app reads its sticks/buttons over the DJI DUML serial protocol, then emulates a virtual Xbox 360 gamepad via ViGEm.

![Screenshot placeholder]

---

## Features

- **Live stick visualization** — see both sticks move in real-time
- **Expo / Rates curves** — adjustable per-axis with visual preview
- **Axis remapping** — swap sticks, invert axes, Mode 1/2/3/4 presets
- **Button mapping** — map camera wheel & RC buttons to Xbox buttons
- **Deadzones** — configurable per-axis
- **Auto-reconnect** — handles USB disconnect/reconnect gracefully
- **High polling rate** — ~200Hz serial polling (vs 10Hz in similar tools)
- **Persistent config** — all settings saved to `config.json`

---

## Requirements

1. **Windows 10/11** (ViGEm is Windows-only)
2. **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)
3. **ViGEm Bus Driver** — **REQUIRED** for virtual gamepad
   - Download from: [github.com/nefarius/ViGEmBus/releases](https://github.com/nefarius/ViGEmBus/releases)
   - Install `ViGEmBus_Setup_x64.msi`
   - Reboot after install
4. **DJI RC controller** connected via USB-C (bottom port)

---

## Installation

```bash
# 1. Install ViGEm Bus Driver first (see link above)

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Connect your DJI RC via USB-C

# 4. Run the app
python main.py
# Or double-click start.bat
```

---

## Usage

1. **Connect your DJI RC** to your PC via the USB-C port on the bottom of the controller
2. **Launch the app** — run `start.bat` or `python main.py`
3. **Click "Connect"** — the app will auto-detect the RC serial port. If not found, select the port manually from the dropdown (look for "DJI USB VCOM For Protocol")
4. **Move the sticks** — you should see them move in the visualizer
5. **Verify in Windows** — open `joy.cpl` (Game Controllers) and check the "Xbox 360 Controller" appears and responds
6. **Open your simulator** (Liftoff, etc.) — configure it to use the Xbox 360 controller
7. **Adjust settings** — click Settings to tune expo, rates, deadzones, axis mapping, and button mapping

### Settings

- **Expo** — 0.0 (linear) to 1.0 (max exponential curve). Higher expo = more precise center control, aggressive at edges. Good starting value for FPV: 0.2–0.4
- **Rate** — Output multiplier. 1.0 = full range. Lower = less sensitive overall
- **Deadzone** — Ignores stick movement near center. Set just high enough to eliminate drift
- **Axis Mapping** — Use Mode 2 preset (default) for standard DJI/FPV layout. Switch to Mode 1 if you fly Japanese-style
- **Buttons** — Camera wheel up/down default to Y (restart race) and B (recover drone) for DCL/Liftoff

---

## Troubleshooting

### "ViGEm not available" error
- Install the ViGEm Bus Driver from [github.com/nefarius/ViGEmBus/releases](https://github.com/nefarius/ViGEmBus/releases)
- Reboot after installing
- Then run `pip install vgamepad` again

### RC not detected
- Make sure USB-C is plugged into the **bottom port** of the RC (not the top/side)
- Check Device Manager → look for "DJI USB VCOM" ports
- Try manually selecting the COM port in the dropdown
- If you see multiple DJI ports, choose the one with "For Protocol" in the name

### Sticks not responding
- Make sure you clicked "Connect" and the status shows green
- The app sends a simulator-mode command to the RC for fast updates
- If sticks respond slowly, disconnect and reconnect

### Input lag
- Default polling is 5ms (~200Hz). You can lower it in Settings → Advanced → Serial poll interval (minimum 1ms)
- Gamepad update rate defaults to 125Hz, adjustable up to 500Hz

### Liftoff doesn't detect the controller
- Make sure the app is running and connected (green status)
- In Liftoff: go to Settings → Controller → select "Xbox 360 Controller"
- Remap axes in Liftoff if needed

---

## Supported Controllers

| Controller | Status |
|-----------|--------|
| DJI RC (RM330) | ✅ Primary target |
| DJI RC-N1 | ✅ Tested (reference project) |
| DJI RC 231 (Mavic 3) | ✅ Tested (reference project) |
| DJI RC-N2 | Should work (same protocol) |
| DJI RC 2 | Should work (same protocol) |
| DJI RC Pro | Untested — may need different cmd bytes |

---

## Project Structure

```
DJI_RC_Liftoff_emu/
├── main.py                    # Entry point
├── requirements.txt           # Python dependencies
├── config.json                # Generated on first run
├── start.bat                  # Quick launcher
├── README.md                  # This file
└── src/
    ├── duml.py                # DUML protocol (CRC, packets)
    ├── rc_connection.py       # Serial port management
    ├── input_processor.py     # Expo, rates, deadzones, remapping
    ├── gamepad.py             # Virtual Xbox 360 controller
    ├── config_manager.py      # JSON config persistence
    └── gui/
        ├── main_window.py     # Main application window
        ├── stick_widget.py    # Stick position visualizer
        └── settings_dialog.py # Settings UI
```

---

## Credits

- Protocol reverse engineering based on [DJI_RC-N1_SIMULATOR_FLY_DCL](https://github.com/) by Ivan Yakymenko
- Virtual gamepad via [ViGEm](https://vigem.org/) and [vgamepad](https://pypi.org/project/vgamepad/)

## License

MIT License
