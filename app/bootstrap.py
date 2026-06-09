import os
import sys
from pathlib import Path


class ApplicationBootstrap:
    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parent.parent

    def inject_conda_dll_paths(self) -> None:
        """Make direct env-python launches find conda DLL dependencies."""
        prefix = Path(sys.prefix)
        blocked = {
            str(prefix / "Library" / "bin").lower(),
        }
        candidates = [
            prefix / "DLLs",
        ]

        existing = os.environ.get("PATH", "")
        existing_parts = [
            part
            for part in existing.split(os.pathsep)
            if part and str(Path(part)).lower() not in blocked
        ]
        prepend = []
        for candidate in candidates:
            if not candidate.exists():
                continue
            candidate_str = str(candidate)
            if candidate_str not in existing_parts:
                prepend.append(candidate_str)
            add_dll_directory = getattr(os, "add_dll_directory", None)
            if callable(add_dll_directory):
                try:
                    add_dll_directory(candidate_str)
                except Exception:
                    pass

        if prepend:
            os.environ["PATH"] = os.pathsep.join(prepend + existing_parts)

    def inject_vendor_packages(self) -> None:
        vendor_root = (
            self.project_root
            / "infrastructure"
            / "tree"
            / "backend"
            / "ete3_vendor"
        )

        if not vendor_root.exists():
            raise FileNotFoundError(
                f"未找到 ete3 vendor 目录: {vendor_root}"
            )

        vendor_root_str = str(vendor_root)
        if vendor_root_str not in sys.path:
            sys.path.insert(0, vendor_root_str)

    def validate_ete3_import(self) -> None:
        try:
            import ete3  # noqa: F401
        except Exception as exc:
            raise ImportError(f"导入内嵌 ete3 失败: {exc}") from exc

    def build_qt_application(self):
        try:
            from PyQt5.QtWidgets import QApplication
        except Exception as exc:
            raise ImportError(f"导入 PyQt5 失败: {exc}") from exc

        app = QApplication(sys.argv)
        app.setApplicationName("RASP-Pro")
        return app

    def build_main_window(self):
        from gui.main_window import MainWindow

        return MainWindow()

    def run(self) -> int:
        self.inject_conda_dll_paths()
        self.inject_vendor_packages()
        self.validate_ete3_import()

        app = self.build_qt_application()
        window = self.build_main_window()
        window.show()

        return app.exec_()
