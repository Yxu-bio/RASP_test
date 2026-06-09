import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from application.services.bayarea_dataset_builder import BayAreaRunFiles


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

    def run(self, run_files: BayAreaRunFiles) -> BayAreaRunOutput:
        exe = self.resolve_executable_path()
        config = run_files.config
        if config is None:
            raise ValueError("BayArea config is required.")

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
        ]
        if int(kwargs["model_type_code"]) == 3:
            cmd.extend([
                "-geoDistancePowerPositive=%s" % self._bool_arg(kwargs["geo_distance_power_positive"]),
                "-geoDistanceTruncate=%s" % self._bool_arg(kwargs["geo_distance_truncate"]),
            ])
        seed = kwargs.get("seed")
        if seed is not None:
            cmd.append("-seed=%s" % int(seed))
        cmd.extend(self._parse_other_options(kwargs.get("other_options", "")))

        proc = subprocess.run(
            cmd,
            cwd=str(run_files.workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        stdout_text = proc.stdout if proc.stdout is not None else ""
        stderr_text = proc.stderr if proc.stderr is not None else ""
        run_files.stdout_log_path.write_text(stdout_text, encoding="utf-8", errors="replace")
        run_files.stderr_log_path.write_text(stderr_text, encoding="utf-8", errors="replace")

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

    def _path_arg(self, path: Path) -> str:
        text = str(Path(path).resolve()).replace("\\", "/")
        if not text.endswith("/"):
            text += "/"
        return text

    def _bool_arg(self, value) -> str:
        return "T" if bool(value) else "F"

    def _parse_other_options(self, text) -> list:
        options = []
        for line in str(text or "").splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#"):
                continue
            options.append(clean)
        return options

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
