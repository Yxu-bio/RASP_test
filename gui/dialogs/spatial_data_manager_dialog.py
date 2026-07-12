from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
)

from domain.models.spatial_data import SpatialDataProject
from gui.workers.spatial_area_import_worker import SpatialAreaImportWorker
from gui.workers.spatial_encoding_worker import SpatialEncodingWorker
from gui.workers.spatial_occurrence_import_worker import SpatialOccurrenceImportWorker
from gui.widgets.spatial_map_view import SpatialMapView


class SpatialDataManagerDialog(QDialog):
    OCCURRENCE_PREVIEW_LIMIT = 500
    AUDIT_PREVIEW_LIMIT = 1000
    SHOW_ALL_CONFIRM_LIMIT = 20000

    def __init__(
        self,
        service,
        project=None,
        tree_taxa=None,
        matrix_taxa=None,
        apply_matrix_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Spatial Data Manager")
        self.setMinimumSize(960, 640)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.service = service
        self._project = project if project is not None else SpatialDataProject()
        self.tree_taxa = list(tree_taxa or [])
        self.matrix_taxa = list(matrix_taxa or [])
        self.apply_matrix_callback = apply_matrix_callback
        self._show_all_occurrences = False
        self._show_all_audit = False
        self._syncing_spatial_selection = False
        self.area_import_worker = None
        self.occurrence_import_worker = None
        self.encoding_worker = None

        self._build_ui()
        self._refresh_all()

    def project(self):
        return self._project

    def reject(self):
        if self.occurrence_import_worker is not None and self.occurrence_import_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Cancel occurrence import",
                "Occurrence import is still running. Cancel it and close this dialog?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self.occurrence_import_worker.cancel()
            if not self.occurrence_import_worker.wait(3000):
                QMessageBox.information(
                    self,
                    "Cancelling",
                    "Occurrence import is still stopping. Please wait for the cancel operation to finish before closing.",
                )
                return
        if self.area_import_worker is not None and self.area_import_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Cancel area import",
                "Area GeoJSON import is still running. Cancel it and close this dialog?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self.area_import_worker.cancel()
            if not self.area_import_worker.wait(3000):
                QMessageBox.information(
                    self,
                    "Cancelling",
                    "Area import is still stopping. Please wait for the cancel operation to finish before closing.",
                )
                return
        if self.encoding_worker is not None and self.encoding_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Cancel encoding",
                "Spatial encoding is still running. Cancel it and close this dialog?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self.encoding_worker.cancel()
            if not self.encoding_worker.wait(3000):
                QMessageBox.information(
                    self,
                    "Cancelling",
                    "Encoding is still stopping. Please wait for the cancel operation to finish before closing.",
                )
                return
        super().reject()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        toolbar = QGroupBox("Import and encode", self)
        toolbar_layout = QHBoxLayout(toolbar)
        self.load_occurrences_button = QPushButton("Load Occurrences CSV", toolbar)
        self.load_occurrences_button.clicked.connect(self._load_occurrences)
        self.load_areas_button = QPushButton("Load Area GeoJSON", toolbar)
        self.load_areas_button.clicked.connect(self._load_areas)
        self.apply_area_edits_button = QPushButton("Apply Area Edits", toolbar)
        self.apply_area_edits_button.clicked.connect(self._apply_area_edits)
        self.min_records_spin = QSpinBox(toolbar)
        self.min_records_spin.setRange(1, 1000000)
        self.min_records_spin.setValue(1)
        self.encode_button = QPushButton("Encode Matrix", toolbar)
        self.encode_button.clicked.connect(self._encode_matrix)
        self.cancel_encode_button = QPushButton("Cancel Encoding", toolbar)
        self.cancel_encode_button.clicked.connect(self._cancel_encoding)
        self.cancel_encode_button.setEnabled(False)
        self.encode_progress_label = QLabel("Ready", toolbar)
        self.encode_progress_bar = QProgressBar(toolbar)
        self.encode_progress_bar.setRange(0, 100)
        self.encode_progress_bar.setValue(0)
        self.export_button = QPushButton("Export Encoded CSV", toolbar)
        self.export_button.clicked.connect(self._export_matrix)
        self.apply_button = QPushButton("Apply Encoded Matrix", toolbar)
        self.apply_button.clicked.connect(self._apply_matrix)

        toolbar_layout.addWidget(self.load_occurrences_button)
        toolbar_layout.addWidget(self.load_areas_button)
        toolbar_layout.addWidget(self.apply_area_edits_button)
        toolbar_layout.addSpacing(12)
        toolbar_layout.addWidget(QLabel("Min records per taxon-area", toolbar))
        toolbar_layout.addWidget(self.min_records_spin)
        toolbar_layout.addSpacing(12)
        toolbar_layout.addWidget(self.encode_button)
        toolbar_layout.addWidget(self.cancel_encode_button)
        toolbar_layout.addWidget(self.encode_progress_label)
        toolbar_layout.addWidget(self.encode_progress_bar)
        toolbar_layout.addWidget(self.export_button)
        toolbar_layout.addWidget(self.apply_button)
        toolbar_layout.addStretch(1)
        layout.addWidget(toolbar)

        project_toolbar = QGroupBox("Project and exports", self)
        project_toolbar_layout = QVBoxLayout(project_toolbar)
        project_toolbar_project_row = QHBoxLayout()
        project_toolbar_export_row = QHBoxLayout()
        self.load_project_button = QPushButton("Load Spatial Project", project_toolbar)
        self.load_project_button.clicked.connect(self._load_project)
        self.save_project_button = QPushButton("Save Spatial Project", project_toolbar)
        self.save_project_button.clicked.connect(self._save_project)
        self.load_area_mapping_button = QPushButton("Load Area Mapping", project_toolbar)
        self.load_area_mapping_button.clicked.connect(self._load_area_mapping)
        self.export_area_mapping_button = QPushButton("Export Area Mapping", project_toolbar)
        self.export_area_mapping_button.clicked.connect(self._export_area_mapping)
        self.auto_area_colors_button = QPushButton("Auto Area Colors", project_toolbar)
        self.auto_area_colors_button.clicked.connect(self._auto_area_colors)
        self.export_taxon_matching_button = QPushButton("Export Taxon Mapping", project_toolbar)
        self.export_taxon_matching_button.clicked.connect(self._export_taxon_matching)
        self.export_audit_button = QPushButton("Export Encoding Audit", project_toolbar)
        self.export_audit_button.clicked.connect(self._export_audit)
        self.show_all_occurrences_button = QPushButton("Show All Occurrences", project_toolbar)
        self.show_all_occurrences_button.clicked.connect(self._toggle_show_all_occurrences)
        self.show_all_audit_button = QPushButton("Show All Audit", project_toolbar)
        self.show_all_audit_button.clicked.connect(self._toggle_show_all_audit)
        self.match_mode_combo = QComboBox(project_toolbar)
        self.match_mode_combo.addItem("Normalized + unique prefix", "normalized_prefix")
        self.match_mode_combo.addItem("Exact only", "exact")
        self.match_mode_combo.currentIndexChanged.connect(self._refresh_summary)
        project_toolbar_project_row.addWidget(self.load_project_button)
        project_toolbar_project_row.addWidget(self.save_project_button)
        project_toolbar_project_row.addSpacing(12)
        project_toolbar_project_row.addWidget(self.load_area_mapping_button)
        project_toolbar_project_row.addWidget(self.export_area_mapping_button)
        project_toolbar_project_row.addWidget(self.auto_area_colors_button)
        project_toolbar_project_row.addStretch(1)
        project_toolbar_export_row.addWidget(QLabel("Taxon-name mapping", project_toolbar))
        project_toolbar_export_row.addWidget(self.match_mode_combo)
        project_toolbar_export_row.addSpacing(12)
        project_toolbar_export_row.addWidget(self.export_taxon_matching_button)
        project_toolbar_export_row.addWidget(self.export_audit_button)
        project_toolbar_export_row.addSpacing(12)
        project_toolbar_export_row.addWidget(self.show_all_occurrences_button)
        project_toolbar_export_row.addWidget(self.show_all_audit_button)
        project_toolbar_export_row.addStretch(1)
        project_toolbar_layout.addLayout(project_toolbar_project_row)
        project_toolbar_layout.addLayout(project_toolbar_export_row)
        layout.addWidget(project_toolbar)

        self.tabs = QTabWidget(self)
        self.occurrence_table = self._new_table()
        self.area_table = self._new_table(editable=True)
        self.audit_table = self._new_table()
        self.map_widget = SpatialMapView(self)
        self.occurrence_table.itemSelectionChanged.connect(self._on_occurrence_table_selection_changed)
        self.area_table.itemSelectionChanged.connect(self._on_area_table_selection_changed)
        self.audit_table.itemSelectionChanged.connect(self._on_audit_table_selection_changed)
        self.map_widget.occurrence_selected.connect(self._on_map_occurrence_selected)
        self.map_widget.area_selected.connect(self._on_map_area_selected)
        self.summary_text = QTextEdit(self)
        self.summary_text.setReadOnly(True)
        self.summary_text.setLineWrapMode(QTextEdit.NoWrap)

        self.tabs.addTab(self.occurrence_table, "Occurrences")
        self.tabs.addTab(self.area_table, "Areas")
        self.tabs.addTab(self.map_widget, "Map Preview")
        self.tabs.addTab(self.audit_table, "Coordinate encoding audit")
        self.tabs.addTab(self.summary_text, "Spatial Project QA")
        layout.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _new_table(self, editable=False):
        table = QTableWidget(self)
        if editable:
            table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked)
        else:
            table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        return table

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
        if dialog.exec_() != QDialog.Accepted:
            return "", ""
        selected_files = dialog.selectedFiles()
        return (selected_files[0] if selected_files else ""), dialog.selectedNameFilter()

    def _load_occurrences(self):
        if self.occurrence_import_worker is not None and self.occurrence_import_worker.isRunning():
            QMessageBox.information(self, "Import in progress", "An occurrence import task is already running.")
            return
        if self.area_import_worker is not None and self.area_import_worker.isRunning():
            QMessageBox.information(self, "Import in progress", "An area import task is already running.")
            return
        if self.encoding_worker is not None and self.encoding_worker.isRunning():
            QMessageBox.information(self, "Encoding in progress", "Wait for the current spatial encoding task to finish first.")
            return
        path, _selected = self._open_file_name(
            "Load occurrences",
            "CSV/TSV files (*.csv *.tsv *.txt);;All files (*)",
        )
        if not path:
            return
        self.occurrence_import_worker = SpatialOccurrenceImportWorker(
            service=self.service,
            file_path=path,
        )
        self.occurrence_import_worker.progress.connect(self._on_task_progress)
        self.occurrence_import_worker.succeeded.connect(self._on_occurrence_import_succeeded)
        self.occurrence_import_worker.failed.connect(self._on_occurrence_import_failed)
        self.occurrence_import_worker.finished.connect(self._on_occurrence_import_finished)
        self.encode_progress_bar.setRange(0, 100)
        self.encode_progress_bar.setValue(0)
        self._set_encoding_running(True, label_text="Loading occurrences ...", cancel_text="Cancel Import")
        self.occurrence_import_worker.start()

    def _on_occurrence_import_succeeded(self, path, records, issues):
        self._project.occurrences = records
        self._project.occurrence_source_path = path
        self._project.qa_issues.extend(issues)
        self._project.encoded_matrix = None
        self._project.encoded_audit_rows = []
        self._show_all_occurrences = False
        self._show_all_audit = False
        self._refresh_all()
        self.encode_progress_bar.setRange(0, 100)
        self.encode_progress_bar.setValue(100)
        self.encode_progress_label.setText("Occurrence import completed")
        QMessageBox.information(
            self,
            "Occurrences loaded",
            "Loaded %d occurrence records. QA issues: %d." % (len(records), len(issues)),
        )

    def _on_occurrence_import_failed(self, message):
        text = str(message or "Occurrence import failed.")
        self.encode_progress_bar.setRange(0, 100)
        self.encode_progress_bar.setValue(0)
        if "cancelled" in text.lower():
            self.encode_progress_label.setText("Occurrence import cancelled")
            QMessageBox.information(self, "Occurrence import cancelled", text)
        else:
            self.encode_progress_label.setText("Occurrence import failed")
            QMessageBox.critical(self, "Occurrence import failed", text)

    def _on_occurrence_import_finished(self):
        self._set_encoding_running(False)
        self.occurrence_import_worker = None

    def _load_areas(self):
        if self.area_import_worker is not None and self.area_import_worker.isRunning():
            QMessageBox.information(self, "Import in progress", "An area import task is already running.")
            return
        if self.occurrence_import_worker is not None and self.occurrence_import_worker.isRunning():
            QMessageBox.information(self, "Import in progress", "Wait for the current occurrence import task to finish first.")
            return
        if self.encoding_worker is not None and self.encoding_worker.isRunning():
            QMessageBox.information(self, "Encoding in progress", "Wait for the current spatial encoding task to finish first.")
            return
        path, _selected = self._open_file_name(
            "Load area polygons",
            "GeoJSON files (*.geojson *.json);;All files (*)",
        )
        if not path:
            return
        self.area_import_worker = SpatialAreaImportWorker(
            service=self.service,
            file_path=path,
        )
        self.area_import_worker.progress.connect(self._on_task_progress)
        self.area_import_worker.succeeded.connect(self._on_area_import_succeeded)
        self.area_import_worker.failed.connect(self._on_area_import_failed)
        self.area_import_worker.finished.connect(self._on_area_import_finished)
        self.encode_progress_bar.setRange(0, 100)
        self.encode_progress_bar.setValue(0)
        self._set_encoding_running(True, label_text="Loading area polygons ...", cancel_text="Cancel Import")
        self.area_import_worker.start()

    def _on_area_import_succeeded(self, path, areas, issues):
        self._project.areas = areas
        self._project.area_source_path = path
        self._project.qa_issues.extend(issues)
        self._project.encoded_matrix = None
        self._project.encoded_audit_rows = []
        self._show_all_audit = False
        self._refresh_all()
        self.encode_progress_bar.setRange(0, 100)
        self.encode_progress_bar.setValue(100)
        self.encode_progress_label.setText("Area import completed")
        QMessageBox.information(
            self,
            "Areas loaded",
            "Loaded %d polygon areas. QA issues: %d." % (len(areas), len(issues)),
        )

    def _on_area_import_failed(self, message):
        text = str(message or "Area import failed.")
        self.encode_progress_bar.setRange(0, 100)
        self.encode_progress_bar.setValue(0)
        if "cancelled" in text.lower():
            self.encode_progress_label.setText("Area import cancelled")
            QMessageBox.information(self, "Area import cancelled", text)
        else:
            self.encode_progress_label.setText("Area import failed")
            QMessageBox.critical(self, "Area import failed", text)

    def _on_area_import_finished(self):
        self._set_encoding_running(False)
        self.area_import_worker = None

    def _apply_area_edits(self):
        if not self._project.areas:
            QMessageBox.warning(self, "Nothing to apply", "Load area polygons first.")
            return
        if self.area_table.rowCount() != len(self._project.areas):
            QMessageBox.warning(
                self,
                "Cannot apply edits",
                "The area table is not synchronized with the loaded area list. Reload the area polygons or spatial project.",
            )
            return
        seen = set()
        for row_index, area in enumerate(self._project.areas):
            code = self._table_text(self.area_table, row_index, 0)
            display_name = self._table_text(self.area_table, row_index, 2)
            color = self._table_text(self.area_table, row_index, 3)
            group = self._table_text(self.area_table, row_index, 4)
            if not code:
                QMessageBox.warning(self, "Invalid area code", "Area code cannot be empty at row %d." % (row_index + 1))
                return
            if code in seen:
                QMessageBox.warning(self, "Duplicate area code", "Duplicate area code: %s." % code)
                return
            seen.add(code)
            area.area_code = code
            area.display_name = display_name
            area.color = color
            area.group = group
        issues = self.service.validate_area_mapping(self._project.areas)
        if any(issue.level == "error" for issue in issues):
            QMessageBox.warning(self, "Invalid area mapping", "\n".join(issue.message for issue in issues[:10]))
            return
        self._project.encoded_matrix = None
        self._project.encoded_audit_rows = []
        self._refresh_all()
        QMessageBox.information(
            self,
            "Area edits applied",
            "Area metadata was updated. Re-run Encode Matrix to rebuild the active area columns.",
        )

    def _encode_matrix(self):
        if self.encoding_worker is not None and self.encoding_worker.isRunning():
            QMessageBox.information(self, "Encoding in progress", "A spatial encoding task is already running.")
            return
        self.encoding_worker = SpatialEncodingWorker(
            service=self.service,
            occurrences=self._project.occurrences,
            areas=self._project.areas,
            min_records_per_taxon_area=self.min_records_spin.value(),
            source_path=self._project.occurrence_source_path or "spatial://encoded_occurrences",
        )
        self.encoding_worker.progress.connect(self._on_encoding_progress)
        self.encoding_worker.succeeded.connect(self._on_encoding_succeeded)
        self.encoding_worker.failed.connect(self._on_encoding_failed)
        self.encoding_worker.finished.connect(self._on_encoding_finished)
        self._set_encoding_running(True)
        self.encoding_worker.start()

    def _cancel_encoding(self):
        if self.occurrence_import_worker is not None and self.occurrence_import_worker.isRunning():
            self.occurrence_import_worker.cancel()
            self.cancel_encode_button.setEnabled(False)
            self.encode_progress_label.setText("Cancelling occurrence import ...")
            return
        if self.area_import_worker is not None and self.area_import_worker.isRunning():
            self.area_import_worker.cancel()
            self.cancel_encode_button.setEnabled(False)
            self.encode_progress_label.setText("Cancelling area import ...")
            return
        if self.encoding_worker is not None and self.encoding_worker.isRunning():
            self.encoding_worker.cancel()
            self.cancel_encode_button.setEnabled(False)
            self.encode_progress_label.setText("Cancelling encoding ...")

    def _on_task_progress(self, done, total, message):
        total = int(total or 0)
        done = int(done or 0)
        percent = int(round(done * 100.0 / total)) if total else 0
        self.encode_progress_bar.setRange(0, 100)
        self.encode_progress_bar.setValue(max(0, min(100, percent)))
        self.encode_progress_label.setText(str(message or "Encoding ..."))

    def _on_encoding_progress(self, done, total, message):
        self._on_task_progress(done, total, message)

    def _on_encoding_succeeded(self, matrix, audit_rows, _diagnostics):
        self._project.encoded_matrix = matrix
        self._project.encoded_audit_rows = list(audit_rows or [])
        self._show_all_audit = False
        self._refresh_all()
        self.tabs.setCurrentWidget(self.audit_table)
        self.encode_progress_bar.setRange(0, 100)
        self.encode_progress_bar.setValue(100)
        self.encode_progress_label.setText("Encoding completed")
        QMessageBox.information(
            self,
            "Encoding completed",
            "Encoded %d taxa across %d areas. Audit rows: %d."
            % (
                len(getattr(matrix, "taxa_names", []) or []),
                len(getattr(matrix, "state_columns", []) or []),
                len(self._project.encoded_audit_rows),
            ),
        )

    def _on_encoding_failed(self, message):
        text = str(message or "Encoding failed.")
        self.encode_progress_bar.setRange(0, 100)
        self.encode_progress_bar.setValue(0)
        if "cancelled" in text.lower():
            self.encode_progress_label.setText("Encoding cancelled")
            QMessageBox.information(self, "Encoding cancelled", text)
        else:
            self.encode_progress_label.setText("Encoding failed")
            QMessageBox.critical(self, "Encoding failed", text)

    def _on_encoding_finished(self):
        self._set_encoding_running(False)
        self.encoding_worker = None

    def _export_matrix(self):
        matrix = self._project.encoded_matrix
        if matrix is None:
            QMessageBox.warning(self, "Nothing to export", "Encode a matrix first.")
            return
        path, _selected = self._save_file_name(
            "Export encoded matrix",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            self.service.write_state_matrix_csv(matrix, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export completed", "Saved encoded matrix to:\n%s" % path)

    def _save_project(self):
        path, _selected = self._save_file_name(
            "Save spatial project",
            "RASP spatial project (*.rasp-spatial.json);;JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".rasp-spatial.json"
        try:
            self.service.save_project_json(self._project, path)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        QMessageBox.information(self, "Project saved", "Saved spatial project to:\n%s" % path)

    def _load_project(self):
        path, _selected = self._open_file_name(
            "Load spatial project",
            "RASP spatial project (*.rasp-spatial.json);;JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            self._project = self.service.load_project_json(path)
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))
            return
        self._show_all_occurrences = False
        self._show_all_audit = False
        self._refresh_all()
        QMessageBox.information(self, "Project loaded", "Loaded spatial project:\n%s" % path)

    def _load_area_mapping(self):
        if not self._project.areas:
            QMessageBox.warning(self, "No areas loaded", "Load area polygons before applying an area mapping file.")
            return
        path, _selected = self._open_file_name(
            "Load area mapping",
            "CSV/TSV files (*.csv *.tsv *.txt);;All files (*)",
        )
        if not path:
            return
        try:
            rows, issues = self.service.read_area_mapping_csv(path)
            report = self.service.apply_area_metadata(self._project.areas, rows)
        except Exception as exc:
            QMessageBox.critical(self, "Load area mapping failed", str(exc))
            return
        self._project.qa_issues.extend(issues)
        self._refresh_all()
        details = [
            "Updated areas: %d" % report.get("updated", 0),
            "Metadata rows without loaded area: %d" % len(report.get("metadata_without_area", []) or []),
            "Loaded areas without metadata: %d" % len(report.get("areas_without_metadata", []) or []),
            "QA issues: %d" % len(issues),
        ]
        QMessageBox.information(self, "Area mapping loaded", "\n".join(details))

    def _export_area_mapping(self):
        if not self._project.areas:
            QMessageBox.warning(self, "Nothing to export", "Load area polygons first.")
            return
        path, _selected = self._save_file_name(
            "Export area mapping",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            self.service.write_area_mapping_csv(self._project.areas, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export completed", "Saved area mapping to:\n%s" % path)

    def _auto_area_colors(self):
        if not self._project.areas:
            QMessageBox.warning(self, "No areas loaded", "Load area polygons first.")
            return
        reply = QMessageBox.question(
            self,
            "Auto area colors",
            "Assign the default color palette to all loaded areas?\n\n"
            "This overwrites existing area colors in the current spatial project.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        count = self.service.assign_default_area_colors(self._project.areas, overwrite=True)
        self._refresh_all()
        QMessageBox.information(self, "Area colors assigned", "Assigned colors to %d areas." % count)

    def _export_taxon_matching(self):
        occurrence_taxa = sorted(set(rec.taxon for rec in list(self._project.occurrences or [])))
        if not (self.tree_taxa or self.matrix_taxa or occurrence_taxa):
            QMessageBox.warning(self, "Nothing to export", "Load a tree, an active matrix, or occurrences first.")
            return
        path, _selected = self._save_file_name(
            "Export taxon matching",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            self.service.write_taxon_mapping_csv(
                self.tree_taxa,
                self.matrix_taxa,
                occurrence_taxa,
                path,
                mode=self._taxon_match_mode(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export completed", "Saved taxon matching report to:\n%s" % path)

    def _export_audit(self):
        if not self._project.encoded_audit_rows:
            QMessageBox.warning(self, "Nothing to export", "Encode a matrix first.")
            return
        path, _selected = self._save_file_name(
            "Export encoding audit",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            self.service.write_encoding_audit_csv(self._project.encoded_audit_rows, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export completed", "Saved encoding audit to:\n%s" % path)

    def _apply_matrix(self):
        matrix = self._project.encoded_matrix
        if matrix is None:
            QMessageBox.warning(self, "Nothing to apply", "Encode a matrix first.")
            return
        if self.apply_matrix_callback is None:
            QMessageBox.warning(self, "Cannot apply", "No project matrix callback is available.")
            return
        try:
            self.apply_matrix_callback(matrix)
        except Exception as exc:
            QMessageBox.critical(self, "Apply failed", str(exc))
            return
        QMessageBox.information(self, "Matrix applied", "The encoded matrix is now the active project matrix.")

    def _refresh_all(self):
        self._refresh_occurrences()
        self._refresh_areas()
        self._refresh_map()
        self._refresh_audit()
        self._refresh_summary()
        self.export_button.setEnabled(self._project.encoded_matrix is not None)
        self.apply_button.setEnabled(self._project.encoded_matrix is not None)
        self.save_project_button.setEnabled(bool(self._project.occurrences or self._project.areas or self._project.encoded_matrix))
        self.apply_area_edits_button.setEnabled(bool(self._project.areas))
        self.load_area_mapping_button.setEnabled(bool(self._project.areas))
        self.export_area_mapping_button.setEnabled(bool(self._project.areas))
        self.auto_area_colors_button.setEnabled(bool(self._project.areas))
        self.export_taxon_matching_button.setEnabled(bool(self.tree_taxa or self.matrix_taxa or self._project.occurrences))
        self.export_audit_button.setEnabled(bool(self._project.encoded_audit_rows))
        occurrence_count = len(self._project.occurrences or [])
        audit_count = len(self._project.encoded_audit_rows or [])
        self.show_all_occurrences_button.setEnabled(occurrence_count > self.OCCURRENCE_PREVIEW_LIMIT)
        self.show_all_audit_button.setEnabled(audit_count > self.AUDIT_PREVIEW_LIMIT)
        self.show_all_occurrences_button.setText(
            "Preview Occurrences" if self._show_all_occurrences else "Show All Occurrences"
        )
        self.show_all_audit_button.setText(
            "Preview Audit" if self._show_all_audit else "Show All Audit"
        )
        if self.occurrence_import_worker is not None and self.occurrence_import_worker.isRunning():
            self._set_encoding_running(True, label_text="Loading occurrences ...", cancel_text="Cancel Import")
        elif self.area_import_worker is not None and self.area_import_worker.isRunning():
            self._set_encoding_running(True, label_text="Loading area polygons ...", cancel_text="Cancel Import")
        elif self.encoding_worker is not None and self.encoding_worker.isRunning():
            self._set_encoding_running(True)

    def _set_encoding_running(self, running, label_text=None, cancel_text=None):
        running = bool(running)
        self.load_occurrences_button.setEnabled(not running)
        self.load_areas_button.setEnabled(not running)
        self.apply_area_edits_button.setEnabled((not running) and bool(self._project.areas))
        self.min_records_spin.setEnabled(not running)
        self.encode_button.setEnabled(not running)
        self.cancel_encode_button.setEnabled(running)
        self.load_project_button.setEnabled(not running)
        self.save_project_button.setEnabled(not running)
        self.load_area_mapping_button.setEnabled((not running) and bool(self._project.areas))
        self.export_area_mapping_button.setEnabled((not running) and bool(self._project.areas))
        self.auto_area_colors_button.setEnabled((not running) and bool(self._project.areas))
        self.export_taxon_matching_button.setEnabled((not running) and bool(self.tree_taxa or self.matrix_taxa or self._project.occurrences))
        self.export_audit_button.setEnabled((not running) and bool(self._project.encoded_audit_rows))
        self.export_button.setEnabled((not running) and self._project.encoded_matrix is not None)
        self.apply_button.setEnabled((not running) and self._project.encoded_matrix is not None)
        self.show_all_occurrences_button.setEnabled((not running) and len(self._project.occurrences or []) > self.OCCURRENCE_PREVIEW_LIMIT)
        self.show_all_audit_button.setEnabled((not running) and len(self._project.encoded_audit_rows or []) > self.AUDIT_PREVIEW_LIMIT)
        if running:
            self.cancel_encode_button.setText(cancel_text or "Cancel Encoding")
            self.encode_progress_bar.setRange(0, 100)
            if self.encode_progress_bar.value() <= 0:
                self.encode_progress_bar.setValue(0)
            self.encode_progress_label.setText(label_text or "Encoding ...")
        else:
            self.cancel_encode_button.setText("Cancel Encoding")

    def _refresh_occurrences(self):
        rows = []
        occurrences = list(self._project.occurrences or [])
        display_records = occurrences if self._show_all_occurrences else occurrences[:self.OCCURRENCE_PREVIEW_LIMIT]
        for rec in display_records:
            rows.append([
                rec.row_index,
                rec.taxon,
                rec.latitude,
                rec.longitude,
                rec.country,
                rec.locality,
                rec.year,
                rec.source,
            ])
        self._set_table(
            self.occurrence_table,
            ["Row", "Taxon", "Latitude", "Longitude", "Country", "Locality", "Year", "Source"],
            rows,
        )

    def _refresh_areas(self):
        rows = []
        for area in list(self._project.areas or [])[:500]:
            rows.append([
                area.area_code,
                area.geometry_id,
                area.display_name,
                area.color,
                getattr(area, "group", ""),
                area.centroid_lon if area.centroid_lon is not None else "",
                area.centroid_lat if area.centroid_lat is not None else "",
                area.crs,
                area.source,
            ])
        self._set_table(
            self.area_table,
            ["Area code", "Geometry ID", "Display name", "Color", "Group", "Centroid lon", "Centroid lat", "CRS", "Source"],
            rows,
            editable_columns={0, 2, 3, 4},
        )

    def _refresh_audit(self):
        rows = []
        audit_rows = list(self._project.encoded_audit_rows or [])
        display_rows = audit_rows if self._show_all_audit else audit_rows[:self.AUDIT_PREVIEW_LIMIT]
        for audit in display_rows:
            rows.append([
                audit.row_index,
                audit.taxon,
                audit.longitude,
                audit.latitude,
                ",".join(audit.matched_areas) if audit.matched_areas else "unmatched",
                self._audit_status_label(audit.status),
            ])
        self._set_table(
            self.audit_table,
            ["Row", "Taxon", "Longitude", "Latitude", "Matched areas", "Coordinate status"],
            rows,
        )

    def _refresh_map(self):
        self.map_widget.set_project(self._project)

    def _on_occurrence_table_selection_changed(self):
        if self._syncing_spatial_selection:
            return
        row_index = self._selected_table_int(self.occurrence_table, 0)
        if row_index is None:
            return
        self._syncing_spatial_selection = True
        try:
            if self.map_widget.select_point_by_row_index(row_index):
                self.tabs.setCurrentWidget(self.map_widget)
        finally:
            self._syncing_spatial_selection = False

    def _on_audit_table_selection_changed(self):
        if self._syncing_spatial_selection:
            return
        row_index = self._selected_table_int(self.audit_table, 0)
        if row_index is None:
            return
        self._syncing_spatial_selection = True
        try:
            if self.map_widget.select_point_by_row_index(row_index):
                self.tabs.setCurrentWidget(self.map_widget)
        finally:
            self._syncing_spatial_selection = False

    def _on_area_table_selection_changed(self):
        if self._syncing_spatial_selection:
            return
        area_code = self._selected_table_text(self.area_table, 0)
        if not area_code:
            return
        self._syncing_spatial_selection = True
        try:
            if self.map_widget.select_area_by_code(area_code):
                self.tabs.setCurrentWidget(self.map_widget)
        finally:
            self._syncing_spatial_selection = False

    def _on_map_occurrence_selected(self, row_index):
        if self._syncing_spatial_selection:
            return
        self._syncing_spatial_selection = True
        try:
            if self._project.encoded_audit_rows:
                if self._select_table_row_by_text(self.audit_table, 0, row_index):
                    return
            self._select_table_row_by_text(self.occurrence_table, 0, row_index)
        finally:
            self._syncing_spatial_selection = False

    def _on_map_area_selected(self, area_code):
        if self._syncing_spatial_selection:
            return
        self._syncing_spatial_selection = True
        try:
            self._select_table_row_by_text(self.area_table, 0, area_code)
        finally:
            self._syncing_spatial_selection = False

    def _refresh_summary(self):
        lines = [
            "Spatial Project QA",
            "",
            "Occurrence source: %s" % (self._project.occurrence_source_path or "None"),
            "Area source: %s" % (self._project.area_source_path or "None"),
            "Occurrence records: %d" % len(self._project.occurrences or []),
            "Area polygons: %d" % len(self._project.areas or []),
        ]
        matrix = self._project.encoded_matrix
        if matrix is not None:
            lines.extend([
                "",
                "Encoded matrix:",
                "  taxa: %d" % len(getattr(matrix, "taxa_names", []) or []),
                "  areas: %d" % len(getattr(matrix, "state_columns", []) or []),
                "  columns: %s" % ", ".join(getattr(matrix, "state_columns", []) or []),
            ])
        occurrence_taxa = sorted(set(rec.taxon for rec in list(self._project.occurrences or [])))
        match = self.service.summarize_taxon_mapping(
            tree_taxa=self.tree_taxa,
            matrix_taxa=self.matrix_taxa,
            occurrence_taxa=occurrence_taxa,
            mode=self._taxon_match_mode(),
        )
        exact = self.service.summarize_taxon_matching(
            tree_taxa=self.tree_taxa,
            matrix_taxa=self.matrix_taxa,
            occurrence_taxa=occurrence_taxa,
        )
        status_counts = dict(match.get("status_counts") or {})
        mode_label = "Exact only" if match.get("mode") == "exact" else "Normalized + unique prefix"
        lines.extend([
            "",
            "Taxon-name mapping QA:",
            "  mode: %s" % mode_label,
            "  target source: %s" % match.get("target_source", ""),
            "  tree taxa: %d" % match["tree_count"],
            "  active matrix taxa: %d" % match["matrix_count"],
            "  occurrence taxa: %d" % match["occurrence_count"],
            "  exact names present in all loaded sources: %d" % len(exact["matched_all"]),
            "  tree taxa matched to target: %d" % match["tree_matched_to_target"],
            "  occurrence taxa matched to target: %d" % match["occurrence_matched_to_target"],
            "  taxon-name status counts: exact=%d, normalized=%d, prefix=%d, ambiguous=%d, unmatched=%d"
            % (
                status_counts.get("exact", 0),
                status_counts.get("normalized", 0),
                status_counts.get("prefix", 0),
                status_counts.get("ambiguous", 0),
                status_counts.get("unmatched", 0),
            ),
            "  note: these counts check taxon labels, not whether coordinates fall inside polygons.",
        ])
        self._append_taxon_match_examples(lines, "taxon-name unmatched tree taxa", match.get("tree_unmatched") or [])
        self._append_taxon_match_examples(lines, "taxon-name ambiguous tree taxa", match.get("tree_ambiguous") or [])
        self._append_taxon_match_examples(lines, "taxon-name unmatched occurrence taxa", match.get("occurrence_unmatched") or [])
        self._append_taxon_match_examples(lines, "taxon-name ambiguous occurrence taxa", match.get("occurrence_ambiguous") or [])

        diagnostics = self.service.build_encoding_diagnostics(
            occurrences=self._project.occurrences,
            areas=self._project.areas,
            matrix=self._project.encoded_matrix,
            audit_rows=self._project.encoded_audit_rows,
        )
        coordinate_status_counts = dict(diagnostics.get("status_counts") or {})
        if coordinate_status_counts:
            lines.extend([
                "",
                "Coordinate encoding QA:",
                "  coordinate status counts: %s" % ", ".join(
                    "%s=%d" % (self._audit_status_label(status), count)
                    for status, count in sorted(coordinate_status_counts.items())
                ),
                "  note: outside_all_polygons means a coordinate did not fall inside any loaded area polygon.",
            ])
            self._append_simple_examples(lines, "areas with no matched occurrence", diagnostics.get("empty_areas") or [])
            self._append_simple_examples(lines, "taxa with all coordinates outside polygons", diagnostics.get("taxa_all_outside_polygons") or [])
            self._append_simple_examples(lines, "taxa with coordinates inside multiple polygons", diagnostics.get("taxa_with_multi_area_points") or [])
            self._append_simple_examples(lines, "encoded taxa with empty range", diagnostics.get("matrix_empty_range_taxa") or [])
            self._append_simple_examples(lines, "taxa filtered to empty by min-record threshold", diagnostics.get("threshold_filtered_empty_taxa") or [])

        area_groups = {}
        for area in list(self._project.areas or []):
            group = str(getattr(area, "group", "") or "").strip()
            if group:
                area_groups[group] = area_groups.get(group, 0) + 1
        if area_groups:
            lines.extend([
                "",
                "Area metadata:",
                "  area groups: %s" % ", ".join("%s=%d" % (key, area_groups[key]) for key in sorted(area_groups)),
            ])

        issues = list(self._project.qa_issues or [])
        lines.extend(["", "QA issues: %d" % len(issues)])
        for issue in issues[-200:]:
            row = " row=%s" % issue.row if issue.row is not None else ""
            taxon = " taxon=%s" % issue.taxon if issue.taxon else ""
            lines.append("  [%s:%s]%s%s %s" % (issue.level, issue.code, row, taxon, issue.message))

        if len(self._project.occurrences or []) > self.OCCURRENCE_PREVIEW_LIMIT:
            lines.append("")
            lines.append(
                "Occurrences table: showing %s of %d records."
                % (
                    "all" if self._show_all_occurrences else "first %d" % self.OCCURRENCE_PREVIEW_LIMIT,
                    len(self._project.occurrences or []),
                )
            )
        if len(self._project.areas or []) > 500:
            lines.append("Area preview is limited to the first 500 records.")
        if len(self._project.encoded_audit_rows or []) > self.AUDIT_PREVIEW_LIMIT:
            lines.append(
                "Encoding audit table: showing %s of %d records."
                % (
                    "all" if self._show_all_audit else "first %d" % self.AUDIT_PREVIEW_LIMIT,
                    len(self._project.encoded_audit_rows or []),
                )
            )
        self.summary_text.setPlainText("\n".join(lines))

    def _toggle_show_all_occurrences(self):
        if not self._show_all_occurrences:
            count = len(self._project.occurrences or [])
            if not self._confirm_show_all("occurrence", count):
                return
        self._show_all_occurrences = not self._show_all_occurrences
        self._refresh_all()

    def _toggle_show_all_audit(self):
        if not self._show_all_audit:
            count = len(self._project.encoded_audit_rows or [])
            if not self._confirm_show_all("encoding audit", count):
                return
        self._show_all_audit = not self._show_all_audit
        self._refresh_all()

    def _confirm_show_all(self, label, count):
        if int(count or 0) <= self.SHOW_ALL_CONFIRM_LIMIT:
            return True
        reply = QMessageBox.question(
            self,
            "Show all rows",
            "Show all %d %s rows?\n\n"
            "This uses QTableWidget for now and may make the dialog slow. "
            "Encoding and export already use the full data even when the table is in preview mode."
            % (count, label),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _set_table(self, table, headers, rows, editable_columns=None):
        editable = set(editable_columns or [])
        table.clear()
        table.setColumnCount(len(headers))
        table.setRowCount(len(rows))
        table.setHorizontalHeaderLabels(headers)
        if len(rows) > 2000:
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        else:
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                if col_index not in editable:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row_index, col_index, item)
        if len(rows) <= 2000:
            table.resizeColumnsToContents()

    def _table_text(self, table, row, column):
        item = table.item(row, column)
        return str(item.text() if item is not None else "").strip()

    def _selected_table_text(self, table, column):
        row = table.currentRow()
        if row < 0:
            selected = table.selectedItems()
            if not selected:
                return ""
            row = selected[0].row()
        return self._table_text(table, row, column)

    def _selected_table_int(self, table, column):
        text = self._selected_table_text(table, column)
        if not text:
            return None
        try:
            return int(float(text))
        except Exception:
            return None

    def _select_table_row_by_text(self, table, column, value):
        needle = str(value or "").strip()
        if not needle:
            return False
        for row in range(table.rowCount()):
            item = table.item(row, column)
            if item is None:
                continue
            if str(item.text()).strip() == needle:
                table.selectRow(row)
                table.scrollToItem(item, QAbstractItemView.PositionAtCenter)
                return True
        return False

    def _append_taxon_match_examples(self, lines, label, rows):
        row_list = list(rows or [])
        if not row_list:
            return
        lines.append("  %s (%d):" % (label, len(row_list)))
        for row in row_list[:20]:
            candidates = str(row.get("candidates", "") or "")
            suffix = " -> %s" % candidates if candidates else ""
            lines.append("    %s%s" % (row.get("source_taxon", ""), suffix))
        if len(row_list) > 20:
            lines.append("    ... %d more" % (len(row_list) - 20))

    def _append_simple_examples(self, lines, label, values):
        value_list = [str(value) for value in list(values or []) if str(value)]
        if not value_list:
            return
        lines.append("  %s (%d): %s" % (label, len(value_list), ", ".join(value_list[:20])))
        if len(value_list) > 20:
            lines.append("    ... %d more" % (len(value_list) - 20))

    def _coordinate_status_counts(self):
        counts = {}
        for row in list(self._project.encoded_audit_rows or []):
            status = str(getattr(row, "status", "") or "")
            if not status:
                continue
            counts[status] = counts.get(status, 0) + 1
        return counts

    def _audit_status_label(self, status):
        return self.service._coordinate_status_label(status)

    def _taxon_match_mode(self):
        value = self.match_mode_combo.currentData() if hasattr(self, "match_mode_combo") else "normalized_prefix"
        return str(value or "normalized_prefix")
