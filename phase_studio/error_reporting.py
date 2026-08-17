from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

try:
    from phase_studio.version import VERSION as __version__
except Exception:
    from version import VERSION as __version__


_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(\b(?:api[_ -]?token|access[_ -]?token|authorization[_ -]?token|"
    r"bearer[_ -]?token|job[_ -]?token|download[_ -]?token|token)\b[\"']?\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_BEARER_RE = re.compile(r"(?i)(\bBearer\s+)[^\s,;]+")
_TOKEN_URL_RE = re.compile(r"(?i)(/api/user/sharp-ed/(?:status|download)/)[^\s/?#]+")
_TOKEN_QUERY_RE = re.compile(
    r"(?i)([?&](?:token|access_token|api_token|job_token|download_token)=)[^&#\s]+"
)


def sanitize_error_details(value: object) -> str:
    """Remove credentials from any user-visible or copyable diagnostic text."""
    text = str(value or "")
    text = _BEARER_RE.sub(r"\1[REDACTED]", text)
    text = _SECRET_ASSIGNMENT_RE.sub(r"\1[REDACTED]", text)
    text = _TOKEN_URL_RE.sub(r"\1[REDACTED]", text)
    return _TOKEN_QUERY_RE.sub(r"\1[REDACTED]", text)


@dataclass(frozen=True)
class ErrorReport:
    category: str
    subsystem: str
    title: str
    summary: str
    guidance: str
    technical_details: str
    operation: str = ""
    severity: str = "error"

    def diagnostic_block(self) -> str:
        lines = [
            f"Phase Studio {__version__}",
            f"Subsystem: {self.subsystem}",
            f"Category: {self.category}",
        ]
        if self.operation:
            lines.append(f"Operation: {self.operation}")
        lines.extend((f"Summary: {self.summary}", "", self.technical_details.strip()))
        return sanitize_error_details("\n".join(lines).strip())


@dataclass(frozen=True)
class ErrorAction:
    label: str
    callback: Callable[[], None]
    primary: bool = False


def _subsystem_from_message(message: str, fallback: str) -> str:
    lower = message.lower()
    if "sharped" in lower or "sharp-ed" in lower:
        return "SharpED"
    if "superflip" in lower:
        return "Superflip"
    if "edma" in lower:
        return "EDMA"
    if "jana2020" in lower or ".inflip" in lower:
        return "Jana2020"
    if "hkl" in lower or "reflection" in lower:
        return "HKL"
    return fallback or "Phase Studio"


def build_error_report(
    error: object,
    *,
    subsystem: str = "",
    operation: str = "",
    paths: Sequence[Path | str] = (),
    extra_details: str = "",
    severity: str = "error",
) -> ErrorReport:
    """Map an existing exception/message to a concise user-facing category."""
    message = sanitize_error_details(error).strip() or "The operation failed without an error message."
    lower = message.lower()
    resolved_subsystem = _subsystem_from_message(message, subsystem)
    category = "internal"
    title = "Unexpected Phase Studio error"
    summary = "The current operation could not be completed."
    guidance = "Review the Execution Log and copy the technical details if you need to report the problem."

    if "immediate stop requested" in lower or "cancelled by the user" in lower or "canceled by the user" in lower:
        category = "cancelled"
        title = "Operation stopped"
        summary = "The current operation was stopped at your request."
        guidance = "You can review the preserved output in the Execution Log or start another run."
        severity = "warning"
    elif "sharped" in lower or resolved_subsystem == "SharpED":
        resolved_subsystem = "SharpED"
        if any(token in lower for token in ("missing sharped api token", "api token is required", "http error 401", "http error 403", "authentication", "unauthorized", "forbidden")):
            category = "sharped_authentication"
            title = "SharpED authentication failed"
            summary = "The SharpED API token is missing or was rejected."
            guidance = "Open SharpED settings and enter a valid API token before trying again."
        elif any(token in lower for token in ("timed out", "timeout", "polling limit", "did not finish within")):
            category = "sharped_timeout"
            title = "SharpED request timed out"
            summary = "The SharpED server did not finish within the configured limit."
            guidance = "Check the server status or increase the timeout/polling limit in SharpED settings."
        elif any(token in lower for token in ("json parse failed", "not a json object", "malformed", "did not look like")):
            category = "sharped_response"
            title = "Invalid SharpED response"
            summary = "Phase Studio received a response it could not interpret."
            guidance = "Verify the configured server URL and try again. The response details are available below."
        elif "download" in lower and any(token in lower for token in ("failed", "could not", "did not create", "request failed")):
            category = "sharped_download"
            title = "SharpED result could not be downloaded"
            summary = "Phase Studio could not retrieve or save the processed SharpED map."
            guidance = "Check the server connection and working-folder permissions, then retry the operation."
        elif any(token in lower for token in ("request failed", "unreachable", "urlerror", "tls error", "certificate", "name or service", "connection refused", "connection reset")):
            category = "sharped_network"
            title = "SharpED server unavailable"
            summary = "Phase Studio could not connect to the configured SharpED server."
            guidance = "Check your internet connection and the SharpED server URL."
        else:
            category = "sharped_server"
            title = "SharpED processing failed"
            summary = "The SharpED server could not complete the submitted job."
            guidance = "Review the final server detail below, then retry or choose another model if appropriate."
    elif "superflip" in lower:
        resolved_subsystem = "Superflip"
        if "executable not found" in lower or "was not found" in lower:
            category = "superflip_missing"
            title = "Superflip not found"
            summary = "Phase Studio could not find the configured Superflip executable."
            guidance = "Select the installed Superflip executable in Paths and try again."
        elif "could not start" in lower or "blocked this executable" in lower:
            category = "superflip_launch"
            title = "Superflip could not be started"
            summary = "The configured Superflip process could not be launched."
            guidance = "Check the executable path, permissions, and operating-system security policy."
        elif "did not create" in lower or "missing or empty" in lower:
            category = "superflip_output"
            title = "Superflip output was not created"
            summary = "Superflip finished without producing the expected output file."
            guidance = "Review the final Superflip log lines in the technical details and Execution Log."
        else:
            category = "superflip_runtime"
            title = "Superflip did not complete successfully"
            summary = "Superflip stopped with an error during reconstruction."
            guidance = "Review the exit information and final log lines, then check the Superflip input settings."
    elif "edma" in lower:
        resolved_subsystem = "EDMA"
        if "executable not found" in lower or "was not found" in lower:
            category = "edma_missing"
            title = "EDMA not found"
            summary = "Phase Studio could not find the configured EDMA executable."
            guidance = "Select the installed EDMA executable in Paths and try again."
        elif "could not start" in lower or "blocked this executable" in lower:
            category = "edma_launch"
            title = "EDMA could not be started"
            summary = "The configured EDMA process could not be launched."
            guidance = "Check the executable path, permissions, and operating-system security policy."
        elif "did not create" in lower or "coordinate output" in lower:
            category = "edma_output"
            title = "EDMA output was not created"
            summary = "EDMA did not produce the expected coordinate output."
            guidance = "Review the EDMA input and final log lines in the technical details."
        else:
            category = "edma_runtime"
            title = "EDMA failed"
            summary = "EDMA stopped while extracting or exporting structure information."
            guidance = "Review the cycle input and final EDMA log lines before trying again."
    elif ("composition" in lower or "unknown element" in lower) and ".inflip" not in lower:
        resolved_subsystem = "Crystal metadata"
        category = "composition"
        title = "Invalid composition"
        summary = "Phase Studio could not interpret the selected chemical composition."
        guidance = "Use valid element symbols followed by positive counts, as shown in Help."
    elif ("space-group" in lower or "space group" in lower or "spacegroup" in lower) and ".inflip" not in lower:
        resolved_subsystem = "Crystal metadata"
        category = "space_group"
        title = "Invalid space group"
        summary = "The selected space-group information could not be resolved consistently."
        guidance = "Check the symbol and number. They must identify the same space group."
    elif ("unit-cell" in lower or "unit cell" in lower or "cell parameter" in lower) and ".inflip" not in lower:
        resolved_subsystem = "Crystal metadata"
        category = "unit_cell"
        title = "Invalid unit cell"
        summary = "The selected unit-cell parameters are missing or invalid."
        guidance = "Provide all six physical unit-cell parameters or select a readable metadata source."
    elif "reference" in lower and any(token in lower for token in ("not found", "does not exist", "no longer exists", "could not read", "requires a cif")):
        category = "reference_missing"
        title = "Reference file unavailable"
        summary = "Phase Studio could not read the selected reference file."
        guidance = "Select another reference file or choose Manual crystal metadata."
    elif ".inflip" in lower or "inflip" in lower:
        resolved_subsystem = "Jana2020"
        category = "inflip"
        title = "Jana2020 hand-off could not be loaded"
        summary = "The supplied .inflip input is missing, unreadable, or incomplete."
        guidance = "Select a valid Jana2020 .inflip file containing the required crystallographic input."
    elif "jana2020" in lower or "hand-off" in lower:
        resolved_subsystem = "Jana2020"
        category = "jana_handoff"
        title = "Jana2020 hand-off failed"
        summary = "Phase Studio could not prepare or transfer the selected result to Jana2020."
        guidance = "Check that the selected cycle, map, and original Jana2020 input are still available."
    elif "hkl" in lower or "reflection" in lower or resolved_subsystem == "HKL":
        resolved_subsystem = "HKL"
        if any(token in lower for token in ("not found", "does not exist", "select an external")):
            category = "hkl_missing"
            title = "HKL file not found"
            summary = "Phase Studio could not read the selected reflection file."
            guidance = "Select an existing HKL file or a Jana .inflip containing reflections."
        else:
            category = "hkl_invalid"
            title = "HKL validation failed"
            summary = "The reflection data could not be parsed using the selected HKL format."
            guidance = "Check the selected reflection format and the HKL column layout."
    elif isinstance(error, FileNotFoundError) or "file not found" in lower or "does not exist" in lower:
        category = "file_missing"
        title = "Input file not found"
        summary = "Phase Studio could not read a required input file."
        guidance = "Select an existing file and try the operation again."
    elif isinstance(error, PermissionError) or "permission denied" in lower or "access is denied" in lower:
        category = "file_permission"
        title = "File access denied"
        summary = "Phase Studio does not have permission to read or write a required file."
        guidance = "Choose a writable working folder and check the file permissions."
    elif any(token in lower for token in ("cannot create", "could not create", "cannot write", "could not write", "read-only file system")):
        category = "file_write"
        title = "Cannot write output"
        summary = "Phase Studio could not create the required working file or folder."
        guidance = "Choose another working directory and verify available space and permissions."
    elif resolved_subsystem == "Structure viewer":
        category = "structure_viewer"
        title = "Structure preview unavailable"
        summary = "Phase Studio could not load one structure preview."
        guidance = "The pipeline can continue; review the structure file and technical details in the Execution Log."
    elif "metadata" in lower:
        resolved_subsystem = "Crystal metadata"
        category = "metadata"
        title = "Crystal metadata unavailable"
        summary = "The selected crystal metadata source is incomplete or unavailable."
        guidance = "Select a readable metadata source or complete the Manual metadata fields."

    path_lines = [f"Path: {Path(path)}" for path in paths if str(path).strip()]
    error_type = type(error).__name__ if isinstance(error, BaseException) else "Error"
    technical_parts = [f"{error_type}: {message}", *path_lines]
    if extra_details.strip():
        technical_parts.extend(("", sanitize_error_details(extra_details).strip()))
    return ErrorReport(
        category=category,
        subsystem=resolved_subsystem,
        title=title,
        summary=summary,
        guidance=guidance,
        technical_details=sanitize_error_details("\n".join(technical_parts)),
        operation=operation,
        severity=severity,
    )


def build_validation_report(issues: Sequence[str], *, technical_details: str = "") -> ErrorReport:
    unique = list(dict.fromkeys(str(issue).strip() for issue in issues if str(issue).strip()))
    bullets = "\n".join(f"• {issue}" for issue in unique)
    return ErrorReport(
        category="input_validation",
        subsystem="Input",
        title="Cannot start pipeline",
        summary="Please fix the following before starting:\n" + bullets,
        guidance="Open the relevant configuration page, correct the listed items, and start the pipeline again.",
        technical_details=sanitize_error_details(technical_details or bullets),
        operation="Pre-run validation",
        severity="error",
    )


def show_phase_studio_error(
    parent: object,
    report: ErrorReport,
    actions: Sequence[ErrorAction] = (),
) -> str:
    """Show one compact, expandable, cross-platform Phase Studio error dialog."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QHBoxLayout,
        QLabel,
        QPlainTextEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    dialog = QDialog(parent)
    dialog.setObjectName("phaseStudioErrorDialog")
    dialog.setProperty("severity", report.severity)
    dialog.setWindowTitle(f"Phase Studio — {report.title}")
    dialog.setMinimumWidth(520)
    dialog.resize(620, 280)

    root = QVBoxLayout(dialog)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    header = QWidget()
    header.setObjectName("errorDialogHeader")
    header_layout = QVBoxLayout(header)
    header_layout.setContentsMargins(18, 12, 18, 12)
    header_layout.setSpacing(2)
    eyebrow = QLabel(report.subsystem.upper())
    eyebrow.setObjectName("errorDialogEyebrow")
    title = QLabel(report.title)
    title.setObjectName("errorDialogTitle")
    title.setWordWrap(True)
    header_layout.addWidget(eyebrow)
    header_layout.addWidget(title)
    root.addWidget(header)

    body = QWidget()
    body.setObjectName("errorDialogBody")
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(18, 14, 18, 14)
    body_layout.setSpacing(6)
    what_label = QLabel("WHAT HAPPENED")
    what_label.setObjectName("errorDialogSectionLabel")
    summary = QLabel(report.summary)
    summary.setObjectName("errorDialogSummary")
    summary.setWordWrap(True)
    action_label = QLabel("WHAT YOU CAN DO")
    action_label.setObjectName("errorDialogSectionLabel")
    guidance = QLabel(report.guidance)
    guidance.setObjectName("errorDialogGuidance")
    guidance.setWordWrap(True)
    body_layout.addWidget(what_label)
    body_layout.addWidget(summary)
    body_layout.addSpacing(4)
    body_layout.addWidget(action_label)
    body_layout.addWidget(guidance)

    details = QPlainTextEdit(report.diagnostic_block())
    details.setObjectName("errorDialogDetails")
    details.setReadOnly(True)
    details.setLineWrapMode(QPlainTextEdit.NoWrap)
    details.setMaximumHeight(220)
    details_font = QFont("Cascadia Mono")
    details_font.setStyleHint(QFont.Monospace)
    details.setFont(details_font)
    details.setVisible(False)
    body_layout.addWidget(details)

    button_row = QHBoxLayout()
    button_row.setSpacing(7)
    details_button = QPushButton("Show details")
    details_button.setObjectName("errorDetailsButton")
    copy_button = QPushButton("Copy details")
    copy_button.setObjectName("errorCopyButton")
    copy_button.setVisible(False)
    button_row.addWidget(details_button)
    button_row.addWidget(copy_button)
    button_row.addStretch(1)

    selected = {"label": ""}

    def toggle_details() -> None:
        expanded = not details.isVisible()
        details.setVisible(expanded)
        copy_button.setVisible(expanded)
        details_button.setText("Hide details" if expanded else "Show details")
        dialog.adjustSize()
        dialog.resize(max(520, min(700, dialog.width())), min(610, dialog.height()))

    details_button.clicked.connect(toggle_details)
    copy_button.clicked.connect(lambda: QApplication.clipboard().setText(report.diagnostic_block()))

    for action in actions:
        button = QPushButton(action.label)
        button.setObjectName("errorPrimaryAction" if action.primary else "errorAction")

        def choose(_checked: bool = False, selected_action: ErrorAction = action) -> None:
            selected["label"] = selected_action.label
            dialog.accept()

        button.clicked.connect(choose)
        button_row.addWidget(button)

    close_button = QPushButton("Close")
    close_button.setObjectName("errorCloseButton")
    close_button.clicked.connect(dialog.reject)
    close_button.setDefault(not any(action.primary for action in actions))
    button_row.addWidget(close_button)
    body_layout.addSpacing(5)
    body_layout.addLayout(button_row)
    root.addWidget(body)

    dialog.exec()
    chosen = selected["label"]
    if chosen:
        for action in actions:
            if action.label == chosen:
                action.callback()
                break
    return chosen
