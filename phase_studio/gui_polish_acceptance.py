"""Opt-in real-widget visual fixtures. No inference or scientific executable runs."""

def run(directory):
    import os,sys,json,shutil,hashlib,tempfile,time
    from pathlib import Path
    from unittest.mock import patch
    from types import SimpleNamespace
    repo=Path(directory).absolute()
    os.environ['QT_QPA_PLATFORM']=os.environ.get('QT_QPA_PLATFORM','offscreen');os.environ['PHASE_STUDIO_STARTUP_PROBE']='1'
    from PySide6.QtCore import QSettings,QRect,Qt
    from PySide6.QtGui import QScreen,QFontInfo
    from PySide6.QtWidgets import QApplication,QDialog,QLabel
    from phase_studio import app as a,jana_superflip as js,update_ui,hkl_diagnostics as d,hkl_diagnostics_ui as hu
    from phase_studio.about_ui import AboutDialog
    from phase_studio.credentials import CredentialStore
    phase='acceptance';scale=os.environ.get('QT_SCALE_FACTOR','1');out=Path(directory).absolute();out.mkdir(parents=True,exist_ok=True)
    provided=os.environ.get('PHASE_STUDIO_POLISH_REAL_INPUT','')
    if provided:
        source=Path(provided).absolute()
        if not source.is_file():raise ValueError('Saved input is unavailable')
    else:
        source=out/'controlled_Superflip.inflip'
        source.write_text('title controlled_ui_fixture\ncell 8 12 7 90 94 90\nspacegroup P1\ncomposition C4 O\ndataformat intensity fwhm\nlambda 1.541866\nfbegin\n'+
            '\n'.join(f'{h} {k} 1 {10+h*k} .0527' for h in range(1,8) for k in range(1,6))+'\nendf\n',encoding='utf8')
    original=source.read_bytes()
    local=out/'input'/source.name;local.parent.mkdir(exist_ok=True);shutil.copy2(source,local)
    if source.with_suffix('.m90').is_file():shutil.copy2(source.with_suffix('.m90'),local.with_suffix('.m90'))
    profile='jana' if (getattr(sys,'frozen',False) and Path(sys.executable).name.lower()=='phase_studio.exe') else os.environ.get('PHASE_STUDIO_GUI_PROFILE','standalone')
    app=QApplication.instance() or QApplication([]);a.apply_phase_studio_style(app);rows={}
    def settle():
        for _ in range(20):app.processEvents()
    def snap(name,widget):
        settle();assert widget.grab().save(str(out/(name+'.png')))
        rows[name]=dict(geometry=widget.geometry().getRect(),dpr=widget.devicePixelRatioF())
    with tempfile.TemporaryDirectory() as temporary,patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,int(1920/float(scale)),int(1040/float(scale)))):
        QSettings.setDefaultFormat(QSettings.IniFormat);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,temporary)
        state=update_ui.UpdateState(QSettings(str(Path(temporary)/'updates.ini'),QSettings.IniFormat),Path(temporary)/'updates.lock');state.set_enabled(False)
        app._phase_studio_updates=update_ui.UpdateService(app,state=state,automatic_allowed=False)
        with patch.object(a.IterativeSuperflipPipelineQtGUI,'load_settings',lambda self:None),patch.object(a.IterativeSuperflipPipelineQtGUI,'save_settings',lambda self:None),patch.object(a.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models',lambda self:None):
            main=a.IterativeSuperflipPipelineQtGUI();main.timer.stop();main.resize(1440,900);main.show();settle()
            for advanced,name in ((False,'Input'),(False,'Workflow'),(False,'Help'),(True,'Help'),(True,'Setup'),(True,'Superflip')):
                main.category_tabs.setCurrentIndex(int(advanced));tabs=main.advanced_tabs if advanced else main.basic_tabs
                tabs.setCurrentIndex(next(i for i in range(tabs.count()) if tabs.tabText(i)==name));snap(('advanced-' if advanced else 'basic-')+name.lower(),main)
            about=AboutDialog(main,jana=profile=='jana');about.show();settle()
            for index,name in enumerate(('authors','license','third-party','citation')):about.cards[index].click();snap('about-'+name,about)
            original_size=about.size()
            for width,height in ((480,520),(640,360)):
                about.resize(width,height)
                settle();expected_size=about.size()
                for index,name in enumerate(('authors','license','third-party','citation')):
                    about.cards[index].click();snap(f'about-{width}x{height}-{name}',about)
                    assert about.size()==expected_size, 'Section changes must preserve geometry'
                    assert about.rect().contains(about.close_button.geometry().bottomRight())
            about.resize(original_size)
            for name in ('LICENSE','THIRD_PARTY_NOTICES.md','AUTHORS.md','CITATION.cff'):
                viewer=about.open_document(name,third_party=name=='THIRD_PARTY_NOTICES.md',contacts=name=='AUTHORS.md');snap('reader-'+name.replace('.','-'),viewer);viewer.close();settle()
            citations=about.open_citations();snap('citations-phase-studio',citations)
            for i,name in enumerate(('phase-studio','superflip','edma','sharped')):
                citations.list.setCurrentRow(i);snap('citations-'+name,citations)
            citations.close();about.close()
            notice=update_ui.UpdateNotice(main,latest_stable=__import__('phase_studio.update_checker',fromlist=['Release']).Release((2,0,6)));notice.show();snap('update',notice);notice.close()
            request=a.build_hkl_analysis_request_from_inflip(local,work_dir=local.parent);load=d.cached_load_result(request);analysis=d.cached_analysis(request)
            view=hu.validation_dialog(main,load);view.show();snap('view-data',view);view.close()
            analysis_dialog=hu.completeness_dialog(main,analysis);analysis_dialog.show();snap('analyze-data',analysis_dialog)
            for index in range(analysis_dialog.hkl_plot_tabs.count()):
                analysis_dialog.hkl_plot_tabs.setCurrentIndex(index);snap('analyze-tab-'+str(index),analysis_dialog)
            rows['scientific']=dict(records=len(load.reflections),d_min=analysis.d_min,d98=analysis.d_full_98,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),diagnostics=analysis.diagnostics.to_dict() if hasattr(analysis.diagnostics,'to_dict') else str(type(analysis.diagnostics)))
            analysis_dialog.close()
            from phase_studio.input_analysis_ui import analyze_data_dialog
            unified=analyze_data_dialog(main,analysis);unified.show();snap('analysis-overview',unified)
            for index in range(unified.analysis_tabs.count()):
                unified.analysis_tabs.setCurrentIndex(index);snap('analysis-page-'+str(index),unified)
            unified.close()
            from phase_studio.error_reporting import build_validation_report
            from phase_studio.validation_issues import ValidationIssue
            for key,report in [('fwhm-validation',build_validation_report([ValidationIssue(
                'FWHM is peak width, not measured uncertainty', 'significance_fwhm','i_over_sigma_min','Superflip',True)])),
                ('missing-superflip',build_validation_report(['Phase Studio could not find a working Superflip executable.']))]:
                def capture_error(dialog):
                    dialog.show();snap(key,dialog);dialog.reject();return QDialog.Rejected
                with patch.object(QDialog,'exec',capture_error):main._show_error_report(report,write_log=False)
            from phase_studio.feedback_diagnostics import compare_stage,save_report,load_summaries
            from phase_studio.feedback_diagnostics_ui import FeedbackDiagnosticsDialog
            directory=out/'controlled-recorded-run';directory.mkdir(exist_ok=True)
            before=[a.Reflection(1,0,0,10,.1),a.Reflection(2,0,0,20,.1)]
            after=[a.Reflection(1,0,0,7.5,.1),a.Reflection(2,0,0,22.5,.1)]
            operation=compare_stage(before,after,a.REFLECTION_DATA_MODE_INTENSITY_FWHM,eligible={(1,0,0),(2,0,0)},groups={(1,0,0):1,(2,0,0):1})
            operation.update(operation='powder',status='Applied',reason='Controlled read-only diagnostic fixture')
            save_report(directory,dict(schema=1,run_id='controlled-ui-record',source_cycle=1,target_cycle=2,operations=[operation],errors=[],definitions='Controlled fixture; not an experimental feedback result'))
            feedback=FeedbackDiagnosticsDialog(main,load_summaries(directory),directory,historical=True);feedback.show();snap('recorded-feedback',feedback);feedback.close()
            empty=FeedbackDiagnosticsDialog(main,[],directory,historical=True);empty.show();snap('empty-feedback',empty)
            assert not empty.tabs.isVisible() and all(not button.isEnabled() for button in empty.cycle_exports)
            empty.close();main.close()
        class MemoryCredentials:
            def __init__(self): self.values={}
            def read(self, origin): return self.values.get(origin, '')
            def write(self, origin, value): self.values[origin]=value
            def delete(self, origin): self.values.pop(origin, None)
        store=CredentialStore(backend=MemoryCredentials())
        store.set('controlled-offline-capture-key', remember=True)
        with patch.object(js,'application_dir',lambda:Path('C:/Jana2020/SharpED')),patch.object(js,'credential_store',store),patch.object(QDialog,'exec',lambda self:QDialog.Rejected),patch.object(js.SharpEDServerClient,'get_models',lambda self:SimpleNamespace(models=[js.SHARPED_ONE_CYCLE_MODEL,js.SHARPED_ITERATIVE_MODEL,'controlled-model-3','controlled-model-4'],default_model=js.SHARPED_ONE_CYCLE_MODEL,provenance='offline')):
            wizard=js._JanaWorkflowWizard([],local);wizard.run();wizard.dialog.show();settle();snap('wizard-workflow',wizard.dialog)
            wizard.superflip_sharped_tile._trigger();settle()
            for _ in range(80):
                if not wizard.model_cache['inflight']:break
                wizard.refresh_timer.timeout.emit();app.processEvents();time.sleep(.005)
            wizard.cycles.setValue(3)
            selected=wizard.model.findText(js.SHARPED_ITERATIVE_MODEL)
            wizard.model.setCurrentIndex(selected);wizard.model.activated.emit(selected)
            snap('wizard-processing',wizard.dialog)
            wizard._go_to_map_feedback();settle();snap('feedback-disabled',wizard.dialog)
            wizard.powder_enabled_checkbox.setChecked(True);snap('feedback-powder',wizard.dialog)
            wizard.intensity_enabled_checkbox.setChecked(True);wizard.intensity_damping_spin.setValue(0);snap('feedback-zero-damping',wizard.dialog)
            wizard.scroll_area.verticalScrollBar().setValue(wizard.scroll_area.verticalScrollBar().maximum());snap('feedback-zero-damping-controls',wizard.dialog)
            wizard.intensity_damping_spin.setValue(.25);snap('feedback-positive-damping',wizard.dialog)
            wizard.dialog.close()
    rows['metadata']=dict(phase=phase,scale=scale,physical_display=False,real_saved_input=bool(provided),profile=profile,scientific_workflow=False,remote_models='controlled offline catalogue')
    assert source.read_bytes()==original
    rows['passed']=True
    (out/'report.json').write_text(json.dumps(rows,indent=2,default=str),encoding='utf8')
    return 0
