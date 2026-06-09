import math

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QColorDialog,
)


class NodeInfoPanel(QWidget):
    state_color_changed = pyqtSignal(str, str)
    node_entry_clicked = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.current_method_name = ""
        self.current_result = None
        self.current_payload = None
        self.current_standard_payload = None
        self.current_node_payloads = []

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        self.main_layout.setSpacing(6)

        self.top_tabs = QTabWidget()

        self.list_tab = QWidget()
        self.list_tab_layout = QVBoxLayout(self.list_tab)
        self.list_tab_layout.setContentsMargins(4, 4, 4, 4)
        self.list_tab_layout.setSpacing(6)

        self.list_table = QTableWidget()
        self.list_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.list_table.setSelectionMode(QTableWidget.SingleSelection)
        self.list_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.list_table.setAlternatingRowColors(True)
        self.list_table.verticalHeader().setVisible(False)
        self.list_table.horizontalHeader().setStretchLastSection(True)
        self.list_table.cellClicked.connect(self._on_list_table_clicked)
        self.list_table.setStyleSheet(
            """
            QTableWidget::item:selected {
                background-color: #2d7ff9;
                color: white;
            }
            QTableWidget::item:selected:!active {
                background-color: #2d7ff9;
                color: white;
            }
            """
        )
        self.list_tab_layout.addWidget(self.list_table, 3)

        self.inner_tabs = QTabWidget()

        self.legend_tab = QWidget()
        self.legend_layout = QVBoxLayout(self.legend_tab)
        self.legend_layout.setContentsMargins(4, 4, 4, 4)
        self.legend_layout.setSpacing(6)

        self.selected_node_title = QLabel("当前未选中节点")
        self.selected_node_title.setWordWrap(True)
        self.legend_layout.addWidget(self.selected_node_title)

        self.legend_note = QLabel("")
        self.legend_note.setWordWrap(True)
        self.legend_layout.addWidget(self.legend_note)

        self.legend_table = QTableWidget()
        self.legend_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.legend_table.setSelectionMode(QTableWidget.NoSelection)
        self.legend_table.setAlternatingRowColors(True)
        self.legend_table.verticalHeader().setVisible(False)
        self.legend_table.horizontalHeader().setStretchLastSection(True)
        self.legend_layout.addWidget(self.legend_table, 1)

        self.color_tab = QWidget()
        self.color_layout = QVBoxLayout(self.color_tab)
        self.color_layout.setContentsMargins(4, 4, 4, 4)
        self.color_layout.setSpacing(6)

        self.color_tip = QLabel("双击颜色单元格可修改状态颜色，并同步刷新树渲染。")
        self.color_tip.setWordWrap(True)
        self.color_layout.addWidget(self.color_tip)

        self.color_table = QTableWidget()
        self.color_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.color_table.setSelectionMode(QTableWidget.SingleSelection)
        self.color_table.setAlternatingRowColors(True)
        self.color_table.verticalHeader().setVisible(False)
        self.color_table.horizontalHeader().setStretchLastSection(True)
        self.color_table.cellDoubleClicked.connect(self._on_color_table_double_clicked)
        self.color_layout.addWidget(self.color_table, 1)

        self.inner_tabs.addTab(self.legend_tab, "Legend")
        self.inner_tabs.addTab(self.color_tab, "Color")
        self.list_tab_layout.addWidget(self.inner_tabs, 2)

        self.info_tab = QWidget()
        self.info_layout = QVBoxLayout(self.info_tab)
        self.info_layout.setContentsMargins(8, 8, 8, 8)
        self.info_placeholder = QLabel("Information 页暂不实现")
        self.info_placeholder.setWordWrap(True)
        self.info_placeholder.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.info_layout.addWidget(self.info_placeholder)

        self.time_tab = QWidget()
        self.time_layout = QVBoxLayout(self.time_tab)
        self.time_layout.setContentsMargins(8, 8, 8, 8)
        self.time_placeholder = QLabel("Time 页暂不实现")
        self.time_placeholder.setWordWrap(True)
        self.time_placeholder.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.time_layout.addWidget(self.time_placeholder)

        self.top_tabs.addTab(self.list_tab, "List")
        self.top_tabs.addTab(self.info_tab, "Information")
        self.top_tabs.addTab(self.time_tab, "Time")

        self.main_layout.addWidget(self.top_tabs)
        self.setLayout(self.main_layout)

        self.clear_info()

    def clear_info(self) -> None:
        self.current_payload = None
        self.current_standard_payload = None

        self.list_table.clear()
        self.list_table.setRowCount(0)
        self.list_table.setColumnCount(0)

        self.selected_node_title.setText("当前未选中节点")
        self.legend_note.setText("")

        self.legend_table.clear()
        self.legend_table.setRowCount(0)
        self.legend_table.setColumnCount(0)

        self.color_table.clear()
        self.color_table.setRowCount(0)
        self.color_table.setColumnCount(0)

        self.info_placeholder.setText("Information 页暂不实现")
        self.time_placeholder.setText("Time 页暂不实现")

    def set_standard_result(self, method_name: str, result, node_payloads: list) -> None:
        self.current_method_name = method_name or ""
        self.current_result = result
        self.current_node_payloads = list(node_payloads or [])

        self._refresh_list_tab()
        self._refresh_color_tab()
        self._clear_selected_node_legend()

    def show_basic_node_info(self, payload: dict) -> None:
        self.current_payload = payload
        self.current_standard_payload = None

        if not payload:
            self._show_global_legend()
            return

        if "error" in payload:
            self.selected_node_title.setText(str(payload.get("error", "")))
            self.legend_note.setText("")
            self._clear_legend_table()
            return

        name = str(payload.get("name", "") or "")
        clade = str(payload.get("clade_signature", "") or "")
        node_id = str(payload.get("node_id", "") or "")

        lines = []
        if name:
            lines.append(f"名称: {name}")
        if node_id:
            lines.append(f"内部编号: {node_id}")
        if clade:
            lines.append(f"Clade: {clade}")

        self.selected_node_title.setText("\n".join(lines) if lines else "当前未选中节点")
        self.legend_note.setText("当前节点暂无方法结果，下面显示全局状态图例。")
        self._show_global_legend(title_override=self.selected_node_title.text())

    def show_standard_node_info(self, tree_payload: dict, standard_payload) -> None:
        self.current_payload = tree_payload
        self.current_standard_payload = standard_payload
        self._refresh_selected_legend(tree_payload, standard_payload)

    def show_message(self, text: str) -> None:
        self.selected_node_title.setText(text or "")
        self.legend_note.setText("")
        self._clear_legend_table()

    def select_row_by_clade_key(self, clade_key: str) -> None:
        clade_key = str(clade_key or "").strip()

        self.list_table.blockSignals(True)
        self.list_table.clearSelection()

        if not clade_key:
            self.list_table.blockSignals(False)
            return

        for row in range(self.list_table.rowCount()):
            item = self.list_table.item(row, 0)
            if item is None:
                continue
            row_clade_key = item.data(Qt.UserRole)
            if str(row_clade_key or "") == clade_key:
                self.list_table.selectRow(row)
                self.list_table.setCurrentCell(row, 0)
                self.list_table.setFocus(Qt.OtherFocusReason)
                break

        self.list_table.blockSignals(False)

    def clear_list_selection(self) -> None:
        self.list_table.blockSignals(True)
        self.list_table.clearSelection()
        self.list_table.setCurrentItem(None)
        self.list_table.blockSignals(False)

    def _on_list_table_clicked(self, row: int, column: int) -> None:
        item = self.list_table.item(row, 0)
        if item is None:
            return

        clade_key = item.data(Qt.UserRole)
        if not clade_key:
            return

        self.node_entry_clicked.emit(str(clade_key))

    def _refresh_list_tab(self) -> None:
        self.list_table.clear()

        payloads = list(self.current_node_payloads or [])
        if not payloads:
            self.list_table.setRowCount(0)
            self.list_table.setColumnCount(0)
            return

        # S-DIVA：只显示已经成功映射到参考树 DIVA 原生节点号的节点
        if self.current_method_name == "S-DIVA":
            payloads = [
                p for p in payloads
                if str(getattr(p, "display_node_id", "") or "").strip()
            ]

        payloads.sort(key=self._node_sort_key)

        rows = []
        for payload in payloads:
            display_id = str(getattr(payload, "display_node_id", "") or "").strip()
            display_text = f"node {display_id}"
            summary = str(getattr(payload, "state_summary", "") or "无")
            rows.append((display_text, summary, str(getattr(payload, "clade_key", "") or "")))

        self.list_table.setRowCount(len(rows))
        self.list_table.setColumnCount(2)
        summary_header = "Continuous value" if str(self.current_method_name).startswith("BayesTraits Continuous") else "Optimal reconstruction"
        self.list_table.setHorizontalHeaderLabels(["节点号", summary_header])

        for row_idx, (display_id, summary, clade_key) in enumerate(rows):
            id_item = QTableWidgetItem(display_id)
            id_item.setData(Qt.UserRole, clade_key)
            summary_item = QTableWidgetItem(summary)
            self.list_table.setItem(row_idx, 0, id_item)
            self.list_table.setItem(row_idx, 1, summary_item)

        self.list_table.resizeColumnsToContents()
        self.list_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.list_table.horizontalHeader().setStretchLastSection(True)

    def _refresh_color_tab(self) -> None:
        if self.current_result is None:
            self.color_table.clear()
            self.color_table.setRowCount(0)
            self.color_table.setColumnCount(0)
            return

        headers = ["Range", "Color"]
        rows = self._legend_rows_for_result()

        self._populate_table(
            self.color_table,
            headers,
            rows,
            color_column=1,
            color_text_mode="double_click",
        )

    def _refresh_selected_legend(self, tree_payload: dict, standard_payload) -> None:
        name = ""
        clade = ""
        if tree_payload:
            name = str(tree_payload.get("name", "") or "")
            clade = str(tree_payload.get("clade_signature", "") or "")

        lines = []
        if name:
            lines.append(f"名称: {name}")

        display_node_id = str(getattr(standard_payload, "display_node_id", "") or "").strip()
        if display_node_id:
            lines.append(f"节点号: {display_node_id}")
        elif getattr(standard_payload, "display_id_source", ""):
            lines.append("节点号: 未映射")

        if clade:
            lines.append(f"Clade: {clade}")

        support_summary = str(getattr(standard_payload, "support_summary", "") or "")
        if support_summary:
            lines.append(support_summary)

        self.selected_node_title.setText("\n".join(lines) if lines else "当前未选中节点")

        interpretation_note = str(getattr(standard_payload, "interpretation_note", "") or "")
        self.legend_note.setText(interpretation_note)

        raw = dict(getattr(standard_payload, "raw_method_payload", {}) or {})
        states = [str(x).strip() for x in list(raw.get("states", []) or []) if str(x).strip()]
        pie_labels = [str(x).strip() for x in list(raw.get("pie_labels", []) or []) if str(x).strip()]
        pie_percents = list(raw.get("pie_percents", []) or [])
        pie_colors = list(raw.get("pie_colors", []) or [])
        state_counts = dict(raw.get("state_counts", {}) or {})
        state_supports = dict(raw.get("state_supports", {}) or {})

        color_map = {}
        source_labels = pie_labels or states
        for idx, state in enumerate(source_labels):
            if idx < len(pie_colors):
                color_map[state] = pie_colors[idx]

        rows = []
        headers = []
        color_column = -1

        if bool(raw.get("continuous", False)):
            display_scale = str(raw.get("display_scale", raw.get("trait_scale", raw.get("trait_transform", "none"))))
            headers = ["Field", "Value"]
            rows = [
                ["Trait", str(raw.get("trait_name", ""))],
                ["Display scale", display_scale],
                ["Plot scale", str(raw.get("plot_scale", raw.get("trait_scale", raw.get("trait_transform", "none"))))],
                ["Mean", "%.6g" % float(raw.get("display_mean", raw.get("mean", 0.0)) or 0.0)],
                ["Median", "%.6g" % float(raw.get("display_median", raw.get("median", 0.0)) or 0.0)],
                ["Lower 95%", "%.6g" % float(raw.get("display_lower95", raw.get("lower95", 0.0)) or 0.0)],
                ["Upper 95%", "%.6g" % float(raw.get("display_upper95", raw.get("upper95", 0.0)) or 0.0)],
                ["Samples", str(raw.get("sample_count", ""))],
            ]
            if str(raw.get("trait_display_scale", "analysis")) == "original":
                rows.extend([
                    ["Analysis scale", str(raw.get("trait_scale", raw.get("trait_transform", "none")))],
                    ["Analysis mean", "%.6g" % float(raw.get("analysis_mean", raw.get("mean", 0.0)) or 0.0)],
                    ["Analysis median", "%.6g" % float(raw.get("analysis_median", raw.get("median", 0.0)) or 0.0)],
                ])
        elif state_supports and self.current_method_name == "S-DIVA":
            headers = ["State", "Support (%)", "Color"]
            for state in states or list(state_supports.keys()):
                rows.append([
                    state,
                    f"{float(state_supports.get(state, 0.0)):.2f}",
                    color_map.get(state, "#808080"),
                ])
            color_column = 2
        elif state_supports:
            headers = ["状态", "加权计数", "支持比例(%)", "颜色"]
            for state in states or list(state_supports.keys()):
                rows.append([
                    state,
                    f"{float(state_counts.get(state, 0.0)):.4f}",
                    f"{float(state_supports.get(state, 0.0)):.2f}",
                    color_map.get(state, "#808080"),
                ])
            color_column = 3
        elif pie_labels and pie_percents:
            headers = ["状态", "比例(%)", "颜色"]
            for idx, state in enumerate(pie_labels):
                percent = pie_percents[idx] if idx < len(pie_percents) else 0.0
                rows.append([
                    state,
                    f"{float(percent):.2f}",
                    color_map.get(state, "#808080"),
                ])
            color_column = 2
        elif states:
            headers = ["状态", "颜色"]
            for state in states:
                rows.append([state, color_map.get(state, "#808080")])
            color_column = 1
        else:
            headers = ["字段", "内容"]
            rows = [["说明", "当前节点无可展示图例字段"]]

        self._populate_table(
            self.legend_table,
            headers=headers,
            rows=rows,
            color_column=color_column,
            color_text_mode="blank",
        )

    def _on_color_table_double_clicked(self, row: int, column: int) -> None:
        if self.current_result is None:
            return
        if column != 1:
            return

        state_item = self.color_table.item(row, 0)
        color_item = self.color_table.item(row, 1)
        if state_item is None or color_item is None:
            return

        state = state_item.text().strip().split(" (", 1)[0].strip()
        old_color = color_item.data(Qt.UserRole) or "#808080"

        qcolor = QColorDialog.getColor(QColor(old_color), self, f"选择状态颜色：{state}")
        if not qcolor.isValid():
            return

        new_color = qcolor.name()
        color_item.setData(Qt.UserRole, new_color)
        color_item.setBackground(QBrush(QColor(new_color)))
        color_item.setText("Double Click")

        self.state_color_changed.emit(state, new_color)

    def _show_global_legend_legacy_old(self, title_override: str = "") -> None:
        if self.current_result is None:
            self.selected_node_title.setText(title_override or "当前未选中节点")
            self.legend_note.setText("")
            self._clear_legend_table()
            return

        self.selected_node_title.setText(title_override or "当前未选中节点")
        self.legend_note.setText("当前未选中节点，下面显示全局状态图例。")

        state_order = list(getattr(self.current_result, "state_order", []) or [])
        state_colors = dict(getattr(self.current_result, "state_colors", {}) or {})

        rows = []
        for state in state_order:
            rows.append([state, state_colors.get(state, "#808080")])

        self._populate_table(
            self.legend_table,
            headers=["状态", "颜色"],
            rows=rows,
            color_column=1,
            color_text_mode="blank",
        )

    def _clear_legend_table(self) -> None:
        self.legend_table.clear()
        self.legend_table.setRowCount(0)
        self.legend_table.setColumnCount(0)

    def _clear_selected_node_legend(self) -> None:
        self.current_standard_payload = None
        self._show_global_legend()

    def _is_continuous_result(self) -> bool:
        return type(self.current_result).__name__ == "ContinuousTraitResult"

    def _legend_rows_for_result(self) -> list:
        state_order = list(getattr(self.current_result, "state_order", []) or [])
        state_colors = dict(getattr(self.current_result, "state_colors", {}) or {})
        if not self._is_continuous_result():
            return [[state, state_colors.get(state, "#808080")] for state in state_order]

        if not state_order:
            state_order = ["Low", "20%", "40%", "60%", "80%", "High"]
        vmin = float(getattr(self.current_result, "color_scale_min", 0.0) or 0.0)
        vmax = float(getattr(self.current_result, "color_scale_max", vmin + 1.0) or (vmin + 1.0))
        if vmax <= vmin:
            vmax = vmin + 1.0
        denom = max(1, len(state_order) - 1)
        rows = []
        for index, label in enumerate(state_order):
            fraction = float(index) / float(denom)
            value = vmin + (vmax - vmin) * fraction
            display_value = self._continuous_display_value(value)
            rows.append(["%s (%.4g)" % (str(label), display_value), state_colors.get(label, "#808080")])
        return rows

    def _continuous_display_value(self, value) -> float:
        result = self.current_result
        display_scale = str(getattr(result, "trait_display_scale", "analysis") or "analysis")
        plot_scale = str(getattr(result, "trait_plot_scale", "analysis") or "analysis")
        transform = str(getattr(result, "trait_transform", "none") or "none")
        number = float(value)
        if display_scale == plot_scale:
            return number
        if display_scale != "original":
            if plot_scale == "original" and transform == "log" and number > 0.0:
                return math.log(number)
            if plot_scale == "original" and transform == "log10" and number > 0.0:
                return math.log10(number)
            return number
        if plot_scale == "original":
            return number
        if transform == "log":
            return math.exp(number)
        if transform == "log10":
            return 10.0 ** number
        return number

    def _show_global_legend(self, title_override: str = "") -> None:
        if self.current_result is None:
            self.selected_node_title.setText(title_override or "Current node")
            self.legend_note.setText("")
            self._clear_legend_table()
            return

        self.selected_node_title.setText(title_override or "Current node")
        headers = ["Scale", "Color"] if self._is_continuous_result() else ["State", "Color"]
        if self._is_continuous_result():
            trait_name = str(getattr(self.current_result, "trait_name", "") or "").strip()
            transform = str(getattr(self.current_result, "trait_transform", "none") or "none")
            display_scale = str(getattr(self.current_result, "trait_display_scale", "analysis") or "analysis")
            plot_scale = str(getattr(self.current_result, "trait_plot_scale", "analysis") or "analysis")
            suffix = ": " + trait_name if trait_name else ""
            if plot_scale == "original" and display_scale == "original" and transform != "none":
                self.legend_note.setText(
                    "Continuous color scale%s. Colors and labels use back-transformed original values."
                    % suffix
                )
            elif plot_scale == "original" and transform != "none":
                self.legend_note.setText(
                    "Continuous color scale%s. Colors use back-transformed original values; labels use %s values."
                    % (suffix, transform)
                )
            elif display_scale == "original" and transform != "none":
                self.legend_note.setText(
                    "Continuous color scale%s. Colors use %s values; labels are back-transformed."
                    % (suffix, transform)
                )
            else:
                self.legend_note.setText("Continuous color scale%s." % suffix)
        else:
            self.legend_note.setText("Global state legend.")

        self._populate_table(
            self.legend_table,
            headers=headers,
            rows=self._legend_rows_for_result(),
            color_column=1,
            color_text_mode="blank",
        )

    def _populate_table(
        self,
        table: QTableWidget,
        headers: list,
        rows: list,
        color_column: int = -1,
        color_text_mode: str = "keep",
    ) -> None:
        table.clear()
        table.setRowCount(len(rows))
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)

                if col_idx == color_column:
                    color_value = str(value)
                    item.setData(Qt.UserRole, color_value)
                    item.setBackground(QBrush(QColor(color_value)))
                    item.setTextAlignment(Qt.AlignCenter)

                    if color_text_mode == "blank":
                        item.setText("")
                    elif color_text_mode == "double_click":
                        item.setText("Double Click")
                    else:
                        item.setText(color_value)

                table.setItem(row_idx, col_idx, item)

        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)

    @staticmethod
    def _node_sort_key(payload) -> tuple:
        display_id = str(getattr(payload, "display_node_id", "") or "").strip()
        if display_id.isdigit():
            return (0, int(display_id), str(getattr(payload, "clade_key", "") or ""))
        return (1, 10 ** 9, str(getattr(payload, "clade_key", "") or ""))
