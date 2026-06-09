from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)


class ProjectImportDialog(QDialog):
    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self._plan = plan
        self.setWindowTitle("一键导入项目")
        self.resize(620, 220)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("请选择要导入的项目文件。", self))

        form = QFormLayout()
        self.consensus_combo = self._build_combo(plan.consensus_tree_candidates)
        self.collection_combo = self._build_combo(plan.tree_collection_candidates)
        self.matrix_combo = self._build_combo(plan.matrix_candidates)

        form.addRow("共识树 / 参考树:", self.consensus_combo)
        form.addRow("树集合:", self.collection_combo)
        form.addRow("分布矩阵:", self.matrix_combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_consensus_tree(self):
        return str(self.consensus_combo.currentData() or "")

    def selected_tree_collection(self):
        return str(self.collection_combo.currentData() or "")

    def selected_matrix(self):
        return str(self.matrix_combo.currentData() or "")

    def _build_combo(self, candidates):
        combo = QComboBox(self)
        values = list(candidates or [])
        if not values:
            combo.addItem("不导入", "")
            combo.setEnabled(False)
            return combo
        for candidate in values:
            combo.addItem(str(candidate.label), str(candidate.path))
        return combo
