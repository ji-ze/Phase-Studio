from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

try:
    from phase_studio.version import VERSION as __version__
except Exception:
    from version import VERSION as __version__


_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(\b(?:api[_ -]?token|access[_ -]?token|authorization[_ -]?token|"
    r"bearer[_ -]?token|job[_ -]?token|download[_ -]?token|api[_ -]?key|access[_ -]?key|"
    r"authorization[_ -]?code|code[_ -]?verifier|pkce[_ -]?verifier|token)\b[\"']?\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_BEARER_RE = re.compile(r"(?i)(\bBearer\s+)[^\s,;]+")
_TOKEN_URL_RE = re.compile(r"(?i)(/api/user/sharp-ed/(?:status|download)/)[^\s/?#]+")
_TOKEN_QUERY_RE = re.compile(
    r"(?i)([?&](?:code|code_verifier|token|access_token|api_token|job_token|download_token)=)[^&#\s]+"
)

_PRIVATE_VALUES: set[str] = set()


def register_private_value(value: str) -> None:
    """Redact a configured credential even if a server echoes it without a label."""
    if str(value or "").strip():
        _PRIVATE_VALUES.add(str(value).strip())


def sanitize_error_details(value: object) -> str:
    """Remove credentials from any user-visible or copyable diagnostic text."""
    text = str(value or "")
    for private in sorted(tuple(_PRIVATE_VALUES), key=len, reverse=True):
        text = text.replace(private, "[REDACTED]")
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
    if "superflip" in lower:
        return "Superflip"
    if "sharped" in lower or "sharp-ed" in lower:
        return "SharpED"
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
    resolved_subsystem = "EDMA" if subsystem == "EDMA" else _subsystem_from_message(message, subsystem)
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
    elif (
        "superflip executable" in lower
        and any(token in lower for token in ("not found", "was not found", "could not be resolved"))
    ):
        resolved_subsystem = "Jana2020 integration"
        category = "superflip_runtime"
        title = "Jana2020 Superflip runtime unavailable"
        summary = "The Superflip executable for the active Jana2020 installation could not be resolved."
        guidance = "Repair the Phase Studio integration for this Jana2020 installation and try again."
    elif resolved_subsystem != "EDMA" and ("sharped" in lower or resolved_subsystem == "SharpED"):
        resolved_subsystem = "SharpED"
        if (getattr(error, "code", None) == 403 or "http error 403" in lower
                or "http 403" in lower or getattr(error, "category", "") == "authorization"):
            category = "sharped_access_denied"
            title = "SharpED access unavailable"
            summary = "SharpED denied this request."
            guidance = "Check the account's access with the SharpED administrator. The response does not by itself establish a billing problem."
        elif any(token in lower for token in ("missing sharped api token", "api token is required", "http error 401", "authentication", "unauthorized")):
            category = "sharped_authentication"
            title = "SharpED account access"
            summary = "The SharpED access key is missing or was not accepted."
            guidance = "Connect using your existing Jana2020 account and check its SharpED access key."
        elif "http header" in lower and "invalid sharped" in lower:
            category = "sharped_configuration"
            title = "Invalid SharpED request configuration"
            summary = "A configured HTTP header cannot be sent safely."
            guidance = "Check the client header configuration. Unicode metadata must remain in the UTF-8 request body."
        elif any(token in lower for token in ("certificate_verify_failed", "certificate verify failed", "could not verify", "tls certificate chain")):
            category = "sharped_tls_certificate"
            title = "SharpED secure connection failed"
            summary = "Phase Studio reached sharped.fzu.cz, but could not verify the server's TLS certificate chain."
            guidance = (
                "Check Windows updates and system date/time. If the problem persists, Phase Studio may not "
                "be using the Windows trusted certificate store."
            )
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
            summary = "Phase Studio could not retrieve or save the SharpED map."
            guidance = "Check the server connection and working-folder permissions, then retry the operation."
        elif any(token in lower for token in ("name or service", "getaddrinfo", "nodename nor servname", "hostname resolution")):
            category = "sharped_dns"
            title = "SharpED server name could not be resolved"
            summary = "Windows could not resolve the SharpED server name."
            guidance = "Check the network connection and DNS configuration, then try Refresh models."
        elif any(token in lower for token in ("http error 500", "http error 501", "http error 502", "http error 503", "http error 504", "http error 505")):
            category = "sharped_server"
            title = "SharpED server error"
            summary = "The SharpED service returned a server-side error."
            guidance = "Try again later or check the SharpED service status."
        elif any(token in lower for token in ("request failed", "unreachable", "urlerror", "tls error", "connection refused", "connection reset")):
            category = "sharped_network"
            title = "SharpED server unavailable"
            summary = "Phase Studio could not connect to the configured SharpED server."
            guidance = (
                "Check your internet connection and try again. "
                "If the problem persists, the SharpED service may be temporarily unavailable."
            )
        else:
            category = "sharped_server"
            title = "SharpED processing failed"
            summary = "The SharpED server could not complete the submitted job."
            guidance = "Review the final server detail below, then retry or choose another model if appropriate."
    elif resolved_subsystem != "EDMA" and "superflip" in lower:
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
    elif resolved_subsystem == "EDMA" or "edma" in lower:
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
        title = "Jana2020 handoff could not be loaded"
        summary = "The supplied Jana2020 .inflip file is missing, unreadable, or incomplete."
        guidance = "Select a valid Jana2020 .inflip file containing the required crystallographic input."
    elif "jana2020" in lower or "hand-off" in lower or "handoff" in lower:
        resolved_subsystem = "Jana2020"
        category = "jana_handoff"
        title = "Jana2020 handoff failed"
        summary = "Phase Studio could not prepare or transfer the selected result to Jana2020."
        guidance = "Check that the selected cycle, map, and original Jana2020 input are still available."
    elif "hkl" in lower or "reflection" in lower or resolved_subsystem == "HKL":
        resolved_subsystem = "HKL"
        if any(token in lower for token in ("not found", "does not exist", "select an external")):
            category = "hkl_missing"
            title = "HKL file not found"
            summary = "Phase Studio could not read the selected reflection file."
            guidance = "Select an existing HKL file or a Jana2020 .inflip file containing reflections."
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
        guidance = "The workflow can continue; review the structure file and technical details in the Execution Log."
    elif "metadata" in lower:
        resolved_subsystem = "Crystal metadata"
        category = "metadata"
        title = "Crystal metadata unavailable"
        summary = "The selected crystal metadata source is incomplete or unavailable."
        guidance = "Select a readable metadata source or complete the Manual metadata fields."

    # Prefer transport classifications over translated/variable server text.
    if resolved_subsystem == "SharpED":
        classified = {
            "authentication": ("sharped_authentication", "Sign in to SharpED again", "SharpED authentication could not be completed.", "Sign in with Jana2020 or use an access key, then retry the unfinished operation."),
            "authorization": ("sharped_access_denied", "SharpED access unavailable", "SharpED denied this request.", "Check account access with the SharpED administrator; this response alone does not establish a billing problem."),
            "malformed_catalog": ("sharped_catalogue", "Cannot check available models", "The SharpED catalogue response could not be read.", "Check the catalogue again. Its availability is unknown; no model removal is inferred."),
            "tls_certificate": ("sharped_tls_certificate", "Secure connection could not be verified", "The configured SharpED server certificate could not be verified.", "Check the Windows trust store and system date/time. Do not disable certificate verification."),
        }.get(getattr(error, "category", ""))
        if classified:
            category, title, summary, guidance = classified

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
    wavelength_issue = next((issue for issue in unique if "wavelength" in issue.casefold()
                             and "powder overlap" in issue.casefold()), None)
    if wavelength_issue:
        return ErrorReport(
            category="input_validation", subsystem="Input", title="Powder wavelength required",
            summary="Powder overlap repartitioning needs a positive radiation wavelength.",
            guidance="Enter Wavelength (Å) in Map feedback → Powder overlap repartitioning, "
                     "or provide it in the Jana project, incoming .inflip or reference CIF. "
                     "Zero requests automatic detection; no wavelength was found.\n" + bullets,
            technical_details=sanitize_error_details(technical_details or bullets),
            operation="Pre-run validation", severity="error",
        )
    if len(unique) == 1:
        issue = unique[0]
        lowered = issue.casefold()
        if "working edma executable" in lowered:
            return ErrorReport(
                category="edma_missing", subsystem="EDMA", title="EDMA setup required",
                summary="Phase Studio could not find a working EDMA executable.",
                guidance="Select an existing EDMA installation or install EDMA before starting this workflow.",
                technical_details=sanitize_error_details(technical_details or issue),
                operation="Pre-run validation", severity="error",
            )
        if "working superflip executable" in lowered:
            return ErrorReport(
                category="superflip_missing", subsystem="Superflip", title="Superflip setup required",
                summary="Phase Studio could not find a working Superflip executable.",
                guidance="Select an existing Superflip installation or install Superflip before starting this workflow.",
                technical_details=sanitize_error_details(technical_details or issue),
                operation="Pre-run validation", severity="error",
            )
        if "sharped api token" in lowered:
            return ErrorReport(
                category="sharped_authentication", subsystem="SharpED", title="Connect to SharpED",
                summary="A SharpED access key is required for the selected workflow.",
                guidance="Connect using your existing Jana2020 account before starting this workflow.",
                technical_details=sanitize_error_details(technical_details or issue),
                operation="Pre-run validation", severity="error",
            )
    return ErrorReport(
        category="input_validation",
        subsystem="Input",
        title="Cannot start workflow",
        summary="Please fix the following before starting:\n" + bullets,
        guidance="Open the relevant configuration page, correct the listed items, and start the workflow again.",
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
    details.setMinimumHeight(160)
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
        target_height = min(610, dialog.sizeHint().height()) if expanded else max(250, dialog.minimumSizeHint().height())
        dialog.resize(max(520, min(700, dialog.width())), target_height)

    details_button.clicked.connect(toggle_details)
    copy_button.clicked.connect(lambda: QApplication.clipboard().setText(report.diagnostic_block()))

    for action in actions:
        button = QPushButton(action.label)
        button.setObjectName("errorPrimaryAction" if action.primary else "errorAction")
        button.setMinimumHeight(30)

        def choose(_checked: bool = False, selected_action: ErrorAction = action) -> None:
            selected["label"] = selected_action.label
            dialog.accept()

        button.clicked.connect(choose)
        button_row.addWidget(button)

    close_button = QPushButton("Close")
    close_button.setObjectName("errorCloseButton")
    for button in (details_button, copy_button, close_button):
        button.setMinimumHeight(30)
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
                try:
                    action.callback()
                except Exception as exc:
                    show_phase_studio_error(parent, build_error_report(
                        exc, subsystem=report.subsystem, operation=f"Recovery: {action.label}",
                    ))
                break
    return chosen
