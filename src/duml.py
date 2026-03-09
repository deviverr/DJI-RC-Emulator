"""
DUML (DJI Universal Messaging Language) protocol implementation.
Handles CRC calculation, packet construction, and response parsing
for communication with DJI RC controllers over USB serial.
"""
import struct

# CRC-16 lookup table used for packet body checksum (P3/P4/Mavic seed: 0x3692)
CRC16_TABLE = [
    0x0000, 0x1189, 0x2312, 0x329B, 0x4624, 0x57AD, 0x6536, 0x74BF,
    0x8C48, 0x9DC1, 0xAF5A, 0xBED3, 0xCA6C, 0xDBE5, 0xE97E, 0xF8F7,
    0x1081, 0x0108, 0x3393, 0x221A, 0x56A5, 0x472C, 0x75B7, 0x643E,
    0x9CC9, 0x8D40, 0xBFDB, 0xAE52, 0xDAED, 0xCB64, 0xF9FF, 0xE876,
    0x2102, 0x308B, 0x0210, 0x1399, 0x6726, 0x76AF, 0x4434, 0x55BD,
    0xAD4A, 0xBCC3, 0x8E58, 0x9FD1, 0xEB6E, 0xFAE7, 0xC87C, 0xD9F5,
    0x3183, 0x200A, 0x1291, 0x0318, 0x77A7, 0x662E, 0x54B5, 0x453C,
    0xBDCB, 0xAC42, 0x9ED9, 0x8F50, 0xFBEF, 0xEA66, 0xD8FD, 0xC974,
    0x4204, 0x538D, 0x6116, 0x709F, 0x0420, 0x15A9, 0x2732, 0x36BB,
    0xCE4C, 0xDFC5, 0xED5E, 0xFCD7, 0x8868, 0x99E1, 0xAB7A, 0xBAF3,
    0x5285, 0x430C, 0x7197, 0x601E, 0x14A1, 0x0528, 0x37B3, 0x263A,
    0xDECD, 0xCF44, 0xFDDF, 0xEC56, 0x98E9, 0x8960, 0xBBFB, 0xAA72,
    0x6306, 0x728F, 0x4014, 0x519D, 0x2522, 0x34AB, 0x0630, 0x17B9,
    0xEF4E, 0xFEC7, 0xCC5C, 0xDDD5, 0xA96A, 0xB8E3, 0x8A78, 0x9BF1,
    0x7387, 0x620E, 0x5095, 0x411C, 0x35A3, 0x242A, 0x16B1, 0x0738,
    0xFFCF, 0xEE46, 0xDCDD, 0xCD54, 0xB9EB, 0xA862, 0x9AF9, 0x8B70,
    0x8408, 0x9581, 0xA71A, 0xB693, 0xC22C, 0xD3A5, 0xE13E, 0xF0B7,
    0x0840, 0x19C9, 0x2B52, 0x3ADB, 0x4E64, 0x5FED, 0x6D76, 0x7CFF,
    0x9489, 0x8500, 0xB79B, 0xA612, 0xD2AD, 0xC324, 0xF1BF, 0xE036,
    0x18C1, 0x0948, 0x3BD3, 0x2A5A, 0x5EE5, 0x4F6C, 0x7DF7, 0x6C7E,
    0xA50A, 0xB483, 0x8618, 0x9791, 0xE32E, 0xF2A7, 0xC03C, 0xD1B5,
    0x2942, 0x38CB, 0x0A50, 0x1BD9, 0x6F66, 0x7EEF, 0x4C74, 0x5DFD,
    0xB58B, 0xA402, 0x9699, 0x8710, 0xF3AF, 0xE226, 0xD0BD, 0xC134,
    0x39C3, 0x284A, 0x1AD1, 0x0B58, 0x7FE7, 0x6E6E, 0x5CF5, 0x4D7C,
    0xC60C, 0xD785, 0xE51E, 0xF497, 0x8028, 0x91A1, 0xA33A, 0xB2B3,
    0x4A44, 0x5BCD, 0x6956, 0x78DF, 0x0C60, 0x1DE9, 0x2F72, 0x3EFB,
    0xD68D, 0xC704, 0xF59F, 0xE416, 0x90A9, 0x8120, 0xB3BB, 0xA232,
    0x5AC5, 0x4B4C, 0x79D7, 0x685E, 0x1CE1, 0x0D68, 0x3FF3, 0x2E7A,
    0xE70E, 0xF687, 0xC41C, 0xD595, 0xA12A, 0xB0A3, 0x8238, 0x93B1,
    0x6B46, 0x7ACF, 0x4854, 0x59DD, 0x2D62, 0x3CEB, 0x0E70, 0x1FF9,
    0xF78F, 0xE606, 0xD49D, 0xC514, 0xB1AB, 0xA022, 0x92B9, 0x8330,
    0x7BC7, 0x6A4E, 0x58D5, 0x495C, 0x3DE3, 0x2C6A, 0x1EF1, 0x0F78,
]

