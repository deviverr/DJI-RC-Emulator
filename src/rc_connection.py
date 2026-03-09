"""
DJI RC connection manager — supports serial (RC-N1) and USB bulk (RM330, RC 2).
Handles device detection, connection, DUML communication,
and auto-reconnect on USB disconnect.
"""
import time
import logging
from threading import Thread, Event

import serial
import serial.tools.list_ports

from src.duml import (
    build_enable_simulator, build_read_sticks, read_packet,
    extract_packet_from_bytes, extract_all_packets_from_bytes,
    parse_stick_data, STICK_RESPONSE_LENGTHS,
)
from src.usb_transport import (
    USBBulkTransport, scan_dji_usb_devices, is_usb_available,
    DJI_PRODUCT_IDS,
)

logger = logging.getLogger(__name__)

# Strings to search for in USB serial port descriptions
PORT_IDENTIFIERS = ["For Protocol", "RM330", "DJI"]


def find_dji_port() -> str | None:
    """
    Scan serial ports for a DJI RC controller.
    Returns the port name (e.g. 'COM5') or None if not found.
    """
    ports = serial.tools.list_ports.comports(include_links=True)
    for port in ports:
        desc = (port.description or "").lower()
        mfr = (port.manufacturer or "").lower()
        hwid = (port.hwid or "").lower()
        combined = f"{desc} {mfr} {hwid}"
        for identifier in PORT_IDENTIFIERS:
            if identifier.lower() in combined:
                if "for protocol" in desc:
                    logger.info("Found DJI RC on %s: %s", port.device, port.description)
                    return port.device
    # Second pass: accept any DJI-related port
    for port in ports:
        desc = (port.description or "").lower()
        mfr = (port.manufacturer or "").lower()
        hwid = (port.hwid or "").lower()
        combined = f"{desc} {mfr} {hwid}"
        for identifier in PORT_IDENTIFIERS:
            if identifier.lower() in combined:
                logger.info("Found DJI device on %s: %s", port.device, port.description)
                return port.device
    return None


def list_all_ports() -> list[dict]:
    """Return list of all serial ports with details, for the GUI port selector."""
    result = []
    for port in serial.tools.list_ports.comports(include_links=True):
        result.append({
            'device': port.device,
            'description': port.description or '',
            'manufacturer': port.manufacturer or '',
            'hwid': port.hwid or '',
        })
    return result


def scan_all_devices() -> list[dict]:
    """
    Scan for all DJI devices — both serial ports and USB bulk devices.
    Returns unified list with 'type' field ('serial' or 'usb').
    """
    devices = []

    # Serial ports
    for port in serial.tools.list_ports.comports(include_links=True):
        devices.append({
            'type': 'serial',
            'device': port.device,
            'description': port.description or '',
            'manufacturer': port.manufacturer or '',
            'hwid': port.hwid or '',
            'is_dji': any(
                ident.lower() in f"{(port.description or '')} {(port.manufacturer or '')} {(port.hwid or '')}".lower()
                for ident in PORT_IDENTIFIERS
            ),
        })

    # USB bulk devices
    if is_usb_available():
        for usb_dev in scan_dji_usb_devices():
            sn = usb_dev.get('serial', '')
            sn_short = sn[:10] + '...' if len(sn) > 10 else sn
            devices.append({
                'type': 'usb',
                'device': f"USB:{usb_dev['pid_hex']}",
                'description': usb_dev['model_name'],
                'serial': sn,
                'serial_short': sn_short,
                'pid': usb_dev['pid'],
                'needs_zadig': usb_dev.get('needs_zadig', False),
                'duml_claimable': usb_dev.get('duml_claimable', False),
                'is_dji': True,
            })

    return devices


