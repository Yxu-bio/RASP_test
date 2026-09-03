import ast
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / "infrastructure" / "tree" / "backend" / "ete3_vendor"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog, QWidget

from application.services.spatial_data_service import SpatialDataService
from application.services.heuristic_event_summary_service import HeuristicEventSummaryService
from gui.dialogs.bayarea_config_dialog import BayAreaConfigDialog
from gui.dialogs.bayarea_tracer_dialog import BayAreaTracerDialog
from gui.dialogs.bayestraits_config_dialog import BayesTraitsConfigDialog
from gui.dialogs.bbm_config_dialog import BBMConfigDialog
from gui.dialogs.bsm_event_table_dialog import BSMEventTableDialog
from gui.dialogs.bsm_network_map_editor_dialog import BSMNetworkMapEditorDialog
from gui.dialogs.bsm_run_config_dialog import BSMRunConfigDialog
from gui.dialogs.dec_config_dialog import DECConfigDialog
from gui.dialogs.phytools_config_dialog import PhytoolsConfigDialog
from gui.dialogs.project_import_dialog import ProjectImportDialog
from gui.dialogs.region_geojson_builder_dialog import RegionGeoJsonBuilderDialog
from gui.dialogs.result_view_window import ContinuousFigureGroupDialog, ResultViewWindow
from gui.dialogs.sbgb_config_dialog import SBGBConfigDialog
from gui.dialogs.sdec_config_dialog import SDECConfigDialog
from gui.dialogs.sdiva_config_dialog import SDivaConfigDialog
from gui.dialogs.spatial_data_manager_dialog import SpatialDataManagerDialog
import gui.main_window as main_window_module
from gui.main_window import MainWindow
from gui.widgets.node_info_panel import NodeInfoPanel
from gui.window_behavior import configure_resizable_window


def _assert_resizable(window):
    flags = window.windowFlags()
    assert flags & Qt.WindowMinimizeButtonHint, type(window).__name__
    assert flags & Qt.WindowMaximizeButtonHint, type(window).__name__
    assert flags & Qt.WindowCloseButtonHint, type(window).__name__
    assert not flags & Qt.MSWindowsFixedSizeDialogHint, type(window).__name__
    assert window.isSizeGripEnabled(), type(window).__name__
    assert window.maximumWidth() > 1000000, type(window).__name__
    assert window.maximumHeight() > 1000000, type(window).__name__


