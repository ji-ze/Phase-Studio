"""Offline real-data acceptance; at most ten actual Qt screenshots in OUT.

Prepare a trusted local pickle once, then render in separate Qt DPR processes.
No server access, inference, or executable build is performed.
"""
import os
import sys
import json
import pickle
import hashlib
import tempfile
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT),str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ['PHASE_STUDIO_STARTUP_PROBE']='1'
from phase_studio import app as a, jana_superflip as js
from phase_studio import hkl_diagnostics_ui as ui
from phase_studio.hkl_diagnostics import cached_analysis, export_shell_csv
OUT = ROOT/'build/acceptance-gui-polish-2.0.5'
OUT.mkdir(parents=True,exist_ok=True)
sha = lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def prepare():
    spec = importlib.util.spec_from_file_location('phase_studio._before_gui_polish',OUT/'before-hkl_diagnostics_ui.py')
    before = importlib.util.module_from_spec(spec);spec.loader.exec_module(before)
    cache = {}
    expected = json.loads((ROOT/'build/hkl-presentation/real-acceptance.json').read_text(encoding='utf8'))
    for name,source in [('ochlor',ROOT/'build/powder-final/wizard-input/ochlor_Superflip.inflip'),('2int3total',Path('C:/Users/honzi/Documents/flipovani-phase-studio/2int3total.inflip'))]:
        source_hash = sha(source)
        request = a.build_hkl_analysis_request_from_inflip(source,work_dir=OUT/'prepared'/name)
        analysis = cached_analysis(request)
        load = a.build_hkl_load_result(request)
        report = ui.presentation_report(analysis)
        old = before.presentation_report(analysis)
        assert report==old
        assert analysis.d_min==expected[name]['d_min'] and analysis.d_full_98==expected[name]['d98']
        assert len(analysis.reflections_raw)==expected[name]['parsed_records'] and source_hash==expected[name]['input_sha256']
        for tag,r in [('before',old),('after',report)]:
            r.export_json(OUT/(name+'-'+tag+'.json'),analysis)
            export_shell_csv(OUT/(name+'-'+tag+'.csv'),r)
        assert (OUT/(name+'-before.json')).read_bytes()==(OUT/(name+'-after.json')).read_bytes()
        assert (OUT/(name+'-before.csv')).read_bytes()==(OUT/(name+'-after.csv')).read_bytes()
        assert before.overlap_bin_rows(analysis,report)==ui.overlap_bin_rows(analysis,report) if dict(report.overlap)['available'] else True
        evidence = dict(source_sha256=source_hash,parsed=len(load.reflections),d_min=analysis.d_min,d98=analysis.d_full_98,
            counts=dict(report.counts),statistics=dict(report.statistics),overlap=dict(report.overlap),
            json_sha256=sha(OUT/(name+'-after.json')),csv_sha256=sha(OUT/(name+'-after.csv')))
        (OUT/(name+'-invariants.json')).write_text(json.dumps(evidence,indent=2),encoding='utf8')
        cache[name]=(load,analysis)
        assert sha(source)==source_hash
        print(name+' scientific baselines and exports identical',flush=True)
    (OUT/'prepared-data.pickle').write_bytes(pickle.dumps(cache))


