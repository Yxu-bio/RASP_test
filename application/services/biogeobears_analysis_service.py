from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import textwrap

from application.services.biogeobears_dataset_builder import BioGeoBEARSDatasetBuilder
from infrastructure.biogeobears.biogeobears_bsm_event_parser import BioGeoBEARSBSMEventParser
from infrastructure.biogeobears.biogeobears_output_parser import BioGeoBEARSOutputParser
from infrastructure.biogeobears.biogeobears_runner import BioGeoBEARSRunner


class BioGeoBEARSAnalysisService:
    def __init__(self, rscript_path=None, wrapper_script_path=None, work_root=None, site_library_path=None):
        self.dataset_builder = BioGeoBEARSDatasetBuilder()
        self.output_parser = BioGeoBEARSOutputParser()
        self.runner = BioGeoBEARSRunner(
            rscript_path=rscript_path,
            wrapper_script_path=wrapper_script_path,
            site_library_path=site_library_path,
        )
        self.work_root = Path(work_root) if work_root else Path("runs") / "biogeobears"
        self.bsm_event_parser = BioGeoBEARSBSMEventParser()

    def set_rscript_path(self, rscript_path):
        self.runner.set_rscript_path(rscript_path)

    def set_wrapper_script_path(self, wrapper_script_path):
        self.runner.set_wrapper_script_path(wrapper_script_path)

    def set_site_library_path(self, site_library_path):
        self.runner.set_site_library_path(site_library_path)

    def analyze(
        self,
        *,
        tree,
        matrix,
        config,
        run_name=None,
        scale_tree_to_root_age=False,
    ):
        if config is None:
            raise ValueError("BioGeoBEARS config is required.")

        config_kwargs = config.engine_kwargs()
        model_name = config_kwargs["model_name"]
        max_range_size = config_kwargs["max_range_size"]
        include_null_range = config_kwargs["include_null_range"]
        null_range_mode = config_kwargs["null_range_mode"]
        cores = config_kwargs["cores"]
        include_ranges = config_kwargs["include_ranges"]
        exclude_ranges = config_kwargs["exclude_ranges"]
        period_times = config_kwargs["period_times"]
        time_matrix_kind = config_kwargs["time_matrix_kind"]
        period_matrices = config_kwargs["period_matrices"]
        root_age = config_kwargs["root_age"]
        if run_name is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_name = "bgb_%s_%s" % (str(model_name).lower(), stamp)

        run_files = self.build_run_files(
            tree=tree,
            matrix=matrix,
            run_name=run_name,
            model_name=model_name,
            max_range_size=max_range_size,
            include_null_range=include_null_range,
            null_range_mode=null_range_mode,
            cores=cores,
            include_ranges=include_ranges,
            exclude_ranges=exclude_ranges,
            period_times=period_times,
            time_matrix_kind=time_matrix_kind,
            period_matrices=period_matrices,
            root_age=root_age,
            scale_tree_to_root_age=scale_tree_to_root_age,
        )

        bsm_dir = run_files.workdir / "bsm"
        if bsm_dir.exists():
            shutil.rmtree(str(bsm_dir))

        try:
            run_output = self.runner.run(run_files)
        except Exception as exc:
            raise RuntimeError(
                "BioGeoBEARS 运行失败。\n"
                "workdir: {workdir}\n"
                "treefile: {treefile}\n"
                "geogfile: {geogfile}\n"
                "areas_json: {areas_json}\n"
                "model: {model}\n"
                "{msg}".format(
                    workdir=run_files.workdir,
                    treefile=run_files.tree_path,
                    geogfile=run_files.geog_path,
                    areas_json=run_files.areas_json_path,
                    model=run_files.model_name,
                    msg=str(exc),
                )
            )

        result = self.parse_run_files(tree=tree, run_files=run_files)
        result.config = config
        return result

    def generate_bsm_events(
        self,
        *,
        tree,
        matrix,
        config,
        run_name=None,
        nummaps=100,
        seed=12345,
        maxtries_per_branch=40000,
        scale_tree_to_root_age=False,
    ):
        if config is None:
            raise ValueError("BioGeoBEARS config is required.")

        config_kwargs = config.engine_kwargs()
        model_name = config_kwargs["model_name"]
        max_range_size = config_kwargs["max_range_size"]
        include_null_range = config_kwargs["include_null_range"]
        null_range_mode = config_kwargs["null_range_mode"]
        cores = config_kwargs["cores"]
        include_ranges = config_kwargs["include_ranges"]
        exclude_ranges = config_kwargs["exclude_ranges"]
        period_times = config_kwargs["period_times"]
        time_matrix_kind = config_kwargs["time_matrix_kind"]
        period_matrices = config_kwargs["period_matrices"]
        root_age = config_kwargs["root_age"]

        if run_name is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_name = "bgb_%s_bsm_%s" % (str(model_name).lower(), stamp)

        run_files = self.build_run_files(
            tree=tree,
            matrix=matrix,
            run_name=run_name,
            model_name=model_name,
            max_range_size=max_range_size,
            include_null_range=include_null_range,
            null_range_mode=null_range_mode,
            cores=cores,
            include_ranges=include_ranges,
            exclude_ranges=exclude_ranges,
            period_times=period_times,
            time_matrix_kind=time_matrix_kind,
            period_matrices=period_matrices,
            root_age=root_age,
            scale_tree_to_root_age=scale_tree_to_root_age,
        )

        bsm_dir = run_files.workdir / "bsm"
        if bsm_dir.exists():
            shutil.rmtree(str(bsm_dir))

        try:
            self.runner.run(
                run_files,
                bsm_outdir=bsm_dir,
                bsm_nummaps=int(nummaps),
                bsm_seed=int(seed),
                bsm_maxtries_per_branch=int(maxtries_per_branch),
            )
        except Exception as exc:
            raise RuntimeError(
                "BioGeoBEARS BSM 运行失败。\n"
                "workdir: {workdir}\n"
                "treefile: {treefile}\n"
                "geogfile: {geogfile}\n"
                "areas_json: {areas_json}\n"
                "model: {model}\n"
                "{msg}".format(
                    workdir=run_files.workdir,
                    treefile=run_files.tree_path,
                    geogfile=run_files.geog_path,
                    areas_json=run_files.areas_json_path,
                    model=run_files.model_name,
                    msg=str(exc),
                )
            )

        return self.bsm_event_parser.parse(
            output_json_path=run_files.output_json_path,
            bsm_dir=bsm_dir,
        )

    def load_existing_bsm_events(self, source_path):
        """Load an existing BioGeoBEARS BSM output directory into RASP.

        The normal in-app BSM runner writes CSV files. Older/manual runs may
        only contain BioGeoBEARS Rdata event tables, so this method exports
        those tables to the same CSV format first, then reuses the normal
        parser.
        """
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError("BSM source path does not exist: %s" % source)
        bsm_dir = self._resolve_existing_bsm_directory(source)
        if bsm_dir is None:
            raise FileNotFoundError(
                "Could not find BSM event tables. Select a directory containing "
                "bsm_ana_events.csv / bsm_clado_events.csv, RES_ana_events_tables.Rdata / "
                "RES_clado_events_tables.Rdata, or a run directory containing bsm/bsm_output."
            )

        ana_csv = bsm_dir / "bsm_ana_events.csv"
        clado_csv = bsm_dir / "bsm_clado_events.csv"
        if not (ana_csv.exists() and clado_csv.exists()):
            self._export_existing_bsm_rdata_to_csv(bsm_dir)

        summary_path = bsm_dir / "bsm_summary.json"
        if not summary_path.exists():
            self._write_existing_bsm_summary(bsm_dir)

        output_json_path = self._find_existing_bgb_output_json(source, bsm_dir)
        return self._load_existing_bsm_lightweight(
            output_json_path=output_json_path,
            bsm_dir=bsm_dir,
            source_path=source,
        )

    def _resolve_existing_bsm_directory(self, source):
        source = Path(source)
        candidates = []
        if source.is_file():
            candidates.append(source.parent)
        else:
            candidates.extend([
                source,
                source / "bsm",
                source / "bsm_output",
            ])
        for candidate in candidates:
            if self._has_existing_bsm_tables(candidate):
                return candidate
        return None

    def _has_existing_bsm_tables(self, directory):
        directory = Path(directory)
        if not directory.exists() or not directory.is_dir():
            return False
        has_csv = (
            (directory / "bsm_ana_events.csv").exists()
            and (directory / "bsm_clado_events.csv").exists()
        )
        has_rdata = (
            (directory / "RES_ana_events_tables.Rdata").exists()
            and (directory / "RES_clado_events_tables.Rdata").exists()
        )
        return bool(has_csv or has_rdata)

    def _export_existing_bsm_rdata_to_csv(self, bsm_dir):
        bsm_dir = Path(bsm_dir)
        ana_rdata = bsm_dir / "RES_ana_events_tables.Rdata"
        clado_rdata = bsm_dir / "RES_clado_events_tables.Rdata"
        if not (ana_rdata.exists() and clado_rdata.exists()):
            raise FileNotFoundError("Missing RES_ana_events_tables.Rdata or RES_clado_events_tables.Rdata in %s" % bsm_dir)

        rscript = self.runner.resolve_rscript_path()
        script_path = bsm_dir / "rasp_export_existing_bsm_events.R"
        script_path.write_text(textwrap.dedent(r"""
            args <- commandArgs(trailingOnly=TRUE)
            bsm_dir <- normalizePath(args[[1]], winslash="/", mustWork=TRUE)

            stringify_bsm_table <- function(df) {
              if (is.null(df) || !is.data.frame(df)) {
                return(data.frame())
              }
              for (nm in names(df)) {
                if (is.list(df[[nm]]) && !is.data.frame(df[[nm]])) {
                  df[[nm]] <- vapply(
                    df[[nm]],
                    function(x) paste(as.character(unlist(x)), collapse = "|"),
                    FUN.VALUE = character(1)
                  )
                }
              }
              df
            }

            rbind_bsm_tables <- function(tables) {
              pieces <- list()
              for (i in seq_along(tables)) {
                df <- stringify_bsm_table(tables[[i]])
                if (!is.null(df) && is.data.frame(df) && nrow(df) > 0) {
                  df$sample_id <- i
                  pieces[[length(pieces) + 1]] <- df
                }
              }
              if (length(pieces) == 0) {
                return(data.frame(sample_id = integer()))
              }
              do.call(rbind, pieces)
            }

            load_table <- function(path, expected_name) {
              env <- new.env(parent=emptyenv())
              load(path, envir=env)
              if (exists(expected_name, envir=env, inherits=FALSE)) {
                return(get(expected_name, envir=env, inherits=FALSE))
              }
              names <- ls(env)
              for (nm in names) {
                value <- get(nm, envir=env, inherits=FALSE)
                if (is.list(value)) {
                  return(value)
                }
              }
              stop(sprintf("No list-like BSM table found in %s", path))
            }

            ana <- load_table(file.path(bsm_dir, "RES_ana_events_tables.Rdata"), "RES_ana_events_tables")
            clado <- load_table(file.path(bsm_dir, "RES_clado_events_tables.Rdata"), "RES_clado_events_tables")
            all_ana <- rbind_bsm_tables(ana)
            all_clado <- rbind_bsm_tables(clado)
            write.csv(all_ana, file=file.path(bsm_dir, "bsm_ana_events.csv"), row.names=FALSE)
            write.csv(all_clado, file=file.path(bsm_dir, "bsm_clado_events.csv"), row.names=FALSE)
            cat(sprintf("ana_maps=%d ana_rows=%d\n", length(ana), nrow(all_ana)))
            cat(sprintf("clado_maps=%d clado_rows=%d\n", length(clado), nrow(all_clado)))
        """).strip() + "\n", encoding="utf-8")

        completed = subprocess.run(
            [str(rscript), str(script_path), str(bsm_dir)],
            cwd=str(bsm_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        (bsm_dir / "rasp_export_existing_bsm_events.stdout.log").write_text(completed.stdout or "", encoding="utf-8")
        (bsm_dir / "rasp_export_existing_bsm_events.stderr.log").write_text(completed.stderr or "", encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(
                "Failed to export existing BSM Rdata tables to CSV.\n"
                "directory: %s\n%s%s" % (bsm_dir, completed.stdout or "", completed.stderr or "")
            )

    def _write_existing_bsm_summary(self, bsm_dir):
        import csv
        import json

        bsm_dir = Path(bsm_dir)
        summary = {
            "enabled": True,
            "directory": str(bsm_dir),
            "source": "loaded_existing_bsm_result",
        }
        for key, filename in (("ana", "bsm_ana_events.csv"), ("clado", "bsm_clado_events.csv")):
            path = bsm_dir / filename
            sample_ids = set()
            row_count = 0
            if path.exists():
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        row_count += 1
                        sample_id = str(row.get("sample_id", "") or row.get("trynum", "") or "").strip()
                        if sample_id:
                            sample_ids.add(sample_id)
            summary["%s_rows" % key] = row_count
            summary["%s_maps" % key] = len(sample_ids)
        summary["nummaps"] = max(int(summary.get("ana_maps", 0) or 0), int(summary.get("clado_maps", 0) or 0))
        (bsm_dir / "bsm_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _load_existing_bsm_lightweight(self, *, output_json_path, bsm_dir, source_path, preview_limit=5000):
        import csv
        import json
        from collections import Counter, defaultdict

        from application.services.bsm_dispersal_network_service import BSMDispersalNetworkService
        from domain.models.biogeobears_event_result import BioGeoBEARSEventResult

        bsm_dir = Path(bsm_dir)
        result = BioGeoBEARSEventResult(
            source_output_json_path=str(output_json_path),
            source_run_directory=str(Path(source_path)),
        )
        result.summary = {"enabled": True, "directory": str(bsm_dir), "source": "loaded_existing_bsm_result"}
        summary_path = bsm_dir / "bsm_summary.json"
        if summary_path.exists():
            try:
                result.summary.update(json.loads(summary_path.read_text(encoding="utf-8")))
            except Exception as exc:
                result.parse_warnings.append("Could not read BSM summary JSON: %s" % exc)

        edge_rows, node_rows = self._load_precomputed_bsm_network_tables(bsm_dir)
        full_scan_required = not bool(edge_rows)
        raw_tables = {}
        events = []
        event_type_counts = Counter()
        route_counts = Counter()
        time_buckets = defaultdict(Counter)
        total_rows = {}
        sample_ids_by_scope = defaultdict(set)

        for scope, filename in (("anagenetic", "bsm_ana_events.csv"), ("cladogenetic", "bsm_clado_events.csv")):
            path = bsm_dir / filename
            preview_rows = []
            row_count = 0
            if path.exists():
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        clean_row = {str(k): self.bsm_event_parser._clean_csv_value(v) for k, v in dict(row).items()}
                        row_count += 1
                        sample_id = clean_row.get("sample_id") or clean_row.get("trynum") or ""
                        if sample_id:
                            sample_ids_by_scope[scope].add(str(sample_id))
                        event = self.bsm_event_parser._row_to_event(scope, clean_row)
                        if event is not None:
                            event_type_counts[self.bsm_event_parser._event_count_key(event)] += 1
                            route = self.bsm_event_parser._event_route_key(event)
                            if route:
                                route_counts[route] += 1
                            if event.time is not None:
                                time_key = round(float(event.time), 6)
                                time_buckets[time_key][self.bsm_event_parser._event_count_key(event)] += 1
                                time_buckets[time_key]["total"] += 1
                            if len(events) < int(preview_limit):
                                events.append(event)
                        if len(preview_rows) < int(preview_limit):
                            preview_rows.append(clean_row)
                        if not full_scan_required and len(preview_rows) >= int(preview_limit):
                            break
            total_rows[scope] = row_count
            if preview_rows:
                raw_tables[scope] = preview_rows

        result.raw_tables = raw_tables
        result.events = events
        result.event_type_counts = dict(event_type_counts)
        result.route_counts = dict(route_counts.most_common(200))
        result.time_series = self._time_series_from_buckets(time_buckets)
        if full_scan_required:
            result.summary["ana_rows"] = total_rows.get("anagenetic", result.summary.get("ana_rows", 0))
            result.summary["clado_rows"] = total_rows.get("cladogenetic", result.summary.get("clado_rows", 0))
            result.summary["ana_maps"] = len(sample_ids_by_scope.get("anagenetic", set())) or result.summary.get("ana_maps", 0)
            result.summary["clado_maps"] = len(sample_ids_by_scope.get("cladogenetic", set())) or result.summary.get("clado_maps", 0)
        else:
            result.summary.setdefault("ana_rows", total_rows.get("anagenetic", 0))
            result.summary.setdefault("clado_rows", total_rows.get("cladogenetic", 0))
            result.summary.setdefault("ana_maps", len(sample_ids_by_scope.get("anagenetic", set())))
            result.summary.setdefault("clado_maps", len(sample_ids_by_scope.get("cladogenetic", set())))
        result.summary["nummaps"] = max(int(result.summary.get("ana_maps", 0) or 0), int(result.summary.get("clado_maps", 0) or 0))
        if int(total_rows.get("anagenetic", 0) + total_rows.get("cladogenetic", 0)) > int(preview_limit):
            result.parse_warnings.append(
                "Existing BSM result was loaded in lightweight mode: event/raw tables show a preview, while network summaries use aggregated tables."
            )

        if not edge_rows:
            edge_rows = self._aggregate_existing_bsm_network_edges(bsm_dir, result.summary.get("nummaps", 1))
        result.precomputed_bsm_network_edges = edge_rows
        result.precomputed_bsm_node_rows = node_rows
        self.bsm_event_parser._attach_text(result)
        return result

    def _time_series_from_buckets(self, time_buckets):
        rows = []
        for time_key in sorted(time_buckets.keys()):
            counter = time_buckets[time_key]
            row = {"time": time_key}
            for key, value in sorted(counter.items()):
                row[key] = int(value)
            rows.append(row)
        return rows

    def _load_precomputed_bsm_network_tables(self, bsm_dir):
        import csv

        bsm_dir = Path(bsm_dir)
        search_roots = [
            bsm_dir,
            bsm_dir.parent,
            bsm_dir.parent / "fig2b_reproduction",
        ]
        edge_path = None
        node_path = None
        for root in search_roots:
            candidate = root / "fig2b_dispersal_edges.csv"
            if candidate.exists():
                edge_path = candidate
            candidate = root / "fig2b_node_richness.csv"
            if candidate.exists():
                node_path = candidate
        edge_rows = self._read_csv_rows(edge_path) if edge_path else []
        node_rows = self._read_csv_rows(node_path) if node_path else []
        return edge_rows, node_rows

    def _read_csv_rows(self, path):
        import csv

        if not path:
            return []
        path = Path(path)
        rows = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append({str(k): self.bsm_event_parser._clean_csv_value(v) for k, v in dict(row).items()})
        return rows

    def _aggregate_existing_bsm_network_edges(self, bsm_dir, nummaps):
        import csv

        from application.services.bsm_dispersal_network_service import BSMDispersalNetworkService

        network_service = BSMDispersalNetworkService()
        bsm_dir = Path(bsm_dir)
        area_codes = self._infer_bsm_area_codes_from_csvs(bsm_dir, network_service)
        edge_acc = {}

        ana_path = bsm_dir / "bsm_ana_events.csv"
        if ana_path.exists():
            with ana_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    clean_row = {str(k): self.bsm_event_parser._clean_csv_value(v) for k, v in dict(row).items()}
                    target = clean_row.get("dispersal_to") or clean_row.get("new_area_num_1based")
                    source_range = clean_row.get("current_rangetxt") or clean_row.get("sampled_states_AT_brbots")
                    if target and source_range:
                        network_service._add_split_source_edge(edge_acc, source_range, target, area_codes, "anagenetic")

        clado_path = bsm_dir / "bsm_clado_events.csv"
        if clado_path.exists():
            with clado_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    clean_row = {str(k): self.bsm_event_parser._clean_csv_value(v) for k, v in dict(row).items()}
                    event_type = clean_row.get("clado_event_type") or clean_row.get("event_type") or ""
                    if event_type != network_service.FOUNDER_EVENT:
                        continue
                    target = clean_row.get("clado_dispersal_to") or clean_row.get("dispersal_to")
                    text = clean_row.get("clado_event_txt") or clean_row.get("event_txt") or ""
                    source_range = text.split("->", 1)[0].strip() if "->" in text else clean_row.get("sampled_states_AT_brbots", "")
                    if target and source_range:
                        network_service._add_split_source_edge(edge_acc, source_range, target, area_codes, "founder")

        edge_rows = []
        denom = float(nummaps or 1)
        for key in sorted(edge_acc.keys()):
            row = edge_acc[key]
            total = float(row.get("anagenetic_count", 0.0)) + float(row.get("founder_count", 0.0))
            edge_rows.append({
                "source_area": row.get("source_area", ""),
                "target_area": row.get("target_area", ""),
                "anagenetic_count": row.get("anagenetic_count", 0.0),
                "founder_count": row.get("founder_count", 0.0),
                "total_count": total,
                "mean_per_map": total / denom,
            })
        return edge_rows

    def _infer_bsm_area_codes_from_csvs(self, bsm_dir, network_service):
        import csv

        codes = []
        for filename in ("bsm_ana_events.csv", "bsm_clado_events.csv"):
            path = Path(bsm_dir) / filename
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for idx, row in enumerate(reader):
                    for key in ("current_rangetxt", "new_rangetxt", "dispersal_to", "clado_dispersal_to", "clado_event_txt", "sampled_states_AT_brbots"):
                        for code in network_service._extract_event_area_codes(row.get(key, "")):
                            if code and code not in codes:
                                codes.append(code)
                    if idx >= 20000 and codes:
                        break
        return codes

    def _find_existing_bgb_output_json(self, source, bsm_dir):
        source = Path(source)
        bsm_dir = Path(bsm_dir)
        candidates = []
        if source.is_file() and source.suffix.lower() == ".json":
            candidates.append(source)
        for root in [source if source.is_dir() else source.parent, bsm_dir.parent, bsm_dir]:
            candidates.extend([
                root / "output.json",
                root / "bgb_output.json",
                root / "result.json",
                root / "biogeobears_output.json",
            ])
            candidates.extend(sorted(root.glob("*output*.json")))
        for path in candidates:
            if path.exists():
                return path
        return bsm_dir / "loaded_existing_bsm_output.json"

    def build_run_files(
        self,
        *,
        tree,
        matrix,
        run_name,
        model_name,
        max_range_size,
        include_null_range,
        null_range_mode,
        cores,
        include_ranges,
        exclude_ranges,
        period_times,
        time_matrix_kind,
        period_matrices,
        root_age,
        scale_tree_to_root_age=False,
    ):
        self.work_root.mkdir(parents=True, exist_ok=True)
        return self.dataset_builder.build(
            tree=tree,
            matrix=matrix,
            output_dir=self.work_root,
            run_name=run_name,
            model_name=model_name,
            max_range_size=max_range_size,
            include_null_range=include_null_range,
            null_range_mode=null_range_mode,
            cores=cores,
            include_ranges=include_ranges,
            exclude_ranges=exclude_ranges,
            period_times=period_times,
            time_matrix_kind=time_matrix_kind,
            period_matrices=period_matrices,
            root_age=root_age,
            scale_tree_to_root_age=scale_tree_to_root_age,
        )

    def run_batch(
        self,
        run_files_list,
        *,
        batch_workdir,
        batch_name="batch",
        job_ids=None,
        progress_callback=None,
    ):
        return self.runner.run_batch(
            run_files_list,
            batch_workdir=batch_workdir,
            batch_name=batch_name,
            job_ids=job_ids,
            progress_callback=progress_callback,
        )

    def parse_run_files(self, *, tree, run_files):
        result = self.output_parser.parse(
            reference_tree=tree,
            output_json_path=run_files.output_json_path,
        )
        result.result_note += " workdir=%s" % run_files.workdir
        return result
