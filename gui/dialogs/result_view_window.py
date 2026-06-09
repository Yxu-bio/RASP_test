from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
import math

from PyQt5.QtWidgets import (
    QAction,
    QCheckBox,
    QComboBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from application.services.export_service import ExportService
from application.services.result_schema_adapter import ResultSchemaAdapterFactory
from gui.widgets.node_info_panel import NodeInfoPanel
from gui.widgets.tree_graph_panel import TreeGraphPanel


class ContinuousFigureGroupDialog(QDialog):
    def __init__(self, group: dict = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Figure Group")
        self._group = dict(group or {})
        self._color = str(self._group.get("color", "") or "#6d6ab1")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(str(self._group.get("name", "") or ""), self)
        self.short_label_edit = QLineEdit(str(self._group.get("short_label", "") or ""), self)

        self.color_button = QPushButton(self)
        self.color_button.clicked.connect(self._choose_color)
        self._sync_color_button()

        taxa = list(self._group.get("taxa", []) or [])
        clade_key = str(self._group.get("clade_key", "") or "")
        self.clade_label = QLabel("%d taxa" % len(taxa), self)
        self.clade_label.setWordWrap(True)
        self.clade_label.setToolTip(clade_key)

        self.distribution_check = QCheckBox("C panel distribution", self)
        self.distribution_check.setChecked(bool(self._group.get("show_in_distribution", True)))
        self.marker_check = QCheckBox("A panel marker", self)
        self.marker_check.setChecked(bool(self._group.get("show_marker_on_tree", True)))

        form.addRow("Name:", self.name_edit)
        form.addRow("Short label:", self.short_label_edit)
        form.addRow("Color:", self.color_button)
        form.addRow("Clade:", self.clade_label)
        form.addRow("", self.distribution_check)
        form.addRow("", self.marker_check)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._color), self)
        if color.isValid():
            self._color = str(color.name())
            self._sync_color_button()

    def _sync_color_button(self) -> None:
        self.color_button.setText(self._color)
        self.color_button.setStyleSheet(
            "QPushButton { background-color: %s; color: %s; }"
            % (self._color, self._text_color_for_background(self._color))
        )

    def _text_color_for_background(self, color: str) -> str:
        try:
            raw = str(color or "").strip().lstrip("#")
            red = int(raw[0:2], 16)
            green = int(raw[2:4], 16)
            blue = int(raw[4:6], 16)
            luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255.0
            return "#111111" if luminance > 0.62 else "#ffffff"
        except Exception:
            return "#ffffff"

    def group_data(self) -> dict:
        group = dict(self._group)
        group["name"] = str(self.name_edit.text() or "").strip()
        group["short_label"] = str(self.short_label_edit.text() or "").strip()
        group["color"] = self._color
        group["show_in_distribution"] = bool(self.distribution_check.isChecked())
        group["show_marker_on_tree"] = bool(self.marker_check.isChecked())
        group.setdefault("show_regime_on_branches", False)
        return group


