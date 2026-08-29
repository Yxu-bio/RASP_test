"""Application installation and writable-data path policy."""

import os
from pathlib import Path


class ApplicationPaths:
    INSTALL_MANIFEST = "RASP5-APPLICATION-MANIFEST.json"

    def __init__(self, project_root, data_root):
        self.project_root = Path(project_root).resolve()
        self.data_root = Path(data_root).resolve()
        self.runs_root = self.data_root / "runs"

    @classmethod
    def discover(cls, project_root=None):
        root = Path(project_root or Path(__file__).resolve().parents[1]).resolve()
        override = str(os.environ.get("RASP5_DATA_HOME", "") or "").strip()
        if override:
            data_root = Path(os.path.expandvars(os.path.expanduser(override)))
        elif (root / cls.INSTALL_MANIFEST).is_file():
            local_app_data = str(os.environ.get("LOCALAPPDATA", "") or "").strip()
            if not local_app_data:
                local_app_data = str(Path.home() / "AppData" / "Local")
            data_root = Path(local_app_data) / "RASP5"
        else:
            data_root = root
        paths = cls(root, data_root)
        paths.runs_root.mkdir(parents=True, exist_ok=True)
        return paths
