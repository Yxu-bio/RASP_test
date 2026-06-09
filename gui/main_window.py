from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (
    QAction,
    QFileDialog,
    QDockWidget,
    QDialog,
    QGroupBox,
    QSplitter,
    QVBoxLayout,
    QMainWindow,
    QMessageBox,
    QTextEdit,
    QWidget,
)

from copy import deepcopy
from pathlib import Path


from application.services.diva_analysis_service import DivaAnalysisService
from application.services.sdiva_analysis_service import SDivaAnalysisService
from application.services.dec_analysis_service import DECAnalysisService
from application.services.sdec_analysis_service import SDECAnalysisService
from application.services.biogeobears_analysis_service import BioGeoBEARSAnalysisService
from application.services.sbgb_analysis_service import SBGBAnalysisService
from application.services.bayarea_analysis_service import BayAreaAnalysisService
from application.services.bbm_analysis_service import BBMAnalysisService
from application.services.bayestraits_analysis_service import BayesTraitsAnalysisService
from application.services.taxon_match_service import TaxonMatchService
from application.services.tree_collection_prepare_service import TreeCollectionPrepareService
from application.services.biogeobears_model_test_service import BioGeoBEARSModelTestService
from application.services.project_import_service import ProjectImportService
from application.services.result_schema_adapter import ResultSchemaAdapterFactory


from gui.workers.diva_run_worker import DivaRunWorker
from gui.workers.sdiva_run_worker import SDivaRunWorker
from gui.workers.dec_run_worker import DECRunWorker
from gui.workers.sdec_run_worker import SDECRunWorker
from gui.workers.biogeobears_run_worker import BioGeoBEARSRunWorker
from gui.workers.sbgb_run_worker import SBGBRunWorker
from gui.workers.bayarea_run_worker import BayAreaRunWorker
from gui.workers.bbm_run_worker import BBMRunWorker
from gui.workers.bayestraits_run_worker import BayesTraitsRunWorker
from gui.workers.biogeobears_model_test_worker import BioGeoBEARSModelTestWorker


from domain.models.sdiva_config import infer_sdiva_area_names
from domain.models.sbgb_config import SBGBConfig, SBGB_MODEL_DISPLAY
from domain.models.bayarea_config import BayAreaConfig
from domain.models.bbm_config import BBMConfig
from domain.models.bayestraits_config import BayesTraitsConfig
from gui.dialogs.sdiva_config_dialog import SDivaConfigDialog
from gui.dialogs.dec_config_dialog import DECConfigDialog
from gui.dialogs.sdec_config_dialog import SDECConfigDialog
from gui.dialogs.sbgb_config_dialog import SBGBConfigDialog
from gui.dialogs.bayarea_config_dialog import BayAreaConfigDialog
from gui.dialogs.bayarea_tracer_dialog import BayAreaTracerDialog
from gui.dialogs.bbm_config_dialog import BBMConfigDialog
from gui.dialogs.bayestraits_config_dialog import BayesTraitsConfigDialog
from gui.dialogs.project_import_dialog import ProjectImportDialog
from gui.dialogs.result_view_window import ResultViewWindow
from gui.widgets.matrix_preview_table import MatrixPreviewTable
from gui.widgets.progress_panel import ProgressPanel
from gui.widgets.tree_collection_info_panel import TreeCollectionInfoPanel
from domain.models.tree_collection_options import TreeCollectionOptions

