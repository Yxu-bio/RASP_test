import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from application.services.bbm_dataset_builder import BBMRunFiles


@dataclass
class MrBayesRunOutput:
    executable_path: Path
    workdir: Path
    stdout: str
    stderr: str
    returncode: int
    run1_p_path: Path
    run2_p_path: Path
    mcmc_path: Path


class MrBayesRunner:
    def __init__(self, executable_path=None):
        self.executable_path = Path(executable_path) if executable_path else None

    def set_executable_path(self, executable_path) -> None:
        self.executable_path = Path(executable_path) if executable_path else None

    def resolve_executable_path(self) -> Path:
        candidates = []
        if self.executable_path:
            candidates.append(Path(self.executable_path))

        hit = shutil.which("mb.exe") or shutil.which("mb") or shutil.which("mrbayes")
        if hit:
            candidates.append(Path(hit))

        for path in candidates:
            if path.exists():
                return path.resolve()

        raise FileNotFoundError("MrBayes executable was not found. Expected engines/mrbayes/mb.3.2.7-win32.exe.")

    def run(self, run_files: BBMRunFiles) -> MrBayesRunOutput:
        exe = self.resolve_executable_path()
        cmd = [str(exe), run_files.nexus_path.name]
        proc = subprocess.run(
            cmd,
            cwd=str(run_files.workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            input="\n",
        )

        stdout_text = proc.stdout if proc.stdout is not None else ""
        stderr_text = proc.stderr if proc.stderr is not None else ""
        run_files.stdout_log_path.write_text(stdout_text, encoding="utf-8", errors="replace")
        run_files.stderr_log_path.write_text(stderr_text, encoding="utf-8", errors="replace")

        if proc.returncode != 0:
            detail = stderr_text.strip() or stdout_text.strip() or "MrBayes run failed"
            raise RuntimeError(detail)

        paths = self._locate_output_files(run_files.workdir, run_files.nexus_path.name)
        run_files.run1_p_path = paths["run1_p"]
        run_files.run2_p_path = paths["run2_p"]
        run_files.mcmc_path = paths["mcmc"]

        return MrBayesRunOutput(
            executable_path=exe,
            workdir=run_files.workdir,
            stdout=stdout_text,
            stderr=stderr_text,
            returncode=proc.returncode,
            run1_p_path=run_files.run1_p_path,
            run2_p_path=run_files.run2_p_path,
            mcmc_path=run_files.mcmc_path,
        )

    def _locate_output_files(self, workdir: Path, nexus_name: str) -> dict:
        direct = {
            "run1_p": workdir / (nexus_name + ".run1.p"),
            "run2_p": workdir / (nexus_name + ".run2.p"),
            "mcmc": workdir / (nexus_name + ".mcmc"),
        }
        if all(path.exists() for path in direct.values()):
            return direct

        patterns = {
            "run1_p": "*.run1.p",
            "run2_p": "*.run2.p",
            "mcmc": "*.mcmc",
        }
        found = {}
        for key, pattern in patterns.items():
            matches = sorted(
                workdir.glob(pattern),
                key=lambda path: path.stat().st_mtime if path.exists() else 0,
                reverse=True,
            )
            if not matches:
                raise FileNotFoundError("MrBayes output file was not produced: %s" % pattern)
            found[key] = matches[0]
        return found
