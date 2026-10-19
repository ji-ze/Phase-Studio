"""Offline actual Qt remediation capture; mock catalogue/auth, real HKL data."""
import os
import sys
import json
import tempfile
import time
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ['PHASE_STUDIO_STARTUP_PROBE']='1'
os.environ.pop('SHARPED_API_TOKEN',None)
from PySide6.QtCore import QSettings,QRect,QPoint,Qt
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication,QDialog
BEFORE='--before' in sys.argv
if BEFORE:
    import importlib.util
    import phase_studio
    for name in ('hkl_diagnostics_ui','sharped_access','jana_superflip'):
        spec=importlib.util.spec_from_file_location('phase_studio.'+name,ROOT/'build/gui-remediation-205-before'/(name+'.py'))
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        setattr(phase_studio,name,module)
from phase_studio import app as a,jana_superflip as js,hkl_diagnostics_ui as ui
from phase_studio.credentials import CredentialStore
from phase_studio.sharped_access import SharpEDAccessDialog
from phase_studio.hkl_diagnostics import cached_analysis,export_shell_csv
from test_wizard_text_clipping import write_inflip

factor=float(os.environ.get('QT_SCALE_FACTOR','1'))
OUT=ROOT/'build/acceptance-gui-remediation-2.0.5'/('before' if BEFORE else 'after')/('scale-'+str(factor))
OUT.mkdir(parents=True,exist_ok=True)
qt=QApplication([]);a.apply_phase_studio_style(qt)
evidence={}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def settle():
    for _ in range(25):qt.processEvents()
def snap(name,dialog,kind):
    settle()
    assert dialog.grab().save(str(OUT/(name+'.png')))
    evidence[name]=dict(size=dialog.size().toTuple(),dpr=dialog.devicePixelRatioF(),input=kind)

