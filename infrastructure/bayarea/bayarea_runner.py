import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from application.services.bayarea_dataset_builder import BayAreaRunFiles
from infrastructure.run_provenance import write_run_provenance


@dataclass
class BayAreaRunOutput:
    executable_path: Path
    workdir: Path
    stdout: str
    stderr: str
    returncode: int
    parameters_path: Path
    area_states_path: Path
    area_probs_path: Path
    nhx_path: Path


class BayAreaRunCancelled(RuntimeError):
    pass


class BayAreaRunner:
    def __init__(self, executable_path=None):
        self.executable_path = Path(executable_path) if executable_path else None

    def set_executable_path(self, executable_path) -> None:
        self.executable_path = Path(executable_path) if executable_path else None

    def resolve_executable_path(self) -> Path:
        candidates = []
        if self.executable_path:
            candidates.append(Path(self.executable_path))

        hit = shutil.which("bayarea.exe") or shutil.which("bayarea")
        if hit:
            candidates.append(Path(hit))

        for path in candidates:
            if path.exists():
                return path.resolve()

        raise FileNotFoundError("BayArea executable was not found. Expected engines/bayarea/bin/bayarea.exe.")

    def run(self, run_files: BayAreaRunFiles, progress_callback=None, cancel_callback=None) -> BayAreaRunOutput:
        exe = self.resolve_executable_path()
        config = run_files.config
        if config is None:
            raise ValueError("BayArea config is required.")
        write_run_provenance(
            run_files.workdir,
            analysis="BayArea",
            engine_paths={"bayarea_executable": exe},
            extra={"model_type": str(getattr(config, "model_type", "") or "")},
        )

        kwargs = config.engine_kwargs()
        input_path = self._path_arg(run_files.workdir)
        output_path = self._path_arg(run_files.workdir)

        cmd = [
            str(exe),
            "-areaFileName=%s" % run_files.areas_path.name,
            "-geoFileName=%s" % run_files.geo_path.name,
            "-treeFileName=%s" % run_files.tree_path.name,
            "-inputFilePath=%s" % input_path,
            "-outputFilePath=%s" % output_path,
            "-outputTimestamp=F",
            "-outputPrefix=%s" % run_files.output_prefix,
            "-parameterSampleFrequency=%s" % int(kwargs["sample_frequency"]),
            "-historySampleFrequency=%s" % int(kwargs["sample_frequency"]),
            "-printFrequency=%s" % int(kwargs["sample_frequency"]),
            "-chainLength=%s" % int(kwargs["chain_length"]),
            "-chainBurnIn=0",
            "-probBurnIn=0",
            "-modelType=%s" % int(kwargs["model_type_code"]),
            "-guessInitialRates=%s" % self._bool_arg(kwargs["guess_initial_rates"]),
            "-useAuxiliarySampling=%s" % self._bool_arg(kwargs["use_auxiliary_sampling"]),
            "-gainPrior=%s" % self._float_arg(kwargs["gain_prior"]),
            "-lossPrior=%s" % self._float_arg(kwargs["loss_prior"]),
            "-areaProposalTuner=%s" % self._float_arg(kwargs["area_proposal_tuner"]),
            "-rateProposalTuner=%s" % self._float_arg(kwargs["rate_proposal_tuner"]),
        ]
        if int(kwargs["model_type_code"]) == 3:
            cmd.extend([
                "-geoDistancePowerPositive=%s" % self._bool_arg(kwargs["geo_distance_power_positive"]),
                "-geoDistanceTruncate=%s" % self._bool_arg(kwargs["geo_distance_truncate"]),
                "-distancePowerPrior=%s" % self._float_arg(kwargs["distance_power_prior"]),
                "-distanceProposalTuner=%s" % self._float_arg(kwargs["distance_proposal_tuner"]),
            ])
        seed = kwargs.get("seed")
        if seed is not None:
            cmd.append("-seed=%s" % int(seed))
        cmd.extend(self._parse_other_options(kwargs.get("other_options", "")))

        timeout_seconds = self._timeout_seconds(kwargs)
        proc = None
        started = time.monotonic()
        read_offset = 0
        partial_line = ""
        last_cycle = -1
        mcmc_started = False
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if progress_callback is not None:
            progress_callback(0, "Starting BayArea")

        with run_files.stdout_log_path.open("w", encoding="utf-8", errors="replace") as stdout_handle, \
                run_files.stderr_log_path.open("w", encoding="utf-8", errors="replace") as stderr_handle:
            proc = subprocess.Popen(
                cmd,
                cwd=str(run_files.workdir),
                stdout=stdout_handle,
                stderr=stderr_handle,
                universal_newlines=True,
                creationflags=creationflags,
            )
            try:
                while proc.poll() is None:
                    if cancel_callback is not None and bool(cancel_callback()):
                        self._stop_process(proc)
                        raise BayAreaRunCancelled(
                            "BayArea run cancelled. Partial logs were kept in: %s" % run_files.workdir
                        )
                    if time.monotonic() - started > timeout_seconds:
                        self._stop_process(proc)
                        raise TimeoutError(
                            "BayArea did not exit within %s seconds.\n"
                            "workdir: %s\n"
                            "This usually indicates a degenerate model/data combination or an unusually long MCMC run."
                            % (timeout_seconds, run_files.workdir)
                        )
                    if progress_callback is not None:
                        read_offset, partial_line, last_cycle, mcmc_started = self._report_progress(
                            log_path=run_files.stdout_log_path,
                            read_offset=read_offset,
                            partial_line=partial_line,
                            last_cycle=last_cycle,
                            mcmc_started=mcmc_started,
                            chain_length=int(kwargs["chain_length"]),
                            callback=progress_callback,
                        )
                    time.sleep(0.1)
            except Exception:
                if proc.poll() is None:
                    self._stop_process(proc)
                raise

        stdout_text = run_files.stdout_log_path.read_text(encoding="utf-8", errors="replace")
        stderr_text = run_files.stderr_log_path.read_text(encoding="utf-8", errors="replace")
        if progress_callback is not None:
            progress_callback(100, "BayArea MCMC complete")

        if proc.returncode != 0:
            detail = stderr_text.strip() or stdout_text.strip() or "BayArea run failed"
            raise RuntimeError(detail)

        paths = self._locate_output_files(run_files.workdir)
        run_files.parameters_path = paths["parameters"]
        run_files.area_states_path = paths["area_states"]
        run_files.area_probs_path = paths["area_probs"]
        run_files.nhx_path = paths["nhx"]

        self._copy_original_outputs_if_requested(run_files)

        return BayAreaRunOutput(
            executable_path=exe,
            workdir=run_files.workdir,
            stdout=stdout_text,
            stderr=stderr_text,
            returncode=proc.returncode,
            parameters_path=run_files.parameters_path,
            area_states_path=run_files.area_states_path,
            area_probs_path=run_files.area_probs_path,
            nhx_path=run_files.nhx_path,
        )

    def _report_progress(
        self,
        *,
        log_path,
        read_offset,
        partial_line,
        last_cycle,
        mcmc_started,
        chain_length,
        callback
    ):
        try:
            with Path(log_path).open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(int(read_offset))
                chunk = handle.read()
                read_offset = handle.tell()
        except Exception:
            return read_offset, partial_line, last_cycle, mcmc_started
        if not chunk:
            return read_offset, partial_line, last_cycle, mcmc_started

        text = partial_line + chunk
        lines = text.splitlines(True)
        partial_line = ""
        if lines and not lines[-1].endswith(("\n", "\r")):
            partial_line = lines.pop()
        for line in lines:
            if "MCMC initated" in line or "MCMC initiated" in line:
                mcmc_started = True
                continue
            if not mcmc_started:
                continue
            match = re.match(r"^\s*(\d+)\s+(?:--|~p)", line)
            if not match:
                continue
            cycle = int(match.group(1))
            if cycle <= last_cycle:
                continue
            last_cycle = cycle
            percent = int(round(100.0 * float(cycle) / float(max(1, chain_length))))
            callback(max(0, min(99, percent)), "BayArea MCMC: %d / %d" % (cycle, chain_length))
        return read_offset, partial_line, last_cycle, mcmc_started

    def _stop_process(self, proc) -> None:
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=3)
            except Exception:
                pass

    def _path_arg(self, path: Path) -> str:
        text = str(Path(path).resolve()).replace("\\", "/")
        if not text.endswith("/"):
            text += "/"
        return text

    def _bool_arg(self, value) -> str:
        return "T" if bool(value) else "F"

    def _float_arg(self, value) -> str:
        return "%.12g" % float(value)

    def _parse_other_options(self, text) -> list:
        options = []
        for line in str(text or "").splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#"):
                continue
            options.append(clean)
        return options

    def _timeout_seconds(self, kwargs) -> int:
        try:
            chain_length = int(kwargs.get("chain_length", 0) or 0)
        except Exception:
            chain_length = 0
        if chain_length <= 0:
            return 900
        return max(900, min(21600, int(chain_length / 5000)))

    def _timeout_text(self, value) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    def _locate_output_files(self, workdir: Path) -> dict:
        patterns = {
            "parameters": "*.parameters.txt",
            "area_states": "*.area_states.txt",
            "area_probs": "*.area_probs.txt",
            "nhx": "*.nhx",
        }
        found = {}
        for key, pattern in patterns.items():
            matches = sorted(
                workdir.glob(pattern),
                key=lambda path: path.stat().st_mtime if path.exists() else 0,
                reverse=True,
            )
            if not matches:
                raise FileNotFoundError("BayArea output file was not produced: %s" % pattern)
            found[key] = matches[0]
        return found

    def _copy_original_outputs_if_requested(self, run_files: BayAreaRunFiles) -> None:
        config = run_files.config
        if not bool(getattr(config, "save_original_results", False)):
            return
        target_text = str(getattr(config, "save_original_results_path", "") or "").strip()
        if not target_text:
            return
        target = Path(target_text)
        target.mkdir(parents=True, exist_ok=True)
        for path in [
            run_files.parameters_path,
            run_files.area_states_path,
            run_files.area_probs_path,
            run_files.nhx_path,
        ]:
            if path and path.exists():
                target_path = target / path.name
                if path == run_files.nhx_path:
                    self._copy_nhx_with_taxon_names(path, target_path, run_files)
                else:
                    shutil.copy2(str(path), str(target_path))

    def _copy_nhx_with_taxon_names(self, source: Path, target: Path, run_files: BayAreaRunFiles) -> None:
        text = source.read_text(encoding="utf-8", errors="replace")
        names = [str(name) for name in list(getattr(run_files, "taxon_names", []) or [])]
        if not names:
            shutil.copy2(str(source), str(target))
            return
        rewritten = self._rewrite_nhx_taxlabels_and_translate(text, names)
        target.write_text(rewritten, encoding="utf-8")

    def _rewrite_nhx_taxlabels_and_translate(self, text: str, taxon_names: list) -> str:
        lines = str(text or "").splitlines()
        output = []
        index = 0
        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            output.append(line)
            lower = stripped.lower()

            if lower == "taxlabels":
                index += 1
                while index < len(lines) and lines[index].strip() != ";":
                    index += 1
                for name in taxon_names:
                    output.append("\t\t" + str(name))
                if index < len(lines):
                    output.append(lines[index])

            elif lower == "translate":
                index += 1
                while index < len(lines) and lines[index].strip() != ";":
                    index += 1
                last = len(taxon_names) - 1
                for taxon_index, name in enumerate(taxon_names):
                    suffix = "," if taxon_index < last else ""
                    output.append("\t\t%s\t%s%s" % (taxon_index, str(name), suffix))
                if index < len(lines):
                    output.append(lines[index])

            index += 1
        return "\n".join(output) + ("\n" if text.endswith("\n") else "")
