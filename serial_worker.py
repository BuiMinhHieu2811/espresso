"""
Serial Worker Module
====================
QThread-based worker for continuous serial port read/write.
Runs in background, emits signals when data is received or errors occur.
"""

import serial
import serial.tools.list_ports
from PyQt5.QtCore import QThread, pyqtSignal, QMutex

from packet_protocol import PacketParser


def get_available_ports() -> list:
    """Return list of available COM port names."""
    ports = serial.tools.list_ports.comports()
    return [p.device for p in sorted(ports)]


class SerialWorker(QThread):
    """
    Background thread for serial communication.

    Signals:
        packet_received(bytes): Emitted when a complete packet is received.
        raw_data_received(bytes): Emitted for every chunk of raw bytes received (for logging).
        data_sent(bytes): Emitted after data is successfully sent.
        error_occurred(str): Emitted on serial errors.
        connection_changed(bool): Emitted when connection state changes.
    """

    packet_received = pyqtSignal(bytes)
    raw_data_received = pyqtSignal(bytes)
    data_sent = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._serial = None
        self._running = False
        self._mutex = QMutex()
        self._parser = PacketParser()

    def configure(self, port: str, baudrate: int = 115200,
                  bytesize: int = serial.EIGHTBITS,
                  stopbits: float = serial.STOPBITS_ONE,
                  parity: str = serial.PARITY_NONE,
                  timeout: float = 0.1):
        """Configure serial port parameters before connecting."""
        self._port = port
        self._baudrate = baudrate
        self._bytesize = bytesize
        self._stopbits = stopbits
        self._parity = parity
        self._timeout = timeout

    def connect_port(self) -> bool:
        """Open the serial port. Returns True on success."""
        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                bytesize=self._bytesize,
                stopbits=self._stopbits,
                parity=self._parity,
                timeout=self._timeout,
            )
            self._parser.reset()
            self.connection_changed.emit(True)
            return True
        except serial.SerialException as e:
            self.error_occurred.emit(f"Connection failed: {e}")
            self.connection_changed.emit(False)
            return False

    def disconnect_port(self):
        """Close the serial port."""
        self._running = False
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
        self._parser.reset()
        self.connection_changed.emit(False)

    def is_connected(self) -> bool:
        """Check if serial port is open."""
        return self._serial is not None and self._serial.is_open

    def send(self, data: bytes):
        """Send data through serial port (thread-safe)."""
        self._mutex.lock()
        try:
            if not self.is_connected():
                self.error_occurred.emit("Not connected")
                return
            try:
                self._serial.write(data)
                self.data_sent.emit(data)
            except serial.SerialException as e:
                self.error_occurred.emit(f"Send failed: {e}")
        finally:
            self._mutex.unlock()

    def run(self):
        """Main loop: continuously read from serial port."""
        self._running = True
        while self._running:
            if not self.is_connected():
                self.msleep(100)
                continue

            self._mutex.lock()
            try:
                if not self.is_connected():
                    continue
                if self._serial.in_waiting > 0:
                    raw = self._serial.read(self._serial.in_waiting)
                    if raw:
                        self.raw_data_received.emit(raw)
                        packets = self._parser.feed(raw)
                        for pkt in packets:
                            self.packet_received.emit(pkt)
            except serial.SerialException as e:
                self.error_occurred.emit(f"Read error: {e}")
                self._mutex.unlock()
                self.disconnect_port()
                break
            except Exception as e:
                self.error_occurred.emit(f"Unexpected error: {e}")
            finally:
                self._mutex.unlock()

            self.msleep(10)  # Avoid busy-wait

    def stop(self):
        """Stop the worker thread and close port."""
        self._running = False
        self.disconnect_port()
        self.wait(2000)
