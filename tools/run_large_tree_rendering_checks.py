# -*- coding: utf-8 -*-
import gc
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENDOR_ROOT = PROJECT_ROOT / "infrastructure" / "tree" / "backend" / "ete3_vendor"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt5 import sip
except ImportError:
    import sip
from PyQt5.QtCore import QCoreApplication, QEvent
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication
from ete3 import Tree

from domain.models.biogeobears_result import BioGeoBEARSNodeResult, BioGeoBEARSResult
from domain.models.continuous_trait_result import (
    ContinuousTraitNodeResult,
    ContinuousTraitResult,
)
from domain.models.dec_result import DECNodeResult, DECResult
from domain.models.diva_result import DivaNodeResult, DivaResult
from domain.services.range_state_color_mapper import RangeStateColorMapper
from gui.dialogs.result_view_window import (
    LINEAGE_RANGE_DYNAMICS_ENABLED,
    ResultViewWindow,
)
from infrastructure.tree.tree_reader import TreeReader
from infrastructure.tree.composite_range_pie_face import _CompositeRangePieItem
from visualization.renderers.biogeobears_result_renderer import BioGeoBEARSResultRenderer
from visualization.renderers.continuous_trait_result_renderer import (
    ContinuousTraitResultRenderer,
)
from visualization.renderers.dec_result_renderer import DECResultRenderer
from visualization.renderers.diva_result_renderer import DivaResultRenderer


COLORS = ["#4e79a7", "#59a14f", "#f28e2b", "#e15759", "#76b7b2", "#edc948", "#b07aa1"]
STATES = list("ABCDEFG")
RANGE_STATES = ["A", "B", "AB", "C", "ABC", "D", "CD"]
RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
RUN_ROOT = PROJECT_ROOT / "runs" / "large_tree_rendering" / RUN_STAMP
REPORT_PATH = RUN_ROOT / "report.json"
LATEST_PATH = PROJECT_ROOT / "docs" / "large_tree_rendering_latest.md"
LARGE_TREE_PATH = (
    PROJECT_ROOT
    / "data"
    / "benchmarks"
    / "dore_ponerinae"
    / "final_inputs"
    / "Ponerinae_phylogeny_MCC_1534t.tree"
)


class LargeTreeCheckFailure(AssertionError):
    pass


def git_output(*args):
    try:
        return subprocess.check_output(
            ["git"] + list(args),
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.STDOUT,
        ).decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def load_large_tree():
    return Tree(LARGE_TREE_PATH.read_text(encoding="utf-8").strip(), format=1)


def clade_key(node):
    return "|".join(sorted(str(leaf.name).strip() for leaf in node.iter_leaves()))


def internal_records(tree):
    tip_count = len(tree)
    records = []
    internal_index = 0
    for traversal_index, node in enumerate(tree.traverse("postorder")):
        if node.is_leaf():
            continue
        internal_index += 1
        records.append({
            "key": clade_key(node),
            "display_id": str(tip_count + internal_index),
            "state": RANGE_STATES[traversal_index % len(RANGE_STATES)],
            "value": float(traversal_index % 101) / 100.0,
        })
    return records


def leaf_states(tree):
    return {
        str(leaf.name): STATES[index % len(STATES)]
        for index, leaf in enumerate(tree.iter_leaves())
    }


def build_diva_result(tree):
    result = DivaResult(dataset=SimpleNamespace(reference_tree=tree))
    result.state_order = list(RANGE_STATES)
    for record in internal_records(tree):
        result.node_results[record["key"]] = DivaNodeResult(
            node_key=record["key"],
            diva_node_id=int(record["display_id"]),
            terminal_spec="",
            states=[record["state"]],
            state_supports={record["state"]: 100.0},
            pie_labels=[record["state"]],
            pie_percents=[100.0],
            pie_colors=[],
        )
    RangeStateColorMapper.apply_to_result(result, area_order=STATES)
    return result


def build_dec_result(tree):
    result = DECResult(reference_tree=tree)
    result.state_order = list(RANGE_STATES)
    for record in internal_records(tree):
        result.node_results[record["key"]] = DECNodeResult(
            node_key=record["key"],
            display_node_id=record["display_id"],
            states=[record["state"]],
            pie_labels=[record["state"]],
            pie_percents=[100.0],
            pie_colors=[],
        )
        result.reference_node_ids[record["key"]] = record["display_id"]
    RangeStateColorMapper.apply_to_result(result, area_order=STATES)
    return result


