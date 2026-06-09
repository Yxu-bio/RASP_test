from pathlib import Path
import subprocess


class DivaRunner:
    """Run DIVA.exe with all generated files kept in the per-run directory."""

    def __init__(self, diva_exe_path: str):
        self.diva_exe = Path(diva_exe_path).resolve()
        if not self.diva_exe.exists():
            raise FileNotFoundError("DIVA executable does not exist: %s" % self.diva_exe)

        self.diva_dir = self.diva_exe.parent

    def run(
        self,
        batch_file_path: str,
        wrapper_name: str = "_diva_runner_input.txt",
        log_name: str = "_diva_console.log",
        timeout_seconds: int = None,
    ) -> dict:
        batch_file = Path(batch_file_path).resolve()
        if not batch_file.exists():
            raise FileNotFoundError("DIVA batch file does not exist: %s" % batch_file)

        run_dir = batch_file.parent

        wrapper_file = run_dir / wrapper_name
        wrapper_text = "proc %s;\nquit;\n" % batch_file.name
        with wrapper_file.open("w", encoding="ascii", newline="") as f:
            f.write(wrapper_text.replace("\n", "\r\n"))

        log_file = run_dir / log_name
        if log_file.exists():
            log_file.unlink()

        try:
            with wrapper_file.open("rb") as fin, log_file.open("wb") as fout:
                completed = subprocess.run(
                    [str(self.diva_exe)],
                    stdin=fin,
                    stdout=fout,
                    stderr=subprocess.STDOUT,
                    cwd=str(run_dir),
                    check=False,
                    timeout=timeout_seconds,
                )
        except subprocess.TimeoutExpired as exc:
            log_tail = self._read_log_tail(log_file)
            raise TimeoutError(
                "DIVA timed out after %s seconds.\n"
                "DIVA directory: %s\n"
                "Run directory: %s\n"
                "Batch file: %s\n"
                "Wrapper file: %s\n"
                "Log file: %s\n"
                "Log tail:\n%s"
                % (timeout_seconds, self.diva_dir, run_dir, batch_file, wrapper_file, log_file, log_tail)
            ) from exc

        return_code = completed.returncode
        if return_code != 0:
            log_tail = self._read_log_tail(log_file)
            raise RuntimeError(
                "DIVA failed with return code: %s\n"
                "DIVA directory: %s\n"
                "Run directory: %s\n"
                "Batch file: %s\n"
                "Wrapper file: %s\n"
                "Log file: %s\n"
                "Log tail:\n%s"
                % (return_code, self.diva_dir, run_dir, batch_file, wrapper_file, log_file, log_tail)
            )

        return {
            "return_code": return_code,
            "batch_file": str(batch_file),
            "wrapper_file": str(wrapper_file),
            "console_log": str(log_file),
        }

    def _read_log_tail(self, log_file: Path, max_lines: int = 30) -> str:
        if not log_file.exists():
            return "<log file does not exist>"

        try:
            text = log_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return "<log file could not be read>"

        lines = text.splitlines()
        if not lines:
            return "<log is empty>"
        return "\n".join(lines[-max_lines:])
