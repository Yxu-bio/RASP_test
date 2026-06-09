import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from application.services.biogeobears_dataset_builder import BioGeoBEARSRunFiles


@dataclass
class BioGeoBEARSRunOutput:
    rscript_path: Path
    script_path: Path
    workdir: Path

    stdout: str
    stderr: str
    returncode: int

    output_json_path: Path


@dataclass
class BioGeoBEARSBatchOutput:
    rscript_path: Path
    script_path: Path
    workdir: Path

    manifest_path: Path
    progress_path: Path
    summary_path: Path
    stdout_log_path: Path
    stderr_log_path: Path
    returncode: int


class BioGeoBEARSRunner:
    def __init__(self, rscript_path=None, wrapper_script_path=None, site_library_path=None):
        self.rscript_path = Path(rscript_path) if rscript_path else None
        self.wrapper_script_path = Path(wrapper_script_path) if wrapper_script_path else None
        self.site_library_path = Path(site_library_path) if site_library_path else None

    def set_rscript_path(self, rscript_path) -> None:
        self.rscript_path = Path(rscript_path) if rscript_path else None

    def set_wrapper_script_path(self, wrapper_script_path) -> None:
        self.wrapper_script_path = Path(wrapper_script_path) if wrapper_script_path else None

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

        raise FileNotFoundError("未找到 Rscript.exe。请先安装 R，并在设置中配置 Rscript 路径。")

    def resolve_wrapper_script_path(self) -> Path:
        if self.wrapper_script_path and self.wrapper_script_path.exists():
            return self.wrapper_script_path.resolve()
        raise FileNotFoundError("未找到 BioGeoBEARS wrapper 脚本 bgb_runner.R。")

    def resolve_site_library_path(self) -> Path:
        if self.site_library_path and self.site_library_path.exists():
            return self.site_library_path.resolve()
        raise FileNotFoundError("未找到 BioGeoBEARS 私有 R 库目录。")

    def run(self, run_files: BioGeoBEARSRunFiles) -> BioGeoBEARSRunOutput:
        rscript = self.resolve_rscript_path()
        wrapper = self.resolve_wrapper_script_path()
        site_lib = self.resolve_site_library_path()

        cmd = [
            str(rscript),
            str(wrapper),
            "--tree", str(run_files.tree_path),
            "--geog", str(run_files.geog_path),
            "--areas", str(run_files.areas_json_path),
            "--model", str(run_files.model_name),
            "--max_range_size", str(run_files.max_range_size),
            "--include_null_range", "TRUE" if run_files.include_null_range else "FALSE",
            "--null_range_mode", str(run_files.null_range_mode),
            "--lib", str(site_lib),
            "--out", str(run_files.output_json_path),
        ]

        env = os.environ.copy()
        site_lib = str(self.resolve_site_library_path())

        env["R_LIBS"] = site_lib
        env["R_LIBS_SITE"] = site_lib
        env["R_LIBS_USER"] = site_lib

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
            detail = stderr_text.strip() or stdout_text.strip() or "BioGeoBEARS 运行失败"
            raise RuntimeError(detail)

        if not run_files.output_json_path.exists():
            raise FileNotFoundError(
                "BioGeoBEARS 运行完成，但未找到输出 JSON：%s" % run_files.output_json_path
            )

        return BioGeoBEARSRunOutput(
            rscript_path=rscript,
            script_path=wrapper,
            workdir=run_files.workdir,
            stdout=stdout_text,
            stderr=stderr_text,
            returncode=proc.returncode,
            output_json_path=run_files.output_json_path,
        )

    def run_batch(
        self,
        run_files_list,
        *,
        batch_workdir,
        batch_name="batch",
        job_ids=None,
        progress_callback=None,
    ) -> BioGeoBEARSBatchOutput:
        run_files_list = list(run_files_list or [])
        if not run_files_list:
            raise ValueError("BioGeoBEARS batch run requires at least one job.")

        rscript = self.resolve_rscript_path()
        wrapper = self.resolve_wrapper_script_path()
        site_lib = self.resolve_site_library_path()
        batch_workdir = Path(batch_workdir)
        batch_workdir.mkdir(parents=True, exist_ok=True)

        safe_name = str(batch_name or "batch")
        manifest_path = batch_workdir / ("%s_manifest.json" % safe_name)
        progress_path = batch_workdir / ("%s_progress.tsv" % safe_name)
        summary_path = batch_workdir / ("%s_summary.json" % safe_name)
        stdout_log_path = batch_workdir / ("%s_stdout.log" % safe_name)
        stderr_log_path = batch_workdir / ("%s_stderr.log" % safe_name)

        if progress_path.exists():
            progress_path.unlink()

        job_ids = list(job_ids or [])
        jobs = []
        for idx, run_files in enumerate(run_files_list, start=1):
            job_id = str(job_ids[idx - 1]) if idx - 1 < len(job_ids) else str(idx)
            jobs.append(
                {
                    "id": job_id,
                    "tree": str(run_files.tree_path),
                    "geog": str(run_files.geog_path),
                    "areas": str(run_files.areas_json_path),
                    "model": str(run_files.model_name),
                    "max_range_size": str(run_files.max_range_size),
                    "include_null_range": "TRUE" if run_files.include_null_range else "FALSE",
                    "null_range_mode": str(run_files.null_range_mode),
                    "out": str(run_files.output_json_path),
                }
            )

        manifest_path.write_text(
            json.dumps(
                {
                    "jobs": jobs,
                    "summary": str(summary_path),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        cmd = [
            str(rscript),
            str(wrapper),
            "--batch",
            str(manifest_path),
            "--lib",
            str(site_lib),
            "--progress",
            str(progress_path),
        ]

        env = os.environ.copy()
        site_lib_text = str(site_lib)
        env["R_LIBS"] = site_lib_text
        env["R_LIBS_SITE"] = site_lib_text
        env["R_LIBS_USER"] = site_lib_text

        seen_terminal_jobs = set()

        with stdout_log_path.open("w", encoding="utf-8", errors="replace") as stdout_fh:
            with stderr_log_path.open("w", encoding="utf-8", errors="replace") as stderr_fh:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(batch_workdir),
                    env=env,
                    stdout=stdout_fh,
                    stderr=stderr_fh,
                    universal_newlines=True,
                )

                while proc.poll() is None:
                    self._emit_batch_progress(progress_path, seen_terminal_jobs, progress_callback)
                    time.sleep(0.5)

                returncode = proc.wait()
                self._emit_batch_progress(progress_path, seen_terminal_jobs, progress_callback)

        if returncode != 0:
            stderr_text = stderr_log_path.read_text(encoding="utf-8", errors="replace") if stderr_log_path.exists() else ""
            stdout_text = stdout_log_path.read_text(encoding="utf-8", errors="replace") if stdout_log_path.exists() else ""
            detail = stderr_text.strip() or stdout_text.strip() or "BioGeoBEARS batch run failed"
            raise RuntimeError(detail)

        return BioGeoBEARSBatchOutput(
            rscript_path=rscript,
            script_path=wrapper,
            workdir=batch_workdir,
            manifest_path=manifest_path,
            progress_path=progress_path,
            summary_path=summary_path,
            stdout_log_path=stdout_log_path,
            stderr_log_path=stderr_log_path,
            returncode=returncode,
        )

    def _emit_batch_progress(self, progress_path: Path, seen_terminal_jobs: set, progress_callback) -> None:
        if progress_callback is None or not progress_path.exists():
            return

        try:
            lines = progress_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return

        for line in lines:
            parts = line.split("\t", 2)
            if len(parts) < 2:
                continue
            job_id = parts[0].strip()
            status = parts[1].strip().upper()
            message = parts[2].strip() if len(parts) > 2 else ""
            if status not in ("DONE", "ERROR") or not job_id:
                continue
            if job_id in seen_terminal_jobs:
                continue
            seen_terminal_jobs.add(job_id)
            try:
                progress_callback(job_id, status, message)
            except Exception:
                pass
