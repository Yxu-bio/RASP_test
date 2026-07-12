from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from application.services.bsm_sampling_diagnostics_service import BSMSamplingDiagnosticsService
from domain.models.sbgb_config import SBGB_MODEL_DISPLAY


DEFAULT_BSM_NUMMAPS = 100
DEFAULT_BSM_SEED = 12345
DEFAULT_BSM_MAXTRIES_PER_BRANCH = 40000


class BSMRunConfigDialog(QDialog):
    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BioGeoBEARS BSM Events")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        model_name = str(getattr(config, "model_name", "") or "DEC")
        model_label = SBGB_MODEL_DISPLAY.get(model_name, model_name)

        self.maps_spin = QSpinBox(self)
        self.maps_spin.setMinimum(1)
        self.maps_spin.setMaximum(100000)
        self.maps_spin.setValue(DEFAULT_BSM_NUMMAPS)
        self.maps_spin.valueChanged.connect(self._refresh_sampling_note)

        self.sampling_diagnostics = BSMSamplingDiagnosticsService()
        self.sampling_note = QLabel(self)
        self.sampling_note.setWordWrap(True)

        self.seed_spin = QSpinBox(self)
        self.seed_spin.setMinimum(-2147483647)
        self.seed_spin.setMaximum(2147483647)
        self.seed_spin.setValue(DEFAULT_BSM_SEED)

        self.maxtries_spin = QSpinBox(self)
        self.maxtries_spin.setMinimum(1)
        self.maxtries_spin.setMaximum(10000000)
        self.maxtries_spin.setValue(DEFAULT_BSM_MAXTRIES_PER_BRANCH)

        note = QLabel(
            "Generate stochastic biogeographic maps and extract ana.events / clado.events "
            "for the current BioGeoBEARS model.",
            self,
        )
        note.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Model:", QLabel(model_label, self))
        form.addRow("Maps:", self.maps_spin)
        form.addRow("Seed:", self.seed_spin)
        form.addRow("Max tries per branch:", self.maxtries_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(note)
        layout.addLayout(form)
        layout.addWidget(self.sampling_note)
        layout.addWidget(buttons)
        self._refresh_sampling_note()

    def _refresh_sampling_note(self, *args):
        diagnostics = self.sampling_diagnostics.describe_count(self.maps_spin.value())
        half_width = diagnostics.get("worst_case_mc95_half_width")
        error_text = "unknown" if half_width is None else "±%.1f percentage points" % (100.0 * half_width)
        self.sampling_note.setText(
            "%s: %d maps. Conservative worst-case 95%% Monte Carlo half-width: %s. "
            "This describes sampling precision only; it does not test model adequacy."
            % (
                diagnostics.get("sampling_label", ""),
                diagnostics.get("map_count", 0),
                error_text,
            )
        )
        tier = diagnostics.get("sampling_tier")
        if tier in ("debug_only", "preview"):
            color = "#fff0e6"
            border = "#cf6b32"
        elif tier == "exploratory":
            color = "#fff7d6"
            border = "#b7962e"
        else:
            color = "#eef7f0"
            border = "#568a61"
        self.sampling_note.setStyleSheet(
            "QLabel { background: %s; border: 1px solid %s; padding: 6px; color: #30343a; }"
            % (color, border)
        )

    def values(self):
        return {
            "bsm_nummaps": int(self.maps_spin.value()),
            "bsm_seed": int(self.seed_spin.value()),
            "bsm_maxtries_per_branch": int(self.maxtries_spin.value()),
        }
