# Importy standardowe i biblioteki GUI + grafiki
import sys
import serial
import struct
from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg
import serial.tools.list_ports

class BinaryOscilloscope(QtWidgets.QMainWindow):
    def __init__(self, port='COM5', baudrate=2000000, samples=800):
        super().__init__()
        self.setWindowTitle("Oscyloskop ESP32 - Binarny")
        self.resize(1200, 600)

        self.samples = samples           # Liczba próbek w jednej ramce (800 * 64)
        self.buffer = bytearray()       # Bufor do odbioru danych binarnych
        self.paused = False             # Flaga pauzy wykresu
        self.trigger_enabled = False    # Flaga triggera
        self.voltage_range = 3.3        # Początkowy zakres napięcia (0–3.3V)

        # === UI: Pasek informacyjny ===
        self.voltage_label = QtWidgets.QLabel("Napięcie: --- V")
        self.min_label = QtWidgets.QLabel("Min: --- V")
        self.max_label = QtWidgets.QLabel("Max: --- V")
        self.freq_label = QtWidgets.QLabel("Częstotliwość: --- Hz")

        self.voltage_range_combo = QtWidgets.QComboBox()
        self.voltage_range_combo.addItems(["0–3.3V", "0–6.6V", "0–16.5V", "0–33V"])
        self.voltage_range_combo.currentIndexChanged.connect(self.update_voltage_range)

        # Layout paska informacyjnego
        self.info_bar = QtWidgets.QHBoxLayout()
        for label in [self.voltage_label, self.min_label, self.max_label, self.freq_label]:
            label.setStyleSheet("padding: 4px; font-weight: bold")
            self.info_bar.addWidget(label)

        self.info_bar.addWidget(QtWidgets.QLabel("Zakres:"))
        self.info_bar.addWidget(self.voltage_range_combo)
        self.info_bar.addStretch()

        # === Wykres ===
        self.plot_widget = pg.PlotWidget()
        self.curve = self.plot_widget.plot(pen='y')
        self.plot_widget.setBackground('k')
        self.plot_widget.setYRange(0, self.voltage_range)
        self.plot_widget.setLabel('left', 'Napięcie', units='V')
        self.plot_widget.setLabel('bottom', 'Czas', units='ms')

        # === Panel sterowania ===
        self.pause_button = QtWidgets.QPushButton("⏸ Zatrzymaj")
        self.resume_button = QtWidgets.QPushButton("▶ Wznów")
        self.center_button = QtWidgets.QPushButton("🎯 Wyśrodkuj")
        self.trigger_button = QtWidgets.QPushButton("⚡ Trigger")

        # === Layouty główne ===
        main_layout = QtWidgets.QVBoxLayout()
        content_layout = QtWidgets.QHBoxLayout()
        sidebar = QtWidgets.QVBoxLayout()

        # Ustawienia stylów przycisków
        self.default_style = "background-color: none"
        self.active_style = "background-color: lightgray"

        # Przypisanie akcji do przycisków
        self.pause_button.clicked.connect(self.pause_plot)
        self.resume_button.clicked.connect(self.resume_plot)
        self.center_button.clicked.connect(self.center_plot)
        self.trigger_button.clicked.connect(self.toggle_trigger)

        # Ułożenie elementów GUI
        sidebar.addWidget(self.pause_button)
        sidebar.addWidget(self.resume_button)
        sidebar.addWidget(self.center_button)
        sidebar.addWidget(self.trigger_button)
        sidebar.addStretch()

        content_layout.addWidget(self.plot_widget)
        content_layout.addLayout(sidebar)

        main_layout.addLayout(self.info_bar)
        main_layout.addLayout(content_layout)

        central_widget = QtWidgets.QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.update_button_states()

        # === Połączenie szeregowe ===
        try:
            self.ser = serial.Serial(port, baudrate, timeout=0.1)
        except serial.SerialException as e:
            QtWidgets.QMessageBox.critical(self, "Błąd portu", str(e))
            sys.exit(1)

        # Timer do odczytu danych co 5 ms
        self.read_timer = QtCore.QTimer()
        self.read_timer.timeout.connect(self.read_serial)
        self.read_timer.start(5)

    def update_button_states(self):
        self.pause_button.setStyleSheet(self.active_style if self.paused else self.default_style)
        self.resume_button.setStyleSheet(self.default_style if self.paused else self.active_style)

    def toggle_trigger(self):
        self.trigger_enabled = not self.trigger_enabled
        style = self.active_style if self.trigger_enabled else self.default_style
        self.trigger_button.setStyleSheet(style)

    def find_trigger_index(self, voltages, threshold=1.65):
        for i in range(1, len(voltages)):
            if voltages[i - 1] < threshold and voltages[i] >= threshold:
                return i
        return None

    def pause_plot(self):
        self.paused = True
        self.update_button_states()

    def resume_plot(self):
        self.paused = False
        self.update_button_states()

    def center_plot(self):
        self.plot_widget.enableAutoRange()

    def update_voltage_range(self):
        text = self.voltage_range_combo.currentText()
        if text == "0–3.3V":
            self.voltage_range = 3.3
        elif text == "0–6.6V":
            self.voltage_range = 6.6
        elif text == "0–16.5V":
            self.voltage_range = 16.5
        elif text == "0–33V":
            self.voltage_range = 33.0

        self.plot_widget.setYRange(0, self.voltage_range)

    def estimate_frequency(self, data, vmin, vmax):
        if vmax - vmin < 0.05:
            return 0.0

        center = (vmax + vmin) / 2
        delta = (vmax - vmin) * 0.1
        low_thresh = center - delta
        high_thresh = center + delta

        crossings = []
        prev = data[0]
        for i in range(1, len(data)):
            if prev < low_thresh and data[i] >= high_thresh:
                crossings.append(i)
            prev = data[i]

        if len(crossings) < 2:
            return 0.0

        periods = [crossings[i + 1] - crossings[i] for i in range(len(crossings) - 1)]
        avg_samples = sum(periods) / len(periods)
        avg_time_s = avg_samples * 4 / 800_000
        return 1.0 / avg_time_s if avg_time_s else 0.0

    def read_serial(self):
        if self.paused:
            return

        self.buffer += self.ser.read_all()

        while len(self.buffer) >= 2 + self.samples * 2:
            start_idx = self.buffer.find(b'\xA5\xA5')
            if start_idx == -1:
                self.buffer.clear()
                return

            if len(self.buffer) < start_idx + 2 + self.samples * 2:
                return

            frame = self.buffer[start_idx + 2:start_idx + 2 + self.samples * 2]
            self.buffer = self.buffer[start_idx + 2 + self.samples * 2:]

            samples = struct.unpack('<' + 'H' * self.samples, frame)

            voltages = [(val & 0x0FFF) * self.voltage_range / 4095 for val in samples]

            if self.trigger_enabled:
                trigger_idx = self.find_trigger_index(voltages)
                if trigger_idx is None or trigger_idx + 200 > len(voltages):
                    continue
                voltages = voltages[trigger_idx:]

            averaged = [sum(voltages[i:i+4])/4 for i in range(0, len(voltages), 4) if len(voltages[i:i+4]) == 4]
            time_axis = [i * 5e-3 for i in range(len(averaged))]

            self.curve.setData(x=time_axis, y=averaged)

            if averaged:
                v_min = min(averaged)
                v_max = max(averaged)
                v_now = averaged[-1]
                self.voltage_label.setText(f"Napięcie: {v_now:.2f} V")
                self.min_label.setText(f"Min: {v_min:.2f} V")
                self.max_label.setText(f"Max: {v_max:.2f} V")
                freq = self.estimate_frequency(averaged, v_min, v_max)
                self.freq_label.setText(f"Częstotliwość: {freq:.1f} Hz")

    def closeEvent(self, event):
        if hasattr(self, 'ser') and self.ser.is_open:
            self.ser.close()
        event.accept()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = BinaryOscilloscope(port="COM3", baudrate=921600, samples=800*64)
    window.show()
    sys.exit(app.exec())
