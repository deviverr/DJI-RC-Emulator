"""
USB bulk transport for DJI RC smart controllers (RM330, RC 2, etc.).
These controllers don't expose serial VCOM ports — they use raw USB bulk
endpoints for DUML communication.

Requires:
  - pyusb + libusb (pip install pyusb libusb)
  - WinUSB driver installed on the DJI BULK interface via Zadig
"""
import logging
import os
import sys

logger = logging.getLogger(__name__)

# DJI USB vendor ID
DJI_VENDOR_ID = 0x2CA3

# Known DJI RC product IDs (add more as discovered)
DJI_PRODUCT_IDS = {
    0x1023: "DJI RC (RM330)",
    0x001F: "DJI RC-N1 / RC231",
    0x0036: "DJI RC-N1 (alt)",
    0x0047: "DJI RC 2",
    0x004B: "DJI RC Pro",
    0x0064: "DJI RC Pro 2",
    0x0082: "DJI RC-N2",
    0x0059: "DJI RC Motion",
    0x003B: "DJI RC-N3",
}


def load_custom_pids(pids: list):
    """
    Extend DJI_PRODUCT_IDS at runtime from user config.
    pids: list of int or hex-string values, e.g. [0x1234, "0x5678"]
    """
    for entry in pids:
        if isinstance(entry, str):
            try:
                pid = int(entry, 16)
            except ValueError:
                continue
        elif isinstance(entry, int):
            pid = entry
        else:
            continue
        if pid not in DJI_PRODUCT_IDS:
            DJI_PRODUCT_IDS[pid] = f"Custom Device (PID:{pid:#06x})"
            logger.info("Registered custom USB PID: %s", f"{pid:#06x}")


# Interface class/subclass/protocol for DUML bulk interface
DUML_INTERFACE_CLASS = 0xFF
DUML_INTERFACE_SUBCLASS = 0x43
DUML_INTERFACE_PROTOCOL = 0x01

# Try to import USB libraries
try:
    import usb.core
    import usb.util
    import usb.backend.libusb1

    # Find the libusb-1.0 DLL from the libusb package
    _backend = None
    try:
        import libusb as _libusb_pkg
        _pkg_dir = os.path.dirname(_libusb_pkg.__file__)
        # Check platform-specific paths
        _dll_candidates = [
            os.path.join(_pkg_dir, '_platform', 'windows', 'x86_64', 'libusb-1.0.dll'),
            os.path.join(_pkg_dir, '_platform', 'windows', 'x86', 'libusb-1.0.dll'),
            os.path.join(_pkg_dir, '_platform', 'windows', 'arm64', 'libusb-1.0.dll'),
        ]
        for dll_path in _dll_candidates:
            if os.path.exists(dll_path):
                _backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
                if _backend is not None:
                    logger.info("Using libusb1 backend: %s", dll_path)
                    break
    except ImportError:
        pass

    if _backend is None:
        # Try default backend discovery
        _backend = usb.backend.libusb1.get_backend()

    PYUSB_AVAILABLE = _backend is not None
    if not PYUSB_AVAILABLE:
        logger.warning("libusb1 backend not found — USB bulk mode unavailable")

except ImportError:
    PYUSB_AVAILABLE = False
    _backend = None
    logger.info("pyusb not installed — USB bulk mode unavailable")


def is_usb_available() -> bool:
    """Check if USB bulk transport is available."""
    return PYUSB_AVAILABLE


