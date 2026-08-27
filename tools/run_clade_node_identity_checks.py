import hashlib
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.bootstrap import ApplicationBootstrap

ApplicationBootstrap().inject_vendor_packages()

from ete3 import Tree

from application.services.bayarea_dataset_builder import BayAreaDatasetBuilder
from application.services.bbm_dataset_builder import BBMDatasetBuilder
from application.services.sbgb_analysis_service import SBGBAnalysisService
from application.services.sdec_analysis_service import SDECAnalysisService
from application.services.sdiva_analysis_service import SDivaAnalysisService
from application.services.tree_collection_prepare_service import TreeCollectionPrepareService
from infrastructure.biogeobears.biogeobears_output_parser import BioGeoBEARSOutputParser
from infrastructure.dec.dec_output_parser import DECOutputParser
from infrastructure.io.csv_matrix_reader import CsvMatrixReader
from infrastructure.tree.clade_node_identity import CladeNodeIdentityService
from infrastructure.tree.tree_reader import TreeReader


DATA_ROOT = PROJECT_ROOT / "data" / "benchmarks" / "psychotria"
BASELINE_PATH = DATA_ROOT / "psychotria_gold_expected.json"
RUN_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
RUN_ROOT = PROJECT_ROOT / "runs" / "clade_node_identity" / RUN_STAMP
REPORT_PATH = RUN_ROOT / "report.json"
LATEST_PATH = PROJECT_ROOT / "docs" / "clade_node_identity_latest.md"
TREE_SAMPLE_COUNT = 25
FULL_TREE_COUNT = 1001
DORE_TREE_PATH = (
    PROJECT_ROOT
    / "data"
    / "benchmarks"
    / "dore_ponerinae"
    / "final_inputs"
    / "Ponerinae_phylogeny_MCC_1534t.tree"
)


class IdentityCheckFailure(AssertionError):
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


def extract_tree(entry):
    for attr in ("parsed_tree", "tree", "ete_tree", "tree_obj"):
        value = getattr(entry, attr, None)
        if value is not None:
            return value
    if hasattr(entry, "get_leaf_names"):
        return entry
    raise IdentityCheckFailure("Prepared tree entry has no usable tree object")


def load_psychotria():
    tree_text = TreeReader().read_tree(str(DATA_ROOT / "Psychotria.tree"))
    reference_tree = Tree(tree_text, format=1)
    matrix = CsvMatrixReader().read(str(DATA_ROOT / "distribution.csv"))
    collection = TreeReader().read_tree_collection(str(DATA_ROOT / "dataset.trees"))
    prepared = TreeCollectionPrepareService().prepare(
        collection,
        pre_burnin=0,
        post_burnin=0,
        enable_random_sampling=False,
        random_sample_size=0,
    )
    entries = list(prepared.analysis_entries or [])
    if len(entries) != FULL_TREE_COUNT:
        raise IdentityCheckFailure(
            "Psychotria tree fixture changed: expected %s valid trees, found %s"
            % (FULL_TREE_COUNT, len(entries))
        )
    return reference_tree, matrix, [extract_tree(entry) for entry in entries]


def independent_reference_node_id_map(tree):
    taxon_count = len(list(tree.get_leaf_names()))
    mapping = {}
    counter = 0
    for node in tree.traverse("postorder"):
        if node.is_leaf():
            continue
        counter += 1
        names = sorted(str(name or "").strip() for name in node.get_leaf_names())
        mapping["|".join(names)] = str(taxon_count + counter)
    return mapping


