import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run small DIVA, DEC, and BioGeoBEARS analyses from an installed RASP5 tree."
    )
    parser.add_argument("--install-root", required=True, help="Installed RASP5 directory.")
    parser.add_argument("--output-root", required=True, help="Directory for generated run files and report.")
    return parser.parse_args()


def assert_imported_from(module, install_root):
    module_path = Path(module.__file__).resolve()
    try:
        module_path.relative_to(install_root)
    except ValueError:
        raise AssertionError(
            "Module was not imported from the installed tree: %s" % module_path
        )
    return str(module_path)


def assert_installed_python(install_root):
    expected = (install_root / "runtime" / "python" / "python.exe").resolve()
    actual = Path(sys.executable).resolve()
    if os.path.normcase(str(actual)) != os.path.normcase(str(expected)):
        raise AssertionError(
            "Smoke must run with the installed Python runtime: expected %s, got %s"
            % (expected, actual)
        )
    return str(actual)


def estimate_root_age(tree):
    try:
        _leaf, distance = tree.get_farthest_leaf()
        if float(distance) > 0:
            return "%g" % float(distance)
    except Exception:
        pass
    return ""


def infer_taxon_ranges(matrix, area_names, dec_service):
    detected_areas, rows = dec_service.dataset_builder._collect_area_names_and_rows(matrix)
    ranges = []
    for _taxon, bits in rows:
        value = "".join(
            area for area, bit in zip(detected_areas, bits) if str(bit) == "1"
        )
        if value:
            ranges.append(value)
    if list(detected_areas) != list(area_names):
        raise AssertionError("Area-name inference differs between DEC and S-DIVA builders.")
    return ranges


def run_case(name, callback):
    started = time.perf_counter()
    record = {"name": name, "status": "running", "error": "", "summary": {}}
    print("START %s" % name, flush=True)
    try:
        record["summary"] = callback()
        record["status"] = "ok"
        print("OK %s" % name, flush=True)
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = str(exc)
        record["traceback"] = traceback.format_exc()
        print("FAILED %s: %s" % (name, exc), flush=True)
    record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    return record


def summarize_result(result):
    node_count = len(getattr(result, "node_results", {}) or {})
    if node_count <= 0:
        raise AssertionError("Analysis produced no parsed node results.")
    artifacts = getattr(result, "artifacts", None)
    run_dir = str(getattr(artifacts, "run_dir", "") or "")
    if not run_dir:
        note = str(getattr(result, "result_note", "") or "")
        marker = " workdir="
        if marker in note:
            run_dir = note.split(marker, 1)[1].split(" ", 1)[0].strip()
    return {
        "result_class": type(result).__name__,
        "node_count": node_count,
        "warning_count": len(getattr(result, "parse_warnings", []) or []),
        "run_dir": run_dir,
    }


def main():
    args = parse_args()
    install_root = Path(args.install_root).resolve()
    output_root = Path(args.output_root).resolve()
    if not (install_root / "BUNDLE-MANIFEST.json").is_file():
        raise FileNotFoundError("Not an installed RASP5 tree: %s" % install_root)
    installed_python = assert_installed_python(install_root)
    output_root.mkdir(parents=True, exist_ok=True)

    os.environ["RASP5_DATA_HOME"] = str(output_root / "user-data")
    sys.path.insert(0, str(install_root))

    import app.bootstrap as bootstrap_module

    bootstrap = bootstrap_module.ApplicationBootstrap()
    bootstrap.inject_conda_dll_paths()
    bootstrap.inject_vendor_packages()

    from ete3 import Tree
    from application.services.biogeobears_analysis_service import BioGeoBEARSAnalysisService
    from application.services.dec_analysis_service import DECAnalysisService
    from application.services.diva_analysis_service import DivaAnalysisService
    from domain.models.sbgb_config import SBGBConfig
    from domain.models.sdec_config import SDECConfig
    from domain.models.sdiva_config import SDivaConfig, infer_sdiva_area_names
    from infrastructure.io.csv_matrix_reader import CsvMatrixReader
    from infrastructure.tree.tree_reader import TreeReader

    imported_bootstrap = assert_imported_from(bootstrap_module, install_root)
    data_dir = install_root / "data" / "benchmarks" / "psychotria"
    tree_path = data_dir / "Psychotria.tree"
    matrix_path = data_dir / "distribution.csv"
    for required_path in (tree_path, matrix_path):
        if not required_path.is_file():
            raise FileNotFoundError("Installed benchmark file is missing: %s" % required_path)

    tree_text = TreeReader().read_tree(str(tree_path))
    tree = Tree(tree_text, format=1)
    matrix = CsvMatrixReader().read(str(matrix_path))

    dec_service = DECAnalysisService(
        engine_path=install_root / "engines" / "lagrange-ng" / "lagrange-ng.exe",
        work_root=output_root / "dec",
    )
    area_names = infer_sdiva_area_names(matrix)
    root_age = estimate_root_age(tree)
    taxon_ranges = infer_taxon_ranges(matrix, area_names, dec_service)

    diva_config = SDivaConfig.default_for_areas(area_names)
    diva_config.threads = 2

    dec_config = SDECConfig.default_for_areas(area_names)
    dec_config.root_age = root_age
    dec_config.threads = 1

    bgb_config = SBGBConfig.default_for_areas(area_names, taxon_ranges)
    bgb_config.root_age = root_age
    bgb_config.cores = 1
    bgb_config.model_name = "DEC"

    diva_service = DivaAnalysisService(
        project_root=str(install_root),
        work_root=str(output_root / "diva"),
    )
    bgb_service = BioGeoBEARSAnalysisService(
        rscript_path=install_root / "engines" / "R" / "bin" / "Rscript.exe",
        wrapper_script_path=install_root / "engines" / "biogeobears" / "bgb_runner.R",
        work_root=output_root / "biogeobears",
        site_library_path=install_root / "engines" / "R" / "site-library",
    )

    records = []
    records.append(
        run_case(
            "DIVA",
            lambda: summarize_result(
                diva_service.run(
                    tree,
                    matrix,
                    tree_name="installed_smoke",
                    distribution_name="psychotria",
                    config=diva_config,
                    timeout_seconds=300,
                )
            ),
        )
    )
    records.append(
        run_case(
            "DEC",
            lambda: summarize_result(
                dec_service.analyze(
                    tree=tree,
                    matrix=matrix,
                    run_name="installed_smoke_dec",
                    scale_tree_to_root_age=True,
                    config=dec_config,
                )
            ),
        )
    )
    records.append(
        run_case(
            "BioGeoBEARS DEC",
            lambda: summarize_result(
                bgb_service.analyze(
                    tree=tree,
                    matrix=matrix,
                    config=bgb_config,
                    run_name="installed_smoke_bgb_dec",
                    scale_tree_to_root_age=True,
                )
            ),
        )
    )

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "install_root": str(install_root),
        "output_root": str(output_root),
        "python_executable": installed_python,
        "imported_bootstrap": imported_bootstrap,
        "area_names": list(area_names),
        "tasks": records,
    }
    report_path = output_root / "installed_release_smoke.json"
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    failed = [record for record in records if record["status"] != "ok"]
    print("REPORT %s" % report_path, flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