def build_bgb_result(tree):
    result = BioGeoBEARSResult(reference_tree=tree, model_name="BioGeoBEARS-DEC")
    result.state_order = list(RANGE_STATES)
    for record in internal_records(tree):
        result.node_results[record["key"]] = BioGeoBEARSNodeResult(
            node_key=record["key"],
            display_node_id=record["display_id"],
            states=[record["state"]],
            state_supports={record["state"]: 100.0},
            pie_labels=[record["state"]],
            pie_percents=[100.0],
            pie_colors=[],
        )
        result.reference_node_ids[record["key"]] = record["display_id"]
    RangeStateColorMapper.apply_to_result(result, area_order=STATES)
    return result


def build_continuous_result(tree):
    result = ContinuousTraitResult(reference_tree=tree)
    result.trait_name = "Synthetic continuous benchmark"
    result.color_scale_min = 0.0
    result.color_scale_max = 1.0
    leaves = list(tree.iter_leaves())
    denominator = float(max(1, len(leaves) - 1))
    for index, leaf in enumerate(leaves):
        value = float(index) / denominator
        result.tip_values[str(leaf.name)] = value
        result.plot_tip_values[str(leaf.name)] = value
    for record in internal_records(tree):
        value = record["value"]
        result.node_results[record["key"]] = ContinuousTraitNodeResult(
            node_key=record["key"],
            display_node_id=record["display_id"],
            trait_name=result.trait_name,
            mean=value,
            median=value,
            lower95=max(0.0, value - 0.05),
            upper95=min(1.0, value + 0.05),
            sample_count=100,
        )
        result.plot_node_values[record["key"]] = value
        result.reference_node_ids[record["key"]] = record["display_id"]
    return result


def build_discrete_renderer(renderer_class, tree, result):
    renderer = renderer_class()
    renderer.set_tree(tree)
    renderer.apply_leaf_states(leaf_states(tree), dict(zip(STATES, COLORS)))
    renderer.set_result(result)
    return renderer


def assert_scene(view, name):
    rect = view.scene().sceneRect()
    if rect.isEmpty() or rect.width() <= 0 or rect.height() <= 0:
        raise LargeTreeCheckFailure("%s produced an empty scene" % name)
    if rect.width() >= 5000.0:
        raise LargeTreeCheckFailure("%s circular scene is unexpectedly wide: %s" % (name, rect.width()))
    return {"scene_width": rect.width(), "scene_height": rect.height()}


def dispose_view(view):
    if view is None:
        return
    scene = view.scene()
    view.close()
    view.setScene(None)
    if scene is not None:
        try:
            scene.view = None
        except Exception:
            pass
        scene.deleteLater()
    view.deleteLater()


def dispose_renderer(renderer):
    adapter = getattr(renderer, "adapter", None)
    if adapter is None:
        return
    dispose_view(getattr(adapter, "_view", None))
    adapter._view = None
    adapter._scene = None