def scan_dji_usb_devices() -> list[dict]:
    """
    Scan for DJI USB devices.
    Returns list of dicts with device info and interface status.
    """
    if not PYUSB_AVAILABLE:
        return []

    results = []
    try:
        devices = usb.core.find(find_all=True, idVendor=DJI_VENDOR_ID, backend=_backend)
        for dev in devices:
            try:
                info = {
                    'vid': dev.idVendor,
                    'pid': dev.idProduct,
                    'vid_hex': f"{dev.idVendor:04X}",
                    'pid_hex': f"{dev.idProduct:04X}",
                    'serial': '',
                    'manufacturer': '',
                    'product': '',
                    'model_name': DJI_PRODUCT_IDS.get(dev.idProduct, f"Unknown (PID:{dev.idProduct:#06x})"),
                    'bus': dev.bus,
                    'address': dev.address,
                    'duml_interface': None,
                    'duml_claimable': False,
                    'needs_zadig': False,
                    'interfaces': [],
                }

                # Try to read string descriptors
                try:
                    info['serial'] = dev.serial_number or ''
                except Exception:
                    pass
                try:
                    info['manufacturer'] = dev.manufacturer or ''
                except Exception:
                    pass
                try:
                    info['product'] = dev.product or ''
                except Exception:
                    pass

                # Enumerate interfaces
                try:
                    cfg = dev[0]
                    for intf in cfg:
                        intf_info = {
                            'number': intf.bInterfaceNumber,
                            'class': intf.bInterfaceClass,
                            'subclass': intf.bInterfaceSubClass,
                            'protocol': intf.bInterfaceProtocol,
                            'is_duml': (intf.bInterfaceClass == DUML_INTERFACE_CLASS and
                                        intf.bInterfaceSubClass == DUML_INTERFACE_SUBCLASS),
                            'claimable': False,
                            'ep_out': None,
                            'ep_in': None,
                        }

                        # Find bulk endpoints
                        for ep in intf:
                            if ep.bmAttributes == 2:  # Bulk transfer
                                direction = usb.util.endpoint_direction(ep.bEndpointAddress)
                                if direction == usb.util.ENDPOINT_OUT:
                                    intf_info['ep_out'] = ep.bEndpointAddress
                                elif direction == usb.util.ENDPOINT_IN:
                                    intf_info['ep_in'] = ep.bEndpointAddress

                        # Check if DUML interface
                        if intf_info['is_duml']:
                            info['duml_interface'] = intf.bInterfaceNumber

                            # Test if we can claim it
                            try:
                                usb.util.claim_interface(dev, intf.bInterfaceNumber)
                                usb.util.release_interface(dev, intf.bInterfaceNumber)
                                intf_info['claimable'] = True
                                info['duml_claimable'] = True
                            except Exception:
                                info['needs_zadig'] = True

                        info['interfaces'].append(intf_info)
                except Exception as e:
                    logger.debug("Failed to enumerate interfaces: %s", e)

                results.append(info)

            except Exception as e:
                logger.debug("Failed to read device info: %s", e)

    except Exception as e:
        logger.error("USB scan error: %s", e)

    return results


