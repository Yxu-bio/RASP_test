import os
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENDOR_ROOT = PROJECT_ROOT / "infrastructure" / "tree" / "backend" / "ete3_vendor"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from ete3 import Tree

from domain.models.biogeobears_result import BioGeoBEARSNodeResult, BioGeoBEARSResult
from gui.dialogs.result_view_window import ResultViewWindow
from infrastructure.tree.tree_reader import TreeReader
from visualization.renderers.biogeobears_result_renderer import BioGeoBEARSResultRenderer


COLORS = ["#4e79a7", "#59a14f", "#f28e2b", "#e15759", "#76b7b2", "#edc948", "#b07aa1"]
STATES = list("ABCDEFG")


def build_result(tree):
    result = BioGeoBEARSResult(reference_tree=tree, model_name="BioGeoBEARS-DEC")
    result.state_order = list(STATES)
    result.state_colors = dict(zip(STATES, COLORS))
    for index, node in enumerate(tree.traverse("postorder")):
        if node.is_leaf():
            continue
        clade_key = "|".join(sorted(str(leaf.name).strip() for leaf in node.iter_leaves()))
        state = STATES[index % len(STATES)]
        result.node_results[clade_key] = BioGeoBEARSNodeResult(
            node_key=clade_key,
            display_node_id=str(index + 1),
            states=[state],
            state_supports={state: 100.0},
            pie_labels=[state],
            pie_percents=[100.0],
            pie_colors=[COLORS[index % len(COLORS)]],
        )
    return result


def build_renderer(tree, result):
    renderer = BioGeoBEARSResultRenderer()
    renderer.set_tree(tree)
    renderer.apply_leaf_states(
        {
            str(leaf.name): STATES[index % len(STATES)]
            for index, leaf in enumerate(tree.iter_leaves())
        },
        result.state_colors,
    )
    renderer.set_result(result)
    return renderer


def main():
    app = QApplication.instance() or QApplication([])
    large_tree_path = (
        PROJECT_ROOT
        / "data"
        / "benchmarks"
        / "dore_ponerinae"
        / "final_inputs"
        / "Ponerinae_phylogeny_MCC_1534t.tree"
    )
    large_tree = Tree(large_tree_path.read_text(encoding="utf-8").strip(), format=1)
    result = build_result(large_tree)

    renderer = build_renderer(large_tree, result)
    assert renderer.get_leaf_count() == 1534
    assert renderer.is_large_tree()
    renderer.set_show_leaf_name(False)
    renderer.set_circular_enabled(True)
    started = time.perf_counter()
    circular_view = renderer.build_view()
    circular_seconds = time.perf_counter() - started
    circular_rect = circular_view.scene().sceneRect()
    assert circular_seconds < 15.0, circular_seconds
    assert circular_rect.width() < 4000.0, circular_rect.width()
    leaf_marker_offsets = []
    for leaf in renderer.adapter.tree.iter_leaves():
        item = renderer.adapter._scene.n2i[leaf]
        node_ball = item.mapped_items[0]
        if node_ball is not None:
            leaf_marker_offsets.append(
                abs(float(node_ball.pos().x()) - float(item.branch_length))
            )
    assert leaf_marker_offsets
    assert max(leaf_marker_offsets) < 1.0e-6, max(leaf_marker_offsets)

    renderer.set_circular_enabled(False)
    rectangular_view = renderer.build_view()
    rectangular_view.resize(1400, 900)
    rectangular_view.show()
    app.processEvents()
    renderer.fit_to_view()
    app.processEvents()
    rectangular_rect = rectangular_view.scene().sceneRect()
    vertical_pixels = rectangular_rect.height() * rectangular_view.transform().m22()
    assert vertical_pixels > rectangular_view.viewport().height() * 2.0

    window_renderer = build_renderer(large_tree, result)
    window = ResultViewWindow()
    window.set_renderer(window_renderer)
    assert window.circular_tree_action.isChecked()
    assert not window.show_leaf_name_action.isChecked()
    assert window.tree_detail_combo_action.isVisible()
    assert len(result.node_results) == 1533
    started = time.perf_counter()
    window.set_result(result)
    result_context_seconds = time.perf_counter() - started
    assert result_context_seconds < 5.0, result_context_seconds
    first_payload = next(iter(window.standard_node_payloads.values()))
    window.node_info_panel.show_standard_node_info({}, first_payload)
    assert window.node_info_panel.legend_table.rowCount() == len(
        first_payload.state_supports
    )

    small_newick = TreeReader().read_tree(
        str(PROJECT_ROOT / "data" / "benchmarks" / "psychotria" / "Psychotria.tree")
    )
    small_tree = Tree(small_newick, format=1)
    small_renderer = BioGeoBEARSResultRenderer()
    small_renderer.set_tree(small_tree)
    assert small_renderer.get_leaf_count() == 19
    assert not small_renderer.is_large_tree()

    print("large_tree_tips=1534")
    print("circular_build_seconds=%.3f" % circular_seconds)
    print("circular_scene_width=%.1f" % circular_rect.width())
    print("circular_leaf_marker_max_offset=%.6f" % max(leaf_marker_offsets))
    print("rectangular_scene_height=%.1f" % rectangular_rect.height())
    print("rectangular_scaled_height=%.1f" % vertical_pixels)
    print("small_tree_tips=19")
    print("result_context_seconds=%.3f" % result_context_seconds)
    print("large-tree rendering checks passed")


if __name__ == "__main__":
    main()
