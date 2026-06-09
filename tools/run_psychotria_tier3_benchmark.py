import json
import os
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Keep native math libraries from multiplying per-process threads during
# tree-set analyses. S-DEC still controls tree-level parallelism explicitly.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import tools.run_psychotria_benchmark as bench

from application.services.bayarea_analysis_service import BayAreaAnalysisService
from application.services.bayestraits_analysis_service import BayesTraitsAnalysisService
from application.services.bbm_analysis_service import BBMAnalysisService
from application.services.biogeobears_analysis_service import BioGeoBEARSAnalysisService
from application.services.dec_analysis_service import DECAnalysisService
from application.services.sbgb_analysis_service import SBGBAnalysisService
from application.services.sdec_analysis_service import SDECAnalysisService
from domain.models.bayarea_config import BayAreaConfig
from domain.models.bayestraits_config import BayesTraitsConfig
from domain.models.bbm_config import BBMConfig
from domain.models.sbgb_config import SBGBConfig
from domain.models.sdec_config import SDECConfig
from domain.models.sdiva_config import infer_sdiva_area_names
from infrastructure.io.csv_matrix_reader import CsvMatrixReader
from infrastructure.tree.tree_reader import TreeReader
from ete3 import Tree


RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
RUN_ROOT = PROJECT_ROOT / "runs" / "benchmarks" / ("psychotria_tier3_%s" % RUN_STAMP)
REPORT_PATH = PROJECT_ROOT / "docs" / ("psychotria_tier3_benchmark_%s.md" % RUN_STAMP)

bench.RUN_ROOT = RUN_ROOT
bench.STATE_PATH = RUN_ROOT / "benchmark_state.json"
bench.REPORT_PATH = REPORT_PATH
bench.PROGRESS_PATH = RUN_ROOT / "progress.log"


def sbgb_progress_logger(model_name):
    def callback(done, total, message):
        if done == total or done % 25 == 0:
            bench.log("S-BGB %s progress %s/%s %s" % (model_name, done, total, message))
    return callback


