import argparse
import csv
import hashlib
import json
from itertools import combinations
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bootstrap import ApplicationBootstrap

ApplicationBootstrap().inject_vendor_packages()

from ete3 import Tree

from application.services.biogeobears_analysis_service import BioGeoBEARSAnalysisService
from application.services.bsm_dispersal_network_service import BSMDispersalNetworkService
from domain.models.sbgb_config import SBGBConfig
from domain.models.state_matrix import StateMatrix
from infrastructure.io.csv_matrix_reader import CsvMatrixReader
from infrastructure.tree.tree_reader import TreeReader


SPEC_PATH = (
    PROJECT_ROOT
    / "data"
    / "benchmarks"
    / "dore_ponerinae"
    / "dore_bsm_1000_benchmark_spec.json"
)
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "runs" / "benchmarks" / "dore_bsm_1000"


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild or validate the Dore-derived paper-rule DEC+J "
            "BSM benchmark."
        )
    )
    parser.add_argument("--nummaps", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--maxnum-maps-to-try", type=int, default=None)
    parser.add_argument("--maxtries-per-branch", type=int, default=None)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument(
        "--reuse-fitted-run",
        default=None,
        help=(
            "Reuse the fitted result referenced by a completed Dore benchmark manifest."
        ),
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate inputs and generated BioGeoBEARS files without fitting or running BSM.",
    )
    return parser.parse_args()


def resolve_reusable_fit(value, spec_hash):
    source = Path(value).resolve()
    source_manifest = None
    if source.is_file() and source.name.lower() == "benchmark_manifest.json":
        source_manifest = json.loads(source.read_text(encoding="utf-8"))
        if source_manifest.get("status") != "completed":
            raise ValueError("Reusable benchmark manifest is not completed: %s" % source)
        if source_manifest.get("benchmark_id") != "dore_ponerinae_decj_bsm_1000":
            raise ValueError("Reusable benchmark manifest belongs to another benchmark.")
        if str(source_manifest.get("spec_sha256", "") or "").upper() != spec_hash.upper():
            raise ValueError("Reusable benchmark manifest was built from a different specification.")
        run_dir = Path(source_manifest["result"]["source_run_directory"])
        inputs_path = run_dir / "bsm" / "BSM_inputs_file.Rdata"
        output_json_path = run_dir / "bgb_result.json"
    else:
        raise ValueError(
            "--reuse-fitted-run must point to a completed Dore benchmark_manifest.json."
        )
    if not inputs_path.exists():
        raise FileNotFoundError("Reusable BSM inputs are missing: %s" % inputs_path)
    return {
        "inputs_path": inputs_path,
        "output_json_path": output_json_path,
        "source_manifest_path": source if source_manifest is not None else None,
        "source_manifest": source_manifest,
    }


def run_bsm_from_fitted_inputs(
    *,
    rscript,
    site_library,
    inputs_path,
    output_dir,
    nummaps,
    seed,
    maxnum_maps_to_try,
    maxtries_per_branch,
):
    helper = PROJECT_ROOT / "tools" / "rerun_bsm_from_inputs.R"
    if not helper.exists():
        raise FileNotFoundError("Missing reusable BSM helper: %s" % helper)
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(rscript),
        str(helper),
        "--lib",
        str(site_library),
        "--inputs",
        str(inputs_path),
        "--outdir",
        str(output_dir),
        "--nummaps",
        str(int(nummaps)),
        "--seed",
        str(int(seed)),
        "--maxnum-maps-to-try",
        str(int(maxnum_maps_to_try)),
        "--maxtries-per-branch",
        str(int(maxtries_per_branch)),
    ]
    stdout_path = output_dir / "bsm_stdout.log"
    stderr_path = output_dir / "bsm_stderr.log"
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        completed = subprocess.run(
            command,
            cwd=str(output_dir),
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
    if completed.returncode != 0:
        stderr_tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-8000:]
        stdout_tail = stdout_path.read_text(encoding="utf-8", errors="replace")[-8000:]
        raise RuntimeError(
            "Reusable BSM run failed with return code %s.\n%s\n%s"
            % (completed.returncode, stdout_tail, stderr_tail)
        )
    return {
        "helper": helper,
        "stdout": stdout_path,
        "stderr": stderr_path,
    }


