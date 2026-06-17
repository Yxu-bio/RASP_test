from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

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
        layout.addWidget(buttons)

    def values(self):
        return {
            "bsm_nummaps": int(self.maps_spin.value()),
            "bsm_seed": int(self.seed_spin.value()),
            "bsm_maxtries_per_branch": int(self.maxtries_spin.value()),
        }