class USBBulkTransport:
    """
    USB bulk transport for DUML communication with DJI smart controllers.
    Wraps pyusb to provide a serial-like read/write interface.
    """

    def __init__(self):
        self._dev = None
        self._ep_out = None
        self._ep_in = None
        self._intf_number = None
        self._claimed = False

    @property
    def is_open(self) -> bool:
        return self._dev is not None and self._claimed

    @property
    def port(self) -> str:
        if self._dev:
            pid = self._dev.idProduct
            name = DJI_PRODUCT_IDS.get(pid, f"PID:{pid:#06x}")
            return f"USB:{name}"
        return ""

    def open(self, vid: int = DJI_VENDOR_ID, pid: int = None) -> None:
        """
        Open connection to a DJI USB device.

        Args:
            vid: USB vendor ID (default DJI)
            pid: USB product ID (None = find first DJI device)

        Raises:
            ConnectionError: If device not found or can't be claimed
        """
        if not PYUSB_AVAILABLE:
            raise ConnectionError(
                "USB support not available. Install: pip install pyusb libusb"
            )

        # Find the device
        if pid is not None:
            self._dev = usb.core.find(idVendor=vid, idProduct=pid, backend=_backend)
        else:
            self._dev = usb.core.find(idVendor=vid, backend=_backend)

        if self._dev is None:
            raise ConnectionError(
                "DJI RC not found via USB. Make sure it's connected via USB-C."
            )

        # Find the DUML bulk interface
        cfg = self._dev[0]
        target_intf = None
        for intf in cfg:
            if (intf.bInterfaceClass == DUML_INTERFACE_CLASS and
                    intf.bInterfaceSubClass == DUML_INTERFACE_SUBCLASS):
                target_intf = intf
                break

        if target_intf is None:
            # Fallback: try any vendor-specific interface with bulk endpoints
            for intf in cfg:
                if intf.bInterfaceClass == DUML_INTERFACE_CLASS:
                    has_bulk_out = any(
                        ep.bmAttributes == 2 and
                        usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT
                        for ep in intf
                    )
                    has_bulk_in = any(
                        ep.bmAttributes == 2 and
                        usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN
                        for ep in intf
                    )
                    if has_bulk_out and has_bulk_in:
                        target_intf = intf
                        break

        if target_intf is None:
            raise ConnectionError("No DUML bulk interface found on this DJI device.")

        # Find bulk endpoints
        self._ep_out = usb.util.find_descriptor(
            target_intf,
            custom_match=lambda e: (
                e.bmAttributes == 2 and
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
            )
        )
        self._ep_in = usb.util.find_descriptor(
            target_intf,
            custom_match=lambda e: (
                e.bmAttributes == 2 and
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
            )
        )

        if self._ep_out is None or self._ep_in is None:
            raise ConnectionError("DUML interface missing bulk endpoints.")

        self._intf_number = target_intf.bInterfaceNumber

        # Try to detach kernel driver
        try:
            if self._dev.is_kernel_driver_active(self._intf_number):
                self._dev.detach_kernel_driver(self._intf_number)
        except Exception:
            pass

        # Claim the interface
        try:
            usb.util.claim_interface(self._dev, self._intf_number)
            self._claimed = True
        except usb.core.USBError as e:
            self._dev = None
            raise ConnectionError(
                f"Cannot claim USB interface {self._intf_number}. "
                f"You need to install the WinUSB driver using Zadig:\n"
                f"1. Download Zadig from https://zadig.akeo.ie/\n"
                f"2. Options → List All Devices\n"
                f"3. Select the interface named 'BULK Interface' or '1023_MI01'\n"
                f"4. Set target driver to 'WinUSB'\n"
                f"5. Click 'Replace Driver'\n"
                f"6. Unplug and replug the RC\n"
                f"\nOriginal error: {e}"
            ) from e
        except NotImplementedError as e:
            self._dev = None
            raise ConnectionError(
                f"Cannot claim USB interface — wrong driver installed. "
                f"Please install WinUSB driver using Zadig (https://zadig.akeo.ie/).\n"
                f"Select the DJI BULK interface and replace driver with WinUSB.\n"
                f"\nOriginal error: {e}"
            ) from e

        # Flush any pending data
        try:
            while True:
                self._ep_in.read(512, timeout=50)
        except Exception:
            pass

        logger.info(
            "USB bulk connected: VID=%04X PID=%04X intf=%d EP_OUT=%02X EP_IN=%02X",
            vid, self._dev.idProduct, self._intf_number,
            self._ep_out.bEndpointAddress, self._ep_in.bEndpointAddress
        )

    def close(self):
        """Release the USB interface and close the device."""
        if self._dev and self._claimed:
            try:
                usb.util.release_interface(self._dev, self._intf_number)
            except Exception:
                pass
            try:
                usb.util.dispose_resources(self._dev)
            except Exception:
                pass
        self._dev = None
        self._ep_out = None
        self._ep_in = None
        self._claimed = False

    def write(self, data: bytes) -> int:
        """Write data to the USB bulk OUT endpoint."""
        if not self.is_open:
            raise ConnectionError("USB device not open")
        try:
            return self._ep_out.write(data, timeout=1000)
        except usb.core.USBError as e:
            raise OSError(f"USB write error: {e}") from e

    def read(self, size: int = 512, timeout: int = 500) -> bytes | None:
        """
        Read data from the USB bulk IN endpoint.
        Returns bytes or None on timeout.
        """
        if not self.is_open:
            raise ConnectionError("USB device not open")
        try:
            data = self._ep_in.read(size, timeout=timeout)
            return bytes(data)
        except usb.core.USBTimeoutError:
            return None
        except usb.core.USBError as e:
            raise OSError(f"USB read error: {e}") from e
