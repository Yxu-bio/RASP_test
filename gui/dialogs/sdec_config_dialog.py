from itertools import combinations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from domain.models.sdec_config import SDECConfig, SDECMRCAConstraint


class CheckableAreaComboBox(QComboBox):
    def __init__(self, areas, parent=None):
        super().__init__(parent)
        self._areas = [str(area).strip() for area in list(areas or []) if str(area).strip()]
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText("")
        for area in self._areas:
            self.addItem(area, area)
            item = self.model().item(self.count() - 1, 0)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
        self.view().pressed.connect(self._toggle_item)
        self._sync_text()

    def selected_areas(self):
        values = []
        for index in range(self.count()):
            item = self.model().item(index, 0)
            if item is not None and item.checkState() == Qt.Checked:
                values.append(str(self.itemData(index) or self.itemText(index)).strip())
        return values

    def set_selected_areas(self, areas):
        wanted = set(str(area).strip() for area in list(areas or []) if str(area).strip())
        for index in range(self.count()):
            area = str(self.itemData(index) or self.itemText(index)).strip()
            item = self.model().item(index, 0)
            if item is not None:
                item.setCheckState(Qt.Checked if area in wanted else Qt.Unchecked)
        self._sync_text()

    def _toggle_item(self, model_index):
        item = self.model().itemFromIndex(model_index)
        if item is None:
            return
        item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
        self._sync_text()

    def _sync_text(self):
        self.lineEdit().setText("".join(self.selected_areas()))


