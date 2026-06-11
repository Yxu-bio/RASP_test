from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from domain.models.bayestraits_config import BAYESTRAITS_CONTINUOUS_TRANSFORMS
from domain.models.phytools_config import (
    PHYTOOLS_METHODS,
    PhytoolsConfig,
    phytools_method_kind,
    phytools_is_experimental,
    normalize_phytools_method,
)


class PhytoolsConfigDialog(QDialog):
    def __init__(
        self,
        trait_columns,
        config=None,
        parent=None,
        show_threads=False,
        title="phytools",
        method_keys=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.show_threads = bool(show_threads)
        allowed = [str(x) for x in list(method_keys or []) if str(x) in PHYTOOLS_METHODS]
        self.method_keys = allowed if allowed else list(PHYTOOLS_METHODS.keys())
        self.trait_columns = [str(x).strip() for x in list(trait_columns or []) if str(x).strip()]
        if config is not None and list(getattr(config, "trait_columns", []) or []) == self.trait_columns:
            self._config = config
        else:
            self._config = PhytoolsConfig.default_for_columns(self.trait_columns)
        self._build_ui()
        self._load_config(self._config)
        self._update_controls()

    def config(self):
        return self._config

    def _build_ui(self):
        layout = QVBoxLayout(self)
        group = QGroupBox("Model", self)
        form = QFormLayout(group)

        self.method_combo = QComboBox(group)
        for key in self.method_keys:
            label = PHYTOOLS_METHODS[key]
            self.method_combo.addItem(label, key)
        self.method_combo.currentIndexChanged.connect(self._update_controls)
        self.trait_combo = QComboBox(group)
        for column in self.trait_columns:
            self.trait_combo.addItem(column, column)
        self.transform_combo = QComboBox(group)
        for key, label in BAYESTRAITS_CONTINUOUS_TRANSFORMS.items():
            self.transform_combo.addItem(label, key)
        self.threads_spin = QSpinBox(group)
        self.threads_spin.setRange(1, 128)
        self.threads_spin.setValue(1)
        self.anc_ml_maxit_spin = QSpinBox(group)
        self.anc_ml_maxit_spin.setRange(100, 1000000)
        self.anc_ml_maxit_spin.setSingleStep(100)
        self.anc_ml_maxit_spin.setValue(2000)
        self.bayes_iterations_spin = QSpinBox(group)
        self.bayes_iterations_spin.setRange(100, 2000000000)
        self.bayes_iterations_spin.setSingleStep(1000)
        self.bayes_iterations_spin.setValue(10000)
        self.bayes_sample_spin = QSpinBox(group)
        self.bayes_sample_spin.setRange(1, 2000000000)
        self.bayes_sample_spin.setSingleStep(100)
        self.bayes_sample_spin.setValue(1000)
        self.bayes_burnin_spin = QSpinBox(group)
        self.bayes_burnin_spin.setRange(0, 2000000000)
        self.bayes_burnin_spin.setSingleStep(1000)
        self.bayes_burnin_spin.setValue(0)
        self.seed_spin = QSpinBox(group)
        self.seed_spin.setRange(0, 2147483647)
        self.seed_spin.setValue(1)
        self.experimental_note = QLabel(
            "Experimental anc.ML methods are exposed for testing only; "
            "the current bundled R/phytools runtime may fail on Windows.",
            group,
        )
        self.experimental_note.setWordWrap(True)

        form.addRow("Method", self.method_combo)
        form.addRow("Trait", self.trait_combo)
        form.addRow("Trait transform", self.transform_combo)
        self.anc_ml_maxit_label = QLabel("anc.ML maxit", group)
        form.addRow(self.anc_ml_maxit_label, self.anc_ml_maxit_spin)
        self.bayes_iterations_label = QLabel("MCMC iterations", group)
        form.addRow(self.bayes_iterations_label, self.bayes_iterations_spin)
        self.bayes_sample_label = QLabel("Sample frequency", group)
        form.addRow(self.bayes_sample_label, self.bayes_sample_spin)
        self.bayes_burnin_label = QLabel("Burn-in", group)
        form.addRow(self.bayes_burnin_label, self.bayes_burnin_spin)
        self.seed_label = QLabel("Seed", group)
        form.addRow(self.seed_label, self.seed_spin)
        if self.show_threads:
            form.addRow("Threads", self.threads_spin)
        form.addRow(self.experimental_note)
        layout.addWidget(group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Reset,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Reset).clicked.connect(self._reset_config)
        layout.addWidget(buttons)

    def _load_config(self, config):
        method = normalize_phytools_method(getattr(config, "method", self.method_keys[0]))
        if method not in self.method_keys:
            method = self.method_keys[0]
        self._set_combo_data(self.method_combo, method)
        self._set_combo_data(self.trait_combo, str(getattr(config, "trait_column", "") or ""))
        self._set_combo_data(self.transform_combo, str(getattr(config, "continuous_transform", "none") or "none"))
        self.threads_spin.setValue(max(1, int(getattr(config, "threads", 1) or 1)))
        self.anc_ml_maxit_spin.setValue(max(100, int(getattr(config, "anc_ml_maxit", 2000) or 2000)))
        self.bayes_iterations_spin.setValue(max(100, int(getattr(config, "bayes_iterations", 10000) or 10000)))
        self.bayes_sample_spin.setValue(max(1, int(getattr(config, "bayes_sample_frequency", 1000) or 1000)))
        self.bayes_burnin_spin.setValue(max(0, int(getattr(config, "bayes_burnin", 0) or 0)))
        self.seed_spin.setValue(max(0, int(getattr(config, "seed", 1) or 0)))

    def _collect_config(self):
        return PhytoolsConfig(
            trait_columns=list(self.trait_columns),
            trait_column=str(self.trait_combo.currentData() or self.trait_combo.currentText() or ""),
            method=str(self.method_combo.currentData() or "FASTANC"),
            continuous_transform=str(self.transform_combo.currentData() or "none"),
            threads=int(self.threads_spin.value()),
            anc_ml_maxit=int(self.anc_ml_maxit_spin.value()),
            bayes_iterations=int(self.bayes_iterations_spin.value()),
            bayes_sample_frequency=int(self.bayes_sample_spin.value()),
            bayes_burnin=int(self.bayes_burnin_spin.value()),
            seed=int(self.seed_spin.value()),
        )

    def accept(self):
        try:
            config = self._collect_config()
            config.validate()
        except Exception as exc:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Invalid configuration", str(exc))
            return
        self._config = config
        super().accept()

    def _reset_config(self):
        self._config = PhytoolsConfig.default_for_columns(self.trait_columns)
        self._load_config(self._config)
        self._update_controls()

    def _set_combo_data(self, combo, value):
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _update_controls(self):
        method = str(self.method_combo.currentData() or "FASTANC")
        try:
            is_continuous = phytools_method_kind(method) == "continuous"
        except Exception:
            is_continuous = False
        is_bayes = method == "ANC_BAYES"
        is_anc_ml = method.startswith("ANC_ML_")
        is_experimental = False
        try:
            is_experimental = phytools_is_experimental(method)
        except Exception:
            pass
        self.transform_combo.setEnabled(is_continuous)
        if not is_continuous:
            self._set_combo_data(self.transform_combo, "none")
        self.anc_ml_maxit_label.setVisible(is_anc_ml)
        self.anc_ml_maxit_spin.setVisible(is_anc_ml)
        self.bayes_iterations_label.setVisible(is_bayes)
        self.bayes_iterations_spin.setVisible(is_bayes)
        self.bayes_sample_label.setVisible(is_bayes)
        self.bayes_sample_spin.setVisible(is_bayes)
        self.bayes_burnin_label.setVisible(is_bayes)
        self.bayes_burnin_spin.setVisible(is_bayes)
        self.seed_label.setVisible(is_bayes)
        self.seed_spin.setVisible(is_bayes)
        self.experimental_note.setVisible(is_experimental)