def exercise_renderer(app, name, renderer, result):
    if renderer.get_leaf_count() != 1534 or not renderer.is_large_tree():
        raise LargeTreeCheckFailure("%s did not enter the large-tree profile" % name)
    renderer.set_show_leaf_name(False)
    renderer.set_display_profile("auto")
    renderer.set_circular_enabled(True)
    if getattr(result, "state_area_members", None):
        if renderer.adapter._range_color_mode != "independent":
            raise LargeTreeCheckFailure(
                "%s did not default to independent range colors" % name
            )
        renderer.set_range_color_mode("composition")
    started = time.perf_counter()
    view = renderer.build_view()
    elapsed = time.perf_counter() - started
    if elapsed >= 20.0:
        raise LargeTreeCheckFailure("%s circular build took %.3f seconds" % (name, elapsed))
    metrics = assert_scene(view, name)
    if getattr(result, "state_area_members", None):
        composite_marker_count = sum(
            isinstance(item, _CompositeRangePieItem)
            for item in view.scene().items()
        )
        if composite_marker_count <= 0:
            raise LargeTreeCheckFailure(
                "%s large-tree overview lost composite range markers" % name
            )
        metrics["composite_marker_count"] = composite_marker_count
    view.resize(1400, 900)
    view.show()
    app.processEvents()

    initial_scale = float(view.transform().m11())
    renderer.zoom_in()
    zoomed_scale = float(view.transform().m11())
    if zoomed_scale <= initial_scale:
        raise LargeTreeCheckFailure("%s zoom-in did not change the view transform" % name)
    renderer.zoom_out()
    renderer.fit_to_view()
    app.processEvents()

    selected_key = next(iter(result.node_results))
    payload = renderer.select_node_by_clade_key(selected_key)
    if not payload or str(payload.get("clade_signature", "")) != selected_key:
        raise LargeTreeCheckFailure("%s could not select an internal node" % name)
    renderer.set_circular_enabled(False)
    rectangular_view = renderer.build_view()
    rectangular_view.resize(1400, 900)
    rectangular_view.show()
    app.processEvents()
    renderer.fit_to_view()
    app.processEvents()
    rectangular_rect = rectangular_view.scene().sceneRect()
    vertical_pixels = rectangular_rect.height() * rectangular_view.transform().m22()
    if vertical_pixels <= rectangular_view.viewport().height() * 2.0:
        raise LargeTreeCheckFailure("%s rectangular tree was compressed into a black line" % name)
    if renderer.adapter._selected_clade_key != selected_key:
        raise LargeTreeCheckFailure("%s lost selection while changing layout" % name)
    if renderer.adapter._show_leaf_name:
        raise LargeTreeCheckFailure("%s unexpectedly restored large-tree labels" % name)

    dispose_view(view)
    dispose_view(rectangular_view)
    renderer.adapter._view = None
    renderer.adapter._scene = None
    metrics.update({
        "circular_build_seconds": elapsed,
        "rectangular_scene_height": rectangular_rect.height(),
        "rectangular_scaled_height": vertical_pixels,
        "selection_preserved": True,
    })
    return metrics


def check_leaf_marker_anchor(renderer):
    renderer.set_circular_enabled(True)
    renderer.set_show_leaf_name(False)
    view = renderer.build_view()
    offsets = []
    for leaf in renderer.adapter.tree.iter_leaves():
        item = renderer.adapter._scene.n2i[leaf]
        node_ball = item.mapped_items[0]
        if node_ball is not None:
            offsets.append(abs(float(node_ball.pos().x()) - float(item.branch_length)))
    dispose_view(view)
    renderer.adapter._view = None
    renderer.adapter._scene = None
    if not offsets or max(offsets) >= 1.0e-6:
        raise LargeTreeCheckFailure("Circular tip markers are not anchored at branch ends")
    return max(offsets)


