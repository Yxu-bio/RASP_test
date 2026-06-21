from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from domain.models.bayarea_config import (
    BAYAREA_MODEL_DISPLAY,
    BayAreaConfig,
    bayarea_recommended_parameters,
    normalize_bayarea_model_type,
)


class BayAreaConfigDialog(QDialog):
    def __init__(self, area_names, config=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BayArea")
        self.resize(760, 500)
        self.setMinimumSize(680, 440)
        self.setMaximumSize(980, 720)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._loading_config = False

        self.area_names = [str(x).strip() for x in list(area_names or []) if str(x).strip()]
        if config is not None and list(getattr(config, "area_names", []) or []) == self.area_names:
            self._config = config
        else:
            self._config = BayAreaConfig.default_for_areas(self.area_names)

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
        if not self._confirm_independence_rate_tuner(self._config):
            return
        if not self._confirm_distance_coordinates(self._config):
            return
        super().accept()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        left = self._build_geo_group()
        left.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        right = QWidget(self)
        right.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)

        right_content = QWidget(right)
        right_content.setMinimumWidth(0)
        right_content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        right_content_layout = QVBoxLayout(right_content)
        right_content_layout.setContentsMargins(0, 0, 0, 0)
        right_content_layout.setSpacing(4)
        right_content_layout.addWidget(self._build_mcmc_group())
        right_content_layout.addWidget(self._build_model_group())
        right_content_layout.addWidget(self._build_parameter_group())
        right_content_layout.addWidget(self._build_advanced_group())
        right_content_layout.addWidget(self._build_output_group())
        right_content_layout.addWidget(self._build_options_group())
        right_content_layout.addStretch(1)

        right_scroll = QScrollArea(right)
        right_scroll.setMinimumWidth(320)
        right_scroll.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
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

        layout.addWidget(left, 1)
        layout.addWidget(right, 1)

    def _build_geo_group(self):
        group = QGroupBox("Geographic data", self)
        layout = QVBoxLayout(group)
        self.geo_table = QTableWidget(group)
        self.geo_table.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.geo_table.setColumnCount(3)
        self.geo_table.setHorizontalHeaderLabels(["Area", "Latitude", "Longitude"])
        self.geo_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.geo_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.geo_table.setRowCount(len(self.area_names))
        for row, area in enumerate(self.area_names):
            item = QTableWidgetItem(area)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.geo_table.setItem(row, 0, item)
            self.geo_table.setItem(row, 1, QTableWidgetItem("0.0"))
            self.geo_table.setItem(row, 2, QTableWidgetItem("0.0"))

        buttons = QHBoxLayout()
        self.load_geo_button = QPushButton("Load", group)
        self.save_geo_button = QPushButton("Save", group)
        self.clear_geo_button = QPushButton("Clear", group)
        self.load_geo_button.clicked.connect(self._load_geo_file)
        self.save_geo_button.clicked.connect(self._save_geo_file)
        self.clear_geo_button.clicked.connect(self._clear_geo_table)
        buttons.addWidget(self.load_geo_button)
        buttons.addWidget(self.save_geo_button)
        buttons.addStretch(1)
        buttons.addWidget(self.clear_geo_button)

        layout.addWidget(self.geo_table, 1)
        layout.addLayout(buttons)
        return group

    def _build_mcmc_group(self):
        group = QGroupBox("MCMC", self)
        form = QFormLayout(group)
        self.chain_length_spin = QSpinBox(group)
        self.chain_length_spin.setRange(1, 2147483647)
        self.chain_length_spin.setSingleStep(1000)
        self.sample_frequency_spin = QSpinBox(group)
        self.sample_frequency_spin.setRange(1, 2147483647)
        self.sample_frequency_spin.setSingleStep(100)
        self.burnin_spin = QSpinBox(group)
        self.burnin_spin.setRange(0, 2147483647)
        self.burnin_spin.setSingleStep(1000)
        form.addRow("Chain Length", self.chain_length_spin)
        form.addRow("Sample freq.", self.sample_frequency_spin)
        return group

    def _build_model_group(self):
        group = QGroupBox("Model", self)
        form = QFormLayout(group)
        self.model_combo = QComboBox(group)
        for key in ["INDEPENDENCE", "DISTANCE_NORM"]:
            self.model_combo.addItem(BAYAREA_MODEL_DISPLAY[key], key)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        self.guess_rates_combo = QComboBox(group)
        self.guess_rates_combo.addItem("T", True)
        self.guess_rates_combo.addItem("F", False)
        self.distance_power_combo = QComboBox(group)
        self.distance_power_combo.addItem("T", True)
        self.distance_power_combo.addItem("F", False)
        self.distance_truncate_combo = QComboBox(group)
        self.distance_truncate_combo.addItem("T", True)
        self.distance_truncate_combo.addItem("F", False)
        form.addRow("Model Type", self.model_combo)
        form.addRow("Guess rates", self.guess_rates_combo)
        form.addRow("Distance power +", self.distance_power_combo)
        form.addRow("Distance truncate", self.distance_truncate_combo)
        self.apply_recommended_button = QPushButton("Recommended", group)
        self.apply_recommended_button.clicked.connect(self._apply_recommended_parameters)
        self.model_guide_label = QLabel(group)
        self.model_guide_label.setWordWrap(True)
        self.model_guide_label.setMaximumWidth(360)
        self.model_guide_label.setMaximumHeight(44)
        self.model_guide_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)
        form.addRow(self.apply_recommended_button)
        form.addRow(self.model_guide_label)
        return group

    def _build_parameter_group(self):
        group = QGroupBox("Engine parameters", self)
        form = QFormLayout(group)
        self.gain_prior_spin = self._make_double_spin(group, 0.000001, 1000000.0, 0.1)
        self.loss_prior_spin = self._make_double_spin(group, 0.000001, 1000000.0, 0.1)
        self.distance_power_prior_spin = self._make_double_spin(group, 0.000001, 1000000.0, 0.1)
        self.area_proposal_tuner_spin = self._make_double_spin(group, 0.0, 1.0, 0.05)
        self.rate_proposal_tuner_spin = self._make_double_spin(group, 0.000001, 100.0, 0.05)
        self.distance_proposal_tuner_spin = self._make_double_spin(group, 0.000001, 100.0, 0.05)
        self.rate_proposal_tuner_spin.setSingleStep(0.005)
        self.gain_prior_spin.setToolTip("Half-Cauchy prior scale for area gain rate.")
        self.loss_prior_spin.setToolTip("Half-Cauchy prior scale for area loss rate.")
        self.distance_power_prior_spin.setToolTip("Prior scale for the geographic distance-power parameter; only used by DISTANCE NORM.")
        self.area_proposal_tuner_spin.setToolTip("Average probability of resampling area histories; BayArea requires 0 to 1.")
        self.rate_proposal_tuner_spin.setToolTip("Proposal window for gain/loss rates. INDEPENDENCE is safest near 0.005.")
        self.distance_proposal_tuner_spin.setToolTip("Proposal window for distance-power proposals; only used by DISTANCE NORM.")
        form.addRow("Gain prior", self.gain_prior_spin)
        form.addRow("Loss prior", self.loss_prior_spin)
        form.addRow("Dist. power prior", self.distance_power_prior_spin)
        form.addRow("Area proposal", self.area_proposal_tuner_spin)
        form.addRow("Rate proposal", self.rate_proposal_tuner_spin)
        form.addRow("Dist. proposal", self.distance_proposal_tuner_spin)
        return group

    def _build_advanced_group(self):
        group = QGroupBox("Advanced", self)
        form = QFormLayout(group)
        self.seed_edit = QLineEdit(group)
        self.seed_edit.setPlaceholderText("engine random")
        self.auxiliary_sampling_combo = QComboBox(group)
        self.auxiliary_sampling_combo.addItem("F", False)
        self.auxiliary_sampling_combo.addItem("T", True)
        form.addRow("Seed", self.seed_edit)
        form.addRow("Aux sampling", self.auxiliary_sampling_combo)
        return group

    def _build_output_group(self):
        group = QGroupBox("Original output", self)
        layout = QVBoxLayout(group)
        row = QHBoxLayout()
        self.save_original_check = QCheckBox("Save original to", group)
        self.save_original_path_edit = QLineEdit(group)
        self.save_original_path_edit.setReadOnly(True)
        self.browse_original_button = QPushButton("...", group)
        self.save_original_check.toggled.connect(self._on_save_original_toggled)
        self.browse_original_button.clicked.connect(self._browse_original_output_dir)
        row.addWidget(self.save_original_check)
        row.addWidget(self.save_original_path_edit, 1)
        row.addWidget(self.browse_original_button)
        layout.addLayout(row)
        return group

    def _build_options_group(self):
        group = QGroupBox("Other Options", self)
        layout = QVBoxLayout(group)
        note = QLabel("Additional raw BayArea command-line options. Do not repeat the structured parameters above.", group)
        note.setWordWrap(True)
        note.setMaximumWidth(360)
        note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Maximum)
        self.other_options_edit = QTextEdit(group)
        self.other_options_edit.setAcceptRichText(False)
        self.other_options_edit.setFixedHeight(62)
        layout.addWidget(note)
        layout.addWidget(self.other_options_edit)
        return group

    def _load_config(self, config):
        self._loading_config = True
        try:
            self.chain_length_spin.setValue(int(config.chain_length))
            self.sample_frequency_spin.setValue(int(config.sample_frequency))
            self.burnin_spin.setValue(int(config.burnin))
            self.seed_edit.setPlaceholderText("engine random")
            self.seed_edit.setText("" if config.seed is None else str(config.seed))
            self._set_combo_data(self.model_combo, normalize_bayarea_model_type(config.model_type))
            self._set_combo_data(self.guess_rates_combo, bool(config.guess_initial_rates))
            self._set_combo_data(self.auxiliary_sampling_combo, bool(getattr(config, "use_auxiliary_sampling", False)))
            self._set_combo_data(self.distance_power_combo, bool(config.geo_distance_power_positive))
            self._set_combo_data(self.distance_truncate_combo, bool(config.geo_distance_truncate))
            self.gain_prior_spin.setValue(float(getattr(config, "gain_prior", 0.1)))
            self.loss_prior_spin.setValue(float(getattr(config, "loss_prior", 0.1)))
            self.distance_power_prior_spin.setValue(float(getattr(config, "distance_power_prior", 0.1)))
            self.area_proposal_tuner_spin.setValue(float(getattr(config, "area_proposal_tuner", 0.1)))
            model_type = normalize_bayarea_model_type(config.model_type)
            rate_tuner = float(getattr(config, "rate_proposal_tuner", 0.5))
            if model_type == "INDEPENDENCE" and abs(rate_tuner - 0.1) < 0.0000001:
                rate_tuner = float(bayarea_recommended_parameters("INDEPENDENCE")["rate_proposal_tuner"])
            self.rate_proposal_tuner_spin.setValue(rate_tuner)
            self.distance_proposal_tuner_spin.setValue(float(getattr(config, "distance_proposal_tuner", 0.5)))
            self.other_options_edit.setPlainText(str(config.other_options or ""))
            self.save_original_check.setChecked(bool(config.save_original_results))
            self.save_original_path_edit.setText(str(config.save_original_results_path or ""))
            self._on_save_original_toggled(bool(config.save_original_results))

            coords = dict(config.coordinates or {})
            for row, area in enumerate(self.area_names):
                lat, lon = coords.get(area, (0.0, 0.0))
                self.geo_table.item(row, 1).setText("%g" % float(lat))
                self.geo_table.item(row, 2).setText("%g" % float(lon))
        finally:
            self._loading_config = False
        self._update_model_controls()

    def _collect_config(self):
        coords = {}
        for row, area in enumerate(self.area_names):
            lat_item = self.geo_table.item(row, 1)
            lon_item = self.geo_table.item(row, 2)
            coords[area] = (
                float(str(lat_item.text() if lat_item else "0").strip() or 0.0),
                float(str(lon_item.text() if lon_item else "0").strip() or 0.0),
            )
        seed_text = self.seed_edit.text().strip()
        seed = int(seed_text) if seed_text else None
        return BayAreaConfig(
            area_names=list(self.area_names),
            coordinates=coords,
            chain_length=int(self.chain_length_spin.value()),
            sample_frequency=int(self.sample_frequency_spin.value()),
            burnin=0,
            model_type=normalize_bayarea_model_type(self.model_combo.currentData()),
            guess_initial_rates=bool(self.guess_rates_combo.currentData()),
            use_auxiliary_sampling=bool(self.auxiliary_sampling_combo.currentData()),
            geo_distance_power_positive=bool(self.distance_power_combo.currentData()),
            geo_distance_truncate=bool(self.distance_truncate_combo.currentData()),
            seed=seed,
            gain_prior=float(self.gain_prior_spin.value()),
            loss_prior=float(self.loss_prior_spin.value()),
            distance_power_prior=float(self.distance_power_prior_spin.value()),
            area_proposal_tuner=float(self.area_proposal_tuner_spin.value()),
            rate_proposal_tuner=float(self.rate_proposal_tuner_spin.value()),
            distance_proposal_tuner=float(self.distance_proposal_tuner_spin.value()),
            other_options=self.other_options_edit.toPlainText(),
            save_original_results=bool(self.save_original_check.isChecked()),
            save_original_results_path=self.save_original_path_edit.text().strip(),
        )

    def _set_combo_data(self, combo, value):
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _update_model_controls(self):
        model_type = normalize_bayarea_model_type(self.model_combo.currentData())
        distance_model = model_type == "DISTANCE_NORM"
        self.distance_power_combo.setEnabled(distance_model)
        self.distance_truncate_combo.setEnabled(distance_model)
        self.distance_power_prior_spin.setEnabled(distance_model)
        self.distance_proposal_tuner_spin.setEnabled(distance_model)
        self.model_guide_label.setText(self._model_guide_text(model_type))

    def _on_model_changed(self):
        if not self._loading_config:
            self._apply_recommended_parameters()
        self._update_model_controls()

    def _apply_recommended_parameters(self, *_args):
        model_type = normalize_bayarea_model_type(self.model_combo.currentData())
        defaults = bayarea_recommended_parameters(model_type)
        self.gain_prior_spin.setValue(float(defaults["gain_prior"]))
        self.loss_prior_spin.setValue(float(defaults["loss_prior"]))
        self.distance_power_prior_spin.setValue(float(defaults["distance_power_prior"]))
        self.area_proposal_tuner_spin.setValue(float(defaults["area_proposal_tuner"]))
        self.rate_proposal_tuner_spin.setValue(float(defaults["rate_proposal_tuner"]))
        self.distance_proposal_tuner_spin.setValue(float(defaults["distance_proposal_tuner"]))
        self._set_combo_data(self.distance_power_combo, bool(defaults["geo_distance_power_positive"]))
        self._set_combo_data(self.distance_truncate_combo, bool(defaults["geo_distance_truncate"]))
        self._update_model_controls()

    def _model_guide_text(self, model_type):
        if normalize_bayarea_model_type(model_type) == "INDEPENDENCE":
            return (
                "INDEPENDENCE ignores distance. Recommended rate proposal is 0.005; larger values can "
                "drift to huge sampled histories and run for a very long time."
            )
        return (
            "DISTANCE NORM follows the official BayArea tutorial style: real non-identical coordinates, "
            "gain/loss/distance-power priors 0.1, area proposal tuner 0.1, positive distance power enabled. "
            "Do not run this model with all-zero or identical coordinates."
        )

    def _make_double_spin(self, parent, minimum, maximum, step):
        spin = QDoubleSpinBox(parent)
        spin.setDecimals(6)
        spin.setRange(float(minimum), float(maximum))
        spin.setSingleStep(float(step))
        return spin

    def _confirm_distance_coordinates(self, config):
        if normalize_bayarea_model_type(config.model_type) != "DISTANCE_NORM":
            return True
        coords = [
            (round(float(config.coordinates[area][0]), 12), round(float(config.coordinates[area][1]), 12))
            for area in config.area_names
            if area in config.coordinates
        ]
        if len(coords) <= 1 or len(set(coords)) > 1:
            return True
        choice = QMessageBox.question(
            self,
            "Geographic data",
            "All areas have identical coordinates. DISTANCE NORM will not contain meaningful geographic-distance information. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return choice == QMessageBox.Yes

    def _confirm_independence_rate_tuner(self, config):
        if normalize_bayarea_model_type(config.model_type) != "INDEPENDENCE":
            return True
        try:
            rate_tuner = float(config.rate_proposal_tuner)
        except Exception:
            return True
        if rate_tuner <= 0.02:
            return True
        choice = QMessageBox.question(
            self,
            "BayArea INDEPENDENCE",
            "The INDEPENDENCE model is sensitive to the Rate proposal tuner. Values above 0.02 can "
            "make BayArea sample extremely large histories and run for a very long time. Continue with %.6g?"
            % rate_tuner,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return choice == QMessageBox.Yes

    def _load_geo_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load geographic data",
            "",
            "CSV/Text files (*.csv *.txt);;All files (*.*)",
        )
        if not path:
            return
        try:
            text = open(path, "r", encoding="utf-8-sig", errors="ignore").read()
            self._apply_geo_text(text)
        except Exception as exc:
            QMessageBox.warning(self, "Load failed", str(exc))

    def _save_geo_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save geographic data",
            "",
            "CSV files (*.csv);;All files (*.*)",
        )
        if not path:
            return
        try:
            lines = []
            for row, area in enumerate(self.area_names):
                lat = self.geo_table.item(row, 1).text()
                lon = self.geo_table.item(row, 2).text()
                lines.append("%s,%s,%s" % (area, lat, lon))
            open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))

    def _apply_geo_text(self, text):
        rows = [line.strip() for line in str(text or "").splitlines() if line.strip() and not line.strip().startswith("#")]
        values = []
        for line in rows:
            if "," in line:
                parts = [x.strip() for x in line.split(",")]
                if len(parts) >= 3:
                    values.append((parts[1], parts[2]))
                elif len(parts) >= 2:
                    values.append((parts[0], parts[1]))
            else:
                parts = line.split()
                if len(parts) >= 2:
                    values.append((parts[0], parts[1]))
        if len(values) < len(self.area_names):
            raise ValueError("Geographic data does not contain enough rows for all areas.")
        for row, (lat, lon) in enumerate(values[: len(self.area_names)]):
            self.geo_table.item(row, 1).setText(str(lat))
            self.geo_table.item(row, 2).setText(str(lon))

    def _clear_geo_table(self):
        for row in range(len(self.area_names)):
            self.geo_table.item(row, 1).setText("0.0")
            self.geo_table.item(row, 2).setText("0.0")

    def _on_save_original_toggled(self, checked):
        self.save_original_path_edit.setEnabled(bool(checked))
        self.browse_original_button.setEnabled(bool(checked))

    def _browse_original_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select output directory", "")
        if path:
            self.save_original_path_edit.setText(path)

    def _save_settings(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save BayArea setting",
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
            "Load BayArea setting",
            "",
            "JSON files (*.json);;All files (*.*)",
        )
        if not path:
            return
        try:
            text = open(path, "r", encoding="utf-8", errors="ignore").read()
            config = BayAreaConfig.from_preset_json_text(
                text,
                area_names=self.area_names,
                base_config=self._collect_config(),
            )
            self._config = config
            self._load_config(config)
        except Exception as exc:
            QMessageBox.warning(self, "Load failed", str(exc))

    def _reset_config(self):
        config = BayAreaConfig.default_for_areas(self.area_names)
        self._config = config
        self._load_config(config)
