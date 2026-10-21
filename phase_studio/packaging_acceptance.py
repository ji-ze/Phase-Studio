"""Explicit frozen-package diagnostics; no login or remote scientific jobs.

This path is entered only with --packaging-acceptance and a caller-selected
output directory. All settings/credentials are isolated for the diagnostic run.
An additional opt-in saved-map check exercises local native EDMA only.
"""
import json,os,time,hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def run(directory):
    if os.environ.get('PHASE_STUDIO_EDMA_ACCEPTANCE_INPUT'):
        from .edma_acceptance import run_saved_map_check
        return run_saved_map_check(directory, os.environ['PHASE_STUDIO_EDMA_ACCEPTANCE_INPUT'])
    directory=Path(directory).absolute();directory.mkdir(parents=True,exist_ok=True)
    responsive=os.environ.get('PHASE_STUDIO_RESPONSIVE_ACCEPTANCE')=='1'
    started=time.perf_counter();report={'offline':True,'scientific_run':False,'real_jana':False,'controlled_fixtures':True}
    os.environ['PHASE_STUDIO_STARTUP_PROBE']='1'
    from PySide6.QtCore import QSettings,QTimer,QLocale,Qt,QRect
    from PySide6.QtGui import QScreen
    from PySide6.QtWidgets import QApplication,QDialog,QFileDialog,QToolButton
    from PySide6.QtTest import QTest
    from . import credentials
    from .credentials import CredentialStore
    store=CredentialStore(backend=None)
    credentials.credential_store=store
    from . import jana_superflip as js,update_ui
    from .ui_style import apply_phase_studio_style
    from .version import VERSION
    app=QApplication.instance() or QApplication([]);apply_phase_studio_style(app)
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,str(directory/'settings'))
    screen_patch=None
    if app.platformName()=='offscreen' or responsive:
        # Explicit 1920x1040 physical acceptance viewport; the offscreen
        # plugin's small default is not a representative high-DPI monitor.
        scale=float(os.environ.get('QT_SCALE_FACTOR','1'))
        width,height=map(int,os.environ.get('PHASE_STUDIO_ACCEPTANCE_SCREEN','1920x1040').split('x'))
        screen_patch=patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,int(width/scale),int(height/scale)))
        screen_patch.start()
    factory=lambda org,name:QSettings(str(directory/(name+'.ini')),QSettings.IniFormat)
    state=update_ui.UpdateState(factory('PhaseStudio','updates'),directory/'updates.lock');state.set_enabled(False)
    app._phase_studio_updates=update_ui.UpdateService(app,state=state,automatic_allowed=False)
    programs=directory/'Jana'/'SUPERFLIP';programs.mkdir(parents=True,exist_ok=True)
    for name in ('superflip.exe','EDMA.exe'):(programs/name).write_bytes(b'Never execute: path-resolution fixture')
    source=directory/'input.inflip'
    source.write_text('title packaging_fixture\nperform CF\noutputformat xplor\ndimension 3\ncell 10 11 12 90 90 90\nspacegroup P1\ncomposition C2\ndataformat intensity\nfbegin\n1 0 0 10\n0 1 0 20\nendf\n',encoding='utf8')
    if responsive:
        # Controlled powder data, never a user's project or real API job.
        source.write_text('title responsive_fixture\nperform CF\noutputformat xplor\ndimension 3\ncell 8.2512 18.8436 6.7032 90 92.58 90\nspacegroup P1\ncomposition C9 O N Cl\ndataformat intensity fwhm\nfbegin\n'+
                          '\n'.join(f'{i%8-4} {i//8%8-4} {i//64+1} {10000 if i==343 else (i%50+1)/10} {0.05+i%7*.001}' for i in range(344))+'\nendf\n',encoding='utf8')
    source_bytes=source.read_bytes()
    def settle():
        for _ in range(20):app.processEvents()
    screenshots=[]
    def snap(name,widget):
        settle();assert widget.isVisible()
        assert widget.grab().save(str(directory/(name+'.png')))
        screenshots.append(name)
    try:
        imports=js._qt_imports
        with patch.object(js,'_qt_imports',lambda:imports()|{'QSettings':factory}),patch.object(js,'credential_store',store),\
                patch.object(js,'application_dir',lambda:programs.parent),patch.object(QDialog,'exec',lambda self:QDialog.Rejected),\
                patch.object(js.SharpEDServerClient,'get_models',lambda self:SimpleNamespace(models=[js.SHARPED_ONE_CYCLE_MODEL,js.SHARPED_ITERATIVE_MODEL],default_model=js.SHARPED_ONE_CYCLE_MODEL,provenance='offline')):
            wizard=js._JanaWorkflowWizard([],source);wizard.run();wizard.dialog.show();settle()
            readiness=dict(version=VERSION,pid=os.getpid(),visible=wizard.dialog.isVisible(),platform=app.platformName(),
                locale=QLocale.system().name(),ready_seconds=time.perf_counter()-started,title=wizard.dialog.windowTitle())
            (directory/'visible.json').write_text(json.dumps(readiness),encoding='utf8')
            assert readiness['visible'];report.update(readiness)
            snap('01-wizard',wizard.dialog)
            report['initial_geometry']=wizard.dialog.geometry().getRect()
            report['workflow_scroll']=wizard.scroll_area.verticalScrollBar().maximum()
            if responsive and report['workflow_scroll']:
                wizard.scroll_area.verticalScrollBar().setValue(report['workflow_scroll']);snap('01c-workflow-scrolled',wizard.dialog)
                wizard.scroll_area.verticalScrollBar().setValue(0);settle()
            if responsive:
                initial=wizard.dialog.geometry()
                wizard.dialog.resize(max(640,initial.width()-80),max(400,initial.height()-80));snap('01b-manual-resize',wizard.dialog)
                wizard.dialog.setGeometry(initial);settle()
                report['all_cards_visible']=all(wizard.scroll_area.viewport().rect().contains(tile.mapTo(wizard.scroll_area.viewport(),tile.rect().bottomRight())) for tile in
                    (wizard.original_superflip_tile,wizard.superflip_sharped_tile,wizard.autosolve_tile,wizard.professional_mode_tile))
            if os.environ.get('PHASE_STUDIO_ACCEPTANCE_STARTUP_ONLY')=='1':
                report['ok']=True
            else:
                wizard.superflip_sharped_tile._trigger();settle()
                deadline=time.monotonic()+10
                while wizard.model_cache['inflight']:
                    settle();QTest.qWait(10);assert time.monotonic()<deadline
                wizard.cycles.setValue(3)
                if responsive:
                    snap('02a-configuration',wizard.dialog)
                    wizard.model.showPopup();snap('02b-model-popup',wizard.model.view().window());wizard.model.hidePopup()
                wizard.primary_button.click();settle()
                assert wizard.stack.currentWidget() is wizard.page3
                snap('02-map-feedback',wizard.dialog)
                if responsive:
                    wizard.powder_enabled_checkbox.setChecked(True);settle();snap('02c-feedback-enabled',wizard.dialog)
                    report['powder_applicable']=wizard.feedback_is_powder
                    report['wavelength_missing']=wizard._map_feedback_wavelength()[0]==0
                    wizard.powder_wavelength_spin.setValue(1.5406);settle();snap('02d-feedback-manual-wavelength',wizard.dialog)
                    report['manual_wavelength']=wizard._map_feedback_wavelength()[0]
                    source.with_suffix('.m90').write_text('lambda 1.541866\nend\n',encoding='utf8')
                    wizard.powder_wavelength_spin.setValue(0);settle();snap('02dd-feedback-automatic-wavelength',wizard.dialog)
                    assert wizard._map_feedback_wavelength()[0]==1.541866
                    report['automatic_wavelength']=wizard._map_feedback_wavelength()[0]
                    if wizard.scroll_area.verticalScrollBar().maximum():
                        wizard.scroll_area.verticalScrollBar().setValue(wizard.scroll_area.verticalScrollBar().maximum())
                        snap('02de-feedback-scrolled-footer',wizard.dialog)
                wizard.back_button.click();settle()
                if responsive:
                    wizard.back_button.click();settle();snap('02e-return-workflow',wizard.dialog)
                    assert wizard.dialog.geometry()==initial
                    report['navigation_geometry_unchanged']=True
                from .sharped_access import SharpEDAccessDialog
                access=SharpEDAccessDialog(wizard.dialog,store=store);access.show();snap('03-account',access);access.close()
                menu=wizard.update_menu.menu();menu.popup(wizard.update_menu.mapToGlobal(wizard.update_menu.rect().bottomLeft()));snap('04-menu',menu);menu.hide()
                assert js.resolve_active_jana_superflip(programs)==programs/'superflip.exe'
                report['wizard_navigation']=True;report['superflip_resolution']=True
        if not report.get('ok'):
            from . import app as a,hkl_diagnostics as hd,hkl_diagnostics_ui as hu,structure_camera as camera,result_selection as selection
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            import numpy as np,gemmi
            with patch.object(a,'QSettings',factory),patch.object(camera,'QSettings',factory),patch.object(selection,'QSettings',factory),\
                    patch.object(a.IterativeSuperflipPipelineQtGUI,'load_settings',lambda self:None),\
                    patch.object(a.IterativeSuperflipPipelineQtGUI,'save_settings',lambda self:None),\
                    patch.object(a.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models',lambda self:None):
                backend=a.IterativeSuperflipPipelineQtGUI();backend.timer.stop()
                _check_feedback_significance(a, backend, wizard, report, directory, snap)
                hkl=directory/'fixture.hkl'
                hkl.write_text('\n'.join(f'{i%8-4} {i//8%8-4} {i//64+1} {10000 if i==343 else (i%50+1)/10} {0.05+i%7*.001}' for i in range(344)) if responsive else
                               '\n'.join(f'{h} {k} 1 {h*k+.125} .0527' for h in range(1,8) for k in range(1,7)))
                mode=a.REFLECTION_DATA_MODE_INTENSITY_FWHM
                raw=list(hd.read_diagnostic_reflections(hkl,mode)[0]);cell=gemmi.UnitCell(8.2512,18.8436,6.7032,90,92.58,90);sg=gemmi.SpaceGroup('P 1 21/n 1')
                loaded=a.HklLoadResult(hkl,mode,cell,sg,sg.xhm(),'Controlled packaging fixture',*a.reflection_columns_for_mode(mode),raw,a.merge_duplicate_reflections(raw))
                loaded.diagnostics=hd.build_diagnostics(loaded,fwhm_units='degrees_2theta',overlap_groups={(1,1,1):1,(2,1,1):1})
                analysis=a.analyze_hkl_data(hkl,mode,cell,sg,sg.xhm(),loaded.source_note,_loaded=loaded)
                diagnostics=hu.presentation_report(analysis)
                diagnostics.export_json(directory/'hkl-report.json',analysis);hd.export_shell_csv(directory/'hkl-report.csv',diagnostics)
                validation=hu.validation_dialog(backend,loaded);validation.show();snap('05-hkl-validation',validation)
                if responsive:
                    assert validation.hkl_table.model().rowCount()==344
                    validation.hkl_table.scrollToBottom();snap('05b-validation-last-records',validation)
                    validation.hkl_table.sortByColumn(3,Qt.DescendingOrder);snap('05c-validation-numeric-sort',validation)
                    assert validation.hkl_table.model().index(0,3).data(Qt.UserRole)==10000
                    validation.hkl_table.selectRow(0);validation.hkl_copy_selected_button.click();snap('05d-validation-copy',validation)
                validation.close()
                complete=hu.completeness_dialog(backend,analysis);complete.show();snap('06-completeness',complete)
                if responsive:
                    complete.hkl_histogram_focus.setCurrentIndex(1);snap('06b-histogram-detail',complete)
                    complete.hkl_histogram_focus.setCurrentIndex(0);snap('06c-histogram-full',complete)
                    advanced=hu._detail_dialog(complete,diagnostics);advanced.show()
                    for index in range(7):
                        advanced.hkl_details_tabs.setCurrentIndex(index);snap('06d-advanced-'+str(index),advanced)
                    advanced.close()
                for index in range(complete.hkl_plot_tabs.count()):
                    complete.hkl_plot_tabs.setCurrentIndex(index);snap('07-plots-'+str(index),complete)
                for extension in ('png','pdf','svg'):
                    complete.hkl_figure.savefig(directory/('completeness.'+extension))
                report['plots']=True;report['hkl_records']=len(raw);complete.close()
                figure=Figure(figsize=(7,4));canvas=FigureCanvasQTAgg(figure)
                grid=np.arange(256,dtype=float).reshape(16,16)/255;figure.add_subplot().imshow(grid)
                canvas.show();canvas.draw();snap('08-density-array',canvas)
                for extension in canvas.get_supported_filetypes():
                    if extension in ('pgf','eps','ps'):continue  # external TeX/PostScript is not an acceptance prerequisite
                    figure.savefig(directory/('image-format.'+extension))
                report['image_formats']=sorted(canvas.get_supported_filetypes());report['array_sha256']=hashlib.sha256(grid.tobytes()).hexdigest();canvas.close()
                from .map_quality import ResultCandidate,MapQualityMetrics,ValidationProfile,profile_definition,recommend_best_result
                from .result_selection import ResultSelectionDialog,create_result_preview_host
                cif=directory/'structure.cif'
                cif.write_text("data_fixture\n_cell_length_a 10\n_cell_length_b 10\n_cell_length_c 10\n_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n_space_group_name_H-M_alt 'P 1'\nloop_\n_atom_site_label\n_atom_site_type_symbol\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\nC1 C 0.1 0.1 0.1\nO1 O 0.22 0.1 0.1\n")
                from .xplor_io import XplorMap,write_xplor_map,read_xplor_map
                density=np.arange(64,dtype=float).reshape(4,4,4)/63
                map_path=directory/'controlled-map.xplor'
                write_xplor_map(map_path,XplorMap('Controlled packaging fixture',(4,0,3,4,0,3,4,0,3),(10,10,10,90,90,90),'ZYX',density))
                assert np.allclose(read_xplor_map(map_path).data,density.ravel(),atol=1e-5)
                report['map_array_sha256']=hashlib.sha256(density.tobytes()).hexdigest()
                candidates=[ResultCandidate(cycle=i,source='superflip',map_path=str(map_path),structure_path=str(cif),metrics=MapQualityMetrics(amplitude_rf=.3/i),candidate_id='controlled-'+str(i),edma_sigma=1.,unit_cell=(10,10,10,90,90,90),space_group='P 1',edma_asu_composition='C1 O1') for i in (1,2,3)]
                profile=ValidationProfile.REFERENCE_FREE
                selector=ResultSelectionDialog(backend,candidates,[],profile,profile_definition(profile),recommend_best_result(profile,candidates),recommend_best_result(profile,[]),
                    superflip_tab_available=True,sharped_tab_available=False,initial_source='superflip',map_feedback_intensity_enabled=False,jana_context=False,
                    preview_host=create_result_preview_host(backend,gemmi.UnitCell(10,10,10,90,90,90),30,-60),parse_structure=a.parse_cif_atoms,reference_atoms=[],source_title=lambda source:'Superflip')
                selector.show();selector.resize(1200,760);snap('09-result-selection',selector)
                assert selector._resolved_preview is not None and selector._action_button.isEnabled()
                before=selector._resolved_preview
                camera_button=next(button for button in selector.findChildren(QToolButton) if button.text()=='Camera')
                camera_button.menu().popup(camera_button.mapToGlobal(camera_button.rect().bottomLeft()))
                snap('09a-camera',camera_button.menu());camera_button.menu().hide()
                selector._open_fullscreen();settle()
                detached=next(w for w in app.topLevelWidgets() if w is not selector and w.isFullScreen())
                snap('10-fullscreen',detached);detached.close()
                assert selector._resolved_preview==before
                report['rendered_atoms']=len(before.atoms);report['candidate_id']=selector.preview_candidate_id
                selector.close();backend.close()
            dialog=QFileDialog(wizard.dialog,'Phase Studio controlled file-dialog acceptance',str(directory));dialog.setFileMode(QFileDialog.ExistingFile)
            QTimer.singleShot(250,dialog.reject);dialog.exec();report['file_dialog_open_close']=True
            from .error_reporting import build_error_report,show_phase_studio_error
            def close_error():
                for w in app.topLevelWidgets():
                    if w.objectName()=='phaseStudioErrorDialog':snap('11-error',w);w.reject()
            QTimer.singleShot(100,close_error);show_phase_studio_error(wizard.dialog,build_error_report(ValueError('Controlled packaging check'),subsystem='Packaging',operation='Offline acceptance'))
            from .ui_branding import phase_studio_brand_runtime_report
            report['branding']=phase_studio_brand_runtime_report('packaging-acceptance')
            report['original_input_unchanged']=source.read_bytes()==source_bytes
            assert report['original_input_unchanged']
            report['ok']=True
    except Exception as exc:
        import traceback
        report.update(ok=False,error_type=type(exc).__name__,details=traceback.format_exc())
    finally:
        report['screenshots']=screenshots
        (directory/'acceptance.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf8')
        for widget in app.topLevelWidgets():widget.close()
        settle()
        if screen_patch is not None:screen_patch.stop()
    return 0 if report.get('ok') else 1


def _check_feedback_significance(a, backend, wizard, report, directory, snap):
    """Frozen UI + actual correction gate, controlled predictions and no network."""
    import gemmi
    import math
    backend.inputs['map_feedback_intensity_enabled'].setChecked(True)
    control = backend.inputs['map_feedback_intensity_max_i_over_sigma']
    assert backend.input_labels['map_feedback_intensity_max_i_over_sigma'].text() == 'I/σ(I) limit'
    assert 'I/σ(I) ≈ F/[2σ(F)]' in control.toolTip()
    for index in range(backend.basic_tabs.count()):
        if 'map feedback' in backend.basic_tabs.tabText(index).casefold():
            backend.basic_tabs.setCurrentIndex(index)
    backend.category_tabs.setCurrentIndex(0)
    backend.resize(1100, 800)
    backend.show()
    predictions = {(1,0,0):(1.,0.), (2,0,0):(9.,0.), (3,0,0):(16.,0.)}
    results = []
    for mode in (a.REFLECTION_DATA_MODE_INTENSITY, a.REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA,
                 a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA, a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA):
        amplitude = a.reflection_mode_is_amplitude(mode)
        backend._set_widget_value_from_string(backend.inputs['reflection_data_mode'],a.format_reflection_data_mode(mode))
        rows = [a.Reflection(i,0,0,f if amplitude else f*f,s if amplitude else 2*f*s,37.)
                for i,(f,s) in enumerate(((2.,.5),(4.,1.),(6.,.5)),1)]
        original = [(r.value,r.sigma,r.phase) for r in rows]
        with patch.object(wizard,'_detect_reflection_data_mode',return_value=mode), \
                patch.object(wizard,'input_reflections',rows,create=True):
            wizard._sync_page3_for_data_type()
            wizard.stack.setCurrentWidget(wizard.page3)
            wizard.intensity_enabled_checkbox.setChecked(True)
            wizard.intensity_damping_spin.setValue(.5)
            assert wizard.intensity_form.labelForField(wizard.intensity_sigma_spin).text() == 'I/σ(I) limit'
            assert 'F/[2σ(F)]' in wizard.intensity_sigma_spin.toolTip()
            if amplitude:
                assert 'first-order approximation' in wizard.intensity_note.text()
            for threshold in (2.,2.5):
                control.setValue(threshold)
                wizard.intensity_sigma_spin.setValue(threshold)
                for origin, limit in (('configuration',control.value()),('wizard',wizard.intensity_sigma_spin.value())):
                    with patch.object(a,'xplor_fft_predictions',return_value=predictions):
                        updated,_ = a.apply_map_feedback_to_reflections(rows,mode,directory/'controlled-map.xplor',
                            gemmi.UnitCell(10,10,10,90,90,90),0,False,0,True,.5,limit,lambda s:None)
                    expected = (4.,16.,36.) if threshold == 2. else (3.125,18.125,36.)
                    assert all(math.isclose(r.value*r.value if amplitude else r.value,value,abs_tol=1e-10)
                               for r,value in zip(updated,expected))
                    assert [(r.sigma,r.phase) for r in updated] == [(r.sigma,r.phase) for r in rows]
                    results.append(dict(format=mode,ui=origin,limit=limit,passed=True))
            assert [(r.value,r.sigma,r.phase) for r in rows] == original
            suffix = 'amplitude' if amplitude else 'intensity'
            if not a.reflection_mode_has_phase(mode):
                snap('12-map-significance-wizard-'+suffix,wizard.dialog)
                snap('12-map-significance-configuration-'+suffix,backend)
    # Sentinel bypass and width-only rejection use the same frozen authority.
    zeros = [a.Reflection(1,0,0,0.,None),a.Reflection(2,0,0,4.,None)]
    with patch.object(a,'xplor_fft_predictions',return_value=predictions):
        updated,_ = a.apply_map_feedback_to_reflections(zeros,a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA,
            directory/'controlled-map.xplor',gemmi.UnitCell(10,10,10,90,90,90),0,False,0,True,.5,0,lambda s:None)
    assert updated[0].value > 0
    for mode in (a.REFLECTION_DATA_MODE_INTENSITY_FWHM,a.REFLECTION_DATA_MODE_AMPLITUDE_FWHM):
        try:
            a.apply_map_feedback_to_reflections(zeros,mode,directory/'controlled-map.xplor',
                gemmi.UnitCell(10,10,10,90,90,90),0,False,0,True,.5,2,lambda s:None)
        except ValueError as error:
            assert 'FWHM' in str(error)
        else:
            raise AssertionError('FWHM was treated as an uncertainty')
    report['map_feedback_significance'] = dict(checks=results,zero_bypasses_filter=True,
        fwhm_rejected=True,observations_unchanged=True,shared_unit='I/σ(I)')
    wizard.dialog.close()
