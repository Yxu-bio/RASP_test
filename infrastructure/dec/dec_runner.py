from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os
import shutil
import subprocess

from application.services.dec_dataset_builder import DECRunFiles


@dataclass
class DECRunOutput:
    engine_path: Path
    workdir: Path
    config_path: Path

    stdout: str
    stderr: str
    returncode: int

    results_json_path: Path
    nodes_tree_path: Path
    states_tree_path: Optional[Path]
    splits_tree_path: Optional[Path]
    scaled_tree_path: Optional[Path]
    clean_tree_path: Optional[Path]


class DECRunner:
    def __init__(self, engine_path=None):
        self.engine_path = Path(engine_path) if engine_path else None

    def set_engine_path(self, engine_path) -> None:
        self.engine_path = Path(engine_path) if engine_path else None

    def resolve_engine_path(self) -> Path:
        candidates = []

        if self.engine_path:
            candidates.append(Path(self.engine_path))

        # 允许 PATH 中已有 lagrange-ng.exe
        path_hit = shutil.which("lagrange-ng.exe") or shutil.which("lagrange-ng")
        if path_hit:
            candidates.append(Path(path_hit))

        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate.resolve()

        raise FileNotFoundError(
            "未找到 Lagrange-NG 引擎。请确认 lagrange-ng.exe 已存在，"
            "并在 DECAnalysisService 中配置 engine_path。"
        )

    def run(self, run_files: DECRunFiles, env_overrides=None) -> DECRunOutput:
        engine = self.resolve_engine_path()

        env = os.environ.copy()
        engine_dir = str(engine.parent.resolve())
        env["PATH"] = engine_dir + os.pathsep + env.get("PATH", "")
        for key, value in dict(env_overrides or {}).items():
            env[str(key)] = str(value)

        cmd = [str(engine), str(run_files.config_path.name)]
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

        if proc.returncode != 0:
            detail = stderr_text.strip() or stdout_text.strip() or "DEC 引擎运行失败"
            raise RuntimeError(
                "lagrange-ng.exe process exited abnormally.\n"
                f"workdir: {run_files.workdir}\n"
                f"config: {run_files.config_path}\n"
                f"exit code: {proc.returncode}\n"
                f"{detail}"
            )

        results_json_path = self._resolve_required_output(
            run_files.workdir,
            exact=run_files.results_json_path,
            suffix=".results.json",
        )
        nodes_tree_path = self._resolve_required_output(
            run_files.workdir,
            exact=run_files.nodes_tree_path,
            suffix=".nodes.tre",
        )

        states_tree_path = self._resolve_optional_output(
            run_files.workdir,
            exact=run_files.states_tree_path,
            suffix=".states.tre",
        )
        splits_tree_path = self._resolve_optional_output(
            run_files.workdir,
            exact=run_files.splits_tree_path,
            suffix=".splits.tre",
        )
        scaled_tree_path = self._resolve_optional_output(
            run_files.workdir,
            exact=run_files.scaled_tree_path,
            suffix=".scaled.tre",
        )
        clean_tree_path = self._resolve_optional_output(
            run_files.workdir,
            exact=run_files.clean_tree_path,
            suffix=".clean.tre",
        )

        return DECRunOutput(
            engine_path=engine,
            workdir=run_files.workdir,
            config_path=run_files.config_path,
            stdout=stdout_text,
            stderr=stderr_text,
            returncode=proc.returncode,
            results_json_path=results_json_path,
            nodes_tree_path=nodes_tree_path,
            states_tree_path=states_tree_path,
            splits_tree_path=splits_tree_path,
            scaled_tree_path=scaled_tree_path,
            clean_tree_path=clean_tree_path,
        )

    def _resolve_required_output(self, workdir: Path, *, exact: Path, suffix: str) -> Path:
        found = self._resolve_optional_output(workdir, exact=exact, suffix=suffix)
        if found is None:
            raise FileNotFoundError(f"DEC 运行完成，但未找到输出文件：*{suffix}")
        return found

    def _resolve_optional_output(self, workdir: Path, *, exact: Path, suffix: str) -> Optional[Path]:
        if exact.exists():
            return exact

        matches = sorted(workdir.glob(f"*{suffix}"), key=lambda p: p.stat().st_mtime, reverse=True)
        return matches[0] if matches else None