def postprocess_bsm_source_areas(*, rscript, site_library, bsm_dir, seed):
    helper = PROJECT_ROOT / "tools" / "postprocess_bsm_source_areas.R"
    if not helper.exists():
        raise FileNotFoundError("Missing BSM source-area postprocessor: %s" % helper)
    command = [
        str(rscript),
        str(helper),
        "--lib",
        str(site_library),
        "--bsm-dir",
        str(bsm_dir),
        "--seed",
        str(int(seed)),
    ]
    stdout_path = Path(bsm_dir) / "source_assignment_stdout.log"
    stderr_path = Path(bsm_dir) / "source_assignment_stderr.log"
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        completed = subprocess.run(
            command,
            cwd=str(bsm_dir),
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
    if completed.returncode != 0:
        stderr_tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-8000:]
        stdout_tail = stdout_path.read_text(encoding="utf-8", errors="replace")[-8000:]
        raise RuntimeError(
            "BSM source-area postprocessing failed with return code %s.\n%s\n%s"
            % (completed.returncode, stdout_tail, stderr_tail)
        )
    return {
        "helper": helper,
        "stdout": stdout_path,
        "stderr": stderr_path,
        "reference_edges": Path(bsm_dir) / "bsm_dore_reference_edges.csv",
    }


def compare_network_to_reference(network_rows, reference_path, tolerance=1e-8):
    with Path(reference_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reference_rows = list(csv.DictReader(handle))
    keys = ("anagenetic_count", "founder_count", "total_count", "mean_per_map")
    observed = dict(
        ((str(row.get("source_area", "")), str(row.get("target_area", ""))), row)
        for row in list(network_rows or [])
    )
    expected = dict(
        ((str(row.get("source_area", "")), str(row.get("target_area", ""))), row)
        for row in reference_rows
    )
    mismatches = []
    max_abs_difference = 0.0
    for edge_key in sorted(set(observed) | set(expected)):
        observed_row = observed.get(edge_key, {})
        expected_row = expected.get(edge_key, {})
        for metric in keys:
            observed_value = float(observed_row.get(metric, 0.0) or 0.0)
            expected_value = float(expected_row.get(metric, 0.0) or 0.0)
            difference = abs(observed_value - expected_value)
            max_abs_difference = max(max_abs_difference, difference)
            if difference > tolerance:
                mismatches.append({
                    "source_area": edge_key[0],
                    "target_area": edge_key[1],
                    "metric": metric,
                    "observed": observed_value,
                    "expected": expected_value,
                    "absolute_difference": difference,
                })
    if mismatches:
        raise AssertionError(
            "RASP BSM network differs from BioGeoBEARS reference counts on %d values; "
            "maximum absolute difference %.12g."
            % (len(mismatches), max_abs_difference)
        )
    return {
        "reference_edge_count": len(expected),
        "observed_edge_count": len(observed),
        "mismatch_count": 0,
        "max_absolute_difference": max_abs_difference,
        "tolerance": tolerance,
    }


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest().upper()


def load_spec():
    with SPEC_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_input(spec, name):
    record = spec["inputs"][name]
    path = PROJECT_ROOT / record["path"]
    if not path.exists():
        raise FileNotFoundError("Missing benchmark input: %s" % path)
    actual_hash = sha256(path)
    expected_hash = str(record.get("sha256", "") or "").upper()
    if expected_hash and actual_hash != expected_hash:
        raise ValueError(
            "Benchmark input hash mismatch for %s: expected %s, got %s"
            % (name, expected_hash, actual_hash)
        )
    return path


def read_boundaries(path):
    values = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        if text:
            values.append(float(text))
    if not values or values != sorted(set(values)):
        raise ValueError("Time boundaries must be unique and sorted from young to old.")
    return values


def read_period_matrices(path, target_codes):
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    matrices = []
    index = 0
    while index < len(lines):
        header_text = lines[index].strip()
        index += 1
        if not header_text:
            continue
        if header_text.upper() == "END":
            break
        header = header_text.split()
        size = len(header)
        rows = []
        for _row in range(size):
            if index >= len(lines):
                raise ValueError("Adjacency matrix ended before all rows were read.")
            values = [float(value) for value in lines[index].strip().split()]
            index += 1
            if len(values) != size:
                raise ValueError("Adjacency matrix row width does not match its header.")
            rows.append(values)
        if set(header) != set(target_codes):
            raise ValueError(
                "Adjacency area codes (%s) do not match matrix areas (%s)."
                % (", ".join(header), ", ".join(target_codes))
            )
        positions = [header.index(code) for code in target_codes]
        matrices.append(
            [[rows[row][col] for col in positions] for row in positions]
        )
    if not matrices:
        raise ValueError("No adjacency matrices were read from %s" % path)
    return matrices


def encode_area_columns(matrix, area_code_mapping, taxon_aliases):
    source_columns = list(matrix.state_columns or [])
    missing = [name for name in source_columns if name not in area_code_mapping]
    if missing:
        raise ValueError(
            "No engine area code is defined for: %s" % ", ".join(missing)
        )
    codes = [str(area_code_mapping[name]).strip() for name in source_columns]
    if any(not code for code in codes) or len(set(codes)) != len(codes):
        raise ValueError("Engine area codes must be non-empty and unique.")
    if any(len(code) != 1 or code == "_" for code in codes):
        raise ValueError("BioGeoBEARS engine area codes must be unique single characters.")

    rows = []
    encoded_names = []
    for source_row in list(matrix.rows or []):
        source_name = str(source_row.get("Name", "") or "").strip()
        taxon_name = str(taxon_aliases.get(source_name, source_name)).strip()
        row = {
            "ID": source_row.get("ID", ""),
            "Name": taxon_name,
        }
        for area_name, code in zip(source_columns, codes):
            row[code] = source_row.get(area_name, "")
        rows.append(row)
        encoded_names.append(taxon_name)

    if len(set(encoded_names)) != len(encoded_names):
        raise ValueError("Taxon aliases produce duplicate matrix names.")

    return StateMatrix(
        ids=list(matrix.ids or []),
        taxa_names=encoded_names,
        state_columns=codes,
        rows=rows,
        source_path=matrix.source_path,
    )


def taxon_ranges(matrix):
    values = []
    for row in list(matrix.rows or []):
        state = "".join(
            column
            for column in matrix.state_columns
            if str(row.get(column, "")).strip() == "1"
        )
        if state:
            values.append(state)
    return values


def dore_allowed_ranges_by_period(area_codes, max_range_size, include_null_range, period_matrices):
    codes = [str(value) for value in list(area_codes or [])]
    labels = ["_"] if include_null_range else []
    for size in range(1, min(int(max_range_size), len(codes)) + 1):
        labels.extend("".join(combo) for combo in combinations(codes, size))

    output = []
    for matrix in list(period_matrices or []):
        allowed_pairs = set()
        for left in range(len(codes) - 1):
            for right in range(left + 1, len(codes)):
                if float(matrix[left][right]) != 0.0:
                    allowed_pairs.add(codes[left] + codes[right])
        valid = set(["_"] if include_null_range else [])
        valid.update(codes)
        valid.update(allowed_pairs)
        for label in labels:
            if len(label) <= 2:
                continue
            focal = list(label)
            covered = set()
            for left, right in combinations(focal, 2):
                pair = "".join(code for code in codes if code in set([left, right]))
                if pair in allowed_pairs:
                    covered.update([left, right])
            if all(code in covered for code in focal):
                valid.add(label)
        output.append([label for label in labels if label in valid])
    return output


def git_value(*args):
    try:
        return subprocess.check_output(
            ["git"] + list(args),
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        ).strip()
    except Exception:
        return ""


def command_capture(command):
    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        return {
            "exit_code": int(completed.returncode),
            "stdout": str(completed.stdout or "").strip(),
            "stderr": str(completed.stderr or "").strip(),
        }
    except Exception as exc:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": "unavailable: %s" % exc,
        }


