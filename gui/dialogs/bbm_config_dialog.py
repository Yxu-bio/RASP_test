from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QDoubleSpinBox,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.models.bbm_config import (
    BBMConfig,
    BBM_RATE_VARIATION_MODELS,
    BBM_ROOT_DISTRIBUTIONS,
    BBM_STATE_FREQUENCY_MODELS,
    normalize_bbm_rate_variation_model,
    normalize_bbm_root_distribution,
    normalize_bbm_state_frequency_model,
)


class BBMConfigDialog(QDialog):
    def __init__(self, area_names, node_records, config=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bayesian Analysis")
        self.resize(760, 500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.area_names = [str(x).strip() for x in list(area_names or []) if str(x).strip()]
        self.node_records = list(node_records or [])
        node_ids = [str(record.get("display_node_id", "")).strip() for record in self.node_records]
        node_ids = [node_id for node_id in node_ids if node_id]
        if config is not None and list(getattr(config, "area_names", []) or []) == self.area_names:
            self._config = config
        else:
            self._config = BBMConfig.default_for_areas(self.area_names, node_ids=node_ids)

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
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.addWidget(self._build_area_group())
        left_layout.addWidget(self._build_node_group(), 1)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.addWidget(self._build_mcmc_group())
        right_layout.addWidget(self._build_model_group())
        right_layout.addWidget(self._build_advanced_group())
        right_layout.addStretch(1)

        buttons = QHBoxLayout()
        self.save_setting_button = QPushButton("Save Setting", self)
        self.load_setting_button = QPushButton("Load Setting", self)
        self.reset_button = QPushButton("Reset", self)
        self.ok_button = QPushButton("OK", self)
        self.cancel_button = QPushButton("Cancel", self)
        self.save_setting_button.clicked.connect(self._save_settings)
        self.load_setting_button.clicked.connect(self._load_settings)
        self.reset_button.clicked.connect(self._reset_config)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.save_setting_button)
        buttons.addWidget(self.load_setting_button)
        buttons.addStretch(1)
        buttons.addWidget(self.reset_button)
        buttons.addWidget(self.ok_button)
        buttons.addWidget(self.cancel_button)
        right_layout.addLayout(buttons)

        layout.addWidget(left, 1)
        layout.addWidget(right, 1)

    def _build_area_group(self):
        group = QGroupBox("Area", self)
        form = QFormLayout(group)
        self.max_areas_spin = QSpinBox(group)
        self.max_areas_spin.setRange(1, max(1, len(self.area_names)))
        self.include_null_check = QCheckBox("Allow null distribution in analysis", group)
        form.addRow("Maximum number of areas", self.max_areas_spin)
        form.addRow("", self.include_null_check)
        return group

    def _build_node_group(self):
        group = QGroupBox("Node list", self)
        layout = QVBoxLayout(group)
        self.node_table = QTableWidget(group)
        self.node_table.setColumnCount(4)
        self.node_table.setHorizontalHeaderLabels(["Node", "Terminals", "Support", "Select"])
        self.node_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.node_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.node_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.node_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.node_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.node_table.setRowCount(len(self.node_records))
        for row, record in enumerate(self.node_records):
            node_id = str(record.get("display_node_id", ""))
            terminal_span = str(record.get("terminal_span", ""))
            support = float(record.get("support", 100.0) or 100.0)
            node_item = QTableWidgetItem(node_id)
            terminals_item = QTableWidgetItem(terminal_span)
            support_item = QTableWidgetItem("%.2f" % support)
            select_item = QTableWidgetItem("")
            select_item.setFlags(select_item.flags() | Qt.ItemIsUserCheckable)
            select_item.setCheckState(Qt.Checked)
            for item in [node_item, terminals_item, support_item]:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.node_table.setItem(row, 0, node_item)
            self.node_table.setItem(row, 1, terminals_item)
            self.node_table.setItem(row, 2, support_item)
            self.node_table.setItem(row, 3, select_item)

        buttons = QHBoxLayout()
        self.all_button = QPushButton("All", group)
        self.clear_button = QPushButton("Clear", group)
        self.select_button = QPushButton("Select", group)
        self.threshold_spin = QSpinBox(group)
        self.threshold_spin.setRange(0, 100)
        self.threshold_spin.setValue(90)
        self.all_button.clicked.connect(self._select_all_nodes)
        self.clear_button.clicked.connect(self._clear_nodes)
        self.select_button.clicked.connect(self._select_by_threshold)
        buttons.addWidget(self.all_button)
        buttons.addWidget(self.clear_button)
        buttons.addWidget(self.select_button)
        buttons.addWidget(QLabel(">=", group))
        buttons.addWidget(self.threshold_spin)
        buttons.addWidget(QLabel("%", group))
        buttons.addStretch(1)

        layout.addWidget(self.node_table, 1)
        layout.addLayout(buttons)
        return group

    def _build_mcmc_group(self):
        group = QGroupBox("Markov Chain Monte Carlo analysis", self)
        form = QFormLayout(group)
        self.chain_length_spin = QSpinBox(group)
        self.chain_length_spin.setRange(1, 2147483647)
        self.chain_length_spin.setSingleStep(1000)
        self.chains_spin = QSpinBox(group)
        self.chains_spin.setRange(1, 100000000)
        self.sample_frequency_spin = QSpinBox(group)
        self.sample_frequency_spin.setRange(1, 2147483647)
        self.sample_frequency_spin.setSingleStep(100)
        self.discard_samples_spin = QSpinBox(group)
        self.discard_samples_spin.setRange(0, 2147483647)
        self.discard_samples_spin.setSingleStep(10)
        self.temperature_spin = QDoubleSpinBox(group)
        self.temperature_spin.setRange(0.000001, 1000000.0)
        self.temperature_spin.setDecimals(6)
        self.temperature_spin.setSingleStep(0.1)
        form.addRow("Number of cycles", self.chain_length_spin)
        form.addRow("Number of chains", self.chains_spin)
        form.addRow("Frequent of samples", self.sample_frequency_spin)
        form.addRow("Discard samples", self.discard_samples_spin)
        form.addRow("Temperature", self.temperature_spin)
        return group

    def _build_model_group(self):
        group = QGroupBox("Model", self)
        form = QFormLayout(group)
        self.state_frequency_combo = QComboBox(group)
        for key in ["JC", "F81"]:
            self.state_frequency_combo.addItem(BBM_STATE_FREQUENCY_MODELS[key], key)
        self.state_frequency_combo.currentIndexChanged.connect(self._update_model_controls)
        self.dirichlet_alpha_spin = QDoubleSpinBox(group)
        self.dirichlet_alpha_spin.setRange(0.000001, 1000000.0)
        self.dirichlet_alpha_spin.setDecimals(6)
        self.dirichlet_beta_spin = QDoubleSpinBox(group)
        self.dirichlet_beta_spin.setRange(0.000001, 1000000.0)
        self.dirichlet_beta_spin.setDecimals(6)
        self.rate_variation_combo = QComboBox(group)
        for key in ["EQUAL", "GAMMA"]:
            self.rate_variation_combo.addItem(BBM_RATE_VARIATION_MODELS[key], key)
        self.rate_variation_combo.currentIndexChanged.connect(self._update_model_controls)
        self.gamma_min_spin = QDoubleSpinBox(group)
        self.gamma_min_spin.setRange(0.000001, 1000000.0)
        self.gamma_min_spin.setDecimals(6)
        self.gamma_max_spin = QDoubleSpinBox(group)
        self.gamma_max_spin.setRange(0.000001, 1000000.0)
        self.gamma_max_spin.setDecimals(6)
        form.addRow("State frequencies", self.state_frequency_combo)
        form.addRow("Dirichlet alpha", self.dirichlet_alpha_spin)
        form.addRow("Dirichlet beta", self.dirichlet_beta_spin)
        form.addRow("Among-site rate variation", self.rate_variation_combo)
        form.addRow("Gamma min", self.gamma_min_spin)
        form.addRow("Gamma max", self.gamma_max_spin)
        return group

    def _build_advanced_group(self):
        group = QGroupBox("Advanced", self)
        form = QFormLayout(group)
        self.root_distribution_combo = QComboBox(group)
        for key in ["NULL", "WIDE", "CUSTOM"]:
            self.root_distribution_combo.addItem(BBM_ROOT_DISTRIBUTIONS[key], key)
        self.root_distribution_combo.currentIndexChanged.connect(self._update_model_controls)
        self.custom_root_edit = QComboBox(group)
        self.custom_root_edit.setEditable(True)
        self.custom_root_edit.addItem("")
        for area in self.area_names:
            self.custom_root_edit.addItem(area)
        self.large_dataset_check = QCheckBox("Add OG0 outgroup", group)
        self.large_dataset_check.setToolTip(
            "Write one extra OG0 outgroup row in the MrBayes matrix."
        )
        form.addRow("Root distribution", self.root_distribution_combo)
        form.addRow("Custom distribution", self.custom_root_edit)
        form.addRow("", self.large_dataset_check)
        return group

    def _load_config(self, config):
        self.max_areas_spin.setValue(min(int(config.max_areas), max(1, len(self.area_names))))
        self.include_null_check.setChecked(bool(config.include_null_range))
        self.chain_length_spin.setValue(int(config.chain_length))
        self.chains_spin.setValue(int(config.chains))
        self.sample_frequency_spin.setValue(int(config.sample_frequency))
        self.discard_samples_spin.setValue(int(config.discard_samples))
        self.temperature_spin.setValue(float(config.temperature))
        self._set_combo_data(self.state_frequency_combo, normalize_bbm_state_frequency_model(config.state_frequency_model))
        self.dirichlet_alpha_spin.setValue(float(config.dirichlet_alpha))
        self.dirichlet_beta_spin.setValue(float(config.dirichlet_beta))
        self._set_combo_data(self.rate_variation_combo, normalize_bbm_rate_variation_model(config.rate_variation_model))
        self.gamma_min_spin.setValue(float(config.gamma_min))
        self.gamma_max_spin.setValue(float(config.gamma_max))
        self._set_combo_data(self.root_distribution_combo, normalize_bbm_root_distribution(config.root_distribution))
        self.custom_root_edit.setEditText(str(config.custom_root_distribution or ""))
        self.large_dataset_check.setChecked(bool(config.large_dataset_mode))
        self._set_selected_node_ids(list(config.selected_node_ids or []))
        self._update_model_controls()

    def _collect_config(self):
        return BBMConfig(
            area_names=list(self.area_names),
            max_areas=int(self.max_areas_spin.value()),
            include_null_range=bool(self.include_null_check.isChecked()),
            chain_length=int(self.chain_length_spin.value()),
            sample_frequency=int(self.sample_frequency_spin.value()),
            discard_samples=int(self.discard_samples_spin.value()),
            chains=int(self.chains_spin.value()),
            temperature=float(self.temperature_spin.value()),
            state_frequency_model=str(self.state_frequency_combo.currentData()),
            dirichlet_alpha=float(self.dirichlet_alpha_spin.value()),
            dirichlet_beta=float(self.dirichlet_beta_spin.value()),
            rate_variation_model=str(self.rate_variation_combo.currentData()),
            gamma_min=float(self.gamma_min_spin.value()),
            gamma_max=float(self.gamma_max_spin.value()),
            root_distribution=str(self.root_distribution_combo.currentData()),
            custom_root_distribution=str(self.custom_root_edit.currentText() or ""),
            large_dataset_mode=bool(self.large_dataset_check.isChecked()),
            selected_node_ids=self._selected_node_ids(),
        )

    def _set_combo_data(self, combo, value):
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _update_model_controls(self):
        f81 = str(self.state_frequency_combo.currentData()) == "F81"
        self.dirichlet_alpha_spin.setEnabled(f81)
        self.dirichlet_beta_spin.setEnabled(f81)
        gamma = str(self.rate_variation_combo.currentData()) == "GAMMA"
        self.gamma_min_spin.setEnabled(gamma)
        self.gamma_max_spin.setEnabled(gamma)
        custom = str(self.root_distribution_combo.currentData()) == "CUSTOM"
        self.custom_root_edit.setEnabled(custom)

    def _selected_node_ids(self):
        selected = []
        for row in range(self.node_table.rowCount()):
            node_item = self.node_table.item(row, 0)
            select_item = self.node_table.item(row, 3)
            if node_item is not None and select_item is not None and select_item.checkState() == Qt.Checked:
                selected.append(str(node_item.text()).strip())
        return selected

    def _set_selected_node_ids(self, node_ids):
        selected = {str(x).strip() for x in list(node_ids or []) if str(x).strip()}
        if not selected:
            selected = {
                str(self.node_table.item(row, 0).text()).strip()
                for row in range(self.node_table.rowCount())
                if self.node_table.item(row, 0) is not None
            }
        for row in range(self.node_table.rowCount()):
            node_item = self.node_table.item(row, 0)
            select_item = self.node_table.item(row, 3)
            if node_item is None or select_item is None:
                continue
            select_item.setCheckState(Qt.Checked if str(node_item.text()).strip() in selected else Qt.Unchecked)

    def _select_all_nodes(self):
        for row in range(self.node_table.rowCount()):
            item = self.node_table.item(row, 3)
            if item is not None:
                item.setCheckState(Qt.Checked)

    def _clear_nodes(self):
        for row in range(self.node_table.rowCount()):
            item = self.node_table.item(row, 3)
            if item is not None:
                item.setCheckState(Qt.Unchecked)

    def _select_by_threshold(self):
        threshold = float(self.threshold_spin.value())
        for row in range(self.node_table.rowCount()):
            support_item = self.node_table.item(row, 2)
            select_item = self.node_table.item(row, 3)
            if support_item is None or select_item is None:
                continue
            try:
                support = float(support_item.text())
            except Exception:
                support = 100.0
            select_item.setCheckState(Qt.Checked if support >= threshold else Qt.Unchecked)

    def _save_settings(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save BBM setting",
            "",
            "JSON files (*.json);;All files (*.*)",
        )
        if not path:
            return
        try:
            config = self._collect_config()
            open(path, "w", encoding="utf-8").write(config.to_preset_json_text())
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))

    def _load_settings(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load BBM setting",
            "",
            "JSON files (*.json);;All files (*.*)",
        )
        if not path:
            return
        try:
            text = open(path, "r", encoding="utf-8", errors="ignore").read()
            config = BBMConfig.from_preset_json_text(
                text,
                area_names=self.area_names,
                node_ids=[
                    str(record.get("display_node_id", "")).strip()
                    for record in self.node_records
                ],
                base_config=self._collect_config(),
            )
            self._config = config
            self._load_config(config)
        except Exception as exc:
            QMessageBox.warning(self, "Load failed", str(exc))

    def _reset_config(self):
        config = BBMConfig.default_for_areas(
            self.area_names,
            node_ids=[
                str(record.get("display_node_id", "")).strip()
                for record in self.node_records
            ],
        )
        self._config = config
        self._load_config(config)