def assert_production_builders(reference_tree, matrix):
    expected = CladeNodeIdentityService.build_reference_node_id_map(reference_tree)
    independent_expected = independent_reference_node_id_map(reference_tree)
    if expected != independent_expected:
        raise IdentityCheckFailure("Canonical identity helper differs from independent oracle")
    taxa_order = [str(row.get("Name", "")).strip() for row in matrix.rows]
    name_to_index = dict((name, index) for index, name in enumerate(taxa_order, 1))
    index_to_name = dict((index, name) for name, index in name_to_index.items())

    sdiva_nodes = SDivaAnalysisService()._build_reference_nodes(
        reference_tree, name_to_index, index_to_name
    )
    sdec_service = object.__new__(SDECAnalysisService)
    sdec_records = sdec_service._build_reference_nodes(
        reference_tree, name_to_index, index_to_name
    )
    sbgb_service = object.__new__(SBGBAnalysisService)
    sbgb_records = sbgb_service._build_reference_nodes(
        reference_tree, name_to_index, index_to_name
    )

    actual_maps = {
        "sdiva": dict(
            (row["node_key"], str(row["display_id"])) for row in sdiva_nodes
        ),
        "sdec": dict(
            (row["node_key"], str(row["display_id"])) for row in sdec_records
        ),
        "sbgb": dict(
            (row["node_key"], str(row["display_id"])) for row in sbgb_records
        ),
        "dec_parser": DECOutputParser()._build_reference_node_id_map(reference_tree),
        "bgb_parser": BioGeoBEARSOutputParser()._build_reference_node_id_map(reference_tree),
        "bayarea": BayAreaDatasetBuilder()._build_reference_node_id_map(reference_tree),
    }

    taxon_id_map = dict((name, str(index)) for index, name in enumerate(taxa_order, 1))
    bbm_records = BBMDatasetBuilder().build_node_records(reference_tree, taxon_id_map)
    actual_maps["bbm"] = dict(
        (row["clade_key"], str(row["display_node_id"])) for row in bbm_records
    )

    mismatches = {}
    for name, actual in actual_maps.items():
        if actual != expected:
            mismatches[name] = {
                "missing": sorted(set(expected) - set(actual)),
                "unexpected": sorted(set(actual) - set(expected)),
                "display_id_mismatches": sorted(
                    key
                    for key in set(expected) & set(actual)
                    if str(expected[key]) != str(actual[key])
                ),
            }
    if mismatches:
        raise IdentityCheckFailure(
            "Production reference-node builders disagree: %s"
            % json.dumps(mismatches, ensure_ascii=False, sort_keys=True)
        )
    return {
        "reference_node_count": len(expected),
        "independent_oracle_matches": True,
        "checked_components": sorted(actual_maps.keys()),
        "all_components_match": True,
    }


