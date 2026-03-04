"""
Main Window Module
==================
PyQt5 main window with connection panel, control panel, and hex message log.
"""

import os
from datetime import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QPushButton, QComboBox, QLabel, QTextEdit,
    QSpinBox, QSlider, QStatusBar, QSplitter, QFrame,
    QSizePolicy, QMessageBox, QLineEdit
)
from PyQt5.QtCore import Qt, pyqtSlot, QTimer
from PyQt5.QtGui import QFont, QColor, QTextCursor, QIcon

from serial_worker import SerialWorker, get_available_ports
from packet_protocol import (
    encode_packet, decode_packet,
    CMD_LIGHT_ON, CMD_LIGHT_OFF, CMD_LIGHT_STATUS,
    CMD_SET_WATER_LEVEL, CMD_WATER_LEVEL_ACK,
    CMD_SET_TEMPERATURE, CMD_TEMPERATURE_ACK,
    CMD_STATUS_REPORT, STATUS_OK, CMD_NAMES
)


class IndicatorDot(QWidget):
    """A circular indicator that changes color to show status."""

    def __init__(self, size=16, parent=None):
        super().__init__(parent)
        self._size = size
        self._color = QColor("#555555")  # Inactive gray
        self.setFixedSize(size, size)

    def set_active(self, active: bool):
        """Set the indicator to active (green) or inactive (gray)."""
        self._color = QColor("#00e676") if active else QColor("#555555")
        self.update()

    def set_color(self, color: str):
        """Set a custom color."""
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QBrush
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(self._color))
        painter.setPen(Qt.NoPen)
        margin = 2
        painter.drawEllipse(margin, margin,
                            self._size - 2 * margin,
                            self._size - 2 * margin)
        painter.end()


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("☕ Coffee Machine - UART Controller")
        self.setMinimumSize(750, 650)
        self.resize(850, 700)

        # Serial worker
        self._worker = SerialWorker()
        self._worker.packet_received.connect(self._on_packet_received)
        self._worker.data_sent.connect(self._on_data_sent)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.connection_changed.connect(self._on_connection_changed)

        # State
        self._connected = False

        # Build UI
        self._build_ui()

        # Status bar
        self.statusBar().showMessage("Disconnected")

        # Refresh ports periodically
        self._port_timer = QTimer(self)
        self._port_timer.timeout.connect(self._refresh_ports)
        self._port_timer.start(3000)
        self._refresh_ports()

    def _build_ui(self):
        """Build the complete UI layout."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 12, 16, 12)

        # Title
        title = QLabel("☕ Coffee Machine Controller")
        title.setObjectName("lbl_title")
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # ---- Connection Panel ----
        conn_group = QGroupBox("🔌 Connection")
        conn_layout = QHBoxLayout(conn_group)
        conn_layout.setSpacing(10)

        conn_layout.addWidget(QLabel("Port:"))
        self.combo_port = QComboBox()
        self.combo_port.setMinimumWidth(100)
        conn_layout.addWidget(self.combo_port)

        conn_layout.addWidget(QLabel("Baud:"))
        self.combo_baud = QComboBox()
        self.combo_baud.addItems(["4800", "9600", "19200", "38400", "57600", "115200"])
        self.combo_baud.setCurrentText("115200")
        conn_layout.addWidget(self.combo_baud)

        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.clicked.connect(self._refresh_ports)
        conn_layout.addWidget(self.btn_refresh)

        conn_layout.addStretch()

        self.indicator_conn = IndicatorDot(18)
        conn_layout.addWidget(self.indicator_conn)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setObjectName("btn_connect")
        self.btn_connect.clicked.connect(self._on_connect)
        conn_layout.addWidget(self.btn_connect)

        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.setObjectName("btn_disconnect")
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.clicked.connect(self._on_disconnect)
        conn_layout.addWidget(self.btn_disconnect)

        main_layout.addWidget(conn_group)

        # ---- Control Panel ----
        ctrl_group = QGroupBox("🎛️ Command Sender")
        ctrl_layout = QVBoxLayout(ctrl_group)
        ctrl_layout.setSpacing(12)

        self._cmd_combos = []
        self._cmd_inputs = []

        # Create 3 identical command rows
        for i in range(3):
            row_layout = QHBoxLayout()
            
            # Command selector
            combo = QComboBox()
            # Populate with commands from CMD_NAMES
            for cmd_val, cmd_name in CMD_NAMES.items():
                combo.addItem(f"{cmd_name} (0x{cmd_val:02X})", cmd_val)
            combo.setMinimumWidth(220)
            self._cmd_combos.append(combo)
            row_layout.addWidget(combo)

            # Optional Data Input
            row_layout.addWidget(QLabel("Data (Hex):"))
            data_input = QLineEdit()
            data_input.setPlaceholderText("e.g. 0A 1B 2C")
            self._cmd_inputs.append(data_input)
            row_layout.addWidget(data_input)

            # Send Button
            btn_send = QPushButton("📤 Send")
            # Connect the button click to a lambda that captures the row index 'i'
            btn_send.clicked.connect(lambda checked, idx=i: self._on_send_dynamic(idx))
            row_layout.addWidget(btn_send)

            ctrl_layout.addLayout(row_layout)

        main_layout.addWidget(ctrl_group)

        # ---- Hex Message Log ----
        log_group = QGroupBox("📋 Hex Message Log")
        log_layout = QVBoxLayout(log_group)

        self.hex_log = QTextEdit()
        self.hex_log.setObjectName("hex_log")
        self.hex_log.setReadOnly(True)
        self.hex_log.setMinimumHeight(150)
        log_layout.addWidget(self.hex_log)

        log_btn_layout = QHBoxLayout()
        log_btn_layout.addStretch()
        self.btn_clear_log = QPushButton("🗑️ Clear Log")
        self.btn_clear_log.clicked.connect(self.hex_log.clear)
        log_btn_layout.addWidget(self.btn_clear_log)
        log_layout.addLayout(log_btn_layout)

        main_layout.addWidget(log_group, stretch=1)

    # ---- Port management ----

    def _refresh_ports(self):
        """Refresh the list of available COM ports."""
        current = self.combo_port.currentText()
        self.combo_port.clear()
        ports = get_available_ports()
        self.combo_port.addItems(ports)
        if current in ports:
            self.combo_port.setCurrentText(current)

    # ---- Connection handlers ----

    @pyqtSlot()
    def _on_connect(self):
        port = self.combo_port.currentText()
        if not port:
            self._log_message("ERROR", "No COM port selected")
            return
        baud = int(self.combo_baud.currentText())
        self._worker.configure(port, baudrate=baud)
        if self._worker.connect_port():
            self._worker.start()
            self._log_message("SYS", f"Connected to {port} @ {baud} baud")

    @pyqtSlot()
    def _on_disconnect(self):
        self._worker.stop()
        self._log_message("SYS", "Disconnected")

    @pyqtSlot(bool)
    def _on_connection_changed(self, connected: bool):
        self._connected = connected
        self.indicator_conn.set_active(connected)
        self.btn_connect.setEnabled(not connected)
        self.btn_disconnect.setEnabled(connected)
        self.combo_port.setEnabled(not connected)
        self.combo_baud.setEnabled(not connected)

        if connected:
            self.statusBar().showMessage("✅ Connected")
        else:
            self.statusBar().showMessage("❌ Disconnected")

    # ---- Control handlers ----

    @pyqtSlot(int)
    def _on_send_dynamic(self, row_idx: int):
        if not self._connected:
            self._log_message("ERROR", "Not connected to any port")
            return

        combo = self._cmd_combos[row_idx]
        data_input = self._cmd_inputs[row_idx]
        
        cmd_val = combo.currentData()
        
        # Parse hex data string
        hex_text = data_input.text().strip().replace(" ", "")
        data_bytes = bytearray()
        
        if len(hex_text) % 2 != 0:
            QMessageBox.warning(self, "Invalid Data", "Hex data must have an even number of characters.")
            return

        try:
            if hex_text:
                data_bytes = bytearray.fromhex(hex_text)
        except ValueError:
            QMessageBox.warning(self, "Invalid Data", "Invalid hex string. Use only 0-9 and A-F.")
            return

        pkt = encode_packet(cmd_val, data_bytes)
        self._send_packet(pkt)

    # ---- Send / Receive ----

    def _send_packet(self, packet: bytes):
        if not self._connected:
            self._log_message("ERROR", "Not connected to any port")
            return
        self._worker.send(packet)

    def _get_packet_description(self, raw: bytes) -> str:
        """Decode a packet and return a description string like (CMD_LIGHT_ON)."""
        parsed = decode_packet(raw)
        if parsed['valid']:
            cmd_name = CMD_NAMES.get(parsed['cmd'], f'CMD_0x{parsed["cmd"]:02X}')
            return cmd_name
        return "INVALID_FRAME"

    @pyqtSlot(bytes)
    def _on_data_sent(self, data: bytes):
        hex_str = ' '.join(f'{b:02X}' for b in data)
        desc = self._get_packet_description(data)
        self._log_message("TX", hex_str, desc)

    @pyqtSlot(bytes)
    def _on_packet_received(self, raw: bytes):
        hex_str = ' '.join(f'{b:02X}' for b in raw)
        desc = self._get_packet_description(raw)
        self._log_message("RX", hex_str, desc)

        parsed = decode_packet(raw)
        if not parsed['valid']:
            return

        cmd = parsed['cmd']
        data = parsed['data']

        if cmd == CMD_STATUS_REPORT:
            self._log_message("SYS", "Status report received from MCU")

    @pyqtSlot(str)
    def _on_error(self, msg: str):
        self._log_message("ERROR", msg)

    # ---- Logging ----

    def _log_message(self, direction: str, message: str, description: str = ""):
        """Append a message to the hex log with timestamp, direction, and optional description."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        color_map = {
            "TX":    "#ff9800",   # Orange
            "RX":    "#00e676",   # Green
            "SYS":   "#6c63ff",   # Purple
            "ERROR": "#ff5252",   # Red
            "WARN":  "#ffeb3b",   # Yellow
        }
        color = color_map.get(direction, "#a8b2d1")

        arrow = ">>" if direction == "TX" else "<<" if direction == "RX" else "::"

        # Build description suffix
        desc_html = ""
        if description:
            desc_color = "#ff5252" if description == "INVALID_FRAME" else "#666"
            desc_html = f' <span style="color: {desc_color}; font-style: italic;">({description})</span>'

        html = (
            f'<span style="color: #666;">[{timestamp}]</span> '
            f'<span style="color: {color}; font-weight: bold;">{direction} {arrow}</span> '
            f'<span style="color: #e0e0e0;">{message}</span>'
            f'{desc_html}'
        )

        self.hex_log.append(html)

        # Auto-scroll to bottom
        cursor = self.hex_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.hex_log.setTextCursor(cursor)

    # ---- Cleanup ----

    def closeEvent(self, event):
        """Ensure serial worker is stopped on window close."""
        self._worker.stop()
        event.accept()
