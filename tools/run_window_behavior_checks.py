import ast
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QDialog

from application.services.spatial_data_service import SpatialDataService
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
    assert main_source.count("configure_resizable_window(dialog)") == 2
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
            dialog.close()

    result_window = ResultViewWindow()
    assert result_window.windowTitle() == "Result View"
    result_window.set_window_title_by_method("DEC")
    assert result_window.windowTitle() == "Result View - DEC"
    result_window.close()

    _assert_all_dialog_classes_configured()
    _assert_ad_hoc_dialogs_configured()
    _assert_application_titles()
    _assert_literal_titles_are_english()
    app.processEvents()
    print("Window behavior checks passed for %d representative dialogs." % len(dialogs))


if __name__ == "__main__":
    main()