def run_synthetic_checks():
    reference = Tree("((A,B),(C,D));", format=1)
    reordered = Tree("((B,A),(D,C));", format=1)
    topology_change = Tree("((A,C),(B,D));", format=1)
    polytomy = Tree("(A,B,C,D);", format=1)
    rerooted = Tree("(A,(B,(C,D)));", format=1)
    missing_taxon = Tree("((A,B),C);", format=1)
    duplicate_taxon = Tree("((A,B),(C,C));", format=1)
    unary_tree = Tree("(((A,B)),C);", format=1)

    reordered_report = CladeNodeIdentityService.audit_tree(reference, reordered)
    topology_report = CladeNodeIdentityService.audit_tree(reference, topology_change)
    polytomy_report = CladeNodeIdentityService.audit_tree(reference, polytomy)
    rerooted_report = CladeNodeIdentityService.audit_tree(reference, rerooted)
    missing_report = CladeNodeIdentityService.audit_tree(reference, missing_taxon)
    duplicate_report = CladeNodeIdentityService.audit_tree(reference, duplicate_taxon)

    if not reordered_report["taxon_identity_is_valid"]:
        raise IdentityCheckFailure("Child-order-only change was not accepted")
    if not reordered_report["topology_matches_reference"]:
        raise IdentityCheckFailure("Child-order-only change altered clade identity")
    if topology_report["missing_reference_clade_count"] == 0:
        raise IdentityCheckFailure("Topology change was not detected")
    if topology_report["topology_matches_reference"]:
        raise IdentityCheckFailure("Changed topology was reported as an exact match")
    if polytomy_report["missing_reference_clade_count"] == 0:
        raise IdentityCheckFailure("Polytomy was not detected")
    if rerooted_report["topology_matches_reference"]:
        raise IdentityCheckFailure("Rerooted topology was not detected")
    if not missing_report["missing_taxa"]:
        raise IdentityCheckFailure("Missing taxon was not detected")
    if "C" not in duplicate_report["duplicate_taxa"]:
        raise IdentityCheckFailure("Duplicate taxon was not detected")
    unary_ids = [
        str(row["display_node_id"])
        for row in BBMDatasetBuilder().build_node_records(
            unary_tree, {"A": "1", "B": "2", "C": "3"}
        )
    ]
    if len(unary_ids) != len(set(unary_ids)):
        raise IdentityCheckFailure("BBM postorder IDs collapsed duplicate unary clades")
    unary_audit = CladeNodeIdentityService.audit_result_nodes(
        unary_tree,
        CladeNodeIdentityService.build_reference_node_records(unary_tree),
        method_name="synthetic_unary",
    )
    if unary_audit["identity_matches_reference"]:
        raise IdentityCheckFailure("Ambiguous unary clade identity was not reported")
    collapsed_unary = Tree("((A,B),C);", format=1)
    unary_topology_audit = CladeNodeIdentityService.audit_tree(
        unary_tree, collapsed_unary
    )
    if unary_topology_audit["topology_matches_reference"]:
        raise IdentityCheckFailure("Collapsed unary topology was reported as exact")

    exact_nodes = CladeNodeIdentityService.build_reference_node_records(reference)
    exact_audit = CladeNodeIdentityService.audit_result_nodes(
        reference, exact_nodes, method_name="synthetic_exact"
    )
    broken_nodes = [dict(row) for row in exact_nodes]
    broken_nodes[0]["display_node_id"] = "999"
    broken_nodes.pop(1)
    broken_nodes.append(
        {
            "clade_key": "A|C",
            "display_node_id": "998",
            "tip_names": ["A", "C"],
        }
    )
    broken_audit = CladeNodeIdentityService.audit_result_nodes(
        reference, broken_nodes, method_name="synthetic_broken"
    )
    if not exact_audit["identity_matches_reference"]:
        raise IdentityCheckFailure("Exact synthetic result did not pass")
    if broken_audit["identity_matches_reference"]:
        raise IdentityCheckFailure("Broken synthetic result was not rejected")
    if not broken_audit["display_node_id_mismatches"]:
        raise IdentityCheckFailure("Wrong display node ID was not detected")
    if not broken_audit["missing_reference_clades"]:
        raise IdentityCheckFailure("Missing result clade was not detected")
    if not broken_audit["unexpected_result_clades"]:
        raise IdentityCheckFailure("Unexpected result clade was not detected")

    blank_nodes = [dict(row) for row in exact_nodes]
    blank_nodes.append({"clade_key": "", "display_node_id": ""})
    blank_audit = CladeNodeIdentityService.audit_result_nodes(
        reference, blank_nodes, method_name="synthetic_blank"
    )
    if blank_audit["identity_matches_reference"]:
        raise IdentityCheckFailure("Blank result clade was not rejected")

    mixed_collection = CladeNodeIdentityService.audit_tree_collection(
        reference, [reordered, missing_taxon]
    )
    if mixed_collection["input_tree_count"] != 2:
        raise IdentityCheckFailure("Mixed collection input denominator differs")
    if mixed_collection["effective_tree_count"] != 1:
        raise IdentityCheckFailure("Invalid taxon tree entered the effective denominator")
    mixed_support = dict(
        (row["clade_key"], row["supporting_tree_count"])
        for row in mixed_collection["node_support"]
    )
    if mixed_support.get("A|B") != 1:
        raise IdentityCheckFailure("Invalid taxon tree contributed clade support")

    exact_collection = CladeNodeIdentityService.audit_tree_collection(
        reference, [reordered]
    )
    missing_support_audit = CladeNodeIdentityService.audit_supporting_tree_counts(
        exact_collection,
        [dict(row) for row in exact_nodes],
        method_name="synthetic_missing_support",
    )
    if missing_support_audit["supporting_tree_counts_are_complete"]:
        raise IdentityCheckFailure("Missing support-count fields passed the audit")
    filtered_nodes = []
    for row in exact_nodes:
        item = dict(row)
        item["supporting_tree_count"] = 0
        filtered_nodes.append(item)
    filtered_support_audit = CladeNodeIdentityService.audit_supporting_tree_counts(
        exact_collection,
        filtered_nodes,
        method_name="synthetic_filtered_state",
    )
    if not filtered_support_audit["topology_presence_is_upper_bound"]:
        raise IdentityCheckFailure("Filtered state contribution violated topology upper bound")
    if filtered_support_audit["supporting_tree_counts_match_topology"]:
        raise IdentityCheckFailure("Filtered state contribution was treated as topology equality")

    return {
        "child_order_invariant": reordered_report,
        "topology_change": topology_report,
        "polytomy": polytomy_report,
        "rerooted": rerooted_report,
        "missing_taxon": missing_report,
        "duplicate_taxon": duplicate_report,
        "unary_bbm_display_node_ids": unary_ids,
        "unary_identity_audit": unary_audit,
        "collapsed_unary_topology": unary_topology_audit,
        "exact_result": exact_audit,
        "broken_result": broken_audit,
        "blank_result": blank_audit,
        "mixed_valid_invalid_collection": mixed_collection,
        "missing_support_count": missing_support_audit,
        "filtered_state_contribution": filtered_support_audit,
    }


