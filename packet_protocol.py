"""
Packet Protocol Module
======================
Handles encoding/decoding of UART packets for MCU communication.

Packet Format:
    [HEADER] [LENGTH] [CMD] [DATA_0] ... [DATA_N] [CRC]

- HEADER: 0xFF (fixed start byte)
- LENGTH: Total bytes from CMD to last DATA byte (excluding HEADER, LENGTH, CRC)
- CMD:    Command byte
- DATA:   Payload bytes (variable length, depends on command)
- CRC:    XOR checksum of all bytes from LENGTH to last DATA byte
"""


# --- Header byte ---
HEADER_BYTE = 0xFF

# --- Command definitions ---
CMD_LIGHT_ON        = 0x01  # Bật đèn
CMD_LIGHT_OFF       = 0x02  # Tắt đèn
CMD_LIGHT_STATUS    = 0x03  # MCU phản hồi trạng thái đèn

CMD_SET_WATER_LEVEL = 0x04  # Gửi mức nước cho MCU
CMD_WATER_LEVEL_ACK = 0x05  # MCU phản hồi mức nước

CMD_SET_TEMPERATURE = 0x06  # Gửi nhiệt độ cho MCU
CMD_TEMPERATURE_ACK = 0x07  # MCU phản hồi nhiệt độ

CMD_STATUS_REPORT   = 0x08  # MCU gửi báo cáo trạng thái tổng hợp

# --- Command name lookup ---
CMD_NAMES = {
    CMD_LIGHT_ON:        "CMD_LIGHT_ON",
    CMD_LIGHT_OFF:       "CMD_LIGHT_OFF",
    CMD_LIGHT_STATUS:    "CMD_LIGHT_STATUS",
    CMD_SET_WATER_LEVEL: "CMD_SET_WATER_LEVEL",
    CMD_WATER_LEVEL_ACK: "CMD_WATER_LEVEL_ACK",
    CMD_SET_TEMPERATURE: "CMD_SET_TEMPERATURE",
    CMD_TEMPERATURE_ACK: "CMD_TEMPERATURE_ACK",
    CMD_STATUS_REPORT:   "CMD_STATUS_REPORT",
}

# --- Status values ---
STATUS_OK   = 0x01
STATUS_FAIL = 0x00


def calculate_crc(data: bytes) -> int:
    """
    Calculate CRC using XOR of all bytes.
    Can be replaced with a more robust algorithm later.
    """
    crc = 0x00
    for b in data:
        crc ^= b
    return crc & 0xFF


def encode_packet(cmd: int, data: bytes = b'') -> bytes:
    """
    Encode a command and data into a packet.

    Args:
        cmd: Command byte
        data: Payload bytes

    Returns:
        Complete packet as bytes
    """
    length = 1 + len(data)  # CMD byte + DATA bytes
    payload = bytes([length, cmd]) + data
    crc = calculate_crc(payload)
    return bytes([HEADER_BYTE]) + payload + bytes([crc])


def decode_packet(raw: bytes) -> dict:
    """
    Decode raw bytes into a packet dictionary.

    Args:
        raw: Raw bytes received from serial

    Returns:
        dict with keys: 'valid', 'cmd', 'data', 'raw'
        'valid' is False if packet is malformed or CRC mismatch.
    """
    result = {
        'valid': False,
        'cmd': None,
        'data': b'',
        'raw': raw,
    }

    if len(raw) < 4:  # Minimum: HEADER + LENGTH + CMD + CRC
        return result

    if raw[0] != HEADER_BYTE:
        return result

    length = raw[1]
    expected_total = 1 + 1 + length + 1  # HEADER + LENGTH + payload + CRC

    if len(raw) < expected_total:
        return result

    payload = raw[2:2 + length]     # CMD + DATA
    crc_received = raw[2 + length]
    crc_calculated = calculate_crc(raw[1:2 + length])  # LENGTH + CMD + DATA

    if crc_received != crc_calculated:
        return result

    result['valid'] = True
    result['cmd'] = payload[0]
    result['data'] = payload[1:] if len(payload) > 1 else b''
    return result


class PacketParser:
    """
    Stateful parser that accumulates incoming bytes and extracts
    complete packets from a stream.
    """

    def __init__(self):
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list:
        """
        Feed raw bytes into the parser.

        Returns:
            List of complete raw packet bytes found in the stream.
        """
        self._buffer.extend(data)
        packets = []

        while True:
            # Find header byte
            header_idx = -1
            for i in range(len(self._buffer)):
                if self._buffer[i] == HEADER_BYTE:
                    header_idx = i
                    break

            if header_idx == -1:
                self._buffer.clear()
                break

            # Discard bytes before header
            if header_idx > 0:
                self._buffer = self._buffer[header_idx:]

            # Need at least HEADER + LENGTH
            if len(self._buffer) < 2:
                break

            length = self._buffer[1]
            total_len = 1 + 1 + length + 1  # HEADER + LENGTH + payload + CRC

            if length == 0 or total_len > 256:
                # Invalid length, skip this header byte
                self._buffer = self._buffer[1:]
                continue

            # Wait for complete packet
            if len(self._buffer) < total_len:
                break

            # Extract packet
            packet_bytes = bytes(self._buffer[:total_len])
            self._buffer = self._buffer[total_len:]
            packets.append(packet_bytes)

        return packets

    def reset(self):
        """Clear the internal buffer."""
        self._buffer.clear()
