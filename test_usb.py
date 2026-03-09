"""Test USB bulk communication with DJI RC RM330."""
import usb.core
import usb.util
import usb.backend.libusb1
import time
import sys
import os

# Try to find libusb-1.0.dll from the libusb package
try:
    import libusb
    dll_path = os.path.join(os.path.dirname(libusb.__file__), '_platform', 'windows', 'x86_64', 'libusb-1.0.dll')
    if os.path.exists(dll_path):
        backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
        print(f"Using libusb1 backend: {dll_path}")
    else:
        backend = None
        print(f"libusb1 dll not found at {dll_path}, trying default")
except ImportError:
    backend = None
    print("libusb package not installed, trying system default")

sys.path.insert(0, '.')
from src.duml import build_enable_simulator, build_read_sticks

dev = usb.core.find(idVendor=0x2CA3, idProduct=0x1023, backend=backend)
if dev is None:
    print("DJI RC not found via USB")
    # Also try without backend
    dev = usb.core.find(idVendor=0x2CA3, idProduct=0x1023)
    if dev is None:
        print("Still not found with default backend either")
        sys.exit(1)
    print("Found with default (libusb0) backend")

print(f"Found: {dev.manufacturer} - {dev.product} (S/N: {dev.serial_number})")
print(f"Backend: {dev._ctx.backend.__class__.__module__}")

# List all interfaces
cfg = dev[0]
print(f"\nConfiguration: {cfg.bNumInterfaces} interfaces")
for intf in cfg:
    print(f"  Interface {intf.bInterfaceNumber}: class={hex(intf.bInterfaceClass)} sub={hex(intf.bInterfaceSubClass)} proto={hex(intf.bInterfaceProtocol)}")
    for ep in intf:
        d = "IN" if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN else "OUT"
        print(f"    EP {hex(ep.bEndpointAddress)} ({d}): {ep.bmAttributes} max={ep.wMaxPacketSize}")

# Use the vendor-specific bulk interface
intf = None
for i in cfg:
    if i.bInterfaceClass == 0xFF and i.bInterfaceSubClass == 0x43:
        intf = i
        break
if intf is None:
    # Fallback to first interface with bulk endpoints
    intf = cfg.interfaces()[0]
    
print(f"\nUsing interface {intf.bInterfaceNumber}")

ep_out = usb.util.find_descriptor(
    intf,
    custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
)
ep_in = usb.util.find_descriptor(
    intf,
    custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
)

print(f"EP OUT={hex(ep_out.bEndpointAddress)}, EP IN={hex(ep_in.bEndpointAddress)}")

# Try to set auto-detach kernel driver (libusb1 feature)
try:
    dev._ctx.backend.lib.libusb_set_auto_detach_kernel_driver(
        dev._ctx.backend.lib.libusb_open(dev.bus, dev.address) if hasattr(dev._ctx, 'handle') else None,
        1
    )
    print("Set auto-detach kernel driver")
except Exception as e:
    print(f"Auto-detach note: {e}")

# Claim the interface
try:
    if dev.is_kernel_driver_active(intf.bInterfaceNumber):
        dev.detach_kernel_driver(intf.bInterfaceNumber)
        print("Detached kernel driver")
except Exception as e:
    print(f"Kernel driver note: {e}")

claimed = False
try:
    usb.util.claim_interface(dev, intf.bInterfaceNumber)
    print("Interface claimed OK")
    claimed = True
except Exception as e:
    print(f"Claim failed: {e}")
    print()
    print("Trying alternative: raw device write via dev.write()...")
    try:
        # Try writing directly to the endpoint address
        written = dev.write(ep_out.bEndpointAddress, build_enable_simulator(), timeout=1000)
        print(f"Direct write succeeded: {written} bytes")
        claimed = True  # works without claim
    except Exception as e2:
        print(f"Direct write also failed: {e2}")
        print()
        # Try all interfaces
        for test_intf in cfg:
            if test_intf.bInterfaceNumber == intf.bInterfaceNumber:
                continue
            print(f"Trying interface {test_intf.bInterfaceNumber}...")
            try:
                usb.util.claim_interface(dev, test_intf.bInterfaceNumber)
                print(f"  Claimed interface {test_intf.bInterfaceNumber} OK!")
                test_ep_out = usb.util.find_descriptor(
                    test_intf,
                    custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
                )
                test_ep_in = usb.util.find_descriptor(
                    test_intf,
                    custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN and e.bmAttributes == 2
                )
                if test_ep_out and test_ep_in:
                    print(f"  Has bulk endpoints: OUT={hex(test_ep_out.bEndpointAddress)}, IN={hex(test_ep_in.bEndpointAddress)}")
                    ep_out = test_ep_out
                    ep_in = test_ep_in
                    intf = test_intf
                    claimed = True
                    break
                else:
                    print(f"  No suitable bulk endpoints")
                    usb.util.release_interface(dev, test_intf.bInterfaceNumber)
            except Exception as e3:
                print(f"  Interface {test_intf.bInterfaceNumber} also failed: {e3}")

if not claimed:
    print()
    print("=" * 60)
    print("DRIVER FIX NEEDED")
    print("=" * 60)
    print()
    print("The DJI RC's USB interface needs the WinUSB driver.")
    print("Please install it using Zadig:")
    print("  1. Download Zadig from https://zadig.akeo.ie/")
    print("  2. Run Zadig")
    print("  3. Options -> List All Devices")
    print("  4. Select '1023_MI01' or 'BULK Interface (Interface 1)'")
    print("  5. Set target driver to 'WinUSB'")
    print("  6. Click 'Replace Driver'")
    print("  7. Unplug and replug the RC, then try again")
    sys.exit(1)

# Flush any pending data
try:
    while True:
        ep_in.read(512, timeout=100)
except usb.core.USBTimeoutError:
    pass

# Enable simulator mode
sim_pkt = build_enable_simulator()
print(f"\nSending enable sim ({len(sim_pkt)} bytes): {' '.join(f'{b:02x}' for b in sim_pkt)}")
ep_out.write(sim_pkt)
time.sleep(0.1)

try:
    resp = bytes(ep_in.read(512, timeout=1000))
    print(f"Sim response ({len(resp)} bytes): {' '.join(f'{b:02x}' for b in resp)}")
except usb.core.USBTimeoutError:
    print("No sim response (timeout)")

# Read sticks
print("\nReading sticks...")
for i in range(10):
    stick_pkt = build_read_sticks()
    ep_out.write(stick_pkt)
    try:
        resp = bytes(ep_in.read(512, timeout=1000))
        print(f"  Read {i} ({len(resp):2d} bytes): {' '.join(f'{b:02x}' for b in resp)}")
    except usb.core.USBTimeoutError:
        print(f"  Read {i}: timeout")
    time.sleep(0.05)

usb.util.release_interface(dev, intf.bInterfaceNumber)
print("\nDone — interface released")
