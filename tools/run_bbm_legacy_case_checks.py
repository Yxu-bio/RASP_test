# -*- coding: utf-8 -*-
import argparse
import copy
import hashlib
import itertools
import json
import math
import platform
import re
import struct
import subprocess
import sys
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bootstrap import ApplicationBootstrap

ApplicationBootstrap().inject_vendor_packages()

from ete3 import Tree

from application.services.bbm_dataset_builder import BBMDatasetBuilder
from domain.models.bbm_config import BBMConfig
from infrastructure.io.csv_matrix_reader import CsvMatrixReader
from infrastructure.mrbayes.bbm_output_parser import BBMOutputParser
from infrastructure.tree.tree_reader import TreeReader


DATA_ROOT = PROJECT_ROOT / "data" / "benchmarks" / "psychotria"
CURRENT_ENGINE = PROJECT_ROOT / "engines" / "mrbayes" / "mb.3.2.7-win32.exe"
LEGACY_CONFIG_SOURCE = PROJECT_ROOT / "_reference_RASP" / "Codes" / "Config_BBM.vb"
LEGACY_PARSER_SOURCE = PROJECT_ROOT / "_reference_RASP" / "Codes" / "Module_BBM.vb"
LEGACY_RESULT_SOURCE = PROJECT_ROOT / "_reference_RASP" / "Codes" / "Form_Main.vb"
RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
RUN_ROOT = PROJECT_ROOT / "runs" / "bbm_legacy_case" / RUN_STAMP
REPORT_PATH = RUN_ROOT / "report.json"
LATEST_PATH = PROJECT_ROOT / "docs" / "bbm_legacy_case_latest.md"
SEED = 13579
SWAP_SEED = 24681
RAW_TOLERANCE = 1e-10
LEGACY_MARGINAL_TOLERANCE = 2e-6
LEGACY_STATE_TOLERANCE = 1e-3
EXPECTED_CHAIN10_WARNING = (
    "WARNING: Allocation of zero size attempted. This is probably a bug; "
    "problems may follow."
)


class BBMLegacyCheckFailure(AssertionError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def git_output(*args):
    try:
        return subprocess.check_output(
            ["git"] + list(args),
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.STDOUT,
        ).decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def format_float(value):
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return "%.12g" % number


def load_inputs():
    tree_text = TreeReader().read_tree(str(DATA_ROOT / "Psychotria.tree"))
    tree = Tree(tree_text, format=1)
    matrix = CsvMatrixReader().read(str(DATA_ROOT / "distribution.csv"))
    return tree, matrix


def legacy_node_records(tree, taxon_id_map):
    records = []
    taxon_count = len(list(tree.get_leaf_names()))
    node_index = 0
    for node in tree.traverse("postorder"):
        if node.is_leaf():
            continue
        node_index += 1
        leaf_names = [str(leaf.name or "").strip() for leaf in node.iter_leaves()]
        leaf_ids = [str(taxon_id_map[name]) for name in leaf_names]
        records.append({
            "node_index": node_index,
            "display_node_id": str(taxon_count + node_index),
            "leaf_names": leaf_names,
            "leaf_ids": leaf_ids,
            "clade_key": "|".join(sorted(leaf_names)),
        })
    return records


def root_bits(config, area_names):
    mode = str(config.root_distribution or "NULL").upper()
    if mode == "WIDE":
        return "1" * len(area_names)
    if mode == "CUSTOM":
        custom = str(config.custom_root_distribution or "").upper()
        return "".join("1" if area in custom else "0" for area in area_names)
    return "0" * len(area_names)


def expected_commands(config, records, selected_node_ids, taxon_count, label_constraints):
    selected = set(str(value) for value in selected_node_ids)
    commands = ["outgroup %s;" % (taxon_count + 2)]
    commands.append("lset nst=1 rates=equal;")
    if config.state_frequency_model == "F81":
        commands.append(
            "prset statefreqpr=dirichlet(%s,%s);"
            % (format_float(config.dirichlet_alpha), format_float(config.dirichlet_beta))
        )
    if config.rate_variation_model == "GAMMA":
        commands.append("lset nst=1 rates=gamma;")
        commands.append(
            "prset Shapepr=Uniform(%s,%s);"
            % (format_float(config.gamma_min), format_float(config.gamma_max))
        )

    constraint_names = []
    for record in records:
        if str(record["display_node_id"]) not in selected:
            continue
        name = "c%s" % record["node_index"]
        constraint_names.append(name)
        taxa = list(record["leaf_ids"])
        if label_constraints:
            taxa = ["TID%s" % value for value in taxa]
        commands.append("constraint %s -1 = %s;" % (name, " ".join(taxa)))
    commands.append("prset topologypr=constraints(%s);" % ",".join(constraint_names))
    commands.extend([
        "lset coding=variable;",
        "set autoclose=yes nowarn=yes;",
        "report ancstates=yes;",
        (
            "mcmc printfreq=1000 diagnfreq=1000 Ordertaxa=Yes "
            "Samplefreq=%s ngen=%s nchains=%s Temp=%s;"
        ) % (
            int(config.sample_frequency),
            int(config.chain_length),
            int(config.chains),
            format_float(config.temperature),
        ),
        "[burnin=%s,taxonnum=%s,node_num=%s]" % (
            int(config.discard_samples),
            len(config.area_names),
            len(records),
        ),
    ])
    return commands


def expected_matrix(rows, config, area_names):
    values = [("TID%s" % row_id, bits) for _taxon, bits, row_id in rows]
    bits = root_bits(config, area_names)
    if bool(config.large_dataset_mode):
        values.append(("OG0", bits))
    values.extend([("OG1", bits), ("OG2", bits)])
    return values


def write_legacy_nexus(path, rows, area_names, records, selected_node_ids, config):
    matrix = expected_matrix(rows, config, area_names)
    commands = expected_commands(
        config,
        records,
        selected_node_ids,
        len(rows),
        label_constraints=False,
    )
    lines = [
        "#NEXUS",
        "Begin data;",
        "Dimensions ntax=%s nchar=%s;" % (len(matrix), len(area_names)),
        "Format datatype=restriction;",
        "Matrix",
    ]
    lines.extend("%s    %s" % item for item in matrix)
    lines.extend([";", "End;", "begin mrbayes;"])
    lines.extend(commands)
    lines.append("End;")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"matrix": matrix, "commands": commands}