def main():
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    bench.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    bench.log("Psychotria tier 3 benchmark run root: %s" % RUN_ROOT)

    data_dir = bench.find_data_dir()
    tree_path = data_dir / "Psychotria.tree"
    matrix_path = data_dir / "distribution.csv"
    trees_path = data_dir / "dataset.trees"

    reference_tree_text = TreeReader().read_tree(str(tree_path))
    reference_tree = Tree(reference_tree_text, format=1)
    matrix = CsvMatrixReader().read(str(matrix_path))
    collection, prepared = bench.load_tree_entries(trees_path)
    tree_entries = list(prepared.analysis_entries or [])

    dec_service = DECAnalysisService(
        engine_path=PROJECT_ROOT / "engines" / "lagrange-ng" / "lagrange-ng.exe",
        work_root=RUN_ROOT / "dec",
    )
    sdec_service = SDECAnalysisService(dec_service, project_root=PROJECT_ROOT)

    area_names = infer_sdiva_area_names(matrix)
    taxon_ranges = bench.infer_taxon_ranges(matrix, area_names, dec_service)
    root_age = bench.estimate_root_age(reference_tree)
    coordinates, coordinates_path = bench.load_coordinates(area_names)

    payload = {
        "benchmark_tier": "tier3",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": "",
        "run_root": str(RUN_ROOT),
        "data_dir": str(data_dir),
        "tree_path": str(tree_path),
        "matrix_path": str(matrix_path),
        "trees_path": str(trees_path),
        "coordinates_path": coordinates_path,
        "area_names": area_names,
        "taxon_ranges": taxon_ranges,
        "root_age": root_age,
        "reference_tree": reference_tree_text,
        "runtime_environment": {
            "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS", ""),
            "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", ""),
            "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS", ""),
            "NUMEXPR_NUM_THREADS": os.environ.get("NUMEXPR_NUM_THREADS", ""),
        },
        "tree_collection": {
            "raw_count": int(collection.raw_tree_count),
            "loaded_count": int(prepared.loaded_count),
            "parse_error_count": int(prepared.parse_error_count),
            "bifurcating_count": int(prepared.bifurcating_count),
            "analysis_count": int(prepared.analysis_count),
        },
        "results": [],
    }
    bench.save_state(payload)

    bgb_service = BioGeoBEARSAnalysisService(
        rscript_path=PROJECT_ROOT / "engines" / "R" / "bin" / "Rscript.exe",
        wrapper_script_path=PROJECT_ROOT / "engines" / "biogeobears" / "bgb_runner.R",
        work_root=RUN_ROOT / "biogeobears",
        site_library_path=PROJECT_ROOT / "engines" / "R" / "site-library",
    )
    sbgb_service = SBGBAnalysisService(bgb_service, project_root=PROJECT_ROOT)
    bayarea_service = BayAreaAnalysisService(
        executable_path=PROJECT_ROOT / "engines" / "bayarea" / "bin" / "bayarea.exe",
        work_root=RUN_ROOT / "bayarea",
    )
    bbm_service = BBMAnalysisService(
        executable_path=PROJECT_ROOT / "engines" / "mrbayes" / "mb.3.2.7-win32.exe",
        work_root=RUN_ROOT / "bbm",
    )
    bayestraits_service = BayesTraitsAnalysisService(
        executable_path=PROJECT_ROOT / "engines" / "bayestraits" / "BayesTraitsV5.exe",
        work_root=RUN_ROOT / "bayestraits",
    )

    sdec_config = SDECConfig.default_for_areas(area_names)
    sdec_config.root_age = root_age
    sdec_config.threads = 1

    bench.run_task(
        payload,
        "S-DEC full tree set serial OpenBLAS-limited",
        lambda: bench.summarize_result(
            sdec_service.analyze(
                reference_tree=reference_tree,
                matrix=matrix,
                tree_entries=tree_entries,
                run_name_prefix="psychotria_tier3_sdec_serial",
                config=sdec_config,
            ),
            "S-DEC",
        ),
    )

    for model_name in ["DEC", "DECJ", "DIVALIKE", "DIVALIKEJ", "BAYAREALIKE", "BAYAREALIKEJ"]:
        def run_sbgb(model=model_name):
            config = SBGBConfig.default_for_areas(area_names, taxon_ranges)
            config.root_age = root_age
            config.cores = 4
            config.model_name = model
            return bench.summarize_result(
                sbgb_service.analyze(
                    reference_tree=reference_tree,
                    matrix=matrix,
                    tree_entries=tree_entries,
                    config=config,
                    run_name_prefix="psychotria_tier3_sbgb_%s" % model.lower(),
                    progress_callback=sbgb_progress_logger(model),
                ),
                "S-BioGeoBEARS-%s" % model,
            )

        bench.run_task(payload, "S-BioGeoBEARS %s full tree set" % model_name, run_sbgb)

    bayarea_config = BayAreaConfig.default_for_areas(area_names)
    bayarea_config.coordinates = coordinates
    bayarea_config.chain_length = 50000000
    bayarea_config.sample_frequency = 10000
    bayarea_config.burnin = 0
    bayarea_config.model_type = "DISTANCE_NORM"

    bench.run_task(
        payload,
        "BayArea 50M",
        lambda: bench.summarize_result(
            bayarea_service.analyze(
                tree=reference_tree,
                matrix=matrix,
                config=bayarea_config,
                run_name="psychotria_tier3_bayarea_50m",
            ),
            "BayArea",
        ),
    )

    bbm_node_records = bbm_service.dataset_builder.build_node_records(
        reference_tree,
        bbm_service.dataset_builder._collect_taxon_ids(
            matrix,
            [name for name in reference_tree.get_leaf_names()],
        ),
    )
    bbm_node_ids = [
        str(record.get("display_node_id", "")).strip()
        for record in bbm_node_records
        if str(record.get("display_node_id", "")).strip()
    ]
    bbm_config = BBMConfig.default_for_areas(area_names, node_ids=bbm_node_ids)
    bbm_config.chain_length = 500000
    bbm_config.sample_frequency = 100
    bbm_config.discard_samples = 500

    bench.run_task(
        payload,
        "BBM 500k",
        lambda: bench.summarize_result(
            bbm_service.analyze(
                tree=reference_tree,
                matrix=matrix,
                config=bbm_config,
                run_name="psychotria_tier3_bbm_500k",
            ),
            "BBM",
        ),
    )

    bayestraits_node_records = bayestraits_service.dataset_builder.build_node_records(
        reference_tree,
        bayestraits_service.dataset_builder._collect_taxon_ids(
            matrix,
            list(reference_tree.get_leaf_names()),
        ),
    )
    bayestraits_node_ids = [
        str(record.get("display_node_id", "")).strip()
        for record in bayestraits_node_records
        if str(record.get("display_node_id", "")).strip()
    ]
    trait_columns = list(getattr(matrix, "state_columns", []) or [])
    bayestraits_config = BayesTraitsConfig.default_for_columns(trait_columns, node_ids=bayestraits_node_ids)
    bayestraits_config.analysis_method = "MCMC"
    bayestraits_config.iterations = 5050000
    bayestraits_config.sample_frequency = 10000
    bayestraits_config.burnin = 50000
    bayestraits_config.use_tree_collection = True

    bench.run_task(
        payload,
        "BayesTraits MultiState MCMC",
        lambda: bench.summarize_result(
            bayestraits_service.analyze(
                reference_tree=reference_tree,
                matrix=matrix,
                config=bayestraits_config,
                tree_entries=tree_entries,
                run_name="psychotria_tier3_bayestraits_multistate_mcmc",
            ),
            "BayesTraits MultiState MCMC",
        ),
    )

    payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
    bench.save_state(payload)
    bench.log("Tier 3 benchmark finished. Report: %s" % REPORT_PATH)


if __name__ == "__main__":
    main()