def validate_export(path, kind):
    path = Path(path)
    if not path.exists() or path.stat().st_size < 1000:
        raise LargeTreeCheckFailure("%s export is missing or too small: %s" % (kind, path))
    if kind == "png":
        image = QImage(str(path))
        if image.isNull():
            raise LargeTreeCheckFailure("PNG export cannot be decoded")
        colors = set()
        step_x = max(1, image.width() // 60)
        step_y = max(1, image.height() // 60)
        for y in range(0, image.height(), step_y):
            for x in range(0, image.width(), step_x):
                colors.add(int(image.pixel(x, y)))
        if len(colors) < 4:
            raise LargeTreeCheckFailure("PNG export appears blank")
    elif kind == "svg":
        if b"<svg" not in path.read_bytes()[:4096].lower():
            raise LargeTreeCheckFailure("SVG export does not contain an SVG document")
    elif kind == "pdf":
        if not path.read_bytes().startswith(b"%PDF"):
            raise LargeTreeCheckFailure("PDF export does not contain a PDF header")
    return path.stat().st_size


def exercise_exports(tree, result):
    renderer = build_discrete_renderer(BioGeoBEARSResultRenderer, tree, result)
    renderer.set_show_leaf_name(False)
    renderer.set_display_profile("auto")
    renderer.set_circular_enabled(True)
    renderer.build_view()
    paths = {
        "png": RUN_ROOT / "large_tree.png",
        "svg": RUN_ROOT / "large_tree.svg",
        "pdf": RUN_ROOT / "large_tree.pdf",
    }
    renderer.export_tree_png(str(paths["png"]))
    renderer.export_tree_svg(str(paths["svg"]))
    renderer.export_tree_pdf(str(paths["pdf"]))
    sizes = dict((kind, validate_export(path, kind)) for kind, path in paths.items())
    dispose_renderer(renderer)
    return sizes


def exercise_result_window(app, tree, result):
    renderer = build_discrete_renderer(BioGeoBEARSResultRenderer, tree, result)
    window = ResultViewWindow()
    window.set_window_title_by_method("BioGeoBEARS-DEC")
    window.set_renderer(renderer)
    window.set_result(result)
    if not window.circular_tree_action.isChecked():
        raise LargeTreeCheckFailure("Large result window did not default to circular layout")
    if window.show_leaf_name_action.isChecked():
        raise LargeTreeCheckFailure("Large result window did not hide leaf labels")
    if not window.tree_detail_combo_action.isVisible():
        raise LargeTreeCheckFailure("Large result window did not expose Tree detail")
    if hasattr(window, "temporal_playback_action"):
        raise LargeTreeCheckFailure("Sealed Lineage Range Dynamics leaked into the result toolbar")

    selected_key = next(iter(result.node_results))
    window._set_selected_clade(selected_key, toggle=False)
    window._toggle_branch_length(True)
    window.tree_detail_combo.setCurrentIndex(1)
    window._toggle_circular_tree(False)
    window._toggle_circular_tree(True)
    app.processEvents()
    if window.current_selected_clade_key != selected_key:
        raise LargeTreeCheckFailure("Result-window refresh lost the selected clade")
    if renderer.adapter._selected_clade_key != selected_key:
        raise LargeTreeCheckFailure("Renderer refresh lost the selected clade")
    if not renderer.adapter._show_branch_length:
        raise LargeTreeCheckFailure("Renderer refresh lost the branch-length setting")
    if renderer.get_display_profile() != "overview":
        raise LargeTreeCheckFailure("Renderer refresh lost the Tree detail setting")
    dispose_renderer(renderer)
    window.close()
    window.deleteLater()
    return {"selection_preserved": True, "profile": "overview"}


def run_main_window_probe(output_path):
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    tree = load_large_tree()
    result = build_bgb_result(tree)
    window = MainWindow()
    window.current_tree = tree
    window.current_method_name = "BioGeoBEARS-DEC"
    window.current_biogeobears_result = result
    window.open_result_action.trigger()
    app.processEvents()
    result_window = window.current_result_window
    if result_window is None or not result_window.isVisible():
        raise LargeTreeCheckFailure("Open Result Window did not open the actual result window")
    if "BioGeoBEARS-DEC" not in result_window.windowTitle():
        raise LargeTreeCheckFailure("Actual result-window title does not identify the method")
    if not result_window.circular_tree_action.isChecked():
        raise LargeTreeCheckFailure("Actual menu entry bypassed the large-tree defaults")
    title = result_window.windowTitle()
    payload = {"window_title": title, "visible": True}
    Path(output_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sys.stdout.flush()
    # Full MainWindow imports Qt WebEngine-backed spatial widgets. In an
    # offscreen one-shot probe, Windows can wait indefinitely during Qt module
    # teardown even after every window is closed. The parent process owns the
    # timeout and validates this result file before accepting the probe.
    os._exit(0)


def exercise_main_window_entry():
    output_path = RUN_ROOT / "main_window_probe.json"
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--main-window-probe", str(output_path)],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        universal_newlines=True,
    )
    if proc.returncode != 0:
        raise LargeTreeCheckFailure(
            "Actual MainWindow probe failed: %s" % ((proc.stderr or proc.stdout).strip())
        )
    if not output_path.exists():
        raise LargeTreeCheckFailure("Actual MainWindow probe did not write its result")
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    if not payload.get("visible"):
        raise LargeTreeCheckFailure("Actual MainWindow probe did not show the result window")
    return payload


def write_latest(report):
    lines = [
        "# 1534-tip 大树与结果视图门禁（最新）",
        "",
        "状态：**Passed**",
        "",
        "- 运行时间：`%s`" % report["generated_at"],
        "- Git commit：`%s`" % report["git_commit"],
        "- 固定树：`%s`" % report["input_tree"],
        "- tips：`%s`；internal nodes：`%s`" % (
            report["tip_count"], report["internal_node_count"]
        ),
        "- 机器可读报告：`%s`" % report["report_path"],
        "",
        "## Renderer",
        "",
    ]
    for name, metrics in report["renderers"].items():
        lines.append(
            "- `%s`：circular `%.3f s`，scene `%.1f x %.1f`，选择与布局状态保持。"
            % (
                name,
                metrics["circular_build_seconds"],
                metrics["scene_width"],
                metrics["scene_height"],
            )
        )
    lines.extend([
        "",
        "## 交互与导出",
        "",
        "- 圆形 tip marker 最大 branch-end 偏移：`%.12g`。" % report["tip_marker_max_offset"],
        "- ResultViewWindow 刷新后保留 selected clade、branch length 和 detail profile。",
        "- 实际 `Open Result Window` 菜单入口已打开 1534-tip BGB 结果窗口。",
        "- PNG/SVG/PDF 字节数：`%s`。" % report["exports"],
        "- Lineage Range Dynamics 公开入口保持封锁；其内部 temporal 原型由独立 checker 管理。",
        "",
    ])
    LATEST_PATH.write_text("\n".join(lines), encoding="utf-8")


def main():
    app = QApplication.instance() or QApplication([])
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    if LINEAGE_RANGE_DYNAMICS_ENABLED:
        raise LargeTreeCheckFailure("Lineage Range Dynamics must remain sealed during WP3")

    renderer_specs = [
        ("DIVA", DivaResultRenderer, build_diva_result),
        ("DEC", DECResultRenderer, build_dec_result),
        ("BioGeoBEARS", BioGeoBEARSResultRenderer, build_bgb_result),
    ]
    renderer_reports = {}
    for name, renderer_class, result_builder in renderer_specs:
        tree = load_large_tree()
        result = result_builder(tree)
        renderer = build_discrete_renderer(renderer_class, tree, result)
        renderer_reports[name] = exercise_renderer(app, name, renderer, result)

    continuous_tree = load_large_tree()
    continuous_result = build_continuous_result(continuous_tree)
    continuous_renderer = ContinuousTraitResultRenderer()
    continuous_renderer.set_tree(continuous_tree)
    continuous_renderer.set_result(continuous_result)
    renderer_reports["ContinuousTrait"] = exercise_renderer(
        app, "ContinuousTrait", continuous_renderer, continuous_result
    )

    anchor_tree = load_large_tree()
    anchor_result = build_bgb_result(anchor_tree)
    anchor_renderer = build_discrete_renderer(
        BioGeoBEARSResultRenderer, anchor_tree, anchor_result
    )
    tip_marker_max_offset = check_leaf_marker_anchor(anchor_renderer)

    export_tree = load_large_tree()
    export_result = build_bgb_result(export_tree)
    exports = exercise_exports(export_tree, export_result)

    result_window_tree = load_large_tree()
    result_window_result = build_bgb_result(result_window_tree)
    result_window_report = exercise_result_window(
        app, result_window_tree, result_window_result
    )

    main_window_report = exercise_main_window_entry()

    small_newick = TreeReader().read_tree(
        str(PROJECT_ROOT / "data" / "benchmarks" / "psychotria" / "Psychotria.tree")
    )
    small_tree = Tree(small_newick, format=1)
    small_renderer = BioGeoBEARSResultRenderer()
    small_renderer.set_tree(small_tree)
    if small_renderer.is_large_tree() or small_renderer.get_leaf_count() != 19:
        raise LargeTreeCheckFailure("Small-tree profile regression")

    app.closeAllWindows()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    gc.collect()

    report = {
        "status": "passed",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_output("rev-parse", "HEAD"),
        "git_status_porcelain": git_output("status", "--porcelain").splitlines(),
        "report_path": str(REPORT_PATH),
        "run_root": str(RUN_ROOT),
        "input_tree": str(LARGE_TREE_PATH),
        "tip_count": 1534,
        "internal_node_count": 1533,
        "small_tree_tip_count": 19,
        "renderers": renderer_reports,
        "tip_marker_max_offset": tip_marker_max_offset,
        "exports": exports,
        "result_window": result_window_report,
        "main_window_entry": main_window_report,
        "lineage_range_dynamics_public_enabled": LINEAGE_RANGE_DYNAMICS_ENABLED,
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_latest(report)
    app.quit()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    gc.collect()
    sip.delete(app)
    print("large-tree rendering checks passed")
    print("Report: %s" % REPORT_PATH)
    print("Latest: %s" % LATEST_PATH)
    sys.stdout.flush()
    # Repeated ETE3/PyQt offscreen scene construction can leave Windows Qt
    # teardown waiting after the one-shot checks have completed. Reaching this
    # point means every assertion and artifact write succeeded.
    os._exit(0)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--main-window-probe":
        try:
            run_main_window_probe(Path(sys.argv[2]))
        except Exception as exc:
            sys.stderr.write("MainWindow probe failed: %s\n" % exc)
            sys.stderr.flush()
            os._exit(1)
    else:
        try:
            main()
        except Exception:
            traceback.print_exc()
            sys.stderr.flush()
            os._exit(1)