def parse_nexus_contract(path):
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    matrix = []
    commands = []
    dimensions = None
    in_matrix = False
    in_mrbayes = False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith("dimensions "):
            dimensions = line
        if line.lower() == "matrix":
            in_matrix = True
            continue
        if in_matrix:
            if line == ";":
                in_matrix = False
                continue
            parts = line.split()
            if len(parts) >= 2:
                matrix.append((parts[0], parts[1]))
            continue
        if line.lower() == "begin mrbayes;":
            in_mrbayes = True
            continue
        if in_mrbayes:
            if line.lower() == "end;":
                in_mrbayes = False
                continue
            commands.append(line)
    return {"dimensions": dimensions, "matrix": matrix, "commands": commands}


def assert_contract(name, run_files, rows, legacy_records):
    actual = parse_nexus_contract(run_files.nexus_path)
    expected = {
        "matrix": expected_matrix(rows, run_files.config, run_files.area_names),
        "commands": expected_commands(
            run_files.config,
            legacy_records,
            run_files.selected_node_ids,
            len(rows),
            label_constraints=True,
        ),
    }
    expected_dimension = "Dimensions ntax=%s nchar=%s;" % (
        len(expected["matrix"]),
        len(run_files.area_names),
    )
    if actual["dimensions"] != expected_dimension:
        raise BBMLegacyCheckFailure(
            "%s dimensions differ: %r != %r"
            % (name, actual["dimensions"], expected_dimension)
        )
    if actual["matrix"] != expected["matrix"]:
        raise BBMLegacyCheckFailure("%s matrix differs from the legacy contract" % name)
    if actual["commands"] != expected["commands"]:
        raise BBMLegacyCheckFailure(
            "%s MrBayes commands differ from the legacy contract\nactual=%s\nexpected=%s"
            % (
                name,
                json.dumps(actual["commands"], ensure_ascii=False),
                json.dumps(expected["commands"], ensure_ascii=False),
            )
        )
    return {
        "name": name,
        "nexus_path": str(run_files.nexus_path),
        "nexus_sha256": sha256(run_files.nexus_path),
        "taxon_count": len(rows),
        "area_count": len(run_files.area_names),
        "matrix_row_count": len(actual["matrix"]),
        "constraint_count": len([
            line for line in actual["commands"] if line.lower().startswith("constraint ")
        ]),
        "add_og0": bool(run_files.config.large_dataset_mode),
        "state_frequency_model": run_files.config.state_frequency_model,
        "rate_variation_model": run_files.config.rate_variation_model,
        "root_distribution": run_files.config.root_distribution,
        "include_null_range": bool(run_files.config.include_null_range),
        "max_areas": int(run_files.config.max_areas),
        "contract_matches": True,
    }


def inject_seed(text):
    lines = str(text).splitlines()
    seed_line = "set seed=%s swapseed=%s;" % (SEED, SWAP_SEED)
    for index, line in enumerate(lines):
        if line.strip().lower().startswith("mcmc "):
            lines.insert(index, seed_line)
            return "\n".join(lines) + "\n"
    raise BBMLegacyCheckFailure("Could not insert the deterministic MrBayes seed")


