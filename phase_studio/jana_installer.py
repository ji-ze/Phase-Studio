"""Dedicated Jana2020 integration manager; never imports the scientific GUI."""
from __future__ import annotations
import html
import sys
from pathlib import Path
from typing import Dict, Optional
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QScrollArea, QFrame, QGroupBox, QLineEdit, QPushButton, QLabel, QTextEdit,
    QFileDialog, QMessageBox)
from phase_studio.version import VERSION
from phase_studio.ui_style import apply_phase_studio_style
from phase_studio.ui_branding import (create_phase_studio_brand_header,
    create_phase_studio_context_banner, apply_safe_dialog_geometry, apply_phase_studio_app_icon)


def create_integration_dialog(parent=None, configured_paths=()):
    from phase_studio import jana_integration as ji

    dialog = QDialog(parent)
    dialog.setWindowTitle(f"Phase Studio {VERSION} - Jana2020 Integration")
    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addWidget(create_phase_studio_brand_header())
    outer.addWidget(create_phase_studio_context_banner(
        "JANA2020 INTEGRATION",
        "Install the Phase Studio workflow launcher into Jana2020",
    ))

    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QFrame.NoFrame)
    content = QWidget()
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(14, 10, 14, 10)
    content_layout.setSpacing(10)
    scroll_area.setWidget(content)
    outer.addWidget(scroll_area, 1)

    path_group = QGroupBox("Jana2020 Installation")
    path_group_layout = QVBoxLayout(path_group)
    path_row = QHBoxLayout()
    path_edit = QLineEdit()
    path_edit.setPlaceholderText(r"C:\Jana2020")
    path_edit.setReadOnly(True)
    browse_btn = QPushButton("Browse…")
    path_row.addWidget(path_edit, 1)
    path_row.addWidget(browse_btn)
    path_group_layout.addLayout(path_row)
    path_hint = QLabel("Select the Jana2020 root folder; Phase Studio looks for its SUPERFLIP subfolder.")
    path_hint.setWordWrap(True)
    path_hint.setStyleSheet("color: #52658b;")
    path_group_layout.addWidget(path_hint)
    content_layout.addWidget(path_group)

    status_group = QGroupBox("Detection Status")
    status_layout = QVBoxLayout(status_group)
    content_layout.addWidget(status_group)

    state_label = QLabel("")
    state_label.setObjectName("settingsCallout")
    state_label.setTextFormat(Qt.RichText)
    state_label.setWordWrap(True)
    content_layout.addWidget(state_label)

    explain_label = QLabel("")
    explain_label.setWordWrap(True)
    explain_label.setTextFormat(Qt.RichText)
    content_layout.addWidget(explain_label)

    signature_label = QLabel("")
    signature_label.setWordWrap(True)
    signature_label.setTextFormat(Qt.RichText)
    signature_label.setStyleSheet("color: #52658b;")
    content_layout.addWidget(signature_label)

    result_label = QLabel("")
    result_label.setWordWrap(True)
    result_label.setVisible(False)
    content_layout.addWidget(result_label)

    log_view = QTextEdit()
    log_view.setReadOnly(True)
    log_view.setVisible(False)
    log_view.setMaximumHeight(140)
    content_layout.addWidget(log_view)
    content_layout.addStretch(1)

    footer = QWidget()
    footer.setObjectName("wizardFooter")
    footer_layout = QHBoxLayout(footer)
    footer_layout.setContentsMargins(14, 8, 14, 12)
    close_btn = QPushButton("Close")
    remove_btn = QPushButton("Remove integration")
    primary_btn = QPushButton("Install integration")
    primary_btn.setObjectName("primaryButton")
    # Disabled from construction, before the first refresh() has run --
    # never rely on Qt's default-enabled state for a button whose real
    # state depends on detecting a payload/writable directory first.
    remove_btn.setEnabled(False)
    primary_btn.setEnabled(False)
    footer_layout.addWidget(close_btn)
    footer_layout.addStretch(1)
    footer_layout.addWidget(remove_btn)
    footer_layout.addWidget(primary_btn)
    outer.addWidget(footer)

    state: Dict[str, object] = {"jana_root": None, "superflip_dir": None, "report": None, "install_state": ji.IntegrationState.NOT_INSTALLED}

    def clear_status_layout() -> None:
        while status_layout.count():
            child = status_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def status_row(ok: bool, text: str) -> QLabel:
        mark = "✓" if ok else "✗"
        color = "#2264b8" if ok else "#b42318"
        label = QLabel(f"<span style='color:{color};font-weight:600;'>{mark}</span>&nbsp;&nbsp;{html.escape(text)}")
        label.setTextFormat(Qt.RichText)
        return label

    def refresh(jana_root: Optional[Path]) -> None:
        state["jana_root"] = jana_root
        path_edit.setText(str(jana_root) if jana_root is not None else "")
        superflip_dir = ji.superflip_dir_for_root(jana_root) if jana_root is not None else None
        state["superflip_dir"] = superflip_dir
        report = ji.inspect_jana_superflip_dir(superflip_dir) if superflip_dir is not None else None
        state["report"] = report
        install_state = ji.classify_install_state(report, ji.bundled_integration_version()) if report is not None else ji.IntegrationState.NOT_INSTALLED
        state["install_state"] = install_state

        clear_status_layout()
        if report is None:
            status_layout.addWidget(status_row(False, "No Jana2020 installation selected."))
        else:
            status_layout.addWidget(status_row(report.exists, "SUPERFLIP directory detected"))
            status_layout.addWidget(status_row(report.has_original_exe or (report.has_superflip_exe and not report.has_marker), "Original Superflip detected"))
            status_layout.addWidget(status_row(report.has_edma_exe, "EDMA detected"))
            if not report.is_writable and report.exists:
                status_layout.addWidget(status_row(False, "Directory is not writable with the current Windows permissions"))

        state_text = {
            ji.IntegrationState.NOT_INSTALLED: "Not installed",
            ji.IntegrationState.INSTALLED_CURRENT: f"Installed · version {ji.bundled_integration_version()}",
            ji.IntegrationState.UPDATE_AVAILABLE: f"Update available · installed {report.marker.version if report and report.marker else '?'}, bundled {ji.bundled_integration_version()}",
            ji.IntegrationState.REPAIR_REQUIRED: "Repair required",
            ji.IntegrationState.CONFLICT: "Conflict detected",
        }.get(install_state, "Not installed")
        state_label.setText(f"<b>Status:</b> {html.escape(state_text)}")

        if install_state == ji.IntegrationState.CONFLICT:
            explain_label.setText(
                "<b>Existing Superflip backup detected.</b> Phase Studio did not modify this installation "
                "because its ownership could not be verified. Nothing was changed."
            )
        elif install_state == ji.IntegrationState.NOT_INSTALLED:
            explain_label.setText(
                "Phase Studio will:<br>"
                "&bull; preserve the existing Superflip executable as <code>superflip_original.exe</code><br>"
                "&bull; install the Phase Studio Jana2020 launcher as <code>superflip.exe</code><br>"
                "&bull; install its required runtime files<br>"
                "&bull; leave EDMA and all Jana2020 crystallographic data unchanged"
            )
        elif install_state == ji.IntegrationState.UPDATE_AVAILABLE:
            explain_label.setText("A newer Phase Studio Jana2020 launcher is available. Updating preserves the original Superflip executable and replaces only Phase-Studio-owned files.")
        elif install_state == ji.IntegrationState.REPAIR_REQUIRED:
            explain_label.setText("The Phase Studio integration is incomplete (a required file is missing). Repair replaces only Phase-Studio-owned files; the original Superflip executable is preserved.")
        else:
            explain_label.setText("The installed Phase Studio Jana2020 launcher is up to date.")

        payload_dir = ji.resolve_bundled_jana_payload_dir()
        if payload_dir is None:
            signature_label.setText(
                "<b>Integration package: Not available</b><br>"
                "The Jana2020 integration package is not available in this Phase Studio build."
            )
        else:
            sig = ji.authenticode_signature_status(payload_dir / ji.WRAPPER_EXE_NAME)
            sig_text = {"signed": "Signed", "unsigned": "Unsigned"}.get(sig, "Unknown")
            signature_label.setText(f"<b>Integration package: Ready</b><br>Wrapper signature: {sig_text}")

        can_write = report is not None and report.exists and report.is_writable
        primary_btn.setText({
            ji.IntegrationState.UPDATE_AVAILABLE: "Update integration",
            ji.IntegrationState.REPAIR_REQUIRED: "Repair integration",
            ji.IntegrationState.INSTALLED_CURRENT: "Repair integration",
        }.get(install_state, "Install integration"))
        primary_btn.setEnabled(can_write and install_state != ji.IntegrationState.CONFLICT and payload_dir is not None)

        # Remove is only ever safe when a verified Phase Studio marker
        # proves ownership of the installed integration AND a valid
        # (non-empty) original Superflip backup still exists to restore
        # -- not merely "some state other than not-installed/conflict",
        # since REPAIR_REQUIRED can itself mean the backup went missing.
        owns_installation = (report is not None and report.has_marker and report.marker is not None
                             and install_state != ji.IntegrationState.CONFLICT)
        original_backup_path = report.directory / ji.ORIGINAL_EXE_NAME if report is not None else None
        has_valid_backup = False
        if owns_installation and original_backup_path is not None:
            try:
                has_valid_backup = original_backup_path.stat().st_size > 0
            except OSError:
                has_valid_backup = False
        remove_btn.setEnabled(can_write and owns_installation and has_valid_backup)
        apply_safe_dialog_geometry(dialog, 640, 640)

    def browse_clicked() -> None:
        start_dir = str(state["jana_root"]) if state.get("jana_root") else r"C:\Jana2020"
        picked = QFileDialog.getExistingDirectory(dialog, "Select the Jana2020 installation folder", start_dir)
        if picked:
            refresh(Path(picked))

    def show_result(result: object, success_detail: str = "") -> None:
        result_label.setVisible(True)
        log_view.setVisible(bool(result.log))
        log_view.setPlainText("\n".join(result.log))
        if result.success:
            result_label.setStyleSheet("color: #2264b8;")
            text = f"<b>{html.escape(result.message)}</b>"
            if success_detail:
                text += f"<br>{success_detail}"
            result_label.setText(text)
        else:
            result_label.setStyleSheet("color: #b42318;")
            result_label.setText(f"<b>{html.escape(result.message)}</b>")

    def install_clicked() -> None:
        superflip_dir = state.get("superflip_dir")
        if not superflip_dir:
            return
        # A failed (or unexpectedly raised) attempt must never leave the
        # dialog's buttons out of sync with the real on-disk state --
        # refresh() always runs in `finally`, whatever happened above.
        try:
            payload_dir = ji.resolve_bundled_jana_payload_dir()
            if payload_dir is None:
                show_result(ji.OperationResult(False, "error", "Bundled Jana2020 integration payload was not found in this Phase Studio installation."))
                return
            result = ji.install_or_update_integration(superflip_dir, payload_dir, bundled_version=ji.bundled_integration_version())
            success_detail = ""
            if result.success:
                success_detail = (
                    f"Jana2020:<br>{html.escape(str(state['jana_root']))}<br><br>"
                    f"Original Superflip:<br>{html.escape(str(Path(superflip_dir) / ji.ORIGINAL_EXE_NAME))}<br><br>"
                    f"Phase Studio launcher:<br>{html.escape(str(Path(superflip_dir) / ji.WRAPPER_EXE_NAME))}"
                )
            show_result(result, success_detail)
        except Exception as exc:
            show_result(ji.OperationResult(False, "error", str(exc)))
        finally:
            refresh(state["jana_root"])

    def remove_clicked() -> None:
        superflip_dir = state.get("superflip_dir")
        if not superflip_dir:
            return
        confirmation = QMessageBox.question(
            dialog,
            "Remove Jana2020 Integration",
            "Restore the original Superflip executable and remove the Phase Studio launcher?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return
        try:
            result = ji.remove_integration(superflip_dir)
            show_result(result)
        except Exception as exc:
            show_result(ji.OperationResult(False, "error", str(exc)))
        finally:
            refresh(state["jana_root"])

    browse_btn.clicked.connect(browse_clicked)
    primary_btn.clicked.connect(install_clicked)
    remove_btn.clicked.connect(remove_clicked)
    close_btn.clicked.connect(dialog.reject)

    refresh(ji.detect_jana_root(configured_paths))
    apply_safe_dialog_geometry(dialog, 640, 640)
    dialog.primary_button = primary_btn
    dialog.remove_button = remove_btn
    dialog.refresh_status = refresh
    dialog.integration_state = state
    return dialog



def main():
    if "--version" in sys.argv:
        print(VERSION)
        return 0
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Phase Studio Jana2020 Installer")
    app.setApplicationVersion(VERSION)
    apply_phase_studio_style(app)
    apply_phase_studio_app_icon(app)
    settings = QSettings("PhaseStudio", "PhaseStudio")
    paths = [Path(value) for key in ("superflip_exe", "edma_exe")
             if (value := str(settings.value(f"inputs/{key}", ""))).strip()]
    dialog = create_integration_dialog(configured_paths=paths)
    dialog.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