def find_gold_report(explicit_path=None):
    if explicit_path:
        candidates = [Path(explicit_path)]
    else:
        candidates = sorted(
            (PROJECT_ROOT / "runs" / "psychotria_gold").glob("*/report.json"),
            reverse=True,
        )
    for path in candidates:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") != "passed":
            continue
        actual = payload.get("actual", {}) or {}
        if isinstance(actual.get("methods", None), dict):
            return path, payload, actual
    raise IdentityCheckFailure(
        "No passed Psychotria gold report with current actual results was found. "
        "Run tools/run_psychotria_gold_checks.py first."
    )


def audit_large_dore_tree():
    tree_text = TreeReader().read_tree(str(DORE_TREE_PATH))
    tree = Tree(tree_text, format=1)
    self_audit = CladeNodeIdentityService.audit_tree(tree, tree)
    records = CladeNodeIdentityService.build_reference_node_records(tree)
    display_ids = [str(row["display_node_id"]) for row in records]
    if len(tree.get_leaf_names()) != 1534:
        raise IdentityCheckFailure("Dore fixture is no longer a 1534-tip tree")
    if not self_audit["topology_matches_reference"]:
        raise IdentityCheckFailure("Dore tree does not match its own identity map")
    if len(display_ids) != len(set(display_ids)):
        raise IdentityCheckFailure("Dore reference display-node IDs are not unique")
    return {
        "tree_path": str(DORE_TREE_PATH),
        "tree_sha256": sha256(DORE_TREE_PATH),
        "leaf_count": len(tree.get_leaf_names()),
        "internal_node_count": len(records),
        "unique_clade_key_count": len(set(row["clade_key"] for row in records)),
        "unique_display_node_id_count": len(set(display_ids)),
        "self_audit": self_audit,
    }


