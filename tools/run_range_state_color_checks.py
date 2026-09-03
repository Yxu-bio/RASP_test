import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / "infrastructure" / "tree" / "backend" / "ete3_vendor"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QImage, QPainter
from PyQt5.QtWidgets import QApplication
from ete3 import Tree

from domain.models.biogeobears_result import BioGeoBEARSResult
from domain.services.range_state_color_mapper import RangeStateColorMapper
from gui.dialogs.result_view_window import ResultViewWindow
from gui.widgets.node_info_panel import NodeInfoPanel, SegmentedColorSwatch
from infrastructure.dec.dec_output_parser import DECOutputParser
from infrastructure.tree.composite_range_pie_face import _CompositeRangePieItem
from infrastructure.tree.tree_reader import TreeReader
from visualization.renderers.dec_result_renderer import DECResultRenderer


def _assert_palette_contract():
    states = ["A", "B", "AB", "ABC", "EMPTY", "*"]
    palette = RangeStateColorMapper.build(states, area_order=["A", "B", "C"])
    assert palette.area_colors["A"] == "#e41a1c"
    assert palette.area_colors["B"] == "#377eb8"
    assert palette.state_colors["A"] == palette.area_colors["A"]
    assert palette.state_colors["B"] == palette.area_colors["B"]
    assert palette.state_area_members["AB"] == ["A", "B"]
    assert palette.state_area_members["ABC"] == ["A", "B", "C"]
    assert palette.state_colors["AB"] not in {palette.state_colors["A"], palette.state_colors["B"]}
    assert palette.independent_state_colors["AB"] not in {
        palette.independent_state_colors["A"],
        palette.independent_state_colors["B"],
    }
    assert palette.biogeobears_state_colors["AB"] == RangeStateColorMapper.mix_colors(
        [palette.area_colors["A"], palette.area_colors["B"]]
    )
    assert palette.biogeobears_state_colors["ABC"] == "#ffffff"
    assert palette.biogeobears_state_colors["EMPTY"] == "#000000"
    assert palette.state_colors["EMPTY"] == "#ffffff"
    assert palette.state_colors["*"] == "#000000"

    reordered = RangeStateColorMapper.build(
        list(reversed(states)),
        area_order=["A", "B", "C"],
    )
    assert reordered.state_colors["AB"] == palette.state_colors["AB"]

    custom = RangeStateColorMapper.build(
        states,
        area_order=["A", "B", "C"],
        base_colors={"A": "#00ff00"},
    )
    assert custom.area_colors["A"] == "#00ff00"
    assert custom.state_colors["AB"] != palette.state_colors["AB"]
    assert custom.state_colors["B"] == palette.state_colors["B"]

    named = RangeStateColorMapper.build(
        ["East", "West", "EastWest"],
        area_order=["East", "West"],
    )
    assert named.state_area_members["EastWest"] == ["East", "West"]


