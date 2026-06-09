import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from application.services.bayestraits_dataset_builder import BayesTraitsRunFiles


@dataclass
class BayesTraitsRunOutput:
    executable_path: Path
    executable_version: str
    workdir: Path
    stdout: str
    stderr: str
    returncode: int
    output_log_path: Path
    stones_path: Path = None


class BayesTraitsRunner:
    def __init__(self, executable_path=None):
        self.executable_path = Path(executable_path) if executable_path else None

    def set_executable_path(self, executable_path) -> None:
        self.executable_path = Path(executable_path) if executable_path else None

    def resolve_executable_path(self) -> Path:
        candidates = []
        if self.executable_path:
            candidates.append(Path(self.executable_path))

        project_root = Path(__file__).resolve().parents[2]
        candidates.extend([
            project_root / "engines" / "bayestraits" / "BayesTraitsV5.exe",
            project_root / "engines" / "bayestraits" / "bin" / "BayesTraitsV5.exe",
        ])

        hit = shutil.which("BayesTraitsV5.exe") or shutil.which("BayesTraitsV5")
        if hit:
            candidates.append(Path(hit))

        for path in candidates:
            if path.exists():
                return path.resolve()

        raise FileNotFoundError("BayesTraits V5 executable was not found. Expected engines/bayestraits/BayesTraitsV5.exe.")

    def run(self, run_files: BayesTraitsRunFiles) -> BayesTraitsRunOutput:
        exe = self.resolve_executable_path()
        executable_version = self.detect_version(exe)
        if bool(getattr(run_files, "continuous_asr", False)):
            return self._run_continuous_asr(run_files, exe, executable_version)

        proc, stdout_text, stderr_text = self._run_command_file(
            executable_path=exe,
            run_files=run_files,
            commands_path=run_files.commands_path,
        )
        run_files.stdout_log_path.write_text(stdout_text, encoding="utf-8", errors="replace")
        run_files.stderr_log_path.write_text(stderr_text, encoding="utf-8", errors="replace")

        if proc.returncode != 0:
            raise RuntimeError(self._failure_detail(proc.returncode, stdout_text, stderr_text))

        output_log = self._locate_output_log(run_files.workdir)
        if output_log is None:
            detail = stderr_text.strip() or stdout_text.strip() or "BayesTraits did not produce trait.dat.Log.txt"
            raise RuntimeError(detail)

        stones_path = self._locate_stones_log(output_log)
        run_files.output_log_path = output_log
        run_files.stones_path = stones_path
        self._record_engine_metadata(run_files, exe, executable_version)
        return BayesTraitsRunOutput(
            executable_path=exe,
            executable_version=executable_version,
            workdir=run_files.workdir,
            stdout=stdout_text,
            stderr=stderr_text,
            returncode=proc.returncode,
            output_log_path=output_log,
            stones_path=stones_path,
        )

    def _run_command_file(self, *, executable_path: Path, run_files: BayesTraitsRunFiles, commands_path: Path):
        command_text = Path(commands_path).read_text(encoding="ascii", errors="ignore")
        cmd = [str(executable_path), run_files.trees_path.name, run_files.data_path.name]
        proc = subprocess.run(
            cmd,
            cwd=str(run_files.workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            input=command_text,
        )
        stdout_text = proc.stdout if proc.stdout is not None else ""
        stderr_text = proc.stderr if proc.stderr is not None else ""
        return proc, stdout_text, stderr_text

    def _run_continuous_asr(self, run_files: BayesTraitsRunFiles, exe: Path, executable_version: str) -> BayesTraitsRunOutput:
        stage1_commands = Path(run_files.model_save_commands_path)
        stage2_commands = Path(run_files.estimate_commands_path)
        model_save_path = Path(run_files.model_save_path)

        stage1, stdout1, stderr1 = self._run_command_file(
            executable_path=exe,
            run_files=run_files,
            commands_path=stage1_commands,
        )
        (run_files.workdir / "bayestraits_stdout_stage1.log").write_text(stdout1, encoding="utf-8", errors="replace")
        (run_files.workdir / "bayestraits_stderr_stage1.log").write_text(stderr1, encoding="utf-8", errors="replace")
        if stage1.returncode != 0:
            raise RuntimeError("Model-build stage failed.\n" + self._failure_detail(stage1.returncode, stdout1, stderr1))
        if not model_save_path.exists():
            raise RuntimeError("Model-build stage did not produce %s.\n%s" % (model_save_path.name, stdout1.strip() or stderr1.strip()))

        self._archive_stage_outputs(run_files.workdir, "model_build")

        stage2, stdout2, stderr2 = self._run_command_file(
            executable_path=exe,
            run_files=run_files,
            commands_path=stage2_commands,
        )
        (run_files.workdir / "bayestraits_stdout_stage2.log").write_text(stdout2, encoding="utf-8", errors="replace")
        (run_files.workdir / "bayestraits_stderr_stage2.log").write_text(stderr2, encoding="utf-8", errors="replace")
        run_files.stdout_log_path.write_text(stdout1 + "\n\n--- Continuous ASR estimate stage ---\n\n" + stdout2, encoding="utf-8", errors="replace")
        run_files.stderr_log_path.write_text(stderr1 + "\n\n--- Continuous ASR estimate stage ---\n\n" + stderr2, encoding="utf-8", errors="replace")
        if stage2.returncode != 0:
            raise RuntimeError("Node-estimate stage failed.\n" + self._failure_detail(stage2.returncode, stdout2, stderr2))

        output_log = self._locate_output_log(run_files.workdir)
        if output_log is None:
            detail = stderr2.strip() or stdout2.strip() or "BayesTraits did not produce trait.dat.Log.txt"
            raise RuntimeError(detail)

        stones_path = self._locate_stones_log(output_log)
        run_files.output_log_path = output_log
        run_files.stones_path = stones_path
        self._record_engine_metadata(run_files, exe, executable_version)
        return BayesTraitsRunOutput(
            executable_path=exe,
            executable_version=executable_version,
            workdir=run_files.workdir,
            stdout=stdout1 + "\n" + stdout2,
            stderr=stderr1 + "\n" + stderr2,
            returncode=stage2.returncode,
            output_log_path=output_log,
            stones_path=stones_path,
        )

    def _failure_detail(self, returncode: int, stdout_text: str, stderr_text: str) -> str:
        detail = stderr_text.strip() or stdout_text.strip() or "BayesTraits run failed"
        if detail == "BayesTraits run failed":
            detail = (
                "BayesTraits run failed with exit code %s. "
                "If stdout/stderr are empty, check that the BayesTraits V5 executable "
                "is complete and runnable."
            ) % returncode
        return detail

    def _archive_stage_outputs(self, workdir: Path, prefix: str) -> None:
        for path in sorted(workdir.glob("trait.dat*.txt")):
            name = path.name
            target = workdir / ("%s_%s" % (prefix, name))
            try:
                if target.exists():
                    target.unlink()
                path.rename(target)
            except OSError:
                pass

    def _locate_output_log(self, workdir: Path):
        candidates = [
            workdir / "trait.dat.Log.txt",
            workdir / "trait.dat.log.txt",
        ]
        for path in candidates:
            if path.exists():
                return path
        matches = sorted(
            workdir.glob("trait.dat*.txt"),
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )
        for path in matches:
            name = path.name.lower()
            if "schedule" not in name and "stones" not in name:
                return path
        return None

    def _locate_stones_log(self, output_log: Path):
        candidates = [
            Path(str(output_log) + ".Stones.txt"),
            output_log.parent / "trait.dat.Log.txt.Stones.txt",
            output_log.parent / "trait.dat.log.txt.Stones.txt",
        ]
        for path in candidates:
            if path.exists():
                return path
        matches = sorted(
            output_log.parent.glob("*Stones.txt"),
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )
        return matches[0] if matches else None

    def detect_version(self, executable_path=None) -> str:
        exe = Path(executable_path) if executable_path else self.resolve_executable_path()
        try:
            proc = subprocess.run(
                [str(exe)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                input="\n",
                timeout=5,
            )
        except Exception:
            return ""

        text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        for line in text.splitlines():
            clean = line.strip()
            if clean.startswith("BayesTraits"):
                return clean
        return ""

    def _record_engine_metadata(self, run_files: BayesTraitsRunFiles, executable_path: Path, executable_version: str) -> None:
        if not run_files.manifest_path.exists():
            return
        try:
            payload = json.loads(run_files.manifest_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        payload["engine"] = {
            "target": "BayesTraits V5",
            "executable_path": str(executable_path),
            "executable_version": str(executable_version or ""),
        }
        run_files.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
