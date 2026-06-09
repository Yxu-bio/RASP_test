from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QCheckBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from domain.models.sbgb_config import (
    SBGBConfig,
    SBGB_MODEL_DISPLAY,
    SBGB_NULL_RANGE_MODE_DISPLAY,
    normalize_sbgb_model_name,
    normalize_sbgb_null_range_mode,
)


class SBGBConfigDialog(QDialog):
    def __init__(
        self,
        area_names,
        taxon_ranges=None,
        root_age="",
        config=None,
        cores_label="Threads",
        show_cores_control=True,
        show_model_selector=True,
        show_test_j_models=False,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("BioGeoBEARS")
        self.resize(760, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.area_names = [str(x).strip() for x in list(area_names or []) if str(x).strip()]
        self.taxon_ranges = [str(x).strip() for x in list(taxon_ranges or []) if str(x).strip()]
        self.root_age = str(root_age or "").strip()
        self.cores_label_text = str(cores_label or "Threads").strip() or "Threads"
        self.show_cores_control = bool(show_cores_control)
        self.show_model_selector = bool(show_model_selector)
        self.show_test_j_models = bool(show_test_j_models)

        if config is not None and list(getattr(config, "area_names", []) or []) == self.area_names:
            self._config = config
            self._config.taxon_ranges = list(self.taxon_ranges)
            if self.root_age and not str(getattr(self._config, "root_age", "") or "").strip():
                self._config.root_age = self.root_age
        else:
            self._config = SBGBConfig.default_for_areas(self.area_names, self.taxon_ranges)
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
        except Exception as exc:
            QMessageBox.warning(self, "Invalid configuration", str(exc))
            return
        super().accept()

    def _build_ui(self):
        menu_bar = QMenuBar(self)
        operation_menu = menu_bar.addMenu("Operation")
        refresh_action = operation_menu.addAction("Refresh Range List")
        save_action = operation_menu.addAction("Save Setting")
        load_action = operation_menu.addAction("Load Setting")
        refresh_action.triggered.connect(self._refresh_ranges_from_matrix)
        save_action.triggered.connect(self._save_settings)
        load_action.triggered.connect(self._load_settings)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self._build_range_tab(), "Range constraints")
        self.tabs.addTab(self._build_time_tab(), "Time-Stratified")

        self.model_combo = QComboBox(self)
        for model in ["DEC", "DECJ", "DIVALIKE", "DIVALIKEJ", "BAYAREALIKE", "BAYAREALIKEJ"]:
            self.model_combo.addItem(SBGB_MODEL_DISPLAY[model], model)
        self.model_combo.setVisible(self.show_model_selector)

        self.test_j_models_check = QCheckBox("Test +J models", self)
        self.test_j_models_check.setChecked(True)
        self.test_j_models_check.setVisible(self.show_test_j_models)

        self.null_range_combo = QComboBox(self)
        for mode in ["include", "exclude"]:
            self.null_range_combo.addItem(SBGB_NULL_RANGE_MODE_DISPLAY[mode], mode)

        self.cores_spin = QSpinBox(self)
        self.cores_spin.setMinimum(1)
        self.cores_spin.setMaximum(256)
        self.cores_label = QLabel(self.cores_label_text, self)
        self.cores_label.setVisible(self.show_cores_control)
        self.cores_spin.setVisible(self.show_cores_control)

        self.reset_button = QPushButton("Reset", self)
        self.ok_button = QPushButton("OK", self)
        self.cancel_button = QPushButton("Cancel", self)
        self.reset_button.clicked.connect(self._reset_config)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

        bottom = QHBoxLayout()
        bottom.addWidget(self.model_combo)
        bottom.addWidget(self.test_j_models_check)
        bottom.addWidget(QLabel("Null range:", self))
        bottom.addWidget(self.null_range_combo)
        bottom.addStretch(1)
        bottom.addWidget(self.cores_label)
        bottom.addWidget(self.cores_spin)
        bottom.addWidget(self.reset_button)
        bottom.addWidget(self.ok_button)
        bottom.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.setMenuBar(menu_bar)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(bottom)

    def _build_range_tab(self):
        page = QWidget(self)
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        self.range_table = QTableWidget(page)
        self.range_table.setRowCount(len(self.area_names))
        self.range_table.setColumnCount(len(self.area_names))
        self.range_table.setHorizontalHeaderLabels(self.area_names)
        self.range_table.setVerticalHeaderLabels(self.area_names)
        self.range_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.range_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.range_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.range_table.itemChanged.connect(self._on_range_matrix_changed)

        right = QWidget(page)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)

        header = QHBoxLayout()
        header.addWidget(QLabel("Include", right))
        self.to_exclude_button = QPushButton(">>", right)
        self.to_include_button = QPushButton("<<", right)
        header.addWidget(self.to_exclude_button)
        header.addWidget(self.to_include_button)
        header.addWidget(QLabel("Exclude", right))

        lists = QHBoxLayout()
        self.include_list = QListWidget(right)
        self.exclude_list = QListWidget(right)
        lists.addWidget(self.include_list)
        lists.addWidget(self.exclude_list)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Max areas:", right))
        self.max_areas_spin = QSpinBox(right)
        min_areas = max([1] + [len(x) for x in self.taxon_ranges])
        self.max_areas_spin.setMinimum(min_areas)
        self.max_areas_spin.setMaximum(max(min_areas, len(self.area_names)))
        self.max_areas_spin.valueChanged.connect(self._refresh_ranges_from_matrix)
        controls.addWidget(self.max_areas_spin)
        controls.addStretch(1)

        self.to_exclude_button.clicked.connect(self._move_selected_to_exclude)
        self.to_include_button.clicked.connect(self._move_selected_to_include)

        right_layout.addLayout(header)
        right_layout.addLayout(lists, 1)
        right_layout.addLayout(controls)

        layout.addWidget(self.range_table, 2)
        layout.addWidget(right, 1)
        return page

    def _build_time_tab(self):
        page = QWidget(self)
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        left = QWidget(page)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.time_matrix_table = QTableWidget(left)
        self.time_matrix_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.time_matrix_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        left_buttons = QHBoxLayout()
        self.export_period_button = QPushButton("Export", left)
        self.import_period_button = QPushButton("Import", left)
        self.save_apply_button = QPushButton("Save && Apply", left)
        self.export_period_button.clicked.connect(self._export_period_file)
        self.import_period_button.clicked.connect(self._import_period_file)
        self.save_apply_button.clicked.connect(self._save_apply_time_matrix)
        left_buttons.addWidget(self.export_period_button)
        left_buttons.addWidget(self.import_period_button)
        left_buttons.addStretch(1)
        left_buttons.addWidget(self.save_apply_button)

        left_layout.addWidget(self.time_matrix_table, 1)
        left_layout.addLayout(left_buttons)

        right = QWidget(page)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)

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

        self.time_matrix_kind_combo = QComboBox(right)
        self.time_matrix_kind_combo.addItem("dispersal multipliers", "dispersal_multipliers")
        self.time_matrix_kind_combo.addItem("areas allowed", "areas_allowed")
        self.time_matrix_kind_combo.addItem("areas adjacency", "areas_adjacency")
        self.time_matrix_kind_combo.addItem("distances", "distances")

        right_layout.addLayout(root_row)
        right_layout.addLayout(period_buttons)
        right_layout.addWidget(self.period_table, 1)
        right_layout.addWidget(self.time_matrix_kind_combo)

        layout.addWidget(left, 4)
        layout.addWidget(right, 1)
        return page

    def _load_config(self, config):
        self._building = True
        self.cores_spin.setValue(1 if not self.show_cores_control else max(1, int(config.cores)))
        self.test_j_models_check.setChecked(bool(getattr(config, "test_j_models", True)))
        model_name = normalize_sbgb_model_name(config.model_name)
        model_index = self.model_combo.findData(model_name)
        if model_index >= 0:
            self.model_combo.setCurrentIndex(model_index)
        null_mode = normalize_sbgb_null_range_mode(
            getattr(config, "null_range_mode", ""),
            getattr(config, "include_null_range", True),
        )
        null_index = self.null_range_combo.findData(null_mode)
        if null_index >= 0:
            self.null_range_combo.setCurrentIndex(null_index)
        self.max_areas_spin.setValue(max(self.max_areas_spin.minimum(), min(int(config.max_areas), self.max_areas_spin.maximum())))
        self._load_range_matrix(config.range_matrix)
        self._populate_list(self.include_list, config.include_ranges)
        self._populate_list(self.exclude_list, config.exclude_ranges)
        self.root_age_edit.setText(str(config.root_age or ""))
        self._load_period_table(config.period_times)
        self._load_time_matrix_table(config.period_matrices, config.period_times)
        kind_index = self.time_matrix_kind_combo.findData(config.time_matrix_kind)
        if kind_index >= 0:
            self.time_matrix_kind_combo.setCurrentIndex(kind_index)
        self._building = False

    def _reset_config(self):
        config = SBGBConfig.default_for_areas(self.area_names, self.taxon_ranges)
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

    def _load_range_matrix(self, matrix):
        self.range_table.blockSignals(True)
        for row in range(len(self.area_names)):
            for col in range(len(self.area_names)):
                item = QTableWidgetItem("")
                if row < col:
                    checked = False
                    if row < len(matrix or []) and col < len(matrix[row] or []):
                        checked = bool(matrix[row][col])
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                else:
                    item.setFlags(Qt.NoItemFlags)
                    item.setBackground(QColor("#d8d8d8"))
                self.range_table.setItem(row, col, item)
        self.range_table.blockSignals(False)

    def _on_range_matrix_changed(self, _item):
        if not self._building:
            self._refresh_ranges_from_matrix()

    def _refresh_ranges_from_matrix(self):
        if self._building:
            return
        config = self._collect_range_config()
        include_ranges, exclude_ranges = config.build_range_lists()
        self._populate_list(self.include_list, include_ranges)
        self._populate_list(self.exclude_list, exclude_ranges)

    def _move_selected_to_exclude(self):
        self._move_selected(self.include_list, self.exclude_list)

    def _move_selected_to_include(self):
        self._move_selected(self.exclude_list, self.include_list)

    def _move_selected(self, source, target):
        row = source.currentRow()
        if row < 0:
            return
        item = source.takeItem(row)
        if item is not None:
            target.addItem(item.text())
            target.sortItems()

    def _collect_range_matrix(self):
        matrix = []
        for row in range(len(self.area_names)):
            matrix_row = []
            for col in range(len(self.area_names)):
                item = self.range_table.item(row, col)
                matrix_row.append(bool(item and item.checkState() == Qt.Checked))
            matrix.append(matrix_row)
        return matrix

    def _collect_range_config(self):
        return SBGBConfig(
            area_names=list(self.area_names),
            range_matrix=self._collect_range_matrix(),
            include_ranges=self._list_values(self.include_list),
            exclude_ranges=self._list_values(self.exclude_list),
            taxon_ranges=list(self.taxon_ranges),
            max_areas=self.max_areas_spin.value(),
            min_max_areas=self.max_areas_spin.minimum(),
            cores=self._selected_cores(),
            model_name=self.model_combo.currentData() or "DEC",
            test_j_models=self.test_j_models_check.isChecked(),
            include_null_range=(self.null_range_combo.currentData() or "include") == "include",
            null_range_mode=self.null_range_combo.currentData() or "include",
        )

    def _load_period_table(self, times):
        values = [float(x) for x in list(times or [0.0])]
        if not values:
            values = [0.0]
        self.period_table.setRowCount(len(values))
        for row, value in enumerate(values):
            self.period_table.setVerticalHeaderItem(row, QTableWidgetItem(str(row)))
            item = QTableWidgetItem(self._format_number(value))
            if row == 0:
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setBackground(QColor("#d8d8d8"))
            self.period_table.setItem(row, 0, item)

    def _load_time_matrix_table(self, matrices, times):
        period_count = max(1, len(list(times or [])) - 1)
        if period_count <= 0:
            period_count = max(1, len(list(matrices or [])))
        n = len(self.area_names)
        self.time_matrix_table.setColumnCount(n)
        self.time_matrix_table.setHorizontalHeaderLabels(self.area_names)
        self.time_matrix_table.setRowCount(period_count * n)

        for period in range(period_count):
            matrix = matrices[period] if period < len(matrices or []) else None
            for area_row, area in enumerate(self.area_names):
                row = period * n + area_row
                self.time_matrix_table.setVerticalHeaderItem(row, QTableWidgetItem("%s-%s %s" % (period, period + 1, area)))
                for col in range(n):
                    value = 1.0
                    if matrix is not None and area_row < len(matrix) and col < len(matrix[area_row]):
                        value = matrix[area_row][col]
                    self.time_matrix_table.setItem(row, col, QTableWidgetItem(self._format_number(value)))

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

    def _collect_period_matrices(self):
        n = len(self.area_names)
        if n <= 0:
            return []
        period_count = max(1, self.time_matrix_table.rowCount() // n)
        matrices = []
        for period in range(period_count):
            matrix = []
            for area_row in range(n):
                row_values = []
                for col in range(n):
                    item = self.time_matrix_table.item(period * n + area_row, col)
                    text = item.text().strip() if item is not None else "1"
                    row_values.append(float(text or "1"))
                matrix.append(row_values)
            matrices.append(matrix)
        return matrices

    def _add_period_time(self):
        times = self._collect_period_times()
        next_value = (times[-1] if times else 0.0) + 1.0
        times.append(next_value)
        matrices = self._collect_period_matrices()
        matrices.append(SBGBConfig._default_matrix(len(self.area_names)))
        self._load_period_table(times)
        self._load_time_matrix_table(matrices, times)

    def _remove_period_time(self):
        row = self.period_table.currentRow()
        if row <= 0:
            return
        times = self._collect_period_times()
        if row < len(times):
            del times[row]
        matrices = self._collect_period_matrices()
        period_count = max(1, len(times) - 1)
        matrices = matrices[:period_count]
        self._load_period_table(times)
        self._load_time_matrix_table(matrices, times)

    def _save_apply_time_matrix(self):
        try:
            self._collect_period_times()
            self._collect_period_matrices()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid time-stratified matrix", str(exc))
            return

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
        self._load_time_matrix_table(matrices, times)

    def _export_period_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export time periods", "", "Text files (*.txt);;All files (*)")
        if not path:
            return
        text = self._format_period_file(self._collect_period_matrices(), self._collect_period_times())
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
            parts = stripped.replace(",", " ").split()
            if len(parts) == len(self.area_names) and all(part in self.area_names for part in parts):
                continue
            rows.append([float(x) for x in parts])

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
            matrices = [SBGBConfig._default_matrix(n)]
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

    def _collect_config(self):
        range_config = self._collect_range_config()
        return SBGBConfig(
            area_names=list(self.area_names),
            range_matrix=range_config.range_matrix,
            include_ranges=range_config.include_ranges,
            exclude_ranges=range_config.exclude_ranges,
            taxon_ranges=list(self.taxon_ranges),
            max_areas=range_config.max_areas,
            min_max_areas=self.max_areas_spin.minimum(),
            cores=self._selected_cores(),
            model_name=self.model_combo.currentData() or "DEC",
            test_j_models=self.test_j_models_check.isChecked(),
            include_null_range=(self.null_range_combo.currentData() or "include") == "include",
            null_range_mode=self.null_range_combo.currentData() or "include",
            root_age=self.root_age_edit.text().strip(),
            period_times=self._collect_period_times(),
            time_matrix_kind=self.time_matrix_kind_combo.currentData() or "dispersal_multipliers",
            period_matrices=self._collect_period_matrices(),
        )

    def _selected_cores(self):
        if not self.show_cores_control:
            return 1
        return self.cores_spin.value()

    def _save_settings(self):
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Save BioGeoBEARS Setting",
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
            "Load BioGeoBEARS Setting",
            "",
            "JSON files (*.json);;Text files (*.txt);;All files (*)",
        )
        if not path:
            return
        try:
            text = open(path, "r", encoding="utf-8", errors="ignore").read()
            base_config = self._collect_config()
            if not str(text or "").lstrip().startswith("{"):
                raise ValueError("Only JSON BioGeoBEARS setting files are supported by this version.")
            config = SBGBConfig.from_preset_json_text(
                text,
                area_names=self.area_names,
                taxon_ranges=list(self.taxon_ranges),
                base_config=base_config,
            )
            if not self.show_cores_control:
                config.cores = 1
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

    def _format_number(self, value):
        try:
            number = float(value)
        except Exception:
            return str(value)
        if number.is_integer():
            return str(int(number))
        return "%g" % number