class ResultViewWindow(QMainWindow):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("结果视图")
        self.resize(1200, 800)

        self.renderer = None
        self.current_result = None
        self.current_method_name = ""
        self.current_selected_clade_key = ""
        self.current_payload = None

        self.result_adapter = None
        self.standard_node_payloads = {}
        self._updating_continuous_scale_controls = False

        self.export_service = ExportService()
        self.leaf_state_map = {}

        self.tree_panel = TreeGraphPanel()
        self.node_info_panel = NodeInfoPanel()
        self.figure_group_box = self._build_figure_group_panel()
        self.figure_group_box.setVisible(False)

        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(4)
        self.right_layout.addWidget(self.node_info_panel, 4)
        self.right_layout.addWidget(self.figure_group_box, 1)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.tree_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([960, 240])
        self.setCentralWidget(self.splitter)

        self._build_toolbar()
        self._bind_signals()

        self.statusBar().showMessage("结果窗口已就绪")

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("视图工具")

        fit_action = QAction("适应窗口", self)
        fit_action.triggered.connect(self.tree_panel.fit_to_view)
        toolbar.addAction(fit_action)

        zoom_in_action = QAction("放大", self)
        zoom_in_action.triggered.connect(self.tree_panel.zoom_in)
        toolbar.addAction(zoom_in_action)

        zoom_out_action = QAction("缩小", self)
        zoom_out_action.triggered.connect(self.tree_panel.zoom_out)
        toolbar.addAction(zoom_out_action)

        reset_action = QAction("重置", self)
        reset_action.triggered.connect(self.tree_panel.reset_zoom)
        toolbar.addAction(reset_action)

        toolbar.addSeparator()

        self.show_leaf_name_action = QAction("显示名称", self)
        self.show_leaf_name_action.setCheckable(True)
        self.show_leaf_name_action.setChecked(True)
        self.show_leaf_name_action.triggered.connect(self._toggle_leaf_name)
        toolbar.addAction(self.show_leaf_name_action)

        self.show_branch_length_action = QAction("显示分支长度", self)
        self.show_branch_length_action.setCheckable(True)
        self.show_branch_length_action.setChecked(False)
        self.show_branch_length_action.triggered.connect(self._toggle_branch_length)
        toolbar.addAction(self.show_branch_length_action)

        self.show_branch_support_action = QAction("显示支持率", self)
        self.show_branch_support_action.setCheckable(True)
        self.show_branch_support_action.setChecked(False)
        self.show_branch_support_action.triggered.connect(self._toggle_branch_support)
        toolbar.addAction(self.show_branch_support_action)

        self.circular_tree_action = QAction("环形树", self)
        self.circular_tree_action.setCheckable(True)
        self.circular_tree_action.setChecked(False)
        self.circular_tree_action.triggered.connect(self._toggle_circular_tree)
        toolbar.addAction(self.circular_tree_action)

        toolbar.addSeparator()

        self.continuous_display_label = QLabel("Display:", self)
        self.continuous_display_combo = QComboBox(self)
        self.continuous_display_combo.addItem("Analysis", "analysis")
        self.continuous_display_combo.addItem("Original", "original")
        self.continuous_display_combo.currentIndexChanged.connect(self._on_continuous_display_scale_changed)
        self.continuous_color_label = QLabel("Color:", self)
        self.continuous_color_combo = QComboBox(self)
        self.continuous_color_combo.addItem("Analysis", "analysis")
        self.continuous_color_combo.addItem("Original", "original")
        self.continuous_color_combo.currentIndexChanged.connect(self._on_continuous_plot_scale_changed)
        self.continuous_display_action = toolbar.addWidget(self.continuous_display_label)
        self.continuous_display_combo_action = toolbar.addWidget(self.continuous_display_combo)
        self.continuous_color_action = toolbar.addWidget(self.continuous_color_label)
        self.continuous_color_combo_action = toolbar.addWidget(self.continuous_color_combo)
        for action in [
            self.continuous_display_action,
            self.continuous_display_combo_action,
            self.continuous_color_action,
            self.continuous_color_combo_action,
        ]:
            action.setVisible(False)

        toolbar.addSeparator()

        export_png_action = QAction("导出PNG", self)
        export_png_action.triggered.connect(self._export_png)
        toolbar.addAction(export_png_action)

        export_svg_action = QAction("导出SVG", self)
        export_svg_action.triggered.connect(self._export_svg)
        toolbar.addAction(export_svg_action)

        export_csv_action = QAction("导出CSV", self)
        export_csv_action.triggered.connect(self._export_csv)
        toolbar.addAction(export_csv_action)

        export_pdf_action = QAction("导出PDF", self)
        export_pdf_action.triggered.connect(self._export_pdf)
        toolbar.addAction(export_pdf_action)

        self.export_continuous_figure_action = QAction("Export Figure", self)
        self.export_continuous_figure_action.triggered.connect(self._export_continuous_figure)
        toolbar.addAction(self.export_continuous_figure_action)
        self.export_continuous_figure_action.setVisible(False)

    def _build_figure_group_panel(self):
        box = QGroupBox("Figure Groups", self)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.figure_group_list = QListWidget(box)
        self.figure_group_list.itemDoubleClicked.connect(self._edit_selected_figure_group)
        self.figure_group_list.currentRowChanged.connect(self._sync_figure_group_buttons)
        layout.addWidget(self.figure_group_list, 1)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(4)

        self.figure_group_add_button = QPushButton("Add Selected", box)
        self.figure_group_add_button.clicked.connect(self._add_figure_group_from_selection)
        self.figure_group_edit_button = QPushButton("Edit", box)
        self.figure_group_edit_button.clicked.connect(self._edit_selected_figure_group)
        self.figure_group_delete_button = QPushButton("Delete", box)
        self.figure_group_delete_button.clicked.connect(self._delete_selected_figure_group)

        button_layout.addWidget(self.figure_group_add_button)
        button_layout.addWidget(self.figure_group_edit_button)
        button_layout.addWidget(self.figure_group_delete_button)
        layout.addLayout(button_layout)
        return box

    def _bind_signals(self) -> None:
        self.tree_panel.node_clicked.connect(self.show_node_payload)
        self.node_info_panel.state_color_changed.connect(self._on_state_color_changed)
        self.node_info_panel.node_entry_clicked.connect(self._on_node_entry_clicked)

    def set_renderer(self, renderer) -> None:
        self.renderer = renderer
        self.tree_panel.set_renderer(renderer)

    def set_result(self, result) -> None:
        self.current_result = result
        self._ensure_continuous_plot_values()
        if self._is_continuous_result():
            self._apply_continuous_display_scale_payloads()
        self._rebuild_standard_context()
        self._sync_node_info_panel()
        self._configure_continuous_scale_controls()
        self._refresh_figure_group_panel()

    def set_window_title_by_method(self, method_name: str) -> None:
        self.current_method_name = method_name or ""
        self.setWindowTitle(f"结果视图 - {self.current_method_name}")
        self._rebuild_standard_context()
        self._sync_node_info_panel()
        self._configure_continuous_scale_controls()
        self._refresh_figure_group_panel()

    def set_leaf_state_context(self, leaf_state_map: dict) -> None:
        self.leaf_state_map = dict(leaf_state_map or {})

    def refresh_view(self) -> None:
        self.tree_panel.refresh_tree()

    def _rebuild_standard_context(self) -> None:
        self.result_adapter = None
        self.standard_node_payloads = {}

        if self.current_result is None:
            return

        self.result_adapter = ResultSchemaAdapterFactory.create(self.current_result)
        standard_result = self.result_adapter.to_standard_result(
            self.current_result,
            method_name=self.current_method_name or getattr(self.result_adapter, "method_name", ""),
        )
        self.standard_node_payloads = dict(standard_result.node_payloads)

    def _sync_node_info_panel(self) -> None:
        payloads = list(self.standard_node_payloads.values())
        self.node_info_panel.set_standard_result(
            method_name=self.current_method_name,
            result=self.current_result,
            node_payloads=payloads,
        )

    def _is_continuous_result(self) -> bool:
        return type(self.current_result).__name__ == "ContinuousTraitResult"

    def _configure_continuous_scale_controls(self) -> None:
        if not hasattr(self, "continuous_display_combo"):
            return

        is_continuous = self._is_continuous_result()
        transform = str(getattr(self.current_result, "trait_transform", "none") or "none") if is_continuous else "none"
        enabled = bool(is_continuous and transform != "none")

        for action in [
            self.continuous_display_action,
            self.continuous_display_combo_action,
            self.continuous_color_action,
            self.continuous_color_combo_action,
        ]:
            action.setVisible(is_continuous)
        if hasattr(self, "export_continuous_figure_action"):
            self.export_continuous_figure_action.setVisible(is_continuous)
        if hasattr(self, "figure_group_box"):
            self.figure_group_box.setVisible(is_continuous)
            self._sync_figure_group_buttons()

        self._updating_continuous_scale_controls = True
        try:
            self.continuous_display_combo.setEnabled(enabled)
            self.continuous_color_combo.setEnabled(enabled)
            display_scale = str(getattr(self.current_result, "trait_display_scale", "analysis") or "analysis") if is_continuous else "analysis"
            plot_scale = str(getattr(self.current_result, "trait_plot_scale", "analysis") or "analysis") if is_continuous else "analysis"
            if transform == "none":
                display_scale = "analysis"
                plot_scale = "analysis"
            self._set_combo_data(self.continuous_display_combo, display_scale)
            self._set_combo_data(self.continuous_color_combo, plot_scale)
        finally:
            self._updating_continuous_scale_controls = False

    def _set_combo_data(self, combo, value) -> None:
        value = str(value or "")
        for index in range(combo.count()):
            if str(combo.itemData(index) or "") == value:
                combo.setCurrentIndex(index)
                return

    def _figure_groups(self) -> list:
        if not self._is_continuous_result():
            return []
        groups = getattr(self.current_result, "figure_groups", None)
        if not isinstance(groups, list):
            groups = []
            self.current_result.figure_groups = groups
        return groups

    def _refresh_figure_group_panel(self) -> None:
        if not hasattr(self, "figure_group_list"):
            return
        self.figure_group_list.blockSignals(True)
        self.figure_group_list.clear()
        for index, group in enumerate(self._figure_groups()):
            group = self._normalise_figure_group(group, index)
            name = str(group.get("name", "") or "Group %d" % (index + 1))
            short_label = str(group.get("short_label", "") or "")
            taxa_count = len(list(group.get("taxa", []) or []))
            flags = []
            if group.get("show_marker_on_tree") is not False:
                flags.append("A")
            if group.get("show_in_distribution") is not False:
                flags.append("C")
            flag_text = ",".join(flags) if flags else "-"
            label = "%s%s (%d taxa; %s)" % (
                ("%s: " % short_label) if short_label else "",
                name,
                taxa_count,
                flag_text,
            )
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, index)
            self.figure_group_list.addItem(item)
        self.figure_group_list.blockSignals(False)
        self._sync_figure_group_buttons()

    def _normalise_figure_group(self, group: dict, index: int = 0) -> dict:
        group = dict(group or {})
        clade_key = str(group.get("clade_key", "") or "").strip()
        taxa = group.get("taxa")
        if not isinstance(taxa, (list, tuple)):
            taxa = clade_key.split("|") if clade_key else []
        taxa = sorted({str(taxon).strip() for taxon in taxa if str(taxon).strip()})
        if not clade_key and taxa:
            clade_key = "|".join(taxa)
        group["clade_key"] = clade_key
        group["taxa"] = taxa
        group["name"] = str(group.get("name", "") or "Group %d" % (index + 1)).strip()
        group["short_label"] = str(group.get("short_label", "") or "G%d" % (index + 1)).strip()
        group["color"] = str(group.get("color", "") or self._default_figure_group_color(index)).strip()
        group["show_in_distribution"] = bool(group.get("show_in_distribution", True))
        group["show_marker_on_tree"] = bool(group.get("show_marker_on_tree", True))
        group["show_regime_on_branches"] = bool(group.get("show_regime_on_branches", False))
        group.setdefault("id", "group_%d" % (index + 1))
        return group

    def _default_figure_group_color(self, index: int) -> str:
        palette = ["#6d6ab1", "#78b7c5", "#88c999", "#e07a5f", "#c95768", "#a17c6b", "#7f7f7f"]
        return palette[int(index) % len(palette)]

    def _selected_figure_group_index(self):
        if not hasattr(self, "figure_group_list"):
            return None
        item = self.figure_group_list.currentItem()
        if item is None:
            return None
        try:
            index = int(item.data(Qt.UserRole))
        except Exception:
            return None
        if index < 0 or index >= len(self._figure_groups()):
            return None
        return index

    def _sync_figure_group_buttons(self, *args) -> None:
        if not hasattr(self, "figure_group_add_button"):
            return
        is_continuous = self._is_continuous_result()
        can_add = bool(is_continuous and self._selected_taxa_from_current_clade())
        can_edit = bool(is_continuous and self._selected_figure_group_index() is not None)
        self.figure_group_add_button.setEnabled(can_add)
        self.figure_group_edit_button.setEnabled(can_edit)
        self.figure_group_delete_button.setEnabled(can_edit)

    def _selected_taxa_from_current_clade(self) -> list:
        clade_key = str(self.current_selected_clade_key or "").strip()
        if not clade_key:
            return []
        taxa = [item for item in clade_key.split("|") if item]
        return taxa if len(taxa) > 1 else []

    def _add_figure_group_from_selection(self) -> None:
        if not self._is_continuous_result():
            return
        taxa = self._selected_taxa_from_current_clade()
        if not taxa:
            QMessageBox.warning(self, "Figure Group", "Select an internal node first.")
            return
        groups = [self._normalise_figure_group(group, index) for index, group in enumerate(self._figure_groups())]
        index = len(groups)
        group = {
            "id": "group_%d" % (index + 1),
            "name": "Group %d" % (index + 1),
            "short_label": "G%d" % (index + 1),
            "color": self._default_figure_group_color(index),
            "clade_key": str(self.current_selected_clade_key or "").strip(),
            "taxa": taxa,
            "show_in_distribution": True,
            "show_marker_on_tree": True,
            "show_regime_on_branches": False,
        }
        dialog = ContinuousFigureGroupDialog(group, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        group = self._normalise_figure_group(dialog.group_data(), index)
        if not group.get("name"):
            QMessageBox.warning(self, "Figure Group", "Group name is required.")
            return
        groups.append(group)
        self._set_figure_groups(groups)

    def _edit_selected_figure_group(self, *args) -> None:
        if not self._is_continuous_result():
            return
        index = self._selected_figure_group_index()
        if index is None:
            return
        groups = [self._normalise_figure_group(group, i) for i, group in enumerate(self._figure_groups())]
        dialog = ContinuousFigureGroupDialog(groups[index], self)
        if dialog.exec_() != QDialog.Accepted:
            return
        group = self._normalise_figure_group(dialog.group_data(), index)
        if not group.get("name"):
            QMessageBox.warning(self, "Figure Group", "Group name is required.")
            return
        groups[index] = group
        self._set_figure_groups(groups)
        self.figure_group_list.setCurrentRow(index)

    def _delete_selected_figure_group(self) -> None:
        index = self._selected_figure_group_index()
        if index is None:
            return
        groups = [self._normalise_figure_group(group, i) for i, group in enumerate(self._figure_groups())]
        del groups[index]
        self._set_figure_groups(groups)

    def _set_figure_groups(self, groups: list) -> None:
        if not self._is_continuous_result():
            return
        groups = [self._normalise_figure_group(group, index) for index, group in enumerate(groups or [])]
        self.current_result.figure_groups = groups
        self.current_result.figure_group_order = [
            group["name"]
            for group in groups
            if group.get("show_in_distribution") is not False
        ]
        self.current_result.figure_group_colors = {
            group["name"]: group["color"]
            for group in groups
            if group.get("name") and group.get("color")
        }
        stats = dict(getattr(self.current_result, "model_statistics", {}) or {})
        stats["figure_groups"] = groups
        stats["figure_group_order"] = list(self.current_result.figure_group_order)
        stats["figure_group_colors"] = dict(self.current_result.figure_group_colors)
        self.current_result.model_statistics = stats
        self._refresh_figure_group_panel()
        if self.renderer is not None:
            self.renderer.set_result(self.current_result)
            if self.current_selected_clade_key:
                self.renderer.select_node_by_clade_key(self.current_selected_clade_key)
            self.tree_panel.refresh_tree(preserve_view=True)

    def _continuous_scale_label(self, scale: str) -> str:
        scale = str(scale or "analysis")
        transform = str(getattr(self.current_result, "trait_transform", "none") or "none")
        if scale == "original" and transform != "none":
            return "Original scale (back-transformed)"
        if transform == "log":
            return "Natural log (ln)"
        if transform == "log10":
            return "Log10"
        return "None"

    def _ensure_continuous_plot_values(self) -> None:
        if not self._is_continuous_result():
            return

        result = self.current_result
        transform = str(getattr(result, "trait_transform", "none") or "none")
        if transform == "none":
            result.trait_display_scale = "analysis"
            result.trait_plot_scale = "analysis"
        elif not str(getattr(result, "trait_display_scale", "") or ""):
            result.trait_display_scale = "original"
        elif str(getattr(result, "trait_display_scale", "analysis") or "analysis") == "analysis":
            # New results default to readable original-scale labels while colors stay on analysis scale.
            result.trait_display_scale = "original"
        if not str(getattr(result, "trait_plot_scale", "") or ""):
            result.trait_plot_scale = "analysis"

        result.original_tip_values = self._continuous_original_tip_values(result)
        result.analysis_node_values = self._continuous_analysis_node_values(result)
        result.original_node_values = self._continuous_original_node_values(result)
        self._apply_continuous_plot_scale_values()

    def _continuous_original_tip_values(self, result) -> dict:
        values = {str(k): float(v) for k, v in dict(getattr(result, "tip_values", {}) or {}).items()}
        transform = str(getattr(result, "trait_transform", "none") or "none")
        existing = dict(getattr(result, "original_tip_values", {}) or {})
        if existing:
            return {str(k): float(v) for k, v in existing.items()}
        if transform == "log":
            return {taxon: math.exp(value) for taxon, value in values.items()}
        if transform == "log10":
            return {taxon: 10.0 ** value for taxon, value in values.items()}
        return dict(values)

    def _continuous_analysis_node_values(self, result) -> dict:
        existing = dict(getattr(result, "analysis_node_values", {}) or {})
        if existing:
            return {str(k): float(v) for k, v in existing.items()}
        return {
            str(key): float(getattr(node, "mean", 0.0) or 0.0)
            for key, node in dict(getattr(result, "node_results", {}) or {}).items()
        }

    def _continuous_original_node_values(self, result) -> dict:
        existing = dict(getattr(result, "original_node_values", {}) or {})
        if existing:
            return {str(k): float(v) for k, v in existing.items()}

        transform = str(getattr(result, "trait_transform", "none") or "none")
        values = {}
        for key, node in dict(getattr(result, "node_results", {}) or {}).items():
            payload = dict(getattr(node, "raw_method_payload", {}) or {})
            if "original_mean" in payload:
                values[str(key)] = float(payload.get("original_mean", 0.0) or 0.0)
                continue
            analysis_value = float(getattr(node, "mean", 0.0) or 0.0)
            if transform == "log":
                values[str(key)] = math.exp(analysis_value)
            elif transform == "log10":
                values[str(key)] = 10.0 ** analysis_value
            else:
                values[str(key)] = analysis_value
        return values

    def _apply_continuous_plot_scale_values(self) -> None:
        if not self._is_continuous_result():
            return
        result = self.current_result
        transform = str(getattr(result, "trait_transform", "none") or "none")
        plot_scale = str(getattr(result, "trait_plot_scale", "analysis") or "analysis")
        if transform == "none":
            plot_scale = "analysis"
            result.trait_plot_scale = "analysis"

        if plot_scale == "original":
            result.plot_tip_values = dict(getattr(result, "original_tip_values", {}) or {})
            result.plot_node_values = dict(getattr(result, "original_node_values", {}) or {})
        else:
            result.plot_tip_values = dict(getattr(result, "tip_values", {}) or {})
            result.plot_node_values = dict(getattr(result, "analysis_node_values", {}) or {})

        self._apply_continuous_display_scale_payloads()

        scale_values = list(result.plot_tip_values.values()) + list(result.plot_node_values.values())
        if scale_values:
            result.color_scale_min = min(float(v) for v in scale_values)
            result.color_scale_max = max(float(v) for v in scale_values)
            if result.color_scale_min == result.color_scale_max:
                result.color_scale_max = result.color_scale_min + 1.0

        stats = dict(getattr(result, "model_statistics", {}) or {})
        stats["trait_display_scale"] = str(getattr(result, "trait_display_scale", "analysis") or "analysis")
        stats["display_scale"] = self._continuous_scale_label(stats["trait_display_scale"])
        stats["trait_plot_scale"] = plot_scale
        stats["plot_scale"] = self._continuous_scale_label(plot_scale)
        stats["color_scale_min"] = float(getattr(result, "color_scale_min", 0.0) or 0.0)
        stats["color_scale_max"] = float(getattr(result, "color_scale_max", 1.0) or 1.0)
        result.model_statistics = stats

    def _apply_continuous_display_scale_payloads(self) -> None:
        if not self._is_continuous_result():
            return
        result = self.current_result
        transform = str(getattr(result, "trait_transform", "none") or "none")
        display_scale = str(getattr(result, "trait_display_scale", "analysis") or "analysis")
        plot_scale = str(getattr(result, "trait_plot_scale", "analysis") or "analysis")
        if transform == "none":
            display_scale = "analysis"
            plot_scale = "analysis"
            result.trait_display_scale = "analysis"
            result.trait_plot_scale = "analysis"

        display_label = self._continuous_scale_label(display_scale)
        plot_label = self._continuous_scale_label(plot_scale)

        for clade_key, node in dict(getattr(result, "node_results", {}) or {}).items():
            payload = dict(getattr(node, "raw_method_payload", {}) or {})
            payload["trait_display_scale"] = display_scale
            payload["trait_plot_scale"] = plot_scale
            payload["display_scale"] = display_label
            payload["plot_scale"] = plot_label

            analysis_summary = self._continuous_node_analysis_summary(node, payload)
            original_summary = self._continuous_node_original_summary(clade_key, node, payload)
            payload.update({
                "analysis_mean": analysis_summary["mean"],
                "analysis_median": analysis_summary["median"],
                "analysis_lower95": analysis_summary["lower95"],
                "analysis_upper95": analysis_summary["upper95"],
                "original_mean": original_summary["mean"],
                "original_median": original_summary["median"],
                "original_lower95": original_summary["lower95"],
                "original_upper95": original_summary["upper95"],
            })
            if display_scale == "original" and transform != "none":
                chosen = original_summary
            else:
                chosen = analysis_summary
            payload["display_mean"] = chosen["mean"]
            payload["display_median"] = chosen["median"]
            payload["display_lower95"] = chosen["lower95"]
            payload["display_upper95"] = chosen["upper95"]

            plot_values = dict(getattr(result, "plot_node_values", {}) or {})
            if str(clade_key) in plot_values:
                payload["plot_mean"] = float(plot_values[str(clade_key)])
            elif plot_scale == "original" and transform != "none":
                payload["plot_mean"] = original_summary["mean"]
            else:
                payload["plot_mean"] = analysis_summary["mean"]
            node.raw_method_payload = payload

    def _continuous_node_analysis_summary(self, node, payload: dict) -> dict:
        return {
            "mean": float(payload.get("analysis_mean", getattr(node, "mean", 0.0)) or 0.0),
            "median": float(payload.get("analysis_median", getattr(node, "median", 0.0)) or 0.0),
            "lower95": float(payload.get("analysis_lower95", getattr(node, "lower95", 0.0)) or 0.0),
            "upper95": float(payload.get("analysis_upper95", getattr(node, "upper95", 0.0)) or 0.0),
        }

    def _continuous_node_original_summary(self, clade_key: str, node, payload: dict) -> dict:
        existing_keys = ["original_mean", "original_median", "original_lower95", "original_upper95"]
        if all(key in payload for key in existing_keys):
            return {
                "mean": float(payload.get("original_mean", 0.0) or 0.0),
                "median": float(payload.get("original_median", 0.0) or 0.0),
                "lower95": float(payload.get("original_lower95", 0.0) or 0.0),
                "upper95": float(payload.get("original_upper95", 0.0) or 0.0),
            }

        transform = str(getattr(self.current_result, "trait_transform", "none") or "none")
        samples = []
        for value in list(getattr(node, "raw_samples", []) or []):
            try:
                number = float(value)
            except Exception:
                continue
            if transform == "log":
                samples.append(math.exp(number))
            elif transform == "log10":
                samples.append(10.0 ** number)
            else:
                samples.append(number)
        if samples:
            return self._continuous_sample_summary(samples)

        values = dict(getattr(self.current_result, "original_node_values", {}) or {})
        mean = float(values.get(str(clade_key), getattr(node, "mean", 0.0)) or 0.0)
        return {"mean": mean, "median": mean, "lower95": mean, "upper95": mean}

    def _continuous_sample_summary(self, values: list) -> dict:
        clean = sorted(float(value) for value in list(values or []))
        if not clean:
            return {"mean": 0.0, "median": 0.0, "lower95": 0.0, "upper95": 0.0}
        return {
            "mean": sum(clean) / float(len(clean)),
            "median": self._continuous_quantile(clean, 0.5),
            "lower95": self._continuous_quantile(clean, 0.025),
            "upper95": self._continuous_quantile(clean, 0.975),
        }

    def _continuous_quantile(self, sorted_values: list, q: float) -> float:
        values = list(sorted_values or [])
        if not values:
            return 0.0
        if len(values) == 1:
            return float(values[0])
        q = max(0.0, min(1.0, float(q)))
        pos = q * (len(values) - 1)
        lower = int(pos)
        upper = min(lower + 1, len(values) - 1)
        fraction = pos - lower
        return float(values[lower]) * (1.0 - fraction) + float(values[upper]) * fraction

    def _refresh_result_context_preserving_selection(self) -> None:
        selected = str(self.current_selected_clade_key or "")
        payload = self.current_payload
        self._rebuild_standard_context()
        self._sync_node_info_panel()
        if selected:
            self.node_info_panel.select_row_by_clade_key(selected)
            if payload is not None:
                self._display_payload_only(payload)

    def _display_payload_only(self, payload: dict) -> None:
        self.current_payload = payload

        if self.current_result is None or self.result_adapter is None:
            self.node_info_panel.show_basic_node_info(payload)
        else:
            standard_payload = self._build_standard_payload_from_tree_payload(payload)
            if standard_payload is None:
                self.node_info_panel.show_basic_node_info(payload)
            else:
                self.node_info_panel.show_standard_node_info(
                    tree_payload=payload,
                    standard_payload=standard_payload,
                )

        if payload and "error" not in payload:
            self.statusBar().showMessage(
                f"当前节点: {payload.get('name', '')} ({payload.get('node_id', '')})"
            )
        else:
            self.statusBar().showMessage(str(payload.get("error", "")) if payload else "")

    def _build_standard_payload_from_tree_payload(self, payload: dict):
        if not payload or "error" in payload or self.result_adapter is None:
            return None

        clade_key = str(payload.get("clade_signature", "") or "").strip()
        if not clade_key:
            return None

        if clade_key in self.standard_node_payloads:
            return self.standard_node_payloads[clade_key]

        node_name = str(payload.get("name", "") or "")
        return self.result_adapter.build_node_payload(clade_key, node_name=node_name)

    def _set_selected_clade(self, clade_key: str, payload: dict = None, toggle: bool = True) -> None:
        clade_key = str(clade_key or "").strip()

        if self.renderer is None:
            return

        if toggle and clade_key and self.current_selected_clade_key == clade_key:
            self.current_selected_clade_key = ""
            self.renderer.select_node_by_clade_key("")
            self.tree_panel.refresh_tree(preserve_view=True)
            self.node_info_panel.clear_list_selection()

            if payload:
                self.node_info_panel.show_basic_node_info(payload)
            else:
                self.node_info_panel.show_basic_node_info({})
            self._sync_figure_group_buttons()
            return

        self.current_selected_clade_key = clade_key
        returned_payload = self.renderer.select_node_by_clade_key(clade_key)
        self.tree_panel.refresh_tree(preserve_view=True)
        self.node_info_panel.select_row_by_clade_key(clade_key)

        if payload is None:
            payload = returned_payload

        if payload is not None:
            self._display_payload_only(payload)
        self._sync_figure_group_buttons()

    def show_node_payload(self, payload: dict) -> None:
        if not payload or "error" in payload:
            self.current_selected_clade_key = ""
            if self.renderer is not None:
                self.renderer.select_node_by_clade_key("")
            self.node_info_panel.clear_list_selection()
            self._display_payload_only(payload or {})
            self._sync_figure_group_buttons()
            return

        clade_key = str(payload.get("clade_signature", "") or "").strip()
        standard_payload = None
        if self.current_result is not None and clade_key:
            standard_payload = self._build_standard_payload_from_tree_payload(payload)

        if standard_payload is None:
            self.current_selected_clade_key = ""
            if self.renderer is not None:
                self.renderer.select_node_by_clade_key("")
            self.node_info_panel.clear_list_selection()
            self._display_payload_only(payload)
            self._sync_figure_group_buttons()
            return

        self._set_selected_clade(clade_key, payload=payload, toggle=True)

    def _on_state_color_changed(self, state: str, color: str) -> None:
        if self.current_result is None:
            return

        state = str(state).strip()
        color = str(color).strip()
        if not state or not color:
            return

        self.current_result.state_colors[state] = color

        for node_result in self.current_result.node_results.values():
            labels = list(getattr(node_result, "pie_labels", []) or [])
            if not labels:
                labels = list(getattr(node_result, "states", []) or [])
                node_result.pie_labels = labels

            node_result.pie_colors = [
                self.current_result.state_colors.get(label, "#808080")
                for label in labels
            ]

        self._rebuild_standard_context()
        self._sync_node_info_panel()

        if self.current_payload is not None:
            self._display_payload_only(self.current_payload)

        if self.renderer is not None:
            self.renderer.apply_leaf_states(self.leaf_state_map, self.current_result.state_colors)
            self.renderer.set_result(self.current_result)
            self.refresh_view()

    def _toggle_leaf_name(self, checked: bool) -> None:
        if self.renderer is None:
            return
        self.renderer.set_show_leaf_name(checked)
        self.refresh_view()

    def _toggle_branch_length(self, checked: bool) -> None:
        if self.renderer is None:
            return
        self.renderer.set_show_branch_length(checked)
        self.refresh_view()

    def _toggle_branch_support(self, checked: bool) -> None:
        if self.renderer is None:
            return
        self.renderer.set_show_branch_support(checked)
        self.refresh_view()

    def _toggle_circular_tree(self, checked: bool) -> None:
        if self.renderer is None:
            return
        self.renderer.set_circular_enabled(checked)
        self.refresh_view()

    def _on_continuous_display_scale_changed(self, *args) -> None:
        if self._updating_continuous_scale_controls or not self._is_continuous_result():
            return
        scale = str(self.continuous_display_combo.currentData() or "analysis")
        transform = str(getattr(self.current_result, "trait_transform", "none") or "none")
        if transform == "none":
            scale = "analysis"
        self.current_result.trait_display_scale = scale
        self._apply_continuous_plot_scale_values()
        self._refresh_result_context_preserving_selection()
        self._configure_continuous_scale_controls()

    def _on_continuous_plot_scale_changed(self, *args) -> None:
        if self._updating_continuous_scale_controls or not self._is_continuous_result():
            return
        scale = str(self.continuous_color_combo.currentData() or "analysis")
        transform = str(getattr(self.current_result, "trait_transform", "none") or "none")
        if transform == "none":
            scale = "analysis"
        self.current_result.trait_plot_scale = scale
        self._apply_continuous_plot_scale_values()
        self._refresh_result_context_preserving_selection()

        if self.renderer is not None:
            self.renderer.set_result(self.current_result)
            if self.current_selected_clade_key:
                self.renderer.select_node_by_clade_key(self.current_selected_clade_key)
            self.tree_panel.refresh_tree(preserve_view=True)
        self._configure_continuous_scale_controls()

    def _export_png(self) -> None:
        if self.renderer is None:
            QMessageBox.warning(self, "无法导出", "当前没有可导出的树。")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "导出PNG", "", "PNG Files (*.png)")
        if not file_path:
            return
        if not file_path.lower().endswith(".png"):
            file_path += ".png"

        try:
            self.export_service.export_tree_png(self.renderer, file_path)
            self.statusBar().showMessage(f"已导出PNG: {file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def _export_svg(self) -> None:
        if self.renderer is None:
            QMessageBox.warning(self, "无法导出", "当前没有可导出的树。")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "导出SVG", "", "SVG Files (*.svg)")
        if not file_path:
            return
        if not file_path.lower().endswith(".svg"):
            file_path += ".svg"

        try:
            self.export_service.export_tree_svg(self.renderer, file_path)
            self.statusBar().showMessage(f"已导出SVG: {file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def _export_csv(self) -> None:
        if self.current_result is None:
            QMessageBox.warning(self, "无法导出", "当前没有可导出的结果。")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "导出CSV", "", "CSV Files (*.csv)")
        if not file_path:
            return
        if not file_path.lower().endswith(".csv"):
            file_path += ".csv"

        try:
            self.export_service.export_result_csv(
                self.current_result,
                file_path,
                method_name=self.current_method_name,
            )
            self.statusBar().showMessage(f"已导出CSV: {file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def _export_pdf(self) -> None:
        if self.renderer is None:
            QMessageBox.warning(self, "无法导出", "当前没有可导出的树。")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "导出PDF", "", "PDF Files (*.pdf)")
        if not file_path:
            return
        if not file_path.lower().endswith(".pdf"):
            file_path += ".pdf"

        try:
            self.export_service.export_tree_pdf(self.renderer, file_path)
            self.statusBar().showMessage(f"已导出PDF: {file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def _export_continuous_figure(self) -> None:
        if not self._is_continuous_result():
            QMessageBox.warning(
                self,
                "Export unavailable",
                "Publication-style figure is only available for continuous-trait results.",
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export publication-style figure",
            "",
            "PNG Files (*.png);;PDF Files (*.pdf);;SVG Files (*.svg)",
        )
        if not file_path:
            return
        lower = file_path.lower()
        if not (lower.endswith(".png") or lower.endswith(".pdf") or lower.endswith(".svg")):
            file_path += ".png"

        try:
            self._apply_continuous_plot_scale_values()
            self.export_service.export_continuous_publication_figure(
                self.current_result,
                file_path,
                method_name=self.current_method_name,
            )
            self.statusBar().showMessage("Exported publication-style figure: %s" % file_path)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _on_node_entry_clicked(self, clade_key: str) -> None:
        self._set_selected_clade(clade_key, payload=None, toggle=True)
