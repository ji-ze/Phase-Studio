"""Offline regressions: no inference, scientific processes or real credentials."""
import os
import threading
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QProgressDialog

from phase_studio import autosolve_review as policy
from phase_studio.error_reporting import ErrorAction, ErrorReport, build_error_report, show_phase_studio_error, sanitize_error_details
from phase_studio.requirements_ui import check_requirements_responsively


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def test_universal_only_policy():
    assert policy.REQUIRED_SHARPED_MODELS == ("UNIVERSAL",)
    assert policy.PHASE_SEARCH_MODEL == policy.PREDICTION_MODEL == "UNIVERSAL"
    assert policy.missing_required_models(["UNIVERSAL"]) == []
    assert policy.missing_required_models(["default", "universal", "koala phase boost 2"]) == ["UNIVERSAL"]


def test_preflight_worker_is_responsive_and_result_owned(app):
    gui_thread = threading.get_ident()
    ticks = []
    ready = threading.Event()
    QTimer.singleShot(20, lambda: (ticks.append(True), ready.set()))
    def check():
        assert threading.get_ident() != gui_thread
        assert ready.wait(2)
        return "live-result"
    assert check_requirements_responsively(check) == "live-result"
    assert ticks


def test_cancelled_preflight_drops_late_result(app):
    finish = threading.Event()
    done = threading.Event()
    def check():
        finish.wait(2)
        done.set()
        return "stale"
    def cancel():
        for widget in app.topLevelWidgets():
            if isinstance(widget, QProgressDialog):
                widget.reject()
    QTimer.singleShot(20, cancel)
    assert check_requirements_responsively(check) is None
    finish.set()
    assert done.wait(2)
    assert check_requirements_responsively(lambda: "new") == "new"


def test_real_error_action_click_runs_after_modal_closes(app):
    executed = []
    report = ErrorReport("sharped_model_missing", "SharpED", "Model unavailable", "Missing UNIVERSAL", "Try again", "No fallback")
    def action():
        assert not any(isinstance(w, QDialog) and w.isVisible() for w in app.topLevelWidgets())
        executed.append(True)
    def click():
        dialog = app.activeModalWidget()
        assert dialog is not None
        dialog.findChild(QPushButton, "errorPrimaryAction").click()
    QTimer.singleShot(20, click)
    assert show_phase_studio_error(None, report, [ErrorAction("Try again", action, True)]) == "Try again"
    assert executed == [True]


def test_forbidden_is_distinct_from_expired_authentication():
    denied = build_error_report("SharpED HTTP error 403", subsystem="SharpED")
    expired = build_error_report("SharpED HTTP error 401", subsystem="SharpED")
    assert denied.category == "sharped_access_denied"
    assert expired.category == "sharped_authentication"


def test_duplicate_start_is_ignored():
    from phase_studio.app import IterativeSuperflipPipelineQtGUI
    state = SimpleNamespace(_start_request_active=True, _start_run_checked=lambda: pytest.fail("duplicate start"))
    IterativeSuperflipPipelineQtGUI.start_run(state)


@pytest.mark.parametrize("requirements_ok", [False, True])
def test_failed_preflight_never_allocates_or_launches_science(requirements_ok):
    from phase_studio.app import IterativeSuperflipPipelineQtGUI as Backend
    cfg = SimpleNamespace(imported_jana_value="preserve", sharped_model="UNIVERSAL")
    reports = []
    state = SimpleNamespace(
        worker=None, get_config=lambda: cfg,
        _validate_run_config=lambda cfg: ([], ""),
        _ensure_workflow_requirements=lambda cfg: requirements_ok,
        jana_wizard_context=SimpleNamespace(launch_mode="autosolve"),
        _sharped_catalog_models=("SEED (cyclic CF)",),
        _show_error_report=reports.append,
        _begin_fresh_run_context=lambda cfg: pytest.fail("science allocated before preflight"),
    )
    state._autosolve_models_available = lambda: Backend._autosolve_models_available(state)
    Backend._start_run_checked(state)
    assert state.worker is None
    assert vars(cfg) == {"imported_jana_value": "preserve", "sharped_model": "UNIVERSAL"}
    assert bool(reports) == requirements_ok


def test_settings_recovery_opens_hidden_destination(app, monkeypatch):
    from phase_studio.app import IterativeSuperflipPipelineQtGUI
    for method in ("load_settings", "save_settings", "refresh_sharped_models"):
        monkeypatch.setattr(IterativeSuperflipPipelineQtGUI, method, lambda self: None)
    backend = IterativeSuperflipPipelineQtGUI()
    try:
        original = backend.inputs["cycles"].value()
        report = ErrorReport("input_validation", "Input", "Configure SharpED", "SharpED model", "Open settings", "fixture")
        actions = backend._error_actions(report)
        QTimer.singleShot(20, lambda: app.activeModalWidget().findChild(QPushButton, "errorPrimaryAction").click())
        show_phase_studio_error(None, report, actions)
        assert backend.isVisible()
        assert backend.category_tabs.currentIndex() == 1
        assert backend.advanced_tabs.tabText(backend.advanced_tabs.currentIndex()) == "Setup"
        assert backend.inputs["cycles"].value() == original
    finally:
        backend.close()
        backend.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("label", ["authorization_code", "code_verifier", "api_key", "access_key"])
def test_recovery_details_redact_oauth_and_manual_secrets(label):
    assert "mock-secret" not in sanitize_error_details(f"{label}=mock-secret")
    assert "mock-secret" not in sanitize_error_details("https://example.invalid/callback?code=mock-secret")
