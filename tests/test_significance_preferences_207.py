"""User-authorized zero default and explicit compatible advanced persistence."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication
from phase_studio import app as a
from phase_studio.significance_preferences import load_explicit,save_explicit,preference_key
from test_wizard_regressions_207 import wait_for

_application=None


@pytest.fixture
def window(tmp_path,monkeypatch):
    global _application
    from PySide6.QtCore import QCoreApplication,QEvent
    from PySide6.QtTest import QTest
    _application=QApplication.instance() or QApplication([])
    a.apply_phase_studio_style(_application)
    monkeypatch.setenv('PHASE_STUDIO_STARTUP_PROBE','1')
    monkeypatch.setattr(a,'QSettings',lambda *_:QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat))
    for name in ['load_settings','save_settings','refresh_sharped_models']:
        monkeypatch.setattr(a.IterativeSuperflipPipelineQtGUI,name,lambda self:None)
    win=a.IterativeSuperflipPipelineQtGUI();win.timer.stop();win.show();_application.processEvents()
    yield win
    win.close();QTest.qWait(360);win.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);_application.processEvents()


def test_legacy_default_is_not_explicit_consent(tmp_path):
    settings=QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat)
    settings.setValue('inputs/i_over_sigma_min',2)
    assert load_explicit(settings,'standalone','new-project',a.REFLECTION_DATA_MODE_INTENSITY)==(0,'zero default')


def test_project_then_compatible_last_then_zero_precedence(tmp_path):
    settings=QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat);mode=a.REFLECTION_DATA_MODE_INTENSITY
    save_explicit(settings,'standalone','first',mode,3)
    assert load_explicit(settings,'standalone','second',mode)==(3,'last explicit')
    save_explicit(settings,'standalone','second',mode,0)
    save_explicit(settings,'standalone','first',mode,4)
    assert load_explicit(settings,'standalone','second',mode)==(0,'project')
    assert load_explicit(settings,'standalone','new',a.REFLECTION_DATA_MODE_AMPLITUDE_MEASURED_SIGMA)==(0,'zero default')
    assert load_explicit(settings,'jana-full','new',mode)==(0,'zero default')


@pytest.mark.parametrize('mode',[a.REFLECTION_DATA_MODE_INTENSITY_FWHM,a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM,a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA])
def test_width_and_unverified_modes_cannot_store_positive_filter(tmp_path,mode):
    settings=QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat)
    with pytest.raises(ValueError):save_explicit(settings,'standalone','project',mode,2)
    assert load_explicit(settings,'standalone','project',mode)==(0,'unavailable')


def test_scope_hash_is_independent_of_launch_working_directory(tmp_path,monkeypatch):
    sources=('external',str(tmp_path/'input.hkl'),'')
    first=preference_key('standalone',sources)
    elsewhere=tmp_path/'elsewhere';elsewhere.mkdir();monkeypatch.chdir(elsewhere)
    assert preference_key('standalone',sources)==first


def configure_measured(window,tmp_path):
    path=tmp_path/'measured.hkl';path.write_text('1 0 0 12 2\n0 1 0 15 3\n',encoding='utf8')
    for name,value in [('input_source_mode',a.INPUT_MODE_EXTERNAL),('hkl',str(path)),('reflection_data_mode',a.format_reflection_data_mode(a.REFLECTION_DATA_MODE_INTENSITY))]:
        window._set_widget_value_from_string(window.inputs[name],value)
    return path


def test_full_configuration_requires_confirmed_valid_save_and_reset(window,tmp_path):
    source=configure_measured(window,tmp_path);before=source.read_bytes()
    window.settings.setValue('inputs/i_over_sigma_min',2)
    controller=window.significance_preferences;controller.reload()
    assert controller.widget.value()==0
    controller.widget.setValue(2.5)
    profile,project,mode,_=controller.scope()
    assert load_explicit(window.settings,profile,project,mode)[0]==0
    spy=QSignalSpy(controller.loader.completed)
    window.significance_save_button.click()
    wait_for(lambda:spy.count()==1)
    assert load_explicit(window.settings,profile,project,mode)==(2.5,'project')
    controller.reload();wait_for(lambda:controller.widget.value()==2.5)
    window.significance_reset_button.click()
    assert controller.widget.value()==0
    assert load_explicit(window.settings,profile,project,mode)==(0,'project')
    assert source.read_bytes()==before


def test_invalid_explicit_edit_is_not_saved_or_silently_replaced(window,tmp_path,monkeypatch):
    source=configure_measured(window,tmp_path);source.write_text('1 0 0 12 ?\n',encoding='utf8')
    controller=window.significance_preferences;controller.reload();controller.widget.setValue(2)
    reports=[];monkeypatch.setattr(window,'_show_error_report',reports.append)
    window.significance_save_button.click();wait_for(lambda:bool(reports))
    profile,project,mode,_=controller.scope()
    assert controller.widget.value()==2
    assert load_explicit(window.settings,profile,project,mode)[0]==0
    assert reports[0].category=='input_validation'


def test_full_override_diagnostics_use_exact_external_columns(window,tmp_path):
    source=tmp_path/'original.inflip';source.write_text('cell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\ndataformat intensity fwhm\nfbegin\n1 0 0 999 .3\nendf\n',encoding='utf8')
    hkl=tmp_path/'override.hkl';hkl.write_text('1 0 0 12 2\n0 1 0 15 3\n',encoding='utf8')
    before=(source.read_bytes(),hkl.read_bytes())
    for mode in [a.REFLECTION_DATA_MODE_AMPLITUDE_MEASURED_SIGMA,a.REFLECTION_DATA_MODE_INTENSITY_FWHM,a.REFLECTION_DATA_MODE_INTENSITY]:
        for name,value in [('input_source_mode',a.INPUT_MODE_INFLIP_OVERRIDES),('jana_inflip',str(source)),('hkl',str(hkl)),('metadata_source',a.METADATA_SOURCE_INFLIP),('reflection_data_mode',a.format_reflection_data_mode(mode))]:
            window._set_widget_value_from_string(window.inputs[name],value)
        request=window._collect_hkl_analysis_request();result=a.build_hkl_load_result(request)
        assert Path(request.hkl_text)==hkl and result.data_mode==mode
        assert [r.value for r in result.reflections]==[12,15]
        assert (source.read_bytes(),hkl.read_bytes())==before