def _assert_composite_pie_pixels():
    colors = ["#e41a1c", "#377eb8"]
    item = _CompositeRangePieItem([100.0], 48, 48, [colors])
    image = QImage(48, 48, QImage.Format_ARGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    item.paint(painter, None, None)
    painter.end()
    pixels = {
        image.pixelColor(x, y).name()
        for x in range(image.width())
        for y in range(image.height())
    }
    assert colors[0] in pixels
    assert colors[1] in pixels


def _assert_segmented_legend():
    result = BioGeoBEARSResult(reference_tree=None)
    result.state_order = ["AB"]
    RangeStateColorMapper.apply_to_result(result, area_order=["A", "B"])
    panel = NodeInfoPanel()
    panel.set_standard_result("DEC", result, [])
    assert panel.range_color_mode == "independent"
    assert panel.legend_table.cellWidget(0, 1) is None
    assert panel.legend_table.item(0, 1).data(Qt.UserRole) == result.independent_state_colors["AB"]
    assert panel.color_table.rowCount() == 1
    assert panel.color_table.item(0, 0).text() == "AB"

    panel.set_range_color_mode("biogeobears")
    mixed_swatch = panel.legend_table.cellWidget(0, 1)
    assert isinstance(mixed_swatch, SegmentedColorSwatch)
    assert mixed_swatch.colors == [result.biogeobears_state_colors["AB"]]

    panel.set_range_color_mode("composition")
    swatch = panel.legend_table.cellWidget(0, 1)
    assert isinstance(swatch, SegmentedColorSwatch)
    assert swatch.colors == [result.area_colors["A"], result.area_colors["B"]]
    assert panel.color_table.item(0, 0).text() == "A"
    assert panel.color_table.item(1, 0).text() == "B"
    assert panel.color_table.item(2, 0).text() == "AB"
    assert panel.color_table.cellWidget(2, 1).colors == swatch.colors
    panel.close()


def _assert_non_range_colors_unchanged():
    result = BioGeoBEARSResult(reference_tree=None)
    result.state_order = ["0", "1"]
    result.state_colors = {"0": "#123456", "1": "#abcdef"}
    panel = NodeInfoPanel()
    panel.set_standard_result("BayesTraits-MULTISTATE", result, [])
    assert panel.legend_table.item(0, 1).data(Qt.UserRole) == "#123456"
    panel.set_range_color_mode("composition")
    assert panel.legend_table.item(1, 1).data(Qt.UserRole) == "#abcdef"
    panel.close()

    window = ResultViewWindow()
    window.set_result(result)
    assert not window.range_color_combo_action.isVisible()
    window.close()


def _assert_dec_integration():
    tree_path = ROOT / "data" / "benchmarks" / "psychotria" / "Psychotria.tree"
    result_path = ROOT / "data" / "benchmarks" / "psychotria" / "dec_results_fixture.json"
    newick = TreeReader().read_tree(str(tree_path))
    tree = Tree(newick, format=1)
    result = DECOutputParser().parse(
        reference_tree=tree,
        area_names=["A", "B", "C", "D"],
        results_json_path=result_path,
        nodes_tree_path=result_path,
    )
    assert result.area_order == ["A", "B", "C", "D"]
    assert result.state_area_members["AB"] == ["A", "B"]
    assert result.state_colors["AB"] == RangeStateColorMapper.mix_colors(
        [result.area_colors["A"], result.area_colors["B"]]
    )
    assert any(
        "AB" in list(getattr(node, "pie_labels", []) or [])
        and result.state_colors["AB"] in list(getattr(node, "pie_colors", []) or [])
        for node in result.node_results.values()
    )
    renderer = DECResultRenderer()
    renderer.set_tree(tree)
    renderer.set_result(result)
    renderer.set_show_leaf_name(False)
    view = renderer.build_view()
    assert view.scene() is not None
    assert not view.scene().sceneRect().isEmpty()
    assert not any(
        isinstance(item, _CompositeRangePieItem)
        for item in view.scene().items()
    )
    view.close()

    renderer.set_range_color_mode("biogeobears")
    mixed_node = next(
        node
        for node in result.node_results.values()
        if any(
            len(result.state_area_members.get(label, [])) > 1
            for label in list(getattr(node, "pie_labels", []) or [])
        )
    )
    assert renderer.adapter._display_pie_colors(mixed_node) == [
        result.biogeobears_state_colors[label]
        for label in mixed_node.pie_labels
    ]
    mixed_view = renderer.build_view()
    assert not any(
        isinstance(item, _CompositeRangePieItem)
        for item in mixed_view.scene().items()
    )
    mixed_view.close()

    renderer.set_range_color_mode("composition")
    composition_view = renderer.build_view()
    assert any(
        isinstance(item, _CompositeRangePieItem)
        for item in composition_view.scene().items()
    )
    composition_view.close()

    result.area_colors = {}
    result.state_area_members = {}
    legacy_renderer = DECResultRenderer()
    legacy_renderer.set_tree(tree)
    legacy_renderer.set_result(result)
    legacy_renderer.set_show_leaf_name(False)
    legacy_view = legacy_renderer.build_view()
    assert not any(
        isinstance(item, _CompositeRangePieItem)
        for item in legacy_view.scene().items()
    )
    legacy_view.close()

    RangeStateColorMapper.apply_to_result(result, area_order=["A", "B", "C", "D"])
    window_renderer = DECResultRenderer()
    window_renderer.set_tree(tree)
    window_renderer.set_result(result)
    window = ResultViewWindow()
    window.set_renderer(window_renderer)
    leaf_name = next(tree.iter_leaves()).name
    extra_leaf_state = "A_B"
    assert extra_leaf_state not in result.state_order
    window.set_leaf_state_context({leaf_name: extra_leaf_state})
    window.set_result(result)
    assert window.range_color_combo.currentData() == "independent"
    assert window.range_color_combo_action.isVisible()
    assert window_renderer.adapter._range_color_mode == "independent"
    assert window_renderer.adapter._leaf_state_colors[extra_leaf_state] != "#808080"

    selected_key = next(
        key
        for key, node in result.node_results.items()
        if any(
            len(result.state_area_members.get(label, [])) > 1
            for label in list(getattr(node, "pie_labels", []) or [])
        )
    )
    window._set_selected_clade(selected_key, toggle=False)
    assert window.current_selected_clade_key == selected_key
    color_column = window.node_info_panel.legend_table.columnCount() - 1
    assert all(
        window.node_info_panel.legend_table.cellWidget(row, color_column) is None
        for row in range(window.node_info_panel.legend_table.rowCount())
    )

    independent_state = result.state_order[0]
    composition_color_before = result.state_colors[independent_state]
    window._on_state_color_changed(independent_state, "#13579b")
    assert result.independent_state_colors[independent_state] == "#13579b"
    assert result.state_colors[independent_state] == composition_color_before

    tree_widget = window.tree_panel.tree_widget
    tree_widget.scale(1.35, 1.35)
    app = QApplication.instance()
    app.processEvents()
    transform_before = float(tree_widget.transform().m11())
    horizontal_before = tree_widget.horizontalScrollBar().value()
    vertical_before = tree_widget.verticalScrollBar().value()

    mixed_index = window.range_color_combo.findData("biogeobears")
    window.range_color_combo.setCurrentIndex(mixed_index)
    assert window_renderer.adapter._range_color_mode == "biogeobears"
    assert window.node_info_panel.range_color_mode == "biogeobears"
    assert window.current_selected_clade_key == selected_key
    assert abs(float(window.tree_panel.tree_widget.transform().m11()) - transform_before) < 1.0e-9
    assert window_renderer.adapter._leaf_state_colors[extra_leaf_state] != "#808080"

    composition_index = window.range_color_combo.findData("composition")
    window.range_color_combo.setCurrentIndex(composition_index)
    assert window_renderer.adapter._range_color_mode == "composition"
    assert window.node_info_panel.range_color_mode == "composition"
    assert window.current_selected_clade_key == selected_key
    assert window_renderer.adapter._selected_clade_key == selected_key
    assert abs(float(window.tree_panel.tree_widget.transform().m11()) - transform_before) < 1.0e-9
    assert window.tree_panel.tree_widget.horizontalScrollBar().value() == horizontal_before
    assert window.tree_panel.tree_widget.verticalScrollBar().value() == vertical_before
    assert window_renderer.adapter._leaf_state_colors[extra_leaf_state] != "#808080"
    assert any(
        isinstance(
            window.node_info_panel.legend_table.cellWidget(
                row,
                window.node_info_panel.legend_table.columnCount() - 1,
            ),
            SegmentedColorSwatch,
        )
        for row in range(window.node_info_panel.legend_table.rowCount())
    )

    window._on_state_color_changed("A", "#2468ac")
    assert result.area_colors["A"] == "#2468ac"
    assert result.biogeobears_state_colors["A"] == "#2468ac"
    assert result.independent_state_colors[independent_state] == "#13579b"
    window.close()


def main():
    app = QApplication.instance() or QApplication([])
    _assert_palette_contract()
    _assert_composite_pie_pixels()
    _assert_segmented_legend()
    _assert_non_range_colors_unchanged()
    _assert_dec_integration()
    app.processEvents()
    print("Range-state color checks passed.")


if __name__ == "__main__":
    main()