with tempfile.TemporaryDirectory() as tmp,patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,int(1920/factor),int(1040/factor))):
    base=Path(tmp)
    QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
    factory=lambda org,name:QSettings(str(base/(name+'.ini')),QSettings.IniFormat)
    imports=js._qt_imports
    source=write_inflip(base)
    source.write_text(source.read_text().replace('dataformat amplitude','dataformat intensity fwhm'),encoding='utf8')
    source.with_suffix('.m90').write_text('datblock Block1\nlambda 1.541866\nend\n',encoding='utf8')
    jana=base/'Jana';(jana/'SUPERFLIP').mkdir(parents=True)
    for name in ('superflip.exe','EDMA.exe'):(jana/'SUPERFLIP'/name).write_bytes(b'fixture never executed')
    with patch.object(js,'_qt_imports',lambda:imports()|{'QSettings':factory}),patch.object(js,'credential_store',CredentialStore()),patch.object(js,'application_dir',lambda:jana),patch.object(QDialog,'exec',lambda self:QDialog.Rejected),patch.object(js.SharpEDServerClient,'get_models',lambda self:SimpleNamespace(models=[js.SHARPED_ONE_CYCLE_MODEL,js.SHARPED_ITERATIVE_MODEL],default_model=js.SHARPED_ONE_CYCLE_MODEL)):
        w=js._JanaWorkflowWizard([],source);w.run();w.dialog.show();settle()
        kind='Offline synthetic wizard input; mocked public model catalogue; no inference'
        snap('01-initial',w.dialog,kind)
        # The existing optional-file disclosure is exercised by the wizard tests.
        toggle=w.files_toggle
        if toggle:
            toggle.setChecked(True);snap('02-advanced-input',w.dialog,kind);toggle.setChecked(False)
        w.superflip_sharped_tile._trigger();settle()
        deadline=time.monotonic()+4
        while w.model_cache['inflight']:
            qt.processEvents();w.refresh_timer.timeout.emit()
            assert time.monotonic()<deadline
            time.sleep(.005)
        w.cycles.setValue(3);settle()
        snap('03-configuration',w.dialog,kind)
        w.sharped_toggle.setChecked(True);snap('04-advanced-sharped',w.dialog,kind)
        w.sharped_toggle.setChecked(False)
        w._go_to_map_feedback();snap('07-feedback-disabled',w.dialog,kind)
        w.powder_enabled_checkbox.setChecked(True);snap('08-feedback-powder',w.dialog,kind)
        w.dialog.close()
    auth=SharpEDAccessDialog(store=CredentialStore());auth.show();settle()
    snap('05-auth-ready',auth,'Offline authentication UI; no credentials or server request')
    auth._present('waiting');snap('06-auth-waiting',auth,'Simulated browser-waiting presentation; no authentication success')
    auth._present('timeout');snap('06b-auth-timeout',auth,'Simulated timeout; no server request')
    auth.close()
    with patch.object(a.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models',lambda self:None),patch.object(a.IterativeSuperflipPipelineQtGUI,'load_settings',lambda self:None),patch.object(a.IterativeSuperflipPipelineQtGUI,'save_settings',lambda self:None):
        win=a.IterativeSuperflipPipelineQtGUI();win.timer.stop()
        for name,source in {'ochlor':ROOT/'build/powder-final/wizard-input/ochlor_Superflip.inflip','2int3total':Path.home()/'Documents/flipovani-phase-studio/2int3total.inflip'}.items():
            original=sha(source)
            request=a.build_hkl_analysis_request_from_inflip(source,work_dir=ROOT/'build/acceptance-hkl-completeness-2.0.5/prepared'/name)
            load=a.build_hkl_load_result(request);analysis=cached_analysis(request);report=ui.presentation_report(analysis)
            for stage in ('before',):
                report.export_json(OUT/f'{name}-{stage}.json',analysis);export_shell_csv(OUT/f'{name}-{stage}.csv',report)
            kind='Actual local '+name+' data; no phasing or external API'
            start=time.perf_counter();dialog=ui.completeness_dialog(win,analysis);dialog.show();settle()
            timing=time.perf_counter()-start
            if name=='ochlor':
                validation=ui.validation_dialog(win,load);validation.show();snap('09-validation',validation,kind);validation.close()
                snap('10-analysis-default',dialog,kind)
                if not BEFORE:
                    assert dialog.hkl_histogram_range_controls.isHidden()
                    assert dialog.hkl_canvas.height()<=dialog.hkl_chart_scroll.viewport().height()
                    table=dialog.hkl_bins_table
                    visible=sum(0<=table.rowViewportPosition(row) and
                        table.rowViewportPosition(row)+table.rowHeight(row)<=table.viewport().height()
                        for row in range(table.rowCount()))
                    assert visible>=5,visible
                    evidence['default_graph_viewport']=dict(canvas=dialog.hkl_canvas.size().toTuple(),
                        viewport=dialog.hkl_chart_scroll.viewport().size().toTuple(),visible_bin_rows=visible)
                dialog.hkl_histogram_focus.setCurrentIndex(2);snap('11-analysis-custom',dialog,kind)
                dialog.hkl_histogram_reset.click()
                dialog.hkl_histogram_scale.setCurrentIndex(0);dialog.hkl_resolution_axis.setCurrentIndex(1)
                snap('12-analysis-log-d',dialog,kind)
                dialog.hkl_plot_tabs.setCurrentIndex(1);snap('13-peak-overlap',dialog,kind)
            else:
                snap('14-large-hkl',dialog,kind)
            report.export_json(OUT/f'{name}-after.json',analysis);export_shell_csv(OUT/f'{name}-after.csv',report)
            for ext in ('json','csv'):
                assert (OUT/f'{name}-before.{ext}').read_bytes()==(OUT/f'{name}-after.{ext}').read_bytes()
                assert (OUT/f'{name}-after.{ext}').read_bytes()==(ROOT/f'build/acceptance-hkl-completeness-2.0.5/{name}-after.{ext}').read_bytes()
            assert sha(source)==original
            evidence[name]=dict(records=report.count('parsed_records'),d_min=analysis.d_min,d98=analysis.d_full_98,
                construct_and_first_paint_seconds=timing,source_sha256=original,
                json_sha256=sha(OUT/f'{name}-after.json'),csv_sha256=sha(OUT/f'{name}-after.csv'))
            if name=='2int3total':
                validation=ui.validation_dialog(win,load);validation.show();settle()
                from PySide6.QtTest import QTest
                r=load.reflections[-1]
                validation.hkl_search.setText(f'{r.h} {r.k} {r.l}')
                started=time.perf_counter()
                QTest.keyClick(validation.hkl_search,Qt.Key_Return);settle()
                evidence[name]['exact_search_and_paint_seconds']=time.perf_counter()-started
                assert 0<validation.hkl_table.rowCount()<=200
                if not BEFORE:
                    assert validation.isVisible() and validation.hkl_advanced is None
                validation.close()
            dialog.close()
        win.close()
(OUT/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')
print('PASS offline Qt captures, original input hashes and byte-identical real diagnostic exports',factor,flush=True)
