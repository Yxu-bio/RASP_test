import csv
import json
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from domain.models.spatial_data import SpatialDataProject
from gui.widgets.spatial_map_view import SpatialMapView
from gui.workers.region_geojson_builder_worker import RegionGeoJsonBuilderWorker
from gui.window_behavior import configure_resizable_window


class RegionGeoJsonBuilderDialog(QDialog):
    def __init__(self, *, spatial_service, load_areas_callback=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Region GeoJSON Builder")
        self.setMinimumSize(980, 680)
        configure_resizable_window(self)
        self.spatial_service = spatial_service
        self.load_areas_callback = load_areas_callback
        self.worker = None
        self.last_result = None

        self._build_ui()
        self._load_presets()

    def reject(self):
        if self.worker is not None and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Cancel build",
                "Region GeoJSON build is still running. Cancel it and close this dialog?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self.worker.cancel()
            if not self.worker.wait(3000):
                QMessageBox.information(self, "Cancelling", "Build is still stopping. Please wait before closing.")
                return
        super().reject()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.workflow_group = QGroupBox("Workflow", self)
        workflow_layout = QGridLayout(self.workflow_group)
        self.template_group = QGroupBox("Template / advanced rule set", self)
        template_layout = QGridLayout(self.template_group)
        self.template_summary_group = QGroupBox("Template source summary", self)
        template_summary_layout = QVBoxLayout(self.template_summary_group)
        self.input_group = QGroupBox("Custom input boundary data", self)
        input_layout = QGridLayout(self.input_group)
        self.settings_group = QGroupBox("Custom mapping and region settings", self)
        settings_layout = QGridLayout(self.settings_group)
        self.output_group = QGroupBox("Output files", self)
        output_layout = QGridLayout(self.output_group)

        self.build_mode_combo = QComboBox(self.workflow_group)
        self.build_mode_combo.addItem("Template / advanced config", "config")
        self.build_mode_combo.addItem("Custom input files", "custom")
        self.build_mode_combo.currentIndexChanged.connect(self._on_build_mode_changed)
        self.preset_combo = QComboBox(self.template_group)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        self.base_layer_combo = QComboBox(self.input_group)
        self.base_layer_combo.currentIndexChanged.connect(self._on_base_layer_changed)
        self.config_path_edit = QLineEdit(self.template_group)
        self.base_geojson_edit = QLineEdit(self.input_group)
        self.mapping_csv_edit = QLineEdit(self.input_group)
        self.value_field_edit = QLineEdit(self.settings_group)
        self.area_field_edit = QLineEdit(self.settings_group)
        self.feature_fields_edit = QLineEdit(self.settings_group)
        self.group_name_edit = QLineEdit(self.settings_group)
        self.output_path_edit = QLineEdit(self.output_group)
        self.notes_path_edit = QLineEdit(self.output_group)
        self.unassigned_path_edit = QLineEdit(self.output_group)
        self.template_summary_text = QTextEdit(self.template_summary_group)
        self.template_summary_text.setReadOnly(True)
        self.template_summary_text.setLineWrapMode(QTextEdit.NoWrap)
        self.template_summary_text.setFixedHeight(96)
        self.value_field_edit.setText("match_value")
        self.area_field_edit.setText("area_code")
        self.feature_fields_edit.setText("ISO_A3, ADM0_A3, ADM0_ISO, ADM0_TLC, GU_A3, SU_A3, SUBUNIT, NAME, NAME_LONG, name")
        self.group_name_edit.setText("custom_regions")

        self.config_button = QPushButton("Browse...", self.template_group)
        self.config_button.clicked.connect(self._browse_config)
        self.base_button = QPushButton("Browse...", self.input_group)
        self.base_button.clicked.connect(self._browse_base_geojson)
        self.mapping_button = QPushButton("Browse...", self.input_group)
        self.mapping_button.clicked.connect(self._browse_mapping_csv)
        self.output_button = QPushButton("Browse...", self.output_group)
        self.output_button.clicked.connect(self._browse_output)
        self.notes_button = QPushButton("Browse...", self.output_group)
        self.notes_button.clicked.connect(lambda: self._browse_save_path(self.notes_path_edit, "Build notes CSV", "CSV files (*.csv);;All files (*)"))
        self.unassigned_button = QPushButton("Browse...", self.output_group)
        self.unassigned_button.clicked.connect(lambda: self._browse_save_path(self.unassigned_path_edit, "Unassigned CSV", "CSV files (*.csv);;All files (*)"))

        workflow_layout.addWidget(QLabel("Build mode", self.workflow_group), 0, 0)
        workflow_layout.addWidget(self.build_mode_combo, 0, 1)
        workflow_layout.setColumnStretch(1, 1)

        template_layout.addWidget(QLabel("Template", self.template_group), 0, 0)
        template_layout.addWidget(self.preset_combo, 0, 1)
        template_layout.addWidget(QLabel("Advanced config JSON", self.template_group), 1, 0)
        template_layout.addWidget(self.config_path_edit, 1, 1)
        template_layout.addWidget(self.config_button, 1, 2)
        template_layout.setColumnStretch(1, 1)

        template_summary_layout.addWidget(self.template_summary_text)

        input_layout.addWidget(QLabel("Base layer", self.input_group), 0, 0)
        input_layout.addWidget(self.base_layer_combo, 0, 1)
        input_layout.addWidget(QLabel("Base GeoJSON file", self.input_group), 1, 0)
        input_layout.addWidget(self.base_geojson_edit, 1, 1)
        input_layout.addWidget(self.base_button, 1, 2)
        input_layout.addWidget(QLabel("Mapping CSV", self.input_group), 2, 0)
        input_layout.addWidget(self.mapping_csv_edit, 2, 1)
        input_layout.addWidget(self.mapping_button, 2, 2)
        input_layout.setColumnStretch(1, 1)

        settings_layout.addWidget(QLabel("Mapping columns", self.settings_group), 0, 0)
        mapping_columns = QHBoxLayout()
        mapping_columns.addWidget(QLabel("value", self.settings_group))
        mapping_columns.addWidget(self.value_field_edit)
        mapping_columns.addWidget(QLabel("area", self.settings_group))
        mapping_columns.addWidget(self.area_field_edit)
        settings_layout.addLayout(mapping_columns, 0, 1)
        settings_layout.addWidget(QLabel("GeoJSON match fields", self.settings_group), 1, 0)
        settings_layout.addWidget(self.feature_fields_edit, 1, 1)
        settings_layout.addWidget(QLabel("Output group/name", self.settings_group), 2, 0)
        settings_layout.addWidget(self.group_name_edit, 2, 1)
        settings_layout.setColumnStretch(1, 1)

        output_layout.addWidget(QLabel("Output GeoJSON", self.output_group), 0, 0)
        output_layout.addWidget(self.output_path_edit, 0, 1)
        output_layout.addWidget(self.output_button, 0, 2)
        output_layout.addWidget(QLabel("Build notes CSV", self.output_group), 1, 0)
        output_layout.addWidget(self.notes_path_edit, 1, 1)
        output_layout.addWidget(self.notes_button, 1, 2)
        output_layout.addWidget(QLabel("Unassigned CSV", self.output_group), 2, 0)
        output_layout.addWidget(self.unassigned_path_edit, 2, 1)
        output_layout.addWidget(self.unassigned_button, 2, 2)
        output_layout.setColumnStretch(1, 1)

        layout.addWidget(self.workflow_group)
        layout.addWidget(self.template_group)
        layout.addWidget(self.template_summary_group)
        layout.addWidget(self.input_group)
        layout.addWidget(self.settings_group)
        layout.addWidget(self.output_group)

        action_row = QHBoxLayout()
        self.run_button = QPushButton("Build", self)
        self.run_button.clicked.connect(self._run_build)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self._cancel_build)
        self.cancel_button.setEnabled(False)
        self.load_output_button = QPushButton("Load Output Into Spatial Project", self)
        self.load_output_button.clicked.connect(self._load_output_into_project)
        self.load_output_button.setEnabled(False)
        self.progress_label = QLabel("Ready", self)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        action_row.addWidget(self.run_button)
        action_row.addWidget(self.cancel_button)
        action_row.addWidget(self.load_output_button)
        action_row.addSpacing(12)
        action_row.addWidget(self.progress_label)
        action_row.addWidget(self.progress_bar, 1)
        layout.addLayout(action_row)

        self.tabs = QTabWidget(self)
        self.summary_text = QTextEdit(self)
        self.summary_text.setReadOnly(True)
        self.summary_text.setLineWrapMode(QTextEdit.NoWrap)
        self.map_widget = SpatialMapView(self)
        self.notes_table = QTableWidget(self)
        self.unassigned_table = QTableWidget(self)
        self.config_preview = QTextEdit(self)
        self.config_preview.setReadOnly(True)
        self.config_preview.setLineWrapMode(QTextEdit.NoWrap)
        self.tabs.addTab(self.summary_text, "Summary")
        self.tabs.addTab(self.map_widget, "Map Preview")
        self.tabs.addTab(self.notes_table, "Build notes")
        self.tabs.addTab(self.unassigned_table, "Unassigned")
        self.tabs.addTab(self.config_preview, "Config")
        layout.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for widget in [
            self.base_geojson_edit,
            self.mapping_csv_edit,
            self.value_field_edit,
            self.area_field_edit,
            self.feature_fields_edit,
            self.group_name_edit,
        ]:
            widget.textChanged.connect(self._refresh_config_preview)

    def _load_presets(self):
        self._load_base_layer_presets()
        root = Path(__file__).resolve().parents[2]
        examples = root / "data" / "fixtures" / "region_builder"
        presets = [
            ("Custom config...", ""),
            ("Dore et al. Ponerinae 7 bioregions", examples / "dore_ponerinae_7_palea_rules.json"),
            ("Kawahara et al. butterfly 7 bioregions", examples / "kawahara_7_bioregion_rules.json"),
            ("Simple demo", examples / "simple_region_rules.json"),
        ]
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for label, path in presets:
            self.preset_combo.addItem(label, str(path or ""))
        self.preset_combo.blockSignals(False)
        if self.preset_combo.count() > 1:
            self.preset_combo.setCurrentIndex(1)
            self._set_config_path(self.preset_combo.currentData(), reset_outputs=True)
        self._sync_mode_widgets()

    def _load_base_layer_presets(self):
        root = Path(__file__).resolve().parents[2]
        presets = [
            {
                "label": "Natural Earth admin0 map subunits (countries, territories, disputed units)",
                "path": root / "resources" / "spatial_base_layers" / "natural_earth" / "ne_50m_admin_0_map_subunits.geojson",
                "fields": "ISO_A3, ISO_A3_EH, ADM0_A3, ADM0_ISO, ADM0_TLC, GU_A3, SU_A3, SUBUNIT, NAME, NAME_LONG",
            },
            {
                "label": "Simplified world countries (small/fast demo layer)",
                "path": root / "data" / "spatial" / "base_layers" / "world_countries_simplified.geojson",
                "fields": "name",
            },
            {
                "label": "Natural Earth admin1 states/provinces",
                "path": root / "resources" / "spatial_base_layers" / "natural_earth" / "ne_10m_admin_1_states_provinces.geojson",
                "fields": "adm1_code, iso_3166_2, name, name_en, gn_name, adm0_a3, iso_a2",
            },
            {
                "label": "Custom GeoJSON file",
                "path": "",
                "fields": self.feature_fields_edit.text(),
            },
        ]
        self.base_layer_combo.blockSignals(True)
        self.base_layer_combo.clear()
        for preset in presets:
            self.base_layer_combo.addItem(preset["label"], preset)
        self.base_layer_combo.blockSignals(False)
        if presets:
            self.base_layer_combo.setCurrentIndex(0)

    def _build_mode(self):
        return str(self.build_mode_combo.currentData() or "config")

    def _on_build_mode_changed(self):
        self._sync_mode_widgets()
        self._refresh_config_preview()
        if self._build_mode() == "custom":
            self._fill_default_outputs(reset=False)

    def _sync_mode_widgets(self):
        custom = self._build_mode() == "custom"
        self.template_group.setVisible(not custom)
        self.template_summary_group.setVisible(not custom)
        self.input_group.setVisible(custom)
        self.settings_group.setVisible(custom)
        self.preset_combo.setEnabled(not custom)
        self.config_path_edit.setEnabled(not custom)
        self.config_button.setEnabled(not custom)
        self.base_layer_combo.setEnabled(custom)
        self.base_geojson_edit.setEnabled(custom)
        self.base_button.setEnabled(custom)
        self.mapping_csv_edit.setEnabled(custom)
        self.mapping_button.setEnabled(custom)
        self.value_field_edit.setEnabled(custom)
        self.area_field_edit.setEnabled(custom)
        self.feature_fields_edit.setEnabled(custom)
        self.group_name_edit.setEnabled(custom)

    def _on_base_layer_changed(self):
        preset = self.base_layer_combo.currentData()
        if not isinstance(preset, dict):
            return
        path = str(preset.get("path") or "")
        fields = str(preset.get("fields") or "")
        if path:
            self.base_geojson_edit.setText(path)
        if fields:
            self.feature_fields_edit.setText(fields)
        self._refresh_config_preview()

    def _set_base_layer_by_path(self, path):
        target = self._normalise_path_for_compare(path)
        for index in range(self.base_layer_combo.count()):
            preset = self.base_layer_combo.itemData(index)
            if not isinstance(preset, dict):
                continue
            preset_path = self._normalise_path_for_compare(preset.get("path") or "")
            if preset_path and preset_path == target:
                self.base_layer_combo.blockSignals(True)
                self.base_layer_combo.setCurrentIndex(index)
                self.base_layer_combo.blockSignals(False)
                return
        self.base_layer_combo.blockSignals(True)
        self.base_layer_combo.setCurrentIndex(max(0, self.base_layer_combo.count() - 1))
        self.base_layer_combo.blockSignals(False)

    def _normalise_path_for_compare(self, path):
        text = str(path or "").strip()
        if not text or self._is_url(text):
            return text.lower()
        try:
            return str(Path(text).resolve()).lower()
        except Exception:
            return text.lower()

    def _on_preset_changed(self):
        path = str(self.preset_combo.currentData() or "")
        if path:
            self._set_config_path(path, reset_outputs=True)

    def _browse_config(self):
        path, _selected = self._open_file_name("Select region builder config", "JSON files (*.json);;All files (*)")
        if path:
            self.build_mode_combo.setCurrentIndex(0)
            self.preset_combo.setCurrentIndex(0)
            self._set_config_path(path, reset_outputs=True)

    def _browse_base_geojson(self):
        if self._build_mode() != "custom":
            return
        path, _selected = self._open_file_name("Select base GeoJSON", "GeoJSON files (*.geojson *.json);;All files (*)")
        if path:
            self.base_layer_combo.blockSignals(True)
            self.base_layer_combo.setCurrentIndex(max(0, self.base_layer_combo.count() - 1))
            self.base_layer_combo.blockSignals(False)
            self.base_geojson_edit.setText(path)
            self._fill_default_outputs(reset=False)

    def _browse_mapping_csv(self):
        if self._build_mode() != "custom":
            return
        path, _selected = self._open_file_name("Select mapping CSV", "CSV/TSV files (*.csv *.tsv *.txt);;All files (*)")
        if path:
            self.mapping_csv_edit.setText(path)
            self._fill_default_outputs(reset=False)

    def _browse_output(self):
        self._browse_save_path(self.output_path_edit, "Output area GeoJSON", "GeoJSON files (*.geojson *.json);;All files (*)")

    def _browse_save_path(self, target_edit, title, name_filter):
        path, _selected = self._save_file_name(title, name_filter)
        if path:
            target_edit.setText(path)

    def _set_config_path(self, path, reset_outputs=False):
        path = str(path or "")
        self.config_path_edit.setText(path)
        self._refresh_config_preview()
        self._fill_default_outputs(reset=reset_outputs)

    def _fill_default_outputs(self, reset=False):
        root = Path(__file__).resolve().parents[2]
        out_dir = root / "runs" / "region_builder"
        if self._build_mode() == "custom":
            raw_stem = str(self.group_name_edit.text() or "").strip() or Path(str(self.mapping_csv_edit.text() or "")).stem or "custom_regions"
            stem = "".join(ch if (ch.isalnum() or ch in "_-") else "_" for ch in raw_stem).strip("_") or "custom_regions"
        else:
            config_path = Path(str(self.config_path_edit.text() or ""))
            if not config_path.name:
                return
            stem = config_path.stem
        for suffix in ("_rules", "_config"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        if reset or not self.output_path_edit.text().strip():
            self.output_path_edit.setText(str(out_dir / ("%s.geojson" % stem)))
        if reset or not self.notes_path_edit.text().strip():
            self.notes_path_edit.setText(str(out_dir / ("%s_notes.csv" % stem)))
        if reset or not self.unassigned_path_edit.text().strip():
            self.unassigned_path_edit.setText(str(out_dir / ("%s_unassigned.csv" % stem)))

    def _refresh_config_preview(self):
        if self._build_mode() == "custom":
            try:
                self.config_preview.setPlainText(json.dumps(self._build_custom_config(validate=False), ensure_ascii=False, indent=2))
                self.template_summary_text.setPlainText("")
            except Exception as exc:
                self.config_preview.setPlainText("Generated config preview failed:\n%s" % exc)
            return
        path = Path(str(self.config_path_edit.text() or ""))
        if not path.exists():
            self.config_preview.setPlainText("")
            self.template_summary_text.setPlainText("")
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            self.config_preview.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))
            self._populate_inputs_from_config(payload, path.parent)
        except Exception as exc:
            self.config_preview.setPlainText("Failed to read config:\n%s" % exc)

    def _populate_inputs_from_config(self, config, config_dir):
        config = dict(config or {})
        mapping_config = dict(config.get("base_mapping") or {})
        base_geojson = str(config.get("base_geojson") or config.get("base_url") or "")
        if base_geojson and not self._is_url(base_geojson):
            path = Path(base_geojson)
            if not path.is_absolute():
                base_geojson = str((Path(config_dir) / path).resolve())
        mapping_file = str(mapping_config.get("mapping_file") or config.get("mapping_csv") or "")
        if mapping_file and not self._is_url(mapping_file):
            path = Path(mapping_file)
            if not path.is_absolute():
                mapping_file = str((Path(config_dir) / path).resolve())
        self.base_geojson_edit.blockSignals(True)
        self.mapping_csv_edit.blockSignals(True)
        self.value_field_edit.blockSignals(True)
        self.area_field_edit.blockSignals(True)
        self.feature_fields_edit.blockSignals(True)
        self.group_name_edit.blockSignals(True)
        try:
            self.base_geojson_edit.setText(base_geojson)
            self.mapping_csv_edit.setText(mapping_file)
            self.value_field_edit.setText(str(mapping_config.get("value_field") or "match_value"))
            self.area_field_edit.setText(str(mapping_config.get("area_field") or "area_code"))
            self.feature_fields_edit.setText(", ".join(mapping_config.get("feature_fields") or []))
            self.group_name_edit.setText(str(config.get("group") or config.get("name") or "custom_regions"))
        finally:
            self.base_geojson_edit.blockSignals(False)
            self.mapping_csv_edit.blockSignals(False)
            self.value_field_edit.blockSignals(False)
            self.area_field_edit.blockSignals(False)
            self.feature_fields_edit.blockSignals(False)
            self.group_name_edit.blockSignals(False)
        self._set_base_layer_by_path(base_geojson)
        self._update_template_source_summary(config, base_geojson, mapping_file, mapping_config)

    def _update_template_source_summary(self, config, base_geojson, mapping_file, mapping_config):
        base_layer = self.base_layer_combo.currentText() or "Custom/unknown base layer"
        lines = [
            "This template builds the output GeoJSON from a predefined rule set.",
            "Base layer: %s" % base_layer,
            "Base GeoJSON: %s" % (base_geojson or "(not set)"),
            "Mapping CSV: %s" % (mapping_file or "(not set)"),
            "Mapping columns: value=%s, area=%s"
            % (
                str(mapping_config.get("value_field") or "match_value"),
                str(mapping_config.get("area_field") or "area_code"),
            ),
            "GeoJSON match fields: %s" % (", ".join(mapping_config.get("feature_fields") or []) or "(not set)"),
            "Output group/name: %s" % (str(config.get("group") or config.get("name") or "custom_regions")),
        ]
        self.template_summary_text.setPlainText("\n".join(lines))

    def _build_custom_config(self, validate=True):
        base_geojson = self.base_geojson_edit.text().strip()
        mapping_csv = self.mapping_csv_edit.text().strip()
        value_field = self.value_field_edit.text().strip() or "match_value"
        area_field = self.area_field_edit.text().strip() or "area_code"
        feature_fields = self._split_csv_text(self.feature_fields_edit.text())
        group = self.group_name_edit.text().strip() or "custom_regions"
        if validate:
            if not base_geojson:
                raise ValueError("Base GeoJSON file is required.")
            if not mapping_csv:
                raise ValueError("Mapping CSV path is required.")
            if not feature_fields:
                raise ValueError("At least one GeoJSON match field is required.")
        area_order = self._area_order_from_mapping_csv(mapping_csv, area_field) if mapping_csv else []
        return {
            "name": group,
            "group": group,
            "source": "RASP5 Region GeoJSON Builder custom input files",
            "boundary_kind": "custom_rule_based_reference",
            "official_author_boundary": False,
            "build_notes": "Built from user-selected base GeoJSON and mapping CSV. No split/override rules are applied in Custom input files mode.",
            "base_geojson": base_geojson,
            "base_mapping": {
                "mapping_file": mapping_csv,
                "value_field": value_field,
                "area_field": area_field,
                "feature_fields": feature_fields,
            },
            "area_order": area_order,
            "rules": [],
        }

    def _area_order_from_mapping_csv(self, mapping_csv, area_field):
        if not mapping_csv or self._is_url(mapping_csv):
            return []
        path = Path(mapping_csv)
        if not path.exists():
            return []
        areas = []
        seen = set()
        delimiter = "\t" if path.suffix.lower() in (".tsv", ".txt") else ","
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=delimiter)
                for row in reader:
                    area = str(row.get(area_field, "") or "").strip()
                    if area and area not in seen:
                        seen.add(area)
                        areas.append(area)
        except Exception:
            return []
        return areas

    def _split_csv_text(self, text):
        return [part.strip() for part in str(text or "").split(",") if part.strip()]

    def _is_url(self, value):
        text = str(value or "")
        return text.startswith("http://") or text.startswith("https://")

    def _run_build(self):
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "Build in progress", "A region GeoJSON build task is already running.")
            return
        output_path = self.output_path_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, "Missing output", "Output GeoJSON path is required.")
            return
        if self._build_mode() == "custom":
            try:
                config_data = self._build_custom_config(validate=True)
            except Exception as exc:
                QMessageBox.warning(self, "Invalid custom inputs", str(exc))
                return
            self.worker = RegionGeoJsonBuilderWorker(
                config_data=config_data,
                config_dir=str(Path(self.mapping_csv_edit.text().strip()).parent) if self.mapping_csv_edit.text().strip() else "",
                output_path=output_path,
                notes_path=self.notes_path_edit.text().strip(),
                unassigned_path=self.unassigned_path_edit.text().strip(),
            )
        else:
            config_path = self.config_path_edit.text().strip()
            if not config_path:
                QMessageBox.warning(self, "Missing config", "Advanced config JSON path is required in template/config mode.")
                return
            self.worker = RegionGeoJsonBuilderWorker(
                config_path=config_path,
                output_path=output_path,
                notes_path=self.notes_path_edit.text().strip(),
                unassigned_path=self.unassigned_path_edit.text().strip(),
            )
        self.worker.progress.connect(self._on_progress)
        self.worker.succeeded.connect(self._on_build_succeeded)
        self.worker.failed.connect(self._on_build_failed)
        self.worker.finished.connect(self._on_build_finished)
        self._set_running(True)
        self.summary_text.setPlainText("Running region GeoJSON builder ...")
        self.worker.start()

    def _cancel_build(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.progress_label.setText("Cancelling build ...")

    def _on_progress(self, done, total, message):
        total = int(total or 100)
        done = int(done or 0)
        percent = int(round(done * 100.0 / total)) if total else 0
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(max(0, min(100, percent)))
        self.progress_label.setText(str(message or "Building ..."))

    def _on_build_succeeded(self, result):
        self.last_result = dict(result or {})
        self.progress_bar.setValue(100)
        self.progress_label.setText("Build completed")
        self._refresh_result_views()
        self.load_output_button.setEnabled(True)
        QMessageBox.information(
            self,
            "Build completed",
            "Built %d area feature(s).\nOutput:\n%s"
            % (
                len((self.last_result.get("collection") or {}).get("features") or []),
                self.last_result.get("output_path", ""),
            ),
        )

    def _on_build_failed(self, message):
        text = str(message or "Region GeoJSON build failed.")
        self.progress_bar.setValue(0)
        if "cancelled" in text.lower():
            self.progress_label.setText("Build cancelled")
            QMessageBox.information(self, "Build cancelled", text)
        else:
            self.progress_label.setText("Build failed")
            QMessageBox.critical(self, "Build failed", text)

    def _on_build_finished(self):
        self._set_running(False)
        self.worker = None

    def _refresh_result_views(self):
        result = self.last_result or {}
        collection = result.get("collection") or {}
        features = list(collection.get("features") or [])
        notes = list(result.get("notes") or [])
        unassigned = list(result.get("unassigned") or [])
        lines = [
            "Region GeoJSON Builder",
            "",
            "Config: %s" % result.get("config_path", ""),
            "Output: %s" % result.get("output_path", ""),
            "Notes CSV: %s" % result.get("notes_path", ""),
            "Unassigned CSV: %s" % result.get("unassigned_path", ""),
            "",
            "Area features: %d" % len(features),
            "Build note rows: %d" % len(notes),
            "Unassigned source features: %d" % len(unassigned),
        ]
        for feature in features:
            props = dict(feature.get("properties") or {})
            polygons = list((feature.get("geometry") or {}).get("coordinates") or [])
            lines.append("  %s: %d polygon part(s)" % (props.get("area_code", ""), len(polygons)))
        self.summary_text.setPlainText("\n".join(lines))
        self._set_rows(self.notes_table, ["source_id", "source_name", "area_code", "rule", "polygon_count"], notes[:5000])
        self._set_rows(
            self.unassigned_table,
            ["source_id", "source_name", "properties_json"],
            [
                {
                    "source_id": row.get("source_id", ""),
                    "source_name": row.get("source_name", ""),
                    "properties_json": json.dumps(row.get("properties") or {}, ensure_ascii=False, sort_keys=True),
                }
                for row in unassigned[:5000]
            ],
        )
        self._refresh_output_map(result.get("output_path", ""))

    def _refresh_output_map(self, output_path):
        try:
            areas, issues = self.spatial_service.import_area_geojson(str(output_path))
        except Exception as exc:
            self.map_widget.set_project(SpatialDataProject())
            self.summary_text.append("\nMap preview failed: %s" % exc)
            return
        self.map_widget.set_project(SpatialDataProject(areas=areas, qa_issues=list(issues or [])))

    def _load_output_into_project(self):
        result = self.last_result or {}
        output_path = str(result.get("output_path") or self.output_path_edit.text() or "").strip()
        if not output_path:
            QMessageBox.warning(self, "No output", "Build or select an output GeoJSON first.")
            return
        try:
            areas, issues = self.spatial_service.import_area_geojson(output_path)
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))
            return
        if self.load_areas_callback is not None:
            self.load_areas_callback(areas, output_path, issues)
        QMessageBox.information(
            self,
            "Areas loaded",
            "Loaded %d area polygon(s) into the current spatial project. QA issues: %d."
            % (len(areas), len(issues)),
        )

    def _set_rows(self, table, headers, rows):
        rows = list(rows or [])
        table.clear()
        table.setColumnCount(len(headers))
        table.setRowCount(len(rows))
        table.setHorizontalHeaderLabels(headers)
        for row_index, row in enumerate(rows):
            for col_index, header in enumerate(headers):
                if isinstance(row, dict):
                    value = row.get(header, "")
                else:
                    value = ""
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row_index, col_index, item)
        table.resizeColumnsToContents()

    def _set_running(self, running):
        running = bool(running)
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.load_output_button.setEnabled((not running) and bool(self.last_result))
        self.build_mode_combo.setEnabled(not running)
        self.output_path_edit.setEnabled(not running)
        self.notes_path_edit.setEnabled(not running)
        self.unassigned_path_edit.setEnabled(not running)
        self.output_button.setEnabled(not running)
        self.notes_button.setEnabled(not running)
        self.unassigned_button.setEnabled(not running)
        if not running:
            self._sync_mode_widgets()
        else:
            for widget in [
                self.preset_combo,
                self.config_path_edit,
                self.config_button,
                self.base_layer_combo,
                self.base_geojson_edit,
                self.base_button,
                self.mapping_csv_edit,
                self.mapping_button,
                self.value_field_edit,
                self.area_field_edit,
                self.feature_fields_edit,
                self.group_name_edit,
            ]:
                widget.setEnabled(False)
        if running:
            self.progress_bar.setValue(0)
            self.progress_label.setText("Building ...")

    def _open_file_name(self, title, name_filter):
        return self._file_name_dialog(title, name_filter, QFileDialog.AcceptOpen, QFileDialog.ExistingFile)

    def _save_file_name(self, title, name_filter):
        return self._file_name_dialog(title, name_filter, QFileDialog.AcceptSave, QFileDialog.AnyFile)

    def _file_name_dialog(self, title, name_filter, accept_mode, file_mode):
        dialog = QFileDialog(self, title, "")
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setAcceptMode(accept_mode)
        dialog.setFileMode(file_mode)
        dialog.setNameFilter(name_filter)
        dialog.setMinimumSize(640, 420)
        dialog.resize(860, 560)
        configure_resizable_window(dialog)
        if dialog.exec_() != QDialog.Accepted:
            return "", ""
        selected_files = dialog.selectedFiles()
        return (selected_files[0] if selected_files else ""), dialog.selectedNameFilter()
