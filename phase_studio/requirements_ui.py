"""Shared Qt remediation UI for the pure checks in :mod:`requirements`."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from phase_studio import requirements as reqs
from phase_studio.error_reporting import sanitize_error_details
from phase_studio.ui_branding import (
    apply_safe_dialog_geometry,
    create_phase_studio_brand_header,
    create_phase_studio_context_banner,
)


def show_requirement_remediation_dialog(
    parent: Optional[QWidget],
    status: reqs.RequirementStatus,
    configured_value: str = "",
    *,
    download_dir: Optional[Path] = None,
    download_opener: Optional[Callable[..., object]] = None,
) -> Optional[str]:
    """Return a repaired path/token, or ``None`` for *Skip for now*."""
    kind = status.kind
    dialog = QDialog(parent)
    dialog.setObjectName("requirementRemediationDialog")
    dialog.setWindowTitle(f"Phase Studio — {status.title}")
    dialog.setModal(True)
    root = QVBoxLayout(dialog)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    root.addWidget(create_phase_studio_brand_header())
    subtitle = {
        reqs.RequirementKind.SUPERFLIP: "Locate or install the Superflip executable required by this workflow",
        reqs.RequirementKind.EDMA: "Locate or install the EDMA executable required by this workflow",
        reqs.RequirementKind.SHARPED: "Configure access before SharpED processing starts",
    }[kind]
    root.addWidget(create_phase_studio_context_banner(status.title.upper(), subtitle))

    body = QWidget(dialog)
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(22, 18, 22, 18)
    body_layout.setSpacing(10)
    explanation = QLabel(status.message)
    explanation.setObjectName("requirementMessage")
    explanation.setWordWrap(True)
    body_layout.addWidget(explanation)
    feedback = QLabel("")
    feedback.setObjectName("requirementFeedback")
    feedback.setWordWrap(True)
    feedback.setStyleSheet("color: #b94a48;")
    feedback.setVisible(False)

    selected: dict[str, Optional[str]] = {"value": None}
    buttons = QHBoxLayout()
    buttons.setSpacing(8)

    def show_feedback(message: str) -> None:
        feedback.setText(str(message))
        feedback.setVisible(True)
        dialog.adjustSize()

    if kind is reqs.RequirementKind.SHARPED:
        account_text = QLabel(
            "SharpED processing requires an active Jana2020 or SharpED account and an API token."
        )
        account_text.setWordWrap(True)
        body_layout.addWidget(account_text)
        token_row = QFormLayout()
        token_edit = QLineEdit(str(configured_value or ""))
        token_edit.setObjectName("requirementTokenEdit")
        token_edit.setEchoMode(QLineEdit.Password)
        token_edit.setPlaceholderText("Enter API token")
        token_row.addRow("API token", token_edit)
        body_layout.addLayout(token_row)
        open_account = QPushButton("Open SharpED account")
        open_account.setObjectName("requirementOpenAccountButton")
        open_account.clicked.connect(
            lambda _checked=False: QDesktopServices.openUrl(QUrl(reqs.SHARPED_ACCOUNT_URL))
        )
        set_token = QPushButton("Set token")
        set_token.setObjectName("primaryButton")

        def accept_token() -> None:
            token = token_edit.text().strip()
            if not token:
                show_feedback("Enter an API token or choose Skip for now.")
                return
            selected["value"] = token
            dialog.accept()

        set_token.clicked.connect(accept_token)
        buttons.addWidget(open_account)
        buttons.addStretch(1)
        buttons.addWidget(set_token)
    else:
        license_text = QLabel(
            'This third-party program is distributed by its authors. '
            '<a href="https://superflip.fzu.cz/">Review license information</a> before downloading.'
        )
        license_text.setObjectName("requirementLicenseText")
        license_text.setOpenExternalLinks(True)
        license_text.setWordWrap(True)
        body_layout.addWidget(license_text)
        browse_button = QPushButton("Browse…")
        browse_button.setObjectName("requirementBrowseButton")
        open_download = QPushButton("Open download page")
        open_download.setObjectName("requirementOpenDownloadButton")
        download_button = QPushButton("Download automatically")
        download_button.setObjectName("primaryButton")
        label = "Superflip" if kind is reqs.RequirementKind.SUPERFLIP else "EDMA"
        download_url = (
            reqs.SUPERFLIP_DOWNLOAD_URL
            if kind is reqs.RequirementKind.SUPERFLIP else reqs.EDMA_DOWNLOAD_URL
        )

        def accept_path(path_text: str) -> bool:
            path = reqs.resolve_executable(path_text)
            if path is None or not reqs.is_expected_executable(kind, path):
                show_feedback(f"The selected file is not a valid {kind.value} executable.")
                return False
            if kind is reqs.RequirementKind.SUPERFLIP and reqs.is_phase_studio_wrapper(path):
                show_feedback("The selected file is the Phase Studio Jana2020 wrapper. Select the real Superflip executable.")
                return False
            selected["value"] = str(path)
            dialog.accept()
            return True

        def browse() -> None:
            path = QFileDialog.getOpenFileName(
                dialog, f"Select {label} executable", str(configured_value or ""),
                "Executables (*.exe);;All files (*)",
            )[0]
            if path:
                accept_path(path)

        def automatic_download() -> None:
            answer = QMessageBox.question(
                dialog,
                f"Download {label}",
                f"{label} is third-party software supplied under its authors' license. "
                "By choosing Yes, you confirm that you reviewed and accept the license information at "
                f"{reqs.SUPERFLIP_LICENSE_URL}\n\nDownload and install {label} for Phase Studio now?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return
            destination = download_dir
            if destination is None:
                base = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
                destination = Path(base or str(Path.home() / ".phase_studio")) / "external_tools" / kind.value
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                path = reqs.download_requirement_executable(
                    kind, destination, opener=download_opener,
                )
            except Exception as exc:
                show_feedback("Automatic download failed: " + sanitize_error_details(exc))
            else:
                accept_path(str(path))
            finally:
                QApplication.restoreOverrideCursor()

        browse_button.clicked.connect(browse)
        open_download.clicked.connect(
            lambda _checked=False: QDesktopServices.openUrl(QUrl(download_url))
        )
        download_button.clicked.connect(automatic_download)
        buttons.addWidget(browse_button)
        buttons.addWidget(open_download)
        buttons.addStretch(1)
        buttons.addWidget(download_button)

    body_layout.addWidget(feedback)
    skip_button = QPushButton("Skip for now")
    skip_button.setObjectName("requirementSkipButton")
    skip_button.clicked.connect(dialog.reject)
    buttons.addWidget(skip_button)
    body_layout.addLayout(buttons)
    root.addWidget(body)
    apply_safe_dialog_geometry(dialog, 720, 360)
    dialog.exec()
    return selected["value"]


def run_remediation_loop(
    parent: Optional[QWidget],
    check: Callable[[], reqs.PreflightResult],
    current_value: Callable[[reqs.RequirementKind], str],
    persist: Callable[[reqs.RequirementKind, str, bool], None],
    on_success: Optional[Callable[[reqs.PreflightResult], None]] = None,
    *,
    download_dir: Optional[Path] = None,
    download_opener: Optional[Callable[..., object]] = None,
) -> bool:
    """Run check–repair–recheck while callers retain state ownership."""
    while True:
        result = check()
        for repaired in result.repaired:
            persist(repaired.kind, str(repaired.path), True)
        if result.ok:
            if on_success is not None:
                on_success(result)
            return True
        status = result.first_failure
        if status is None:
            return True
        value = show_requirement_remediation_dialog(
            parent, status, current_value(status.kind),
            download_dir=download_dir, download_opener=download_opener,
        )
        if value is None:
            return False
        persist(status.kind, value, False)
