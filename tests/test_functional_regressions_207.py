"""Functional regressions: scientific readiness must precede native/remote work."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from test_gui_finish_207 import window
from phase_studio import app as a


def _config(tmp_path, mode, threshold, records='1 0 0 12 1\n'):
    hkl=tmp_path/'observed.hkl';hkl.write_text(records,encoding='utf8')
    return SimpleNamespace(i_over_sigma_min=threshold,reflection_data_mode=mode,crystal_metadata=None,
        extra_superflip_keywords='',powder_wavelength=1.541866,powder_separation_factor=.2,
        map_feedback_missing_enabled=False,map_export_format='xplor',input_source_mode=a.INPUT_MODE_EXTERNAL,
        superflip_referencefile=None,jana_inflip=None,hkl=hkl,first_cycle_modelfile=None,
        redistribute_overlaps=False,cycles=3,powder_redistribution_from_cycle=1,run_superflip=True)


@pytest.mark.parametrize('mode,records',[
    (a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,'1 0 0 12 1\n'),
    (a.REFLECTION_DATA_MODE_INTENSITY,'1 0 0 12\n'),
])
def test_missing_or_auxiliary_uncertainty_is_rejected_before_run(tmp_path,mode,records):
    cfg=_config(tmp_path,mode,2,records)
    host=SimpleNamespace(_resolve_configured_data_mode=lambda cfg:mode)
    issues,_=a.IterativeSuperflipPipelineQtGUI._validate_run_config(host,cfg)
    assert any(getattr(issue,'code','')=='significance_unavailable' for issue in issues)
    assert cfg.i_over_sigma_min==2 and cfg.hkl.read_text(encoding='utf8')==records


@pytest.mark.parametrize('cycles',[1,2,5])
def test_feedback_step_is_always_discoverable(window,tmp_path,monkeypatch,cycles):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QDialog,QApplication
    from phase_studio import jana_superflip as js
    original=js._qt_imports
    monkeypatch.setattr(js,'_qt_imports',lambda:original()|{'QSettings':lambda org,name:QSettings(str(tmp_path/(name+'.ini')),QSettings.IniFormat)})
    monkeypatch.setattr(QDialog,'exec',lambda self:QDialog.Rejected)
    wizard=js._JanaWorkflowWizard([],None)
    wizard._ensure_models_loaded=lambda **kwargs:None
    wizard.run();wizard.dialog.show();wizard.superflip_sharped_tile._trigger();wizard.cycles.setValue(cycles)
    for _ in range(10):QApplication.processEvents()
    assert 'Map feedback' in wizard.primary_button.text()
    wizard.primary_button.click()
    assert wizard.stack.currentWidget() is wizard.page3
    assert 'Run phasing'==wizard.primary_button.text()
    wizard.dialog.close()


@pytest.mark.parametrize('sigma',['', '0', '-1', 'nan', 'inf'])
@pytest.mark.parametrize('threshold',[0,2])
def test_invalid_uncertainty_and_zero_threshold_keep_native_policy(tmp_path,sigma,threshold):
    cfg=_config(tmp_path,a.REFLECTION_DATA_MODE_INTENSITY,threshold,f'1 0 0 12 {sigma}\n')
    host=SimpleNamespace(_resolve_configured_data_mode=lambda cfg:cfg.reflection_data_mode)
    issues,_=a.IterativeSuperflipPipelineQtGUI._validate_run_config(host,cfg)
    assert bool(issues)==bool(threshold)
    if issues:assert issues[0].code=='significance_unavailable'
    if threshold==0:
        rows=a.read_hkl(cfg.hkl)
        assert [r.value for r in a.filtered_reflections(rows,cfg.reflection_data_mode,0)]==[12]


@pytest.mark.parametrize('mode,records',[
    (a.REFLECTION_DATA_MODE_INTENSITY,'1 0 0 6 2\n'),
    (a.REFLECTION_DATA_MODE_AMPLITUDE_MEASURED_SIGMA,'1 0 0 6 2\n'),
    (a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA,'1 0 0 6 45 2\n'),
])
def test_measured_uncertainties_keep_direct_ratio_and_native_values(tmp_path,mode,records):
    cfg=_config(tmp_path,mode,3,records)
    host=SimpleNamespace(_resolve_configured_data_mode=lambda cfg:mode)
    assert not a.IterativeSuperflipPipelineQtGUI._validate_run_config(host,cfg)[0]
    cols=a.reflection_columns_for_mode(mode)
    rows=a.read_hkl(cfg.hkl,*cols)
    assert len(a.filtered_reflections(rows,mode,3))==1
    assert a.reflection_amplitude_signal_to_noise(rows[0],mode)==3
    assert a.reflection_signal_to_noise(rows[0],mode)==(1.5 if a.reflection_mode_is_amplitude(mode) else 3)
    assert cfg.hkl.read_text(encoding='utf8')==records


def test_start_rejects_before_requirement_checks_or_run_allocation(window,tmp_path,monkeypatch):
    cfg=_config(tmp_path,a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,2)
    cfg.work_dir=tmp_path/'never-allocated'
    monkeypatch.setattr(window,'get_config',lambda:cfg)
    reports=[]
    monkeypatch.setattr(window,'_show_error_report',reports.append)
    def forbidden(*args,**kwargs):raise AssertionError('Preflight must precede native/remote work and run allocation')
    monkeypatch.setattr(window,'_ensure_workflow_requirements',forbidden)
    monkeypatch.setattr(window,'_begin_fresh_run_context',forbidden)
    window._start_run_checked()
    assert reports[0].title=='Reflection significance filter unavailable'
    assert reports[0].issues[0].setting=='i_over_sigma_min'
    assert cfg.i_over_sigma_min==2 and not cfg.work_dir.exists()


def test_runtime_fallback_retains_trace_and_correct_recovery():
    from phase_studio.reflection_readiness import validate_loaded_significance,ReflectionReadinessError
    from phase_studio.error_reporting import build_error_report
    with pytest.raises(ReflectionReadinessError) as caught:
        validate_loaded_significance(a.REFLECTION_DATA_MODE_INTENSITY,2,[a.Reflection(1,0,0,12,None)])
    report=build_error_report(caught.value,extra_details='controlled traceback evidence')
    assert report.category=='input_validation' and report.issues[0].code=='significance_unavailable'
    assert 'controlled traceback evidence' in report.technical_details


def test_input_loader_delivers_metadata_and_rejects_stale_completion(window):
    import threading,time
    from PySide6.QtWidgets import QApplication
    from phase_studio.input_readiness import InputReadinessLoader
    loader=InputReadinessLoader(window);gate=threading.Event();ready=[];metadata=[]
    loader.completed.connect(ready.append);loader.metadata.connect(metadata.append)
    def old(publish):publish('old metadata');gate.wait(2);return 'old result'
    loader.start('old',old)
    loader.start('new',lambda publish:(publish('new metadata'),'new result')[1])
    deadline=time.monotonic()+2
    while not ready and time.monotonic()<deadline:QApplication.processEvents();time.sleep(.005)
    assert ready==['new result'] and metadata==['new metadata']
    gate.set()
    for _ in range(20):QApplication.processEvents();time.sleep(.002)
    assert ready==['new result']
    assert not loader.start('new',lambda publish:(_ for _ in ()).throw(AssertionError('Unchanged input must reuse its result')))
    loader.cancel()


def test_execution_table_filters_preserve_original_records(window, tmp_path, monkeypatch):
    import copy
    from phase_studio import run_log_viewer as ui
    from phase_studio.run_review import PersistedRunReview
    records = [dict(timestamp='2026-11-10T11:00:00.123456+01:00', session_id='fixture',
                    session_sequence=index, event_type='native_command', cycle=cycle,
                    severity=severity, component=component,
                    payload=dict(message=message, native_command=['superflip', 'original.inflip']))
               for index, (cycle, severity, component, message) in enumerate([
                   (None, 'INFO', 'Application', 'Start'),
                   (3, 'WARNING', 'Superflip', 'Stopped after four completed cycles'),
                   (4, 'SUCCESS', 'EDMA', 'Candidate complete')])]
    original = copy.deepcopy(records)
    review = PersistedRunReview.__new__(PersistedRunReview)
    review.records = records; review.manifest = {}; review.incomplete_records = 0
    review.directory = tmp_path; review.reload = lambda: None
    monkeypatch.setattr(ui, 'PersistedRunReview', lambda directory: review)
    dialog = ui.RunLogViewer(window, tmp_path); dialog.timer.stop(); dialog.refresh()
    assert dialog.table.rowCount() == 3 and dialog.table.item(0, 3).text() == 'Global'
    assert dialog.table.item(0, 0).text() == records[0]['timestamp']
    dialog.kind.setCurrentIndex(dialog.kind.findData('important'))
    assert dialog.table.rowCount() == 2
    dialog.component.setCurrentIndex(dialog.component.findData('Superflip'))
    assert dialog.table.rowCount() == 1
    dialog.search.setText('no matching record')
    assert dialog.table.rowCount() == 0
    dialog.search.clear(); dialog.kind.setCurrentIndex(0); dialog.component.setCurrentIndex(0)
    assert 'session_sequence' in dialog.text.toPlainText() and 'original.inflip' in dialog.text.toPlainText()
    assert records == original
    dialog.close()


def test_large_run_preflight_does_not_parse_on_gui_thread(tmp_path):
    import threading
    cfg = _config(tmp_path, a.REFLECTION_DATA_MODE_INTENSITY, 2)
    cfg.hkl.write_text('1 0 0 12 1\n' * 100001, encoding='utf8')
    queued = []; validation_threads = []
    def validate(configuration):
        validation_threads.append(threading.get_ident())
        return [], ''
    host = SimpleNamespace(worker=None, hkl_task_worker=None, inputs={}, get_config=lambda:cfg,
        _validate_run_config=validate,
        _start_hkl_background_task=lambda label, job, kind:queued.append((job,kind)))
    a.IterativeSuperflipPipelineQtGUI._start_run_checked(host)
    assert not validation_threads and len(queued) == 1
    assert queued[0][1] == 'hkl_run_preflight'
    thread = threading.Thread(target=queued[0][0]); thread.start(); thread.join()
    assert validation_threads and validation_threads[0] != threading.get_ident()


def test_amplitude_input_choices_preserve_legacy_provenance():
    assert a.normalize_reflection_data_mode('h k l · F · σ(F)') == a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA
    assert 'unverified' in a.format_reflection_data_mode(a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA)
    assert 'measured' in a.format_reflection_data_mode(a.REFLECTION_DATA_MODE_AMPLITUDE_MEASURED_SIGMA)
