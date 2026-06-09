from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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

from domain.models.sdiva_config import SDivaConfig


class SDivaConfigDialog(QDialog):
    def __init__(
        self,
        area_names,
        config=None,
        fossil_count=0,
        fossil_nodes=None,
        final_tree_available=True,
        parent=None,
        title="S-DIVA 配置",
        show_final_tree=True,
        show_threads=True,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 620)

        self.area_names = [str(x).strip() for x in list(area_names or []) if str(x).strip()]
        self.fossil_nodes = list(fossil_nodes or [])
        self.fossil_count = len(self.fossil_nodes) if self.fossil_nodes else max(0, int(fossil_count or 0))
        self.final_tree_available = bool(final_tree_available)
        self.show_final_tree = bool(show_final_tree)
        self.show_threads = bool(show_threads)
        if config is not None and list(getattr(config, "area_names", []) or []) == self.area_names:
            self._config = config
        else:
            self._config = SDivaConfig.default_for_areas(self.area_names)

        self._building = False
        self._build_ui()
        self._load_config(self._config)

    def config(self):
        return self._config

    def accept(self):
        try:
            self._config = self._collect_config()
        except Exception as exc:
            QMessageBox.warning(self, "閰嶇疆鏃犳晥", str(exc))
            return
        super().accept()

    def _build_ui(self):
        menu_bar = QMenuBar(self)
        operation_menu = menu_bar.addMenu("Operation")
        refresh_action = operation_menu.addAction("Refresh the Range List")
        save_action = operation_menu.addAction("Save Setting")
        load_action = operation_menu.addAction("Load Setting")
        refresh_action.triggered.connect(self._refresh_ranges_from_matrix)
        save_action.triggered.connect(self._save_settings)
        load_action.triggered.connect(self._load_settings)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_range_tab(), "Range constraints")
        self.tabs.addTab(self._build_optimize_tab(), "Optimize")
        self.tabs.addTab(self._build_fossil_tab(), "Fossils")

        self.spin_threads = QSpinBox()
        self.spin_threads.setMinimum(1)
        self.spin_threads.setMaximum(1024)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.button(QDialogButtonBox.Ok).setText("纭畾")
        self.button_box.button(QDialogButtonBox.Cancel).setText("鍙栨秷")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.setMenuBar(menu_bar)
        layout.addWidget(self.tabs)
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)
        self.threads_label = QLabel("Threads:")
        bottom_layout.addWidget(self.threads_label)
        bottom_layout.addWidget(self.spin_threads)
        self.threads_label.setVisible(self.show_threads)
        self.spin_threads.setVisible(self.show_threads)
        bottom_layout.addWidget(self.button_box)
        layout.addLayout(bottom_layout)
        self.setLayout(layout)

    def _build_range_tab(self):
        page = QWidget()
        layout = QVBoxLayout()

        self.range_table = QTableWidget()
        self.range_table.setRowCount(len(self.area_names))
        self.range_table.setColumnCount(len(self.area_names))
        self.range_table.setHorizontalHeaderLabels(self.area_names)
        self.range_table.setVerticalHeaderLabels(self.area_names)
        self.range_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.range_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.range_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.range_table.itemChanged.connect(self._on_range_matrix_changed)

        self.include_list = QListWidget()
        self.exclude_list = QListWidget()

        include_box = QGroupBox("Include")
        include_layout = QVBoxLayout()
        include_layout.addWidget(self.include_list)
        include_box.setLayout(include_layout)

        exclude_box = QGroupBox("Exclude")
        exclude_layout = QVBoxLayout()
        exclude_layout.addWidget(self.exclude_list)
        exclude_box.setLayout(exclude_layout)

        self.exclude_button = QPushButton("Exclude >>")
        self.include_button = QPushButton("<< Include")
        self.refresh_ranges_button = QPushButton("Refresh")
        self.exclude_button.clicked.connect(self._move_selected_to_exclude)
        self.include_button.clicked.connect(self._move_selected_to_include)
        self.refresh_ranges_button.clicked.connect(self._refresh_ranges_from_matrix)

        button_column = QVBoxLayout()
        button_column.addStretch(1)
        button_column.addWidget(self.exclude_button)
        button_column.addWidget(self.include_button)
        button_column.addSpacing(16)
        button_column.addWidget(self.refresh_ranges_button)
        button_column.addStretch(1)

        list_panel = QWidget()
        list_layout = QHBoxLayout()
        list_layout.addWidget(include_box)
        list_layout.addLayout(button_column)
        list_layout.addWidget(exclude_box)
        list_panel.setLayout(list_layout)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.range_table)
        splitter.addWidget(list_panel)
        splitter.setSizes([320, 220])

        layout.addWidget(QLabel("Range matrix constraints: edit the upper triangle; gray cells are inactive."))
        layout.addWidget(splitter)
        page.setLayout(layout)
        return page

    def _build_optimize_tab(self):
        page = QWidget()
        layout = QVBoxLayout()

        optimize_box = QGroupBox("Optimize")
        form = QFormLayout()

        self.check_max_areas = QCheckBox("Max areas at each node")
        self.spin_max_areas = QSpinBox()
        self.spin_max_areas.setMinimum(2)
        self.spin_max_areas.setMaximum(15)
        self.spin_max_areas.valueChanged.connect(self._refresh_ranges_from_matrix)
        self.check_max_areas.toggled.connect(self.spin_max_areas.setEnabled)

        self.check_extinction = QCheckBox("Allow Extinction (Slow)")
        self.check_reconstruction = QCheckBox("Allow Reconstruction (Slow)")
        self.check_use_final_tree = QCheckBox("Use Final tree")
        self.check_use_final_tree.setVisible(self.show_final_tree)

        self.spin_max_reconstructions = QSpinBox()
        self.spin_max_reconstructions.setMinimum(1)
        self.spin_max_reconstructions.setMaximum(10 ** 9)

        self.check_random_step = QCheckBox("Random Step")
        self.spin_random_step = QSpinBox()
        self.spin_random_step.setMinimum(1)
        self.spin_random_step.setMaximum(10 ** 9)
        self.check_random_step.toggled.connect(self.spin_random_step.setEnabled)

        self.check_final_tree_max = QCheckBox("Max Reconstructions for final tree")
        self.spin_final_tree_max = QSpinBox()
        self.spin_final_tree_max.setMinimum(1)
        self.spin_final_tree_max.setMaximum(10 ** 9)
        self.check_final_tree_max.toggled.connect(self.spin_final_tree_max.setEnabled)

        self.check_keep = QCheckBox("keep")
        self.spin_keep = QSpinBox()
        self.spin_keep.setMinimum(1)
        self.spin_keep.setMaximum(2 ** 31 - 1)
        self.check_keep.toggled.connect(self.spin_keep.setEnabled)
        self.check_keep.setVisible(False)
        self.spin_keep.setVisible(False)

        self.check_reconstruction.toggled.connect(self._sync_reconstruction_controls)

        form.addRow(self.check_max_areas, self.spin_max_areas)
        form.addRow(self.check_extinction)
        form.addRow(self.check_reconstruction)
        form.addRow(self.check_use_final_tree)
        form.addRow("Max reconstructions", self.spin_max_reconstructions)
        form.addRow(self.check_random_step, self.spin_random_step)
        form.addRow(self.check_final_tree_max, self.spin_final_tree_max)
        form.addRow(self.check_keep, self.spin_keep)

        optimize_box.setLayout(form)
        layout.addWidget(optimize_box)
        layout.addStretch(1)
        page.setLayout(layout)
        return page

    def _build_fossil_tab(self):
        page = QWidget()
        layout = QVBoxLayout()

        self.fossil_table = QTableWidget()
        self.fossil_table.setColumnCount(3)
        self.fossil_table.setHorizontalHeaderLabels(["Node ID", "Member", "Fossil"])
        self.fossil_table.setRowCount(self.fossil_count)
        self.fossil_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.fossil_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        for row in range(self.fossil_count):
            node_info = self.fossil_nodes[row] if row < len(self.fossil_nodes) else {}
            if isinstance(node_info, dict):
                node_id = str(node_info.get("node_id", "Node %s" % (row + 1)))
                member = str(node_info.get("member", ""))
            else:
                node_id = "Node %s" % (row + 1)
                member = ""
            self.fossil_table.setVerticalHeaderItem(row, QTableWidgetItem(str(row + 1)))
            self.fossil_table.setItem(row, 0, QTableWidgetItem(node_id))
            self.fossil_table.setItem(row, 1, QTableWidgetItem(member))
            self.fossil_table.setItem(row, 2, QTableWidgetItem(""))
            self.fossil_table.item(row, 0).setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.fossil_table.item(row, 1).setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

        layout.addWidget(QLabel("Fossil values are written to the final-tree DIVA run in legacy node order; blanks are exported as 0."))
        layout.addWidget(self.fossil_table)
        page.setLayout(layout)
        return page

    def _load_config(self, config):
        self._building = True
        self._load_range_matrix(config.range_matrix)
        self._populate_list(self.include_list, config.include_ranges)
        self._populate_list(self.exclude_list, config.exclude_ranges)

        self.check_max_areas.setChecked(bool(config.max_areas_enabled))
        self.spin_max_areas.setValue(max(self.spin_max_areas.minimum(), min(int(config.max_areas), self.spin_max_areas.maximum())))
        self.check_extinction.setChecked(bool(config.allow_extinction or config.has_fossils() or config.runtime_exclude_ranges()))
        self.check_reconstruction.setChecked(bool(config.allow_reconstruction))
        self.check_use_final_tree.setChecked(bool(
            self.show_final_tree
            and getattr(config, "use_final_tree", False)
            and self.final_tree_available
        ))
        self.check_use_final_tree.setEnabled(self.show_final_tree and self.final_tree_available)
        self.spin_max_reconstructions.setValue(max(1, int(config.max_reconstructions)))
        self.check_random_step.setChecked(bool(config.random_step_enabled))
        self.spin_random_step.setValue(max(1, int(config.random_step)))
        self.check_final_tree_max.setChecked(bool(config.final_tree_max_enabled))
        self.spin_final_tree_max.setValue(max(1, int(config.max_reconstructions_for_final_tree)))
        self.check_keep.setChecked(bool(getattr(config, "keep_enabled", True)))
        self.spin_keep.setValue(max(1, int(getattr(config, "keep_value", 65536) or 65536)))
        self.spin_threads.setValue(max(1, min(1024, int(getattr(config, "threads", 1) or 1))))

        fossil_values = list(config.fossil_values or [])
        for row in range(self.fossil_table.rowCount()):
            text = fossil_values[row] if row < len(fossil_values) else ""
            self.fossil_table.setItem(row, 2, QTableWidgetItem(str(text)))

        self._building = False
        self._sync_reconstruction_controls()
        self.spin_max_areas.setEnabled(self.check_max_areas.isChecked())
        self.spin_random_step.setEnabled(self.check_random_step.isChecked() and self.check_reconstruction.isChecked())
        self.spin_final_tree_max.setEnabled(self.check_final_tree_max.isChecked() and self.check_reconstruction.isChecked())
        self.spin_keep.setEnabled(self.check_keep.isChecked())

    def _load_range_matrix(self, matrix):
        self.range_table.blockSignals(True)
        for row, _row_name in enumerate(self.area_names):
            for col, _col_name in enumerate(self.area_names):
                item = QTableWidgetItem("")
                if row < col:
                    checked = False
                    if row < len(matrix) and col < len(matrix[row]):
                        checked = bool(matrix[row][col])
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                else:
                    item.setFlags(Qt.NoItemFlags)
                    item.setBackground(QColor("#e6e6e6"))
                self.range_table.setItem(row, col, item)
        self.range_table.blockSignals(False)

    def _sync_reconstruction_controls(self):
        enabled = self.check_reconstruction.isChecked()
        self.spin_max_reconstructions.setEnabled(enabled)
        self.check_random_step.setEnabled(enabled)
        self.check_final_tree_max.setEnabled(enabled)
        self.spin_random_step.setEnabled(enabled and self.check_random_step.isChecked())
        self.spin_final_tree_max.setEnabled(enabled and self.check_final_tree_max.isChecked())

    def _on_range_matrix_changed(self, _item):
        if self._building:
            return
        self._refresh_ranges_from_matrix()

    def _refresh_ranges_from_matrix(self):
        if self._building:
            return
        config = self._collect_config(refresh_lists=False)
        include_ranges, exclude_ranges = config.build_range_lists()
        self._populate_list(self.include_list, include_ranges)
        self._populate_list(self.exclude_list, exclude_ranges)
        self._sync_extinction_from_ranges()

    def _move_selected_to_exclude(self):
        self._move_selected(self.include_list, self.exclude_list)
        self._sync_extinction_from_ranges()

    def _move_selected_to_include(self):
        self._move_selected(self.exclude_list, self.include_list)
        self._sync_extinction_from_ranges()

    def _move_selected(self, source, target):
        row = source.currentRow()
        if row < 0:
            return
        item = source.takeItem(row)
        if item is not None:
            target.addItem(item.text())

    def _collect_config(self, refresh_lists=True):
        matrix = []
        for row in range(len(self.area_names)):
            matrix_row = []
            for col in range(len(self.area_names)):
                item = self.range_table.item(row, col)
                matrix_row.append(bool(item and item.checkState() == Qt.Checked))
            matrix.append(matrix_row)

        config = SDivaConfig(
            area_names=list(self.area_names),
            range_matrix=matrix,
            include_ranges=self._list_values(self.include_list),
            exclude_ranges=self._list_values(self.exclude_list),
            fossil_values=self._fossil_values(),
            fossil_node_signature=self._fossil_node_signature(),
            use_final_tree=(
                self.show_final_tree
                and self.check_use_final_tree.isChecked()
                and self.check_use_final_tree.isEnabled()
            ),
            max_areas_enabled=self.check_max_areas.isChecked(),
            max_areas=self.spin_max_areas.value(),
            allow_extinction=(
                self.check_extinction.isChecked()
                or any(self._fossil_values())
                or bool(self._list_values(self.exclude_list))
            ),
            allow_reconstruction=self.check_reconstruction.isChecked(),
            max_reconstructions=self.spin_max_reconstructions.value(),
            random_step_enabled=self.check_random_step.isChecked(),
            random_step=self.spin_random_step.value(),
            final_tree_max_enabled=self.check_final_tree_max.isChecked(),
            max_reconstructions_for_final_tree=self.spin_final_tree_max.value(),
            keep_enabled=self.check_keep.isChecked(),
            keep_value=self.spin_keep.value(),
            threads=self.spin_threads.value(),
        )

        if refresh_lists:
            config.include_ranges = self._list_values(self.include_list)
            config.exclude_ranges = self._list_values(self.exclude_list)

        return config

    def _populate_list(self, widget, values):
        widget.clear()
        for value in list(values or []):
            text = str(value).strip()
            if text:
                widget.addItem(text)

    def _list_values(self, widget):
        return [
            widget.item(i).text().strip()
            for i in range(widget.count())
            if widget.item(i).text().strip()
        ]

    def _fossil_values(self):
        values = []
        for row in range(self.fossil_table.rowCount()):
            item = self.fossil_table.item(row, 2)
            values.append(item.text().strip() if item is not None else "")
        return values

    def _fossil_node_signature(self):
        signature = []
        for row in range(self.fossil_table.rowCount()):
            node_item = self.fossil_table.item(row, 0)
            member_item = self.fossil_table.item(row, 1)
            node_id = node_item.text().strip() if node_item is not None else ""
            member = member_item.text().strip() if member_item is not None else ""
            signature.append("%s|%s" % (node_id, member))
        return signature

    def _sync_extinction_from_ranges(self):
        if getattr(self, "_building", False):
            return
        if self.exclude_list.count() > 0:
            self.check_extinction.setChecked(True)
        elif not any(self._fossil_values()):
            self.check_extinction.setChecked(False)

    def _save_settings(self):
        file_path, _selected = QFileDialog.getSaveFileName(
            self,
            "Save S-DIVA Setting",
            "",
            "S-DIVA setting (*.txt);;All files (*.*)",
        )
        if not file_path:
            return
        try:
            config = self._collect_config()
            with open(file_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(config.to_legacy_config_text(fossil_count=self.fossil_table.rowCount()))
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))

    def _load_settings(self):
        file_path, _selected = QFileDialog.getOpenFileName(
            self,
            "Load S-DIVA Setting",
            "",
            "S-DIVA setting (*.txt);;All files (*.*)",
        )
        if not file_path:
            return
        try:
            text = open(file_path, "r", encoding="utf-8", errors="ignore").read()
            config = self._config_from_legacy_text(text)
            self._config = config
            self._load_config(config)
        except Exception as exc:
            QMessageBox.warning(self, "Load failed", str(exc))

    def _config_from_legacy_text(self, text):
        sections = self._parse_legacy_sections(text)
        current = self._collect_config()
        n = len(self.area_names)

        matrix = [row[:] for row in current.range_matrix]
        matrix_values = self._split_legacy_values(sections.get("Range list", ""))
        if len(matrix_values) >= n * n:
            matrix = [[False for _col in range(n)] for _row in range(n)]
            for row in range(n):
                for col in range(n):
                    value = matrix_values[row * n + col]
                    matrix[row][col] = value.strip() == "1"

        optimize = self._split_legacy_values(sections.get("Optimize", ""))
        values = current.optimize_values()
        for index, value in enumerate(optimize[:len(values)]):
            values[index] = self._safe_int(value, values[index])

        include_ranges = self._split_legacy_values(sections.get("Include", ""))
        exclude_ranges = self._split_legacy_values(sections.get("Exclude", ""))
        fossil_values = self._split_legacy_values(sections.get("Fossils", ""), keep_empty=True)

        config = SDivaConfig(
            area_names=list(self.area_names),
            range_matrix=matrix,
            include_ranges=include_ranges,
            exclude_ranges=exclude_ranges,
            fossil_values=fossil_values,
            fossil_node_signature=self._fossil_node_signature(),
            use_final_tree=current.use_final_tree,
            max_areas_enabled=bool(values[0]),
            max_areas=max(2, values[1]),
            allow_extinction=bool(values[2] or exclude_ranges or any(fossil_values)),
            allow_reconstruction=bool(values[3]),
            max_reconstructions=max(1, values[4]),
            random_step_enabled=bool(values[5]),
            random_step=max(1, values[6]),
            final_tree_max_enabled=bool(values[7]),
            max_reconstructions_for_final_tree=max(1, values[8]),
            keep_enabled=current.keep_enabled,
            keep_value=current.keep_value,
            threads=current.threads,
        )
        if not config.include_ranges and not config.exclude_ranges:
            config.refresh_range_lists()
        return config

    def _parse_legacy_sections(self, text):
        sections = {}
        current = None
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if line.startswith("[") and line.endswith("]"):
                current = line[1:-1].strip()
                sections[current] = []
                continue
            if current is not None:
                sections[current].append(line)
        return {
            key: ",".join(value)
            for key, value in sections.items()
        }

    def _split_legacy_values(self, text, keep_empty=False):
        values = [value.strip() for value in str(text or "").split(",")]
        if values and values[-1] == "":
            values = values[:-1]
        if keep_empty:
            return values
        return [value for value in values if value]

    def _safe_int(self, value, default):
        try:
            return int(float(str(value).strip()))
        except Exception:
            return int(default)
