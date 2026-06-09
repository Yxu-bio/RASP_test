from gui.dialogs.sdec_config_dialog import SDECConfigDialog


class DECConfigDialog(SDECConfigDialog):
    """Single-tree DEC uses the same lagrange-ng configuration surface as S-DEC."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("threads_label", "Workers:")
        super().__init__(*args, **kwargs)
