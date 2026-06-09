from pathlib import Path
import csv

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QBrush, QColor, QDesktopServices, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class BayAreaTracePlot(QWidget):
    def __init__(self, samples=None, parent=None):
        super().__init__(parent)
        self.samples = list(samples or [])
        self.setMinimumSize(700, 360)

    def set_samples(self, samples):
        self.samples = list(samples or [])
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), Qt.white)

        left = 44
        top = 18
        right = 12
        bottom = 24
        width = max(1, self.width() - left - right)
        height = max(1, self.height() - top - bottom)

        painter.setPen(QPen(QColor("#111827"), 1))
        painter.drawLine(left, top, left, top + height)
        painter.drawLine(left, top + height, left + width, top + height)

        if not self.samples:
            painter.setPen(QColor("#6b7280"))
            painter.drawText(self.rect(), Qt.AlignCenter, "No BayArea parameter samples found.")
            return

        cycles = [int(cycle) for cycle, _lnl in self.samples]
        values = [float(lnl) for _cycle, lnl in self.samples]
        min_cycle = min(cycles)
        max_cycle = max(cycles)
        min_value = min(values)
        max_value = max(values)
        if max_cycle == min_cycle:
            max_cycle = min_cycle + 1
        if max_value == min_value:
            max_value = min_value + 1.0

        font = QFont("Arial", 9)
        painter.setFont(font)
        grid_pen = QPen(QColor("#d1d5db"), 1)
        label_pen = QPen(QColor("#6b7280"), 1)
        for i in range(1, 10):
            x = left + int(width * i / 10.0)
            painter.setPen(grid_pen)
            painter.drawLine(x, top, x, top + height)
            cycle_label = int(min_cycle + (max_cycle - min_cycle) * i / 10.0)
            painter.setPen(label_pen)
            painter.drawText(x + 2, top + 14, str(cycle_label))

            y = top + int(height * i / 10.0)
            painter.setPen(grid_pen)
            painter.drawLine(left, y, left + width, y)
            value_label = int(max_value - (max_value - min_value) * i / 10.0)
            painter.setPen(label_pen)
            painter.drawText(2, y + 4, str(value_label))

        point_brush = QBrush(QColor("#1d4ed8"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(point_brush)
        for cycle, value in self.samples:
            x = left + int(width * (float(cycle) - min_cycle) / float(max_cycle - min_cycle))
            y = top + height - int(height * (float(value) - min_value) / float(max_value - min_value))
            painter.drawEllipse(x - 2, y - 2, 4, 4)


class BayAreaTracerDialog(QDialog):
    def __init__(self, parameters_path, sample_frequency, chain_length, burnin=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tracer View")
        self.resize(820, 500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.parameters_path = Path(parameters_path)
        self.sample_frequency = int(sample_frequency or 0)
        self.chain_length = int(chain_length or 0)
        self.samples = self._read_samples(self.parameters_path)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.path_label = QLabel(str(self.parameters_path), self)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.path_label)

        self.plot = BayAreaTracePlot(self.samples, self)
        layout.addWidget(self.plot, 1)

        self.summary_label = QLabel("", self)
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.summary_label)

        controls = QHBoxLayout()
        self.open_button = QPushButton("Open Parameters", self)
        self.export_button = QPushButton("Export Trace CSV", self)
        self.open_button.clicked.connect(self._open_parameters_file)
        self.export_button.clicked.connect(self._export_trace_csv)
        controls.addWidget(self.open_button)
        controls.addWidget(self.export_button)
        controls.addStretch(1)
        controls.addWidget(QLabel("Burn-in:", self))
        self.burnin_spin = QSpinBox(self)
        self.burnin_spin.setRange(0, max(0, self.chain_length - 1))
        self.burnin_spin.setSingleStep(max(1, self.sample_frequency))
        self.burnin_spin.setValue(max(0, int(burnin or 0)))
        self.burnin_spin.valueChanged.connect(self._update_summary)
        self.calculate_button = QPushButton("Calculate", self)
        self.calculate_button.clicked.connect(self._calculate)
        controls.addWidget(self.burnin_spin)
        controls.addWidget(self.calculate_button)
        layout.addLayout(controls)
        self._update_summary()

    def selected_burnin(self):
        return int(self.burnin_spin.value())

    def _calculate(self):
        burnin = int(self.burnin_spin.value())
        if self.sample_frequency > 0 and burnin % self.sample_frequency != 0:
            QMessageBox.warning(self, "Burn-in error", "Burn-in should be an integer multiple of frequent of samples.")
            return
        if self.chain_length > 0 and burnin >= self.chain_length:
            QMessageBox.warning(self, "Burn-in error", "Burn-in should be no more than chain length.")
            return
        self.accept()

    def _update_summary(self):
        total = len(self.samples)
        burnin = int(self.burnin_spin.value())
        kept = [(cycle, value) for cycle, value in self.samples if int(cycle) >= burnin]
        if not kept:
            self.summary_label.setText("Samples: %s; retained after burn-in: 0" % total)
            return
        values = [float(value) for _cycle, value in kept]
        mean = sum(values) / float(len(values))
        self.summary_label.setText(
            "Samples: %s; retained after burn-in: %s; lnL min/mean/max: %.4f / %.4f / %.4f"
            % (total, len(kept), min(values), mean, max(values))
        )

    def _open_parameters_file(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.parameters_path)))

    def _export_trace_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export BayArea trace",
            "",
            "CSV files (*.csv);;All files (*.*)",
        )
        if not path:
            return
        try:
            burnin = int(self.burnin_spin.value())
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["cycle", "lnL", "included_after_burnin"])
                for cycle, value in self.samples:
                    writer.writerow([int(cycle), float(value), int(int(cycle) >= burnin)])
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def _read_samples(self, path):
        if not path.exists():
            raise FileNotFoundError("Could not find BayArea parameters: %s" % path)

        samples = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            try:
                samples.append((int(float(parts[0])), float(parts[1])))
            except Exception:
                continue
        return samples
