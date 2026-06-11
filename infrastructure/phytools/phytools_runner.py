import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from application.services.phytools_dataset_builder import PhytoolsRunFiles


@dataclass
class PhytoolsRunOutput:
    rscript_path: Path
    workdir: Path
    stdout: str
    stderr: str
    returncode: int
    output_json_path: Path


class PhytoolsRunner:
    def __init__(self, rscript_path=None, site_library_path=None):
        self.rscript_path = Path(rscript_path) if rscript_path else None
        self.site_library_path = Path(site_library_path) if site_library_path else None

    def set_rscript_path(self, rscript_path) -> None:
        self.rscript_path = Path(rscript_path) if rscript_path else None

    def set_site_library_path(self, site_library_path) -> None:
        self.site_library_path = Path(site_library_path) if site_library_path else None

    def resolve_rscript_path(self) -> Path:
        candidates = []
        if self.rscript_path:
            candidates.append(Path(self.rscript_path))
        for name in ("Rscript.exe", "Rscript"):
            hit = shutil.which(name)
            if hit:
                candidates.append(Path(hit))
        for path in candidates:
            if path.exists():
                return path.resolve()
        raise FileNotFoundError("Rscript.exe was not found. Configure an Rscript path before running phytools.")

    def resolve_site_library_path(self):
        if self.site_library_path and self.site_library_path.exists():
            return self.site_library_path.resolve()
        return None

    def run(self, run_files: PhytoolsRunFiles) -> PhytoolsRunOutput:
        rscript = self.resolve_rscript_path()
        cmd = [
            str(rscript),
            str(run_files.script_path),
            "--tree", str(run_files.tree_path),
            "--traits", str(run_files.traits_path),
            "--out", str(run_files.output_json_path),
            "--method", str(run_files.config.method),
            "--ace_model", self._ace_model(run_files.config.method),
            "--anc_ml_maxit", str(int(getattr(run_files.config, "anc_ml_maxit", 2000) or 2000)),
            "--bayes_iterations", str(int(getattr(run_files.config, "bayes_iterations", 10000) or 10000)),
            "--bayes_sample_frequency", str(int(getattr(run_files.config, "bayes_sample_frequency", 1000) or 1000)),
            "--bayes_burnin", str(int(getattr(run_files.config, "bayes_burnin", 0) or 0)),
            "--seed", str(int(getattr(run_files.config, "seed", 1) or 0)),
        ]

        env = os.environ.copy()
        site_lib = self.resolve_site_library_path()
        if site_lib is not None:
            site_lib_text = str(site_lib)
            env["R_LIBS"] = site_lib_text
            env["R_LIBS_SITE"] = site_lib_text
            env["R_LIBS_USER"] = site_lib_text

        proc = subprocess.run(
            cmd,
            cwd=str(run_files.workdir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        stdout_text = proc.stdout if proc.stdout is not None else ""
        stderr_text = proc.stderr if proc.stderr is not None else ""
        run_files.stdout_log_path.write_text(stdout_text, encoding="utf-8")
        run_files.stderr_log_path.write_text(stderr_text, encoding="utf-8")

        if proc.returncode != 0:
            detail = stderr_text.strip() or stdout_text.strip()
            if not detail:
                detail = "phytools run failed with exit code %s" % proc.returncode
            raise RuntimeError(detail)
        if not run_files.output_json_path.exists():
            raise FileNotFoundError("phytools finished but did not write output JSON: %s" % run_files.output_json_path)

        return PhytoolsRunOutput(
            rscript_path=rscript,
            workdir=run_files.workdir,
            stdout=stdout_text,
            stderr=stderr_text,
            returncode=proc.returncode,
            output_json_path=run_files.output_json_path,
        )

    def _ace_model(self, method: str) -> str:
        method = str(method or "").upper()
        if method == "ACE_ER":
            return "ER"
        if method == "ACE_SYM":
            return "SYM"
        if method == "ACE_ARD":
            return "ARD"
        return ""
