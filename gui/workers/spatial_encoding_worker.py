from PyQt5.QtCore import QThread, pyqtSignal


class SpatialEncodingWorker(QThread):
    succeeded = pyqtSignal(object, object, object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)

    def __init__(
        self,
        *,
        service,
        occurrences,
        areas,
        min_records_per_taxon_area=1,
        source_path="spatial://encoded_occurrences",
    ):
        super().__init__()
        self.service = service
        self.occurrences = list(occurrences or [])
        self.areas = list(areas or [])
        self.min_records_per_taxon_area = min_records_per_taxon_area
        self.source_path = source_path
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def _is_cancelled(self):
        return bool(self._cancel_requested)

    def run(self):
        try:
            matrix, audit_rows = self.service.encode_occurrences_to_matrix(
                self.occurrences,
                self.areas,
                min_records_per_taxon_area=self.min_records_per_taxon_area,
                source_path=self.source_path,
                progress_callback=self.progress.emit,
                cancel_callback=self._is_cancelled,
            )
            diagnostics = self.service.build_encoding_diagnostics(
                occurrences=self.occurrences,
                areas=self.areas,
                matrix=matrix,
                audit_rows=audit_rows,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        self.succeeded.emit(matrix, audit_rows, diagnostics)