def runtime_metadata(rscript, site_library, wrapper):
    expression = ".libPaths(c(%s, .libPaths())); cat(as.character(packageVersion('BioGeoBEARS')))" % json.dumps(
        str(site_library).replace("\\", "/")
    )
    rscript_version = command_capture([str(rscript), "--version"])
    biogeobears_version = command_capture([str(rscript), "-e", expression])
    return {
        "python": sys.version.replace("\n", " "),
        "git_head": git_value("rev-parse", "HEAD"),
        "git_status_porcelain": git_value("status", "--porcelain"),
        "rscript": (
            rscript_version["stdout"]
            or rscript_version["stderr"]
        ),
        "biogeobears_version": biogeobears_version["stdout"],
        "biogeobears_version_warnings": biogeobears_version["stderr"],
        "bgb_runner": {
            "path": str(wrapper),
            "size": wrapper.stat().st_size,
            "sha256": sha256(wrapper),
        },
    }


def input_metadata(paths):
    return {
        name: {
            "path": str(path),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        }
        for name, path in paths.items()
    }


def result_file_metadata(paths):
    records = []
    for path in paths:
        path = Path(path)
        if path.exists() and path.is_file():
            records.append(
                {
                    "path": str(path),
                    "size": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    return records


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def payload_fingerprint(payload):
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest().upper()


def build_config(spec, matrix, boundaries, period_matrices):
    analysis = spec["analysis"]
    area_names = list(matrix.state_columns or [])
    config = SBGBConfig.default_for_areas(area_names, taxon_ranges(matrix))
    config.model_name = str(analysis["model_name"])
    config.max_areas = int(analysis["max_range_size"])
    config.include_null_range = bool(analysis["include_null_range"])
    config.null_range_mode = "include" if config.include_null_range else "exclude"
    config.cores = int(analysis["cores"])
    config.period_times = [0.0] + list(boundaries)
    config.time_matrix_kind = str(analysis["time_matrix_kind"])
    config.period_matrices = list(period_matrices)
    config.root_age = ""
    config.refresh_range_lists()
    config.validate()
    over_limit = [
        value
        for value in config.runtime_include_ranges()
        if value != "_" and len(value) > config.max_areas
    ]
    if over_limit:
        raise ValueError(
            "Generated include ranges exceed max_range_size=%s: %s"
            % (config.max_areas, ", ".join(over_limit[:10]))
        )
    return config


def build_run_files(service, tree, matrix, config, run_name):
    values = config.engine_kwargs()
    return service.build_run_files(
        tree=tree,
        matrix=matrix,
        run_name=run_name,
        model_name=values["model_name"],
        max_range_size=values["max_range_size"],
        include_null_range=values["include_null_range"],
        null_range_mode=values["null_range_mode"],
        cores=values["cores"],
        include_ranges=values["include_ranges"],
        exclude_ranges=values["exclude_ranges"],
        period_times=values["period_times"],
        time_matrix_kind=values["time_matrix_kind"],
        period_matrices=values["period_matrices"],
        root_age=values["root_age"],
        scale_tree_to_root_age=False,
    )


def main():
    args = parse_args()
    spec = load_spec()
    analysis = spec["analysis"]
    nummaps = int(args.nummaps if args.nummaps is not None else analysis["bsm_nummaps"])
    seed = int(args.seed if args.seed is not None else analysis["bsm_seed"])
    maxnum_maps_to_try = int(
        args.maxnum_maps_to_try
        if args.maxnum_maps_to_try is not None
        else analysis["bsm_maxnum_maps_to_try"]
    )
    maxtries = int(
        args.maxtries_per_branch
        if args.maxtries_per_branch is not None
        else analysis["bsm_maxtries_per_branch"]
    )
    if nummaps < 1 or maxnum_maps_to_try < 1 or maxtries < 1:
        raise ValueError(
            "nummaps, maxnum-maps-to-try, and maxtries-per-branch must be positive."
        )
    j_start = float(analysis["j_start"])
    if abs(j_start - 0.0001) > 1e-12:
        raise ValueError(
            "The bundled BioGeoBEARS nested +J workflow currently fixes j_start at "
            "0.0001; the benchmark specification must record that invariant."
        )

    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    spec_hash = sha256(SPEC_PATH)
    fingerprint_payload = {
        "benchmark_id": spec["benchmark_id"],
        "spec_sha256": spec_hash,
        "validate_only": bool(args.validate_only),
        "nummaps": nummaps,
        "seed": seed,
        "maxnum_maps_to_try": maxnum_maps_to_try,
        "maxtries_per_branch": maxtries,
        "reuse_fitted_run": str(args.reuse_fitted_run or ""),
    }
    fingerprint = payload_fingerprint(fingerprint_payload)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    mode = "validate" if args.validate_only else "run"
    execution_id = "%s_%s_%s" % (mode, timestamp, fingerprint[:12].lower())
    execution_root = output_root / execution_id
    execution_root.mkdir(parents=True, exist_ok=False)
    manifest_path = execution_root / "benchmark_manifest.json"
    started = time.perf_counter()
    manifest = {
        "benchmark_id": spec["benchmark_id"],
        "benchmark_scope": spec["asset_status"],
        "execution_id": execution_id,
        "execution_root": str(execution_root),
        "parameter_fingerprint_sha256": fingerprint,
        "spec_path": str(SPEC_PATH),
        "spec_sha256": spec_hash,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "status": "running",
        "validate_only": bool(args.validate_only),
        "parameters": {
            "model_name": analysis["model_name"],
            "max_range_size": analysis["max_range_size"],
            "include_null_range": analysis["include_null_range"],
            "cores": analysis["cores"],
            "time_matrix_kind": analysis["time_matrix_kind"],
            "period_boundaries_ma": analysis["period_boundaries_ma"],
            "j_start": j_start,
            "j_start_source": "bundled bgb_runner nested +J invariant",
            "bsm_nummaps": nummaps,
            "bsm_seed": seed,
            "bsm_maxnum_maps_to_try": maxnum_maps_to_try,
            "bsm_maxtries_per_branch": maxtries,
        },
        "paper_to_rasp_mapping_note": spec["rasp_mapping_note"],
    }
    write_json(manifest_path, manifest)

    try:
        paths = {
            name: resolve_input(spec, name)
            for name in ["tree", "range_matrix", "time_boundaries", "areas_adjacency"]
        }
        rscript = PROJECT_ROOT / "engines" / "R" / "bin" / "Rscript.exe"
        wrapper = PROJECT_ROOT / "engines" / "biogeobears" / "bgb_runner.R"
        site_library = PROJECT_ROOT / "engines" / "R" / "site-library"
        for required in [rscript, wrapper, site_library]:
            if not required.exists():
                raise FileNotFoundError("Missing bundled engine asset: %s" % required)

        reusable_fit = None
        if args.reuse_fitted_run:
            if args.validate_only:
                raise ValueError("--validate-only and --reuse-fitted-run cannot be combined.")
            reusable_fit = resolve_reusable_fit(args.reuse_fitted_run, spec_hash)

        tree_text = TreeReader().read_tree(str(paths["tree"]))
        tree = Tree(tree_text, format=1)
        source_matrix = CsvMatrixReader().read(str(paths["range_matrix"]))
        area_code_mapping = dict(spec["area_code_mapping"])
        taxon_aliases = dict(spec.get("matrix_taxon_aliases", {}) or {})
        matrix = encode_area_columns(
            source_matrix,
            area_code_mapping,
            taxon_aliases,
        )
        boundaries = read_boundaries(paths["time_boundaries"])
        area_codes = list(matrix.state_columns)
        period_matrices = read_period_matrices(paths["areas_adjacency"], area_codes)
        if len(period_matrices) != len(boundaries):
            raise ValueError(
                "Expected one adjacency matrix per period boundary: %s matrices, %s boundaries."
                % (len(period_matrices), len(boundaries))
            )
        if len(tree) != len(matrix.rows):
            raise ValueError(
                "Tree/matrix taxon counts differ: %s tips versus %s rows."
                % (len(tree), len(matrix.rows))
            )

        config = build_config(spec, matrix, boundaries, period_matrices)
        service = BioGeoBEARSAnalysisService(
            rscript_path=rscript,
            wrapper_script_path=wrapper,
            work_root=execution_root,
            site_library_path=site_library,
        )
        run_name = "dore_decj_bsm_%s" % nummaps
        prepared = build_run_files(service, tree, matrix, config, run_name)
        allowed_ranges_by_period = dore_allowed_ranges_by_period(
            area_codes,
            analysis["max_range_size"],
            analysis["include_null_range"],
            period_matrices,
        )
        areas_payload = json.loads(prepared.areas_json_path.read_text(encoding="utf-8"))
        areas_payload["allowed_ranges_by_period"] = allowed_ranges_by_period
        areas_payload["allowed_ranges_source"] = "Dore et al. manual adjacency-derived state rule"
        areas_payload["period_state_lists_only"] = True
        prepared.areas_json_path.write_text(
            json.dumps(areas_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        manifest["inputs"] = input_metadata(paths)
        manifest["runtime"] = runtime_metadata(rscript, site_library, wrapper)
        manifest["validated"] = {
            "tree_tip_count": len(tree),
            "matrix_row_count": len(matrix.rows),
            "area_display_names": list(source_matrix.state_columns),
            "area_code_mapping": area_code_mapping,
            "area_codes": area_codes,
            "matrix_taxon_aliases": taxon_aliases,
            "period_count": len(period_matrices),
            "paper_allowed_state_counts": [len(values) for values in allowed_ranges_by_period],
            "period_state_lists_only": bool(areas_payload.get("period_state_lists_only")),
            "runtime_include_range_count": len(config.runtime_include_ranges()),
            "runtime_max_include_range_size": max(
                len(value)
                for value in config.runtime_include_ranges()
                if value != "_"
            ),
            "observed_max_tip_range_size": max(
                sum(str(row.get(column, "")).strip() == "1" for column in matrix.state_columns)
                for row in matrix.rows
            ),
            "generated_workdir": str(prepared.workdir),
            "generated_files": result_file_metadata(
                [
                    prepared.tree_path,
                    prepared.geog_path,
                    prepared.areas_json_path,
                    prepared.timeperiods_path,
                    prepared.period_matrix_path,
                ]
            ),
        }

        if args.validate_only:
            manifest["status"] = "validated"
        else:
            bsm_dir = prepared.workdir / "bsm"
            if reusable_fit is None:
                service.runner.run(
                    prepared,
                    bsm_outdir=bsm_dir,
                    bsm_nummaps=nummaps,
                    bsm_seed=seed,
                    bsm_maxnum_maps_to_try=maxnum_maps_to_try,
                    bsm_maxtries_per_branch=maxtries,
                )
                source_output_json_path = prepared.output_json_path
            else:
                reuse_outputs = run_bsm_from_fitted_inputs(
                    rscript=rscript,
                    site_library=site_library,
                    inputs_path=reusable_fit["inputs_path"],
                    output_dir=bsm_dir,
                    nummaps=nummaps,
                    seed=seed,
                    maxnum_maps_to_try=maxnum_maps_to_try,
                    maxtries_per_branch=maxtries,
                )
                source_output_json_path = reusable_fit["output_json_path"]
                manifest["reused_fit"] = {
                    "source_manifest_path": str(reusable_fit["source_manifest_path"] or ""),
                    "source_bsm_inputs": {
                        "path": str(reusable_fit["inputs_path"]),
                        "size": reusable_fit["inputs_path"].stat().st_size,
                        "sha256": sha256(reusable_fit["inputs_path"]),
                    },
                    "helper": {
                        "path": str(reuse_outputs["helper"]),
                        "size": reuse_outputs["helper"].stat().st_size,
                        "sha256": sha256(reuse_outputs["helper"]),
                    },
                }
            source_assignment_outputs = postprocess_bsm_source_areas(
                rscript=rscript,
                site_library=site_library,
                bsm_dir=bsm_dir,
                seed=seed,
            )
            manifest["source_assignment"] = {
                "method": "biogeobears_probabilistic_unique_source",
                "seed": seed,
                "helper": {
                    "path": str(source_assignment_outputs["helper"]),
                    "size": source_assignment_outputs["helper"].stat().st_size,
                    "sha256": sha256(source_assignment_outputs["helper"]),
                },
            }
            result = service._load_existing_bsm_lightweight(
                output_json_path=source_output_json_path,
                bsm_dir=bsm_dir,
                source_path=source_output_json_path.parent,
            )
            network_service = BSMDispersalNetworkService()
            network = network_service.build_network(
                result,
                range_matrix=matrix,
                min_mean_per_map=0.0,
            )
            reference_comparison = compare_network_to_reference(
                network.get("edge_rows", []) or [],
                source_assignment_outputs["reference_edges"],
            )
            edge_path = execution_root / "bsm_network_edges.csv"
            node_path = execution_root / "bsm_network_nodes.csv"
            display_path = execution_root / "bsm_network_edges_all.csv"
            network_service.write_edges_csv(network, edge_path)
            network_service.write_nodes_csv(network, node_path)
            network_service.write_display_edges_csv(network, display_path)
            source_dir = Path(str(getattr(result, "source_run_directory", "") or ""))
            bsm_dir = Path(str((getattr(result, "summary", {}) or {}).get("directory", "") or ""))
            manifest["result"] = {
                "source_run_directory": str(source_dir),
                "bsm_directory": str(bsm_dir),
                "parsed_event_count": int((getattr(result, "summary", {}) or {}).get("normalized_event_count", 0) or 0),
                "preview_event_count": len(getattr(result, "events", []) or []),
                "events_complete": bool(getattr(result, "events_complete", False)),
                "raw_table_rows": dict(getattr(result, "event_row_counts", {}) or {}),
                "network_edge_count": len(network.get("edge_rows", []) or []),
                "network_node_count": len(network.get("node_rows", []) or []),
                "network_source_assignment_method": network.get("source_assignment_method", ""),
                "source_assignment_warning_count": int(
                    (getattr(result, "summary", {}) or {}).get("source_assignment_warning_count", 0) or 0
                ),
                "biogeobears_reference_comparison": reference_comparison,
                "key_files": result_file_metadata(
                    [
                        source_output_json_path,
                        bsm_dir / "bsm_ana_events.csv",
                        bsm_dir / "bsm_clado_events.csv",
                        bsm_dir / "bsm_summary.json",
                        bsm_dir / "bsm_source_assigned_dispersal_events.csv",
                        bsm_dir / "bsm_dore_reference_edges.csv",
                        source_assignment_outputs["stdout"],
                        source_assignment_outputs["stderr"],
                        edge_path,
                        node_path,
                    ]
                ),
            }
            manifest["status"] = "completed"
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        manifest["traceback"] = traceback.format_exc()
        raise
    finally:
        manifest["finished_at"] = datetime.now().isoformat(timespec="seconds")
        manifest["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        write_json(manifest_path, manifest)
        print("Dore BSM benchmark %s: %s" % (manifest["status"], manifest_path))


if __name__ == "__main__":
    main()
