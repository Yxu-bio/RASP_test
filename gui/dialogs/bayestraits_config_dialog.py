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
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from domain.models.bayestraits_config import (
    BAYESTRAITS_ANALYSIS_METHODS,
    BAYESTRAITS_CONTINUOUS_TRANSFORMS,
    BAYESTRAITS_HYPER_PRIOR_ALL,
    BAYESTRAITS_MODELS,
    BAYESTRAITS_RESTRICT_ALL,
    BAYESTRAITS_REVJUMP_HP,
    BAYESTRAITS_STONES,
    BayesTraitsConfig,
    normalize_bayestraits_analysis_method,
    normalize_bayestraits_continuous_transform,
    normalize_bayestraits_model,
)


class BayesTraitsConfigDialog(QDialog):
    def __init__(self, trait_columns, node_records, config=None, tree_set_available=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BayesTraits")
        self.resize(900, 620)
        self.setMinimumSize(760, 520)
        self.setMaximumSize(1180, 820)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.trait_columns = [str(x).strip() for x in list(trait_columns or []) if str(x).strip()]
        self.node_records = list(node_records or [])
        self.tree_set_available = bool(tree_set_available)
        node_ids = [str(record.get("display_node_id", "")).strip() for record in self.node_records]
        node_ids = [node_id for node_id in node_ids if node_id]
        if config is not None and list(getattr(config, "trait_columns", []) or []) == self.trait_columns:
            self._config = config
        else:
            self._config = BayesTraitsConfig.default_for_columns(self.trait_columns, node_ids=node_ids)

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
        left_layout.addWidget(self._build_node_group(), 1)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)

        right_content = QWidget(right)
        right_content_layout = QVBoxLayout(right_content)
        right_content_layout.setContentsMargins(0, 0, 0, 0)
        right_content_layout.addWidget(self._build_model_group())
        right_content_layout.addWidget(self._build_mcmc_ml_group())
        right_content_layout.addWidget(self._build_prior_group())
        right_content_layout.addWidget(self._build_advanced_group())
        right_content_layout.addStretch(1)

        right_scroll = QScrollArea(right)
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QScrollArea.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setWidget(right_content)
        right_layout.addWidget(right_scroll, 1)

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

        layout.addWidget(left, 3)
        layout.addWidget(right, 2)

    def _build_node_group(self):
        group = QGroupBox("Node reconstruction / fossilisation", self)
        layout = QVBoxLayout(group)
        self.node_table = QTableWidget(group)
        self.node_table.setColumnCount(5)
        self.node_table.setHorizontalHeaderLabels(["Node", "Terminals", "Support", "Select", "Fossil"])
        self.node_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.node_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.node_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.node_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.node_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.node_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.node_table.verticalHeader().setDefaultSectionSize(22)
        self.node_table.setMinimumHeight(280)
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
            fossil_item = QTableWidgetItem("")
            for item in [node_item, terminals_item, support_item]:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.node_table.setItem(row, 0, node_item)
            self.node_table.setItem(row, 1, terminals_item)
            self.node_table.setItem(row, 2, support_item)
            self.node_table.setItem(row, 3, select_item)
            self.node_table.setItem(row, 4, fossil_item)

        layout.addWidget(self.node_table, 1)
        return group

    def _build_model_group(self):
        group = QGroupBox("Model", self)
        layout = QVBoxLayout(group)
        form = QFormLayout()
        self.model_combo = QComboBox(group)
        for key, spec in BAYESTRAITS_MODELS.items():
            self.model_combo.addItem(str(spec["label"]), key)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        self.analysis_combo = QComboBox(group)
        self.analysis_combo.addItem(BAYESTRAITS_ANALYSIS_METHODS["ML"], "ML")
        self.analysis_combo.addItem(BAYESTRAITS_ANALYSIS_METHODS["MCMC"], "MCMC")
        self.analysis_combo.currentIndexChanged.connect(self._update_controls)
        self.trait_column_combo = QComboBox(group)
        for column in self.trait_columns:
            self.trait_column_combo.addItem(column, column)
        self.trait_column_combo.currentIndexChanged.connect(self._on_primary_trait_changed)
        self.continuous_transform_combo = QComboBox(group)
        for key, label in BAYESTRAITS_CONTINUOUS_TRANSFORMS.items():
            self.continuous_transform_combo.addItem(label, key)
        self.continuous_transform_combo.currentIndexChanged.connect(self._on_continuous_transform_changed)
        form.addRow("Model", self.model_combo)
        form.addRow("Analysis", self.analysis_combo)
        form.addRow("Primary trait", self.trait_column_combo)
        form.addRow("Trait transform", self.continuous_transform_combo)
        layout.addLayout(form)

        self.continuous_asr_check = QCheckBox("Continuous ASR visualization (contMap-like)", group)
        self.continuous_asr_check.toggled.connect(self._update_controls)
        layout.addWidget(self.continuous_asr_check)

        self.trait_table = QTableWidget(group)
        self.trait_table.setColumnCount(2)
        self.trait_table.setHorizontalHeaderLabels(["Use", "Trait column"])
        self.trait_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.trait_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.trait_table.verticalHeader().setVisible(False)
        self.trait_table.setMaximumHeight(120)
        self.trait_table.setRowCount(len(self.trait_columns))
        for row, column in enumerate(self.trait_columns):
            use_item = QTableWidgetItem("")
            use_item.setFlags(use_item.flags() | Qt.ItemIsUserCheckable)
            use_item.setCheckState(Qt.Unchecked)
            column_item = QTableWidgetItem(column)
            column_item.setFlags(column_item.flags() & ~Qt.ItemIsEditable)
            self.trait_table.setItem(row, 0, use_item)
            self.trait_table.setItem(row, 1, column_item)
        self.trait_table.itemChanged.connect(self._on_trait_item_changed)
        layout.addWidget(self.trait_table)
        return group

    def _build_mcmc_ml_group(self):
        group = QGroupBox("MCMC && ML", self)
        form = QFormLayout(group)
        self.iterations_spin = QSpinBox(group)
        self.iterations_spin.setRange(1, 2147483647)
        self.iterations_spin.setSingleStep(1000)
        self.sample_spin = QSpinBox(group)
        self.sample_spin.setRange(1, 2147483647)
        self.sample_spin.setSingleStep(100)
        self.burnin_spin = QSpinBox(group)
        self.burnin_spin.setRange(0, 2147483647)
        self.burnin_spin.setSingleStep(1000)
        self.mltries_spin = QSpinBox(group)
        self.mltries_spin.setRange(1, 1000000)
        form.addRow("Iterations", self.iterations_spin)
        form.addRow("Sample", self.sample_spin)
        form.addRow("BurnIn", self.burnin_spin)
        form.addRow("MLTries", self.mltries_spin)
        return group

    def _build_prior_group(self):
        group = QGroupBox("MCMC priors", self)
        form = QFormLayout(group)
        self.hpall_combo = self._combo_from_values(BAYESTRAITS_HYPER_PRIOR_ALL, group)
        self.rjhp_combo = self._combo_from_values(BAYESTRAITS_REVJUMP_HP, group)
        self.resall_combo = self._combo_from_values(BAYESTRAITS_RESTRICT_ALL, group)
        self.stones_combo = self._combo_from_values(BAYESTRAITS_STONES, group)
        self.rjhp_combo.currentIndexChanged.connect(self._exclusive_rjhp_resall)
        self.resall_combo.currentIndexChanged.connect(self._exclusive_rjhp_resall)
        form.addRow("HPAll", self.hpall_combo)
        form.addRow("RJHP", self.rjhp_combo)
        form.addRow("ResAll", self.resall_combo)
        form.addRow("Stone", self.stones_combo)
        return group

    def _build_advanced_group(self):
        group = QGroupBox("Advanced", self)
        layout = QVBoxLayout(group)
        self.auto_map_check = QCheckBox("Auto-map categorical values to BayesTraits symbols", group)
        layout.addWidget(self.auto_map_check)

        layout.addWidget(QLabel("Other commands", group))
        self.extra_commands_edit = QTextEdit(group)
        self.extra_commands_edit.setAcceptRichText(False)
        self.extra_commands_edit.setPlaceholderText("Optional BayesTraits commands, one per line.")
        self.extra_commands_edit.setMaximumHeight(80)
        layout.addWidget(self.extra_commands_edit, 1)
        return group

    def _combo_from_values(self, values, parent):
        combo = QComboBox(parent)
        combo.setEditable(True)
        for value in values:
            combo.addItem(value, value)
        return combo

    def _load_config(self, config):
        self._set_combo_data(self.model_combo, normalize_bayestraits_model(getattr(config, "model", "MULTISTATE")))
        self._set_combo_data(self.analysis_combo, normalize_bayestraits_analysis_method(config.analysis_method))
        self._set_combo_data(self.trait_column_combo, str(config.trait_column or ""))
        self._set_selected_trait_columns(list(getattr(config, "selected_trait_columns", []) or [config.trait_column]))
        self.iterations_spin.setValue(int(config.iterations))
        self.sample_spin.setValue(int(config.sample_frequency))
        self.burnin_spin.setValue(int(config.burnin))
        self.mltries_spin.setValue(int(config.ml_tries))
        self.hpall_combo.setEditText(str(config.hyper_prior_all or ""))
        self.rjhp_combo.setEditText(str(config.revjump_hp or ""))
        self.resall_combo.setEditText(str(config.restrict_all or ""))
        self.stones_combo.setEditText(str(config.stones or ""))
        self.extra_commands_edit.setPlainText(str(config.extra_commands or ""))
        self.auto_map_check.setChecked(bool(config.auto_map_categorical))
        self.continuous_asr_check.setChecked(bool(getattr(config, "continuous_asr", False)))
        self._set_combo_data(
            self.continuous_transform_combo,
            normalize_bayestraits_continuous_transform(getattr(config, "continuous_transform", "none")),
        )
        self._set_selected_node_ids(list(config.selected_node_ids or []))
        self._set_fossil_states(dict(config.fossil_states or {}))
        self._update_controls()

    def _collect_config(self):
        return BayesTraitsConfig(
            trait_columns=list(self.trait_columns),
            trait_column=str(self.trait_column_combo.currentData() or self.trait_column_combo.currentText() or ""),
            model=str(self.model_combo.currentData() or "MULTISTATE"),
            selected_trait_columns=self._selected_trait_columns(),
            analysis_method=str(self.analysis_combo.currentData() or "ML"),
            ml_tries=int(self.mltries_spin.value()),
            iterations=int(self.iterations_spin.value()),
            sample_frequency=int(self.sample_spin.value()),
            burnin=int(self.burnin_spin.value()),
            hyper_prior_all=str(self.hpall_combo.currentText() or ""),
            revjump_hp=str(self.rjhp_combo.currentText() or ""),
            restrict_all=str(self.resall_combo.currentText() or ""),
            stones=str(self.stones_combo.currentText() or ""),
            extra_commands=self.extra_commands_edit.toPlainText(),
            auto_map_categorical=bool(self.auto_map_check.isChecked()),
            continuous_asr=bool(self.continuous_asr_check.isChecked()),
            continuous_transform=str(self.continuous_transform_combo.currentData() or "none"),
            selected_node_ids=self._selected_node_ids(),
            fossil_states=self._fossil_states(),
        )

    def _update_controls(self):
        if not hasattr(self, "trait_table"):
            return
        is_mcmc = str(self.analysis_combo.currentData()) == "MCMC"
        model = str(self.model_combo.currentData() or "MULTISTATE")
        spec = BAYESTRAITS_MODELS.get(model, BAYESTRAITS_MODELS["MULTISTATE"])
        supports_continuous_asr = bool(spec.get("supports_continuous_asr", False))
        if not supports_continuous_asr and self.continuous_asr_check.isChecked():
            self.continuous_asr_check.blockSignals(True)
            self.continuous_asr_check.setChecked(False)
            self.continuous_asr_check.blockSignals(False)
        continuous_asr = bool(self.continuous_asr_check.isChecked() and supports_continuous_asr)
        self.continuous_asr_check.setEnabled(supports_continuous_asr)
        forced_method = str(spec.get("analysis_method", "") or "")
        if continuous_asr:
            forced_method = "MCMC"
        if forced_method and self.analysis_combo.currentData() != forced_method:
            self._set_combo_data(self.analysis_combo, forced_method)
            is_mcmc = str(self.analysis_combo.currentData()) == "MCMC"
        self.analysis_combo.setEnabled(not bool(forced_method))
        self.iterations_spin.setEnabled(is_mcmc)
        self.sample_spin.setEnabled(is_mcmc)
        self.burnin_spin.setEnabled(is_mcmc)
        self.hpall_combo.setEnabled(is_mcmc)
        self.rjhp_combo.setEnabled(is_mcmc)
        self.resall_combo.setEnabled(is_mcmc)
        self.stones_combo.setEnabled(is_mcmc and not continuous_asr)
        self.mltries_spin.setEnabled(not is_mcmc)
        self.node_table.setEnabled(bool(spec.get("supports_nodes", False)) and not continuous_asr)
        self.auto_map_check.setEnabled(str(spec.get("trait_kind", "")) == "categorical")
        is_continuous = str(spec.get("trait_kind", "")) == "continuous"
        self.continuous_transform_combo.setEnabled(is_continuous)
        if not is_continuous:
            self._set_combo_data(self.continuous_transform_combo, "none")
        self._enforce_trait_selection_for_model()

    def _exclusive_rjhp_resall(self):
        sender = self.sender()
        if sender is self.rjhp_combo and self.rjhp_combo.currentText().strip():
            self.resall_combo.setCurrentIndex(0)
        elif sender is self.resall_combo and self.resall_combo.currentText().strip():
            self.rjhp_combo.setCurrentIndex(0)

    def _set_combo_data(self, combo, value):
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return
        if combo.isEditable():
            combo.setEditText(str(value or ""))

    def _on_model_changed(self):
        self._update_controls()

    def _on_continuous_transform_changed(self):
        self._update_controls()

    def _on_primary_trait_changed(self):
        primary = str(self.trait_column_combo.currentData() or self.trait_column_combo.currentText() or "").strip()
        if not primary:
            return
        self._update_controls()

    def _on_trait_item_changed(self, item):
        if item is None or item.column() != 0:
            return
        model = str(self.model_combo.currentData() or "MULTISTATE")
        spec = BAYESTRAITS_MODELS.get(model, BAYESTRAITS_MODELS["MULTISTATE"])
        max_traits = int(spec.get("max_traits", 0) or 0)
        if max_traits == 1 and item.checkState() == Qt.Checked:
            column_item = self.trait_table.item(item.row(), 1)
            if column_item is not None:
                self._set_combo_data(self.trait_column_combo, str(column_item.text()).strip())
        self._update_controls()

    def _selected_trait_columns(self):
        selected = []
        for row in range(self.trait_table.rowCount()):
            use_item = self.trait_table.item(row, 0)
            column_item = self.trait_table.item(row, 1)
            if use_item is None or column_item is None:
                continue
            if use_item.checkState() == Qt.Checked:
                selected.append(str(column_item.text()).strip())
        return [item for item in selected if item]

    def _set_selected_trait_columns(self, columns):
        selected = {str(x).strip() for x in list(columns or []) if str(x).strip()}
        if not selected:
            primary = str(self.trait_column_combo.currentData() or self.trait_column_combo.currentText() or "").strip()
            if primary:
                selected = {primary}
        self.trait_table.blockSignals(True)
        try:
            for row in range(self.trait_table.rowCount()):
                use_item = self.trait_table.item(row, 0)
                column_item = self.trait_table.item(row, 1)
                if use_item is None or column_item is None:
                    continue
                use_item.setCheckState(Qt.Checked if str(column_item.text()).strip() in selected else Qt.Unchecked)
        finally:
            self.trait_table.blockSignals(False)

    def _set_trait_checked(self, column, checked):
        column = str(column or "").strip()
        self.trait_table.blockSignals(True)
        try:
            for row in range(self.trait_table.rowCount()):
                column_item = self.trait_table.item(row, 1)
                use_item = self.trait_table.item(row, 0)
                if column_item is None or use_item is None:
                    continue
                if str(column_item.text()).strip() == column:
                    use_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                    break
        finally:
            self.trait_table.blockSignals(False)

    def _enforce_trait_selection_for_model(self):
        model = str(self.model_combo.currentData() or "MULTISTATE")
        spec = BAYESTRAITS_MODELS.get(model, BAYESTRAITS_MODELS["MULTISTATE"])
        max_traits = int(spec.get("max_traits", 0) or 0)
        primary = str(self.trait_column_combo.currentData() or self.trait_column_combo.currentText() or "").strip()
        selected = self._selected_trait_columns()
        if max_traits == 1:
            selected = [primary or (selected[0] if selected else "")]
        elif not selected and primary:
            selected = [primary]
        if max_traits > 0:
            selected = selected[:max_traits]
        selected = [item for item in selected if item]
        self._set_selected_trait_columns(selected)

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
        self.node_table.blockSignals(True)
        try:
            for row in range(self.node_table.rowCount()):
                node_item = self.node_table.item(row, 0)
                select_item = self.node_table.item(row, 3)
                if node_item is None or select_item is None:
                    continue
                select_item.setCheckState(Qt.Checked if str(node_item.text()).strip() in selected else Qt.Unchecked)
        finally:
            self.node_table.blockSignals(False)

    def _fossil_states(self):
        states = {}
        for row in range(self.node_table.rowCount()):
            node_item = self.node_table.item(row, 0)
            fossil_item = self.node_table.item(row, 4)
            if node_item is None or fossil_item is None:
                continue
            node_id = str(node_item.text()).strip()
            value = str(fossil_item.text() or "").strip()
            if node_id and value:
                states[node_id] = value
        return states

    def _set_fossil_states(self, fossil_states):
        fossils = dict(fossil_states or {})
        for row in range(self.node_table.rowCount()):
            node_item = self.node_table.item(row, 0)
            fossil_item = self.node_table.item(row, 4)
            if node_item is None or fossil_item is None:
                continue
            node_id = str(node_item.text()).strip()
            fossil_item.setText(str(fossils.get(node_id, "") or ""))

    def _save_settings(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save BayesTraits setting",
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
            "Load BayesTraits setting",
            "",
            "JSON files (*.json);;All files (*.*)",
        )
        if not path:
            return
        try:
            text = open(path, "r", encoding="utf-8", errors="ignore").read()
            config = BayesTraitsConfig.from_preset_json_text(
                text,
                trait_columns=self.trait_columns,
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
        config = BayesTraitsConfig.default_for_columns(
            self.trait_columns,
            node_ids=[
                str(record.get("display_node_id", "")).strip()
                for record in self.node_records
            ],
        )
        self._config = config
        self._load_config(config)