# CRC-8 lookup table used for packet header checksum (seed: 0x77)
CRC8_TABLE = [
    0x00, 0x5E, 0xBC, 0xE2, 0x61, 0x3F, 0xDD, 0x83,
    0xC2, 0x9C, 0x7E, 0x20, 0xA3, 0xFD, 0x1F, 0x41,
    0x9D, 0xC3, 0x21, 0x7F, 0xFC, 0xA2, 0x40, 0x1E,
    0x5F, 0x01, 0xE3, 0xBD, 0x3E, 0x60, 0x82, 0xDC,
    0x23, 0x7D, 0x9F, 0xC1, 0x42, 0x1C, 0xFE, 0xA0,
    0xE1, 0xBF, 0x5D, 0x03, 0x80, 0xDE, 0x3C, 0x62,
    0xBE, 0xE0, 0x02, 0x5C, 0xDF, 0x81, 0x63, 0x3D,
    0x7C, 0x22, 0xC0, 0x9E, 0x1D, 0x43, 0xA1, 0xFF,
    0x46, 0x18, 0xFA, 0xA4, 0x27, 0x79, 0x9B, 0xC5,
    0x84, 0xDA, 0x38, 0x66, 0xE5, 0xBB, 0x59, 0x07,
    0xDB, 0x85, 0x67, 0x39, 0xBA, 0xE4, 0x06, 0x58,
    0x19, 0x47, 0xA5, 0xFB, 0x78, 0x26, 0xC4, 0x9A,
    0x65, 0x3B, 0xD9, 0x87, 0x04, 0x5A, 0xB8, 0xE6,
    0xA7, 0xF9, 0x1B, 0x45, 0xC6, 0x98, 0x7A, 0x24,
    0xF8, 0xA6, 0x44, 0x1A, 0x99, 0xC7, 0x25, 0x7B,
    0x3A, 0x64, 0x86, 0xD8, 0x5B, 0x05, 0xE7, 0xB9,
    0x8C, 0xD2, 0x30, 0x6E, 0xED, 0xB3, 0x51, 0x0F,
    0x4E, 0x10, 0xF2, 0xAC, 0x2F, 0x71, 0x93, 0xCD,
    0x11, 0x4F, 0xAD, 0xF3, 0x70, 0x2E, 0xCC, 0x92,
    0xD3, 0x8D, 0x6F, 0x31, 0xB2, 0xEC, 0x0E, 0x50,
    0xAF, 0xF1, 0x13, 0x4D, 0xCE, 0x90, 0x72, 0x2C,
    0x6D, 0x33, 0xD1, 0x8F, 0x0C, 0x52, 0xB0, 0xEE,
    0x32, 0x6C, 0x8E, 0xD0, 0x53, 0x0D, 0xEF, 0xB1,
    0xF0, 0xAE, 0x4C, 0x12, 0x91, 0xCF, 0x2D, 0x73,
    0xCA, 0x94, 0x76, 0x28, 0xAB, 0xF5, 0x17, 0x49,
    0x08, 0x56, 0xB4, 0xEA, 0x69, 0x37, 0xD5, 0x8B,
    0x57, 0x09, 0xEB, 0xB5, 0x36, 0x68, 0x8A, 0xD4,
    0x95, 0xCB, 0x29, 0x77, 0xF4, 0xAA, 0x48, 0x16,
    0xE9, 0xB7, 0x55, 0x0B, 0x88, 0xD6, 0x34, 0x6A,
    0x2B, 0x75, 0x97, 0xC9, 0x4A, 0x14, 0xF6, 0xA8,
    0x74, 0x2A, 0xC8, 0x96, 0x15, 0x4B, 0xA9, 0xF7,
    0xB6, 0xE8, 0x0A, 0x54, 0xD7, 0x89, 0x6B, 0x35,
]

# DUML protocol constants
DUML_HEADER = 0x55
PROTOCOL_VERSION = 0x04  # Version nibble shifted into length MSB
CRC16_SEED = 0x3692      # P3/P4/Mavic family
CRC8_SEED = 0x77

# Command constants for DJI RC
SOURCE_APP = 0x0A
TARGET_RC = 0x06
CMD_TYPE_REQUEST = 0x40
CMD_SET_RC = 0x06
CMD_ID_READ_STICKS = 0x01
CMD_ID_ENABLE_SIM = 0x24