def run_nexus(executable, nexus_path):
    seed_prelude = Path(nexus_path).parent / "seed_prelude.nex"
    seed_prelude.write_text(
        "#NEXUS\nbegin mrbayes;\nset seed=%s swapseed=%s;\nend;\n"
        % (SEED, SWAP_SEED),
        encoding="utf-8",
    )
    started = time.time()
    proc = subprocess.run(
        [str(executable), seed_prelude.name, Path(nexus_path).name],
        cwd=str(Path(nexus_path).parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        input="\n",
    )
    elapsed = time.time() - started
    stdout_path = Path(nexus_path).with_suffix(Path(nexus_path).suffix + ".stdout.log")
    stderr_path = Path(nexus_path).with_suffix(Path(nexus_path).suffix + ".stderr.log")
    stdout_path.write_text(proc.stdout or "", encoding="utf-8", errors="replace")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise BBMLegacyCheckFailure(
            "MrBayes failed for %s: %s"
            % (nexus_path, (proc.stderr or proc.stdout or "").strip())
        )
    outputs = {
        "run1": Path(str(nexus_path) + ".run1.p"),
        "run2": Path(str(nexus_path) + ".run2.p"),
        "mcmc": Path(str(nexus_path) + ".mcmc"),
    }
    missing = [str(path) for path in outputs.values() if not path.exists()]
    if missing:
        raise BBMLegacyCheckFailure("MrBayes outputs are missing: %s" % ", ".join(missing))
    warning_lines = []
    for line in (proc.stdout or "").splitlines() + (proc.stderr or "").splitlines():
        if "WARNING:" in line.upper():
            warning_lines.append(line.strip())
    return {
        "elapsed_seconds": elapsed,
        "returncode": proc.returncode,
        "warnings": warning_lines,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "outputs": dict((key, str(value)) for key, value in outputs.items()),
        "output_sha256": dict((key, sha256(value)) for key, value in outputs.items()),
    }


def find_header_index(lines):
    for index, line in enumerate(lines):
        parts = line.split("\t")
        if parts and parts[0].strip().lower() in ("gen", "generation", "state"):
            return index
    raise BBMLegacyCheckFailure("Could not find a MrBayes .p header")


def as_single(value):
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def f6_single(value):
    return as_single(float("%.6f" % float(value)))


def read_probability_table(path, run_files):
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    header_index = find_header_index(lines)
    header = lines[header_index].split("\t")
    data_lines = []
    generations = []
    for line in lines[header_index + 1:]:
        if not line.strip() or line.lstrip().startswith("["):
            continue
        parts = line.split("\t")
        try:
            generation = float(parts[0])
        except Exception:
            continue
        if not generation.is_integer():
            raise BBMLegacyCheckFailure(
                "Non-integer generation in %s: %s" % (path, parts[0])
            )
        generations.append(int(generation))
        data_lines.append(parts)

    expected_generations = list(range(
        0,
        int(run_files.config.chain_length) + 1,
        int(run_files.config.sample_frequency),
    ))
    if generations != expected_generations:
        raise BBMLegacyCheckFailure(
            "Sample generations in %s are incomplete or non-sequential: expected %s, found %s"
            % (path, expected_generations, generations)
        )

    # Module_BBM.vb reads burnin + 1 rows and starts with the following row.
    discarded_row_count = int(run_files.config.discard_samples) + 1
    kept = data_lines[discarded_row_count:]
    if not kept:
        raise BBMLegacyCheckFailure("No samples remain after the legacy discard rule")

    with_g = 0
    if len(header) > 2 and header[2].strip().lower() == "lnpr":
        with_g += 1
    alpha_index = 5 + with_g
    if len(header) > alpha_index and header[alpha_index].strip().lower() == "alpha":
        with_g += 1
    base = 5 + with_g

    stats = {
        "raw_sample_rows": len(data_lines),
        "expected_sample_rows": len(expected_generations),
        "discarded_sample_rows": discarded_row_count,
        "retained_sample_rows": len(kept),
        "expected_retained_sample_rows": len(expected_generations) - discarded_row_count,
        "first_generation": generations[0],
        "last_generation": generations[-1],
        "with_g_offset": with_g,
        "header_column_count": len(header),
    }
    if stats["retained_sample_rows"] != stats["expected_retained_sample_rows"]:
        raise BBMLegacyCheckFailure("Retained BBM sample count does not match the configured run")
    return header, kept, base, stats


def selected_records(run_files):
    selected_ids = set(str(value) for value in run_files.selected_node_ids)
    return [
        record
        for record in run_files.node_records
        if str(record["display_node_id"]) in selected_ids
    ]


def read_raw_probabilities(path, run_files):
    _header, kept, base, stats = read_probability_table(path, run_files)
    records = selected_records(run_files)
    area_count = len(run_files.area_names)
    values = {}
    for selected_index, record in enumerate(records):
        sums = [[0.0, 0.0] for _ in range(area_count)]
        for row_index, parts in enumerate(kept):
            for area_index in range(area_count):
                offset = selected_index * area_count * 2 + area_index * 2
                for state_index, column_index in enumerate([base + offset, base + offset + 1]):
                    if column_index >= len(parts):
                        raise BBMLegacyCheckFailure(
                            "Missing probability column %s at retained row %s in %s"
                            % (column_index, row_index + 1, path)
                        )
                    try:
                        sums[area_index][state_index] += float(parts[column_index])
                    except Exception as exc:
                        raise BBMLegacyCheckFailure(
                            "Invalid probability at retained row %s, column %s in %s"
                            % (row_index + 1, column_index, path)
                        ) from exc
        values[str(record["display_node_id"])] = [
            (pair[0] / len(kept), pair[1] / len(kept))
            for pair in sums
        ]
    return values, stats


def legacy_read_probabilities(path, run_files):
    _header, kept, base, stats = read_probability_table(path, run_files)

    records = selected_records(run_files)
    area_count = len(run_files.area_names)
    values = {}
    for selected_index, record in enumerate(records):
        sums = [[0.0, 0.0] for _ in range(area_count)]
        counts = [[0, 0] for _ in range(area_count)]
        for row_index, parts in enumerate(kept):
            for area_index in range(area_count):
                offset = selected_index * area_count * 2 + area_index * 2
                indexes = [base + offset, base + offset + 1]
                for state_index, column_index in enumerate(indexes):
                    if column_index >= len(parts):
                        raise BBMLegacyCheckFailure(
                            "Missing legacy probability column %s at retained row %s in %s"
                            % (column_index, row_index + 1, path)
                        )
                    try:
                        value = float(parts[column_index])
                    except Exception as exc:
                        raise BBMLegacyCheckFailure(
                            "Invalid legacy probability at retained row %s, column %s in %s"
                            % (row_index + 1, column_index, path)
                        ) from exc
                    sums[area_index][state_index] = as_single(
                        sums[area_index][state_index] + value
                    )
                    counts[area_index][state_index] += 1
        values[str(record["display_node_id"])] = [
            (
                f6_single(sums[index][0] / counts[index][0]),
                f6_single(sums[index][1] / counts[index][1]),
            )
            for index in range(area_count)
        ]
    return values, stats


def combine_raw_runs(run1, run2):
    result = {}
    for node_id in sorted(set(run1) | set(run2), key=display_sort_key):
        result[node_id] = [
            ((a0 + b0) / 2.0, (a1 + b1) / 2.0)
            for (a0, a1), (b0, b1) in zip(run1[node_id], run2[node_id])
        ]
    return result


def combine_legacy_runs(run1, run2):
    result = {}
    for node_id in sorted(set(run1) | set(run2), key=display_sort_key):
        result[node_id] = []
        for (a0, a1), (b0, b1) in zip(run1[node_id], run2[node_id]):
            result[node_id].append((
                f6_single(as_single(a0 + b0) / 2.0),
                f6_single(as_single(a1 + b1) / 2.0),
            ))
    return result


def raw_range_probabilities(area_probabilities, config, area_names):
    raw = []
    max_areas = min(int(config.max_areas), len(area_names))
    for size in range(1, max_areas + 1):
        for combo in itertools.combinations(range(len(area_names)), size):
            selected = set(combo)
            probability = 1.0
            labels = []
            for index, area in enumerate(area_names):
                p0, p1 = area_probabilities[index]
                if index in selected:
                    probability *= p1
                    labels.append(str(area))
                else:
                    probability *= p0
            raw.append(("".join(labels), probability))
    if bool(config.include_null_range):
        probability = 1.0
        for p0, _p1 in area_probabilities:
            probability *= p0
        raw.append(("/", probability))
    total = sum(value for _label, value in raw)
    if total <= 0:
        return OrderedDict()
    return OrderedDict(
        (label, value * 100.0 / total)
        for label, value in sorted(raw, key=lambda item: (-item[1], item[0]))
    )


def legacy_range_probabilities(area_probabilities, config, area_names):
    raw = []
    max_areas = min(int(config.max_areas), len(area_names))
    for size in range(1, max_areas + 1):
        for combo in itertools.combinations(range(len(area_names)), size):
            chosen = set(combo)
            probability = as_single(1.0)
            labels = []
            for index, area in enumerate(area_names):
                p0, p1 = area_probabilities[index]
                probability = as_single(probability * (p1 if index in chosen else p0))
                if index in chosen:
                    labels.append(str(area))
            raw.append(("".join(labels), probability))
    if bool(config.include_null_range):
        probability = as_single(1.0)
        for p0, _p1 in area_probabilities:
            probability = as_single(probability * p0)
        raw.append(("/", probability))
    total = as_single(0.0)
    for _label, value in raw:
        total = as_single(total + value)
    if total <= 0:
        return OrderedDict()
    return OrderedDict(
        (label, float(value) * 100.0 / float(total))
        for label, value in sorted(raw, key=lambda item: (-item[1], item[0]))
    )


def display_sort_key(value):
    try:
        return (0, int(value))
    except Exception:
        return (1, str(value))


def max_nested_difference(left, right):
    maximum = 0.0
    for node_id in sorted(set(left) | set(right), key=display_sort_key):
        if node_id not in left or node_id not in right:
            return float("inf")
        if len(left[node_id]) != len(right[node_id]):
            return float("inf")
        for left_pair, right_pair in zip(left[node_id], right[node_id]):
            for left_value, right_value in zip(left_pair, right_pair):
                maximum = max(maximum, abs(float(left_value) - float(right_value)))
    return maximum


def max_state_difference(expected, result, probability_function):
    maximum = 0.0
    records = selected_records(result["run_files"])
    expected_clades = set(str(record["clade_key"]) for record in records)
    if set(result["parsed_result"].node_results) != expected_clades:
        return float("inf")
    for record in records:
        node_id = str(record["display_node_id"])
        clade_key = str(record["clade_key"])
        expected_states = probability_function(
            expected[node_id],
            result["run_files"].config,
            result["run_files"].area_names,
        )
        actual_node = result["parsed_result"].node_results.get(clade_key)
        if actual_node is None:
            return float("inf")
        actual_states = dict(actual_node.state_supports or {})
        if set(expected_states) != set(actual_states):
            return float("inf")
        for state, value in expected_states.items():
            maximum = max(maximum, abs(float(value) - float(actual_states[state])))
    return maximum


def seeded_run_files(base_run_files, nexus_path, native_output):
    run_files = copy.copy(base_run_files)
    run_files.workdir = Path(nexus_path).parent
    run_files.nexus_path = Path(nexus_path)
    run_files.run1_p_path = Path(native_output["outputs"]["run1"])
    run_files.run2_p_path = Path(native_output["outputs"]["run2"])
    run_files.mcmc_path = Path(native_output["outputs"]["mcmc"])
    run_files.clade_log_path = run_files.workdir / "clade_b.log"
    run_files.analysis_log_path = run_files.workdir / "analysis_result.log"
    return run_files


def assert_truncated_output_rejected(run_files):
    source = Path(run_files.run1_p_path)
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    remove_index = None
    for index in range(len(lines) - 1, -1, -1):
        parts = lines[index].split("\t")
        try:
            float(parts[0])
        except Exception:
            continue
        remove_index = index
        break
    if remove_index is None:
        raise BBMLegacyCheckFailure("Could not create a truncated MrBayes output fixture")
    del lines[remove_index]
    truncated_path = source.with_name(source.stem + ".truncated.p")
    truncated_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    truncated_run_files = copy.copy(run_files)
    truncated_run_files.run1_p_path = truncated_path
    try:
        BBMOutputParser()._read_run_probabilities(truncated_path, truncated_run_files)
    except ValueError as exc:
        message = str(exc)
        if "Incomplete or non-sequential BBM samples" not in message:
            raise BBMLegacyCheckFailure(
                "Truncated BBM output raised the wrong diagnostic: %s" % message
            )
        return {"rejected": True, "diagnostic": message, "path": str(truncated_path)}
    raise BBMLegacyCheckFailure("The production BBM parser accepted a truncated .p output")


def build_scenarios(tree, matrix):
    builder = BBMDatasetBuilder()
    area_names, raw_rows = builder._dec_builder._collect_area_names_and_rows(matrix)
    taxon_names = [taxon for taxon, _bits in raw_rows]
    taxon_id_map = builder._collect_taxon_ids(matrix, taxon_names)
    rows = [(taxon, bits, taxon_id_map[taxon]) for taxon, bits in raw_rows]
    current_records = builder.build_node_records(tree, taxon_id_map)
    legacy_records = legacy_node_records(tree, taxon_id_map)
    current_identity = [
        (record["node_index"], record["display_node_id"], record["clade_key"], record["leaf_ids"])
        for record in current_records
    ]
    legacy_identity = [
        (record["node_index"], record["display_node_id"], record["clade_key"], record["leaf_ids"])
        for record in legacy_records
    ]
    if current_identity != legacy_identity:
        raise BBMLegacyCheckFailure("Current BBM node identity differs from the legacy postorder contract")
    all_node_ids = [str(record["display_node_id"]) for record in current_records]

    current_default = BBMConfig.default_for_areas(area_names, node_ids=all_node_ids)

    baseline = BBMConfig.default_for_areas(area_names, node_ids=all_node_ids)
    baseline.chains = 10

    large = BBMConfig.default_for_areas(area_names, node_ids=all_node_ids)
    large.chains = 10
    large.large_dataset_mode = True

    advanced = BBMConfig.default_for_areas(area_names, node_ids=all_node_ids[::2])
    advanced.chain_length = 20000
    advanced.sample_frequency = 200
    advanced.discard_samples = 10
    advanced.chains = 4
    advanced.temperature = 0.2
    advanced.state_frequency_model = "F81"
    advanced.dirichlet_alpha = 0.7
    advanced.dirichlet_beta = 1.3
    advanced.rate_variation_model = "GAMMA"
    advanced.gamma_min = 0.01
    advanced.gamma_max = 12.5
    advanced.root_distribution = "CUSTOM"
    advanced.custom_root_distribution = "AC"
    advanced.large_dataset_mode = True
    advanced.max_areas = 2
    advanced.include_null_range = True

    scenarios = []
    for name, config in [
        ("current_safe_default", current_default),
        ("legacy_default", baseline),
        ("legacy_large_dataset", large),
        ("advanced_parameter_mapping", advanced),
    ]:
        config.validate()
        run_files = builder.build(
            tree=tree,
            matrix=matrix,
            config=config,
            output_dir=RUN_ROOT / "contracts",
            run_name=name,
        )
        scenarios.append((name, run_files))
    return rows, legacy_records, scenarios


def run_native_comparison(executable, rows, legacy_records, base_run_files, reference_tree):
    current_dir = RUN_ROOT / "native" / "current"
    legacy_dir = RUN_ROOT / "native" / "legacy"
    current_dir.mkdir(parents=True, exist_ok=True)
    legacy_dir.mkdir(parents=True, exist_ok=True)

    current_nexus = current_dir / "current_seeded.nex"
    current_nexus.write_text(
        inject_seed(base_run_files.nexus_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    legacy_nexus = legacy_dir / "legacy_seeded.nex"
    write_legacy_nexus(
        legacy_nexus,
        rows,
        base_run_files.area_names,
        legacy_records,
        base_run_files.selected_node_ids,
        base_run_files.config,
    )
    legacy_nexus.write_text(
        inject_seed(legacy_nexus.read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    current_native = run_nexus(executable, current_nexus)
    legacy_native = run_nexus(executable, legacy_nexus)
    expected_warnings = [EXPECTED_CHAIN10_WARNING]
    if current_native["warnings"] != expected_warnings:
        raise BBMLegacyCheckFailure(
            "The explicit 10-chain current run did not emit the expected MrBayes warning"
        )
    if legacy_native["warnings"] != expected_warnings:
        raise BBMLegacyCheckFailure(
            "The explicit 10-chain legacy-contract run did not emit the expected MrBayes warning"
        )
    current_run_files = seeded_run_files(base_run_files, current_nexus, current_native)
    legacy_run_files = seeded_run_files(base_run_files, legacy_nexus, legacy_native)

    parser = BBMOutputParser()
    current_run1 = parser._read_run_probabilities(current_run_files.run1_p_path, current_run_files)
    current_run2 = parser._read_run_probabilities(current_run_files.run2_p_path, current_run_files)
    current_combined = parser._combine_runs(current_run1, current_run2)
    parsed_result = parser.parse(reference_tree=reference_tree, run_files=current_run_files)

    raw_current_run1, current_stats1 = read_raw_probabilities(
        current_run_files.run1_p_path, current_run_files
    )
    raw_current_run2, current_stats2 = read_raw_probabilities(
        current_run_files.run2_p_path, current_run_files
    )
    raw_current_combined = combine_raw_runs(raw_current_run1, raw_current_run2)

    raw_legacy_run1, legacy_stats1 = read_raw_probabilities(
        legacy_run_files.run1_p_path, legacy_run_files
    )
    raw_legacy_run2, legacy_stats2 = read_raw_probabilities(
        legacy_run_files.run2_p_path, legacy_run_files
    )
    raw_legacy_combined = combine_raw_runs(raw_legacy_run1, raw_legacy_run2)

    precision_current_run1, _stats = legacy_read_probabilities(
        current_run_files.run1_p_path, current_run_files
    )
    precision_current_run2, _stats = legacy_read_probabilities(
        current_run_files.run2_p_path, current_run_files
    )
    precision_current_combined = combine_legacy_runs(
        precision_current_run1, precision_current_run2
    )
    precision_legacy_run1, _stats = legacy_read_probabilities(
        legacy_run_files.run1_p_path, legacy_run_files
    )
    precision_legacy_run2, _stats = legacy_read_probabilities(
        legacy_run_files.run2_p_path, legacy_run_files
    )
    precision_legacy_combined = combine_legacy_runs(
        precision_legacy_run1, precision_legacy_run2
    )

    parsed_payload = {
        "run_files": current_run_files,
        "parsed_result": parsed_result,
    }
    raw_differences = {
        "current_parser_vs_raw_oracle_run1": max_nested_difference(
            current_run1, raw_current_run1
        ),
        "current_parser_vs_raw_oracle_run2": max_nested_difference(
            current_run2, raw_current_run2
        ),
        "current_parser_vs_raw_oracle_combined": max_nested_difference(
            current_combined, raw_current_combined
        ),
        "current_range_states_vs_raw_formula": max_state_difference(
            raw_current_combined, parsed_payload, raw_range_probabilities
        ),
        "current_TID_vs_legacy_numeric_constraints_run1": max_nested_difference(
            raw_current_run1, raw_legacy_run1
        ),
        "current_TID_vs_legacy_numeric_constraints_run2": max_nested_difference(
            raw_current_run2, raw_legacy_run2
        ),
        "current_TID_vs_legacy_numeric_constraints_combined": max_nested_difference(
            raw_current_combined, raw_legacy_combined
        ),
        "faithful_precision_TID_vs_numeric_constraints": max_nested_difference(
            precision_current_combined, precision_legacy_combined
        ),
    }
    for label, value in raw_differences.items():
        if not math.isfinite(value) or value > RAW_TOLERANCE:
            raise BBMLegacyCheckFailure("%s differs by %r" % (label, value))

    precision_differences = {
        "current_full_precision_vs_legacy_F6_marginals": max_nested_difference(
            current_combined, precision_current_combined
        ),
        "current_full_precision_states_vs_legacy_Single_F6_formula": max_state_difference(
            precision_current_combined, parsed_payload, legacy_range_probabilities
        ),
    }
    if precision_differences["current_full_precision_vs_legacy_F6_marginals"] > LEGACY_MARGINAL_TOLERANCE:
        raise BBMLegacyCheckFailure("Legacy marginal precision drift exceeds its tolerance")
    if precision_differences["current_full_precision_states_vs_legacy_Single_F6_formula"] > LEGACY_STATE_TOLERANCE:
        raise BBMLegacyCheckFailure("Legacy range-state precision drift exceeds its tolerance")

    selected_count = len(selected_records(current_run_files))
    if len(parsed_result.node_results) != selected_count:
        raise BBMLegacyCheckFailure("BBM parser emitted unselected node results")

    return {
        "seed": SEED,
        "swap_seed": SWAP_SEED,
        "current": current_native,
        "legacy": legacy_native,
        "current_nexus": str(current_nexus),
        "legacy_nexus": str(legacy_nexus),
        "current_nexus_sha256": sha256(current_nexus),
        "legacy_nexus_sha256": sha256(legacy_nexus),
        "sample_accounting": {
            "current_run1": current_stats1,
            "current_run2": current_stats2,
            "legacy_run1": legacy_stats1,
            "legacy_run2": legacy_stats2,
        },
        "node_result_count": len(parsed_result.node_results),
        "selected_node_count": selected_count,
        "raw_differences": raw_differences,
        "precision_differences": precision_differences,
        "tolerances": {
            "raw": RAW_TOLERANCE,
            "legacy_marginal": LEGACY_MARGINAL_TOLERANCE,
            "legacy_state_percentage_points": LEGACY_STATE_TOLERANCE,
        },
        "warning_disposition": {
            "chains": 10,
            "expected": expected_warnings,
            "cause": "The bundled 32-bit MrBayes emits this warning with nchains=10.",
        },
        "passed": True,
    }


def run_current_oracle_validation(
    executable,
    base_run_files,
    reference_tree,
    name,
    expected_warnings=None,
):
    workdir = RUN_ROOT / "native" / name
    workdir.mkdir(parents=True, exist_ok=True)
    nexus_path = workdir / (name + "_seeded.nex")
    nexus_path.write_text(
        inject_seed(base_run_files.nexus_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    native = run_nexus(executable, nexus_path)
    expected_warnings = list(expected_warnings or [])
    if native["warnings"] != expected_warnings:
        raise BBMLegacyCheckFailure(
            "%s emitted unexpected MrBayes warnings: %s" % (name, native["warnings"])
        )
    run_files = seeded_run_files(base_run_files, nexus_path, native)

    parser = BBMOutputParser()
    current_run1 = parser._read_run_probabilities(run_files.run1_p_path, run_files)
    current_run2 = parser._read_run_probabilities(run_files.run2_p_path, run_files)
    current_combined = parser._combine_runs(current_run1, current_run2)
    parsed_result = parser.parse(reference_tree=reference_tree, run_files=run_files)

    raw_run1, stats1 = read_raw_probabilities(run_files.run1_p_path, run_files)
    raw_run2, stats2 = read_raw_probabilities(run_files.run2_p_path, run_files)
    raw_combined = combine_raw_runs(raw_run1, raw_run2)
    precision_run1, _stats = legacy_read_probabilities(run_files.run1_p_path, run_files)
    precision_run2, _stats = legacy_read_probabilities(run_files.run2_p_path, run_files)
    precision_combined = combine_legacy_runs(precision_run1, precision_run2)
    payload = {"run_files": run_files, "parsed_result": parsed_result}
    raw_differences = {
        "parser_vs_raw_oracle_run1": max_nested_difference(current_run1, raw_run1),
        "parser_vs_raw_oracle_run2": max_nested_difference(current_run2, raw_run2),
        "parser_vs_raw_oracle_combined": max_nested_difference(
            current_combined, raw_combined
        ),
        "range_states_vs_raw_formula": max_state_difference(
            raw_combined, payload, raw_range_probabilities
        ),
    }
    for label, value in raw_differences.items():
        if not math.isfinite(value) or value > RAW_TOLERANCE:
            raise BBMLegacyCheckFailure("%s %s differs by %r" % (name, label, value))
    precision_differences = {
        "full_precision_vs_legacy_F6_marginals": max_nested_difference(
            current_combined, precision_combined
        ),
        "full_precision_states_vs_legacy_Single_F6_formula": max_state_difference(
            precision_combined, payload, legacy_range_probabilities
        ),
    }
    if precision_differences["full_precision_vs_legacy_F6_marginals"] > LEGACY_MARGINAL_TOLERANCE:
        raise BBMLegacyCheckFailure("%s legacy marginal precision drift is too large" % name)
    if precision_differences["full_precision_states_vs_legacy_Single_F6_formula"] > LEGACY_STATE_TOLERANCE:
        raise BBMLegacyCheckFailure("%s legacy state precision drift is too large" % name)
    if run_files.config.rate_variation_model == "GAMMA":
        if stats1["with_g_offset"] != 2 or stats2["with_g_offset"] != 2:
            raise BBMLegacyCheckFailure(
                "%s did not expose the expected lnPr + alpha output columns" % name
            )

    selected_count = len(selected_records(run_files))
    if len(parsed_result.node_results) != selected_count:
        raise BBMLegacyCheckFailure(
            "%s emitted %s nodes for %s selected nodes"
            % (name, len(parsed_result.node_results), selected_count)
        )
    truncated_output_check = assert_truncated_output_rejected(run_files)

    return {
        "name": name,
        "nexus_path": str(nexus_path),
        "nexus_sha256": sha256(nexus_path),
        "native": native,
        "sample_accounting": {"run1": stats1, "run2": stats2},
        "selected_node_count": selected_count,
        "node_result_count": len(parsed_result.node_results),
        "raw_differences": raw_differences,
        "precision_differences": precision_differences,
        "tolerances": {
            "raw": RAW_TOLERANCE,
            "legacy_marginal": LEGACY_MARGINAL_TOLERANCE,
            "legacy_state_percentage_points": LEGACY_STATE_TOLERANCE,
        },
        "expected_warnings": expected_warnings,
        "truncated_output_check": truncated_output_check,
        "passed": True,
    }


def write_latest(report):
    native = report["native_comparison"]
    safe_default = report["current_safe_default_validation"]
    advanced = report["advanced_native_validation"]
    lines = [
        "# BBM 旧案例系统对照（最新）",
        "",
        "状态：**Passed**",
        "",
        "- 运行时间：`%s`" % report["generated_at"],
        "- Git commit：`%s`" % report["git_commit"],
        "- 机器可读报告：`%s`" % report["report_path"],
        "- 当前 MrBayes SHA256：`%s`" % report["engines"]["current_mrbayes_sha256"],
        "- 旧版 Large dataset MrBayes SHA256：`%s`" % report["engines"]["legacy_mrbayes_sha256"],
        "- 两个 MrBayes 二进制完全相同：`%s`" % report["engines"]["mrbayes_binaries_identical"],
        "",
        "## 覆盖",
        "",
        "- Psychotria：19 tips、4 areas、18 internal nodes。",
        "- 检查当前安全默认、旧版 10-chain 默认、旧版 Large dataset/OG0、F81+Gamma+custom root+null range+node subset 四套输入契约。",
        "- 对照 `Config_BBM.vb` 的 NEXUS/命令写法、`Module_BBM.vb` 的 discard+1 与双 run 平均、`Form_Main.vb` 的范围概率乘积与归一化。",
        "- 使用相同 MrBayes、固定 seed/swapseed，实跑当前 `TID` 约束和旧版数值 taxon 约束。",
        "",
        "## 数值结果",
        "",
        "- 10-chain 对照选中/输出节点：`%s/%s`" % (
            native["selected_node_count"], native["node_result_count"]
        ),
        "- 当前原生运行耗时：`%.3f s`" % native["current"]["elapsed_seconds"],
        "- 旧约束原生运行耗时：`%.3f s`" % native["legacy"]["elapsed_seconds"],
        "- 当前安全默认链数：`4`；warning 数：`%s`" % len(safe_default["native"]["warnings"]),
    ]
    for label, value in sorted(native["raw_differences"].items()):
        lines.append("- `raw_%s` 最大绝对差：`%.12g`" % (label, value))
    for label, value in sorted(native["precision_differences"].items()):
        lines.append("- `precision_%s` 最大绝对差：`%.12g`" % (label, value))
    lines.extend([
        "- 高级参数原生运行耗时：`%.3f s`" % advanced["native"]["elapsed_seconds"],
        "- 高级参数选中节点：`%s`；输出节点：`%s`" % (
            advanced["selected_node_count"], advanced["node_result_count"]
        ),
    ])
    for label, value in sorted(advanced["raw_differences"].items()):
        lines.append("- `advanced_raw_%s` 最大绝对差：`%.12g`" % (label, value))
    for label, value in sorted(advanced["precision_differences"].items()):
        lines.append("- `advanced_precision_%s` 最大绝对差：`%.12g`" % (label, value))
    lines.extend([
        "- 高级参数案例 warning 数：`%s`" % len(advanced["native"]["warnings"]),
        "",
        "## 原生引擎警告",
        "",
    ])
    lines.append(
        "隔离实验确认警告由旧版默认 `nchains=10` 触发，不是由全节点约束触发。"
        "当前默认改为 4 chains，实跑无 warning；显式 10-chain 当前/旧约束运行均产生以下已知 warning："
    )
    lines.extend("- `%s`" % line for line in native["current"]["warnings"])
    lines.extend([
        "",
        "## 结论与边界",
        "",
        "当前 BBM 的参数输入、MrBayes 原始输出读取和全精度双 run 汇总通过独立 raw oracle。固定 seed 下，当前 TID 与旧数字 taxon 约束的原始输出完全一致。旧版随后用 VB Single 并在两阶段写 F6，产生上面记录的微小精度差；当前保留更高精度，不人为降级。当前只输出用户选中的节点，不再继承旧版把未选节点伪装成缺失范围 100% 的展示错误。外部 MrBayes 仍是唯一执行主链，旧 BAYESDLL.dll 不重新接回。",
        "",
    ])
    LATEST_PATH.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Compare current BBM with the old RASP BBM contract.")
    parser.add_argument(
        "--legacy-mrbayes",
        default=r"F:\RASP_Win\Plug-ins\mb.3.2.7-win32.exe",
        help="MrBayes executable used by the old RASP Large dataset path.",
    )
    parser.add_argument(
        "--legacy-bayes-dll",
        default=r"F:\RASP_Win\BAYESDLL.dll",
        help="Optional old default BBM DLL recorded for provenance only.",
    )
    args = parser.parse_args()

    legacy_engine = Path(args.legacy_mrbayes)
    legacy_dll = Path(args.legacy_bayes_dll)
    required = [
        CURRENT_ENGINE,
        legacy_engine,
        LEGACY_CONFIG_SOURCE,
        LEGACY_PARSER_SOURCE,
        LEGACY_RESULT_SOURCE,
        DATA_ROOT / "Psychotria.tree",
        DATA_ROOT / "distribution.csv",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise BBMLegacyCheckFailure("Required files are missing: %s" % ", ".join(missing))

    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    tree, matrix = load_inputs()
    rows, legacy_records, scenarios = build_scenarios(tree, matrix)
    contract_reports = [
        assert_contract(name, run_files, rows, legacy_records)
        for name, run_files in scenarios
    ]
    large_run_files = dict((name, run_files) for name, run_files in scenarios)[
        "legacy_large_dataset"
    ]
    native_report = run_native_comparison(
        CURRENT_ENGINE,
        rows,
        legacy_records,
        large_run_files,
        tree,
    )
    advanced_run_files = dict((name, run_files) for name, run_files in scenarios)[
        "advanced_parameter_mapping"
    ]
    advanced_report = run_current_oracle_validation(
        CURRENT_ENGINE,
        advanced_run_files,
        tree,
        "advanced_parameter_mapping",
    )
    safe_default_run_files = dict((name, run_files) for name, run_files in scenarios)[
        "current_safe_default"
    ]
    safe_default_report = run_current_oracle_validation(
        CURRENT_ENGINE,
        safe_default_run_files,
        tree,
        "current_safe_default",
    )

    current_hash = sha256(CURRENT_ENGINE)
    legacy_hash = sha256(legacy_engine)
    if current_hash != legacy_hash:
        raise BBMLegacyCheckFailure(
            "Current and old Large dataset MrBayes binaries are not identical"
        )

    report = {
        "status": "passed",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_path": str(REPORT_PATH),
        "run_root": str(RUN_ROOT),
        "git_commit": git_output("rev-parse", "HEAD"),
        "git_status_porcelain": git_output("status", "--porcelain").splitlines(),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "inputs": {
            "tree_path": str(DATA_ROOT / "Psychotria.tree"),
            "tree_sha256": sha256(DATA_ROOT / "Psychotria.tree"),
            "matrix_path": str(DATA_ROOT / "distribution.csv"),
            "matrix_sha256": sha256(DATA_ROOT / "distribution.csv"),
            "taxon_count": len(rows),
            "area_count": len(scenarios[0][1].area_names),
            "internal_node_count": len(legacy_records),
        },
        "source_contracts": {
            "config_bbm": {
                "path": str(LEGACY_CONFIG_SOURCE),
                "sha256": sha256(LEGACY_CONFIG_SOURCE),
                "relevant_lines": [57, 92, 114, 168, 240, 242, 308],
            },
            "module_bbm": {
                "path": str(LEGACY_PARSER_SOURCE),
                "sha256": sha256(LEGACY_PARSER_SOURCE),
                "relevant_lines": [3, 21, 83, 128],
            },
            "form_main": {
                "path": str(LEGACY_RESULT_SOURCE),
                "sha256": sha256(LEGACY_RESULT_SOURCE),
                "relevant_lines": [3981, 4114, 4193],
            },
        },
        "engines": {
            "current_mrbayes_path": str(CURRENT_ENGINE),
            "current_mrbayes_sha256": current_hash,
            "legacy_mrbayes_path": str(legacy_engine),
            "legacy_mrbayes_sha256": legacy_hash,
            "mrbayes_binaries_identical": current_hash == legacy_hash,
            "legacy_bayes_dll_path": str(legacy_dll),
            "legacy_bayes_dll_exists": legacy_dll.exists(),
            "legacy_bayes_dll_sha256": sha256(legacy_dll) if legacy_dll.exists() else None,
            "legacy_bayes_dll_executed": False,
        },
        "contract_scenarios": contract_reports,
        "native_comparison": native_report,
        "current_safe_default_validation": safe_default_report,
        "advanced_native_validation": advanced_report,
        "known_intentional_differences": [
            "Current constraints use explicit TID labels; old source writes numeric taxon positions. The seeded native outputs are identical.",
            "Current BBM always uses the external MrBayes runner; old RASP used BAYESDLL.dll by default and the same external MrBayes only in Large dataset mode.",
            "Current UI names the legacy extra-row behavior Add OG0 outgroup instead of implying that it is a general large-data acceleration switch.",
            "Current BBM emits results only for selected nodes; old RASP filled unselected nodes with artificial all-zero-area marginals.",
            "Current BBM retains full Python precision; old RASP accumulated VB Single values and rounded run and combined marginals to F6.",
            "Current BBM defaults to four chains; old RASP used 10, which triggers a known allocation warning in the bundled 32-bit MrBayes.",
            "Current JSON Save/Load Setting is an added UI feature and is not part of the old computation contract.",
        ],
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_latest(report)
    print("BBM legacy case checks passed")
    print("Report: %s" % REPORT_PATH)
    print("Latest: %s" % LATEST_PATH)


if __name__ == "__main__":
    main()
