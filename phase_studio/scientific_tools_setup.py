"""One local scientific-tools setup step, separate from account onboarding."""
from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from phase_studio import requirements as reqs
from phase_studio import scientific_tools as tools
from phase_studio.ui_branding import (
    activate_owned_dialog, apply_safe_dialog_geometry, create_phase_studio_brand_header,
    apply_established_icon,
)


OFFICIAL_PAGE = "https://superflip.fzu.cz/"
LICENCE_URLS = {
    reqs.RequirementKind.SUPERFLIP: reqs.SUPERFLIP_LICENSE_URL,
    reqs.RequirementKind.EDMA: reqs.EDMA_LICENSE_URL,
}
DESCRIPTIONS = {
    reqs.RequirementKind.SUPERFLIP: (
        "Required for charge-flipping structure solution",
        "Superflip solves the crystallographic phase problem using the charge-flipping algorithm. "
        "Phase Studio uses it to reconstruct electron-density maps from diffraction data.",
    ),
    reqs.RequirementKind.EDMA: (
        "Required for locating atomic sites in electron-density maps",
        "EDMA identifies atomic positions in electron-density maps. Phase Studio uses these results "
        "to display structures and prepare atomic models.",
    ),
}


class _Signals(QObject):
    progress = Signal(str)
    completed = Signal(object, object)