# Expected response lengths for stick data (varies by RC model)
STICK_RESPONSE_LENGTH = 38      # RC-N1 serial format
STICK_RESPONSE_LENGTH_32 = 32   # RM330 / RC 2 USB format
STICK_RESPONSE_LENGTHS = (38, 32)

# Stick data byte offsets within response packet
# 38-byte format (RC-N1 serial): channel data starts at byte 13, stride 3
OFFSET_RIGHT_H = (13, 15)
OFFSET_RIGHT_V = (16, 18)
OFFSET_LEFT_V = (19, 21)
OFFSET_LEFT_H = (22, 24)
OFFSET_CAMERA = (25, 27)

# 32-byte format (RM330/RC2 USB): channel data starts at byte 12, stride 3
OFFSET_RIGHT_H_32 = (12, 14)
OFFSET_RIGHT_V_32 = (15, 17)
OFFSET_LEFT_V_32 = (18, 20)
OFFSET_LEFT_H_32 = (21, 23)
OFFSET_CAMERA_32 = (24, 26)

# Raw stick value range
RAW_MIN = 364
RAW_CENTER = 1024
RAW_MAX = 1684


def calc_crc16(data: bytes, length: int) -> int:
    """Calculate CRC-16 checksum for DUML packet body."""
    crc = CRC16_SEED
    for i in range(length):
        crc = (crc >> 8) ^ CRC16_TABLE[(data[i] ^ crc) & 0xFF]
    return crc


def calc_crc8(data: bytes, length: int) -> int:
    """Calculate CRC-8 checksum for DUML packet header."""
    crc = CRC8_SEED
    for i in range(length):
        crc = CRC8_TABLE[(data[i] ^ crc) & 0xFF]
    return crc


def build_packet(source: int, target: int, cmd_type: int,
                 cmd_set: int, cmd_id: int, payload: bytes = b'',
                 sequence: int = 0x34EB) -> bytes:
    """
    Build a complete DUML packet with header, payload, and checksums.

    Args:
        source: Source address (e.g. 0x0A for app)
        target: Target address (e.g. 0x06 for RC)
        cmd_type: Command type byte (e.g. 0x40 for request)
        cmd_set: Command set byte (e.g. 0x06 for RC commands)
        cmd_id: Command ID byte
        payload: Optional payload bytes
        sequence: Packet sequence number

    Returns:
        Complete DUML packet as bytes, ready to send over serial.
    """
    # Header byte
    packet = bytearray([DUML_HEADER])

    # Length = 11 header/footer bytes + payload
    length = 13 + len(payload)
    if length > 0x3FF:
        raise ValueError(f"Packet too large: {length} bytes (max 1023)")

    # Length field: low byte + high byte with protocol version
    packet.append(length & 0xFF)
    packet.append((length >> 8) | PROTOCOL_VERSION)

    # Header CRC (over first 3 bytes)
    hdr_crc = calc_crc8(packet, 3)
    packet.append(hdr_crc)

    # Routing
    packet.append(source)
    packet.append(target)

    # Sequence number (little-endian 16-bit)
    packet.extend(struct.pack('<H', sequence))

    # Command
    packet.append(cmd_type)
    packet.append(cmd_set)
    packet.append(cmd_id)

    # Payload
    packet.extend(payload)

    # Body CRC-16 (over entire packet so far)
    crc = calc_crc16(packet, len(packet))
    packet.extend(struct.pack('<H', crc))

    return bytes(packet)


def build_enable_simulator() -> bytes:
    """Build packet to enable simulator mode on the RC (fast stick updates)."""
    return build_packet(SOURCE_APP, TARGET_RC, CMD_TYPE_REQUEST,
                        CMD_SET_RC, CMD_ID_ENABLE_SIM, b'\x01')


def build_read_sticks() -> bytes:
    """Build packet to request current stick/button values from RC."""
    return build_packet(SOURCE_APP, TARGET_RC, CMD_TYPE_REQUEST,
                        CMD_SET_RC, CMD_ID_READ_STICKS, b'')


