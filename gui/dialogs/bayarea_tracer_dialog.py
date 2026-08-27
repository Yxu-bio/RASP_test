from pathlib import Path
import csv
import math

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QBrush, QColor, QDesktopServices, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QDialog,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from gui.window_behavior import configure_resizable_window


class BayAreaTracePlot(QWidget):
    def __init__(self, samples=None, parent=None):
        super().__init__(parent)
        self.chain_samples = [list(samples or [])]
        self.series_name = "lnL"
        self.burnin = 0
        self.setMinimumSize(700, 360)

    def set_samples(self, samples, series_name=None, burnin=None):
        self.set_chain_samples([list(samples or [])], series_name=series_name, burnin=burnin)

    def set_chain_samples(self, chain_samples, series_name=None, burnin=None):
        self.chain_samples = [list(samples or []) for samples in list(chain_samples or [])]
        if series_name is not None:
            self.series_name = str(series_name)
        if burnin is not None:
            self.burnin = int(burnin or 0)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), Qt.white)

        left = 44
        top = 34
        right = 12
        bottom = 24
        width = max(1, self.width() - left - right)
        height = max(1, self.height() - top - bottom)

        painter.setPen(QPen(QColor("#111827"), 1))
        painter.drawLine(left, top, left, top + height)
        painter.drawLine(left, top + height, left + width, top + height)
        painter.setFont(QFont("Arial", 10))
        painter.drawText(left, 18, str(self.series_name or "Trace"))

        chains = []
        for chain_samples in self.chain_samples:
            chains.append([
                (int(cycle), float(value))
                for cycle, value in chain_samples
                if math.isfinite(float(value))
            ])
        all_samples = [sample for chain in chains for sample in chain]
        if not all_samples:
            painter.setPen(QColor("#6b7280"))
            painter.drawText(self.rect(), Qt.AlignCenter, "No BayArea parameter samples found.")
            return

        cycles = [cycle for cycle, _value in all_samples]
        values = [value for _cycle, value in all_samples]
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
            value_label = self._format_axis_value(max_value - (max_value - min_value) * i / 10.0)
            painter.setPen(label_pen)
            painter.drawText(2, y + 4, value_label)

        painter.setPen(Qt.NoPen)
        palette = ["#2563eb", "#dc2626", "#059669", "#9333ea", "#d97706", "#0891b2", "#be123c", "#4f46e5"]
        if len(chains) > 1:
            legend_x = max(left + 120, left + width - min(260, 64 * len(chains)))
            painter.setFont(QFont("Arial", 9))
            for chain_index in range(len(chains)):
                x = legend_x + chain_index * 64
                painter.setBrush(QBrush(QColor(palette[chain_index % len(palette)])))
                painter.drawEllipse(x, 10, 7, 7)
                painter.setPen(QPen(QColor("#374151"), 1))
                painter.drawText(x + 10, 18, "Chain %d" % (chain_index + 1))
                painter.setPen(Qt.NoPen)
        per_chain_limit = max(500, 10000 // max(1, len(chains)))
        for chain_index, samples in enumerate(chains):
            display_samples = samples
            if len(display_samples) > per_chain_limit:
                step = max(1, len(display_samples) // per_chain_limit)
                display_samples = display_samples[::step]
                if display_samples[-1] != samples[-1]:
                    display_samples.append(samples[-1])
            radius = 1 if len(display_samples) > 5000 else 2
            for cycle, value in display_samples:
                color = QColor("#cbd5e1" if int(cycle) < int(self.burnin) else palette[chain_index % len(palette)])
                if int(cycle) < int(self.burnin):
                    color.setAlpha(150)
                elif len(chains) > 1:
                    color.setAlpha(175)
                painter.setBrush(QBrush(color))
                x = left + int(width * (float(cycle) - min_cycle) / float(max_cycle - min_cycle))
                y = top + height - int(height * (float(value) - min_value) / float(max_value - min_value))
                painter.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)

    def _format_axis_value(self, value):
        value = float(value)
        if value == 0.0:
            return "0"
        if abs(value) >= 10000.0 or abs(value) < 0.001:
            return "%.2g" % value
        if abs(value) >= 100.0:
            return "%.0f" % value
        if abs(value) >= 1.0:
            return "%.2f" % value
        return "%.4f" % value


class BayAreaTracerDialog(QDialog):
    def __init__(self, parameters_path, sample_frequency, chain_length, burnin=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tracer View")
        self.resize(820, 500)
        configure_resizable_window(self)

        if isinstance(parameters_path, (list, tuple)):
            path_values = list(parameters_path)
        else:
            path_values = [parameters_path]
        self.parameters_paths = [Path(value) for value in path_values if str(value or "").strip()]
        if not self.parameters_paths:
            raise FileNotFoundError("No BayArea parameters files were provided.")
        self.parameters_path = self.parameters_paths[0]
        self.sample_frequency = int(sample_frequency or 0)
        self.chain_length = int(chain_length or 0)
        self.trace_rows_by_chain = []
        self.trace_names = None
        for path in self.parameters_paths:
            names, rows = self._read_parameter_table(path)
            if self.trace_names is None:
                self.trace_names = list(names)
            else:
                self.trace_names = [name for name in self.trace_names if name in names]
            self.trace_rows_by_chain.append(rows)
        if not self.trace_names:
            raise ValueError("BayArea chains do not share any numeric parameter traces.")
        initial_name = "lnL" if "lnL" in self.trace_names else self.trace_names[0]
        self.samples = self._selected_samples(initial_name)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        path_text = "\n".join(
            "Chain %d: %s" % (index + 1, path)
            for index, path in enumerate(self.parameters_paths)
        )
        self.path_label = QLabel(path_text, self)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.path_label.setWordWrap(True)
        self.path_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.path_label)

        self.plot = BayAreaTracePlot(parent=self)
        self.plot.set_chain_samples(self._selected_chain_samples(initial_name), initial_name, burnin)
        layout.addWidget(self.plot, 1)

        self.summary_label = QLabel("", self)
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.summary_label.setWordWrap(True)
        self.summary_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.summary_label)

        trace_controls = QHBoxLayout()
        self.open_button = QPushButton(
            "Open Parameters" if len(self.parameters_paths) == 1 else "Open Parameters Folder",
            self,
        )
        self.export_button = QPushButton("Export Trace CSV", self)
        self.open_button.clicked.connect(self._open_parameters_file)
        self.export_button.clicked.connect(self._export_trace_csv)
        trace_controls.addWidget(self.open_button)
        trace_controls.addWidget(self.export_button)
        trace_controls.addStretch(1)
        trace_controls.addWidget(QLabel("Trace:", self))
        self.trace_combo = QComboBox(self)
        for name in self.trace_names:
            self.trace_combo.addItem(name, name)
        if "lnL" in self.trace_names:
            self.trace_combo.setCurrentIndex(self.trace_names.index("lnL"))
        self.trace_combo.currentIndexChanged.connect(self._refresh_trace)
        trace_controls.addWidget(self.trace_combo)
        layout.addLayout(trace_controls)

        burnin_controls = QHBoxLayout()
        burnin_controls.addStretch(1)
        burnin_controls.addWidget(QLabel("Burn-in:", self))
        self.burnin_spin = QSpinBox(self)
        self.burnin_spin.setRange(0, max(0, self.chain_length - 1))
        self.burnin_spin.setSingleStep(max(1, self.sample_frequency))
        self.burnin_spin.setValue(max(0, int(burnin or 0)))
        self.burnin_spin.valueChanged.connect(self._refresh_trace)
        self.calculate_button = QPushButton("Calculate", self)
        self.calculate_button.clicked.connect(self._calculate)
        burnin_controls.addWidget(self.burnin_spin)
        burnin_controls.addWidget(self.calculate_button)
        layout.addLayout(burnin_controls)
        self._refresh_trace()

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
        chain_samples = self._selected_chain_samples(self._selected_trace_name())
        total = sum(len(samples) for samples in chain_samples)
        burnin = int(self.burnin_spin.value())
        kept_by_chain = [
            [(cycle, value) for cycle, value in samples if int(cycle) >= burnin]
            for samples in chain_samples
        ]
        kept = [sample for chain in kept_by_chain for sample in chain]
        if not kept or any(not chain for chain in kept_by_chain):
            self.summary_label.setText("Samples: %s; retained after burn-in: 0" % total)
            self.summary_label.setStyleSheet("")
            return
        values_by_chain = [[float(value) for _cycle, value in chain] for chain in kept_by_chain]
        values = [value for chain in values_by_chain for value in chain]
        diagnostics = [self._trace_diagnostic(chain) for chain in values_by_chain]
        rhat = self._split_rhat(values_by_chain) if len(values_by_chain) > 1 else None
        warning_parts = []
        if any(len(chain) >= 100 and float(item["ess_approx"]) < 50.0 for chain, item in zip(values_by_chain, diagnostics)):
            warning_parts.append("low ESS in at least one chain")
        if any(len(chain) >= 100 and float(item["relative_half_shift"]) > 0.25 for chain, item in zip(values_by_chain, diagnostics)):
            warning_parts.append("strong within-chain drift")
        if rhat is not None and (not math.isfinite(rhat) or rhat > 1.05):
            warning_parts.append("split-Rhat indicates non-convergence")
        warning = " Warning: %s." % "; ".join(warning_parts) if warning_parts else ""
        min_ess = min(float(item["ess_approx"]) for item in diagnostics)
        rhat_text = "n/a" if rhat is None else ("infinite" if not math.isfinite(rhat) else "%.3f" % rhat)
        self.summary_label.setText(
            "%s; chains: %d; samples: %d; retained per chain: %s; pooled min/mean/max: "
            "%.6g / %.6g / %.6g; minimum per-chain ESS: %.1f; split-Rhat: %s.%s"
            % (
                self._selected_trace_name(),
                len(chain_samples),
                total,
                ", ".join(str(len(chain)) for chain in kept_by_chain),
                min(values),
                sum(values) / float(len(values)),
                max(values),
                min_ess,
                rhat_text,
                warning,
            )
        )
        self.summary_label.setStyleSheet("color: #b91c1c;" if warning else "")

    def _refresh_trace(self, *_args):
        name = self._selected_trace_name()
        self.samples = self._selected_samples(name)
        self.plot.set_chain_samples(
            self._selected_chain_samples(name),
            series_name=name,
            burnin=int(self.burnin_spin.value()),
        )
        self._update_summary()

    def _selected_trace_name(self):
        if hasattr(self, "trace_combo"):
            value = self.trace_combo.currentData()
            if value:
                return str(value)
        return "lnL" if "lnL" in self.trace_names else self.trace_names[0]

    def _selected_samples(self, name):
        return [sample for chain in self._selected_chain_samples(name) for sample in chain]

    def _selected_chain_samples(self, name):
        chains = []
        for rows in self.trace_rows_by_chain:
            samples = []
            for row in rows:
                if "n" not in row or name not in row:
                    continue
                samples.append((int(row["n"]), float(row[name])))
            chains.append(samples)
        return chains

    def _open_parameters_file(self):
        target = self.parameters_path if len(self.parameters_paths) == 1 else self.parameters_path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

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
                writer.writerow(["chain"] + self.trace_names_with_cycle() + ["included_after_burnin"])
                for chain_index, rows in enumerate(self.trace_rows_by_chain):
                    for row in rows:
                        cycle = int(row.get("n", 0))
                        writer.writerow(
                            [chain_index + 1]
                            + [row.get(name, "") for name in self.trace_names_with_cycle()]
                            + [int(cycle >= burnin)]
                        )
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def trace_names_with_cycle(self):
        return ["n"] + [name for name in self.trace_names if name != "n"]

    def _read_parameter_table(self, path):
        if not path.exists():
            raise FileNotFoundError("Could not find BayArea parameters: %s" % path)

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            raise ValueError("BayArea parameters file is empty: %s" % path)
        header = lines[0].split("\t")
        rows = []
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < len(header):
                continue
            row = {}
            try:
                for name, value in zip(header, parts):
                    number = float(value)
                    if not math.isfinite(number):
                        raise ValueError("non-finite trace value")
                    row[name] = int(number) if name == "n" else number
            except Exception:
                continue
            rows.append(row)
        trace_names = [name for name in header if name != "n"]
        if not rows or not trace_names:
            raise ValueError("No numeric BayArea parameter samples were found: %s" % path)
        return trace_names, rows

    def _trace_diagnostic(self, values):
        count = len(values)
        midpoint = max(1, count // 2)
        first = values[:midpoint]
        second = values[midpoint:] or values[-1:]
        first_mean = sum(first) / float(len(first))
        second_mean = sum(second) / float(len(second))
        ess_values = values
        if count > 5000:
            step = int(math.ceil(float(count) / 5000.0))
            ess_values = values[::step]
        return {
            "minimum": min(values),
            "maximum": max(values),
            "mean": sum(values) / float(count),
            "ess_approx": self._approximate_ess(ess_values),
            "ess_diagnostic_sample_count": len(ess_values),
            "relative_half_shift": abs(first_mean - second_mean) / max(abs(second_mean), 1e-12),
        }

    def _split_rhat(self, chains):
        split_chains = []
        for values in chains:
            midpoint = len(values) // 2
            if midpoint < 2:
                return None
            split_chains.append(list(values[:midpoint]))
            split_chains.append(list(values[-midpoint:]))
        sample_count = min(len(values) for values in split_chains)
        if sample_count < 2:
            return None
        split_chains = [values[-sample_count:] for values in split_chains]
        means = [sum(values) / float(sample_count) for values in split_chains]
        variances = [
            sum((value - mean) ** 2 for value in values) / float(sample_count - 1)
            for values, mean in zip(split_chains, means)
        ]
        within = sum(variances) / float(len(variances))
        if within <= 0.0:
            return 1.0 if max(means) == min(means) else float("inf")
        grand_mean = sum(means) / float(len(means))
        between = sample_count * sum((mean - grand_mean) ** 2 for mean in means) / float(len(means) - 1)
        variance = ((sample_count - 1.0) / sample_count) * within + between / sample_count
        return max(1.0, math.sqrt(max(0.0, variance / within)))

    def _approximate_ess(self, values, max_lag=500):
        count = len(values)
        if count < 3:
            return float(count)
        mean = sum(values) / float(count)
        variance = sum((value - mean) ** 2 for value in values) / float(count)
        if variance <= 0.0:
            return float(count)
        rho_sum = 0.0
        for lag in range(1, min(int(max_lag), count - 1) + 1):
            covariance = sum(
                (values[index] - mean) * (values[index - lag] - mean)
                for index in range(lag, count)
            ) / float(count - lag)
            rho = covariance / variance
            if rho <= 0.0:
                break
            rho_sum += rho
        return max(1.0, min(float(count), float(count) / (1.0 + 2.0 * rho_sum)))
