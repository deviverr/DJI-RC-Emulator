"""Quick validation tests for DJI RC Emulator core modules."""
from src.duml import (
    build_read_sticks, build_enable_simulator, calc_crc16, calc_crc8,
    parse_stick_data, STICK_RESPONSE_LENGTH,
)
from src.input_processor import InputProcessor, normalize_raw, apply_expo, apply_deadzone

def test_duml():
    # Read sticks packet
    pkt = build_read_sticks()
    print("Read sticks packet:", " ".join(f"{b:02x}" for b in pkt))
    assert pkt[0] == 0x55, "Header must be 0x55"
    assert len(pkt) == 13, f"Empty payload packet should be 13 bytes, got {len(pkt)}"

    # Enable sim packet
    sim = build_enable_simulator()
    print("Enable sim packet:", " ".join(f"{b:02x}" for b in sim))
    assert len(sim) == 14, f"Sim packet should be 14 bytes, got {len(sim)}"
    assert sim[-3] == 0x01, "Sim payload should be 0x01"

    # Verify CRC header byte is valid
    assert pkt[3] == calc_crc8(pkt[:3], 3), "Header CRC mismatch"
    print("DUML tests PASSED")


def test_input_processor():
    proc = InputProcessor()

    # Center -> 0
    center = {"right_h": 1024, "right_v": 1024, "left_h": 1024, "left_v": 1024, "camera": 1024}
    r = proc.process(center)
    assert abs(r["gamepad_left_x"]) <= 1, f"Center LX should be ~0, got {r['gamepad_left_x']}"
    assert abs(r["gamepad_right_y"]) <= 1, f"Center RY should be ~0, got {r['gamepad_right_y']}"

    # Max -> +32767
    maxv = {"right_h": 1684, "right_v": 1684, "left_h": 1684, "left_v": 1684, "camera": 1684}
    r = proc.process(maxv)
    assert r["gamepad_right_x"] == 32767, f"Max RX should be 32767, got {r['gamepad_right_x']}"

    # Min -> -32767
    minv = {"right_h": 364, "right_v": 364, "left_h": 364, "left_v": 364, "camera": 364}
    r = proc.process(minv)
    assert r["gamepad_right_x"] == -32767, f"Min RX should be -32767, got {r['gamepad_right_x']}"

    # Camera buttons
    cam_up = {"right_h": 1024, "right_v": 1024, "left_h": 1024, "left_v": 1024, "camera": 1684}
    r = proc.process(cam_up)
    assert r["camera_up"] is True, "Camera up should trigger"
    assert r["camera_down"] is False, "Camera down should not trigger"

    cam_down = {"right_h": 1024, "right_v": 1024, "left_h": 1024, "left_v": 1024, "camera": 364}
    r = proc.process(cam_down)
    assert r["camera_down"] is True, "Camera down should trigger"

    # Expo reduces mid-range
    proc.expo["right_h"] = 0.5
    half = {"right_h": 1354, "right_v": 1024, "left_h": 1024, "left_v": 1024, "camera": 1024}
    r = proc.process(half)
    print(f"Half stick with expo 0.5: {r['gamepad_right_x']}")
    assert r["gamepad_right_x"] < 16384, "Expo should reduce mid-range output"

    # Deadzone
    assert apply_deadzone(0.01, 0.05) == 0.0, "Value inside deadzone should be 0"
    assert apply_deadzone(0.1, 0.05) > 0.0, "Value outside deadzone should be nonzero"

    # Expo: 0 = linear
    assert apply_expo(0.5, 0.0) == 0.5, "Zero expo should be linear"
    # Expo: 1.0 should reduce mid-range
    assert apply_expo(0.5, 1.0) < 0.5, "Full expo should reduce mid value"
    # Expo at extremes should pass through
    assert abs(apply_expo(1.0, 1.0) - 1.0) < 0.001, "Expo at max should be ~1.0"
    assert abs(apply_expo(-1.0, 1.0) - (-1.0)) < 0.001, "Expo at min should be ~-1.0"

    print("Input processor tests PASSED")


def test_config():
    from src.config_manager import ConfigManager, DEFAULT_CONFIG
    import tempfile, os, json

    # Test with temp file
    tmp = os.path.join(tempfile.gettempdir(), "dji_rc_test_config.json")
    try:
        mgr = ConfigManager(tmp)
        cfg = mgr.load()
        assert os.path.exists(tmp), "Config file should be created on first load"

        # Verify defaults
        assert cfg["poll_interval_ms"] == 5
        assert cfg["axes"]["right_h"]["expo"] == 0.0

        # Test update
        mgr.update({"poll_interval_ms": 10})
        assert mgr.config["poll_interval_ms"] == 10

        # Reload and verify persistence
        mgr2 = ConfigManager(tmp)
        cfg2 = mgr2.load()
        assert cfg2["poll_interval_ms"] == 10, "Updated value should persist"

        print("Config tests PASSED")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


if __name__ == "__main__":
    test_duml()
    test_input_processor()
    test_config()
    print()
    print("=" * 40)
    print("ALL TESTS PASSED")
    print("=" * 40)
