from datetime import datetime
from pathlib import Path
import re
import subprocess
import time

from domain.models.sdiva_config import EMPTY_STATE_TOKENS
from domain.models.sdiva_result import SDivaResult, SDivaNodeResult


class SDivaAnalysisService:
    """
    Legacy S-DIVA pipeline.

    Old RASP does not call single-tree DIVA repeatedly from the host program.
    It writes SDIVA_*.proc files, runs DIVA.exe in proc mode, then aggregates
    the generated *.diva files with the do_analysis logic.  This class follows
    that pipeline and keeps the Python layer limited to input/output handling.
    """

    DIVA_TIMEOUT_SECONDS = 300
    NODE_LINE_RE = re.compile(
        r"^node\s+(?P<node_id>\d+)\s+"
        r"\(anc\.\s+of\s+terminals\s+(?P<terminals>[^)]+)\):\s*"
        r"(?P<states>.*?)\s*$",
        re.IGNORECASE,
    )

    def __init__(self, project_root: str = None) -> None:
        if project_root is None:
            project_root = Path(__file__).resolve().parent.parent.parent
        self.project_root = Path(project_root)
        self.diva_exe_path = self.project_root / "engines" / "diva" / "DIVA.exe"

    def run(
        self,
        tree_entries,
        matrix,
        reference_tree=None,
        distribution_name: str = "d1",
        config=None,
        progress_callback=None,
    ) -> SDivaResult:
        if not tree_entries:
            raise ValueError("S-DIVA run failed: no trees are available for analysis")
        if matrix is None:
            raise ValueError("S-DIVA run failed: matrix is empty")
        if reference_tree is None:
            raise ValueError("S-DIVA run failed: reference tree is required")
        if not self.diva_exe_path.exists():
            raise FileNotFoundError("DIVA executable not found: %s" % self.diva_exe_path)

        valid_entries = [x for x in tree_entries if getattr(x, "parsed_tree", None) is not None]
        if not valid_entries:
            raise ValueError("S-DIVA run failed: no parsed trees are available")

        taxa_order, name_to_index, index_to_name = self._build_global_taxon_order(matrix)
        self._validate_tree_taxa(reference_tree, name_to_index, "reference tree")
        for idx, entry in enumerate(valid_entries, start=1):
            self._validate_tree_taxa(entry.parsed_tree, name_to_index, "tree %s" % idx)

        run_dir = self._make_run_dir()
        config_text = ""
        config_path = ""
        if config is not None:
            config_text = config.to_legacy_config_text(fossil_count=self._count_internal_nodes(reference_tree))
            config_path = str(self._write_text(run_dir / "sdiva_config.txt", config_text))

        prepared = []
        for idx, entry in enumerate(valid_entries, start=1):
            numeric_newick = self._build_numeric_newick(entry.parsed_tree, name_to_index) + ";"
            prepared.append(
                {
                    "tree_index": idx,
                    "entry": entry,
                    "numeric_newick": numeric_newick,
                    "tokens": self._legacy_tree_tokens(numeric_newick),
                }
            )

        reference_numeric_newick = self._build_numeric_newick(reference_tree, name_to_index) + ";"
        reference_nodes = self._build_reference_nodes(reference_tree, name_to_index, index_to_name)
        state_order = self._build_legacy_state_order(matrix, config)
        state_colors = self._build_state_color_map(state_order)

        run_final_tree = self._should_run_final_tree(config)
        proc_paths = self._write_legacy_proc_files(
            run_dir=run_dir,
            prepared=prepared,
            matrix=matrix,
            name_to_index=name_to_index,
            config=config,
            reference_numeric_newick=reference_numeric_newick,
            fossil_count=len(reference_nodes),
            run_final_tree=run_final_tree,
        )
        console_log = self._run_diva_proc_files(
            proc_paths,
            run_dir,
            len(prepared),
            progress_callback=progress_callback,
        )

        warnings = []
        missing = []
        for item in prepared:
            if not (run_dir / ("%s.diva" % item["tree_index"])).exists():
                missing.append(str(item["tree_index"]))
        if missing:
            raise ValueError(
                "S-DIVA run failed: missing DIVA result files for tree(s): %s\nConsole log: %s"
                % (", ".join(missing[:20]), console_log)
            )

        final_tree_constraints = {}
        restrict_to_final_tree_states = False
        if run_final_tree:
            final_diva_path = run_dir / "final.diva"
            if not final_diva_path.exists():
                raise ValueError(
                    "S-DIVA run failed: missing final-tree DIVA result file: %s\nConsole log: %s"
                    % (final_diva_path, console_log)
                )
            final_tree_constraints = self._parse_final_tree_constraints(
                diva_path=final_diva_path,
                reference_tokens=self._legacy_tree_tokens(reference_numeric_newick),
                state_order=state_order,
                warnings=warnings,
            )
            restrict_to_final_tree_states = self._config_has_fossils(config)

        aggregation = self._legacy_do_analysis(
            run_dir=run_dir,
            prepared=prepared,
            reference_nodes=reference_nodes,
            state_order=state_order,
            index_to_name=index_to_name,
            warnings=warnings,
            final_tree_constraints=final_tree_constraints,
            restrict_to_final_tree_states=restrict_to_final_tree_states,
        )

        result = SDivaResult(
            reference_tree=reference_tree,
            tree_count_total=len(prepared),
            parse_warnings=warnings,
            config=config,
            config_text=config_text,
            config_path=config_path,
            state_order=state_order,
            state_colors=state_colors,
            reference_diva_node_ids={
                node["node_key"]: node["display_id"]
                for node in reference_nodes
            },
        )
        result.run_dir = str(run_dir)
        result.proc_file = str(proc_paths[0]) if proc_paths else ""
        result.proc_files = [str(path) for path in proc_paths]
        result.console_log = str(console_log)

        for node in reference_nodes:
            node_key = node["node_key"]
            legacy_clade = node["legacy_clade"]
            counts = aggregation["counts"].get(node["legacy_clade"], {})
            supporting_tree_count = aggregation["presence"].get(node["legacy_clade"], 0)
            node_state_order = list(state_order)
            if restrict_to_final_tree_states and final_tree_constraints.get(legacy_clade):
                allowed = set(final_tree_constraints[legacy_clade])
                node_state_order = [state for state in state_order if state in allowed]
                if not node_state_order:
                    node_state_order = list(state_order)

            node_sum = sum(float(counts.get(state, 0.0)) for state in node_state_order)

            if node_sum > 0:
                state_supports = {
                    state: float(counts.get(state, 0.0)) / node_sum * 100.0
                    for state in node_state_order
                }
            else:
                fallback = 100.0 / len(node_state_order) if node_state_order else 0.0
                state_supports = {state: fallback for state in node_state_order}

            states = sorted(
                node_state_order,
                key=lambda state: (-state_supports.get(state, 0.0), self._legacy_state_rank(state, state_order)),
            )
            state_counts = {state: float(counts.get(state, 0.0)) for state in state_order}

            node_result = SDivaNodeResult(
                node_key=node_key,
                supporting_tree_count=supporting_tree_count,
                total_tree_count=len(prepared),
                states=states,
                state_counts=state_counts,
                state_supports=state_supports,
            )
            node_result.pie_labels = states
            node_result.pie_percents = [state_supports.get(state, 0.0) for state in states]
            node_result.pie_colors = [state_colors.get(state, "#808080") for state in states]
            result.node_results[node_key] = node_result

        analysis_log = self._write_analysis_log(
            run_dir=run_dir,
            result=result,
            taxa_order=taxa_order,
            index_to_name=index_to_name,
            matrix=matrix,
            reference_numeric_newick=reference_numeric_newick,
        )
        result.analysis_log_path = str(analysis_log)
        return result

    def _write_legacy_proc_files(
        self,
        run_dir: Path,
        prepared: list,
        matrix,
        name_to_index: dict,
        config,
        reference_numeric_newick: str = "",
        fossil_count: int = 0,
        run_final_tree: bool = False,
    ) -> list:
        threads = 1
        if config is not None:
            threads = max(1, min(1024, int(getattr(config, "threads", 1) or 1)))
        distribution_line = "distribution %s;" % " ".join(self._build_distributions(matrix, name_to_index))
        optimize_line = self._legacy_optimize_command(config, taxon_count=len(name_to_index))
        exclude_line = self._legacy_exclude_command(config)

        buckets = [[] for _ in range(threads)]
        for item in prepared:
            bucket_index = int(item["tree_index"]) % threads
            lines = buckets[bucket_index]
            tree_index = item["tree_index"]
            lines.append("output %s.diva;" % tree_index)
            lines.append("tree %s" % item["numeric_newick"])
            lines.append(distribution_line)
            if exclude_line:
                lines.append(exclude_line)
            lines.append(optimize_line)

        if run_final_tree:
            fossil_line = self._legacy_fossil_command(config, fossil_count=fossil_count)
            final_optimize_line = self._legacy_optimize_command(
                config,
                taxon_count=len(name_to_index),
                final_tree=True,
            )
            lines = buckets[0]
            lines.append("output final.diva;")
            lines.append("tree %s" % reference_numeric_newick)
            lines.append(distribution_line)
            if exclude_line:
                lines.append(exclude_line)
            if fossil_line:
                lines.append(fossil_line)
            lines.append(final_optimize_line)

        proc_paths = []
        for index, lines in enumerate(buckets):
            lines.append("output DIVA_%s.end;" % index)
            lines.append("quit;")
            proc_path = run_dir / ("SDIVA_%s.proc" % index)
            self._write_text(proc_path, "\n".join(lines) + "\n", newline="\r\n", encoding="ascii")
            proc_paths.append(proc_path)
        return proc_paths

    def _run_diva_proc(self, proc_path: Path, run_dir: Path, tree_count: int) -> Path:
        log_path = run_dir / "DIVA_console.log"
        timeout = max(30, min(self.DIVA_TIMEOUT_SECONDS, 3 * int(tree_count or 1)))
        try:
            with log_path.open("wb") as log_file:
                completed = subprocess.run(
                    [str(self.diva_exe_path), proc_path.name],
                    cwd=str(run_dir),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=timeout,
                )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                "DIVA.exe did not exit in proc mode after %s seconds.\n"
                "Proc file: %s\nConsole log: %s\nLog tail:\n%s"
                % (timeout, proc_path, log_path, self._read_tail(log_path))
            ) from exc

        if completed.returncode != 0:
            raise RuntimeError(
                "DIVA.exe failed with return code %s.\nProc file: %s\nConsole log: %s\nLog tail:\n%s"
                % (completed.returncode, proc_path, log_path, self._read_tail(log_path))
            )
        return log_path

    def _run_diva_proc_files(self, proc_paths: list, run_dir: Path, tree_count: int, progress_callback=None) -> str:
        if not proc_paths:
            raise ValueError("S-DIVA run failed: no proc files were written")

        timeout = max(30, min(self.DIVA_TIMEOUT_SECONDS, 3 * int(tree_count or 1)))
        processes = []
        log_paths = []
        try:
            for index, proc_path in enumerate(proc_paths):
                log_path = run_dir / ("DIVA_console_%s.log" % index)
                log_file = log_path.open("wb")
                process = subprocess.Popen(
                    [str(self.diva_exe_path), proc_path.name],
                    cwd=str(run_dir),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                )
                processes.append((process, proc_path, log_file, log_path))
                log_paths.append(log_path)

            deadline = time.monotonic() + timeout
            last_done = -1
            while True:
                done = self._count_numeric_diva_outputs(run_dir)
                if done != last_done:
                    last_done = done
                    self._emit_progress(
                        progress_callback,
                        min(done, int(tree_count or 0)),
                        int(tree_count or 0),
                        "S-DIVA DIVA.exe finished %s/%s tree result file(s)" % (
                            min(done, int(tree_count or 0)),
                            int(tree_count or 0),
                        ),
                    )

                if all(process.poll() is not None for process, _proc_path, _log_file, _log_path in processes):
                    break

                if time.monotonic() > deadline:
                    for running, _running_proc, _running_log_file, _running_log_path in processes:
                        if running.poll() is None:
                            running.kill()
                    first_proc = processes[0][1]
                    first_log = processes[0][3]
                    raise TimeoutError(
                        "DIVA.exe did not exit in threaded proc mode after %s seconds.\n"
                        "Proc file: %s\nConsole log: %s\nLog tail:\n%s"
                        % (timeout, first_proc, first_log, self._read_tail(first_log))
                    )
                time.sleep(0.5)

            for process, proc_path, log_file, log_path in processes:
                return_code = process.poll()
                log_file.close()

                if return_code != 0:
                    raise RuntimeError(
                        "DIVA.exe failed with return code %s.\nProc file: %s\nConsole log: %s\nLog tail:\n%s"
                        % (return_code, proc_path, log_path, self._read_tail(log_path))
                    )
        finally:
            for process, _proc_path, log_file, _log_path in processes:
                try:
                    if process.poll() is None:
                        process.kill()
                finally:
                    if not log_file.closed:
                        log_file.close()

        return "; ".join(str(path) for path in log_paths)

    def _count_numeric_diva_outputs(self, run_dir: Path) -> int:
        count = 0
        for path in run_dir.glob("*.diva"):
            if str(path.stem).isdigit():
                count += 1
        return count

    def _emit_progress(self, progress_callback, done, total, message):
        if progress_callback is None:
            return
        progress_callback(int(done or 0), int(total or 0), str(message or ""))

    def _legacy_do_analysis(
        self,
        run_dir: Path,
        prepared: list,
        reference_nodes: list,
        state_order: list,
        index_to_name: dict,
        warnings: list,
        final_tree_constraints: dict = None,
        restrict_to_final_tree_states: bool = False,
    ) -> dict:
        final_tree_constraints = final_tree_constraints or {}
        clade_to_index = {node["legacy_clade"]: idx for idx, node in enumerate(reference_nodes)}
        counts_by_clade = {
            node["legacy_clade"]: {state: 0.0 for state in state_order}
            for node in reference_nodes
        }
        presence_by_clade = {node["legacy_clade"]: 0 for node in reference_nodes}

        for item in prepared:
            tree_counts = {
                node["legacy_clade"]: {state: 0.0 for state in state_order}
                for node in reference_nodes
            }
            total_lengths = {node["legacy_clade"]: 0 for node in reference_nodes}
            tree_presence = {node["legacy_clade"]: 0 for node in reference_nodes}

            diva_path = run_dir / ("%s.diva" % item["tree_index"])
            node_lines = self._parse_diva_node_lines(diva_path)
            if not node_lines:
                warnings.append("tree %s: no optimal distributions block in %s" % (item["tree_index"], diva_path.name))
                continue

            for parsed in node_lines:
                legacy_clade = self._legacy_clade_from_terminal_spec(
                    parsed["terminal_spec"],
                    item["tokens"],
                )
                if legacy_clade not in clade_to_index:
                    continue

                raw_states = [state for state in parsed["states"] if str(state).strip()]
                if not raw_states:
                    continue

                tree_presence[legacy_clade] = 1
                total_lengths[legacy_clade] += len(raw_states)
                allowed_states = set(final_tree_constraints.get(legacy_clade, []))
                for state in raw_states:
                    if restrict_to_final_tree_states and allowed_states and state not in allowed_states:
                        continue
                    if state in state_order:
                        tree_counts[legacy_clade][state] += 1.0

            for legacy_clade in counts_by_clade:
                total = float(total_lengths.get(legacy_clade, 0))
                if total <= 0:
                    continue
                for state in state_order:
                    counts_by_clade[legacy_clade][state] += tree_counts[legacy_clade][state] / total
                presence_by_clade[legacy_clade] += int(tree_presence.get(legacy_clade, 0))

        return {
            "counts": counts_by_clade,
            "presence": presence_by_clade,
        }

    def _parse_diva_node_lines(self, diva_path: Path) -> list:
        text = diva_path.read_text(encoding="utf-8", errors="ignore")
        result = []
        in_block = False
        current = ""

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.lower().startswith("optimal distributions"):
                in_block = True
                current = ""
                continue
            if not in_block:
                continue
            if not line:
                if current:
                    parsed = self._parse_node_line(current)
                    if parsed is not None:
                        result.append(parsed)
                    current = ""
                break
            if line.lower().startswith("node"):
                if current:
                    parsed = self._parse_node_line(current)
                    if parsed is not None:
                        result.append(parsed)
                current = line
            elif current:
                current += " " + line

        if in_block and current:
            parsed = self._parse_node_line(current)
            if parsed is not None:
                result.append(parsed)
        return result

    def _parse_node_line(self, line: str):
        match = self.NODE_LINE_RE.match(str(line or "").strip())
        if not match:
            return None
        states = [
            token.strip()
            for token in re.split(r"\s+", match.group("states").strip())
            if token.strip()
        ]
        return {
            "node_id": int(match.group("node_id")),
            "terminal_spec": match.group("terminals").strip(),
            "states": states,
            "raw_line": line,
        }

    def _legacy_clade_from_terminal_spec(self, terminal_spec: str, tree_tokens: list) -> str:
        terminals = [token.strip() for token in str(terminal_spec or "").split("-") if token.strip()]
        if not terminals:
            return ""
        if len(terminals) == 1:
            return "#" + terminals[0]

        left = terminals[0]
        right = terminals[-1]
        try:
            left_idx = tree_tokens.index(left)
            right_idx = tree_tokens.index(right)
        except ValueError:
            return ""

        lo = min(left_idx, right_idx)
        hi = max(left_idx, right_idx)
        taxa = [
            token
            for token in tree_tokens[lo:hi + 1]
            if token and token not in ("(", ")", ",")
        ]
        return self._legacy_clade(taxa)

    def _build_reference_nodes(self, reference_tree, name_to_index: dict, index_to_name: dict) -> list:
        nodes = []
        taxon_count = len(name_to_index)
        counter = 0
        for node in reference_tree.traverse("postorder"):
            if node.is_leaf():
                continue
            counter += 1
            indices = [str(name_to_index[str(leaf.name).strip()]) for leaf in node.iter_leaves()]
            names = [index_to_name[int(x)] for x in indices]
            nodes.append(
                {
                    "legacy_clade": self._legacy_clade(indices),
                    "node_key": "|".join(sorted(names)),
                    "display_id": taxon_count + counter,
                }
            )
        return nodes

    def _build_global_taxon_order(self, matrix):
        rows = list(getattr(matrix, "rows", []) or [])
        taxa_order = []
        for row in rows:
            name = str(row.get("Name", "")).strip()
            if not name:
                raise ValueError("S-DIVA run failed: matrix contains an empty Name")
            if name in taxa_order:
                raise ValueError("S-DIVA run failed: duplicate taxon in matrix: %s" % name)
            taxa_order.append(name)

        if not taxa_order:
            raise ValueError("S-DIVA run failed: matrix has no taxa")

        name_to_index = {name: idx for idx, name in enumerate(taxa_order, start=1)}
        index_to_name = {idx: name for name, idx in name_to_index.items()}
        return taxa_order, name_to_index, index_to_name

    def _validate_tree_taxa(self, tree, name_to_index: dict, label: str) -> None:
        leaf_names = {str(leaf.name).strip() for leaf in tree.iter_leaves()}
        matrix_names = set(name_to_index.keys())
        missing = sorted(matrix_names - leaf_names)
        extra = sorted(leaf_names - matrix_names)
        if missing or extra:
            parts = ["S-DIVA run failed: %s taxa do not match matrix." % label]
            if missing:
                parts.append("Missing in tree: %s" % missing[:20])
            if extra:
                parts.append("Extra in tree: %s" % extra[:20])
            raise ValueError("\n".join(parts))

    def _build_numeric_newick(self, tree, name_to_index: dict) -> str:
        def visit(node):
            if node.is_leaf():
                return str(name_to_index[str(node.name).strip()])
            return "(" + ",".join(visit(child) for child in node.children) + ")"

        return visit(tree)

    def _legacy_tree_tokens(self, numeric_newick: str) -> list:
        text = str(numeric_newick or "").replace(";", "")
        parts = re.split(r"([(),])", text)
        tokens = []
        for part in parts:
            part = part.strip()
            if not part or part in ("(", ")", ","):
                continue
            if ":" in part:
                part = part.split(":", 1)[0]
            tokens.append(part)
        return tokens

    def _legacy_clade(self, values) -> str:
        clean = [str(value).strip() for value in values if str(value).strip()]
        return "".join("#" + value for value in sorted(clean))

    def _build_distributions(self, matrix, name_to_index: dict) -> list:
        rows = list(getattr(matrix, "rows", []) or [])
        by_name = {str(row.get("Name", "")).strip(): row for row in rows}
        state_columns = [
            str(col).strip()
            for col in list(getattr(matrix, "state_columns", []) or [])
            if str(col).strip() and str(col).strip() not in ("ID", "Name")
        ]
        if not state_columns:
            raise ValueError("S-DIVA run failed: matrix has no state columns")

        values = []
        for name, _idx in sorted(name_to_index.items(), key=lambda item: item[1]):
            row = by_name[name]
            dist = self._row_to_distribution(row, state_columns)
            values.append(dist if dist else "0")
        return values

    def _row_to_distribution(self, row: dict, state_columns: list) -> str:
        parts = []
        for col in state_columns:
            value = str(row.get(col, "")).strip().upper()
            if value.upper() in EMPTY_STATE_TOKENS:
                continue
            if value in {"1", "TRUE", "T", "YES", "Y", "PRESENT", "+"}:
                parts.append(str(col).strip().upper())
            else:
                parts.append(value)
        return "".join(parts)

    def _build_legacy_state_order(self, matrix, config) -> list:
        if config is not None:
            areas = [
                str(area).strip().upper()
                for area in list(getattr(config, "area_names", []) or [])
                if str(area).strip()
            ]
            ranges = [
                str(value).strip().upper()
                for value in list(getattr(config, "include_ranges", []) or [])
                if str(value).strip()
            ]
            excluded = set(
                str(value).strip().upper()
                for value in list(getattr(config, "runtime_exclude_ranges", lambda: [])() or [])
                if str(value).strip()
            )
            ranges = [value for value in ranges if value not in excluded]
            return self._ordered_unique(areas + ranges)

        areas = []
        for row in list(getattr(matrix, "rows", []) or []):
            for col in list(getattr(matrix, "state_columns", []) or []):
                if col in ("ID", "Name"):
                    continue
                value = str(row.get(col, "")).strip().upper()
                for area in self._split_area_value(value):
                    if area not in areas:
                        areas.append(area)
        return self._ordered_unique(areas)

    def _legacy_optimize_command(self, config, taxon_count: int, final_tree: bool = False) -> str:
        if config is None:
            return "optimize;"
        return config.to_diva_optimize_command(taxon_count=taxon_count, final_tree=final_tree)

    def _legacy_fossil_command(self, config, fossil_count: int) -> str:
        if config is None or not hasattr(config, "to_diva_fossil_command"):
            return ""
        return str(config.to_diva_fossil_command(fossil_count=fossil_count) or "").strip()

    def _legacy_exclude_command(self, config) -> str:
        if config is None or not hasattr(config, "to_diva_exclude_command"):
            return ""
        return str(config.to_diva_exclude_command() or "").strip()

    def _should_run_final_tree(self, config) -> bool:
        if config is None:
            return False
        return bool(getattr(config, "use_final_tree", False))

    def _config_has_fossils(self, config) -> bool:
        if config is None:
            return False
        if hasattr(config, "has_fossils"):
            return bool(config.has_fossils())
        return any(str(value).strip() for value in list(getattr(config, "fossil_values", []) or []))

    def _parse_final_tree_constraints(
        self,
        diva_path: Path,
        reference_tokens: list,
        state_order: list,
        warnings: list,
    ) -> dict:
        parsed_nodes = self._parse_diva_node_lines(diva_path)
        if not parsed_nodes:
            warnings.append("final tree: no optimal distributions block in %s" % diva_path.name)
            return {}

        state_set = set(state_order)
        constraints = {}
        for parsed in parsed_nodes:
            legacy_clade = self._legacy_clade_from_terminal_spec(
                parsed["terminal_spec"],
                reference_tokens,
            )
            if not legacy_clade:
                continue
            states = [
                state
                for state in parsed["states"]
                if str(state).strip() and (not state_set or state in state_set)
            ]
            if states:
                constraints[legacy_clade] = self._ordered_unique(states)
        return constraints

    def _split_area_value(self, value: str) -> list:
        text = str(value or "").strip().upper()
        if text in EMPTY_STATE_TOKENS:
            return []
        if re.search(r"[\s,;|/]+", text):
            return [
                token.strip()
                for token in re.split(r"[\s,;|/]+", text)
                if token.strip() and token.strip() not in EMPTY_STATE_TOKENS
            ]
        if len(text) == 1:
            return [text]
        return [char for char in text if char.strip()]

    def _write_analysis_log(
        self,
        run_dir: Path,
        result: SDivaResult,
        taxa_order: list,
        index_to_name: dict,
        matrix,
        reference_numeric_newick: str,
    ) -> Path:
        lines = [
            "Statistical Dispersal-Vicariance Analysis result file",
            "[TAXON]",
        ]
        by_name = {str(row.get("Name", "")).strip(): row for row in list(getattr(matrix, "rows", []) or [])}
        state_columns = [
            str(col).strip()
            for col in list(getattr(matrix, "state_columns", []) or [])
            if str(col).strip() and str(col).strip() not in ("ID", "Name")
        ]
        for idx, name in enumerate(taxa_order, start=1):
            row = by_name.get(name, {})
            lines.append("%s\t%s\t%s" % (idx, name, self._row_to_distribution(row, state_columns)))

        lines.extend([
            "[TREE]",
            "Tree=" + reference_numeric_newick,
            "[RESULT]",
            "Optimal reconstruction:",
        ])

        ref_map = dict(getattr(result, "reference_diva_node_ids", {}) or {})
        for node_key, node_result in result.node_results.items():
            display_id = ref_map.get(node_key, "")
            parts = []
            for state in node_result.states:
                parts.append(" %s %.2f" % (state, float(node_result.state_supports.get(state, 0.0))))
            lines.append("node %s:%s" % (display_id, "".join(parts)))

        return self._write_text(run_dir / "analysis_result.log", "\n".join(lines) + "\n")

    def _ordered_unique(self, values) -> list:
        result = []
        seen = set()
        for value in list(values or []):
            item = str(value).strip()
            if not item or item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    def _legacy_state_rank(self, state: str, state_order: list) -> int:
        if state in state_order:
            return state_order.index(state)
        return 10 ** 9

    def _build_state_color_map(self, state_order: list) -> dict:
        palette = [
            "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
            "#ffff33", "#a65628", "#f781bf", "#999999", "#66c2a5",
            "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854", "#ffd92f",
            "#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e",
        ]
        return {state: palette[i % len(palette)] for i, state in enumerate(state_order)}

    def _count_internal_nodes(self, tree) -> int:
        if tree is None:
            return 0
        return sum(1 for node in tree.traverse() if not node.is_leaf())

    def _make_run_dir(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        run_dir = self.project_root / "runs" / "sdiva" / ("legacy_sdiva_%s" % stamp)
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    def _write_text(self, path: Path, text: str, newline: str = "\n", encoding: str = "utf-8") -> Path:
        with path.open("w", encoding=encoding, newline="") as handle:
            handle.write(str(text).replace("\n", newline))
        return path

    def _read_tail(self, path: Path, max_lines: int = 40) -> str:
        if not path.exists():
            return "<log file does not exist>"
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        return "\n".join(lines[-max_lines:]) if lines else "<empty log>"