def write_latest(report):
    collection = report["psychotria_tree_collection"]
    lines = [
        "# Clade/node identity audit",
        "",
        "Status: **%s**" % report["status"].upper(),
        "",
        "- Reference: Psychotria, %s tips / %s internal nodes"
        % (
            collection["reference_leaf_count"],
            collection["reference_internal_node_count"],
        ),
        "- Sampled trees: first %s valid trees" % collection["tree_count"],
        "- Full tree-set identity scan: %s effective / %s input trees"
        % (
            report["psychotria_full_tree_collection"]["effective_tree_count"],
            report["psychotria_full_tree_collection"]["input_tree_count"],
        ),
        "- Second real dataset: Dore %s tips / %s internal nodes"
        % (
            report["dore_1534_reference_tree"]["leaf_count"],
            report["dore_1534_reference_tree"]["internal_node_count"],
        ),
        "- Taxon-set mismatches: %s" % collection["taxon_mismatch_tree_count"],
        "- Unmatched reference clade observations: %s"
        % collection["unmatched_clade_observation_count"],
        "- Production identity builders checked: %s"
        % ", ".join(report["production_builders"]["checked_components"]),
        "- Single/S result mappings checked: %s"
        % ", ".join(sorted(report["result_identity_audits"].keys())),
        "- S-series topology denominators checked: %s"
        % ", ".join(sorted(report["supporting_count_audits"].keys())),
        "- Current engine result source: `%s`"
        % report["current_gold_result_source"]["path"],
        "",
        "Synthetic negative fixtures verify topology changes, missing taxa, duplicate taxa,",
        "missing/extra result clades, and incorrect display node IDs are reported.",
        "",
        "Machine-readable report: `%s`" % REPORT_PATH,
    ]
    LATEST_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit RASP clade/node identity contracts")
    parser.add_argument(
        "--gold-report",
        default="",
        help="Passed report.json produced by run_psychotria_gold_checks.py",
    )
    args = parser.parse_args(argv)
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    reference_tree, matrix, all_sampled_trees = load_psychotria()
    sampled_trees = all_sampled_trees[:TREE_SAMPLE_COUNT]
    collection_report = CladeNodeIdentityService.audit_tree_collection(
        reference_tree, sampled_trees
    )
    if collection_report["taxon_mismatch_tree_count"] != 0:
        raise IdentityCheckFailure("Psychotria first-25 contains taxon mismatches")
    if collection_report["unmatched_clade_observation_count"] != 65:
        raise IdentityCheckFailure(
            "Psychotria unmatched-clade total changed: %s"
            % collection_report["unmatched_clade_observation_count"]
        )
    full_collection_report = CladeNodeIdentityService.audit_tree_collection(
        reference_tree, all_sampled_trees
    )
    if full_collection_report["effective_tree_count"] != FULL_TREE_COUNT:
        raise IdentityCheckFailure("Psychotria full collection contains invalid taxon identities")
    full_collection_summary = dict(full_collection_report)
    full_collection_summary.pop("trees", None)

    gold_report_path, gold_report, actual_gold = find_gold_report(args.gold_report)
    methods = dict(actual_gold.get("methods", {}) or {})
    result_identity_audits = {}
    for method_name in (
        "diva",
        "sdiva_25",
        "dec",
        "sdec_25",
        "bgb_dec",
        "sbgb_dec_25",
    ):
        audit = CladeNodeIdentityService.audit_result_nodes(
            reference_tree,
            methods[method_name]["nodes"],
            method_name=method_name,
        )
        if not audit["identity_matches_reference"]:
            raise IdentityCheckFailure(
                "%s result identity differs: %s"
                % (method_name, json.dumps(audit, ensure_ascii=False, sort_keys=True))
            )
        result_identity_audits[method_name] = audit

    supporting_count_audits = {}
    for method_name in ("sdiva_25", "sdec_25", "sbgb_dec_25"):
        audit = CladeNodeIdentityService.audit_supporting_tree_counts(
            collection_report,
            methods[method_name]["nodes"],
            method_name=method_name,
        )
        if not audit["topology_presence_is_upper_bound"]:
            raise IdentityCheckFailure(
                "%s supporting counts exceed or omit topology presence: %s"
                % (method_name, json.dumps(audit, ensure_ascii=False, sort_keys=True))
            )
        supporting_count_audits[method_name] = audit

    report = {
        "status": "passed",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": git_output("rev-parse", "HEAD"),
        "inputs": {
            "Psychotria.tree": sha256(DATA_ROOT / "Psychotria.tree"),
            "dataset.trees": sha256(DATA_ROOT / "dataset.trees"),
            "distribution.csv": sha256(DATA_ROOT / "distribution.csv"),
            "psychotria_gold_expected.json": sha256(BASELINE_PATH),
            "current_gold_report": sha256(gold_report_path),
        },
        "identity_contract": {
            "taxon_normalization": "strip leading/trailing whitespace",
            "clade_key": "sorted descendant taxon names joined with |",
            "display_node_id": "tip count + postorder internal-node ordinal",
            "tree_set_merge": "exact canonical clade-key match",
        },
        "production_builders": assert_production_builders(reference_tree, matrix),
        "current_gold_result_source": {
            "path": str(gold_report_path),
            "generated_at": str(gold_report.get("generated_at", "") or ""),
            "git_commit": str(gold_report.get("git_commit", "") or ""),
            "status": str(gold_report.get("status", "") or ""),
        },
        "psychotria_tree_collection": collection_report,
        "psychotria_full_tree_collection": full_collection_summary,
        "dore_1534_reference_tree": audit_large_dore_tree(),
        "result_identity_audits": result_identity_audits,
        "supporting_count_audits": supporting_count_audits,
        "synthetic_checks": run_synthetic_checks(),
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_latest(report)
    print("Clade/node identity checks passed")
    print("Report: %s" % REPORT_PATH)
    print("Latest: %s" % LATEST_PATH)


if __name__ == "__main__":
    main()
