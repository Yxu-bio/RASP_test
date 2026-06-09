from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QSpinBox,
    QCheckBox,
    QGroupBox,
)


class TreeCollectionInfoPanel(QWidget):
    pre_burnin_changed = pyqtSignal(int)
    post_burnin_changed = pyqtSignal(int)
    enable_random_sampling_changed = pyqtSignal(bool)
    random_sample_size_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        # -----------------------------
        # 只读摘要信息
        # -----------------------------
        self.label_raw_tree_count = QLabel("0")
        self.label_parse_error_count = QLabel("0")
        self.label_bifurcating_count = QLabel("0")
        self.label_loaded_count = QLabel("0")
        self.label_analysis_count = QLabel("0")
        self.label_consensus_tree = QLabel("未导入")

        # -----------------------------
        # 可编辑参数
        # -----------------------------
        self.spin_pre_burnin = QSpinBox()
        self.spin_pre_burnin.setMinimum(0)
        self.spin_pre_burnin.setMaximum(10**9)

        self.spin_post_burnin = QSpinBox()
        self.spin_post_burnin.setMinimum(0)
        self.spin_post_burnin.setMaximum(10**9)

        self.check_random_sampling = QCheckBox("启用随机树抽样")

        self.spin_random_sample_size = QSpinBox()
        self.spin_random_sample_size.setMinimum(0)
        self.spin_random_sample_size.setMaximum(10**9)
        self.spin_random_sample_size.setEnabled(False)

        # -----------------------------
        # 表单布局
        # -----------------------------
        group = QGroupBox("树")
        form = QFormLayout()
        form.addRow("原始树总数", self.label_raw_tree_count)
        form.addRow("解析失败数", self.label_parse_error_count)
        form.addRow("导入的二歧树数量", self.label_bifurcating_count)
        form.addRow("载入前舍弃", self.spin_pre_burnin)
        form.addRow("载入后舍弃", self.spin_post_burnin)
        form.addRow("随机树", self.spin_random_sample_size)
        form.addRow("", self.check_random_sampling)
        form.addRow("当前已载入树数", self.label_loaded_count)
        form.addRow("当前分析树数", self.label_analysis_count)
        form.addRow("当前共识树", self.label_consensus_tree)
        group.setLayout(form)

        layout = QVBoxLayout()
        layout.addWidget(group)
        layout.addStretch(1)
        self.setLayout(layout)

        # -----------------------------
        # 信号绑定
        # -----------------------------
        self.spin_pre_burnin.valueChanged.connect(self.pre_burnin_changed.emit)
        self.spin_post_burnin.valueChanged.connect(self.post_burnin_changed.emit)
        self.spin_random_sample_size.valueChanged.connect(self.random_sample_size_changed.emit)
        self.check_random_sampling.toggled.connect(self._on_random_sampling_toggled)

    def _on_random_sampling_toggled(self, checked: bool) -> None:
        self.spin_random_sample_size.setEnabled(bool(checked))
        self.enable_random_sampling_changed.emit(bool(checked))

    def set_options(
        self,
        pre_burnin: int,
        post_burnin: int,
        enable_sampling: bool,
        sample_size: int,
    ) -> None:
        self.spin_pre_burnin.blockSignals(True)
        self.spin_post_burnin.blockSignals(True)
        self.check_random_sampling.blockSignals(True)
        self.spin_random_sample_size.blockSignals(True)

        self.spin_pre_burnin.setValue(max(0, int(pre_burnin)))
        self.spin_post_burnin.setValue(max(0, int(post_burnin)))
        self.check_random_sampling.setChecked(bool(enable_sampling))
        self.spin_random_sample_size.setValue(max(0, int(sample_size)))
        self.spin_random_sample_size.setEnabled(bool(enable_sampling))

        self.spin_pre_burnin.blockSignals(False)
        self.spin_post_burnin.blockSignals(False)
        self.check_random_sampling.blockSignals(False)
        self.spin_random_sample_size.blockSignals(False)

    def set_tree_summary(
        self,
            raw_tree_count: int,
            parse_error_count: int,
            bifurcating_count: int,
            loaded_count: int,
            analysis_count: int,
    ) -> None:
        self.label_raw_tree_count.setText(str(max(0, int(raw_tree_count))))
        self.label_parse_error_count.setText(str(max(0, int(parse_error_count))))
        self.label_bifurcating_count.setText(str(max(0, int(bifurcating_count))))
        self.label_loaded_count.setText(str(max(0, int(loaded_count))))
        self.label_analysis_count.setText(str(max(0, int(analysis_count))))

    def set_consensus_tree_summary(self, text: str) -> None:
        self.label_consensus_tree.setText(text or "未导入")