class _Task(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = _Signals()
        self.cancelled = Event()

    def run(self):
        try:
            value = self.operation(self.signals.progress.emit, self.cancelled.is_set)
            error = None
        except Exception as exc:
            value, error = None, exc
        self.signals.completed.emit(value, error)


class ScientificToolsSetupDialog(QDialog):
    def __init__(self, parent, statuses, configured=None, *, validator=None,
                 distributions=None, installer=None):
        super().__init__(parent)
        self.statuses = {s.kind: s for s in statuses if s.kind in DESCRIPTIONS}
        if not self.statuses:
            raise ValueError("At least one required local scientific tool is needed.")
        self.configured = configured or {}
        self.validator = validator or tools.validate_program
        self.distributions = tools.APPROVED_DISTRIBUTIONS if distributions is None else distributions
        self.installer = installer or tools.install_distribution
        self.selected_paths = {kind: str(s.path) for kind, s in self.statuses.items() if s.ok and s.path}
        self._closed = False
        self._task = None
        self.setObjectName("requirementRemediationDialog")
        combined = len(self.statuses) > 1
        title = "Set up scientific tools" if combined else next(iter(self.statuses.values())).title
        self.setWindowTitle(title)
        self.setModal(True)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(create_phase_studio_brand_header())
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 10, 20, 6)
        heading = QLabel(title)
        heading.setStyleSheet('font-family:"Segoe UI";font-size:17pt;font-weight:600;color:#001170;')
        title_row = QHBoxLayout()
        icon = QLabel()
        apply_established_icon(icon, "workflow_settings", size=26)
        title_row.addWidget(icon)
        title_row.addWidget(heading, 1)
        header_layout.addLayout(title_row)
        subtitle = QLabel("Phase Studio needs these programs to run the selected workflow." if combined
                          else DESCRIPTIONS[next(iter(self.statuses))][0])
        subtitle.setWordWrap(True)
        header_layout.addWidget(subtitle)
        root.addWidget(header)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 8, 20, 12)
        body_layout.setSpacing(8)
        self.status_labels = {}
        self.locate_buttons = {}
        self.install_buttons = {}
        self.feedback = QLabel()
        self.feedback.setObjectName("requirementFeedback")
        self.feedback.setWordWrap(True)
        self.feedback.hide()
        body_layout.addWidget(self.feedback)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        body_layout.addWidget(self.progress)
        official_action_added = False
        for kind, status in self.statuses.items():
            label = "Superflip" if kind is reqs.RequirementKind.SUPERFLIP else "EDMA"
            if combined:
                body_layout.addWidget(QLabel(f"<b>{label}</b>"))
            description = QLabel(DESCRIPTIONS[kind][1])
            description.setWordWrap(True)
            body_layout.addWidget(description)
            state = QLabel()
            state.setObjectName("requirementMessage")
            state.setWordWrap(True)
            self.status_labels[kind] = state
            body_layout.addWidget(state)
            self._show_status(kind, status)
            actions = QHBoxLayout()
            approved = self.distributions.get(kind.value)
            if approved is not None:
                button = QPushButton(f"Download and set up {label}")
                button.setObjectName("primaryButton")
                button.clicked.connect(lambda _=False, k=kind: self._install(k))
                self.install_buttons[kind] = button
            else:
                button = QPushButton("Official download page")
                button.setObjectName("primaryButton")
                button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(OFFICIAL_PAGE)))
            if approved is not None or not official_action_added:
                actions.addWidget(button)
                official_action_added = approved is None
            else:
                button.deleteLater()
            actions.addStretch(1)
            body_layout.addLayout(actions)
            body_layout.addWidget(QLabel("Already have this program installed?"))
            manual = QHBoxLayout()
            locate = QPushButton(f"Locate existing {label}")
            locate.setObjectName("requirementBrowseButton")
            locate.clicked.connect(lambda _=False, k=kind: self._browse(k))
            self.locate_buttons[kind] = locate
            manual.addWidget(locate)
            licence = QPushButton("View licence information")
            licence.clicked.connect(lambda _=False, k=kind: QDesktopServices.openUrl(QUrl(LICENCE_URLS[k])))
            manual.addWidget(licence)
            manual.addStretch(1)
            body_layout.addLayout(manual)
        notice = QLabel("Superflip and EDMA are third-party scientific programs distributed under their respective licences.")
        notice.setWordWrap(True)
        body_layout.addWidget(notice)
        if any(k.value not in self.distributions for k in self.statuses):
            notice = QLabel("Automatic setup is unavailable until the distribution licence and package integrity are verified.")
            notice.setWordWrap(True)
            body_layout.addWidget(notice)
        body_layout.addStretch(1)
        self._scroll.setWidget(body)
        root.addWidget(self._scroll, 1)
        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 10, 20, 12)
        self.back_button = QPushButton("Back")
        self.back_button.setObjectName("requirementBackButton")
        self.back_button.clicked.connect(self.reject)
        layout.addWidget(self.back_button)
        layout.addStretch(1)
        self.continue_button = QPushButton("Continue")
        self.continue_button.setObjectName("primaryButton")
        self.continue_button.clicked.connect(self.accept)
        self.continue_button.setDefault(True)
        layout.addWidget(self.continue_button)
        root.addWidget(footer)
        self._update_actions()
        apply_safe_dialog_geometry(self, 650, 640 if combined else 510)

    def _show_status(self, kind, status):
        label = self.status_labels[kind]
        label.setText("\u2713 Installed and verified" if status.ok else "\u25cb " + status.message)
        label.setStyleSheet("color:#001170;" if status.ok else "color:#6b4650;")

    def _update_actions(self):
        busy = self._task is not None
        self.continue_button.setEnabled(not busy and len(self.selected_paths) == len(self.statuses))
        for button in [*self.locate_buttons.values(), *self.install_buttons.values()]:
            button.setEnabled(not busy)

    def _browse(self, kind):
        path, _ = QFileDialog.getOpenFileName(self, "Locate " + kind.value, self.configured.get(kind, ""),
                                             "Windows programs (*.exe);;All files (*)")
        if path:
            self.verify_path(kind, path)

    def verify_path(self, kind, path):
        def operation(report, cancelled):
            report("Checking compatibility")
            if kind is reqs.RequirementKind.SUPERFLIP and reqs.is_phase_studio_wrapper(Path(path)):
                return (None, reqs.RequirementStatus(kind, reqs.RequirementState.IS_PHASE_STUDIO_WRAPPER))
            validated = self.validator(kind, Path(path))
            status = reqs.RequirementStatus(kind, reqs.RequirementState(validated.state), path=Path(path).resolve())
            return (str(Path(path).resolve()) if status.ok else None, status)
        self._start(kind, operation)

    def _install(self, kind):
        from phase_studio.requirements_ui import confirm_third_party_download
        if not confirm_third_party_download(self, kind.value,
                                             licence_url=self.distributions[kind.value].licence_reference):
            return
        destination = tools.managed_tools_directory() / kind.value
        def operation(report, cancelled):
            path = self.installer(kind, destination, policy=self.distributions[kind.value],
                                  progress=report, cancelled=cancelled)
            status = reqs.RequirementStatus(kind, reqs.RequirementState.OK, path=path)
            return str(path), status
        self._start(kind, operation)

    def _start(self, kind, operation):
        if self._closed or self._task is not None:
            return
        self._task = _Task(operation)
        self._task.signals.progress.connect(self._progress)
        self._task.signals.completed.connect(lambda value, error: self._complete(kind, value, error))
        self.progress.show()
        self.feedback.show()
        self.feedback.setText("Checking compatibility")
        self._update_actions()
        self._scroll.verticalScrollBar().setValue(0)
        QThreadPool.globalInstance().start(self._task)

    def _progress(self, text):
        if not self._closed:
            self.feedback.setText(text)

    def _complete(self, kind, value, error):
        if self._closed:
            return
        self._task = None
        self.progress.hide()
        if error is not None:
            import logging
            from phase_studio.error_reporting import sanitize_error_details
            logging.getLogger(__name__).warning("Scientific tool setup: %s", sanitize_error_details(error))
            if self.feedback.text() == "Verifying downloaded files":
                message = "Package integrity verification failed. Nothing was installed. Use the official download page."
            elif self.feedback.text() in ("Preparing download", "Downloading"):
                message = "The program could not be downloaded. Check your internet connection or open the official download page."
            else:
                message = "Phase Studio could not complete the setup. Your existing installation has not been changed. Choose another file or use the official download page."
            self.feedback.setText(message)
        else:
            path, status = value
            self._show_status(kind, status)
            self.statuses[kind] = status
            if path:
                self.selected_paths[kind] = path
                self.feedback.setText("Ready to continue")
            else:
                self.selected_paths.pop(kind, None)
                self.feedback.setText(status.message)
        self._update_actions()
        # A single-tool repair preserves the original one-selection continuation.
        if error is None and len(self.statuses) == 1 and self.continue_button.isEnabled():
            self.accept()

    def accept(self):
        if self._task is None and len(self.selected_paths) == len(self.statuses):
            super().accept()

    def done(self, result):
        self._closed = True
        if self._task is not None:
            self._task.cancelled.set()
        super().done(result)

    def showEvent(self, event):
        super().showEvent(event)
        activate_owned_dialog(self)


def show_scientific_tools_setup(parent, statuses, configured=None):
    dialog = ScientificToolsSetupDialog(parent, statuses, configured)
    if dialog.exec() == QDialog.Accepted:
        return dialog.selected_paths
    return None