def _call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _assert_all_dialog_classes_configured():
    missing = []
    for path in sorted((ROOT / "gui" / "dialogs").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if "QDialog" not in [_call_name(base) for base in node.bases]:
                continue
            init = next(
                (item for item in node.body if isinstance(item, ast.FunctionDef) and item.name == "__init__"),
                None,
            )
            configured = False
            if init is not None:
                for item in ast.walk(init):
                    if not isinstance(item, ast.Call):
                        continue
                    if _call_name(item.func) != "configure_resizable_window":
                        continue
                    if item.args and isinstance(item.args[0], ast.Name) and item.args[0].id == "self":
                        configured = True
                        break
            if not configured:
                missing.append("%s:%s" % (path.relative_to(ROOT), node.name))
    assert not missing, "Dialogs without shared window behavior: %s" % ", ".join(missing)


def _assert_ad_hoc_dialogs_configured():
    main_source = (ROOT / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert main_source.count("dialog = QDialog(self)") == 2
    assert main_source.count("configure_resizable_window(dialog)") == 3
    assert 'dialog = QFileDialog(self, title, "")' in main_source
    for relative_path in [
        "gui/dialogs/spatial_data_manager_dialog.py",
        "gui/dialogs/region_geojson_builder_dialog.py",
    ]:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "dialog = QFileDialog(self" in source
        assert "configure_resizable_window(dialog)" in source


def _assert_application_titles():
    main_source = (ROOT / "gui" / "main_window.py").read_text(encoding="utf-8-sig")
    bootstrap_source = (ROOT / "app" / "bootstrap.py").read_text(encoding="utf-8-sig")
    assert 'self.setWindowTitle("RASP5")' in main_source
    assert 'app.setApplicationName("RASP5")' in bootstrap_source
    assert 'dialog.setWindowTitle("Compare Models Using BioGeoBEARS")' in main_source


def _assert_result_window_refresh_policy():
    refresh_calls = []
    owner = SimpleNamespace(
        current_result_window=SimpleNamespace(isVisible=lambda: False),
        _update_result_window=lambda activate: refresh_calls.append(activate),
    )
    MainWindow._refresh_result_window_if_open(owner)
    assert refresh_calls == [], "A hidden result window must stay hidden during data refresh."

    owner.current_result_window = SimpleNamespace(isVisible=lambda: True)
    MainWindow._refresh_result_window_if_open(owner)
    assert refresh_calls == [False], "A visible result window should refresh without activation."

    refresh_calls[:] = []
    MainWindow.open_result_window(owner)
    assert refresh_calls == [True], "An explicit View action should activate the result window."


def _assert_run_directories_are_not_deleted_automatically():
    source = (ROOT / "gui" / "main_window.py").read_text(encoding="utf-8-sig")
    assert "self._cleanup_old_run_artifacts(" not in source, (
        "MainWindow must not silently delete complete analysis directories at startup or shutdown."
    )


def _assert_information_overview_tracks_selected_node():
    event = {
        "clade_key": "A|B",
        "display_node_id": "22",
        "parent_range": "AB",
        "child_ranges": ["A", "B"],
        "dispersal": 0,
        "vicariance": 1,
        "extinction": 0,
        "probability": 0.72,
        "dispersal_routes": {},
        "within_routes": {},
    }
    raw_text, totals = HeuristicEventSummaryService()._build_information_text(
        events=[event],
        area_names=["A", "B"],
        method_name="DEC",
        skipped=0,
    )
    assert "Event Route" not in raw_text
    assert "TOP-RANGE COMPARISON" in raw_text
    assert "PRODUCT OF SELECTED-STATE SUPPORTS" in raw_text

    result = SimpleNamespace(
        node_results={"A|B": object()},
        state_order=["A", "B", "AB"],
        state_colors={"A": "#cc0000", "B": "#0066cc", "AB": "#808080"},
        parse_warnings=[],
        tree_failure_reasons=[],
        heuristic_events=[event],
        heuristic_event_totals=totals,
        information_text=raw_text,
        time_summary_text="",
        heuristic_time_data=None,
    )
    payload = SimpleNamespace(
        display_node_id="22",
        clade_key="A|B",
        state_summary="AB 72.00%",
        support_summary="AB 72.00%",
        event_summary="Dispersal:0 Vicariance:1 Extinction:0",
        interpretation_note="多个状态表示等优重建，不表示概率。",
    )
    panel = NodeInfoPanel()
    panel.set_standard_result("DEC", result, [payload])
    assert panel.info_tabs.count() == 2
    assert panel.info_tabs.tabText(0) == "Overview"
    assert panel.info_tabs.tabText(1) == "Raw details"
    assert "No internal node selected" in panel.info_placeholder.toPlainText()

    panel.show_standard_node_info(
        {"name": "<内部节点>", "clade_signature": "A|B"},
        payload,
    )
    overview = panel.info_placeholder.toPlainText()
    assert "Node 22" in overview
    assert "Parent top range" in overview and "AB" in overview
    assert "Child top ranges" in overview
    assert "Product of selected-state supports" in overview and "72.00%" in overview
    assert "不表示概率" in overview
    assert "Event Route" not in overview
    assert panel.info_raw_text.toPlainText() == raw_text
    panel.close()


def _assert_main_file_dialog_policy():
    created = []
    original_configure = main_window_module.configure_resizable_window
    parent = QWidget()

    def capture_dialog(dialog):
        original_configure(dialog)
        created.append(dialog)
        return dialog

    with patch.object(main_window_module, "configure_resizable_window", side_effect=capture_dialog), patch.object(
        QFileDialog,
        "exec_",
        return_value=QDialog.Rejected,
    ):
        selected = MainWindow._choose_file(
            parent,
            "Select Tree File",
            "Tree Files (*.tree)",
        )

    assert selected == ""
    assert len(created) == 1
    dialog = created[0]
    assert dialog.testOption(QFileDialog.DontUseNativeDialog)
    assert dialog.acceptMode() == QFileDialog.AcceptOpen
    assert dialog.fileMode() == QFileDialog.ExistingFile
    assert dialog.minimumWidth() == 640
    assert dialog.minimumHeight() == 420
    assert dialog.width() == 860
    assert dialog.height() == 560
    _assert_resizable(dialog)
    dialog.close()
    parent.close()


def _assert_closed_tree_view_stays_closed(app):
    window = MainWindow()
    tree_path = ROOT / "data" / "benchmarks" / "psychotria" / "Psychotria.tree"
    matrix_path = ROOT / "data" / "benchmarks" / "psychotria" / "distribution.csv"

    window._load_tree_from_path(str(tree_path))
    window.open_result_window()
    app.processEvents()
    assert window.current_result_window is not None
    assert window.current_result_window.isVisible()
    assert window.current_result_window.parent() is None, (
        "The result window must be an independent top-level window."
    )

    window.current_result_window.close()
    app.processEvents()
    assert not window.current_result_window.isVisible()

    window._load_matrix_from_path(str(matrix_path))
    app.processEvents()
    assert not window.current_result_window.isVisible(), (
        "Loading a matrix reopened a result window that the user had closed."
    )

    window.show()
    window.open_result_window()
    app.processEvents()
    result_window = window.current_result_window
    window.showMinimized()
    app.processEvents()
    assert not result_window.isMinimized(), (
        "Minimizing the RASP5 main window also minimized the independent result window."
    )

    window.showNormal()
    window.close()
    app.processEvents()
    assert not result_window.isVisible(), (
        "Closing the RASP5 main window left its independent result window open."
    )


def _assert_literal_titles_are_english():
    problems = []
    for path in sorted((ROOT / "gui").rglob("*.py")):
        if "backend" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            values = []
            if isinstance(node, ast.Call):
                function_name = _call_name(node.func)
                if function_name == "setWindowTitle" and node.args:
                    values.append(node.args[0])
                elif function_name in {"warning", "critical", "information", "question"}:
                    owner = node.func.value if isinstance(node.func, ast.Attribute) else None
                    if isinstance(owner, ast.Name) and owner.id == "QMessageBox" and len(node.args) >= 2:
                        values.append(node.args[1])
                elif function_name in {
                    "getOpenFileName",
                    "getSaveFileName",
                    "getExistingDirectory",
                    "getOpenFileNames",
                }:
                    owner = node.func.value if isinstance(node.func, ast.Attribute) else None
                    if isinstance(owner, ast.Name) and owner.id == "QFileDialog" and len(node.args) >= 2:
                        values.append(node.args[1])
                elif function_name == "_choose_file" and node.args:
                    values.append(node.args[0])
                for keyword in node.keywords:
                    if keyword.arg == "error_title":
                        values.append(keyword.value)
            for value in values:
                if not isinstance(value, ast.Str):
                    continue
                if any(ord(character) > 127 for character in value.s):
                    problems.append(
                        "%s:%d %r" % (path.relative_to(ROOT), getattr(node, "lineno", 0), value.s)
                    )
    assert not problems, "Non-English literal window titles: %s" % ", ".join(problems)


def main():
    app = QApplication.instance() or QApplication([])

    generic = QDialog()
    generic.resize(500, 300)
    configure_resizable_window(generic)
    _assert_resizable(generic)
    generic.show()
    app.processEvents()
    generic.resize(700, 420)
    app.processEvents()
    assert generic.size().width() == 700
    assert generic.size().height() == 420
    generic.showMaximized()
    app.processEvents()
    assert generic.isMaximized()
    generic.showMinimized()
    app.processEvents()
    assert generic.isMinimized()
    generic.close()

    plan = SimpleNamespace(
        consensus_tree_candidates=[],
        tree_collection_candidates=[],
        matrix_candidates=[],
    )
    event_result = SimpleNamespace(
        events=[],
        raw_tables={},
        summary={},
        source_model_name="DEC",
        source_run_directory="",
    )
    with TemporaryDirectory(prefix="rasp_window_behavior_") as tmp:
        parameters_path = Path(tmp) / "parameters.txt"
        parameters_path.write_text(
            "n\tlnL\tgain\n0\t-10\t0.1\n100\t-9\t0.2\n",
            encoding="utf-8",
        )
        dialogs = [
            (BayAreaConfigDialog(["A", "B"]), "BayArea"),
            (BayAreaTracerDialog(parameters_path, 100, 100), "Tracer View"),
            (BayesTraitsConfigDialog(["Trait"], []), "BayesTraits"),
            (BBMConfigDialog(["A", "B"], []), "BBM"),
            (BSMEventTableDialog(event_result), "BioGeoBEARS BSM Event Table"),
            (BSMNetworkMapEditorDialog(event_result), "BSM Network Map Editor"),
            (BSMRunConfigDialog(), "Generate BioGeoBEARS BSM Events"),
            (DECConfigDialog(["A", "B"]), "DEC"),
            (PhytoolsConfigDialog(["Trait"]), "phytools"),
            (ProjectImportDialog(plan), "Quick Import Project"),
            (ContinuousFigureGroupDialog(), "Continuous Trait Figure Group"),
            (RegionGeoJsonBuilderDialog(spatial_service=SpatialDataService()), "Region GeoJSON Builder"),
            (SBGBConfigDialog(["A", "B"]), "BioGeoBEARS"),
            (SBGBConfigDialog(["A", "B"], title="S-BioGeoBEARS"), "S-BioGeoBEARS"),
            (
                SBGBConfigDialog(["A", "B"], title="Compare Models Using BioGeoBEARS"),
                "Compare Models Using BioGeoBEARS",
            ),
            (SDECConfigDialog(["A", "B"]), "S-DEC"),
            (SDivaConfigDialog(["A", "B"], show_fossils=False), "S-DIVA"),
            (SDivaConfigDialog(["A", "B"], show_fossils=False, title="DIVA"), "DIVA"),
            (SpatialDataManagerDialog(SpatialDataService()), "Spatial Data Manager"),
        ]
        for dialog, expected_title in dialogs:
            _assert_resizable(dialog)
            assert dialog.windowTitle() == expected_title, (
                "%s title was %r, expected %r"
                % (type(dialog).__name__, dialog.windowTitle(), expected_title)
            )
            if isinstance(dialog, SDivaConfigDialog):
                assert dialog.button_box.button(QDialogButtonBox.Ok).text() == "Run"
                assert dialog.button_box.button(QDialogButtonBox.Cancel).text() == "Close"
            dialog.close()

    result_window = ResultViewWindow()
    assert result_window.windowTitle() == "Result View"
    result_window.set_window_title_by_method("DEC")
    assert result_window.windowTitle() == "Result View - DEC"
    result_window._display_payload_only(
        {
            "name": "<内部节点>",
            "node_id": "N0024",
            "clade_signature": "A|B",
        }
    )
    assert "N0024" not in result_window.node_info_panel.selected_node_title.text()
    assert "N0024" not in result_window.statusBar().currentMessage()
    assert result_window.statusBar().currentMessage() == "当前节点: 已选择内部节点"
    standard_payload = SimpleNamespace(display_node_id="22", clade_key="A|B")
    result_window.current_result = object()
    result_window.result_adapter = object()
    with patch.object(
        result_window,
        "_build_standard_payload_from_tree_payload",
        return_value=standard_payload,
    ):
        result_window._display_payload_only(
            {
                "name": "<内部节点>",
                "node_id": "N0024",
                "clade_signature": "A|B",
            }
        )
    assert result_window.statusBar().currentMessage() == "当前节点: node 22"
    assert "N0024" not in result_window.node_info_panel.selected_node_title.text()
    result_window.close()

    _assert_all_dialog_classes_configured()
    _assert_ad_hoc_dialogs_configured()
    _assert_application_titles()
    _assert_result_window_refresh_policy()
    _assert_run_directories_are_not_deleted_automatically()
    _assert_information_overview_tracks_selected_node()
    _assert_main_file_dialog_policy()
    _assert_closed_tree_view_stays_closed(app)
    _assert_literal_titles_are_english()
    app.processEvents()
    print("Window behavior checks passed for %d representative dialogs." % len(dialogs))


if __name__ == "__main__":
    main()