class RCConnection:
    """
    Manages connection to a DJI RC controller via serial or USB bulk.
    Runs a background thread that:
      1. Connects to the RC (auto-detect or specified device)
      2. Enables simulator mode for fast stick updates
      3. Continuously polls stick/button values
      4. Auto-reconnects on disconnect

    Callbacks:
      on_stick_data(data: dict) - called with parsed stick values
      on_connection_changed(connected: bool, port: str) - called on connect/disconnect
      on_raw_packet(packet: bytes) - called with every raw response (for debug view)
      on_error(message: str) - called on errors
    """

    def __init__(self):
        self._serial: serial.Serial | None = None
        self._usb: USBBulkTransport | None = None
        self._active_transport: str = ""  # "serial" or "usb"
        self._thread: Thread | None = None
        self._stop_event = Event()
        self._device_override: dict | None = None  # {"type": "serial"/"usb", ...}
        self._poll_interval: float = 0.005
        self._reconnect_interval: float = 2.0
        self._connected = False

        # Packet format override: None (auto), "38-byte", or "32-byte"
        self._format_override: str | None = None

        # Stats tracking
        self._packet_count = 0
        self._packets_per_sec = 0.0
        self._last_stats_time = 0.0
        self._last_stats_count = 0
        self._connect_time = 0.0
        self._model_name = ""

        # Callbacks
        self.on_stick_data = None
        self.on_connection_changed = None
        self.on_raw_packet = None
        self.on_error = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def port_name(self) -> str:
        if self._active_transport == "serial" and self._serial and self._serial.is_open:
            return self._serial.port
        if self._active_transport == "usb" and self._usb and self._usb.is_open:
            return self._usb.port
        return ""

    @property
    def packets_per_sec(self) -> float:
        return self._packets_per_sec

    @property
    def connect_elapsed(self) -> float:
        if self._connected and self._connect_time > 0:
            return time.time() - self._connect_time
        return 0.0

    @property
    def model_name(self) -> str:
        return self._model_name

    def set_device_override(self, device_info: dict | None):
        """
        Set a specific device to use instead of auto-detection.
        device_info: {"type": "serial", "port": "COM5"}
                  or {"type": "usb", "pid": 0x1023}
                  or None for auto-detect
        """
        self._device_override = device_info

    def set_port_override(self, port: str | None):
        """Legacy: set a specific COM port. Use set_device_override for USB."""
        if port:
            self._device_override = {"type": "serial", "port": port}
        else:
            self._device_override = None

    def set_poll_interval(self, interval_ms: float):
        """Set polling interval in milliseconds (minimum 1ms)."""
        self._poll_interval = max(0.001, interval_ms / 1000.0)

    def set_format_override(self, override: str | None):
        """Force packet format: '38-byte', '32-byte', or None for auto."""
        self._format_override = override

    def set_reconnect_interval(self, seconds: float):
        """Set reconnect delay in seconds."""
        self._reconnect_interval = max(0.5, seconds)

    def start(self):
        """Start the connection thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._run, daemon=True, name="RCConnection")
        self._thread.start()

    def stop(self):
        """Stop the connection thread and close transport."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._close_transport()

    def _close_transport(self):
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        if self._usb:
            try:
                self._usb.close()
            except Exception:
                pass
            self._usb = None
        self._active_transport = ""
        if self._connected:
            self._connected = False
            self._model_name = ""
            self._packets_per_sec = 0.0
            self._fire_connection_changed(False, "")

    def _fire_connection_changed(self, connected: bool, port: str):
        if self.on_connection_changed:
            try:
                self.on_connection_changed(connected, port)
            except Exception:
                pass

    def _fire_stick_data(self, data: dict):
        self._packet_count += 1
        self._update_stats()
        if self.on_stick_data:
            try:
                self.on_stick_data(data)
            except Exception:
                pass

    def _fire_raw_packet(self, packet: bytes):
        if self.on_raw_packet:
            try:
                self.on_raw_packet(packet)
            except Exception:
                pass

    def _fire_error(self, msg: str):
        logger.error(msg)
        if self.on_error:
            try:
                self.on_error(msg)
            except Exception:
                pass

    def _update_stats(self):
        """Update packets-per-second calculation."""
        now = time.time()
        elapsed = now - self._last_stats_time
        if elapsed >= 1.0:
            count_diff = self._packet_count - self._last_stats_count
            self._packets_per_sec = count_diff / elapsed
            self._last_stats_time = now
            self._last_stats_count = self._packet_count

    def _connect(self) -> bool:
        """Attempt to connect to the DJI RC via serial or USB."""
        override = self._device_override

        if override:
            if override.get('type') == 'usb':
                return self._connect_usb(pid=override.get('pid'))
            elif override.get('type') == 'serial':
                return self._connect_serial(port=override.get('port'))

        # Auto-detect: try serial first, then USB
        serial_port = find_dji_port()
        if serial_port:
            return self._connect_serial(port=serial_port)

        # Try USB bulk
        if is_usb_available():
            usb_devices = scan_dji_usb_devices()
            for dev in usb_devices:
                if dev.get('duml_claimable'):
                    return self._connect_usb(pid=dev['pid'])
                elif dev.get('needs_zadig'):
                    self._fire_error(
                        "DJI RC found via USB but needs WinUSB driver. "
                        "Use Zadig to install WinUSB on the BULK interface."
                    )
                    return False

        return False

    def _connect_serial(self, port: str) -> bool:
        """Connect via serial port."""
        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=115200,
                timeout=0.1,
                write_timeout=1.0,
            )
            logger.info("Opened serial port: %s", port)

            enable_pkt = build_enable_simulator()
            self._serial.write(enable_pkt)
            time.sleep(0.05)
            self._serial.reset_input_buffer()

            self._active_transport = "serial"
            self._connected = True
            self._connect_time = time.time()
            self._last_stats_time = self._connect_time
            self._last_stats_count = 0
            self._packet_count = 0
            self._model_name = f"Serial ({port})"
            self._fire_connection_changed(True, port)
            return True

        except (serial.SerialException, OSError) as e:
            self._fire_error(f"Could not open {port}: {e}")
            self._serial = None
            return False

    def _connect_usb(self, pid: int | None = None) -> bool:
        """Connect via USB bulk transport."""
        try:
            self._usb = USBBulkTransport()
            self._usb.open(pid=pid)
            logger.info("Opened USB device: %s", self._usb.port)

            enable_pkt = build_enable_simulator()
            self._usb.write(enable_pkt)
            time.sleep(0.1)
            # Read enable response (don't discard — log for diagnostics)
            try:
                resp = self._usb.read(512, timeout=200)
                if resp:
                    logger.info("Enable-sim response (%d bytes): %s", len(resp), resp.hex())
            except Exception:
                pass

            self._active_transport = "usb"
            self._connected = True
            self._connect_time = time.time()
            self._last_stats_time = self._connect_time
            self._last_stats_count = 0
            self._packet_count = 0
            # Resolve model name from PID
            if pid and pid in DJI_PRODUCT_IDS:
                self._model_name = DJI_PRODUCT_IDS[pid]
            else:
                self._model_name = self._usb.port
            self._fire_connection_changed(True, self._usb.port)
            return True

        except ConnectionError as e:
            self._fire_error(str(e))
            self._usb = None
            return False
        except Exception as e:
            self._fire_error(f"USB connection error: {e}")
            self._usb = None
            return False

    def _run(self):
        """Main connection loop: connect, poll, reconnect on failure."""
        while not self._stop_event.is_set():
            if not self._connected:
                if not self._connect():
                    self._stop_event.wait(self._reconnect_interval)
                    continue

            try:
                if self._active_transport == "serial":
                    self._poll_loop_serial()
                elif self._active_transport == "usb":
                    self._poll_loop_usb()
            except (serial.SerialException, OSError) as e:
                self._fire_error(f"Connection lost: {e}")
            except Exception as e:
                self._fire_error(f"Unexpected error: {e}")

            self._close_transport()
            if not self._stop_event.is_set():
                self._stop_event.wait(self._reconnect_interval)

    def _try_parse_stick(self, packet: bytes) -> dict | None:
        """Parse stick data, respecting format override."""
        if self._format_override:
            return parse_stick_data(packet, format_override=self._format_override)
        if len(packet) in STICK_RESPONSE_LENGTHS:
            return parse_stick_data(packet)
        return None

    def _poll_loop_serial(self):
        """Poll stick data over serial."""
        consecutive_errors = 0
        max_consecutive_errors = 20

        while not self._stop_event.is_set():
            try:
                request = build_read_sticks()
                self._serial.write(request)

                packet = read_packet(self._serial)
                if packet is None:
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        raise serial.SerialException("Too many consecutive read failures")
                    continue

                consecutive_errors = 0
                self._fire_raw_packet(packet)

                data = self._try_parse_stick(packet)
                if data:
                    self._fire_stick_data(data)

                time.sleep(self._poll_interval)

            except (serial.SerialException, OSError):
                raise

    def _poll_loop_usb(self):
        """Poll stick data over USB bulk — adaptive passive/active approach.

        Some DJI smart controllers (RM330, RC 2) push stick data
        automatically after enable_simulator, while simpler RCs need
        explicit read_sticks requests.  This loop tries passive
        listening first, then falls back to active polling.
        """
        consecutive_timeouts = 0
        max_consecutive_timeouts = 100
        last_enable_time = time.time()
        enable_interval = 3.0
        use_active_poll = True   # RM330/RC2 need explicit read_sticks requests
        passive_timeout_count = 0
        max_passive_tries = 5   # brief passive check before active fallback
        total_packets = 0
        total_stick_packets = 0
        logged_first_data = False

        logger.info("USB poll: starting in active mode")

        while not self._stop_event.is_set():
            try:
                now = time.time()

                # Re-send enable_simulator periodically
                if now - last_enable_time >= enable_interval:
                    try:
                        self._usb.write(build_enable_simulator())
                        last_enable_time = now
                    except Exception as e:
                        logger.debug("Re-send enable_simulator failed: %s", e)

                # In active mode, explicitly request stick data
                if use_active_poll:
                    self._usb.write(build_read_sticks())

                # Read — minimal timeout for lowest latency
                raw = self._usb.read(512, timeout=10)

                if raw is None or len(raw) == 0:
                    consecutive_timeouts += 1

                    if not use_active_poll:
                        passive_timeout_count += 1
                        if passive_timeout_count >= max_passive_tries:
                            use_active_poll = True
                            logger.info(
                                "No data in passive mode after %d reads "
                                "— switching to active DUML polling",
                                passive_timeout_count,
                            )

                    if consecutive_timeouts >= max_consecutive_timeouts:
                        raise OSError(
                            "No data from DJI RC after %d reads (%s mode)"
                            % (
                                max_consecutive_timeouts,
                                "active" if use_active_poll else "passive",
                            )
                        )
                    continue

                consecutive_timeouts = 0

                # Diagnostic: log first data received
                if not logged_first_data:
                    logged_first_data = True
                    logger.info(
                        "First USB data (%s mode, %d bytes): %s",
                        "active" if use_active_poll else "passive",
                        len(raw),
                        raw[:64].hex(),
                    )

                # Extract ALL DUML packets from the bulk read
                packets = extract_all_packets_from_bytes(raw)

                if not packets:
                    if total_packets < 10:
                        logger.info(
                            "USB data (%d bytes) — no valid DUML packets: %s",
                            len(raw),
                            raw[:64].hex(),
                        )
                    continue

                for packet in packets:
                    total_packets += 1
                    self._fire_raw_packet(packet)

                    data = self._try_parse_stick(packet)
                    if data:
                        total_stick_packets += 1
                        if total_stick_packets == 1:
                            logger.info("Receiving stick data from RC")
                        self._fire_stick_data(data)
                    elif total_packets <= 20:
                        # Log non-stick packets for diagnostics
                        cmd_s = packet[9] if len(packet) > 9 else 0xFF
                        cmd_i = packet[10] if len(packet) > 10 else 0xFF
                        logger.info(
                            "DUML pkt #%d: len=%d cmd_set=0x%02X "
                            "cmd_id=0x%02X data=%s",
                            total_packets,
                            len(packet),
                            cmd_s,
                            cmd_i,
                            packet.hex(),
                        )

                # No sleep — USB read timeout provides pacing

            except (OSError, ConnectionError):
                raise
