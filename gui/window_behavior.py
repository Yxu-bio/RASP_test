from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QSizePolicy


def configure_resizable_window(window, size_grip=True):
    """Apply consistent native resize and title-bar controls to app dialogs."""
    flags = window.windowFlags()
    flags &= ~Qt.WindowContextHelpButtonHint
    flags &= ~Qt.MSWindowsFixedSizeDialogHint
    flags |= (
        Qt.WindowTitleHint
        | Qt.WindowSystemMenuHint
        | Qt.WindowMinimizeButtonHint
        | Qt.WindowMaximizeButtonHint
        | Qt.WindowCloseButtonHint
    )
    window.setWindowFlags(flags)
    window.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    if size_grip and isinstance(window, QDialog):
        window.setSizeGripEnabled(True)
    return window
