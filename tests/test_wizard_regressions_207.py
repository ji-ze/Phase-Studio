"""Real Qt dialog ownership, launch, navigation and simple-threshold contract."""
import hashlib
import os
from pathlib import Path
import time
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication,QDialog,QDoubleSpinBox
from phase_studio import app as a, jana_superflip as j

_application=None

@pytest.fixture
def wizard(tmp_path,monkeypatch):
    global _application
    qt=QApplication.instance() or QApplication([])
    _application=qt
    original=j._qt_imports
    monkeypatch.setattr(j,'_qt_imports',lambda:original()|{'QSettings':lambda org,name:QSettings(str(tmp_path/(name+'.ini')),QSettings.IniFormat)})
    monkeypatch.setattr(a.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models',lambda *_:None)
    source=tmp_path/'original_Superflip.inflip'
    source.write_text('title controlled\ncell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\n'
        'dataformat intensity fwhm\nfbegin\n1 0 0 12 .1\n0 1 0 15 .2\nendf\n',encoding='utf8')
    w=j._JanaWorkflowWizard([],source);w._ensure_models_loaded=lambda **kwargs:None
    with patch.object(QDialog,'exec',return_value=QDialog.Rejected):w.run()
    w.dialog.setWindowModality(Qt.ApplicationModal);w.dialog.show()
    for _ in range(20):qt.processEvents()
    yield w
    diagnostic=getattr(w,'_diagnostic_dialog',None)
    if diagnostic is not None:diagnostic.close()
    w.dialog.close();qt.processEvents()
    backing=w.backing_window_holder.get('win')
    if backing:backing.timer.stop();backing.close()
    from PySide6.QtCore import QCoreApplication,QEvent
    from PySide6.QtTest import QTest
    QTest.qWait(360)
    w.dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    qt.processEvents()


def wait_for(predicate,seconds=5):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:
        QApplication.processEvents();time.sleep(.005)
    assert predicate()


@pytest.mark.parametrize('kind',['view','analyze'])
def test_wizard_buttons_open_real_owned_dialogs_and_reopen(wizard,kind):
    source=Path(wizard.inflip_path);before=source.read_bytes()
    assert wizard.validate_hkl_button.isEnabled() and wizard.analyze_completeness_button.isEnabled()
    button=wizard.validate_hkl_button if kind=='view' else wizard.analyze_completeness_button
    spy=QSignalSpy(wizard.diagnostic_loader.completed)
    for count in [1,2]:
        button.click()
        wait_for(lambda:getattr(wizard,'_diagnostic_dialog',None) is not None)
        dialog=wizard._diagnostic_dialog
        assert spy.count()==count and dialog.isVisible()
        assert dialog.parentWidget() is wizard.dialog
        assert dialog.windowModality()==Qt.WindowModal
        assert QApplication.activeModalWidget() is dialog
        request=dialog._phase_studio_hkl_request
        assert Path(request.jana_text)==source
        assert source.read_bytes()==before
        assert wizard.backing_window_holder['win'] is None
        dialog.close();QApplication.processEvents()
        assert wizard._diagnostic_dialog is None


def test_simple_wizard_ignores_stale_global_and_legacy_significance(wizard):
    wizard.shared_settings.setValue('inputs/i_over_sigma_min',2)
    wizard.settings.setValue('observed_filter_threshold',2)
    assert wizard._observed_filter_threshold()==0
    assert not hasattr(wizard,'observed_threshold')
    assert not [w for w in wizard.dialog.findChildren(QDoubleSpinBox) if w.accessibleName()=='Reflection significance threshold']
    assert wizard._build_options('recycle').observed_filter_threshold==0
    assert wizard._build_options('edit').observed_filter_threshold is None
    assert wizard._scientific_input_issue() is None


@pytest.mark.parametrize('cycles',[1,2,5])
def test_next_signal_advances_with_missing_credentials_and_preserves_state(wizard,cycles):
    wizard.superflip_sharped_tile._trigger()
    wizard.cycles.setValue(cycles);wizard.api_token.clear()
    snapshot=(wizard.model.currentText(),wizard.reference_file.text(),wizard.model_file.text(),wizard.inflip_path)
    assert 'Map feedback' in wizard.primary_button.text()
    wizard.primary_button.click()
    assert wizard.stack.currentWidget() is wizard.page3
    assert 'MAP FEEDBACK' in wizard.context_title_label.text()
    assert wizard.primary_button.text()=='Run phasing'
    assert snapshot==(wizard.model.currentText(),wizard.reference_file.text(),wizard.model_file.text(),wizard.inflip_path)
    assert wizard.cycles.value()==cycles
    wizard.back_button.click()
    assert wizard.stack.currentWidget() is wizard.page2
    wizard.primary_button.click()
    assert wizard.stack.currentWidget() is wizard.page3


def test_invalid_then_corrected_input_recovers_real_buttons(wizard):
    source=Path(wizard.inflip_path);good=source.read_bytes()
    source.write_text('not crystallographic input',encoding='utf8')
    wizard._refresh_input_summary_and_refit()
    assert wizard.input_readiness=='Invalid'
    assert not wizard.validate_hkl_button.isEnabled() and not wizard.analyze_completeness_button.isEnabled()
    source.write_bytes(good);wizard._refresh_input_summary_and_refit()
    assert wizard.validate_hkl_button.isEnabled() and wizard.analyze_completeness_button.isEnabled()
    wizard.validate_hkl_button.click()
    wait_for(lambda:getattr(wizard,'_diagnostic_dialog',None) is not None)


def test_async_initial_failure_can_retry_without_enabled_noop(wizard,monkeypatch):
    source=Path(wizard.inflip_path)
    source.write_bytes(source.read_bytes()+b'\n# controlled padding\n'*60000)
    assert source.stat().st_size>1_000_000
    original=a.build_hkl_load_result
    def unavailable(_request):raise OSError('controlled first request failed')
    monkeypatch.setattr(a,'build_hkl_load_result',unavailable)
    wizard._refresh_input_summary_and_refit()
    assert wizard.input_readiness=='Loading'
    assert not wizard.validate_hkl_button.isEnabled()
    wait_for(lambda:wizard.input_readiness=='Invalid',seconds=10)
    assert not wizard.validate_hkl_button.isEnabled()
    monkeypatch.setattr(a,'build_hkl_load_result',original)
    wizard._refresh_input_summary_and_refit()
    wait_for(lambda:wizard.input_readiness in ('Validated','Warning'),seconds=10)
    assert wizard.validate_hkl_button.isEnabled()
    wizard.validate_hkl_button.click()
    wait_for(lambda:getattr(wizard,'_diagnostic_dialog',None) is not None,seconds=10)


def test_closing_wizard_cancels_pending_diagnostic_delivery(wizard,monkeypatch):
    import threading
    gate=threading.Event();original=a.build_hkl_load_result
    def delayed(request):gate.wait(2);return original(request)
    monkeypatch.setattr(a,'build_hkl_load_result',delayed)
    wizard.validate_hkl_button.click();wizard.dialog.reject();gate.set()
    deadline=time.monotonic()+2
    while wizard.diagnostic_loader.worker.is_alive() and time.monotonic()<deadline:
        QApplication.processEvents();time.sleep(.005)
    QApplication.processEvents()
    assert getattr(wizard,'_diagnostic_dialog',None) is None