def capture():
    import time
    from PySide6.QtCore import QSettings,QRect,QPoint,Qt
    from PySide6.QtGui import QScreen
    from PySide6.QtWidgets import QApplication,QDialog,QPushButton,QToolTip
    from PySide6.QtTest import QTest
    from phase_studio.credentials import CredentialStore
    factor = float(os.environ.get('QT_SCALE_FACTOR','1'))
    qt = QApplication([]);a.apply_phase_studio_style(qt)
    cache = pickle.loads((OUT/'prepared-data.pickle').read_bytes())
    evidence={}
    available = QRect(0,0,int(1920/factor),int(1040/factor))
    def settle():
        for _ in range(30):qt.processEvents()
    def snap(name,dialog):
        QToolTip.hideText();settle()
        assert dialog.grab().save(str(OUT/(name+'.png')))
        evidence[name]=dict(geometry=dialog.geometry().getRect(),frame=dialog.frameGeometry().getRect(),dpr=dialog.devicePixelRatioF(),available=available.getRect())
    with tempfile.TemporaryDirectory() as tmp,patch.object(QScreen,'availableGeometry',return_value=available),patch.object(a.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models',lambda self:None):
        base=Path(tmp)
        QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
        win=a.IterativeSuperflipPipelineQtGUI();win.timer.stop()
        if factor in (1,1.25,1.5):
            jana=base/'Jana';(jana/'SUPERFLIP').mkdir(parents=True)
            for name in ('superflip.exe','EDMA.exe'):(jana/'SUPERFLIP'/name).write_bytes(b'UI fixture never executed')
            factory=lambda org,app:QSettings(str(base/(app+'.ini')),QSettings.IniFormat)
            imports=js._qt_imports
            catalog=SimpleNamespace(default_model=js.SHARPED_ITERATIVE_MODEL,models=[js.SHARPED_ONE_CYCLE_MODEL,js.SHARPED_ITERATIVE_MODEL])
            with patch.object(js,'_qt_imports',lambda:imports()|{'QSettings':factory}),patch.object(js,'credential_store',CredentialStore(backend=None)),patch.object(js,'application_dir',lambda:jana),patch.object(QDialog,'exec',lambda self:QDialog.Rejected),patch.object(js.SharpEDServerClient,'get_models',return_value=catalog):
                wizard=js._JanaWorkflowWizard([],ROOT/'build/powder-final/wizard-input/ochlor_Superflip.inflip');wizard.run();wizard.dialog.show();settle()
                assert wizard.data_type_value.text()=='Powder / polycrystalline'
                assert '<i>a</i>' in wizard.cell_value.text()
                assert 'Updates and application information' in wizard.update_menu.toolTip()
                assert wizard.cancel_button.isVisible()
                assert available.contains(QRect(wizard.cancel_button.mapToGlobal(QPoint()),wizard.cancel_button.size()))
                assert wizard.scroll_area.horizontalScrollBar().maximum()==0
                if factor in (1,1.25):
                    assert wizard.scroll_area.verticalScrollBar().maximum()==0
                    snap('01-wizard-collapsed' if factor==1 else '09-wizard-dpi-125',wizard.dialog)
                else:
                    evidence['wizard-layout-dpi-150']=dict(geometry=wizard.dialog.geometry().getRect(),dpr=wizard.dialog.devicePixelRatioF(),cancel_on_screen=True,vertical_scroll=wizard.scroll_area.verticalScrollBar().maximum())
                    wizard.scroll_area.verticalScrollBar().setValue(wizard.scroll_area.verticalScrollBar().maximum());settle()
                    for tile in (wizard.autosolve_tile,wizard.professional_mode_tile):
                        assert wizard.scroll_area.viewport().rect().contains(tile.mapTo(wizard.scroll_area.viewport(),tile.rect().bottomRight()))
                if factor==1:
                    wizard.files_toggle.click();settle()
                    wizard.scroll_area.verticalScrollBar().setValue(wizard.scroll_area.verticalScrollBar().maximum());settle()
                    snap('02-wizard-expanded',wizard.dialog)
                wizard.dialog.close()
                backing = wizard.backing_window_holder.get('win')
                if backing is not None:backing.close()
        if factor==1:
            load,analysis=cache['ochlor']
            validation=win._build_hkl_validation_dialog(load);validation.show();settle();snap('03-validation-powder',validation);validation.close()
            large,_=cache['2int3total']
            validation=win._build_hkl_validation_dialog(large);validation.show();settle()
            target=large.reflections[-1]
            started=time.perf_counter();validation.hkl_search.setText(f'{target.h} {target.k} {target.l}');QTest.qWait(220);settle()
            evidence['large-search']=dict(seconds=time.perf_counter()-started,target=[target.h,target.k,target.l],status=validation.hkl_preview_label.text(),parsed=len(large.reflections))
            assert validation.hkl_table.rowCount()>0
            snap('04-validation-full-dataset-search',validation);validation.close()
        if factor in (1,1.5):
            _,analysis=cache['ochlor']
            view=win._build_hkl_completeness_dialog(analysis);view.show();settle()
            close=next(b for b in view.findChildren(QPushButton) if b.text()=='Close')
            assert available.contains(QRect(close.mapToGlobal(QPoint()),close.size()))
            assert len(view.hkl_figure.axes)==2
            scroll=view.hkl_chart_scroll
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum());settle()
            assert view.hkl_canvas.mapTo(scroll.viewport(),view.hkl_canvas.rect().bottomRight()).y()<=scroll.viewport().height()
            scroll.verticalScrollBar().setValue(0);settle()
            snap('05-completeness-analysis' if factor==1 else '10-completeness-dpi-150',view)
            if factor==1:
                view.hkl_plot_tabs.setCurrentIndex(1);settle();snap('06-completeness-overlap',view)
                view.hkl_content_splitter.setSizes([300,350]);settle();snap('07-completeness-splitter',view)
                view.resize(1000,700);settle();snap('08-completeness-constrained',view)
                assert view.rect().contains(QRect(close.mapTo(view,QPoint()),close.size()))
            view.close()
        win.close()
        for dataset,(_,analysis) in cache.items():
            report=ui.presentation_report(analysis)
            report.export_json(OUT/(dataset+'-after-ui.json'),analysis)
            export_shell_csv(OUT/(dataset+'-after-ui.csv'),report)
            assert (OUT/(dataset+'-after-ui.json')).read_bytes()==(OUT/(dataset+'-before.json')).read_bytes()
            assert (OUT/(dataset+'-after-ui.csv')).read_bytes()==(OUT/(dataset+'-before.csv')).read_bytes()
    (OUT/('geometry-'+str(factor)+'.json')).write_text(json.dumps(evidence,indent=2),encoding='utf8')
    print(json.dumps(evidence),flush=True)


if __name__=='__main__':
    prepare() if '--prepare' in sys.argv else capture()
