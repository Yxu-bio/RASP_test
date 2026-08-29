from datetime import datetime
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import textwrap
import time

from application.services.biogeobears_dataset_builder import BioGeoBEARSDatasetBuilder
from infrastructure.biogeobears.biogeobears_bsm_event_parser import BioGeoBEARSBSMEventParser
from infrastructure.biogeobears.biogeobears_output_parser import BioGeoBEARSOutputParser
from infrastructure.biogeobears.biogeobears_runner import BioGeoBEARSRunner
from infrastructure.run_provenance import write_run_provenance


class BioGeoBEARSAnalysisService:
    BSM_INDEX_FORMAT = "rasp5_biogeobears_bsm_event_index"
    BSM_INDEX_VERSION = 2
    BSM_INDEX_FILENAME = "rasp5_bsm_event_index.json"
    BSM_INDEX_SAMPLE_BYTES = 65536

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
        maxnum_maps_to_try=None,
        maxtries_per_branch=40000,
        scale_tree_to_root_age=False,
        progress_callback=None,
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
                bsm_maxnum_maps_to_try=(
                    None
                    if maxnum_maps_to_try is None
                    else int(maxnum_maps_to_try)
                ),
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

        return self._load_existing_bsm_lightweight(
            output_json_path=run_files.output_json_path,
            bsm_dir=bsm_dir,
            source_path=run_files.workdir,
            progress_callback=progress_callback,
        )

    def load_existing_bsm_events(
        self,
        source_path,
        progress_callback=None,
        force_rebuild_index=False,
    ):
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

        output_json_path = self._find_existing_bgb_output_json(source, bsm_dir)
        return self._load_existing_bsm_lightweight(
            output_json_path=output_json_path,
            bsm_dir=bsm_dir,
            source_path=source,
            progress_callback=progress_callback,
            force_rebuild_index=force_rebuild_index,
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
        write_run_provenance(
            bsm_dir,
            analysis="BioGeoBEARS existing BSM RData export",
            engine_paths={
                "rscript": rscript,
                "bsm_rdata_export_script": script_path,
            },
            extra={
                "source_ana_rdata": ana_rdata.name,
                "source_clado_rdata": clado_rdata.name,
            },
            filename="rasp5_bsm_export_provenance.json",
        )

    def _load_existing_bsm_lightweight(
        self,
        *,
        output_json_path,
        bsm_dir,
        source_path,
        preview_limit=5000,
        progress_callback=None,
        force_rebuild_index=False,
    ):
        import csv
        import json
        from collections import Counter, defaultdict

        from application.services.bsm_dispersal_network_service import BSMDispersalNetworkService
        from domain.models.biogeobears_event_result import BioGeoBEARSEventResult

        bsm_dir = Path(bsm_dir)
        load_started = time.perf_counter()
        network_service = BSMDispersalNetworkService()
        result = BioGeoBEARSEventResult(
            source_output_json_path=str(output_json_path),
            source_run_directory=str(Path(source_path)),
        )
        result.summary = {"enabled": True, "directory": str(bsm_dir), "source": "loaded_existing_bsm_result"}
        if Path(output_json_path).exists():
            try:
                output_payload = json.loads(Path(output_json_path).read_text(encoding="utf-8"))
                output_attrs = dict(output_payload.get("attributes", {}) or {})
                result.source_model_name = self.bsm_event_parser._format_model_name(output_attrs)
                result.summary.update({
                    "source_treefile": str(output_attrs.get("treefile", "") or ""),
                    "source_tip_count": output_attrs.get("tip_count", ""),
                    "source_internal_node_count": output_attrs.get("internal_node_count", ""),
                })
                output_area_names = [
                    str(value or "").strip()
                    for value in list(output_attrs.get("area_names", []) or [])
                    if str(value or "").strip()
                ]
                if output_area_names:
                    result.summary["area_names"] = output_area_names
                result.source_clade_keys = [
                    str(row.get("clade_key", "") or "")
                    for row in list(output_payload.get("node_results", []) or [])
                    if str(row.get("clade_key", "") or "")
                ]
            except Exception as exc:
                result.parse_warnings.append("Could not read source BioGeoBEARS output metadata: %s" % exc)
        summary_path = bsm_dir / "bsm_summary.json"
        if summary_path.exists():
            try:
                summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
                self.bsm_event_parser._validate_summary_schema(summary_payload)
                result.summary.update(summary_payload)
            except Exception as exc:
                result.parse_warnings.append("Could not read BSM summary JSON: %s" % exc)

        result.event_preview_limit = int(preview_limit)
        result.event_source_files = {
            "anagenetic": str(bsm_dir / "bsm_ana_events.csv"),
            "cladogenetic": str(bsm_dir / "bsm_clado_events.csv"),
        }
        self._emit_bsm_load_progress(progress_callback, 0, 100, "Checking BSM event index ...")
        if not force_rebuild_index:
            cached = self._load_bsm_index_cache(
                bsm_dir,
                int(preview_limit),
                output_json_path=output_json_path,
            )
            if cached is not None:
                self._restore_bsm_index_result(result, cached)
                if "network_edges_authoritative" not in cached:
                    result.precomputed_bsm_network_available = bool(
                        result.precomputed_bsm_network_edges
                    ) or self._bsm_authoritative_network_source_exists(bsm_dir)
                result.summary["load_index_status"] = "hit"
                result.summary["load_index_path"] = str(bsm_dir / self.BSM_INDEX_FILENAME)
                result.summary["load_elapsed_seconds"] = round(time.perf_counter() - load_started, 6)
                self.bsm_event_parser._attach_text(result)
                self._emit_bsm_load_progress(progress_callback, 100, 100, "BSM event index loaded")
                return result

        edge_rows, node_rows, precomputed_edge_table_available = (
            self._load_precomputed_bsm_network_tables(bsm_dir)
        )
        raw_tables = {}
        events = []
        event_type_counts = Counter()
        route_counts = Counter()
        time_buckets = defaultdict(Counter)
        total_rows = {}
        sample_ids_by_scope = defaultdict(set)
        preview_event_counts = defaultdict(int)
        normalized_event_counts_by_scope = defaultdict(int)
        time_bucket_decimals = 6
        compact_source_path = bsm_dir / "bsm_source_assigned_dispersal_events.csv"
        scan_area_codes = self._bsm_area_codes_from_metadata(bsm_dir, result.summary)
        raw_network_fallback = (
            not compact_source_path.exists()
            and not precomputed_edge_table_available
        )
        scan_edge_acc = {} if raw_network_fallback else None
        discover_scan_area_codes = bool(scan_edge_acc is not None and not scan_area_codes)
        scan_source_methods = set()
        scan_unresolved_numeric_area_ids = [False]
        expected_rows = int(result.summary.get("ana_rows", 0) or 0) + int(
            result.summary.get("clado_rows", 0) or 0
        )
        scanned_rows = 0
        self._emit_bsm_load_progress(
            progress_callback,
            0,
            expected_rows,
            "Building BSM event index ...",
        )

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
                        if scan_edge_acc is not None:
                            if discover_scan_area_codes:
                                self._extend_bsm_area_codes_from_row(
                                    clean_row,
                                    scan_area_codes,
                                    network_service,
                                )
                            self._accumulate_bsm_network_row(
                                scope,
                                clean_row,
                                scan_area_codes,
                                network_service,
                                scan_edge_acc,
                                scan_source_methods,
                                allow_numeric_area_ids=not discover_scan_area_codes,
                                unresolved_numeric_area_ids=scan_unresolved_numeric_area_ids,
                            )
                        if event is not None:
                            normalized_event_counts_by_scope[scope] += 1
                            event_type_counts[self.bsm_event_parser._event_count_key(event)] += 1
                            route = self.bsm_event_parser._event_route_key(event)
                            if route:
                                route_counts[route] += 1
                            if event.time is not None:
                                time_key = round(float(event.time), time_bucket_decimals)
                                time_buckets[time_key][self.bsm_event_parser._event_count_key(event)] += 1
                                time_buckets[time_key]["total"] += 1
                            if preview_event_counts[scope] < int(preview_limit):
                                events.append(event)
                                preview_event_counts[scope] += 1
                        if len(preview_rows) < int(preview_limit):
                            preview_rows.append(clean_row)
                        scanned_rows += 1
                        if scanned_rows % 25000 == 0:
                            self._emit_bsm_load_progress(
                                progress_callback,
                                scanned_rows,
                                expected_rows,
                                "Indexing BSM rows: %s" % format(scanned_rows, ","),
                            )
            total_rows[scope] = row_count
            if preview_rows:
                raw_tables[scope] = preview_rows

        result.raw_tables = raw_tables
        result.events = events
        result.event_row_counts = dict(total_rows)
        normalized_event_count = int(sum(event_type_counts.values()))
        result.events_complete = all(
            int(normalized_event_counts_by_scope.get(scope, 0) or 0)
            <= int(preview_event_counts.get(scope, 0) or 0)
            for scope in ("anagenetic", "cladogenetic")
        )
        result.raw_tables_complete = all(
            int(total_rows.get(scope, 0) or 0) <= len(raw_tables.get(scope, []) or [])
            for scope in ("anagenetic", "cladogenetic")
        )
        result.event_type_counts = dict(event_type_counts)
        result.route_counts = dict(route_counts.most_common(200))
        result.time_series = self._time_series_from_buckets(time_buckets)
        result.summary["ana_rows"] = total_rows.get("anagenetic", result.summary.get("ana_rows", 0))
        result.summary["clado_rows"] = total_rows.get("cladogenetic", result.summary.get("clado_rows", 0))
        result.summary["ana_maps"] = len(sample_ids_by_scope.get("anagenetic", set())) or result.summary.get("ana_maps", 0)
        result.summary["clado_maps"] = len(sample_ids_by_scope.get("cladogenetic", set())) or result.summary.get("clado_maps", 0)
        result.summary["nummaps"] = max(int(result.summary.get("ana_maps", 0) or 0), int(result.summary.get("clado_maps", 0) or 0))
        result.summary["normalized_event_count"] = normalized_event_count
        result.summary["normalized_event_counts_by_scope"] = dict(normalized_event_counts_by_scope)
        result.summary["time_bucket_decimals"] = time_bucket_decimals
        result.summary["event_preview_count"] = len(events)
        result.summary["event_preview_counts"] = dict(preview_event_counts)
        result.summary["events_complete"] = bool(result.events_complete)
        if compact_source_path.exists():
            edge_rows = self._aggregate_existing_bsm_network_edges(
                bsm_dir,
                result.summary.get("nummaps", 1),
            )
        elif not precomputed_edge_table_available and scan_edge_acc is not None:
            edge_rows = self._bsm_edge_rows_from_accumulator(
                scan_edge_acc,
                scan_source_methods,
                result.summary.get("nummaps", 1),
                network_service,
            )
        reported_source_assignment_method = str(
            result.summary.get("network_source_assignment_method", "")
            or result.summary.get("source_assignment_method", "")
            or ""
        ).strip()
        edge_methods = set(
            str(row.get("source_assignment_method", "") or "").strip()
            for row in list(edge_rows or [])
            if str(row.get("source_assignment_method", "") or "").strip()
        )
        if edge_methods:
            source_assignment_method = network_service._combined_source_assignment_method(edge_methods)
        elif reported_source_assignment_method:
            source_assignment_method = reported_source_assignment_method
        else:
            source_assignment_method = network_service.SOURCE_METHOD_FRACTIONAL
        if (
            reported_source_assignment_method
            and reported_source_assignment_method != source_assignment_method
        ):
            result.parse_warnings.append(
                "BSM source-assignment metadata disagrees with the authoritative edge input; "
                "using %s instead of %s."
                % (source_assignment_method, reported_source_assignment_method)
            )
        result.summary["network_source_assignment_method"] = source_assignment_method
        result.precomputed_bsm_network_edges = edge_rows
        result.precomputed_bsm_node_rows = node_rows
        result.precomputed_bsm_network_available = True
        if scan_unresolved_numeric_area_ids[0]:
            result.parse_warnings.append(
                "Some BSM network rows used numeric one-based area ids, but no authoritative "
                "area order was available; those rows were not assigned to guessed areas."
            )
        result.summary["load_index_status"] = "rebuilt"
        result.summary["load_index_path"] = str(bsm_dir / self.BSM_INDEX_FILENAME)
        result.summary["load_elapsed_seconds"] = round(time.perf_counter() - load_started, 6)
        self._emit_bsm_load_progress(progress_callback, 95, 100, "Saving BSM event index ...")
        if not self._write_bsm_index_cache(bsm_dir, result):
            result.summary["load_index_status"] = "rebuilt_not_saved"
            result.parse_warnings.append(
                "The BSM event index could not be saved; this result will require another full scan next time."
            )
        self.bsm_event_parser._attach_text(result)
        self._emit_bsm_load_progress(progress_callback, 100, 100, "BSM event index ready")
        return result

    def _emit_bsm_load_progress(self, callback, completed, total, message):
        if callback is None:
            return
        callback(int(completed or 0), int(total or 0), str(message or ""))

    def _bsm_index_source_paths(self, bsm_dir, output_json_path=None):
        bsm_dir = Path(bsm_dir)
        paths = [
            bsm_dir / "bsm_ana_events.csv",
            bsm_dir / "bsm_clado_events.csv",
            bsm_dir / "bsm_summary.json",
            bsm_dir / "bsm_source_assigned_dispersal_events.csv",
            bsm_dir / "areas.json",
            bsm_dir / "geog.data",
            bsm_dir.parent / "areas.json",
            bsm_dir.parent / "geog.data",
            bsm_dir.parent / "bgb_result.json",
            bsm_dir.parent / "output.json",
        ]
        if output_json_path:
            paths.append(Path(output_json_path))
        search_roots = [bsm_dir, bsm_dir.parent, bsm_dir.parent / "fig2b_reproduction"]
        for root in search_roots:
            paths.extend([
                root / "fig2b_dispersal_edges.csv",
                root / "fig2b_node_richness.csv",
            ])
        unique = []
        seen = set()
        for path in paths:
            path = Path(path)
            if not path.exists() or not path.is_file():
                continue
            key = str(path.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(path)
        return unique

    def _bsm_index_file_signature(self, bsm_dir, path):
        bsm_dir = Path(bsm_dir)
        path = Path(path)
        stat = path.stat()
        sample_bytes = int(self.BSM_INDEX_SAMPLE_BYTES)
        with path.open("rb") as handle:
            first = handle.read(sample_bytes)
            if stat.st_size > sample_bytes:
                handle.seek(max(0, stat.st_size - sample_bytes))
                last = handle.read(sample_bytes)
            else:
                last = b""
        digest = hashlib.sha256(first + b"\0" + last).hexdigest().upper()
        return {
            "path": os.path.relpath(str(path), str(bsm_dir)).replace("\\", "/"),
            "size": int(stat.st_size),
            "mtime_ns": int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1000000000))),
            "sample_sha256": digest,
        }

    def _bsm_index_source_signatures(self, bsm_dir, output_json_path=None):
        return [
            self._bsm_index_file_signature(bsm_dir, path)
            for path in self._bsm_index_source_paths(bsm_dir, output_json_path=output_json_path)
        ]

    def _bsm_authoritative_network_source_exists(self, bsm_dir):
        bsm_dir = Path(bsm_dir)
        if (bsm_dir / "bsm_source_assigned_dispersal_events.csv").exists():
            return True
        for root in (bsm_dir, bsm_dir.parent, bsm_dir.parent / "fig2b_reproduction"):
            if (root / "fig2b_dispersal_edges.csv").exists():
                return True
        return False

    def _bsm_area_codes_from_metadata(self, bsm_dir, summary):
        import json

        codes = []

        def add_values(values):
            for value in list(values or []):
                code = str(value or "").strip()
                if code and code not in codes:
                    codes.append(code)

        add_values(dict(summary or {}).get("area_names", []))
        if codes:
            return codes

        bsm_dir = Path(bsm_dir)
        for path in (bsm_dir / "areas.json", bsm_dir.parent / "areas.json"):
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                add_values(payload.get("area_names", []))
            except (OSError, TypeError, ValueError):
                continue
            if codes:
                return codes

        for path in (bsm_dir / "geog.data", bsm_dir.parent / "geog.data"):
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8-sig") as handle:
                    header = handle.readline().strip()
            except OSError:
                continue
            if "(" in header and ")" in header:
                add_values(header.split("(", 1)[1].split(")", 1)[0].split())
            if codes:
                return codes
        return codes

    def _load_bsm_index_cache(self, bsm_dir, preview_limit, output_json_path=None):
        import json

        cache_path = Path(bsm_dir) / self.BSM_INDEX_FILENAME
        if not cache_path.exists():
            return None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if str(payload.get("format", "") or "") != self.BSM_INDEX_FORMAT:
                return None
            if int(payload.get("version", 0) or 0) != int(self.BSM_INDEX_VERSION):
                return None
            if int(payload.get("preview_limit", 0) or 0) != int(preview_limit):
                return None
            if list(payload.get("source_files", []) or []) != self._bsm_index_source_signatures(
                bsm_dir,
                output_json_path=output_json_path,
            ):
                return None
            data = payload.get("data")
            data_sha256 = str(payload.get("data_sha256", "") or "").upper()
            if len(data_sha256) != 64:
                return None
            canonical_data = json.dumps(
                data,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            if hashlib.sha256(canonical_data).hexdigest().upper() != data_sha256:
                return None
            if not self._is_valid_bsm_index_data(data):
                return None
            return data
        except (OSError, ValueError, TypeError):
            return None

    def _is_valid_bsm_index_data(self, data):
        if not isinstance(data, dict):
            return False
        required_types = {
            "event_row_counts": dict,
            "events_complete": bool,
            "raw_tables_complete": bool,
            "events": list,
            "raw_tables": dict,
            "computed_summary": dict,
            "event_type_counts": dict,
            "route_counts": dict,
            "time_series": list,
            "network_edges": list,
            "network_nodes": list,
        }
        for key, expected_type in required_types.items():
            if not isinstance(data.get(key), expected_type):
                return False
        if any(not isinstance(row, dict) for row in data["events"]):
            return False
        event_keys = {
            "event_scope", "sample_id", "event_type", "event_text", "time",
            "node", "branch", "source_range", "target_range", "dispersal_to",
            "extirpation_from",
        }
        if any(not event_keys.issubset(set(row.keys())) for row in data["events"]):
            return False
        if any(not isinstance(rows, list) for rows in data["raw_tables"].values()):
            return False
        if any(
            not isinstance(row, dict)
            for rows in data["raw_tables"].values()
            for row in rows
        ):
            return False
        if any(not isinstance(row, dict) for row in data["time_series"]):
            return False
        if any(
            "time" not in row
            or "total" not in row
            or not isinstance(row.get("time"), (int, float))
            or not isinstance(row.get("total"), int)
            or int(row.get("total", 0)) < 0
            for row in data["time_series"]
        ):
            return False
        if any(not isinstance(row, dict) for row in data["network_edges"]):
            return False
        if any(
            not any(key in row for key in ("source_area", "from", "source"))
            or not any(key in row for key in ("target_area", "to", "target"))
            or not any(
                key in row
                for key in (
                    "total_count", "anagenetic_count", "ana_count",
                    "founder_count", "clado_count",
                )
            )
            for row in data["network_edges"]
        ):
            return False
        if any(not isinstance(row, dict) for row in data["network_nodes"]):
            return False
        if any(
            not any(key in row for key in ("area_code", "area"))
            for row in data["network_nodes"]
        ):
            return False
        if "network_edges_authoritative" in data and not isinstance(
            data["network_edges_authoritative"], bool
        ):
            return False
        summary = data["computed_summary"]
        if int(summary.get("time_bucket_decimals", 0) or 0) != 6:
            return False
        try:
            normalized_event_count = int(summary.get("normalized_event_count", -1))
            event_type_total = sum(int(value) for value in data["event_type_counts"].values())
            preview_count = int(summary.get("event_preview_count", -1))
        except (TypeError, ValueError):
            return False
        if normalized_event_count < 0 or event_type_total != normalized_event_count:
            return False
        if preview_count != len(data["events"]):
            return False
        if bool(data["events_complete"]) and preview_count != normalized_event_count:
            return False
        for value in data["event_row_counts"].values():
            try:
                if int(value) < 0:
                    return False
            except (TypeError, ValueError):
                return False
        return True

    def _event_to_bsm_index_row(self, event):
        return {
            "event_scope": str(getattr(event, "event_scope", "") or ""),
            "sample_id": str(getattr(event, "sample_id", "") or ""),
            "event_type": str(getattr(event, "event_type", "") or ""),
            "event_text": str(getattr(event, "event_text", "") or ""),
            "time": getattr(event, "time", None),
            "node": str(getattr(event, "node", "") or ""),
            "branch": str(getattr(event, "branch", "") or ""),
            "source_range": str(getattr(event, "source_range", "") or ""),
            "target_range": str(getattr(event, "target_range", "") or ""),
            "dispersal_to": str(getattr(event, "dispersal_to", "") or ""),
            "extirpation_from": str(getattr(event, "extirpation_from", "") or ""),
        }

    def _bsm_index_computed_summary(self, result):
        keys = (
            "ana_rows",
            "clado_rows",
            "ana_maps",
            "clado_maps",
            "nummaps",
            "normalized_event_count",
            "normalized_event_counts_by_scope",
            "time_bucket_decimals",
            "event_preview_count",
            "event_preview_counts",
            "events_complete",
            "network_source_assignment_method",
        )
        summary = dict(getattr(result, "summary", {}) or {})
        return dict((key, summary.get(key)) for key in keys if key in summary)

    def _write_bsm_index_cache(self, bsm_dir, result):
        import json

        bsm_dir = Path(bsm_dir)
        cache_path = bsm_dir / self.BSM_INDEX_FILENAME
        temp_path = bsm_dir / (self.BSM_INDEX_FILENAME + ".tmp")
        data = {
            "event_row_counts": dict(getattr(result, "event_row_counts", {}) or {}),
            "events_complete": bool(getattr(result, "events_complete", True)),
            "raw_tables_complete": bool(getattr(result, "raw_tables_complete", True)),
            "events": [self._event_to_bsm_index_row(event) for event in list(getattr(result, "events", []) or [])],
            "raw_tables": dict(getattr(result, "raw_tables", {}) or {}),
            "computed_summary": self._bsm_index_computed_summary(result),
            "event_type_counts": dict(getattr(result, "event_type_counts", {}) or {}),
            "route_counts": dict(getattr(result, "route_counts", {}) or {}),
            "time_series": list(getattr(result, "time_series", []) or []),
            "network_edges": list(getattr(result, "precomputed_bsm_network_edges", []) or []),
            "network_nodes": list(getattr(result, "precomputed_bsm_node_rows", []) or []),
            "network_edges_authoritative": bool(
                getattr(result, "precomputed_bsm_network_available", False)
            ),
        }
        canonical_data = json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        payload = {
            "format": self.BSM_INDEX_FORMAT,
            "version": self.BSM_INDEX_VERSION,
            "created_at": datetime.now().isoformat(),
            "preview_limit": int(getattr(result, "event_preview_limit", 0) or 0),
            "source_files": self._bsm_index_source_signatures(
                bsm_dir,
                output_json_path=getattr(result, "source_output_json_path", ""),
            ),
            "data_sha256": hashlib.sha256(canonical_data).hexdigest().upper(),
            "data": data,
        }
        try:
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            os.replace(str(temp_path), str(cache_path))
            return True
        except OSError:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
            return False

    def _restore_bsm_index_result(self, result, data):
        from domain.models.biogeobears_event_result import BioGeoBEARSEventRecord

        result.event_row_counts = dict(data.get("event_row_counts", {}) or {})
        result.events_complete = bool(data.get("events_complete", False))
        result.raw_tables_complete = bool(data.get("raw_tables_complete", False))
        result.events = [
            BioGeoBEARSEventRecord(
                event_scope=str(row.get("event_scope", "") or ""),
                sample_id=str(row.get("sample_id", "") or ""),
                event_type=str(row.get("event_type", "") or ""),
                event_text=str(row.get("event_text", "") or ""),
                time=row.get("time"),
                node=str(row.get("node", "") or ""),
                branch=str(row.get("branch", "") or ""),
                source_range=str(row.get("source_range", "") or ""),
                target_range=str(row.get("target_range", "") or ""),
                dispersal_to=str(row.get("dispersal_to", "") or ""),
                extirpation_from=str(row.get("extirpation_from", "") or ""),
            )
            for row in list(data.get("events", []) or [])
        ]
        result.raw_tables = dict(data.get("raw_tables", {}) or {})
        result.summary.update(dict(data.get("computed_summary", {}) or {}))
        result.event_type_counts = dict(data.get("event_type_counts", {}) or {})
        result.route_counts = dict(data.get("route_counts", {}) or {})
        result.time_series = list(data.get("time_series", []) or [])
        result.precomputed_bsm_network_edges = list(data.get("network_edges", []) or [])
        result.precomputed_bsm_node_rows = list(data.get("network_nodes", []) or [])
        result.precomputed_bsm_network_available = bool(
            data.get("network_edges_authoritative", False)
        )

    def _accumulate_bsm_network_row(
        self,
        scope,
        row,
        area_codes,
        network_service,
        edge_acc,
        source_methods,
        allow_numeric_area_ids=True,
        unresolved_numeric_area_ids=None,
    ):
        if scope == "anagenetic":
            event_type = row.get("event_type") or row.get("clado_event_type") or ""
            if event_type not in network_service.ANAGENETIC_TYPES:
                return
            target = row.get("dispersal_to") or row.get("new_area_num_1based")
            unique_source = row.get("ana_dispersal_from") or ""
            if not allow_numeric_area_ids and self._is_positive_integer_text(target):
                if unresolved_numeric_area_ids is not None:
                    unresolved_numeric_area_ids[0] = True
                return
            if not allow_numeric_area_ids and self._is_positive_integer_text(unique_source):
                unique_source = ""
                if unresolved_numeric_area_ids is not None:
                    unresolved_numeric_area_ids[0] = True
            if unique_source and network_service._add_unique_source_edge(
                edge_acc, unique_source, target, area_codes, "anagenetic"
            ):
                source_methods.add(network_service.SOURCE_METHOD_UNIQUE)
                return
            source_range = row.get("current_rangetxt") or row.get("sampled_states_AT_brbots")
            if target and source_range and network_service._add_split_source_edge(
                edge_acc, source_range, target, area_codes, "anagenetic"
            ):
                source_methods.add(network_service.SOURCE_METHOD_FRACTIONAL)
            return

        event_type = row.get("clado_event_type") or row.get("event_type") or ""
        if event_type != network_service.FOUNDER_EVENT:
            return
        target = row.get("clado_dispersal_to") or row.get("dispersal_to")
        unique_source = row.get("clado_dispersal_from") or ""
        if not allow_numeric_area_ids and self._is_positive_integer_text(target):
            if unresolved_numeric_area_ids is not None:
                unresolved_numeric_area_ids[0] = True
            return
        if not allow_numeric_area_ids and self._is_positive_integer_text(unique_source):
            unique_source = ""
            if unresolved_numeric_area_ids is not None:
                unresolved_numeric_area_ids[0] = True
        if unique_source and network_service._add_unique_source_edge(
            edge_acc, unique_source, target, area_codes, "founder"
        ):
            source_methods.add(network_service.SOURCE_METHOD_UNIQUE)
            return
        text = row.get("clado_event_txt") or row.get("event_txt") or ""
        source_range = text.split("->", 1)[0].strip() if "->" in text else row.get(
            "sampled_states_AT_brbots", ""
        )
        if target and source_range and network_service._add_split_source_edge(
            edge_acc, source_range, target, area_codes, "founder"
        ):
            source_methods.add(network_service.SOURCE_METHOD_FRACTIONAL)

    def _extend_bsm_area_codes_from_row(self, row, area_codes, network_service):
        for key in (
            "current_rangetxt",
            "new_rangetxt",
            "dispersal_to",
            "ana_dispersal_from",
            "clado_dispersal_from",
            "clado_dispersal_to",
            "clado_event_txt",
            "sampled_states_AT_brbots",
        ):
            for code in network_service._extract_event_area_codes(row.get(key, "")):
                if code and code not in area_codes:
                    area_codes.append(code)

    @staticmethod
    def _is_positive_integer_text(value):
        text = str(value or "").strip()
        if not text:
            return False
        try:
            number = float(text)
        except (TypeError, ValueError):
            return False
        return bool(number > 0 and number.is_integer())

    def _bsm_edge_rows_from_accumulator(
        self,
        edge_acc,
        source_methods,
        nummaps,
        network_service,
    ):
        rows = []
        denom = float(nummaps or 1)
        source_assignment_method = network_service._combined_source_assignment_method(source_methods)
        for key in sorted(edge_acc.keys()):
            row = edge_acc[key]
            total = float(row.get("anagenetic_count", 0.0)) + float(
                row.get("founder_count", 0.0)
            )
            rows.append({
                "source_area": row.get("source_area", ""),
                "target_area": row.get("target_area", ""),
                "anagenetic_count": row.get("anagenetic_count", 0.0),
                "founder_count": row.get("founder_count", 0.0),
                "total_count": total,
                "mean_per_map": total / denom,
                "source_assignment_method": source_assignment_method,
            })
        return rows

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
        return edge_rows, node_rows, edge_path is not None

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
        edge_acc = {}
        source_methods = set()

        source_event_path = bsm_dir / "bsm_source_assigned_dispersal_events.csv"
        compact_source_table_available = source_event_path.exists()
        if compact_source_table_available:
            with source_event_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                required_columns = set(["event_kind", "source_area", "target_area"])
                missing_columns = required_columns.difference(set(reader.fieldnames or []))
                if missing_columns:
                    raise ValueError(
                        "Invalid compact BSM source-assignment table; missing columns: %s"
                        % ", ".join(sorted(missing_columns))
                    )
                for row in reader:
                    clean_row = {
                        str(k): self.bsm_event_parser._clean_csv_value(v)
                        for k, v in dict(row).items()
                    }
                    event_kind = clean_row.get("event_kind") or ""
                    if event_kind not in ("anagenetic", "founder"):
                        continue
                    source = str(clean_row.get("source_area", "") or "").strip()
                    target = str(clean_row.get("target_area", "") or "").strip()
                    if source and target and source != target:
                        network_service._add_edge_weight(
                            edge_acc,
                            source,
                            target,
                            event_kind,
                            1.0,
                        )
                        source_methods.add(network_service.SOURCE_METHOD_UNIQUE)

            return self._bsm_edge_rows_from_accumulator(
                edge_acc,
                source_methods,
                nummaps,
                network_service,
            )

        area_codes = self._infer_bsm_area_codes_from_csvs(bsm_dir, network_service)
        if not compact_source_table_available:
            ana_path = bsm_dir / "bsm_ana_events.csv"
            if ana_path.exists():
                with ana_path.open("r", encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        clean_row = {
                            str(k): self.bsm_event_parser._clean_csv_value(v)
                            for k, v in dict(row).items()
                        }
                        event_type = clean_row.get("event_type") or clean_row.get("clado_event_type") or ""
                        if event_type not in network_service.ANAGENETIC_TYPES:
                            continue
                        target = clean_row.get("dispersal_to") or clean_row.get("new_area_num_1based")
                        unique_source = clean_row.get("ana_dispersal_from") or ""
                        if unique_source and network_service._add_unique_source_edge(
                            edge_acc, unique_source, target, area_codes, "anagenetic"
                        ):
                            source_methods.add(network_service.SOURCE_METHOD_UNIQUE)
                        else:
                            source_range = clean_row.get("current_rangetxt") or clean_row.get("sampled_states_AT_brbots")
                            if target and source_range and network_service._add_split_source_edge(
                                edge_acc, source_range, target, area_codes, "anagenetic"
                            ):
                                source_methods.add(network_service.SOURCE_METHOD_FRACTIONAL)

            clado_path = bsm_dir / "bsm_clado_events.csv"
            if clado_path.exists():
                with clado_path.open("r", encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        clean_row = {
                            str(k): self.bsm_event_parser._clean_csv_value(v)
                            for k, v in dict(row).items()
                        }
                        event_type = clean_row.get("clado_event_type") or clean_row.get("event_type") or ""
                        if event_type != network_service.FOUNDER_EVENT:
                            continue
                        target = clean_row.get("clado_dispersal_to") or clean_row.get("dispersal_to")
                        unique_source = clean_row.get("clado_dispersal_from") or ""
                        if unique_source and network_service._add_unique_source_edge(
                            edge_acc, unique_source, target, area_codes, "founder"
                        ):
                            source_methods.add(network_service.SOURCE_METHOD_UNIQUE)
                        else:
                            text = clean_row.get("clado_event_txt") or clean_row.get("event_txt") or ""
                            source_range = text.split("->", 1)[0].strip() if "->" in text else clean_row.get("sampled_states_AT_brbots", "")
                            if target and source_range and network_service._add_split_source_edge(
                                edge_acc, source_range, target, area_codes, "founder"
                            ):
                                source_methods.add(network_service.SOURCE_METHOD_FRACTIONAL)

        edge_rows = []
        denom = float(nummaps or 1)
        source_assignment_method = network_service._combined_source_assignment_method(source_methods)
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
                "source_assignment_method": source_assignment_method,
            })
        return edge_rows

    def _infer_bsm_area_codes_from_csvs(self, bsm_dir, network_service):
        import csv
        import json

        codes = []
        summary_path = Path(bsm_dir) / "bsm_summary.json"
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                for value in list(summary.get("area_names", []) or []):
                    code = str(value or "").strip()
                    if code and code not in codes:
                        codes.append(code)
            except (OSError, ValueError, TypeError):
                pass
        if codes:
            return codes
        for filename in ("bsm_ana_events.csv", "bsm_clado_events.csv"):
            path = Path(bsm_dir) / filename
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    for key in (
                        "current_rangetxt", "new_rangetxt", "dispersal_to",
                        "ana_dispersal_from", "clado_dispersal_from",
                        "clado_dispersal_to", "clado_event_txt", "sampled_states_AT_brbots"
                    ):
                        for code in network_service._extract_event_area_codes(row.get(key, "")):
                            if code and code not in codes:
                                codes.append(code)
        return codes

    def _find_existing_bgb_output_json(self, source, bsm_dir):
        source = Path(source)
        bsm_dir = Path(bsm_dir)
        candidates = []
        source_json = source if source.is_file() and source.suffix.lower() == ".json" else None
        for root in [source if source.is_dir() else source.parent, bsm_dir.parent, bsm_dir]:
            candidates.extend([
                root / "bgb_result.json",
                root / "output.json",
                root / "bgb_output.json",
                root / "result.json",
                root / "biogeobears_output.json",
            ])
            candidates.extend(sorted(root.glob("*output*.json")))
            candidates.extend(sorted(root.glob("*result*.json")))
        if source_json is not None:
            candidates.append(source_json)
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
