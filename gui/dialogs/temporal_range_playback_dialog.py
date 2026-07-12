import csv
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QSizePolicy,
    QSplitter,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from application.services.temporal_range_playback_service import TemporalRangePlaybackService
from application.services.bsm_branch_history_service import BSMBranchHistoryService
from gui.widgets.temporal_range_map_view import TemporalRangeMapView
from gui.widgets.temporal_range_tree_view import TemporalRangeTreeView


class TemporalRangePlaybackDialog(QDialog):
    SLIDER_STEPS = 1000

    def __init__(
        self,
        *,
        result,
        method_name="",
        leaf_state_map=None,
        area_records=None,
        range_matrix=None,
        bsm_result=None,
        reference_tree=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Spatiotemporal Range Playback")
        self.resize(1380, 820)
        self.setMinimumSize(920, 620)

        self.service = TemporalRangePlaybackService()
        self.timeline = self.service.build(
            result=result,
            method_name=method_name,
            leaf_state_map=leaf_state_map,
            area_records=area_records,
            range_matrix=range_matrix,
            reference_tree=reference_tree,
        )
        self._area_records = list(area_records or [])
        self._bsm_result = bsm_result
        if bsm_result is not None:
            self.timeline = BSMBranchHistoryService().attach(self.timeline, bsm_result)
        self._selected_branch_id = ""
        self.current_frame = None
        self._updating_time_controls = False

        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._advance_playback)

        self.tree_view = TemporalRangeTreeView(self)
        self.tree_view.set_timeline(self.timeline)
        self.tree_view.branch_selected.connect(self._on_branch_selected)
        self.map_view = TemporalRangeMapView(self)
        self.map_view.set_areas(self._area_records)

        self.range_table = QTableWidget(0, 3, self)
        self.range_table.setHorizontalHeaderLabels(["Range", "Probability", "Areas"])
        self.range_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.range_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.area_table = QTableWidget(0, 2, self)
        self.area_table.setHorizontalHeaderLabels(["Area", "Marginal probability"])
        self.area_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.area_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_tabs = QTabWidget(self)
        self.table_tabs.addTab(self.range_table, "Range probabilities")
        self.table_tabs.addTab(self.area_table, "Area marginals")

        self.time_slider = QSlider(Qt.Horizontal, self)
        self.time_slider.setRange(0, self.SLIDER_STEPS)
        self.time_slider.setValue(0)
        self.time_slider.valueChanged.connect(self._on_slider_changed)
        self.time_spin = QDoubleSpinBox(self)
        self.time_spin.setDecimals(6)
        self.time_spin.setRange(0.0, max(0.0, float(self.timeline.root_age)))
        self.time_spin.setValue(float(self.timeline.root_age))
        self.time_spin.setSingleStep(max(0.000001, float(self.timeline.root_age) / 100.0))
        self.time_spin.valueChanged.connect(self._on_spin_changed)

        self.play_button = QToolButton(self)
        self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play_button.setToolTip("Play from root toward the present")
        self.play_button.clicked.connect(self._toggle_playback)
        self.speed_combo = QComboBox(self)
        for label, value in [("0.25x", 0.25), ("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0), ("4x", 4.0)]:
            self.speed_combo.addItem(label, value)
        self.speed_combo.setCurrentIndex(2)

        self.scope_combo = QComboBox(self)
        self.scope_combo.addItem("All active lineages", "all_active_lineages")
        self.scope_combo.addItem("Selected lineage", "selected_lineage")
        self.scope_combo.currentIndexChanged.connect(self._refresh_frame)

        self.node_boundary_combo = QComboBox(self)
        self.node_boundary_combo.addItem("After split", "after_split")
        self.node_boundary_combo.addItem("Before split", "before_split")
        self.node_boundary_combo.currentIndexChanged.connect(self._refresh_frame)

        self.playback_mode_combo = QComboBox(self)
        summary_available = bool(self.timeline.metadata.get("bsm_summary_interactive_available", False))
        history_complete = bool(self.timeline.metadata.get("bsm_history_complete", False))
        if summary_available:
            self.playback_mode_combo.addItem("BSM summary", "bsm_summary")
            self.playback_mode_combo.addItem("Single BSM map", "bsm_sample")
        endpoint_label = "BGB endpoints" if self.timeline.source_kind == "bgb_endpoints" else "Node interpolation"
        if not summary_available:
            self.playback_mode_combo.addItem(endpoint_label, "endpoints")
            if self.timeline.history_segments:
                single_label = "Single BSM map" if history_complete else "Single loaded BSM map"
                self.playback_mode_combo.addItem(single_label, "bsm_sample")
        else:
            self.playback_mode_combo.addItem(endpoint_label, "endpoints")
        self.playback_mode_combo.currentIndexChanged.connect(self._on_playback_mode_changed)
        self.sample_combo = QComboBox(self)
        for sample_id in self.timeline.history_sample_ids:
            self.sample_combo.addItem("Map %s" % sample_id, str(sample_id))
        self.sample_combo.currentIndexChanged.connect(self._refresh_frame)

        self.fit_tree_button = QPushButton("Fit tree", self)
        self.fit_tree_button.clicked.connect(self.tree_view.fit_to_tree)
        self.fit_map_button = QPushButton("Fit map", self)
        self.fit_map_button.clicked.connect(self.map_view.fit_to_map)
        self.export_frame_button = QPushButton("Export frame", self)
        self.export_frame_button.clicked.connect(self._export_frame_csv)
        self.close_button = QPushButton("Close", self)
        self.close_button.clicked.connect(self.close)

        self.time_label = QLabel(self)
        self.branch_label = QLabel("No branch selected", self)
        self.branch_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.mode_label = QLabel(self._mode_text(), self)
        self.mode_label.setWordWrap(True)
        self.mode_label.setStyleSheet("QLabel { color: #3f4a52; }")
        self.sampling_label = QLabel(self._sampling_text(), self)
        self.sampling_label.setWordWrap(True)
        self.sampling_label.setMaximumHeight(64)
        self.sampling_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.warning_label = QLabel(self._warning_text(), self)
        self.warning_label.setWordWrap(True)
        self.warning_label.setMaximumHeight(92)
        self.warning_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.warning_label.setStyleSheet(
            "QLabel { background: #fff5d8; border: 1px solid #d7b85d; padding: 6px; color: #4b411f; }"
        )

        self._build_ui()
        self._refresh_frame()
        QTimer.singleShot(0, self._fit_views)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        time_controls = QHBoxLayout()
        time_controls.addWidget(self.play_button)
        time_controls.addWidget(QLabel("Speed", self))
        time_controls.addWidget(self.speed_combo)
        time_controls.addSpacing(10)
        time_controls.addWidget(QLabel("Time before present", self))
        time_controls.addWidget(self.time_spin)
        time_controls.addWidget(self.time_slider, 1)
        time_controls.addWidget(self.time_label)
        time_controls.addWidget(self.close_button)
        root.addLayout(time_controls)

        display_controls = QHBoxLayout()
        display_controls.addWidget(QLabel("Map scope", self))
        display_controls.addWidget(self.scope_combo)
        display_controls.addSpacing(8)
        display_controls.addWidget(QLabel("At nodes", self))
        display_controls.addWidget(self.node_boundary_combo)
        display_controls.addSpacing(8)
        display_controls.addWidget(QLabel("History", self))
        display_controls.addWidget(self.playback_mode_combo)
        display_controls.addWidget(self.sample_combo)
        display_controls.addStretch(1)
        display_controls.addWidget(self.fit_tree_button)
        display_controls.addWidget(self.fit_map_button)
        display_controls.addWidget(self.export_frame_button)
        root.addLayout(display_controls)

        root.addWidget(self.mode_label)
        root.addWidget(self.sampling_label)
        root.addWidget(self.warning_label)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.map_view, 3)
        right_layout.addWidget(self.branch_label)
        right_layout.addWidget(self.table_tabs, 2)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self.tree_view)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([760, 600])
        root.addWidget(splitter, 1)
        self._sync_history_controls()

    def _fit_views(self):
        self.tree_view.fit_to_tree()
        self.map_view.fit_to_map()

    def _mode_text(self):
        endpoint_count = int(self.timeline.metadata.get("bgb_endpoint_branch_count", 0) or 0)
        branch_count = int(self.timeline.metadata.get("branch_count", 0) or 0)
        selected_mode = "endpoints"
        if hasattr(self, "playback_mode_combo"):
            selected_mode = str(self.playback_mode_combo.currentData() or "endpoints")
        if selected_mode == "bsm_summary":
            mode = "BioGeoBEARS BSM summary playback"
        elif selected_mode == "bsm_sample":
            mode = "BioGeoBEARS single-map playback"
        else:
            mode = "BioGeoBEARS endpoint playback" if endpoint_count else "Node-interpolation playback"
        text = "%s | %s | %d branches" % (self.timeline.source_model_name, mode, branch_count)
        if endpoint_count and selected_mode == "endpoints":
            text += " | %d branches use branch-bottom/top probabilities" % endpoint_count
        if self.timeline.history_segments:
            text += " | %d BSM maps, %d reconstructed state segments" % (
                len(self.timeline.history_sample_ids),
                len(self.timeline.history_segments),
            )
        elif self._bsm_result is not None:
            text += " | BSM rows were loaded but could not be mapped to branches"
        return text

    def _warning_text(self):
        mode = "endpoints"
        if hasattr(self, "playback_mode_combo"):
            mode = str(self.playback_mode_combo.currentData() or "endpoints")
        if mode == "bsm_summary":
            note = (
                "BSM summary probabilities are state frequencies across stochastic maps. "
                "They represent posterior uncertainty, not one definitive history."
            )
        elif mode == "bsm_sample":
            note = (
                "A single BSM map is one sampled biogeographic history. "
                "Use it to inspect event sequences, not as a uniquely inferred history."
            )
        else:
            note = self.timeline.semantics_note
        lines = [note]
        for warning in list(self.timeline.warnings or []):
            if mode.startswith("bsm_") and "lack complete BioGeoBEARS endpoints" in str(warning):
                continue
            lines.append(warning)
        return "\n".join(line for line in lines if line)

    def _sampling_text(self):
        diagnostics = dict(self.timeline.metadata.get("bsm_sampling_diagnostics", {}) or {})
        if not diagnostics:
            return ""
        count = int(diagnostics.get("map_count", 0) or 0)
        half_width = diagnostics.get("worst_case_mc95_half_width")
        error_text = "unknown" if half_width is None else "±%.1f pp" % (100.0 * float(half_width))
        text = "%s BSM sampling: %d maps; conservative worst-case 95%% Monte Carlo half-width %s" % (
            diagnostics.get("sampling_label", ""),
            count,
            error_text,
        )
        p95 = diagnostics.get("split_half_p95_total_variation")
        if p95 is not None:
            text += "; split-half stability %s, p95 total variation %.1f pp across %d branch-time checks" % (
                str(diagnostics.get("stability_label", "")),
                100.0 * float(p95),
                int(diagnostics.get("split_half_query_count", 0) or 0),
            )
        text += ". Sampling diagnostics do not test model adequacy."
        return text

    def _style_sampling_label(self):
        diagnostics = dict(self.timeline.metadata.get("bsm_sampling_diagnostics", {}) or {})
        tier = diagnostics.get("sampling_tier")
        stability = diagnostics.get("stability_status")
        if tier in ("debug_only", "preview") or stability == "high_variation":
            color, border = "#fff0e6", "#cf6b32"
        elif tier == "exploratory" or stability == "moderate":
            color, border = "#fff7d6", "#b7962e"
        else:
            color, border = "#eef7f0", "#568a61"
        self.sampling_label.setStyleSheet(
            "QLabel { background: %s; border: 1px solid %s; padding: 6px; color: #30343a; }"
            % (color, border)
        )

    def _on_slider_changed(self, value):
        if self._updating_time_controls:
            return
        root_age = float(self.timeline.root_age)
        age = root_age * (1.0 - (float(value) / float(self.SLIDER_STEPS)))
        self._set_time(age, source="slider")

    def _on_spin_changed(self, value):
        if self._updating_time_controls:
            return
        self._set_time(float(value), source="spin")

    def _set_time(self, age, source=""):
        root_age = float(self.timeline.root_age)
        age = max(0.0, min(root_age, float(age)))
        self._updating_time_controls = True
        try:
            if source != "spin":
                self.time_spin.setValue(age)
            if source != "slider":
                value = 0 if root_age <= 0.0 else int(round((1.0 - age / root_age) * self.SLIDER_STEPS))
                self.time_slider.setValue(max(0, min(self.SLIDER_STEPS, value)))
        finally:
            self._updating_time_controls = False
        self._refresh_frame()

    def _refresh_frame(self, *args):
        scope = str(self.scope_combo.currentData() or "all_active_lineages")
        playback_mode = str(self.playback_mode_combo.currentData() or "endpoints")
        sample_id = str(self.sample_combo.currentData() or "")
        node_boundary_mode = str(self.node_boundary_combo.currentData() or "after_split")
        frame = self.service.frame(
            self.timeline,
            float(self.time_spin.value()),
            selected_branch_id=self._selected_branch_id,
            display_scope=scope,
            history_mode=playback_mode,
            sample_id=sample_id,
            node_boundary_mode=node_boundary_mode,
        )
        self.current_frame = frame
        self.tree_view.set_frame(frame)
        scope_label = (
            "Selected lineage" if scope == "selected_lineage" and self._selected_branch_id
            else "Mean across %d active lineages" % frame.active_branch_count
        )
        self.map_view.set_probabilities(frame.area_probabilities, scope_label=scope_label)
        self.time_label.setText("%.6g / %.6g" % (float(frame.time), float(self.timeline.root_age)))
        self._populate_tables(frame)

    def _export_frame_csv(self):
        frame = self.current_frame
        if frame is None:
            return
        default_name = "spatiotemporal_range_frame_%g.csv" % float(frame.time)
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Spatiotemporal Range Frame",
            default_name,
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            self._write_frame_csv(Path(path), frame)
        except Exception as exc:
            QMessageBox.warning(self, "Export frame", str(exc))

    def _write_frame_csv(self, target, frame=None):
        frame = frame or self.current_frame
        if frame is None:
            raise ValueError("No playback frame is available.")
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "record_type",
                    "time_before_present",
                    "history_mode",
                    "node_boundary_mode",
                    "display_scope",
                    "branch_id",
                    "state_or_area",
                    "probability",
                ],
            )
            writer.writeheader()
            for branch_id, probabilities in sorted(frame.active_branch_probabilities.items()):
                for state, probability in sorted(probabilities.items(), key=lambda item: (-float(item[1]), str(item[0]))):
                    writer.writerow({
                        "record_type": "branch_range_probability",
                        "time_before_present": "%.12g" % float(frame.time),
                        "history_mode": frame.history_mode,
                        "node_boundary_mode": frame.node_boundary_mode,
                        "display_scope": frame.display_scope,
                        "branch_id": branch_id,
                        "state_or_area": state,
                        "probability": "%.12g" % float(probability),
                    })
            for area, probability in sorted(frame.area_probabilities.items()):
                writer.writerow({
                    "record_type": "map_area_marginal_probability",
                    "time_before_present": "%.12g" % float(frame.time),
                    "history_mode": frame.history_mode,
                    "node_boundary_mode": frame.node_boundary_mode,
                    "display_scope": frame.display_scope,
                    "branch_id": frame.selected_branch_id,
                    "state_or_area": area,
                    "probability": "%.12g" % float(probability),
                })

    def _on_playback_mode_changed(self, *args):
        self._sync_history_controls()
        self._refresh_frame()

    def _sync_history_controls(self):
        mode = str(self.playback_mode_combo.currentData() or "endpoints")
        self.sample_combo.setVisible(mode == "bsm_sample")
        self.sample_combo.setEnabled(mode == "bsm_sample" and self.sample_combo.count() > 0)
        if hasattr(self, "sampling_label"):
            self.sampling_label.setText(self._sampling_text())
            self.sampling_label.setToolTip(self.sampling_label.text())
            self.sampling_label.setVisible(mode.startswith("bsm_") and bool(self.sampling_label.text()))
            self._style_sampling_label()
        if hasattr(self, "warning_label"):
            self.warning_label.setText(self._warning_text())
            self.warning_label.setToolTip(self.warning_label.text())
            self.warning_label.setVisible(bool(self.warning_label.text()))
        if hasattr(self, "mode_label"):
            self.mode_label.setText(self._mode_text())

    def _on_branch_selected(self, branch_id):
        self._selected_branch_id = str(branch_id or "")
        branch = self.timeline.branch_by_id(self._selected_branch_id)
        if branch is not None:
            self.branch_label.setText(
                "%s: node %s -> %s, time %.6g to %.6g, %s"
                % (
                    branch.branch_id,
                    branch.parent_node_id or "?",
                    branch.child_node_id or "?",
                    float(branch.older_time),
                    float(branch.younger_time),
                    branch.interpolation_mode,
                )
            )
        self.scope_combo.setCurrentIndex(1)
        self._refresh_frame()

    def _populate_tables(self, frame):
        probabilities = dict(frame.selected_range_probabilities or {})
        if (
            not probabilities
            and frame.display_scope != "selected_lineage"
            and frame.active_branch_probabilities
        ):
            probabilities = self._mean_range_probabilities(frame.active_branch_probabilities.values())
        ordered = sorted(probabilities.items(), key=lambda item: (-float(item[1]), str(item[0])))
        self.range_table.setRowCount(len(ordered))
        for row, (state, value) in enumerate(ordered):
            areas = ", ".join(self.timeline.state_area_members.get(state, []) or []) or "null/other"
            self.range_table.setItem(row, 0, QTableWidgetItem(str(state)))
            self.range_table.setItem(row, 1, QTableWidgetItem("%.3f%%" % (float(value) * 100.0)))
            self.range_table.setItem(row, 2, QTableWidgetItem(areas))
        self.range_table.resizeColumnsToContents()

        area_rows = sorted(frame.area_probabilities.items(), key=lambda item: (-float(item[1]), str(item[0])))
        self.area_table.setRowCount(len(area_rows))
        for row, (area, value) in enumerate(area_rows):
            self.area_table.setItem(row, 0, QTableWidgetItem(str(area)))
            self.area_table.setItem(row, 1, QTableWidgetItem("%.3f%%" % (float(value) * 100.0)))
        self.area_table.resizeColumnsToContents()

    def _mean_range_probabilities(self, rows):
        rows = [dict(row or {}) for row in rows if row]
        if not rows:
            return {}
        labels = set()
        for row in rows:
            labels.update(row.keys())
        return dict((label, sum(float(row.get(label, 0.0)) for row in rows) / float(len(rows))) for label in labels)

    def _toggle_playback(self):
        if self.timer.isActive():
            self.timer.stop()
            self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            return
        if self.time_slider.value() >= self.SLIDER_STEPS:
            self.time_slider.setValue(0)
        self.timer.start()
        self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def _advance_playback(self):
        speed = float(self.speed_combo.currentData() or 1.0)
        increment = max(1, int(round(2.0 * speed)))
        next_value = self.time_slider.value() + increment
        if next_value >= self.SLIDER_STEPS:
            self.time_slider.setValue(self.SLIDER_STEPS)
            self.timer.stop()
            self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            return
        self.time_slider.setValue(next_value)

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)
