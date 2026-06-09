from typing import Callable, Optional

from infrastructure.tree.selected_node_info import SelectedNodeInfo


class _DummyPropTable:
    def update_properties(self, node) -> None:
        pass


class ETEAdapter:
    def __init__(self) -> None:
        # 当前树对象
        self.tree = None
        self.tree_style = None

        # 当前图形场景 / 视图
        self._scene = None
        self._view = None

        # 最近一次载入的 Newick 文本
        self._last_newick = ""

        # 树显示模式
        self._tree_mode = "r"
        self._arc_start = 0
        self._arc_span = 359

        # 视图显示开关
        self._show_leaf_name = True
        self._show_branch_length = False
        self._show_branch_support = False
        self._branch_vertical_margin = 2

        # 当前被外部选中的内部节点（用 clade_key 标识）
        self._selected_clade_key = ""

        # 结果与叶节点状态
        self._diva_result = None
        self._continuous_result = None
        self._leaf_state_map = {}
        self._leaf_state_colors = {}

        # 点击回调
        self._click_callback = None

        # 饼图与叶节点样式
        self._pie_size = 24
        self._pie_opacity = 0.65
        self._pie_shift_x = 6
        self._leaf_node_size = 10
        self._continuous_leaf_node_size = 14
        self._continuous_internal_node_size = 11
        self._continuous_selection_ring_size = 28
        self._continuous_selection_ring_width = 3
        self._continuous_branch_width = 5

    def load_newick(self, newick_text: str) -> None:
        from ete3 import Tree

        self._last_newick = newick_text
        self.tree = Tree(newick_text, format=1)
        self._assign_node_ids()
        self.tree_style = self._build_tree_style()

    def set_tree(self, tree) -> None:
        self.tree = tree
        if self.tree is not None:
            self._assign_node_ids()
        self.tree_style = self._build_tree_style()

    def _assign_node_ids(self) -> None:
        if self.tree is None:
            return

        counter = 1
        for node in self.tree.traverse():
            node._rasp_id = f"N{counter:04d}"
            counter += 1

    def _build_tree_style(self):
        from ete3 import TreeStyle

        ts = TreeStyle()
        ts.show_leaf_name = self._show_leaf_name
        ts.show_branch_length = self._show_branch_length
        ts.show_branch_support = self._show_branch_support
        ts.show_scale = False
        ts.complete_branch_lines_when_necessary = bool(self._continuous_result is not None)
        ts.extra_branch_line_type = 1
        ts.extra_branch_line_color = "#b8b8b8"
        ts.draw_guiding_lines = False
        ts.branch_vertical_margin = self._branch_vertical_margin
        ts.layout_fn = self._layout_node

        ts.mode = self._tree_mode
        ts.arc_start = self._arc_start
        ts.arc_span = self._arc_span

        ts.min_leaf_separation = 6
        ts.margin_left = 10
        ts.margin_right = 10
        ts.margin_top = 10
        ts.margin_bottom = 10

        return ts

    def set_show_leaf_name(self, flag: bool) -> None:
        self._show_leaf_name = bool(flag)
        self.tree_style = self._build_tree_style()

    def set_show_branch_length(self, flag: bool) -> None:
        self._show_branch_length = bool(flag)
        self.tree_style = self._build_tree_style()

    def set_show_branch_support(self, flag: bool) -> None:
        self._show_branch_support = bool(flag)
        self.tree_style = self._build_tree_style()

    def set_branch_vertical_margin(self, value: int) -> None:
        self._branch_vertical_margin = int(value)
        self.tree_style = self._build_tree_style()

    def set_tree_mode(self, mode: str) -> None:
        mode = (mode or "r").strip().lower()
        if mode not in ("r", "c"):
            raise ValueError(f"不支持的树模式: {mode}")
        self._tree_mode = mode
        self.tree_style = self._build_tree_style()

    def set_circular_enabled(self, enabled: bool) -> None:
        self._tree_mode = "c" if enabled else "r"
        self.tree_style = self._build_tree_style()

    def set_circular_arc(self, arc_start: int = 0, arc_span: int = 359) -> None:
        self._arc_start = int(arc_start)
        self._arc_span = int(arc_span)
        self.tree_style = self._build_tree_style()

    def apply_diva_result(self, diva_result) -> None:
        self._diva_result = diva_result
        self._continuous_result = None
        self.tree_style = self._build_tree_style()

    def apply_continuous_result(self, continuous_result) -> None:
        self._continuous_result = continuous_result
        self._diva_result = None
        self.tree_style = self._build_tree_style()

    def apply_leaf_states(self, leaf_state_map: dict, state_colors: dict) -> None:
        self._leaf_state_map = dict(leaf_state_map or {})
        self._leaf_state_colors = dict(state_colors or {})
        self.tree_style = self._build_tree_style()

    def _build_clade_signature(self, node) -> str:
        leaf_names = sorted(
            str(leaf.name).strip()
            for leaf in node.iter_leaves()
            if str(getattr(leaf, "name", "")).strip()
        )
        return "|".join(leaf_names)

    def _reset_leaf_node_style(self, node) -> None:
        node.img_style["size"] = 3
        node.img_style["shape"] = "circle"
        node.img_style["fgcolor"] = "black"
        node.img_style["hz_line_width"] = 1
        node.img_style["vt_line_width"] = 1

    def _layout_leaf_node(self, node) -> None:
        self._reset_leaf_node_style(node)

        continuous_value = self._continuous_value_for_node(node)
        if continuous_value is not None:
            color = self._continuous_color(continuous_value)
            node.img_style["size"] = self._continuous_leaf_node_size
            node.img_style["shape"] = "circle"
            node.img_style["fgcolor"] = color
            node.img_style["hz_line_color"] = color
            node.img_style["vt_line_color"] = color
            node.img_style["hz_line_width"] = self._continuous_branch_width
            node.img_style["vt_line_width"] = self._continuous_branch_width
            return

        taxon_name = str(getattr(node, "name", "")).strip()
        state = self._leaf_state_map.get(taxon_name, "")

        if state:
            color = self._leaf_state_colors.get(state, "#808080")
            node.img_style["size"] = self._leaf_node_size
            node.img_style["shape"] = "circle"
            node.img_style["fgcolor"] = color

    def _layout_continuous_node(self, node) -> None:
        from ete3 import TextFace, faces

        value = self._continuous_value_for_node(node)
        color = self._continuous_color(value) if value is not None else "#777777"
        is_dummy = bool(getattr(node, "_rasp_dummy", False))
        clade_key = "" if is_dummy else self._build_clade_signature(node)
        is_selected = (
            self._selected_clade_key
            and not is_dummy
            and clade_key == self._selected_clade_key
        )

        node.img_style["shape"] = "circle"
        node.img_style["fgcolor"] = color
        node.img_style["bgcolor"] = "transparent"
        node.img_style["size"] = 0 if is_dummy else self._continuous_internal_node_size
        node.img_style["hz_line_color"] = color
        node.img_style["vt_line_color"] = color
        node.img_style["hz_line_width"] = self._continuous_branch_width
        node.img_style["vt_line_width"] = self._continuous_branch_width
        node._rasp_selection_ring = bool(is_selected)
        node._rasp_selection_ring_size = int(self._continuous_selection_ring_size)
        node._rasp_selection_ring_width = int(self._continuous_selection_ring_width)
        node._rasp_selection_ring_color = "#e02020"

        if is_dummy:
            return
        marker_groups = self._continuous_marker_groups(clade_key)
        for index, group in enumerate(marker_groups):
            label = str(group.get("short_label", "") or group.get("name", "") or "").strip()
            if not label:
                continue
            face_color = str(group.get("color", "") or "#222222").strip()
            text_color = self._contrasting_text_color(face_color)
            face = TextFace(" %s " % label, fsize=8, fgcolor=text_color)
            face.inner_background.color = face_color
            face.margin_left = 3
            face.margin_right = 3
            face.margin_top = 1
            face.margin_bottom = 1
            faces.add_face_to_node(face, node, column=index, position="branch-top")

    def _continuous_value_for_node(self, node):
        if self._continuous_result is None:
            return None
        if hasattr(node, "_rasp_continuous_value"):
            try:
                return float(getattr(node, "_rasp_continuous_value"))
            except Exception:
                return None
        if node.is_leaf():
            name = str(getattr(node, "name", "") or "").strip()
            values = dict(getattr(self._continuous_result, "plot_tip_values", {}) or {}) or dict(getattr(self._continuous_result, "tip_values", {}) or {})
            if name not in values:
                return None
            try:
                return float(values[name])
            except Exception:
                return None
        clade_key = self._build_clade_signature(node)
        plot_node_values = dict(getattr(self._continuous_result, "plot_node_values", {}) or {})
        if clade_key in plot_node_values:
            try:
                return float(plot_node_values[clade_key])
            except Exception:
                return None
        node_result = self._continuous_result.get_node_result(clade_key)
        if node_result is None:
            return None
        try:
            return float(getattr(node_result, "mean", 0.0) or 0.0)
        except Exception:
            return None

    def _continuous_color(self, value) -> str:
        try:
            value = float(value)
        except Exception:
            return "#777777"
        if self._continuous_result is None:
            return "#777777"
        vmin = float(getattr(self._continuous_result, "color_scale_min", 0.0) or 0.0)
        vmax = float(getattr(self._continuous_result, "color_scale_max", vmin + 1.0) or (vmin + 1.0))
        if vmax <= vmin:
            vmax = vmin + 1.0
        t = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
        palette = self._continuous_palette()
        if len(palette) <= 1:
            return palette[0] if palette else "#777777"
        scaled = t * float(len(palette) - 1)
        left_index = int(scaled)
        if left_index >= len(palette) - 1:
            return palette[-1]
        local_t = scaled - float(left_index)
        return self._interpolate_hex(palette[left_index], palette[left_index + 1], local_t)

    def _continuous_palette(self):
        if self._continuous_result is None:
            return ["#440154", "#414487", "#2A788E", "#22A884", "#7AD151", "#FDE725"]
        order = list(getattr(self._continuous_result, "state_order", []) or [])
        colors = dict(getattr(self._continuous_result, "state_colors", {}) or {})
        palette = [
            str(colors.get(label, "") or "").strip()
            for label in order
            if str(colors.get(label, "") or "").strip()
        ]
        return palette or ["#440154", "#414487", "#2A788E", "#22A884", "#7AD151", "#FDE725"]

    def _interpolate_hex(self, left: str, right: str, t: float) -> str:
        t = max(0.0, min(1.0, float(t)))
        left = str(left or "#000000").lstrip("#")
        right = str(right or "#ffffff").lstrip("#")
        lr, lg, lb = int(left[0:2], 16), int(left[2:4], 16), int(left[4:6], 16)
        rr, rg, rb = int(right[0:2], 16), int(right[2:4], 16), int(right[4:6], 16)
        r = int(round(lr + (rr - lr) * t))
        g = int(round(lg + (rg - lg) * t))
        b = int(round(lb + (rb - lb) * t))
        return "#%02x%02x%02x" % (r, g, b)

    def _continuous_marker_groups(self, clade_key: str):
        if self._continuous_result is None or not clade_key:
            return []
        stats = dict(getattr(self._continuous_result, "model_statistics", {}) or {})
        groups = getattr(self._continuous_result, "figure_groups", None) or stats.get("figure_groups")
        if not isinstance(groups, (list, tuple)):
            return []
        output = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            if group.get("show_marker_on_tree") is False:
                continue
            if str(group.get("clade_key", "") or "").strip() != clade_key:
                continue
            output.append(group)
        return output

    def _contrasting_text_color(self, color: str) -> str:
        try:
            raw = str(color or "").strip().lstrip("#")
            if len(raw) != 6:
                return "#ffffff"
            red = int(raw[0:2], 16)
            green = int(raw[2:4], 16)
            blue = int(raw[4:6], 16)
            luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255.0
            return "#111111" if luminance > 0.62 else "#ffffff"
        except Exception:
            return "#ffffff"

    def _layout_internal_node(self, node, node_result) -> None:
        from ete3 import PieChartFace, faces

        is_selected = (
            self._selected_clade_key
            and self._build_clade_signature(node) == self._selected_clade_key
        )

        # 内部节点不显示默认圆点；分支线始终保持普通样式
        node.img_style["size"] = 0
        node.img_style["hz_line_color"] = "#000000"
        node.img_style["vt_line_color"] = "#000000"
        node.img_style["hz_line_width"] = 1
        node.img_style["vt_line_width"] = 1

        # 高亮只作用在饼图本体：描边 + 更高透明度，不放大
        pie = PieChartFace(
            node_result.pie_percents,
            width=self._pie_size,
            height=self._pie_size,
            colors=node_result.pie_colors,
            line_color="#111111" if is_selected else None,
        )
        pie.opacity = 0.95 if is_selected else self._pie_opacity
        pie.margin_left = self._pie_shift_x

        faces.add_face_to_node(pie, node, column=0, position="float")

    def _layout_node(self, node) -> None:
        if node.is_leaf():
            self._layout_leaf_node(node)
            return

        if self._continuous_result is not None:
            self._layout_continuous_node(node)
            return

        node.img_style["size"] = 0
        node.img_style["shape"] = "circle"
        node.img_style["fgcolor"] = "black"
        node.img_style["hz_line_color"] = "#000000"
        node.img_style["vt_line_color"] = "#000000"
        node.img_style["hz_line_width"] = 1
        node.img_style["vt_line_width"] = 1

        if self._diva_result is None:
            return

        clade_key = self._build_clade_signature(node)
        node_result = self._diva_result.get_node_result(clade_key)
        if node_result is None or not node_result.pie_percents:
            return

        self._layout_internal_node(node, node_result)

    def get_tree_summary(self) -> str:
        if self.tree is None:
            return "未加载树"

        leaf_names = self.tree.get_leaf_names()
        return f"树已加载：叶节点数={len(leaf_names)}，taxa={leaf_names}"

    def show_tree_window(self) -> None:
        if self.tree is None:
            raise ValueError("当前没有可显示的树")
        self.tree.show(tree_style=self.tree_style)

    def build_embedded_view(self):
        if self.tree is None:
            raise ValueError("当前没有可显示的树")

        from ete3.treeview.qt4_gui import _TreeView
        from ete3.treeview.qt4_render import _TreeScene

        scene = _TreeScene()
        scene.init_values(self.tree, self.tree_style, {}, {})
        scene.draw()

        view = _TreeView(scene)
        scene.view = view
        view.prop_table = _DummyPropTable()

        self._scene = scene
        self._view = view
        return view

    def _redraw_in_place(self) -> None:
        if self.tree is None or self._scene is None or self._view is None:
            return

        view = self._view
        transform = view.transform()
        h_value = view.horizontalScrollBar().value()
        v_value = view.verticalScrollBar().value()

        self.tree_style = self._build_tree_style()
        self._scene.init_values(self.tree, self.tree_style, {}, {})
        self._scene.draw()

        view.setTransform(transform)
        view.horizontalScrollBar().setValue(h_value)
        view.verticalScrollBar().setValue(v_value)
        view.viewport().update()

    def extract_node_from_item(self, item) -> Optional[object]:
        visited = set()
        current = item

        candidate_attrs = [
            "node",
            "n",
            "_node",
            "item_node",
            "tree_node",
            "face_node",
        ]

        while current is not None and id(current) not in visited:
            visited.add(id(current))

            for attr in candidate_attrs:
                if hasattr(current, attr):
                    value = getattr(current, attr)
                    if value is not None:
                        return value

            for attr in ["obj", "_obj", "face", "_face"]:
                if hasattr(current, attr):
                    holder = getattr(current, attr)
                    if holder is not None:
                        for node_attr in candidate_attrs:
                            if hasattr(holder, node_attr):
                                value = getattr(holder, node_attr)
                                if value is not None:
                                    return value

            parent_method = getattr(current, "parentItem", None)
            if callable(parent_method):
                current = parent_method()
            else:
                current = None

        return None

    def build_selected_node_info(self, node: object) -> SelectedNodeInfo:
        name = getattr(node, "name", "") or "<内部节点>"
        node_id = getattr(node, "_rasp_id", "") or "<未分配ID>"
        clade_signature = self._build_clade_signature(node)

        is_leaf = False
        children_count = 0

        is_leaf_method = getattr(node, "is_leaf", None)
        if callable(is_leaf_method):
            try:
                is_leaf = bool(is_leaf_method())
            except Exception:
                is_leaf = False

        children = getattr(node, "children", None)
        if children is not None:
            try:
                children_count = len(children)
            except Exception:
                children_count = 0

        return SelectedNodeInfo(
            node_id=node_id,
            name=name,
            is_leaf=is_leaf,
            children_count=children_count,
            clade_signature=clade_signature,
        )

    def bind_click_callback(self, callback: Callable[[dict], None]) -> None:
        self._click_callback = callback

        if self._view is None:
            raise ValueError("树视图尚未构建，无法绑定点击事件")

        view = self._view
        original_mouse_release = view.mouseReleaseEvent
        adapter = self

        def patched_mouse_release(event):
            original_mouse_release(event)

            try:
                item = view.itemAt(event.pos())
                if item is None:
                    callback({"error": "未点击到可识别节点"})
                    return

                node = adapter.extract_node_from_item(item)
                if node is None:
                    callback({"error": "点击到图元，但未识别出对应节点"})
                    return

                if bool(getattr(node, "_rasp_dummy", False)):
                    callback({"error": "Clicked a rendered gradient segment, not an analysis node."})
                    return

                info = adapter.build_selected_node_info(node)
                callback(info.to_dict())
            except Exception as exc:
                callback({"error": f"节点识别失败: {exc}"})

        view.mouseReleaseEvent = patched_mouse_release

    def get_leaf_names(self):
        if self.tree is None:
            return []
        return self.tree.get_leaf_names()

    def get_tree(self):
        return self.tree

    def export_png(self, file_path: str) -> None:
        if self.tree is None:
            raise ValueError("当前没有可导出的树")
        self.tree.render(file_path, tree_style=self.tree_style, w=2000, units="px")

    def export_svg(self, file_path: str) -> None:
        if self.tree is None:
            raise ValueError("当前没有可导出的树")
        self.tree.render(file_path, tree_style=self.tree_style)

    def export_pdf(self, file_path: str) -> None:
        if self.tree is None:
            raise ValueError("当前没有可导出的树")
        self.tree.render(file_path, tree_style=self.tree_style)

    def select_node_by_clade_key(self, clade_key: str) -> Optional[dict]:
        self._selected_clade_key = str(clade_key or "").strip()

        if self.tree is None:
            return None

        if not self._selected_clade_key:
            return None

        matched_node = None
        for node in self.tree.traverse():
            if bool(getattr(node, "_rasp_dummy", False)):
                continue
            if node.is_leaf():
                continue
            sig = self._build_clade_signature(node)
            if sig == self._selected_clade_key:
                matched_node = node
                break

        if matched_node is None:
            return None

        info = self.build_selected_node_info(matched_node)
        return info.to_dict()
