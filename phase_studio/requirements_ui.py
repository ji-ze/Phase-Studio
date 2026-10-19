"""Shared Qt remediation UI for the pure checks in :mod:`requirements`."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QMessageBox, QWidget,
)

from phase_studio import requirements as reqs


def check_requirements_responsively(check: Callable[[], reqs.PreflightResult], parent=None):
    """Run a bounded read-only probe off the GUI thread; cancellation discards it.

    The worker owns only its local result queue, never a widget or workflow.
    A cancelled request cannot launch work or overwrite a later request.
    """
    import queue
    import threading
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import QDialog, QProgressDialog

    result_queue = queue.Queue()
    dialog = QProgressDialog("Checking input, local tools and SharpED catalogue…", "Cancel", 0, 0, parent)
    dialog.setWindowTitle("SharpED Autosolve — Checking requirements")
    dialog.setWindowModality(Qt.ApplicationModal)
    dialog.setAutoClose(False)
    outcome = []

    def probe():
        try:
            result_queue.put((True, check()))
        except Exception as exc:
            result_queue.put((False, exc))

    def poll():
        try:
            item = result_queue.get_nowait()
        except queue.Empty:
            return
        outcome.append(item)
        dialog.accept()

    timer = QTimer(dialog)
    timer.setInterval(25)
    timer.timeout.connect(poll)
    threading.Thread(target=probe, daemon=True, name="Autosolve-preflight").start()
    timer.start()
    accepted = dialog.exec() == QDialog.Accepted
    timer.stop()
    dialog.deleteLater()
    if not accepted or not outcome:
        return None
    ok, value = outcome[0]
    if not ok:
        raise value
    return value


def confirm_third_party_download(parent: QWidget, label: str, *, licence_url: Optional[str] = None) -> bool:
    """Require an explicit license decision before downloading a tool."""
    confirmation = QMessageBox(parent)
    confirmation.setWindowTitle(f"Download {label}")
    confirmation.setIcon(QMessageBox.Information)
    confirmation.setText(f"{label} is third-party software supplied under its authors' license.")
    confirmation.setInformativeText(
        "Review and accept the third-party license terms before Phase Studio downloads it."
    )
    view_license = confirmation.addButton("View license information", QMessageBox.ActionRole)
    agree = confirmation.addButton("Agree and download", QMessageBox.AcceptRole)
    cancel = confirmation.addButton("Cancel", QMessageBox.RejectRole)
    confirmation.setDefaultButton(agree)
    confirmation.setEscapeButton(cancel)

    while True:
        confirmation.exec()
        clicked = confirmation.clickedButton()
        if clicked is agree:
            return True
        if clicked is view_license:
            QDesktopServices.openUrl(QUrl(licence_url or (
                reqs.EDMA_LICENSE_URL if label.casefold() == "edma" else reqs.SUPERFLIP_LICENSE_URL
            )))
            continue
        return False


def show_requirement_remediation_dialog(
    parent: Optional[QWidget],
    status: reqs.RequirementStatus,
    configured_value: str = "",
    *,
    download_dir: Optional[Path] = None,
    download_opener: Optional[Callable[..., object]] = None,
    sharped_probe: Optional[Callable] = None,
    sharped_base_url: Optional[str] = None,
) -> Optional[str]:
    """Return a repaired path/key, or None when setup is declined."""
    kind = status.kind
    if kind is reqs.RequirementKind.SHARPED:
        from phase_studio.sharped_access import show_sharped_access_dialog
        from phase_studio.sharped_server_client import DEFAULT_SERVER_URL
        return show_sharped_access_dialog(
            parent, status, configured_value,
            base_url=sharped_base_url or DEFAULT_SERVER_URL, verify=sharped_probe,
        )
    from phase_studio.scientific_tools_setup import show_scientific_tools_setup
    selected = show_scientific_tools_setup(parent, [status], {kind: configured_value})
    return selected.get(kind) if selected is not None else None


def run_remediation_loop(
    parent: Optional[QWidget],
    check: Callable[[], reqs.PreflightResult],
    current_value: Callable[[reqs.RequirementKind], str],
    persist: Callable[[reqs.RequirementKind, str, bool], None],
    on_success: Optional[Callable[[reqs.PreflightResult], None]] = None,
    *,
    download_dir: Optional[Path] = None,
    download_opener: Optional[Callable[..., object]] = None,
    sharped_probe: Optional[Callable] = None,
    sharped_base_url: Optional[str] = None,
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
        local_failures = [s for s in result.failures if s.kind is not reqs.RequirementKind.SHARPED]
        if len(local_failures) > 1:
            from phase_studio.scientific_tools_setup import show_scientific_tools_setup
            local_statuses = [s for s in result.statuses if s.kind is not reqs.RequirementKind.SHARPED]
            selected = show_scientific_tools_setup(
                parent, local_statuses, {s.kind: current_value(s.kind) for s in local_statuses},
            )
            if selected is None:
                return False
            for kind, value in selected.items():
                persist(kind, value, False)
            continue
        value = show_requirement_remediation_dialog(
            parent, status, current_value(status.kind),
            download_dir=download_dir, download_opener=download_opener,
            sharped_probe=sharped_probe, sharped_base_url=sharped_base_url,
        )
        if value is None:
            return False
        persist(status.kind, value, False)