class SDECConfigDialog(QDialog):
    def __init__(
        self,
        area_names,
        taxon_names=None,
        taxon_ranges=None,
        root_age="",
        config=None,
        parent=None,
        threads_label="Threads:",
    ):
        super().__init__(parent)
        self.setWindowTitle("DEC")
        self.resize(1120, 660)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.threads_label_text = str(threads_label or "Threads:").strip() or "Threads:"
        self.area_names = [str(x).strip() for x in list(area_names or []) if str(x).strip()]
        self.taxon_names = [str(x).strip() for x in list(taxon_names or []) if str(x).strip()]
        self.taxon_ranges = set(str(x).strip() for x in list(taxon_ranges or []) if str(x).strip())
        self.root_age = str(root_age or "").strip()
        if config is not None and list(getattr(config, "area_names", []) or []) == self.area_names:
            self._config = config
            if self.root_age and not str(getattr(self._config, "root_age", "") or "").strip():
                self._config.root_age = self.root_age
        else:
            self._config = SDECConfig.default_for_areas(self.area_names)
            self._config.root_age = self.root_age

        self._apply_root_age_default_period(self._config)

        self._building = False
        self._build_ui()
        self._load_config(self._config)

    def config(self):
        return self._config

    def accept(self):
        try:
            self._config = self._collect_config()
            self._config.validate()
            self._validate_root_age_periods(self._config)
        except Exception as exc:
            QMessageBox.warning(self, "Invalid configuration", str(exc))
            return
        super().accept()

    def _build_ui(self):
        menu_bar = QMenuBar(self)
        operation_menu = menu_bar.addMenu("Operation")
        refresh_action = operation_menu.addAction("Refresh State Preview")
        save_action = operation_menu.addAction("Save Setting")
        load_action = operation_menu.addAction("Load Setting")
        refresh_action.triggered.connect(self._refresh_state_preview)
        save_action.triggered.connect(self._save_settings)
        load_action.triggered.connect(self._load_settings)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_constraints_tab(), "Constraints")
        self.tabs.addTab(self._build_fossil_tab(), "Fossil && MRCA")

        self.thread_spin = QSpinBox(self)
        self.thread_spin.setMinimum(1)
        self.thread_spin.setMaximum(256)

        self.reset_button = QPushButton("Reset", self)
        self.ok_button = QPushButton("OK", self)
        self.cancel_button = QPushButton("Cancel", self)
        self.reset_button.clicked.connect(self._reset_config)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(QLabel(self.threads_label_text, self))
        bottom.addWidget(self.thread_spin)
        bottom.addWidget(self.reset_button)
        bottom.addWidget(self.ok_button)
        bottom.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.setMenuBar(menu_bar)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(bottom)

    def _build_constraints_tab(self):
        page = QWidget(self)
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal, page)
        self.dispersal_table = QTableWidget(page)
        self.dispersal_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.dispersal_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.dispersal_table.setMinimumWidth(560)

        right = QWidget(page)
        right.setMinimumWidth(460)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("Maximum areas:", right))
        self.max_areas_spin = QSpinBox(right)
        self.max_areas_spin.setMinimum(1)
        self.max_areas_spin.setMaximum(max(1, len(self.area_names)))
        self.max_areas_spin.valueChanged.connect(self._refresh_state_preview)
        range_row.addWidget(self.max_areas_spin)
        range_row.addStretch(1)

        self.state_preview_table = QTableWidget(right)
        self.state_preview_table.setColumnCount(1)
        self.state_preview_table.setHorizontalHeaderLabels(["State"])
        self.state_preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.state_preview_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.state_preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.state_preview_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.state_preview_table.setMaximumHeight(150)

        root_row = QHBoxLayout()
        root_row.addWidget(QLabel("Root age:", right))
        self.root_age_edit = QLineEdit(right)
        root_row.addWidget(self.root_age_edit)

        period_buttons = QHBoxLayout()
        self.add_period_button = QPushButton("Add", right)
        self.remove_period_button = QPushButton("Remove", right)
        self.add_period_button.clicked.connect(self._add_period_time)
        self.remove_period_button.clicked.connect(self._remove_period_time)
        period_buttons.addWidget(self.add_period_button)
        period_buttons.addWidget(self.remove_period_button)

        self.period_table = QTableWidget(right)
        self.period_table.setColumnCount(1)
        self.period_table.setHorizontalHeaderLabels(["Time"])
        self.period_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.period_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        right_layout.addLayout(range_row)
        right_layout.addWidget(QLabel("State Preview", right))
        right_layout.addWidget(self.state_preview_table, 1)
        right_layout.addLayout(root_row)
        right_layout.addLayout(period_buttons)
        right_layout.addWidget(self.period_table, 1)

        self.period_area_rules_table = QTableWidget(right)
        self.period_area_rules_table.setColumnCount(2)
        self.period_area_rules_table.setHorizontalHeaderLabels(["Include area", "Exclude areas"])
        self.period_area_rules_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.period_area_rules_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        file_buttons = QHBoxLayout()
        self.export_period_button = QPushButton("Export", right)
        self.import_period_button = QPushButton("Import", right)
        self.export_period_button.clicked.connect(self._export_period_file)
        self.import_period_button.clicked.connect(self._import_period_file)
        file_buttons.addWidget(self.export_period_button)
        file_buttons.addWidget(self.import_period_button)

        right_layout.addWidget(QLabel("Period Area Rules", right))
        right_layout.addWidget(self.period_area_rules_table, 1)
        right_layout.addLayout(file_buttons)

        splitter.addWidget(self.dispersal_table)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([640, 480])
        layout.addWidget(splitter, 1)
        return page

    def _build_fossil_tab(self):
        page = QWidget(self)
        layout = QHBoxLayout(page)
        layout.setContentsMargins(4, 6, 4, 4)

        left = QWidget(page)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Select two taxa to define their MRCA", left))

        pickers = QHBoxLayout()
        self.taxon1_list = QListWidget(left)
        self.taxon2_list = QListWidget(left)
        for name in self.taxon_names:
            self.taxon1_list.addItem(name)
            self.taxon2_list.addItem(name)
        pickers.addWidget(self.taxon1_list)
        pickers.addWidget(self.taxon2_list)

        self.mrca_range_table = QTableWidget(left)
        self.mrca_range_table.setColumnCount(1)
        self.mrca_range_table.setRowCount(len(self.area_names))
        self.mrca_range_table.setHorizontalHeaderLabels(["Range"])
        self.mrca_range_table.setVerticalHeaderLabels(self.area_names)
        self.mrca_range_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.mrca_range_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        for row, area in enumerate(self.area_names):
            item = QTableWidgetItem(area)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.mrca_range_table.setItem(row, 0, item)

        add_remove = QHBoxLayout()
        self.remove_mrca_button = QPushButton("Remove", left)
        self.add_mrca_button = QPushButton("Add", left)
        self.remove_mrca_button.clicked.connect(self._remove_mrca_constraint)
        self.add_mrca_button.clicked.connect(self._add_mrca_constraint)
        add_remove.addWidget(self.remove_mrca_button)
        add_remove.addWidget(self.add_mrca_button)

        pickers.addWidget(self.mrca_range_table)
        left_layout.addLayout(add_remove)
        left_layout.addLayout(pickers, 1)

        self.mrca_table = QTableWidget(page)
        self.mrca_table.setColumnCount(4)
        self.mrca_table.setHorizontalHeaderLabels(["Taxon1", "Taxon2", "Range", ""])
        self.mrca_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.mrca_table.horizontalHeader().setStretchLastSection(True)
        self.mrca_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        layout.addWidget(left, 1)
        layout.addWidget(self.mrca_table, 1)
        return page

    def _load_config(self, config):
        self._building = True
        self.thread_spin.setValue(max(1, int(config.threads)))
        self.max_areas_spin.setValue(max(1, min(int(config.max_areas), self.max_areas_spin.maximum())))
        self._refresh_state_preview()
        self.root_age_edit.setText(str(config.root_age or ""))
        self._load_period_table(config.period_times)
        self._load_dispersal_table(config.dispersal_matrices, config.period_times)
        self._load_period_area_rules(
            getattr(config, "period_include_area_bits", []),
            getattr(config, "period_exclude_area_bits", []),
            config.period_times,
            config.dispersal_matrices,
        )
        self._load_mrca_table(config.mrca_constraints)
        self._building = False

    def _reset_config(self):
        config = SDECConfig.default_for_areas(self.area_names)
        config.root_age = self.root_age
        self._apply_root_age_default_period(config)
        self._load_config(config)

    def _apply_root_age_default_period(self, config):
        if not self.root_age:
            return
        try:
            root_age = float(self.root_age)
        except Exception:
            return
        if root_age <= 0:
            return
        times = list(getattr(config, "period_times", []) or [])
        if len(times) <= 1:
            config.period_times = [0.0, root_age]

    def _refresh_ranges_from_matrix(self):
        self._refresh_state_preview()

    def _refresh_state_preview(self):
        if not hasattr(self, "state_preview_table"):
            return
        states = self._lagrange_state_preview()
        self.state_preview_table.setRowCount(len(states))

        for idx, state in enumerate(states):
            self.state_preview_table.setItem(idx, 0, QTableWidgetItem(state))

    def _lagrange_state_preview(self):
        max_size = min(max(1, int(self.max_areas_spin.value() or 1)), len(self.area_names))
        states = ["/"]
        for size in range(1, max_size + 1):
            for combo in combinations(self.area_names, size):
                states.append("".join(combo))
        return states

    def _collect_range_matrix(self):
        return SDECConfig.default_for_areas(self.area_names).range_matrix

    def _collect_range_config(self):
        return SDECConfig(
            area_names=list(self.area_names),
            range_matrix=self._collect_range_matrix(),
            include_ranges=[],
            exclude_ranges=[],
            use_include_list=False,
            max_areas=self.max_areas_spin.value(),
            threads=self.thread_spin.value(),
        )

    def _load_period_table(self, times):
        values = [float(x) for x in list(times or [0.0])]
        if not values:
            values = [0.0]
        self.period_table.setRowCount(len(values))
        for row, value in enumerate(values):
            self.period_table.setVerticalHeaderItem(row, QTableWidgetItem(str(row)))
            self.period_table.setItem(row, 0, QTableWidgetItem(self._format_number(value)))

    def _load_dispersal_table(self, matrices, times):
        period_count = max(1, len(list(times or [])) - 1)
        if period_count <= 0:
            period_count = max(1, len(list(matrices or [])))
        n = len(self.area_names)
        self.dispersal_table.setColumnCount(n)
        self.dispersal_table.setHorizontalHeaderLabels(self.area_names)
        self.dispersal_table.setRowCount(period_count * n)

        for period in range(period_count):
            matrix = matrices[period] if period < len(matrices or []) else None
            for area_row, area in enumerate(self.area_names):
                row = period * n + area_row
                self.dispersal_table.setVerticalHeaderItem(row, QTableWidgetItem("%s-%s %s" % (period, period + 1, area)))
                for col in range(n):
                    value = 1.0
                    if matrix is not None and area_row < len(matrix) and col < len(matrix[area_row]):
                        value = matrix[area_row][col]
                    self.dispersal_table.setItem(row, col, QTableWidgetItem(self._format_number(value)))

    def _load_period_area_rules(self, include_bits, exclude_bits, times, matrices):
        period_count = max(1, len(list(times or [])) - 1)
        if period_count <= 0:
            period_count = max(1, len(list(matrices or [])))
        include_values = list(include_bits or [])
        exclude_values = list(exclude_bits or [])
        self.period_area_rules_table.setRowCount(period_count)
        for period in range(period_count):
            self.period_area_rules_table.setVerticalHeaderItem(
                period,
                QTableWidgetItem("%s-%s" % (period, period + 1)),
            )
            combo = QComboBox(self.period_area_rules_table)
            combo.addItem("", "")
            for area in self.area_names:
                combo.addItem(area, area)
            include_text = str(include_values[period]).strip() if period < len(include_values) else ""
            include_area = self._single_area_from_bits(include_text)
            if period == 0:
                combo.setEnabled(False)
            elif include_area:
                combo.setCurrentIndex(max(0, combo.findData(include_area)))
            self.period_area_rules_table.setCellWidget(period, 0, combo)

            exclude_text = str(exclude_values[period]).strip() if period < len(exclude_values) else ""
            exclude_combo = CheckableAreaComboBox(self.area_names, self.period_area_rules_table)
            if period == 0:
                exclude_combo.setEnabled(False)
            else:
                exclude_combo.set_selected_areas(self._parse_area_text(self._areas_from_bits(exclude_text)))
            self.period_area_rules_table.setCellWidget(period, 1, exclude_combo)

    def _collect_period_times(self):
        values = []
        for row in range(self.period_table.rowCount()):
            item = self.period_table.item(row, 0)
            text = item.text().strip() if item is not None else ""
            if text:
                values.append(float(text))
        if not values:
            values = [0.0]
        values = sorted(set(values))
        if values[0] != 0.0:
            values.insert(0, 0.0)
        return values

    def _collect_dispersal_matrices(self):
        n = len(self.area_names)
        if n <= 0:
            return []
        period_count = max(1, self.dispersal_table.rowCount() // n)
        matrices = []
        for period in range(period_count):
            matrix = []
            for area_row in range(n):
                row_values = []
                for col in range(n):
                    item = self.dispersal_table.item(period * n + area_row, col)
                    text = item.text().strip() if item is not None else "1"
                    row_values.append(float(text or "1"))
                matrix.append(row_values)
            matrices.append(matrix)
        return matrices

    def _collect_period_include_area_bits(self):
        values = []
        for row in range(self.period_area_rules_table.rowCount()):
            if row == 0:
                values.append("")
                continue
            combo = self.period_area_rules_table.cellWidget(row, 0)
            area = ""
            if combo is not None:
                area = str(combo.currentData() or "").strip()
            values.append(self._areas_to_bits([area] if area else []))
        return values

    def _collect_period_exclude_area_bits(self):
        values = []
        for row in range(self.period_area_rules_table.rowCount()):
            if row == 0:
                values.append("")
                continue
            combo = self.period_area_rules_table.cellWidget(row, 1)
            if combo is not None and hasattr(combo, "selected_areas"):
                areas = combo.selected_areas()
            else:
                areas = self._parse_area_text(self._table_text(self.period_area_rules_table, row, 1))
            values.append(self._areas_to_bits(areas))
        return values

    def _resize_period_area_rules(self, period_count):
        include_bits = self._collect_period_include_area_bits()
        exclude_bits = self._collect_period_exclude_area_bits()
        count = max(1, int(period_count or 1))
        include_bits = (include_bits + [""] * count)[:count]
        exclude_bits = (exclude_bits + [""] * count)[:count]
        return include_bits, exclude_bits

    def _single_area_from_bits(self, bits):
        text = str(bits or "").strip()
        if len(text) != len(self.area_names) or text.count("1") != 1:
            return ""
        return self.area_names[text.index("1")]

    def _areas_from_bits(self, bits):
        text = str(bits or "").strip()
        if len(text) != len(self.area_names) or any(ch not in "01" for ch in text):
            return ""
        return "".join(area for area, bit in zip(self.area_names, text) if bit == "1")

    def _areas_to_bits(self, areas):
        area_set = set(str(area).strip() for area in list(areas or []) if str(area).strip())
        return "".join("1" if area in area_set else "0" for area in self.area_names)

    def _parse_area_text(self, text):
        value = str(text or "").strip()
        if not value:
            return []
        if len(value) == len(self.area_names) and all(ch in "01" for ch in value):
            return [
                area
                for area, bit in zip(self.area_names, value)
                if bit == "1"
            ]

        normalized = value
        for sep in [",", ";", "/", "|", "+"]:
            normalized = normalized.replace(sep, " ")
        tokens = [part.strip() for part in normalized.split() if part.strip()]
        if (
            len(tokens) == 1
            and tokens[0] not in self.area_names
            and all(sep not in value for sep in [",", ";", "/", "|", "+", " "])
        ):
            tokens = list(value)
        if not tokens and value:
            tokens = list(value)

        areas = []
        for token in tokens:
            if token not in self.area_names:
                raise ValueError("Unknown area in Period Area Rules: %s" % token)
            if token not in areas:
                areas.append(token)
        return areas

    def _add_period_time(self):
        times = self._collect_period_times()
        if len(times) >= 2:
            insert_value = float(times[1]) / 2.0
        else:
            insert_value = (times[-1] if times else 0.0) + 1.0
        times.insert(1, insert_value)
        matrices = self._collect_dispersal_matrices()
        matrices.insert(0, SDECConfig._default_dispersal_matrix(len(self.area_names)))
        self._load_period_table(times)
        self._load_dispersal_table(matrices, times)
        self._load_period_area_rules(*self._resize_period_area_rules(len(times) - 1), times, matrices)

    def _remove_period_time(self):
        if self.period_table.rowCount() <= 2:
            return
        row = self.period_table.currentRow()
        if row <= 0:
            row = 1
        times = self._collect_period_times()
        if row < len(times):
            del times[row]
        matrices = self._collect_dispersal_matrices()
        remove_matrix_index = max(0, row - 1)
        if remove_matrix_index < len(matrices):
            del matrices[remove_matrix_index]
        matrices = matrices[:max(1, len(times) - 1)]
        self._load_period_table(times)
        self._load_dispersal_table(matrices, times)
        self._load_period_area_rules(*self._resize_period_area_rules(len(times) - 1), times, matrices)

    def _import_period_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import time periods", "", "Text files (*.txt);;All files (*)")
        if not path:
            return
        try:
            matrices, times = self._read_period_file(path)
        except Exception as exc:
            QMessageBox.warning(self, "Import failed", str(exc))
            return
        self._load_period_table(times)
        self._load_dispersal_table(matrices, times)
        self._load_period_area_rules([], [], times, matrices)

    def _export_period_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export time periods", "", "Text files (*.txt);;All files (*)")
        if not path:
            return
        text = self._format_period_file(self._collect_dispersal_matrices(), self._collect_period_times())
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def _read_period_file(self, path):
        text = open(path, "r", encoding="utf-8-sig", errors="ignore").read()
        body, marker, tail = text.partition("#periods=")
        times = []
        if marker:
            times = [float(x) for x in tail.replace(",", " ").split() if x.strip()]
            if times and times[0] != 0.0:
                times.insert(0, 0.0)
        else:
            times = [0.0]

        rows = []
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            rows.append([float(x) for x in stripped.replace(",", " ").split()])

        n = len(self.area_names)
        if n <= 0 or len(rows) % n != 0:
            raise ValueError("The matrix row count does not match the number of areas.")
        matrices = []
        for start in range(0, len(rows), n):
            matrix = rows[start:start + n]
            if any(len(row) != n for row in matrix):
                raise ValueError("The matrix column count does not match the number of areas.")
            matrices.append(matrix)

        if not matrices:
            matrices = [SDECConfig._default_dispersal_matrix(n)]
        if len(times) < 2 and len(matrices) > 1:
            times = [float(i) for i in range(len(matrices) + 1)]
        return matrices, times

    def _format_period_file(self, matrices, times):
        blocks = []
        for matrix in matrices:
            for row in matrix:
                blocks.append(" ".join(self._format_number(value) for value in row))
            blocks.append("")
            blocks.append("")
        exported_times = list(times[1:] if times and times[0] == 0.0 else times)
        blocks.append("#periods=" + " ".join(self._format_number(x) for x in exported_times) + " ")
        return "\n".join(blocks).rstrip() + "\n"

    def _load_mrca_table(self, constraints):
        self.mrca_table.setRowCount(0)
        for constraint in list(constraints or []):
            self._append_mrca_row(constraint.taxon1, constraint.taxon2, constraint.range_name)

    def _add_mrca_constraint(self):
        item1 = self.taxon1_list.currentItem()
        item2 = self.taxon2_list.currentItem()
        if item1 is None or item2 is None:
            QMessageBox.warning(self, "Cannot add", "Please select two taxa.")
            return
        taxon1 = item1.text().strip()
        taxon2 = item2.text().strip()
        if taxon1 == taxon2:
            QMessageBox.warning(self, "Cannot add", "Please select different taxa.")
            return
        range_name = self._selected_mrca_range()
        if not range_name:
            QMessageBox.warning(self, "Cannot add", "Please select at least one area.")
            return
        if self._has_mrca_taxon_pair(taxon1, taxon2):
            QMessageBox.warning(self, "Cannot add", "Repeated taxon group.")
            return
        self._append_mrca_row(taxon1, taxon2, range_name)

    def _remove_mrca_constraint(self):
        for row in range(self.mrca_table.rowCount() - 1, -1, -1):
            item = self.mrca_table.item(row, 3)
            if item is not None and item.checkState() == Qt.Checked:
                self.mrca_table.removeRow(row)

    def _append_mrca_row(self, taxon1, taxon2, range_name):
        row = self.mrca_table.rowCount()
        self.mrca_table.insertRow(row)
        for col, value in enumerate([taxon1, taxon2, range_name]):
            item = QTableWidgetItem(str(value))
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.mrca_table.setItem(row, col, item)
        remove_item = QTableWidgetItem("")
        remove_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
        remove_item.setCheckState(Qt.Unchecked)
        self.mrca_table.setItem(row, 3, remove_item)

    def _has_mrca_taxon_pair(self, taxon1, taxon2):
        requested = {str(taxon1).strip(), str(taxon2).strip()}
        for row in range(self.mrca_table.rowCount()):
            existing = {
                self._table_text(self.mrca_table, row, 0),
                self._table_text(self.mrca_table, row, 1),
            }
            if existing == requested:
                return True
        return False

    def _selected_mrca_range(self):
        parts = []
        for row, area in enumerate(self.area_names):
            item = self.mrca_range_table.item(row, 0)
            if item is not None and item.checkState() == Qt.Checked:
                parts.append(area)
        return "".join(parts)

    def _collect_mrca_constraints(self):
        values = []
        for row in range(self.mrca_table.rowCount()):
            taxon1 = self._table_text(self.mrca_table, row, 0)
            taxon2 = self._table_text(self.mrca_table, row, 1)
            range_name = self._table_text(self.mrca_table, row, 2)
            if taxon1 and taxon2 and range_name:
                values.append(SDECMRCAConstraint(taxon1=taxon1, taxon2=taxon2, range_name=range_name))
        return values

    def _collect_config(self):
        range_config = self._collect_range_config()
        return SDECConfig(
            area_names=list(self.area_names),
            range_matrix=range_config.range_matrix,
            include_ranges=range_config.include_ranges,
            exclude_ranges=range_config.exclude_ranges,
            use_include_list=range_config.use_include_list,
            max_areas=range_config.max_areas,
            threads=self.thread_spin.value(),
            root_age=self.root_age_edit.text().strip(),
            period_times=self._collect_period_times(),
            dispersal_matrices=self._collect_dispersal_matrices(),
            period_include_area_bits=self._collect_period_include_area_bits(),
            period_exclude_area_bits=self._collect_period_exclude_area_bits(),
            mrca_constraints=self._collect_mrca_constraints(),
        )

    def _validate_root_age_periods(self, config):
        try:
            root_age = float(str(config.root_age or "").strip())
        except Exception:
            return
        if root_age <= 0:
            return
        count = sum(1 for value in list(config.period_times or [])[1:] if float(value) >= root_age)
        if count > 1:
            raise ValueError("The timeperiods has to have just only one oldest time that is older than the root age of the tree.")

    def _save_settings(self):
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Save DEC Setting",
            "",
            "JSON files (*.json);;Text files (*.txt);;All files (*)",
        )
        if not path:
            return
        if "." not in path.replace("\\", "/").split("/")[-1]:
            path += ".json"
        try:
            config = self._collect_config()
            config.validate()
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(config.to_preset_json_text())
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))

    def _load_settings(self):
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Load DEC Setting",
            "",
            "JSON files (*.json);;Text files (*.txt);;All files (*)",
        )
        if not path:
            return
        try:
            text = open(path, "r", encoding="utf-8", errors="ignore").read()
            base_config = self._collect_config()
            try:
                config = SDECConfig.from_preset_json_text(
                    text,
                    area_names=self.area_names,
                    base_config=base_config,
                )
            except ValueError as exc:
                if not str(text or "").lstrip().startswith("{"):
                    config = SDECConfig.from_legacy_config_text(
                        text,
                        area_names=self.area_names,
                        base_config=base_config,
                    )
                    config.validate()
                else:
                    raise exc
            self._config = config
            self._load_config(config)
        except Exception as exc:
            QMessageBox.warning(self, "Load failed", str(exc))

    def _populate_list(self, widget, values):
        widget.clear()
        for value in list(values or []):
            text = str(value).strip()
            if text:
                widget.addItem(text)
        widget.sortItems()

    def _list_values(self, widget):
        return [
            widget.item(i).text().strip()
            for i in range(widget.count())
            if widget.item(i).text().strip()
        ]

    def _table_text(self, table, row, col):
        item = table.item(row, col)
        return item.text().strip() if item is not None else ""

    def _format_number(self, value):
        try:
            number = float(value)
        except Exception:
            return str(value)
        if number.is_integer():
            return str(int(number))
        return ("%g" % number)