from visualization.renderers.diva_result_renderer import DivaResultRenderer
from visualization.renderers.sdiva_result_renderer import SDivaResultRenderer
from visualization.renderers.dec_result_renderer import DECResultRenderer
from visualization.renderers.sdec_result_renderer import SDECResultRenderer
from visualization.renderers.biogeobears_result_renderer import BioGeoBEARSResultRenderer
from visualization.renderers.continuous_trait_result_renderer import ContinuousTraitResultRenderer
from infrastructure.tree.tree_reader import TreeReader
from infrastructure.io.csv_matrix_reader import CsvMatrixReader



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RASP-Pro")
        self.resize(1200, 800)
        self.setDockNestingEnabled(True)

        # ---------------- 基础服务 ----------------
        self.matrix_reader = CsvMatrixReader()
        self.tree_reader = TreeReader()
        self.taxon_match_service = TaxonMatchService()
        self.tree_collection_prepare_service = TreeCollectionPrepareService()
        self.project_import_service = ProjectImportService()

        self.diva_service = DivaAnalysisService()
        self.sdiva_service = SDivaAnalysisService()

        project_root = Path(__file__).resolve().parents[1]
        default_dec_engine = project_root / "engines" / "lagrange-ng" / "lagrange-ng.exe"
        default_dec_work_root = project_root / "runs" / "dec"
        self.dec_service = DECAnalysisService(
            engine_path=default_dec_engine,
            work_root=default_dec_work_root,
        )
        self.sdec_service = SDECAnalysisService(self.dec_service)

        default_bgb_work_root = project_root / "runs" / "biogeobears"
        default_bgb_wrapper = project_root / "engines" / "biogeobears" / "bgb_runner.R"
        default_bgb_rscript = project_root / "engines" / "R" / "bin" / "Rscript.exe"
        default_bgb_site_lib = project_root / "engines" / "R" / "site-library"

        self.biogeobears_service = BioGeoBEARSAnalysisService(
            rscript_path=default_bgb_rscript,
            wrapper_script_path=default_bgb_wrapper,
            work_root=default_bgb_work_root,
            site_library_path=default_bgb_site_lib,
        )
        self.sbgb_service = SBGBAnalysisService(self.biogeobears_service)

        self.biogeobears_model_test_service = BioGeoBEARSModelTestService(self.biogeobears_service)

        default_bayarea_engine = project_root / "engines" / "bayarea" / "bin" / "bayarea.exe"
        default_bayarea_work_root = project_root / "runs" / "bayarea"
        self.bayarea_service = BayAreaAnalysisService(
            executable_path=default_bayarea_engine,
            work_root=default_bayarea_work_root,
        )

        default_mrbayes_engine = project_root / "engines" / "mrbayes" / "mb.3.2.7-win32.exe"
        default_bbm_work_root = project_root / "runs" / "bbm"
        self.bbm_service = BBMAnalysisService(
            executable_path=default_mrbayes_engine,
            work_root=default_bbm_work_root,
        )

        default_bayestraits_engine = project_root / "engines" / "bayestraits" / "BayesTraitsV5.exe"
        default_bayestraits_work_root = project_root / "runs" / "bayestraits"
        self.bayestraits_service = BayesTraitsAnalysisService(
            executable_path=default_bayestraits_engine,
            work_root=default_bayestraits_work_root,
        )


        # ---------------- 当前单树、矩阵、结果、树集合状态 ----------------
        self.current_tree = None
        self.current_tree_path = ""
        self.current_matrix = None
        self.current_method_name = "DIVA"
        self.current_result_window = None
        self.current_tree_collection = None
        self.current_tree_collection_path = ""
        self.tree_collection_options = TreeCollectionOptions()
        self.current_prepared_tree_entries = []
        self.current_loaded_entries = []
        self.current_loaded_bifurcating_entries = []
        self.current_loaded_parse_error_count = 0

        self.biogeobears_worker = None
        self.diva_worker = None
        self.sdiva_worker = None
        self.dec_worker = None
        self.sdec_worker = None
        self.biogeobears_model_test_worker = None
        self.sbgb_worker = None
        self.bayarea_worker = None
        self.bbm_worker = None
        self.bayestraits_worker = None

        self.current_result = None
        self.current_diva_config = None
        self.current_sdiva_result = None
        self.current_sdiva_config = None
        self.current_dec_result = None
        self.current_dec_config = None
        self.current_sdec_result = None
        self.current_sdec_config = None
        self.current_sbgb_config = None
        self.current_biogeobears_config = None
        self.current_biogeobears_result = None
        self.current_biogeobears_model_test_config = None
        self.current_biogeobears_model_test_result = None
        self.current_bayarea_config = None
        self.current_bbm_config = None
        self.current_bayestraits_config = None
        self.current_selected_trait_column = ""


        # ---------------- 主工作台：矩阵 + 日志 + 状态 ----------------
        self.center_info = QTextEdit()
        self.center_info.setReadOnly(True)
        self.center_info.setPlainText(
            "Main workspace for file import, configuration, task execution, and result dispatch.\n"
            "Use View -> Open Result Window to inspect reconstructed trees."
        )

        self.matrix_preview = MatrixPreviewTable()
        self.matrix_preview.trait_column_selected.connect(self._on_matrix_trait_column_selected)
        self.run_log_box = QTextEdit()
        self.run_log_box.setReadOnly(True)
        self.run_log_box.setLineWrapMode(QTextEdit.NoWrap)
        self.run_log_box.setPlaceholderText("Run log will appear here.")

        self.match_info_box = QTextEdit()
        self.match_info_box.setReadOnly(True)
        self.match_info_box.setPlaceholderText("Taxon matching results will appear after importing a tree and a matrix.")

        # ---------------- 树集合信息面板 ----------------
        self.tree_collection_panel = TreeCollectionInfoPanel()
        self.tree_collection_panel.set_options(
            pre_burnin=self.tree_collection_options.pre_burnin,
            post_burnin=self.tree_collection_options.post_burnin,
            enable_sampling=self.tree_collection_options.enable_random_sampling,
            sample_size=self.tree_collection_options.random_sample_size,
        )
        self.tree_collection_panel.set_tree_summary(
            raw_tree_count=0,
            parse_error_count=0,
            bifurcating_count=0,
            loaded_count=0,
            analysis_count=0,
        )
        self.tree_collection_panel.set_consensus_tree_summary("未导入")

        self.workspace_splitter = QSplitter(Qt.Horizontal, self)
        self.left_workspace_splitter = QSplitter(Qt.Vertical, self.workspace_splitter)
        self.right_workspace_splitter = QSplitter(Qt.Vertical, self.workspace_splitter)

        self.left_workspace_splitter.addWidget(self._wrap_workspace_panel("Matrix", self.matrix_preview))
        self.left_workspace_splitter.addWidget(self._wrap_workspace_panel("Run Log", self.run_log_box))
        self.left_workspace_splitter.setStretchFactor(0, 3)
        self.left_workspace_splitter.setStretchFactor(1, 2)

        self.right_workspace_splitter.addWidget(self._wrap_workspace_panel("Tree / Tree Set", self.tree_collection_panel))
        self.right_workspace_splitter.addWidget(self._wrap_workspace_panel("Taxon Matching", self.match_info_box))
        self.right_workspace_splitter.addWidget(self._wrap_workspace_panel("Current Summary", self.center_info))
        self.right_workspace_splitter.setStretchFactor(0, 3)
        self.right_workspace_splitter.setStretchFactor(1, 2)
        self.right_workspace_splitter.setStretchFactor(2, 2)

        self.workspace_splitter.addWidget(self.left_workspace_splitter)
        self.workspace_splitter.addWidget(self.right_workspace_splitter)
        self.workspace_splitter.setStretchFactor(0, 4)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.workspace_splitter.setCollapsible(0, False)
        self.workspace_splitter.setCollapsible(1, False)
        self.left_workspace_splitter.setMinimumWidth(700)
        self.right_workspace_splitter.setMinimumWidth(220)
        self.workspace_splitter.setSizes([960, 240])
        self.setCentralWidget(self.workspace_splitter)

        # ---------------- 任务进度 ----------------
        self.progress_panel = ProgressPanel()
        self.progress_dock = QDockWidget("任务进度", self)
        self.progress_dock.setWidget(self.progress_panel)
        self.progress_dock.setAllowedAreas(
            Qt.BottomDockWidgetArea |
            Qt.LeftDockWidgetArea |
            Qt.RightDockWidgetArea
        )
        self.addDockWidget(Qt.BottomDockWidgetArea, self.progress_dock)
        self.progress_panel.set_idle("空闲")

        # ---------------- 信号绑定 ----------------
        self.tree_collection_panel.pre_burnin_changed.connect(self._on_pre_burnin_changed)
        self.tree_collection_panel.post_burnin_changed.connect(self._on_post_burnin_changed)
        self.tree_collection_panel.enable_random_sampling_changed.connect(self._on_enable_random_sampling_changed)
        self.tree_collection_panel.random_sample_size_changed.connect(self._on_random_sample_size_changed)

        # ---------------- 菜单构建 ----------------
        self._build_menu()

        # ---------------- 初始界面刷新 ----------------
        self._refresh_consensus_tree_summary()
        self._recompute_tree_collection_state()
        self.append_run_log("RASP-Pro workspace initialized.")

    def _wrap_workspace_panel(self, title, widget):
        group = QGroupBox(str(title or ""), self)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(widget)
        return group

    def _preserve_workspace_split(self):
        if not hasattr(self, "workspace_splitter") or self.workspace_splitter is None:
            return

        sizes = list(self.workspace_splitter.sizes())
        if len(sizes) < 2:
            return

        total = sum(max(0, int(size)) for size in sizes[:2])
        if total <= 0:
            total = max(1, int(self.workspace_splitter.width() or 0))

        minimum_left = int(total * 0.65)
        if int(sizes[0]) >= minimum_left:
            return

        preferred_left = int(total * 0.80)
        minimum_right = 220
        right = max(minimum_right, total - preferred_left)
        left = max(minimum_left, total - right)
        self.workspace_splitter.setSizes([left, right])

    def _build_menu(self):
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background: #f3f4f6;
                border-bottom: 1px solid #c7cdd4;
                spacing: 2px;
            }
            QMenuBar::item {
                padding: 5px 14px;
                border-right: 1px solid #c7cdd4;
                background: transparent;
            }
            QMenuBar::item:selected {
                background: #e5e9ef;
            }
            QMenu {
                border: 1px solid #b8c0ca;
                background: #ffffff;
            }
            QMenu::item {
                padding: 5px 28px 5px 22px;
            }
            QMenu::item:selected {
                background: #dce8f7;
            }
            QMenu::separator {
                height: 1px;
                background: #c7cdd4;
                margin: 5px 8px;
            }
        """)

        file_menu = menubar.addMenu("File")
        reconstruction_menu = menubar.addMenu("Ancestral Range Reconstruction")
        consensus_tree_menu = reconstruction_menu.addMenu("On Consensus Tree")
        trees_menu = reconstruction_menu.addMenu("On Trees")
        model_test_menu = reconstruction_menu.addMenu("Model Test")
        trait_menu = menubar.addMenu("Trait Reconstruction")
        view_menu = menubar.addMenu("View")

        self.open_tree_action = QAction("Open Tree File", self)
        self.open_tree_action.triggered.connect(self.open_tree_file)
        file_menu.addAction(self.open_tree_action)
        file_menu.addSeparator()

        self.open_tree_collection_action = QAction("Import Tree Set", self)
        self.open_tree_collection_action.triggered.connect(self.open_tree_collection_file)
        file_menu.addAction(self.open_tree_collection_action)
        file_menu.addSeparator()

        self.open_matrix_action = QAction("Open Matrix File", self)
        self.open_matrix_action.triggered.connect(self.open_matrix_file)
        file_menu.addAction(self.open_matrix_action)
        file_menu.addSeparator()

        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self.close)
        file_menu.addAction(self.exit_action)

        file_menu.addSeparator()
        self.open_project_action = QAction("Quick Import Project...", self)
        self.open_project_action.triggered.connect(self.open_project_folder)
        file_menu.addAction(self.open_project_action)

        self.run_diva_action = QAction("DIVA", self)
        self.run_diva_action.triggered.connect(self.run_diva)
        consensus_tree_menu.addAction(self.run_diva_action)

        self.run_sdiva_action = QAction("S-DIVA", self)
        self.run_sdiva_action.triggered.connect(self.run_sdiva)
        trees_menu.addAction(self.run_sdiva_action)

        self.run_dec_action = QAction("DEC", self)
        self.run_dec_action.triggered.connect(self.run_dec)
        consensus_tree_menu.addAction(self.run_dec_action)

        self.run_sdec_action = QAction("S-DEC", self)
        self.run_sdec_action.triggered.connect(self.run_sdec)
        trees_menu.addAction(self.run_sdec_action)

        self.run_bayarea_action = QAction("BayArea", self)
        self.run_bayarea_action.triggered.connect(self.run_bayarea)
        consensus_tree_menu.addAction(self.run_bayarea_action)

        self.run_bbm_action = QAction("BBM", self)
        self.run_bbm_action.triggered.connect(self.run_bbm)
        consensus_tree_menu.addAction(self.run_bbm_action)

        self.run_bayestraits_action = QAction("BayesTraits", self)
        self.run_bayestraits_action.triggered.connect(self.run_bayestraits)
        trait_menu.addAction(self.run_bayestraits_action)

        self.run_sbgb_action = QAction("S-BioGeoBEARS", self)
        self.run_sbgb_action.triggered.connect(self.run_sbgb)
        trees_menu.addAction(self.run_sbgb_action)

        self.run_bgb_action = QAction("BioGeoBEARS", self)
        self.run_bgb_action.triggered.connect(lambda: self.run_biogeobears())
        consensus_tree_menu.addAction(self.run_bgb_action)

        self.run_bgb_model_test_action = QAction("Compare Models Using BioGeoBEARS", self)
        self.run_bgb_model_test_action.triggered.connect(self.run_biogeobears_model_test)
        model_test_menu.addAction(self.run_bgb_model_test_action)

        self.open_result_action = QAction("Open Result Window", self)
        self.open_result_action.triggered.connect(self.open_result_window)
        view_menu.addAction(self.open_result_action)

    def _choose_file(self, title, file_filter):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            "",
            file_filter,
        )
        return file_path or ""

    def append_run_log(self, text=""):
        if not hasattr(self, "run_log_box") or self.run_log_box is None:
            return
        value = str(text or "")
        self.run_log_box.moveCursor(QTextCursor.End)
        self.run_log_box.insertPlainText(value + "\n")
        self.run_log_box.moveCursor(QTextCursor.End)

    def append_run_section(self, title):
        label = str(title or "").strip()
        if not label:
            return
        self.append_run_log("")
        self.append_run_log("*******************************************")
        self.append_run_log("*%s*" % label)
        self.append_run_log("*******************************************")

    def _current_timestamp(self):
        from datetime import datetime
        return datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    def _run_ui_task(
        self,
        *,
        progress_text,
        done_text,
        error_progress_text,
        error_title,
        task,
    ):
        try:
            self.append_run_log(progress_text + " ...")
            self.progress_panel.set_progress(10, progress_text)
            task()
            self.append_run_log(done_text)
            self.progress_panel.set_done(done_text)
        except Exception as exc:
            self.append_run_log(error_progress_text + ": " + str(exc))
            self.progress_panel.set_error(error_progress_text)
            QMessageBox.critical(self, error_title, str(exc))

    def _set_center_info(self, text):
        self.center_info.setPlainText(text or "")

    def _set_status_message(self, text):
        self.statusBar().showMessage(text or "")

    def _clear_analysis_results(
            self,
            clear_diva=True,
            clear_sdiva=True,
            clear_dec=True,
            clear_sdec=True,
            clear_biogeobears=True,
    ):
        if clear_diva:
            self.current_result = None

        if clear_sdiva:
            self.current_sdiva_result = None

        if clear_dec:
            self.current_dec_result = None

        if clear_sdec:
            self.current_sdec_result = None

        if clear_biogeobears:
            self.current_biogeobears_result = None

        if self.current_method_name == "S-DIVA" and self.current_sdiva_result is None:
            self.current_method_name = "DIVA"

        if self.current_method_name == "DEC" and self.current_dec_result is None:
            self.current_method_name = "DIVA"

        if self.current_method_name == "S-DEC" and self.current_sdec_result is None:
            self.current_method_name = "DIVA"

        if self._is_biogeobears_method(self.current_method_name) and self.current_biogeobears_result is None:
            self.current_method_name = "DIVA"

    def _is_biogeobears_method(self, method_name):
        text = str(method_name or "")
        return (
            text.startswith("BioGeoBEARS")
            or text.startswith("S-BioGeoBEARS")
            or text.startswith("BayArea")
            or text.startswith("BBM")
            or text.startswith("BayesTraits")
        )

    def _get_active_result_context(self):
        if (
            self.current_biogeobears_result is not None
            and type(self.current_biogeobears_result).__name__ == "ContinuousTraitResult"
        ):
            return {
                "method_name": str(getattr(self.current_biogeobears_result, "model_name", "") or "BayesTraits Continuous ASR"),
                "result": self.current_biogeobears_result,
                "renderer_cls": ContinuousTraitResultRenderer,
            }

        if self._is_biogeobears_method(self.current_method_name) and self.current_biogeobears_result is not None:
            return {
                "method_name": str(self.current_method_name),
                "result": self.current_biogeobears_result,
                "renderer_cls": BioGeoBEARSResultRenderer,
            }

        if self.current_method_name == "S-DEC" and self.current_sdec_result is not None:
            return {
                "method_name": "S-DEC",
                "result": self.current_sdec_result,
                "renderer_cls": SDECResultRenderer,
            }

        if self.current_method_name == "DEC" and self.current_dec_result is not None:
            return {
                "method_name": "DEC",
                "result": self.current_dec_result,
                "renderer_cls": DECResultRenderer,
            }

        if self.current_method_name == "S-DIVA" and self.current_sdiva_result is not None:
            return {
                "method_name": "S-DIVA",
                "result": self.current_sdiva_result,
                "renderer_cls": SDivaResultRenderer,
            }

        if self.current_method_name == "DIVA" and self.current_result is not None:
            return {
                "method_name": "DIVA",
                "result": self.current_result,
                "renderer_cls": DivaResultRenderer,
            }

        if self.current_biogeobears_result is not None and self.current_result is None and self.current_sdiva_result is None and self.current_dec_result is None and self.current_sdec_result is None:
            return {
                "method_name": str(getattr(self.current_biogeobears_result, "model_name", "") or "BioGeoBEARS"),
                "result": self.current_biogeobears_result,
                "renderer_cls": BioGeoBEARSResultRenderer,
            }

        if self.current_sdec_result is not None and self.current_result is None and self.current_sdiva_result is None and self.current_dec_result is None:
            return {
                "method_name": "S-DEC",
                "result": self.current_sdec_result,
                "renderer_cls": SDECResultRenderer,
            }

        if self.current_dec_result is not None and self.current_result is None and self.current_sdiva_result is None:
            return {
                "method_name": "DEC",
                "result": self.current_dec_result,
                "renderer_cls": DECResultRenderer,
            }

        if self.current_sdiva_result is not None and self.current_result is None:
            return {
                "method_name": "S-DIVA",
                "result": self.current_sdiva_result,
                "renderer_cls": SDivaResultRenderer,
            }

        return {
            "method_name": "DIVA",
            "result": self.current_result,
            "renderer_cls": DivaResultRenderer,
        }

    def _build_active_renderer(self, leaf_state_map, state_colors):
        ctx = self._get_active_result_context()

        renderer = ctx["renderer_cls"]()
        renderer.set_tree(self.current_tree)
        renderer.apply_leaf_states(leaf_state_map, state_colors)

        if ctx["result"] is not None:
            renderer.set_result(ctx["result"])

        return ctx, renderer

    def _refresh_result_window_if_open(self):
        if self.current_result_window is not None:
            self.open_result_window()

    def _build_leaf_state_payload_from_matrix(self):
        if self.current_matrix is None:
            return {}, {}

        if self._is_biogeobears_method(self.current_method_name) and str(self.current_method_name).startswith("BayesTraits"):
            config = getattr(self, "current_bayestraits_config", None)
            if str(getattr(config, "model", "MULTISTATE") or "MULTISTATE") != "MULTISTATE":
                return {}, {}
            trait_column = str(getattr(config, "trait_column", "") or "").strip()
            if trait_column:
                leaf_state_map = {}
                states = []
                for row in self.current_matrix.rows:
                    taxon_name = str(row.get("Name", "")).strip()
                    if not taxon_name:
                        continue
                    state = str(row.get(trait_column, "") or "").strip()
                    if not state:
                        continue
                    leaf_state_map[taxon_name] = state
                    if state not in states:
                        states.append(state)
                states.sort(key=lambda x: (len(x), x))
                preferred_colors = {}
                if self.current_biogeobears_result is not None and getattr(self.current_biogeobears_result, "state_colors", None):
                    preferred_colors = dict(self.current_biogeobears_result.state_colors)
                palette = [
                    "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
                    "#ffff33", "#a65628", "#f781bf", "#999999", "#66c2a5",
                    "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854", "#ffd92f",
                    "#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e",
                ]
                state_colors = {
                    state: preferred_colors.get(state, palette[i % len(palette)])
                    for i, state in enumerate(states)
                }
                return leaf_state_map, state_colors

        leaf_state_map = {}
        states = []

        for row in self.current_matrix.rows:
            taxon_name = str(row.get("Name", "")).strip()
            if not taxon_name:
                continue

            state_parts = []
            for col in self.current_matrix.state_columns:
                if col in ("ID", "Name"):
                    continue
                val = str(row.get(col, "")).strip()
                if val:
                    state_parts.append(val)

            state = "".join(state_parts).strip()
            if state:
                leaf_state_map[taxon_name] = state
                if state not in states:
                    states.append(state)

        states.sort(key=lambda x: (len(x), x))
        palette = [
            "#e41a1c",
            "#377eb8",
            "#4daf4a",
            "#984ea3",
            "#ff7f00",
            "#ffff33",
            "#a65628",
            "#f781bf",
            "#999999",
            "#66c2a5",
            "#fc8d62",
            "#8da0cb",
            "#e78ac3",
            "#a6d854",
            "#ffd92f",
            "#1b9e77",
            "#d95f02",
            "#7570b3",
            "#e7298a",
            "#66a61e",
        ]
        state_colors = {
            state: palette[i % len(palette)]
            for i, state in enumerate(states)
        }

        preferred_result = None
        if self._is_biogeobears_method(self.current_method_name) and self.current_biogeobears_result is not None:
            preferred_result = self.current_biogeobears_result
        elif self.current_method_name == "S-DEC" and self.current_sdec_result is not None:
            preferred_result = self.current_sdec_result
        elif self.current_method_name == "DEC" and self.current_dec_result is not None:
            preferred_result = self.current_dec_result
        elif self.current_method_name == "S-DIVA" and self.current_sdiva_result is not None:
            preferred_result = self.current_sdiva_result
        elif self.current_result is not None:
            preferred_result = self.current_result

        if preferred_result is not None and getattr(preferred_result, "state_colors", None):
            preferred_colors = dict(preferred_result.state_colors)
            for state in list(state_colors.keys()):
                if state in preferred_colors:
                    state_colors[state] = preferred_colors[state]

        return leaf_state_map, state_colors

    def open_result_window(self):
        if self.current_result_window is None:
            self.current_result_window = ResultViewWindow(self)

        if self.current_tree is None:
            QMessageBox.warning(self, "无法打开结果窗口", "请先导入共识树。")
            return

        leaf_state_map, state_colors = self._build_leaf_state_payload_from_matrix()
        ctx, renderer = self._build_active_renderer(leaf_state_map, state_colors)

        self.current_result_window.set_renderer(renderer)
        self.current_result_window.set_leaf_state_context(leaf_state_map)
        self.current_result_window.set_window_title_by_method(ctx["method_name"])
        self.current_result_window.set_result(ctx["result"])
        self.current_result_window.refresh_view()

        self.current_result_window.show()
        self.current_result_window.raise_()
        self.current_result_window.activateWindow()

    def _build_tree_loaded_summary_text(self, file_path, leaf_count):
        return (
            f"已加载树文件：{file_path}\n"
            f"叶节点数：{leaf_count}\n"
            "可通过“视图 -> 打开结果窗口”查看树。"
        )

    def _build_tree_collection_summary_text(
        self,
        raw_count,
        loaded_count,
        parse_error_count,
        bifurcating_count,
        analysis_count,
    ):
        sampling_text = "启用" if self.tree_collection_options.enable_random_sampling else "关闭"

        return (
            f"当前树集合文件:\n{self.current_tree_collection_path or '未导入'}\n\n"
            f"原始树总数: {raw_count}\n"
            f"载入前舍弃: {self.tree_collection_options.pre_burnin}（修改后需重新导入树集合才生效）\n"
            f"当前已载入树数: {loaded_count}\n"
            f"解析失败数: {parse_error_count}\n"
            f"导入的二歧树数量: {bifurcating_count}\n"
            f"载入后舍弃: {self.tree_collection_options.post_burnin}\n"
            f"随机树抽样: {sampling_text}\n"
            f"随机树数量: {self.tree_collection_options.random_sample_size}\n"
            f"当前分析树数: {analysis_count}\n\n"
            f"当前共识树:\n{self._get_consensus_tree_summary_text()}"
        )

    def _build_tree_collection_import_status_text(self, file_path, raw_count, bifurcating_count):
        return (
            f"已导入树集合: {file_path} | 原始树数={raw_count} | "
            f"已导入二歧树数={bifurcating_count}"
        )

    def _build_diva_summary_text(self, result):
        node_count = len(getattr(result, "node_results", {}) or {})
        warning_count = len(getattr(result, "parse_warnings", []) or [])

        return (
            f"DIVA 运行完成\n\n"
            f"解析节点数: {node_count}\n"
            f"警告数: {warning_count}\n\n"
            f"当前共识树:\n{self._get_consensus_tree_summary_text()}"
        )

    def _build_sdiva_summary_text(self, result):
        warning_count = len(getattr(result, "parse_warnings", []) or [])
        node_count = len(getattr(result, "node_results", {}) or {})
        tree_count = getattr(result, "tree_count_total", 0)
        config_path = str(getattr(result, "config_path", "") or "").strip()

        lines = [
            "S-DIVA 运行完成",
            "",
            f"参与分析树数: {tree_count}",
            f"聚合节点数: {node_count}",
            f"警告数: {warning_count}",
        ]
        if config_path:
            lines.append(f"配置文件: {config_path}")
        lines.extend([
            "",
            "当前共识树:",
            self._get_consensus_tree_summary_text(),
        ])

        return "\n".join(lines)

    def _build_dec_summary_text(self, result):
        node_count = len(getattr(result, "node_results", {}) or {})
        warning_count = len(getattr(result, "parse_warnings", []) or [])
        model_name = str(getattr(result, "model_name", "DEC") or "DEC")

        return (
            f"{model_name} 运行完成\n\n"
            f"解析节点数: {node_count}\n"
            f"警告数: {warning_count}\n\n"
            f"当前共识树:\n{self._get_consensus_tree_summary_text()}"
        )

    def _build_sdec_summary_text(self, result):
        node_count = len(getattr(result, "node_results", {}) or {})
        warning_count = len(getattr(result, "parse_warnings", []) or [])
        input_tree_count = int(getattr(result, "input_tree_count", 0) or 0)
        effective_tree_count = int(getattr(result, "effective_tree_count", 0) or 0)

        return (
            "S-DEC 运行完成\n\n"
            f"输入树数: {input_tree_count}\n"
            f"有效树数: {effective_tree_count}\n"
            f"解析节点数: {node_count}\n"
            f"警告数: {warning_count}\n\n"
            f"当前共识树:\n{self._get_consensus_tree_summary_text()}"
        )

    def _build_biogeobears_summary_text(self, result):
        node_count = len(getattr(result, "node_results", {}) or {})
        warning_count = len(getattr(result, "parse_warnings", []) or [])
        method_name = str(getattr(result, "model_name", "") or "BioGeoBEARS")
        input_tree_count = int(getattr(result, "input_tree_count", 1) or 1)
        effective_tree_count = int(getattr(result, "effective_tree_count", 1) or 1)
        tree_lines = ""
        if input_tree_count > 1 or method_name.startswith("S-BioGeoBEARS"):
            tree_lines = (
                f"输入树数: {input_tree_count}\n"
                f"有效树数: {effective_tree_count}\n"
            )
        stats_lines = self._build_model_statistic_summary_lines(result, limit=8)
        if stats_lines:
            tree_lines += "\nStatistics:\n" + "\n".join(stats_lines) + "\n"

        return (
            f"{method_name} 运行完成\n\n"
            f"{tree_lines}"
            f"解析节点数: {node_count}\n"
            f"警告数: {warning_count}\n\n"
            f"当前共识树:\n{self._get_consensus_tree_summary_text()}"
        )

    def _build_model_statistic_summary_lines(self, result, limit=8):
        stats = dict(getattr(result, "model_statistics", {}) or {})
        summaries = stats.get("numeric_summaries", {})
        if not summaries:
            return []
        skip = {"Tree No", "Iteration"}
        lines = []
        for name, summary in summaries.items():
            if str(name) in skip:
                continue
            try:
                mean = self._fmt_float(summary.get("mean"))
                min_value = self._fmt_float(summary.get("min"))
                max_value = self._fmt_float(summary.get("max"))
                n = str(summary.get("n", ""))
            except Exception:
                continue
            lines.append("%s: mean=%s, min=%s, max=%s, n=%s" % (name, mean, min_value, max_value, n))
            if len(lines) >= int(limit):
                break
        return lines

    def _build_biogeobears_model_test_summary_text(self, result):
        best_row = self._get_bgb_model_test_best_row(result)
        criterion = str(getattr(result, "criterion_used", "") or "AICc")
        model_count = len(getattr(result, "rows", []) or [])
        model_count = len(getattr(result, "rows", []) or [])
        model_count = len(getattr(result, "rows", []) or [])

        lines = []
        lines.append("BioGeoBEARS 模型检测完成")
        lines.append("")
        lines.append(f"有效模型数: {result.effective_model_count}")
        lines.append(f"失败模型数: {result.failed_model_count}")
        lines.append(f"比较准则: {criterion}")

        if best_row is not None:
            delta_value = self._get_bgb_model_test_delta(best_row, criterion)
            lines.append(f"推荐模型: {best_row.display_name}")
            lines.append(f"模型权重: {self._fmt_float(best_row.weight)}")
            lines.append(f"Δ{criterion}: {self._fmt_float(delta_value)}")
            lines.append("")
            lines.append(
                f"判读: 该模型是在当前 {model_count} 个候选模型中，"
                "综合拟合效果和模型复杂度后获得最高支持的模型。"
            )
        else:
            lines.append("推荐模型: 无")
            lines.append("")
            lines.append("判读: 未能确定推荐模型。请检查运行诊断信息。")

        lines.append("")
        lines.append("简要说明:")
        lines.append("AICc 越小越好；ΔAICc 越接近 0，模型越接近最佳模型；")
        lines.append("模型权重表示当前候选模型集合中的相对支持度。")

        return "\n".join(lines)

    def _fmt_float(self, value, digits=4):
        if value is None:
            return ""
        try:
            return f"{float(value):.{digits}f}"
        except Exception:
            return str(value)



    def _build_diva_status_text(self, result):
        node_count = len(getattr(result, "node_results", {}) or {})
        warning_count = len(getattr(result, "parse_warnings", []) or [])
        return f"DIVA 完成：节点数={node_count}，警告数={warning_count}"

    def _build_sdiva_status_text(self, result):
        warning_count = len(getattr(result, "parse_warnings", []) or [])
        node_count = len(getattr(result, "node_results", {}) or {})
        tree_count = getattr(result, "tree_count_total", 0)
        return f"S-DIVA 完成：树数={tree_count}，节点数={node_count}，警告数={warning_count}"

    def _build_dec_status_text(self, result):
        node_count = len(getattr(result, "node_results", {}) or {})
        warning_count = len(getattr(result, "parse_warnings", []) or [])
        model_name = str(getattr(result, "model_name", "DEC") or "DEC")
        return f"{model_name} 完成：节点数={node_count}，警告数={warning_count}"

    def _build_sdec_status_text(self, result):
        input_tree_count = int(getattr(result, "input_tree_count", 0) or 0)
        effective_tree_count = int(getattr(result, "effective_tree_count", 0) or 0)
        node_count = len(getattr(result, "node_results", {}) or {})
        return f"S-DEC 完成：有效树={effective_tree_count}/{input_tree_count}，节点数={node_count}"

    def _build_biogeobears_status_text(self, result):
        method_name = str(getattr(result, "model_name", "") or "BioGeoBEARS")
        node_count = len(getattr(result, "node_results", {}) or {})
        input_tree_count = int(getattr(result, "input_tree_count", 1) or 1)
        effective_tree_count = int(getattr(result, "effective_tree_count", 1) or 1)
        if input_tree_count > 1 or method_name.startswith("S-BioGeoBEARS"):
            return f"{method_name} 完成：有效树={effective_tree_count}/{input_tree_count}，节点数={node_count}"
        return f"{method_name} 完成：节点数={node_count}"

    def _update_analysis_feedback(self, method_name, result):
        if self._is_biogeobears_method(method_name):
            self._set_center_info(self._build_biogeobears_summary_text(result))
            self._set_status_message(self._build_biogeobears_status_text(result))
        elif method_name == "S-DEC":
            self._set_center_info(self._build_sdec_summary_text(result))
            self._set_status_message(self._build_sdec_status_text(result))
        elif method_name == "DEC":
            self._set_center_info(self._build_dec_summary_text(result))
            self._set_status_message(self._build_dec_status_text(result))
        elif method_name == "S-DIVA":
            self._set_center_info(self._build_sdiva_summary_text(result))
            self._set_status_message(self._build_sdiva_status_text(result))
        else:
            self._set_center_info(self._build_diva_summary_text(result))
            self._set_status_message(self._build_diva_status_text(result))

    def _get_consensus_tree_summary_text(self):
        if self.current_tree is None:
            return "未导入"

        try:
            leaf_count = len(self.current_tree.get_leaf_names())
        except Exception:
            leaf_count = 0

        tree_name = self.current_tree_path if self.current_tree_path else "已导入"
        return f"{tree_name} | 叶节点数={leaf_count}"

    def _refresh_consensus_tree_summary(self):
        self.tree_collection_panel.set_consensus_tree_summary(
            self._get_consensus_tree_summary_text()
        )

    def _update_taxon_match(self):
        if not self.current_tree or not self.current_matrix:
            self.match_info_box.setPlainText("请先同时导入树和矩阵。")
            return

        tree_taxa = self.current_tree.get_leaf_names()
        matrix_taxa = self.current_matrix.taxa_names if self.current_matrix else []
        result = self.taxon_match_service.match(tree_taxa, matrix_taxa)

        text = (
            f"匹配成功: {result['matched_count']}\n"
            f"仅树中存在: {result['only_in_tree_count']}\n"
            f"仅矩阵中存在: {result['only_in_matrix_count']}\n\n"
            f"仅树中存在:\n"
            + ("\n".join(result["only_in_tree"]) if result["only_in_tree"] else "无")
            + "\n\n仅矩阵中存在:\n"
            + ("\n".join(result["only_in_matrix"]) if result["only_in_matrix"] else "无")
        )
        self.match_info_box.setPlainText(text)

    def _load_tree_from_path(self, file_path):
        newick_text = self.tree_reader.read_tree(file_path)

        from infrastructure.tree.ete_renderer import EteTreeRenderer
        renderer = EteTreeRenderer()
        renderer.load_tree(newick_text)

        self.current_tree = renderer.get_tree()
        self.current_tree_path = file_path
        self.current_dec_config = None
        self.current_bayestraits_config = None
        self._clear_analysis_results(clear_diva=True, clear_sdiva=True)

        leaf_count = len(renderer.get_leaf_names())
        self.append_run_log("Load tree successfully: %s" % file_path)
        self.append_run_log("Using Tree: %s" % newick_text.strip())
        self._set_center_info(self._build_tree_loaded_summary_text(file_path, leaf_count))

        if self.current_matrix is not None:
            self._update_taxon_match()

        self._refresh_consensus_tree_summary()
        self._refresh_result_window_if_open()
        QTimer.singleShot(0, self._preserve_workspace_split)

    def _load_matrix_from_path(self, file_path):
        matrix = self.matrix_reader.read(file_path)
        self.current_matrix = matrix
        state_columns = [
            str(col).strip()
            for col in list(getattr(matrix, "state_columns", []) or [])
            if str(col).strip()
        ]
        self.current_selected_trait_column = state_columns[0] if state_columns else ""
        self.current_sdiva_config = None
        self.current_dec_config = None
        self.current_bayestraits_config = None
        self._clear_analysis_results(clear_diva=True, clear_sdiva=True)

        self.matrix_preview.load_matrix(matrix, selected_trait_column=self.current_selected_trait_column)
        self.append_run_log("Load States Successfully: %s" % file_path)
        self._update_taxon_match()
        self._refresh_result_window_if_open()
        QTimer.singleShot(0, self._preserve_workspace_split)

    def _on_matrix_trait_column_selected(self, column_name):
        column = str(column_name or "").strip()
        if not column:
            return
        if self.current_matrix is None:
            return
        state_columns = [
            str(col).strip()
            for col in list(getattr(self.current_matrix, "state_columns", []) or [])
            if str(col).strip()
        ]
        if column not in state_columns:
            return
        self.current_selected_trait_column = column
        if self.current_bayestraits_config is not None and column in list(getattr(self.current_bayestraits_config, "trait_columns", []) or []):
            self.current_bayestraits_config.trait_column = column
        self.append_run_log("Selected trait column: %s" % column)

    def _load_tree_collection_from_path(self, file_path):
        self.append_run_log("Loading Trees Dataset ...")
        collection = self.tree_reader.read_tree_collection(file_path)

        self.current_tree_collection = collection
        self.current_tree_collection_path = file_path
        self._clear_analysis_results(clear_diva=False, clear_sdiva=True)

        self._load_tree_collection_into_memory(collection)
        self._recompute_tree_collection_state()

        self._set_status_message(
            self._build_tree_collection_import_status_text(
                file_path=file_path,
                raw_count=collection.raw_tree_count,
                bifurcating_count=len(self.current_loaded_bifurcating_entries),
            )
        )
        self.append_run_log("Load %s Successfully!" % file_path)
        QTimer.singleShot(0, self._preserve_workspace_split)

    def _select_project_import_paths(self, plan):
        if plan.is_unambiguous():
            return (
                plan.selected_consensus_tree,
                plan.selected_tree_collection,
                plan.selected_matrix,
            )

        dialog = ProjectImportDialog(plan, self)
        if dialog.exec_() != QDialog.Accepted:
            return None
        return (
            dialog.selected_consensus_tree(),
            dialog.selected_tree_collection(),
            dialog.selected_matrix(),
        )

    def _validate_project_import_paths(self, consensus_tree_path, tree_collection_path, matrix_path):
        if consensus_tree_path:
            self.tree_reader.read_tree(consensus_tree_path)
        if tree_collection_path:
            self.tree_reader.read_tree_collection(tree_collection_path)
        if matrix_path:
            self.matrix_reader.read(matrix_path)

    def _load_project_from_paths(self, consensus_tree_path, tree_collection_path, matrix_path):
        if not consensus_tree_path and not tree_collection_path and not matrix_path:
            raise ValueError("未选择任何可导入文件。")

        self._validate_project_import_paths(
            consensus_tree_path=consensus_tree_path,
            tree_collection_path=tree_collection_path,
            matrix_path=matrix_path,
        )

        imported = []
        if consensus_tree_path:
            self._load_tree_from_path(consensus_tree_path)
            imported.append("共识树: %s" % consensus_tree_path)
        if tree_collection_path:
            self._load_tree_collection_from_path(tree_collection_path)
            imported.append("树集合: %s" % tree_collection_path)
        if matrix_path:
            self._load_matrix_from_path(matrix_path)
            imported.append("分布矩阵: %s" % matrix_path)

        self._set_center_info("一键导入完成\n\n" + "\n".join(imported))
        self._set_status_message("一键导入完成")

    def open_project_folder(self):
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "选择项目文件夹",
            "",
        )
        if not folder_path:
            return

        try:
            plan = self.project_import_service.scan(folder_path)
            if not plan.has_any_candidates():
                QMessageBox.warning(self, "未找到可导入文件", "所选文件夹中未识别到树文件、树集合或分布矩阵。")
                return
            selected = self._select_project_import_paths(plan)
            if selected is None:
                return
            consensus_tree_path, tree_collection_path, matrix_path = selected
        except Exception as exc:
            QMessageBox.critical(self, "扫描失败", str(exc))
            return

        self._run_ui_task(
            progress_text="正在一键导入项目",
            done_text="项目导入完成",
            error_progress_text="项目导入失败",
            error_title="一键导入失败",
            task=lambda: self._load_project_from_paths(
                consensus_tree_path,
                tree_collection_path,
                matrix_path,
            ),
        )

    def open_tree_file(self):
        file_path = self._choose_file(
            "选择树文件",
            "Tree Files (*.tre *.tree *.nwk *.newick *.nex *.nexus *.txt);;All Files (*)",
        )
        if not file_path:
            return

        self._run_ui_task(
            progress_text="正在读取树文件",
            done_text="树文件加载完成",
            error_progress_text="树文件加载失败",
            error_title="打开失败",
            task=lambda: self._load_tree_from_path(file_path),
        )

    def open_matrix_file(self):
        file_path = self._choose_file(
            "选择矩阵文件",
            "Table Files (*.csv *.tsv *.txt);;All Files (*)",
        )
        if not file_path:
            return

        self._run_ui_task(
            progress_text="正在读取矩阵文件",
            done_text="矩阵文件加载完成",
            error_progress_text="矩阵文件加载失败",
            error_title="打开失败",
            task=lambda: self._load_matrix_from_path(file_path),
        )

    def open_tree_collection_file(self):
        file_path = self._choose_file(
            "导入树集合",
            "Tree Collection Files (*.nex *.nexus *.tre *.trees *.txt);;All Files (*)",
        )
        if not file_path:
            return

        self._run_ui_task(
            progress_text="正在导入树集合",
            done_text="树集合导入完成",
            error_progress_text="树集合导入失败",
            error_title="树集合导入失败",
            task=lambda: self._load_tree_collection_from_path(file_path),
        )

    def _on_pre_burnin_changed(self, value: int):
        self.tree_collection_options.pre_burnin = max(0, int(value))
        self._recompute_tree_collection_state()
        self._set_status_message("载入前舍弃参数已更新；重新导入树集合后生效。")

    def _on_post_burnin_changed(self, value: int):
        self.tree_collection_options.post_burnin = max(0, int(value))
        self._recompute_tree_collection_state()

    def _on_enable_random_sampling_changed(self, checked: bool):
        self.tree_collection_options.enable_random_sampling = bool(checked)
        self._recompute_tree_collection_state()

    def _on_random_sample_size_changed(self, value: int):
        self.tree_collection_options.random_sample_size = max(0, int(value))
        self._recompute_tree_collection_state()

    def _recompute_tree_collection_state(self):
        self._refresh_consensus_tree_summary()

        if self.current_tree_collection is None:
            self.current_prepared_tree_entries = []

            self.tree_collection_panel.set_options(
                pre_burnin=self.tree_collection_options.pre_burnin,
                post_burnin=self.tree_collection_options.post_burnin,
                enable_sampling=self.tree_collection_options.enable_random_sampling,
                sample_size=self.tree_collection_options.random_sample_size,
            )

            self.tree_collection_panel.set_tree_summary(
                raw_tree_count=0,
                parse_error_count=0,
                bifurcating_count=0,
                loaded_count=0,
                analysis_count=0,
            )
            return

        raw_count = self.current_tree_collection.raw_tree_count
        loaded_entries = self.current_loaded_entries
        parse_error_count = self.current_loaded_parse_error_count

        prepared = self.tree_collection_prepare_service.prepare_loaded_entries(
            self.current_loaded_entries,
            post_burnin=self.tree_collection_options.post_burnin,
            enable_random_sampling=self.tree_collection_options.enable_random_sampling,
            random_sample_size=self.tree_collection_options.random_sample_size,
        )

        self.tree_collection_options.post_burnin = prepared.corrected_post_burnin
        self.tree_collection_options.random_sample_size = prepared.corrected_random_sample_size

        bif_count = prepared.bifurcating_count
        analysis_entries = prepared.analysis_entries

        self.current_prepared_tree_entries = analysis_entries

        self.tree_collection_panel.set_options(
            pre_burnin=self.tree_collection_options.pre_burnin,
            post_burnin=self.tree_collection_options.post_burnin,
            enable_sampling=self.tree_collection_options.enable_random_sampling,
            sample_size=self.tree_collection_options.random_sample_size,
        )

        self.tree_collection_panel.set_tree_summary(
            raw_tree_count=raw_count,
            parse_error_count=parse_error_count,
            bifurcating_count=bif_count,
            loaded_count=len(loaded_entries),
            analysis_count=len(analysis_entries),
        )

        self._set_center_info(
            self._build_tree_collection_summary_text(
                raw_count=raw_count,
                loaded_count=len(loaded_entries),
                parse_error_count=parse_error_count,
                bifurcating_count=bif_count,
                analysis_count=len(analysis_entries),
            )
        )

    def _load_tree_collection_into_memory(self, collection):
        """
        仅在“导入树集合”时调用。
        pre_burnin 在这里生效一次，决定哪些树真正载入内存。
        导入完成后，二歧树数量应固定，不再随 pre_burnin 编辑而变化。
        """
        if collection is None:
            self.current_loaded_entries = []
            self.current_loaded_bifurcating_entries = []
            self.current_loaded_parse_error_count = 0
            return

        pre_burnin = max(0, int(self.tree_collection_options.pre_burnin))

        raw_count = collection.raw_tree_count
        if pre_burnin > raw_count:
            pre_burnin = raw_count
            self.tree_collection_options.pre_burnin = pre_burnin

        loaded_entries = collection.get_loaded_entries(pre_burnin=pre_burnin)
        bifurcating_entries = collection.get_bifurcating_entries(pre_burnin=pre_burnin)

        parse_error_count = sum(
            1 for x in loaded_entries if str(getattr(x, "parse_error", "")).strip()
        )

        self.current_loaded_entries = loaded_entries
        self.current_loaded_bifurcating_entries = bifurcating_entries
        self.current_loaded_parse_error_count = parse_error_count

    def _start_analysis_worker(
        self,
        *,
        worker_attr_name,
        worker,
        action,
        busy_text,
        on_success,
        on_failed,
        on_finished,
        on_progress=None,
    ):
        action.setEnabled(False)
        self.progress_panel.set_busy_indeterminate(busy_text)
        method_label = ""
        try:
            method_label = str(action.text() or "").strip()
        except Exception:
            method_label = ""
        if not method_label:
            method_label = str(busy_text or "Analysis").strip()
        self.append_run_section("%s Analysis" % method_label)
        self.append_run_log("Process begin at %s" % self._current_timestamp())

        setattr(self, worker_attr_name, worker)
        worker.succeeded.connect(on_success)
        worker.failed.connect(on_failed)
        worker.finished.connect(on_finished)
        if on_progress is not None and hasattr(worker, "progress"):
            worker.progress.connect(on_progress)
        worker.start()

    def _finish_analysis_worker(self, worker_attr_name, action):
        worker = getattr(self, worker_attr_name, None)
        if worker is not None:
            try:
                worker.deleteLater()
            except Exception:
                pass
        setattr(self, worker_attr_name, None)

        if action is not None:
            action.setEnabled(True)

    def _append_analysis_result_to_run_log(self, method_name, result):
        try:
            adapter = ResultSchemaAdapterFactory.create(result)
            standard = adapter.to_standard_result(result=result, method_name=str(method_name or ""))
            payloads = list(standard.node_payloads.values())
        except Exception as exc:
            self.append_run_log("Could not summarize result in run log: %s" % exc)
            return

        if not payloads:
            for line in self._build_model_statistic_summary_lines(result, limit=20):
                self.append_run_log("Statistic " + line)

        for payload in sorted(payloads, key=self._node_payload_sort_key):
            self.append_run_log(self._format_node_payload_log_line(payload))

        self.append_run_log("Process end at %s" % self._current_timestamp())
        self.append_run_log("Open [View -> Open Result Window] to see the result")

    def _node_payload_sort_key(self, payload):
        text = str(getattr(payload, "display_node_id", "") or "").strip()
        try:
            return (0, int(text))
        except Exception:
            return (1, text or str(getattr(payload, "clade_key", "") or ""))

    def _format_node_payload_log_line(self, payload):
        display_id = str(getattr(payload, "display_node_id", "") or "").strip()
        if not display_id:
            display_id = str(getattr(payload, "clade_key", "") or "").strip() or "?"

        raw = dict(getattr(payload, "raw_method_payload", {}) or {})
        terminal_spec = (
            str(raw.get("terminal_spec", "") or "").strip()
            or str(raw.get("terminal_span", "") or "").strip()
        )
        prefix = "node %s" % display_id
        if terminal_spec:
            prefix += " (anc. of terminals %s)" % terminal_spec
        prefix += ":"

        supports = dict(getattr(payload, "state_supports", {}) or {})
        labels = [
            str(x).strip()
            for x in list(getattr(payload, "state_labels", []) or [])
            if str(x).strip()
        ]
        if supports:
            if labels:
                items = [
                    (state, float(supports.get(state, 0.0)))
                    for state in labels
                    if state in supports
                ]
            else:
                items = [(str(k), float(v)) for k, v in supports.items()]
            items.sort(key=lambda item: (-float(item[1]), item[0]))
            detail = " ".join("%s %.2f" % (state, value) for state, value in items)
        else:
            detail = str(getattr(payload, "state_text", "") or getattr(payload, "state_summary", "") or "").strip()

        return prefix + (" " + detail if detail else "")

    def _apply_diva_result(self, result):
        self.current_result = result
        self.current_method_name = "DIVA"
        self.progress_panel.set_done("DIVA 运行完成")
        self._update_analysis_feedback("DIVA", result)
        self._append_analysis_result_to_run_log("DIVA", result)
        self.open_result_window()

    def _apply_sdiva_result(self, result):
        self.current_sdiva_result = result
        self.current_method_name = "S-DIVA"
        self.progress_panel.set_done("S-DIVA 运行完成")
        self._update_analysis_feedback("S-DIVA", result)
        self._append_analysis_result_to_run_log("S-DIVA", result)
        self.open_result_window()

    def _apply_dec_result(self, result):
        self.current_dec_result = result
        self.current_method_name = "DEC"
        self.progress_panel.set_done("DEC 运行完成")
        self._update_analysis_feedback("DEC", result)
        self._append_analysis_result_to_run_log("DEC", result)
        self.open_result_window()

    def _apply_sdec_result(self, result):
        self.current_sdec_result = result
        self.current_method_name = "S-DEC"
        self.progress_panel.set_done("S-DEC 运行完成")
        self._update_analysis_feedback("S-DEC", result)
        self._append_analysis_result_to_run_log("S-DEC", result)
        self.open_result_window()

    def _apply_biogeobears_result(self, result):
        self.current_biogeobears_result = result
        self.current_method_name = str(getattr(result, "model_name", "") or "BioGeoBEARS")
        self.progress_panel.set_done(f"{self.current_method_name} 运行完成")
        self._update_analysis_feedback(self.current_method_name, result)
        self._append_analysis_result_to_run_log(self.current_method_name, result)
        self.open_result_window()

    def _open_diva_config_dialog(self):
        if self.current_matrix is None:
            QMessageBox.warning(self, "Cannot configure", "Please import a range matrix first.")
            return None

        area_names = infer_sdiva_area_names(self.current_matrix)
        if not area_names:
            QMessageBox.warning(self, "Cannot configure", "No areas were detected from the matrix.")
            return None

        fossil_nodes = self._sdiva_fossil_nodes_for_config(self.current_tree, self.current_matrix)
        current_config = self._prepare_sdiva_config_for_fossil_nodes(
            self.current_diva_config,
            area_names,
            fossil_nodes,
        )

        dialog = SDivaConfigDialog(
            area_names=area_names,
            config=current_config,
            fossil_count=len(fossil_nodes) if fossil_nodes else self._count_internal_nodes_for_config(self.current_tree),
            fossil_nodes=fossil_nodes,
            final_tree_available=False,
            parent=self,
            title="DIVA 配置",
            show_final_tree=False,
            show_threads=False,
        )
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.config()

    def run_diva(self):
        if not self.current_tree:
            QMessageBox.warning(self, "无法运行", "请先导入树文件。")
            return
        if not self.current_matrix:
            QMessageBox.warning(self, "无法运行", "请先导入矩阵文件。")
            return

        config = self._open_diva_config_dialog()
        if config is None:
            return
        self.current_diva_config = config

        worker = DivaRunWorker(
            service=self.diva_service,
            tree=self.current_tree,
            matrix=self.current_matrix,
            tree_name="t1",
            distribution_name="d1",
            config=config,
        )

        self._start_analysis_worker(
            worker_attr_name="diva_worker",
            worker=worker,
            action=self.run_diva_action,
            busy_text="正在运行 DIVA",
            on_success=self._on_diva_finished,
            on_failed=self._on_diva_failed,
            on_finished=self._on_diva_worker_finished,
        )

    def _on_diva_finished(self, result):
        self._apply_diva_result(result)

    def _on_diva_failed(self, message):
        self.progress_panel.set_error("DIVA 运行失败")
        QMessageBox.critical(self, "DIVA 失败", message)

    def _on_diva_worker_finished(self):
        self._finish_analysis_worker(
            worker_attr_name="diva_worker",
            action=self.run_diva_action,
        )

    def _open_sdiva_config_dialog(self):
        if self.current_matrix is None:
            QMessageBox.warning(self, "无法配置", "请先导入状态矩阵。")
            return None

        area_names = infer_sdiva_area_names(self.current_matrix)
        if not area_names:
            QMessageBox.warning(self, "无法配置", "未能从状态矩阵中识别区域。")
            return None

        fossil_nodes = self._sdiva_fossil_nodes_for_config(self.current_tree, self.current_matrix)
        current_config = self._prepare_sdiva_config_for_fossil_nodes(
            self.current_sdiva_config,
            area_names,
            fossil_nodes,
        )

        dialog = SDivaConfigDialog(
            area_names=area_names,
            config=current_config,
            fossil_count=len(fossil_nodes) if fossil_nodes else self._count_internal_nodes_for_config(self.current_tree),
            fossil_nodes=fossil_nodes,
            final_tree_available=self._is_sdiva_final_tree_available(self.current_tree),
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.config()

    def _open_dec_config_dialog(self):
        if self.current_matrix is None:
            QMessageBox.warning(self, "Cannot configure", "Please import a range matrix first.")
            return None

        area_names = infer_sdiva_area_names(self.current_matrix)
        if not area_names:
            QMessageBox.warning(self, "Cannot configure", "No areas were detected from the matrix.")
            return None

        current_config = self.current_dec_config
        if current_config is not None and list(getattr(current_config, "area_names", []) or []) != area_names:
            current_config = None

        dialog = DECConfigDialog(
            area_names=area_names,
            taxon_names=list(getattr(self.current_matrix, "taxa_names", []) or []),
            taxon_ranges=self._infer_taxon_ranges_for_config(area_names),
            root_age=self._estimate_root_age_for_config(),
            config=current_config,
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.config()

    def _open_sdec_config_dialog(self):
        if self.current_matrix is None:
            QMessageBox.warning(self, "Cannot configure", "Please import a range matrix first.")
            return None

        area_names = infer_sdiva_area_names(self.current_matrix)
        if not area_names:
            QMessageBox.warning(self, "Cannot configure", "No areas were detected from the matrix.")
            return None

        current_config = self.current_sdec_config
        if current_config is not None and list(getattr(current_config, "area_names", []) or []) != area_names:
            current_config = None

        dialog = SDECConfigDialog(
            area_names=area_names,
            taxon_names=list(getattr(self.current_matrix, "taxa_names", []) or []),
            taxon_ranges=self._infer_taxon_ranges_for_config(area_names),
            root_age=self._estimate_root_age_for_config(),
            config=current_config,
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.config()

    def _open_bayarea_config_dialog(self):
        if self.current_matrix is None:
            QMessageBox.warning(self, "Cannot configure", "Please import a range matrix first.")
            return None

        area_names = infer_sdiva_area_names(self.current_matrix)
        if not area_names:
            QMessageBox.warning(self, "Cannot configure", "No areas were detected from the matrix.")
            return None

        current_config = self.current_bayarea_config
        if current_config is not None and list(getattr(current_config, "area_names", []) or []) != area_names:
            current_config = None
        dialog_config = deepcopy(current_config) if current_config is not None else BayAreaConfig.default_for_areas(area_names)

        dialog = BayAreaConfigDialog(
            area_names=area_names,
            config=dialog_config,
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.config()

    def _open_bbm_config_dialog(self):
        if self.current_matrix is None:
            QMessageBox.warning(self, "Cannot configure", "Please import a range matrix first.")
            return None
        if self.current_tree is None:
            QMessageBox.warning(self, "Cannot configure", "Please import a consensus tree first.")
            return None

        area_names = infer_sdiva_area_names(self.current_matrix)
        if not area_names:
            QMessageBox.warning(self, "Cannot configure", "No areas were detected from the matrix.")
            return None

        try:
            node_records = self._bbm_node_records_for_config()
        except Exception as exc:
            QMessageBox.warning(self, "Cannot configure BBM", str(exc))
            return None

        current_config = self.current_bbm_config
        if current_config is not None and list(getattr(current_config, "area_names", []) or []) != area_names:
            current_config = None

        node_ids = [
            str(record.get("display_node_id", "")).strip()
            for record in list(node_records or [])
            if str(record.get("display_node_id", "")).strip()
        ]
        dialog_config = deepcopy(current_config) if current_config is not None else BBMConfig.default_for_areas(area_names, node_ids=node_ids)
        if current_config is not None:
            valid_ids = set(node_ids)
            selected_ids = [
                str(value).strip()
                for value in list(getattr(dialog_config, "selected_node_ids", []) or [])
                if str(value).strip() in valid_ids
            ]
            dialog_config.selected_node_ids = selected_ids or list(node_ids)

        dialog = BBMConfigDialog(
            area_names=area_names,
            node_records=node_records,
            config=dialog_config,
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.config()

    def _bbm_node_records_for_config(self):
        builder = self.bbm_service.dataset_builder
        area_names, rows = builder._dec_builder._collect_area_names_and_rows(self.current_matrix)
        builder._dec_builder._validate_tree_and_matrix(self.current_tree, rows)
        taxon_names = [taxon for taxon, _bits in rows]
        taxon_id_map = builder._collect_taxon_ids(self.current_matrix, taxon_names)
        return builder.build_node_records(self.current_tree, taxon_id_map)

    def _open_bayestraits_config_dialog(self):
        if self.current_matrix is None:
            QMessageBox.warning(self, "Cannot configure", "Please import a trait matrix first.")
            return None
        if self.current_tree is None:
            QMessageBox.warning(self, "Cannot configure", "Please import a reference/consensus tree first.")
            return None

        trait_columns = [
            str(x).strip()
            for x in list(getattr(self.current_matrix, "state_columns", []) or [])
            if str(x).strip()
        ]
        if not trait_columns:
            QMessageBox.warning(self, "Cannot configure", "No trait/state columns were detected from the matrix.")
            return None

        try:
            node_records = self._bayestraits_node_records_for_config()
        except Exception as exc:
            QMessageBox.warning(self, "Cannot configure BayesTraits", str(exc))
            return None

        current_config = self.current_bayestraits_config
        if current_config is not None and list(getattr(current_config, "trait_columns", []) or []) != trait_columns:
            current_config = None

        node_ids = [
            str(record.get("display_node_id", "")).strip()
            for record in list(node_records or [])
            if str(record.get("display_node_id", "")).strip()
        ]
        dialog_config = deepcopy(current_config) if current_config is not None else BayesTraitsConfig.default_for_columns(trait_columns, node_ids=node_ids)
        selected_trait_column = str(getattr(self, "current_selected_trait_column", "") or "").strip()
        if selected_trait_column in trait_columns:
            dialog_config.trait_column = selected_trait_column
            if selected_trait_column not in list(getattr(dialog_config, "selected_trait_columns", []) or []):
                dialog_config.selected_trait_columns = [selected_trait_column]
        if current_config is not None:
            valid_ids = set(node_ids)
            selected_ids = [
                str(value).strip()
                for value in list(getattr(dialog_config, "selected_node_ids", []) or [])
                if str(value).strip() in valid_ids
            ]
            dialog_config.selected_node_ids = selected_ids or list(node_ids)

        tree_set_available = bool(list(getattr(self, "current_prepared_tree_entries", []) or []))
        if not tree_set_available:
            dialog_config.use_tree_collection = False

        dialog = BayesTraitsConfigDialog(
            trait_columns=trait_columns,
            node_records=node_records,
            config=dialog_config,
            tree_set_available=tree_set_available,
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.config()

    def _bayestraits_node_records_for_config(self):
        builder = self.bayestraits_service.dataset_builder
        taxon_names = list(self.current_tree.get_leaf_names())
        taxon_id_map = builder._collect_taxon_ids(self.current_matrix, taxon_names)
        return builder.build_node_records(self.current_tree, taxon_id_map)

    def _open_sbgb_config_dialog(self):
        if self.current_matrix is None:
            QMessageBox.warning(self, "Cannot configure", "Please import a range matrix first.")
            return None

        area_names = infer_sdiva_area_names(self.current_matrix)
        if not area_names:
            QMessageBox.warning(self, "Cannot configure", "No areas were detected from the matrix.")
            return None

        current_config = self.current_sbgb_config
        if current_config is not None and list(getattr(current_config, "area_names", []) or []) != area_names:
            current_config = None
        dialog_config = deepcopy(current_config) if current_config is not None else None

        dialog = SBGBConfigDialog(
            area_names=area_names,
            taxon_ranges=self._infer_taxon_ranges_for_config(area_names),
            root_age=self._estimate_root_age_for_config(),
            config=dialog_config,
            cores_label="Threads",
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.config()

    def _open_biogeobears_config_dialog(self, model_name=None):
        if self.current_matrix is None:
            QMessageBox.warning(self, "Cannot configure", "Please import a range matrix first.")
            return None

        area_names = infer_sdiva_area_names(self.current_matrix)
        if not area_names:
            QMessageBox.warning(self, "Cannot configure", "No areas were detected from the matrix.")
            return None

        current_config = self.current_biogeobears_config
        if current_config is not None and list(getattr(current_config, "area_names", []) or []) != area_names:
            current_config = None

        if current_config is None:
            taxon_ranges = self._infer_taxon_ranges_for_config(area_names)
            dialog_config = SBGBConfig.default_for_areas(area_names, taxon_ranges)
            dialog_config.root_age = self._estimate_root_age_for_config()
        else:
            dialog_config = deepcopy(current_config)

        if model_name:
            dialog_config.model_name = model_name
        dialog = SBGBConfigDialog(
            area_names=area_names,
            taxon_ranges=self._infer_taxon_ranges_for_config(area_names),
            root_age=self._estimate_root_age_for_config(),
            config=dialog_config,
            cores_label="Cores",
            show_cores_control=True,
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.config()

    def _open_biogeobears_model_test_config_dialog(self):
        if self.current_matrix is None:
            QMessageBox.warning(self, "Cannot configure", "Please import a range matrix first.")
            return None

        area_names = infer_sdiva_area_names(self.current_matrix)
        if not area_names:
            QMessageBox.warning(self, "Cannot configure", "No areas were detected from the matrix.")
            return None

        current_config = self.current_biogeobears_model_test_config
        if current_config is not None and list(getattr(current_config, "area_names", []) or []) != area_names:
            current_config = None

        if current_config is None:
            taxon_ranges = self._infer_taxon_ranges_for_config(area_names)
            dialog_config = SBGBConfig.default_for_areas(area_names, taxon_ranges)
            dialog_config.root_age = self._estimate_root_age_for_config()
            dialog_config.test_j_models = True
        else:
            dialog_config = deepcopy(current_config)

        dialog = SBGBConfigDialog(
            area_names=area_names,
            taxon_ranges=self._infer_taxon_ranges_for_config(area_names),
            root_age=self._estimate_root_age_for_config(),
            config=dialog_config,
            cores_label="Cores",
            show_cores_control=True,
            show_model_selector=False,
            show_test_j_models=True,
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.config()

    def _infer_taxon_ranges_for_config(self, area_names):
        try:
            builder = self.dec_service.dataset_builder
            detected_areas, rows = builder._collect_area_names_and_rows(self.current_matrix)
            if list(detected_areas) == list(area_names):
                ranges = []
                for _taxon, bits in rows:
                    ranges.append("".join(area for area, bit in zip(detected_areas, bits) if str(bit) == "1"))
                return [value for value in ranges if value]
        except Exception:
            pass

        rows = list(getattr(self.current_matrix, "rows", []) or [])
        state_columns = [
            str(col).strip()
            for col in list(getattr(self.current_matrix, "state_columns", []) or [])
            if str(col).strip() and str(col).strip() not in ("ID", "Name")
        ]
        values = []
        for row in rows:
            parts = []
            for area in area_names:
                if area in state_columns and str(row.get(area, "")).strip().lower() not in ("", "0", "false", "no", "n", "absent"):
                    parts.append(area)
            if parts:
                values.append("".join(parts))
        return values

    def _estimate_root_age_for_config(self):
        tree = self.current_tree
        if tree is None:
            return ""
        try:
            _leaf, distance = tree.get_farthest_leaf()
            if float(distance) > 0:
                return "%g" % float(distance)
        except Exception:
            pass
        return ""

    def _count_internal_nodes_for_config(self, tree):
        if tree is None:
            return 0
        try:
            return sum(1 for node in tree.traverse() if not node.is_leaf())
        except Exception:
            return 0

    def _is_sdiva_final_tree_available(self, tree):
        if tree is None:
            return False
        try:
            for node in tree.traverse():
                if node.is_leaf():
                    continue
                if len(getattr(node, "children", []) or []) != 2:
                    return False
            return True
        except Exception:
            return False

    def _sdiva_fossil_nodes_for_config(self, tree, matrix):
        if tree is None or matrix is None:
            return []
        rows = list(getattr(matrix, "rows", []) or [])
        name_to_index = {}
        for idx, row in enumerate(rows, start=1):
            name = str(row.get("Name", "")).strip()
            if name:
                name_to_index[name] = idx
        if not name_to_index:
            return []

        nodes = []
        taxon_count = len(name_to_index)
        counter = 0
        try:
            iterator = tree.traverse("postorder")
        except TypeError:
            iterator = tree.traverse()
        for node in iterator:
            if node.is_leaf():
                continue
            counter += 1
            members = []
            for leaf in node.iter_leaves():
                name = str(leaf.name).strip()
                members.append(str(name_to_index.get(name, name)))
            nodes.append({
                "node_id": str(taxon_count + counter),
                "member": ",".join(members),
            })
        return nodes

    def _sdiva_fossil_node_signature(self, fossil_nodes):
        signature = []
        for node in list(fossil_nodes or []):
            if isinstance(node, dict):
                node_id = str(node.get("node_id", "")).strip()
                member = str(node.get("member", "")).strip()
            else:
                node_id = str(node).strip()
                member = ""
            signature.append("%s|%s" % (node_id, member))
        return signature

    def _prepare_sdiva_config_for_fossil_nodes(self, config, area_names, fossil_nodes):
        if config is None:
            return None
        if list(getattr(config, "area_names", []) or []) != list(area_names or []):
            return None

        current_signature = self._sdiva_fossil_node_signature(fossil_nodes)
        stored_signature = [
            str(value).strip()
            for value in list(getattr(config, "fossil_node_signature", []) or [])
        ]
        fossil_values = list(getattr(config, "fossil_values", []) or [])
        has_fossils = any(str(value).strip() for value in fossil_values)

        if stored_signature == current_signature:
            return config

        sanitized = deepcopy(config)
        sanitized.fossil_node_signature = current_signature
        if has_fossils:
            sanitized.fossil_values = [""] * len(current_signature)
        return sanitized

    def run_sdiva(self):
        if self.current_matrix is None:
            QMessageBox.warning(self, "无法运行", "请先导入状态矩阵。")
            return

        if not self.current_prepared_tree_entries:
            QMessageBox.warning(self, "无法运行", "当前没有可用于分析的树集合。")
            return

        if self.current_tree is None:
            QMessageBox.warning(self, "无法运行", "请先导入共识树。")
            return

        config = self._open_sdiva_config_dialog()
        if config is None:
            return
        self.current_sdiva_config = config

        worker = SDivaRunWorker(
            service=self.sdiva_service,
            tree_entries=self.current_prepared_tree_entries,
            matrix=self.current_matrix,
            reference_tree=self.current_tree,
            distribution_name="d1",
            config=config,
        )

        self._start_analysis_worker(
            worker_attr_name="sdiva_worker",
            worker=worker,
            action=self.run_sdiva_action,
            busy_text="正在运行 S-DIVA...",
            on_success=self._on_sdiva_finished,
            on_failed=self._on_sdiva_failed,
            on_finished=self._on_sdiva_worker_finished,
        )

    def _on_sdiva_finished(self, result):
        self._apply_sdiva_result(result)

    def _on_sdiva_failed(self, message):
        self.progress_panel.set_error("S-DIVA 运行失败")
        QMessageBox.critical(self, "S-DIVA 运行失败", message)

    def _on_sdiva_worker_finished(self):
        self._finish_analysis_worker(
            worker_attr_name="sdiva_worker",
            action=self.run_sdiva_action,
        )

    def run_dec(self):
        if self.current_tree is None:
            QMessageBox.warning(self, "无法运行", "请先导入共识树。")
            return

        if self.current_matrix is None:
            QMessageBox.warning(self, "无法运行", "请先导入区域 presence/absence 矩阵。")
            return

        engine_path = Path(self.dec_service.runner.resolve_engine_path())
        if not engine_path.exists():
            QMessageBox.warning(self, "无法运行", "未找到 lagrange-ng.exe，请先配置 DEC 引擎。")
            return

        config = self._open_dec_config_dialog()
        if config is None:
            return
        self.current_dec_config = config

        worker = DECRunWorker(
            service=self.dec_service,
            tree=self.current_tree,
            matrix=self.current_matrix,
            run_name="dec_debug",
            config=config,
            scale_tree_to_root_age=True,
        )

        self._start_analysis_worker(
            worker_attr_name="dec_worker",
            worker=worker,
            action=self.run_dec_action,
            busy_text="正在运行 DEC",
            on_success=self._on_dec_finished,
            on_failed=self._on_dec_failed,
            on_finished=self._on_dec_worker_finished,
        )

    def _on_dec_finished(self, result):
        self._apply_dec_result(result)

    def _on_dec_failed(self, message):
        self.progress_panel.set_error("DEC 运行失败")
        QMessageBox.critical(self, "DEC 运行失败", message)

    def _on_dec_worker_finished(self):
        self._finish_analysis_worker(
            worker_attr_name="dec_worker",
            action=self.run_dec_action,
        )


    def run_sdec(self):
        if self.current_tree is None:
            QMessageBox.warning(self, "无法运行", "请先导入共识树。")
            return

        if self.current_matrix is None:
            QMessageBox.warning(self, "无法运行", "请先导入区域矩阵。")
            return

        tree_entries = list(getattr(self, "current_prepared_tree_entries", []) or [])
        if not tree_entries:
            QMessageBox.warning(self, "无法运行", "请先导入树集并完成可分析树准备。")
            return

        engine_path = Path(self.dec_service.runner.resolve_engine_path())
        if not engine_path.exists():
            QMessageBox.warning(self, "无法运行", "未找到 lagrange-ng.exe，请先配置 DEC 引擎。")
            return

        config = self._open_sdec_config_dialog()
        if config is None:
            return
        self.current_sdec_config = config

        worker = SDECRunWorker(
            service=self.sdec_service,
            reference_tree=self.current_tree,
            matrix=self.current_matrix,
            tree_entries=tree_entries,
            run_name_prefix="sdec_debug",
            config=config,
        )

        self._start_analysis_worker(
            worker_attr_name="sdec_worker",
            worker=worker,
            action=self.run_sdec_action,
            busy_text="正在运行 S-DEC",
            on_success=self._on_sdec_finished,
            on_failed=self._on_sdec_failed,
            on_finished=self._on_sdec_worker_finished,
        )

    def _on_sdec_finished(self, result):
        self._apply_sdec_result(result)

    def _on_sdec_failed(self, message):
        self.progress_panel.set_error("S-DEC 运行失败")
        QMessageBox.critical(self, "S-DEC 运行失败", message)

    def _on_sdec_worker_finished(self):
        self._finish_analysis_worker(
            worker_attr_name="sdec_worker",
            action=self.run_sdec_action,
        )


    def run_bayarea(self):
        if self.current_tree is None:
            QMessageBox.warning(self, "无法运行", "请先导入带枝长的树文件。")
            return

        if self.current_matrix is None:
            QMessageBox.warning(self, "无法运行", "请先导入区域矩阵。")
            return

        try:
            self.bayarea_service.runner.resolve_executable_path()
        except Exception as exc:
            QMessageBox.warning(self, "无法运行", str(exc))
            return

        config = self._open_bayarea_config_dialog()
        if config is None:
            return
        self.current_bayarea_config = config

        worker = BayAreaRunWorker(
            service=self.bayarea_service,
            tree=self.current_tree,
            matrix=self.current_matrix,
            run_name="bayarea_debug",
            config=config,
        )

        self._start_analysis_worker(
            worker_attr_name="bayarea_worker",
            worker=worker,
            action=self.run_bayarea_action,
            busy_text="正在运行 BayArea",
            on_success=self._on_bayarea_finished,
            on_failed=self._on_bayarea_failed,
            on_finished=self._on_bayarea_worker_finished,
        )

    def _on_bayarea_finished(self, result):
        result = self._prompt_bayarea_burnin(result)
        self._apply_biogeobears_result(result)

    def _prompt_bayarea_burnin(self, result):
        stats = dict(getattr(result, "model_statistics", {}) or {})
        parameters_path = str(stats.get("parameters_path", "") or "").strip()
        if not parameters_path:
            return result

        try:
            dialog = BayAreaTracerDialog(
                parameters_path=parameters_path,
                sample_frequency=int(stats.get("sample_frequency", 0) or 0),
                chain_length=int(stats.get("chain_length", 0) or 0),
                burnin=int(stats.get("burnin", 0) or 0),
                parent=self,
            )
        except Exception as exc:
            QMessageBox.warning(self, "BayArea tracer", str(exc))
            return result

        if dialog.exec_() != QDialog.Accepted:
            return result

        burnin = dialog.selected_burnin()
        try:
            reparsed = self.bayarea_service.reparse_existing_result(
                reference_tree=self.current_tree,
                result=result,
                burnin=burnin,
            )
        except Exception as exc:
            QMessageBox.warning(self, "BayArea tracer", str(exc))
            return result

        self.current_bayarea_config = getattr(reparsed, "config", self.current_bayarea_config)
        return reparsed

    def _on_bayarea_failed(self, message):
        self.progress_panel.set_error("BayArea 运行失败")
        QMessageBox.critical(self, "BayArea 运行失败", message)

    def _on_bayarea_worker_finished(self):
        self._finish_analysis_worker(
            worker_attr_name="bayarea_worker",
            action=self.run_bayarea_action,
        )

    def run_bbm(self):
        if self.current_tree is None:
            QMessageBox.warning(self, "无法运行", "请先导入共识树。")
            return

        if self.current_matrix is None:
            QMessageBox.warning(self, "无法运行", "请先导入区域矩阵。")
            return

        try:
            self.bbm_service.runner.resolve_executable_path()
        except Exception as exc:
            QMessageBox.warning(self, "无法运行", str(exc))
            return

        config = self._open_bbm_config_dialog()
        if config is None:
            return
        self.current_bbm_config = config

        worker = BBMRunWorker(
            service=self.bbm_service,
            tree=self.current_tree,
            matrix=self.current_matrix,
            run_name="bbm_debug",
            config=config,
        )

        self._start_analysis_worker(
            worker_attr_name="bbm_worker",
            worker=worker,
            action=self.run_bbm_action,
            busy_text="正在运行 BBM",
            on_success=self._on_bbm_finished,
            on_failed=self._on_bbm_failed,
            on_finished=self._on_bbm_worker_finished,
        )

    def _on_bbm_finished(self, result):
        self._apply_biogeobears_result(result)

    def _on_bbm_failed(self, message):
        self.progress_panel.set_error("BBM 运行失败")
        QMessageBox.critical(self, "BBM 运行失败", message)

    def _on_bbm_worker_finished(self):
        self._finish_analysis_worker(
            worker_attr_name="bbm_worker",
            action=self.run_bbm_action,
        )

    def run_bayestraits(self):
        if self.current_tree is None:
            QMessageBox.warning(self, "无法运行", "请先导入参考/共识树。")
            return

        if self.current_matrix is None:
            QMessageBox.warning(self, "无法运行", "请先导入性状矩阵。")
            return

        try:
            self.bayestraits_service.runner.resolve_executable_path()
        except Exception as exc:
            QMessageBox.warning(self, "无法运行", str(exc))
            return

        config = self._open_bayestraits_config_dialog()
        if config is None:
            return
        self.current_bayestraits_config = config
        trait_column = str(getattr(config, "trait_column", "") or "").strip()
        if trait_column:
            self.current_selected_trait_column = trait_column
            self.matrix_preview.set_selected_trait_column(trait_column)

        tree_entries = []
        if bool(getattr(config, "use_tree_collection", False)) or bool(getattr(config, "continuous_dtt", False)):
            tree_entries = list(getattr(self, "current_prepared_tree_entries", []) or [])

        if not self._confirm_bayestraits_runtime(config, tree_entries):
            return

        worker = BayesTraitsRunWorker(
            service=self.bayestraits_service,
            reference_tree=self.current_tree,
            matrix=self.current_matrix,
            tree_entries=tree_entries,
            run_name="bayestraits_debug",
            config=config,
        )

        self._start_analysis_worker(
            worker_attr_name="bayestraits_worker",
            worker=worker,
            action=self.run_bayestraits_action,
            busy_text="正在运行 BayesTraits",
            on_success=self._on_bayestraits_finished,
            on_failed=self._on_bayestraits_failed,
            on_finished=self._on_bayestraits_worker_finished,
        )

    def _on_bayestraits_finished(self, result):
        self._apply_biogeobears_result(result)

    def _on_bayestraits_failed(self, message):
        self.progress_panel.set_error("BayesTraits 运行失败")
        QMessageBox.critical(self, "BayesTraits 运行失败", message)

    def _on_bayestraits_worker_finished(self):
        self._finish_analysis_worker(
            worker_attr_name="bayestraits_worker",
            action=self.run_bayestraits_action,
        )

    def _confirm_bayestraits_runtime(self, config, tree_entries):
        if not bool(getattr(config, "continuous_asr", False)):
            return True

        tip_count, internal_count = self._bayestraits_tree_size(self.current_tree)
        selected_tree_count = 1
        if bool(getattr(config, "continuous_dtt", False)):
            available = len([
                entry for entry in list(tree_entries or [])
                if getattr(entry, "parsed_tree", None) is not None
            ])
            selected_tree_count = min(
                max(1, int(getattr(config, "continuous_dtt_tree_limit", 30) or 30)),
                max(1, available),
            )

        iterations = max(0, int(getattr(config, "iterations", 0) or 0))
        sample_frequency = max(1, int(getattr(config, "sample_frequency", 1) or 1))
        burnin = max(0, int(getattr(config, "burnin", 0) or 0))
        retained_samples = max(0, int((max(0, iterations - burnin) // sample_frequency) + 1))
        total_bt_runs = 1 + selected_tree_count if bool(getattr(config, "continuous_dtt", False)) else 1
        total_node_tags = internal_count * total_bt_runs

        warnings = []
        if retained_samples < 100:
            warnings.append(
                "Retained posterior samples are fewer than 100; this is suitable for a smoke test, "
                "not for interpreting node values or DTT curves."
            )
        if internal_count >= 200:
            warnings.append(
                "The reference tree has %s internal nodes. BayesTraits Continuous ASR estimates "
                "one unknown value per internal node, so this is a large Bayesian job." % internal_count
            )
        if bool(getattr(config, "continuous_dtt", False)) and internal_count >= 200 and selected_tree_count >= 10:
            warnings.append(
                "Continuous DTT will run BayesTraits on %s dated trees plus the reference tree "
                "(%s total BayesTraits runs)." % (selected_tree_count, total_bt_runs)
            )
        if (
            bool(getattr(config, "continuous_dtt", False))
            and internal_count >= 300
            and selected_tree_count >= 20
            and iterations >= 5000000
        ):
            warnings.append(
                "This setting is in the multi-hour/day range on large trees. For the tetrapod-sized "
                "dataset we tested, 25 trees with 5.05M iterations is roughly a 25-hour class run."
            )

        if not warnings:
            return True

        message = (
            "BayesTraits Continuous ASR runtime check\n\n"
            "Tips: %s\n"
            "Internal nodes / estimated node tags per run: %s\n"
            "Selected dated trees for DTT: %s\n"
            "Total BayesTraits runs: %s\n"
            "Iterations: %s\n"
            "Sample period: %s\n"
            "BurnIn: %s\n"
            "Retained samples per run: about %s\n"
            "Total node tags across runs: %s\n\n"
            "%s\n\n"
            "Continue?"
            % (
                tip_count,
                internal_count,
                selected_tree_count if bool(getattr(config, "continuous_dtt", False)) else 0,
                total_bt_runs,
                iterations,
                sample_frequency,
                burnin,
                retained_samples,
                total_node_tags,
                "\n".join("- " + item for item in warnings),
            )
        )
        reply = QMessageBox.warning(
            self,
            "Large BayesTraits job",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _bayestraits_tree_size(self, tree):
        if tree is None:
            return 0, 0
        tips = 0
        internals = 0
        for node in tree.traverse():
            if node.is_leaf():
                tips += 1
            else:
                internals += 1
        return tips, internals


    def run_sbgb(self):
        if self.current_tree is None:
            QMessageBox.warning(self, "无法运行", "请先导入共识树。")
            return

        if self.current_matrix is None:
            QMessageBox.warning(self, "无法运行", "请先导入区域矩阵。")
            return

        tree_entries = list(getattr(self, "current_prepared_tree_entries", []) or [])
        if not tree_entries:
            QMessageBox.warning(self, "无法运行", "请先导入树集合并完成可分析树准备。")
            return

        try:
            self.biogeobears_service.runner.resolve_rscript_path()
            self.biogeobears_service.runner.resolve_wrapper_script_path()
            self.biogeobears_service.runner.resolve_site_library_path()
        except Exception as exc:
            QMessageBox.warning(self, "无法运行", str(exc))
            return

        config = self._open_sbgb_config_dialog()
        if config is None:
            return
        self.current_sbgb_config = config

        model_name = str(config.model_name)
        display_model = SBGB_MODEL_DISPLAY.get(model_name, model_name)
        if not bool(config.include_null_range):
            display_model = "%s (no null range)" % display_model

        worker = SBGBRunWorker(
            service=self.sbgb_service,
            reference_tree=self.current_tree,
            matrix=self.current_matrix,
            tree_entries=tree_entries,
            run_name_prefix=f"sbgb_{model_name.lower()}",
            config=config,
        )

        self._start_analysis_worker(
            worker_attr_name="sbgb_worker",
            worker=worker,
            action=self.run_sbgb_action,
            busy_text=f"正在运行 S-BGB-{display_model}",
            on_success=self._on_sbgb_finished,
            on_failed=self._on_sbgb_failed,
            on_finished=self._on_sbgb_worker_finished,
            on_progress=self._on_sbgb_progress,
        )

    def _on_sbgb_finished(self, result):
        self._apply_biogeobears_result(result)

    def _on_sbgb_failed(self, message):
        self.progress_panel.set_error("S-BGB 运行失败")
        QMessageBox.critical(self, "S-BGB 运行失败", message)

    def _on_sbgb_progress(self, completed, total, _message):
        total = max(1, int(total or 1))
        completed = max(0, int(completed or 0))
        percent = int(100.0 * completed / total)
        text = "S-BGB 运行中：已完成 %s/%s 棵树" % (completed, total)
        self.progress_panel.set_progress(percent, text)
        self._set_status_message(text)

    def _on_sbgb_worker_finished(self):
        self._finish_analysis_worker(
            worker_attr_name="sbgb_worker",
            action=self.run_sbgb_action,
        )


    def run_biogeobears(self, model_name=None):
        if isinstance(model_name, bool):
            model_name = None

        if self.current_tree is None:
            QMessageBox.warning(self, "无法运行", "请先导入共识树。")
            return

        if self.current_matrix is None:
            QMessageBox.warning(self, "无法运行", "请先导入区域矩阵。")
            return

        try:
            self.biogeobears_service.runner.resolve_wrapper_script_path()
        except Exception as exc:
            QMessageBox.warning(self, "无法运行", str(exc))
            return

        config = self._open_biogeobears_config_dialog(model_name)
        if config is None:
            return
        self.current_biogeobears_config = config

        effective_model_name = str(config.model_name)
        display_model = SBGB_MODEL_DISPLAY.get(effective_model_name, effective_model_name)
        if not bool(config.include_null_range):
            display_model = "%s (no null range)" % display_model

        worker = BioGeoBEARSRunWorker(
            service=self.biogeobears_service,
            tree=self.current_tree,
            matrix=self.current_matrix,
            run_name=f"bgb_{effective_model_name.lower()}_debug",
            config=config,
        )

        if effective_model_name not in {
            "DEC",
            "DECJ",
            "DIVALIKE",
            "DIVALIKEJ",
            "BAYAREALIKE",
            "BAYAREALIKEJ",
        }:
            QMessageBox.warning(self, "无法运行", f"未知 BioGeoBEARS 模型：{model_name}")
            return

        self._start_analysis_worker(
            worker_attr_name="biogeobears_worker",
            worker=worker,
            action=self.run_bgb_action,
            busy_text=f"正在运行 BioGeoBEARS-{display_model}",
            on_success=self._on_biogeobears_finished,
            on_failed=self._on_biogeobears_failed,
            on_finished=self._on_biogeobears_worker_finished,
        )

    def _on_biogeobears_finished(self, result):
        self._apply_biogeobears_result(result)

    def _on_biogeobears_failed(self, message):
        self.progress_panel.set_error("BioGeoBEARS 运行失败")
        QMessageBox.critical(self, "BioGeoBEARS 运行失败", message)

    def _on_biogeobears_worker_finished(self):
        self._finish_analysis_worker(
            worker_attr_name="biogeobears_worker",
            action=self.run_bgb_action,
        )

    def run_biogeobears_model_test(self):
        if self.current_tree is None:
            QMessageBox.warning(self, "无法运行", "请先导入共识树。")
            return

        if self.current_matrix is None:
            QMessageBox.warning(self, "无法运行", "请先导入区域矩阵。")
            return

        config = self._open_biogeobears_model_test_config_dialog()
        if config is None:
            return
        self.current_biogeobears_model_test_config = config

        worker = BioGeoBEARSModelTestWorker(
            service=self.biogeobears_model_test_service,
            tree=self.current_tree,
            matrix=self.current_matrix,
            run_name_prefix="bgb_model_test_debug",
            config=config,
        )

        self._start_analysis_worker(
            worker_attr_name="biogeobears_model_test_worker",
            worker=worker,
            action=self.run_bgb_model_test_action,
            busy_text="正在运行 BioGeoBEARS 模型检测",
            on_success=self._on_biogeobears_model_test_finished,
            on_failed=self._on_biogeobears_model_test_failed,
            on_finished=self._on_biogeobears_model_test_worker_finished,
            on_progress=self._on_biogeobears_model_test_progress,
        )

    def _on_biogeobears_model_test_finished(self, result):
        self.current_biogeobears_model_test_result = result
        self.progress_panel.set_done("BioGeoBEARS 模型检测完成")
        self._set_center_info(self._build_biogeobears_model_test_summary_text(result))
        self._set_status_message(
            f"BioGeoBEARS 模型检测完成：最佳模型={result.best_display_name or '无'}"
        )
        self.append_run_log("Best model: %s" % (result.best_display_name or "None"))
        self.append_run_log("Process end at %s" % self._current_timestamp())
        self.append_run_log("Open [Model Test -> Compare Models Using BioGeoBEARS] to run another comparison")
        self._show_biogeobears_model_test_dialog(result)

    def _on_biogeobears_model_test_failed(self, message):
        self.progress_panel.set_error("BioGeoBEARS 模型检测失败")
        QMessageBox.critical(self, "BioGeoBEARS 模型检测失败", message)

    def _on_biogeobears_model_test_progress(self, completed, total, _message):
        total = max(1, int(total or 1))
        completed = max(0, int(completed or 0))
        percent = int(100.0 * completed / total)
        text = "BioGeoBEARS model test: %s/%s models finished" % (completed, total)
        self.progress_panel.set_progress(percent, text)
        self._set_status_message(text)

    def _on_biogeobears_model_test_worker_finished(self):
        worker = getattr(self, "biogeobears_model_test_worker", None)
        if worker is not None:
            try:
                worker.deleteLater()
            except Exception:
                pass
        self.biogeobears_model_test_worker = None

        if hasattr(self, "run_bgb_model_test_action") and self.run_bgb_model_test_action is not None:
            self.run_bgb_model_test_action.setEnabled(True)

    def _show_biogeobears_model_test_dialog(self, result):
        from PyQt5.QtGui import QFont
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QTabWidget,
            QVBoxLayout,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("BioGeoBEARS 模型检测")
        dialog.resize(1120, 700)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        font = QFont("Microsoft YaHei UI", 10)
        dialog.setFont(font)

        dialog.setStyleSheet("""
            QDialog {
                background-color: #f6f7f9;
            }

            QTabWidget::pane {
                border: 1px solid #d9dde3;
                background: #ffffff;
                border-radius: 8px;
            }

            QTabBar::tab {
                background: #e9edf2;
                color: #333333;
                padding: 9px 18px;
                margin-right: 3px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 10.5pt;
            }

            QTabBar::tab:selected {
                background: #ffffff;
                color: #111111;
                font-weight: 600;
                border: 1px solid #d9dde3;
                border-bottom: 1px solid #ffffff;
            }

            QLabel {
                color: #222222;
                font-size: 10.5pt;
            }

            QTableWidget {
                background: #ffffff;
                alternate-background-color: #f7f9fc;
                gridline-color: #e0e4ea;
                selection-background-color: #dbeafe;
                selection-color: #111111;
                font-size: 10pt;
            }

            QHeaderView::section {
                background-color: #eef1f5;
                color: #222222;
                padding: 7px 10px;
                border: 0px;
                border-right: 1px solid #d9dde3;
                border-bottom: 1px solid #d9dde3;
                font-weight: 600;
            }

            QPushButton {
                padding: 6px 18px;
                font-size: 10pt;
            }
        """)

        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        tabs = QTabWidget(dialog)
        tabs.addTab(self._build_bgb_model_test_lrt_tab(result), "LRT")
        tabs.addTab(self._build_bgb_model_test_overview_tab(result), "概览")
        tabs.addTab(self._build_bgb_model_test_table_tab(result), "模型比较")
        tabs.addTab(self._build_bgb_model_test_explain_tab(result), "模型说明")
        tabs.addTab(self._build_bgb_model_test_diagnostics_tab(result), "运行诊断")
        main_layout.addWidget(tabs)

        button_box = QDialogButtonBox(QDialogButtonBox.Close, dialog)
        button_box.rejected.connect(dialog.reject)
        main_layout.addWidget(button_box)

        dialog.exec_()

    def _build_bgb_model_test_overview_tab(self, result):
        from PyQt5.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(0)

        best_row = self._get_bgb_model_test_best_row(result)
        criterion = str(getattr(result, "criterion_used", "") or "AICc")

        card, card_layout = self._make_bgb_card()
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        card_layout.addWidget(self._make_bgb_section_title("检测结论"))
        card_layout.addSpacing(8)

        if best_row is not None:
            delta_value = self._get_bgb_model_test_delta(best_row, criterion)
            support_label = self._classify_bgb_model_support(delta_value)
            card_layout.setSpacing(8)

            card_layout.addWidget(self._make_bgb_inline_label(
                f"<b>推荐模型：</b>{best_row.display_name}"
            ))
            card_layout.addSpacing(8)

            # 比较准则、模型权重、ΔAICc 竖版排列
            card_layout.addWidget(self._make_bgb_inline_label(
                f"<b>比较准则：</b>{criterion}"
            ))
            card_layout.addSpacing(8)

            card_layout.addWidget(self._make_bgb_inline_label(
                f"<b>模型权重：</b>{self._fmt_float(best_row.weight)}"
            ))
            card_layout.addSpacing(8)

            card_layout.addWidget(self._make_bgb_inline_label(
                f"<b>Δ{criterion}：</b>{self._fmt_float(delta_value)}"
            ))
            card_layout.addSpacing(8)

            card_layout.addWidget(self._make_bgb_inline_label(
                f"<b>支持等级：</b>{support_label}"
            ))
            card_layout.addSpacing(8)

            card_layout.addWidget(self._make_bgb_inline_label(
                f"<span style='color:#374151;'>在当前 {model_count} 个 BioGeoBEARS 候选模型中，"
                f"<b>{best_row.display_name}</b> 在拟合效果和模型复杂度之间取得了最佳平衡。</span>"
            ))
        else:
            card_layout.addWidget(self._make_bgb_paragraph(
                "未能确定推荐模型。所有模型可能均失败，或模型比较指标缺失。请查看“运行诊断”页。"
            ))

        if getattr(result, "warnings", None):
            warning_html = "".join(
                f"<p style='margin: 0 0 8px 0;'>• {str(w)}</p>"
                for w in result.warnings
            )
            card_layout.addWidget(self._make_bgb_section_title("警告"))
            card_layout.addWidget(self._make_bgb_html_label(
                f"<div style='line-height:160%; color:#92400e;'>{warning_html}</div>"
            ))

        card_layout.addStretch(1)
        layout.addWidget(card)

        return content

    def _build_bgb_model_test_table_tab(self, result):
        from PyQt5.QtWidgets import (
            QAbstractItemView,
            QHeaderView,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )

        widget = QWidget()
        layout = QVBoxLayout(widget)

        headers = [
            "模型",
            "lnL",
            "参数数 k",
            "AIC",
            "AICc",
            "ΔAIC",
            "ΔAICc",
            "模型权重",
            "支持等级",
            "状态",
        ]



        table = QTableWidget(widget)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setDefaultSectionSize(34)
        table.verticalHeader().setVisible(False)
        table.setColumnCount(len(headers))
        table.setRowCount(len(result.rows))
        table.setHorizontalHeaderLabels(headers)
        table.setStyleSheet("""
                            QTableWidget {
                                border: 1px solid #d9dde3;
                                border-radius: 8px;
                                background: #ffffff;
                                font-size: 10pt;
                            }

                            QTableWidget::item {
                                padding: 6px 8px;
                            }
                        """)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)


        criterion = str(getattr(result, "criterion_used", "") or "AICc")

        for r, row in enumerate(result.rows):
            delta_for_support = self._get_bgb_model_test_delta(row, criterion)
            support_label = self._classify_bgb_model_support(delta_for_support)

            values = [
                row.display_name,
                self._fmt_float(row.log_likelihood),
                "" if row.num_params is None else str(row.num_params),
                self._fmt_float(row.aic),
                self._fmt_float(row.aicc),
                self._fmt_float(row.delta_aic),
                self._fmt_float(row.delta_aicc),
                self._fmt_float(row.weight),
                support_label,
                "成功" if row.success else "失败",
            ]

            for c, value in enumerate(values):
                table.setItem(r, c, QTableWidgetItem(value))

        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(table)
        return widget

    def _build_bgb_model_test_lrt_tab(self, result):
        from PyQt5.QtWidgets import (
            QAbstractItemView,
            QLabel,
            QHeaderView,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )

        widget = QWidget()
        layout = QVBoxLayout(widget)

        path = str(getattr(result, "teststable_path", "") or "")
        if path:
            note = QLabel("teststable.txt: %s" % path, widget)
            note.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(note)

        headers = [
            "Alternative",
            "Null",
            "lnL alt",
            "lnL null",
            "k alt",
            "k null",
            "df",
            "LRT",
            "p-value",
            "Status",
        ]

        entries = list(getattr(result, "lrt_entries", []) or [])
        table = QTableWidget(widget)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setDefaultSectionSize(34)
        table.verticalHeader().setVisible(False)
        table.setColumnCount(len(headers))
        table.setRowCount(len(entries))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)

        for r, entry in enumerate(entries):
            values = [
                entry.alt_display_name,
                entry.null_display_name,
                self._fmt_float(entry.alt_log_likelihood),
                self._fmt_float(entry.null_log_likelihood),
                "" if entry.alt_num_params is None else str(entry.alt_num_params),
                "" if entry.null_num_params is None else str(entry.null_num_params),
                "" if entry.df is None else str(entry.df),
                self._fmt_float(entry.lrt_statistic),
                self._fmt_float(entry.p_value),
                "Success" if entry.success else ("Failed: %s" % entry.error_message),
            ]
            for c, value in enumerate(values):
                table.setItem(r, c, QTableWidgetItem(value))

        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)
        return widget

    def _build_bgb_model_test_explain_tab(self, result):
        from PyQt5.QtWidgets import QVBoxLayout, QWidget

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)

        metric_card, metric_layout = self._make_bgb_card()
        metric_layout.addWidget(self._make_bgb_section_title("指标含义"))

        metric_layout.setSpacing(8)

        metric_layout.addWidget(self._make_bgb_inline_label(
            "<b>lnL</b>：log likelihood，对数似然。数值越大，表示模型对数据拟合越好。"
        ))
        metric_layout.addWidget(self._make_bgb_inline_label(
            "<b>k</b>：自由参数数量。参数越多，模型越复杂。"
        ))
        metric_layout.addWidget(self._make_bgb_inline_label(
            "<b>AIC</b>：综合拟合度和模型复杂度的模型选择指标，越小越好。"
        ))
        metric_layout.addWidget(self._make_bgb_inline_label(
            "<b>AICc</b>：AIC 的小样本校正版。物种数较少时通常优先使用 AICc。"
        ))
        metric_layout.addWidget(self._make_bgb_inline_label(
            "<b>ΔAICc</b>：该模型与最佳模型之间的 AICc 差值。最佳模型的 ΔAICc 为 0。"
        ))
        metric_layout.addWidget(self._make_bgb_inline_label(
            "<b>模型权重</b>：当前候选模型集合中的相对支持度，不代表绝对真实概率。"
        ))
        layout.addWidget(metric_card)

        rule_card, rule_layout = self._make_bgb_card()
        rule_layout.addWidget(self._make_bgb_section_title("支持等级含义说明"))

        rule_layout.setSpacing(8)

        rule_layout.addWidget(self._make_bgb_inline_label(
            "<b>Δ ≤ 2</b>：强支持，或与最佳模型差异较小。"
        ))
        rule_layout.addWidget(self._make_bgb_inline_label(
            "<b>2 < Δ ≤ 4</b>：中等支持。"
        ))
        rule_layout.addWidget(self._make_bgb_inline_label(
            "<b>4 < Δ ≤ 10</b>：弱支持。"
        ))
        rule_layout.addWidget(self._make_bgb_inline_label(
            "<b>Δ > 10</b>：支持度很低。"
        ))
        layout.addWidget(rule_card)

        layout.addStretch(1)
        return self._build_bgb_scroll_tab(content)

    def _build_bgb_model_test_diagnostics_tab(self, result):
        from PyQt5.QtWidgets import QTextEdit, QVBoxLayout, QWidget

        widget = QWidget()
        layout = QVBoxLayout(widget)

        lines = []
        lines.append("BioGeoBEARS 模型检测运行诊断")
        lines.append("")
        lines.append(f"有效模型数: {getattr(result, 'effective_model_count', 0)}")
        lines.append(f"失败模型数: {getattr(result, 'failed_model_count', 0)}")
        lines.append(f"比较准则: {getattr(result, 'criterion_used', '')}")
        lines.append(f"最佳模型: {getattr(result, 'best_display_name', '') or '无'}")
        lines.append("")

        for row in result.rows:
            lines.append("=" * 60)
            lines.append(f"模型: {row.display_name}")
            lines.append(f"内部名称: {row.model_name}")
            lines.append(f"状态: {'成功' if row.success else '失败'}")
            lines.append(f"workdir: {row.workdir}")
            lines.append(f"output_json: {row.output_json_path}")
            if row.error_message:
                lines.append("错误信息:")
                lines.append(row.error_message)
            lines.append("")

        if getattr(result, "warnings", None):
            lines.append("=" * 60)
            lines.append("警告:")
            for warning in result.warnings:
                lines.append(f"- {warning}")

        text = QTextEdit(widget)
        text.setReadOnly(True)
        text.setPlainText("\n".join(lines))
        text.setStyleSheet("""
            QTextEdit {
                background: #ffffff;
                border: 1px solid #d9dde3;
                border-radius: 8px;
                padding: 12px;
                font-family: "Consolas", "Microsoft YaHei UI";
                font-size: 10pt;
                line-height: 150%;
            }
        """)
        layout.addWidget(text)

        return widget

    def _get_bgb_model_test_best_row(self, result):
        best_name = str(getattr(result, "best_model_name", "") or "")
        if best_name:
            for row in result.rows:
                if row.model_name == best_name:
                    return row

        criterion = str(getattr(result, "criterion_used", "") or "AICc")
        success_rows = [row for row in result.rows if row.success]

        if not success_rows:
            return None

        if criterion == "AICc":
            rows = [row for row in success_rows if row.aicc is not None]
            if rows:
                return min(rows, key=lambda x: float(x.aicc))

        rows = [row for row in success_rows if row.aic is not None]
        if rows:
            return min(rows, key=lambda x: float(x.aic))

        return None

    def _get_bgb_model_test_delta(self, row, criterion):
        criterion = str(criterion or "").upper()
        if criterion == "AICC":
            return row.delta_aicc
        return row.delta_aic

    def _classify_bgb_model_support(self, delta_value):
        if delta_value is None:
            return "无法判断"

        try:
            delta = float(delta_value)
        except Exception:
            return "无法判断"

        if delta == 0:
            return "最佳模型"
        if delta <= 2:
            return "强支持"
        if delta <= 4:
            return "中等支持"
        if delta <= 10:
            return "弱支持"
        return "支持度很低"

    def _build_bgb_scroll_tab(self, inner_widget):
        from PyQt5.QtWidgets import QScrollArea, QVBoxLayout, QWidget

        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(outer)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(inner_widget)

        layout.addWidget(scroll)
        return outer

    def _make_bgb_card(self):
        from PyQt5.QtWidgets import QFrame, QVBoxLayout

        card = QFrame()
        card.setObjectName("bgbCard")
        card.setStyleSheet("""
            QFrame#bgbCard {
                background: #ffffff;
                border: 1px solid #e1e5eb;
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        return card, layout

    def _make_bgb_html_label(self, html):
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QLabel

        label = QLabel()
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setText(html)
        label.setStyleSheet("""
            QLabel {
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", Arial;
                font-size: 10.5pt;
                line-height: 150%;
                color: #222222;
            }
        """)
        return label

    def _make_bgb_section_title(self, text):
        return self._make_bgb_html_label(
            f"""
            <div style="
                font-size: 15pt;
                font-weight: 700;
                color: #111827;
                margin-bottom: 8px;
            ">{text}</div>
            """
        )

    def _make_bgb_paragraph(self, text):
        return self._make_bgb_html_label(
            f"""
            <div style="
                line-height: 165%;
                margin: 0;
            ">{text}</div>
            """
        )

    def _make_bgb_inline_label(self, html):
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QLabel

        label = QLabel()
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setText(html)
        label.setStyleSheet("""
            QLabel {
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", Arial;
                font-size: 10.5pt;
                color: #222222;
                margin: 0px;
                padding: 0px;
            }
        """)
        return label
