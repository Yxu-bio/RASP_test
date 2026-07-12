import json
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from tools.build_region_geojson import build_regions, _write_notes, _write_unassigned


class RegionGeoJsonBuilderWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)

    def __init__(self, *, config_path="", config_data=None, config_dir="", output_path="", notes_path="", unassigned_path=""):
        super().__init__()
        self.config_path = str(config_path or "")
        self.config_data = config_data
        self.config_dir = str(config_dir or "")
        self.output_path = str(output_path or "")
        self.notes_path = str(notes_path or "")
        self.unassigned_path = str(unassigned_path or "")
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def _check_cancelled(self):
        if self._cancel_requested:
            raise RuntimeError("Region GeoJSON build cancelled.")

    def run(self):
        try:
            output_path = Path(self.output_path)
            if not self.output_path:
                raise ValueError("Output GeoJSON path is required.")

            config_path = Path(self.config_path) if self.config_path else None
            if self.config_data is not None:
                self.progress.emit(0, 100, "Preparing region builder config ...")
                config = dict(self.config_data or {})
                config_dir = Path(self.config_dir) if self.config_dir else None
            else:
                if config_path is None or not config_path.exists():
                    raise FileNotFoundError("Config JSON does not exist: %s" % (config_path or self.config_path))
                self.progress.emit(0, 100, "Reading region builder config ...")
                config = json.loads(config_path.read_text(encoding="utf-8-sig"))
                config_dir = config_path.parent
            self._check_cancelled()

            self.progress.emit(10, 100, "Building region GeoJSON ...")
            collection, notes, unassigned = build_regions(config, config_dir=config_dir)
            self._check_cancelled()

            self.progress.emit(85, 100, "Writing output files ...")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(collection, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            if self.notes_path:
                _write_notes(self.notes_path, notes)
            if self.unassigned_path:
                _write_unassigned(self.unassigned_path, unassigned)
            self._check_cancelled()

            self.progress.emit(100, 100, "Region GeoJSON build completed")
            self.succeeded.emit(
                {
                    "config_path": str(config_path) if config_path is not None else "(generated from UI inputs)",
                    "output_path": str(output_path),
                    "notes_path": str(self.notes_path or ""),
                    "unassigned_path": str(self.unassigned_path or ""),
                    "collection": collection,
                    "notes": notes,
                    "unassigned": unassigned,
                }
            )
        except Exception as exc:
            self.failed.emit(str(exc))