def read_packet(serial_port) -> bytes | None:
    """
    Read a single DUML packet from the serial port.

    Scans for the 0x55 start byte, reads the length field,
    then reads the remaining packet body.

    Args:
        serial_port: Open pyserial Serial object.

    Returns:
        Complete packet as bytes, or None if no valid packet found.
    """
    # Scan for start byte
    b = serial_port.read(1)
    if not b or b[0] != DUML_HEADER:
        return None

    buffer = bytearray(b)

    # Read length field (2 bytes)
    length_bytes = serial_port.read(2)
    if len(length_bytes) < 2:
        return None
    buffer.extend(length_bytes)

    # Parse packet length from length field
    raw_length = struct.unpack('<H', length_bytes)[0]
    packet_length = raw_length & 0x03FF  # Lower 10 bits = length

    # Read header CRC + remaining packet body
    remaining = packet_length - 3  # Already read 3 bytes (header + 2 length bytes)
    if remaining <= 0 or remaining > 1024:
        return None

    rest = serial_port.read(remaining)
    if len(rest) < remaining:
        return None
    buffer.extend(rest)

    return bytes(buffer)


def extract_packet_from_bytes(data: bytes) -> bytes | None:
    """
    Extract the first valid DUML packet from raw bytes (for USB bulk mode).
    Scans for 0x55 header, reads length field, returns complete packet.
    """
    for i in range(len(data)):
        if data[i] != DUML_HEADER:
            continue
        if i + 3 > len(data):
            break
        raw_length = struct.unpack('<H', data[i + 1:i + 3])[0]
        packet_length = raw_length & 0x03FF
        if packet_length < 4 or packet_length > 1024:
            continue
        if i + packet_length <= len(data):
            return bytes(data[i:i + packet_length])
    return None


def extract_all_packets_from_bytes(data: bytes) -> list[bytes]:
    """
    Extract all valid DUML packets from raw bytes (for USB bulk mode).
    USB bulk reads can contain multiple concatenated packets.
    """
    packets = []
    i = 0
    while i < len(data):
        if data[i] != DUML_HEADER:
            i += 1
            continue
        if i + 3 > len(data):
            break
        raw_length = struct.unpack('<H', data[i + 1:i + 3])[0]
        packet_length = raw_length & 0x03FF
        if packet_length < 4 or packet_length > 1024:
            i += 1
            continue
        if i + packet_length <= len(data):
            packets.append(bytes(data[i:i + packet_length]))
            i += packet_length
        else:
            break
    return packets


def parse_stick_data(packet: bytes, format_override: str | None = None) -> dict | None:
    """
    Parse stick, camera, scroll, and button values from an RC response packet.

    Supports both 38-byte (RC-N1 serial) and 32-byte (RM330/RC2 USB) formats.
    Channel data uses a 3-byte stride (value_LE16 + tag); the base offset
    differs by format.

    Args:
        packet: Raw DUML response packet (38 or 32 bytes).
        format_override: Force a specific format ("38-byte" or "32-byte")
                         instead of auto-detecting from packet length.

    Returns:
        Dict with raw stick values and button states.
        Returns None if packet format is unrecognised.
    """
    plen = len(packet)
    if format_override == "38-byte":
        if plen < 30:
            return None
        base = 13
        btn_byte = packet[12] if plen > 12 else 0
    elif format_override == "32-byte":
        if plen < 26:
            return None
        base = 12
        btn_byte = packet[11] if plen > 11 else 0
    elif plen == STICK_RESPONSE_LENGTH:
        base = 13  # 38-byte: channel data starts at byte 13
        btn_byte = packet[12] if plen > 12 else 0
    elif plen == STICK_RESPONSE_LENGTH_32:
        base = 12  # 32-byte: channel data starts at byte 12
        btn_byte = packet[11] if plen > 11 else 0
    else:
        return None

    def extract(offset: int) -> int:
        return int.from_bytes(packet[offset:offset + 2], byteorder='little')

    result = {
        'right_h': extract(base),
        'right_v': extract(base + 3),
        'left_v':  extract(base + 6),
        'left_h':  extract(base + 9),
        'camera':  extract(base + 12),
    }

    # 6th channel (scroll wheel / spare axis) — present in 32-byte format
    if base + 15 + 2 <= plen - 2:  # -2 for CRC16 footer
        result['scroll'] = extract(base + 15)
    else:
        result['scroll'] = RAW_CENTER

    # Button bitmask byte (before channel data)
    # Known bit assignments for RM330/RC2:
    #   bit 0 = C1 button
    #   bit 1 = C2 button
    #   bit 2 = Photo/shutter button
    #   bit 3 = Video/record button
    #   bit 4 = Pause/fn button
    result['btn_raw'] = btn_byte
    result['c1'] = bool(btn_byte & 0x01)
    result['c2'] = bool(btn_byte & 0x02)
    result['photo'] = bool(btn_byte & 0x04)
    result['video'] = bool(btn_byte & 0x08)
    result['fn'] = bool(btn_byte & 0x10)

    return result
