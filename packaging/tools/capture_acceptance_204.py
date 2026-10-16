"""At most ten actual current Qt windows; offline, isolated settings, no jobs."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QT_SCALE_FACTOR','1')
OUT=ROOT/'docs/screenshots/2.0.4/wizard'
OUT.mkdir(parents=True,exist_ok=True)

def main(mode):
    if mode=='selector':
        from test_result_selection_redesign import ResultSelectionRedesignTests
        from phase_studio.ui_style import apply_phase_studio_style
        ResultSelectionRedesignTests.setUpClass()
        fixture=ResultSelectionRedesignTests('test_family_selection_warning_and_authoritative_model_count')
        fixture.setUp()
        apply_phase_studio_style(fixture.qtapp)
        dialog=fixture.dialog
        dialog.resize(1450,900);fixture.events()
        dialog._request_preview_fit();dialog._preview_canvas.draw();fixture.events()
        assert dialog.grab().save(str(OUT/'10_result_selection.png'))
        dialog.close();fixture.tearDown()
        return
    if mode=='execution':
        path=ROOT/'packaging/tools/capture_execution.py'
        code=path.read_text(encoding='utf8').split('capture("01-empty")')[0]
        namespace={'__file__':str(path),'__name__':'_acceptance_fixture'}
        exec(compile(code,str(path),'exec'),namespace)
        namespace['out']=OUT
        namespace['backend'].results=[namespace['result']]
        namespace['stage']('SharpED','controlled UI fixture — no inference')
        namespace['capture']('09_execution',height=900,width=1450)
        namespace['window'].close()
        return
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication,QDialog,QToolTip
    from phase_studio.ui_style import apply_phase_studio_style
    from phase_studio import app as a,jana_superflip as js
    from unittest.mock import patch
    qt=QApplication([]);apply_phase_studio_style(qt)
    with tempfile.TemporaryDirectory() as tmp:
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,tmp)
        def settle():
            for _ in range(25):qt.processEvents()
        def save(widget,name,width,height):
            widget.show();settle();widget.resize(width,height);settle();QToolTip.hideText()
            assert widget.grab().save(str(OUT/(name+'.png')))
        source=Path('C:/Users/honzi/Documents/ochlor/ochlor_Superflip.inflip')
        if mode=='hkl':
            w=a.IterativeSuperflipPipelineQtGUI()
            request=a.build_hkl_analysis_request_from_inflip(source,work_dir=ROOT/'build/powder-final/capture')
            load=a.build_hkl_load_result(request)
            v=w._build_hkl_validation_dialog(load);save(v,'03_hkl_validation',1120,800);v.close()
            from phase_studio.hkl_diagnostics import cached_analysis
            v=w._build_hkl_completeness_dialog(cached_analysis(request))
            save(v,'04_hkl_completeness',1120,900)
            v.hkl_plot_tabs.setCurrentIndex(1);settle()
            v.grab().save(str(OUT/'04_hkl_completeness.png'))  # replace, not an extra capture
            v.close();w.timer.stop();w.close()
        elif mode=='auth':
            from phase_studio.sharped_access import SharpEDAccessDialog
            from phase_studio.credentials import CredentialStore
            # No Windows credential lookup/writes; explicitly empty fixture store.
            class EmptyStore(CredentialStore):
                def get(self,*args,**kwargs):return None
            with patch.object(CredentialStore,'get',return_value=None):
                v=SharpEDAccessDialog(store=EmptyStore())
                save(v,'08_sharped_connection',610,450);v.close()
        else:
            js.application_dir=lambda:Path('C:/Jana2020')
            copied=ROOT/'build/powder-final/wizard-input'/source.name
            copied.parent.mkdir(parents=True,exist_ok=True)
            copied.write_bytes(source.read_bytes())
            copied.with_suffix('.m90').write_bytes(source.with_suffix('.m90').read_bytes())
            source=copied
            with patch.object(QDialog,'exec',lambda self:QDialog.Rejected):
                w=js._JanaWorkflowWizard([],source);w.run()
            w._adjust_dialog_size=lambda:None
            save(w.dialog,'01_main_workflow',950,900)
            w.files_toggle.setChecked(True);save(w.dialog,'02_optional_input',900,950)
            w.files_toggle.setChecked(False)
            w._ensure_models_loaded=lambda **kwargs:None
            w._ensure_workflow_requirements=lambda **kwargs:True
            w.model.clear();w.model.addItems(['PEAK A (model prediction)','SEED (cyclic CF)'])
            w.model_catalog['values']=tuple(w.model.itemText(i) for i in range(w.model.count()))
            w.model_cache['loaded']=True
            w.superflip_sharped_tile._trigger();w.cycles.setValue(3);w.model_policy_error=''
            w.model_status.setText('2 models · controlled offline catalogue')
            save(w.dialog,'05_superflip_sharped_config',900,900)
            w._go_to_map_feedback();w.powder_enabled_checkbox.setChecked(True)
            save(w.dialog,'06_map_feedback_powder',950,950);w.dialog.close()
            single=ROOT/'build/powder-final/single-crystal-fixture.inflip'
            single.write_text('title controlled single crystal fixture\nperform CF\ndimension 3\ncell 10 10 10 90 90 90\nspacegroup P1\ncomposition C2\ndataformat amplitude phase dummy\nfbegin\n1 0 0 10 0 2\n2 0 0 20 0 3\nendf\n')
            with patch.object(QDialog,'exec',lambda self:QDialog.Rejected):
                w=js._JanaWorkflowWizard([],single);w.run()
            w._ensure_models_loaded=lambda **kwargs:None
            w._ensure_workflow_requirements=lambda **kwargs:True
            w.model.clear();w.model.addItem('SEED (cyclic CF)');w.model_cache['loaded']=True
            w.workflow_state['key']=js.WORKFLOW_SUPERFLIP_SHARPED
            w.cycles.setValue(3);w.model_policy_error='';w._go_to_map_feedback()
            w.intensity_enabled_checkbox.setChecked(True)
            save(w.dialog,'07_map_feedback_single_crystal',950,950);w.dialog.close()

if __name__=='__main__':
    if len(sys.argv)>1:main(sys.argv[1])
    else:
        for mode in ('wizard','hkl','auth','execution','selector'):
            subprocess.run([sys.executable,__file__,mode],cwd=ROOT,check=True,timeout=90)
        assert len(list(OUT.glob('*.png')))==10
