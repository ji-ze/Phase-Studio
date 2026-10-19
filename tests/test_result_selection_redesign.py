"""Real Qt selector geometry, scientific identity and metric transparency guards."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import unittest
from unittest.mock import patch
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QDialog
from phase_studio import app as engine
import test_jana_completion as fixture
from test_map_quality import synthetic_map, context_for, GRID, CELL, HKLS
from phase_studio.map_quality import compute_map_quality

class ResultSelectionRedesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owns_app=QApplication.instance() is None
        cls.qtapp=QApplication.instance() or QApplication([])
        if os.name == 'nt':
            from PySide6.QtGui import QFontDatabase
            for name in ('segoeui.ttf','segoeuib.ttf','seguisym.ttf'):
                QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name))
        from phase_studio.ui_style import apply_phase_studio_style
        apply_phase_studio_style(cls.qtapp)
    @classmethod
    def tearDownClass(cls):
        if cls.owns_app:
            import shiboken6
            cls.qtapp.processEvents()
            shiboken6.delete(cls.qtapp)
            cls.qtapp=None
    def setUp(self):
        self.settings=patch.multiple(engine.IterativeSuperflipPipelineQtGUI,
            load_settings=lambda self:None,save_settings=lambda self:None,
            refresh_sharped_models=lambda self:None)
        self.settings.start()
        self.backend,results=fixture.build_window(engine)
        self.backend.results=results
        opened=[]
        with patch.object(engine.ResultSelectionDialog,'exec',lambda d:opened.append(d) or QDialog.Rejected):
            self.backend.open_result_selector('jana')
        self.dialog=opened[0]
        self.dialog._rotate_timer.stop()
        self.dialog._auto_rotate_button.setChecked(False)
        self.dialog.show()
        self.events()
    def events(self):
        for _ in range(5):self.qtapp.processEvents()
    def tearDown(self):
        from PySide6.QtTest import QTest
        QTest.qWait(360)  # Drain existing native activation timers while owners live.
        for window in (self.dialog,self.backend):
            window.close();window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.settings.stop()
    def test_projected_geometry_and_manual_camera(self):
        from mpl_toolkits.mplot3d import proj3d
        d=self.dialog
        for width,height in ((1280,720),(1500,850),(1920,1080),(2560,1440)):
            d.resize(width,height);self.events();d._request_preview_fit();d._preview_canvas.draw()
            axis=d._preview_figure.axes[0]
            points=d._preview_fit_coords.copy()
            x,y,_=proj3d.proj_transform(*points.T,axis.get_proj())
            pixels=axis.transData.transform(np.column_stack((x,y)))
            viewport=axis.get_position(original=True).transformed(axis.figure.transFigure)
            self.assertAlmostEqual(max(np.ptp(pixels,axis=0)/[viewport.width,viewport.height]),.78,places=5)
            self.assertTrue(np.all(pixels.min(axis=0)>[viewport.x0,viewport.y0]))
            self.assertTrue(np.all(pixels.max(axis=0)<[viewport.x1,viewport.y1]))
            np.testing.assert_array_equal(points,d._preview_fit_coords)
        axis.set_xlim3d(-3,8)
        d._preview_camera_interaction('pan')
        before=axis.get_xlim3d()
        d._render_preview(d.selected_candidate);self.events()
        self.assertEqual(d._preview_figure.axes[0].get_xlim3d(),before)
        d.resize(1400,800);self.events()
        self.assertEqual(d._preview_figure.axes[0].get_xlim3d(),before)
    def test_family_selection_warning_and_authoritative_model_count(self):
        d=self.dialog
        d._superflip_btn.setChecked(True);self.events()
        d._views['superflip'].table.selectRow(0);self.events()
        selected=d.selected_candidate
        self.assertEqual(d._views['superflip'].table.horizontalHeaderItem(0).text(),'★')
        self.assertEqual(d._views['superflip'].table.columnWidth(0),40)
        before=d._preview_canvas.geometry()
        d._sharped_btn.setChecked(True);self.events()
        after=d._preview_canvas.geometry()
        self.assertEqual(before,after)
        d._superflip_btn.setChecked(True);self.events()
        self.assertEqual(selected,d.selected_candidate)
        self.assertIn('Jana model: 2 atomic sites',d._metadata_label.text())
        from test_result_selection_viewer import large_cif
        path=Path(selected.structure_path).parent/'nine-edma-sites.cif'
        path.write_text(large_cif(9),encoding='utf8')
        path.with_suffix('.m40').write_bytes(Path(selected.jana_model_path).read_bytes())
        updated=engine.seal_result_candidate(replace(selected,structure_path=str(path)))
        self.assertEqual(len(engine.parse_cif_atoms(path)),9)
        self.assertEqual(engine._m40_model_count(path.with_suffix('.m40')),2)
        d._render_preview(updated)
        self.assertEqual(dict(d._candidate_detail_rows)['EDMA candidate'],'9 sites')
        self.assertIn('EDMA ASU composition',d._metadata_label.toolTip())
        self.assertNotIn('&lt;b&gt;',d._metadata_label.toolTip())
        self.assertIn('Jana model: 2 atomic sites',d._metadata_label.text())
        captured=[]
        def inspect_details(widget):
            from PySide6.QtWidgets import QLabel
            captured.extend(label.text() for label in widget.findChildren(QLabel))
            return QDialog.Rejected
        with patch.object(QDialog,'exec',inspect_details):d._candidate_info.click()
        self.assertIn('9 sites',captured)
        self.assertIn('2 atomic sites',captured)
        absent=replace(updated,jana_model_sha256='',jana_model_site_count=None)
        d._render_preview(absent)
        self.assertEqual(dict(d._candidate_detail_rows)['Jana model'],'prepared during handoff')
    def test_async_identity_pending_and_same_m40(self):
        d=self.dialog
        pending=[]
        def request(c,add,callback):
            req=SimpleNamespace(threshold=c.edma_sigma+(-.1 if add else .1))
            pending.append((c,callback,req));return req
        d._adjust_threshold_async=request
        d._change_threshold(True)
        original,callback,req=pending[0]
        self.assertAlmostEqual(req.threshold,.4)
        self.assertFalse(d._action_button.isEnabled())
        self.assertEqual(d.selected_candidate,original)
        model=Path(original.jana_model_path).read_bytes()
        updated=replace(original,edma_sigma=.4,detected_atom_count=7,candidate_id='completed-.4')
        callback(updated,None,req)
        self.assertTrue(d._action_button.isEnabled())
        self.assertEqual(d.selected_candidate,updated)
        self.assertEqual(Path(updated.jana_model_path).read_bytes(),model)
        self.assertIn('Jana model: 2 atomic sites',d._metadata_label.text())
        callback(original,None,req)
        self.assertEqual(d.selected_candidate,updated)
        d._change_threshold(False)
        failed,callback,req=pending[-1]
        self.assertAlmostEqual(req.threshold,.5)
        callback(None,'failed',req)
        self.assertTrue(d._action_button.isEnabled())
        self.assertEqual(d.selected_candidate,updated)
        self.assertIn('retained',d._threshold_status.text())

    def test_empty_family_clears_foreign_preview_and_disables_handoff(self):
        d=self.dialog
        d._views['deblurred'].selected=None
        d._apply_source('deblurred')
        self.assertIsNone(d.selected_candidate)
        self.assertEqual(d.preview_candidate_id,'')
        self.assertFalse(d._action_button.isEnabled())
        self.assertEqual(d._preview_host._structure_interactive_axes,[])

    def test_sidecar_counts_require_matching_threshold_and_retained_cif(self):
        import json
        from phase_studio.result_selection import recorded_edma_site_lineage
        c=self.dialog.selected_candidate
        path=Path(c.structure_path)
        sidecar=path.with_name(path.stem+'_site_counts.json')
        data=dict(threshold_sigma=.5,raw_edma_sites=4,cif_sites=2,independent_asu_sites=2)
        sidecar.write_text(json.dumps(data),encoding='utf8')
        self.assertEqual(recorded_edma_site_lineage(c)['raw_edma_sites'],4)
        self.assertEqual(recorded_edma_site_lineage(replace(c,edma_sigma=.4)),{})
        data['cif_sites']=3;sidecar.write_text(json.dumps(data),encoding='utf8')
        self.assertEqual(recorded_edma_site_lineage(c),{})

    def test_combined_default_and_unmodified_pass_use_recommended_sharped(self):
        backend=self.backend
        backend.last_run_config.modelfile_source='none'
        backend._result_selection_session=None
        selected=[]
        def accept(dialog):
            self.assertEqual(dialog.active_source,'deblurred')
            candidate=dialog.selected_candidate
            self.assertEqual(candidate,dialog.active_recommendation.recommended_candidate)
            self.assertEqual(dialog.preview_candidate_id,candidate.candidate_id)
            self.assertIn('Structure prediction',dialog._selected_output_summary.text())
            self.assertIn(f'Cycle {candidate.cycle}',dialog._selected_output_summary.text())
            selected.append(candidate)
            return QDialog.Accepted
        with patch.object(engine.ResultSelectionDialog,'exec',accept), patch.object(backend,'_start_jana_handoff') as handoff:
            backend.open_result_selector('jana')
            self.assertEqual(handoff.call_args.args[2],selected[0])
            self.assertEqual(handoff.call_args.args[2].jana_model_sha256,selected[0].jana_model_sha256)

    def test_manual_selection_reopens_same_run_but_new_run_resets_default(self):
        backend=self.backend
        opened=[]
        def manual(dialog):
            dialog._superflip_btn.setChecked(True)
            dialog._views['superflip'].table.selectRow(0)
            opened.append(dialog.selected_candidate)
            return QDialog.Rejected
        with patch.object(engine.ResultSelectionDialog,'exec',manual):
            backend.open_result_selector('jana')
        def inspect(dialog):
            self.assertEqual(dialog.selected_candidate,opened[0])
            self.assertEqual(dialog.active_source,'superflip')
            return QDialog.Rejected
        with patch.object(engine.ResultSelectionDialog,'exec',inspect):
            backend.open_result_selector('jana')
        backend.last_run_config.run_id='new-run-default'
        def new_run(dialog):
            self.assertEqual(dialog.active_source,'deblurred')
            return QDialog.Rejected
        with patch.object(engine.ResultSelectionDialog,'exec',new_run):
            backend.open_result_selector('jana')

    def test_async_new_structure_hash_preserves_user_camera(self):
        d=self.dialog
        axis=d._preview_figure.axes[0]
        axis.set_xlim3d(-7,13)
        d._preview_camera_interaction('zoom')
        candidate=d.selected_candidate
        path=Path(candidate.structure_path).with_name('updated-generation.cif')
        path.write_bytes(Path(candidate.structure_path).read_bytes()+b'\n')
        path.with_suffix('.m40').write_bytes(Path(candidate.jana_model_path).read_bytes())
        d._render_preview(engine.seal_result_candidate(replace(candidate,structure_path=str(path),edma_sigma=.4)))
        self.events()
        self.assertEqual(d._preview_figure.axes[0].get_xlim3d(),(-7,13))

    def test_single_line_tabs_and_default_sigma(self):
        d=self.dialog
        self.assertEqual(d._sharped_btn.title_label.text(),'STRUCTURE PREDICTION')
        self.assertTrue(d._sharped_btn.subtitle_label.isHidden())
        self.assertEqual(engine.NORMAL_EDMA_THRESHOLD_SIGMA,.5)
        self.assertEqual(d.selected_candidate.edma_sigma,.5)

    def test_superflip_only_and_failed_sharped_fallback(self):
        backend=self.backend
        backend.results=[replace(r,deblur_map=Path(r.deblur_map).with_name('missing.xplor'),
                                 deblur_edma_cif=Path(r.deblur_edma_cif).with_name('missing.cif')) for r in backend.results]
        def inspect(dialog):
            self.assertEqual(dialog.active_source,'superflip')
            self.assertIn('No completed SharpED structure is available',dialog._warning_callout.text())
            self.assertTrue(dialog._action_button.isEnabled())
            return QDialog.Rejected
        backend._result_selection_session=None
        with patch.object(engine.ResultSelectionDialog,'exec',inspect):
            backend.open_result_selector('jana')

    def test_nonorthogonal_cell_fit_and_incomplete_model_guard(self):
        from mpl_toolkits.mplot3d import proj3d
        from phase_studio.result_selection import format_result_metric
        d=self.dialog
        candidate=d.selected_candidate
        path=Path(candidate.structure_path).with_name('nonorthogonal-preview.cif')
        text=Path(candidate.structure_path).read_text(encoding='utf8')
        text=text.replace('_cell_angle_beta 90','_cell_angle_beta 105').replace('_cell_angle_gamma 90','_cell_angle_gamma 73')
        path.write_text(text,encoding='utf8')
        d._view_mode='cell'
        d._render_preview(engine.seal_result_candidate(replace(candidate,structure_path=str(path))))
        self.events();d._request_preview_fit();d._preview_canvas.draw()
        axis=d._preview_figure.axes[0];points=d._preview_fit_coords
        x,y,_=proj3d.proj_transform(*points.T,axis.get_proj())
        pixels=axis.transData.transform(np.column_stack((x,y)))
        viewport=axis.get_position(original=True).transformed(axis.figure.transFigure)
        self.assertAlmostEqual(max(np.ptp(pixels,axis=0)/[viewport.width,viewport.height]),.78,places=5)
        self.assertEqual(format_result_metric(float('nan')),'n/a')
        self.assertEqual(format_result_metric(float('inf')),'n/a')
        view=d._views[d.active_source]
        view.selected=replace(candidate,jana_model_sha256='',usable_structure=False)
        d._sync_action_button()
        self.assertFalse(d._action_button.isEnabled())

    def test_fullscreen_cycle_title_tracks_actual_selected_atom_data(self):
        d=self.dialog
        d._apply_source('deblurred')
        view=d._views['deblurred']
        view.table.selectRow(1);self.events()
        selected=d.selected_candidate
        expected=d._candidate_presentation(selected)
        d._open_fullscreen();self.events()
        try:
            self.assertIs(d._detached_viewer._viewer,d._preview_section)
            self.assertEqual(d.preview_candidate_id,selected.candidate_id)
            self.assertTrue(np.array_equal(d._preview_fit_coords,expected[1]))
            from mpl_toolkits.mplot3d import proj3d
            d._preview_canvas.draw()
            axis=d._preview_figure.axes[0]
            x,y,_=proj3d.proj_transform(*d._preview_fit_coords.T,axis.get_proj())
            pixels=axis.transData.transform(np.column_stack((x,y)))
            viewport=axis.get_position(original=True).transformed(axis.figure.transFigure)
            self.assertTrue(np.all(pixels.min(axis=0)>[viewport.x0,viewport.y0]))
            self.assertTrue(np.all(pixels.max(axis=0)<[viewport.x1,viewport.y1]))
            view.table.selectRow(2);self.events()
            self.assertIn('Cycle 3',d._metadata_label.text())
            self.assertIn('Cycle 3',d._detached_viewer.title_label.text())
        finally:
            d._detached_viewer.close()

    def test_resolved_snapshot_and_artists_survive_identical_refresh(self):
        d=self.dialog;c=d.selected_candidate
        snapshot=d._resolved_preview
        artists=tuple(d._preview_figure.axes[0].collections)
        d._render_preview(c)
        self.assertIs(d._resolved_preview,snapshot)
        self.assertEqual(tuple(d._preview_figure.axes[0].collections),artists)
        self.assertEqual(snapshot.identity,d.selection_snapshot.identity)
        self.assertTrue(np.array_equal(np.asarray(snapshot.coordinates),d._candidate_presentation(c)[1]))
        with self.assertRaises(Exception):snapshot.composition='changed'

    def test_accept_freezes_candidate_despite_later_selection_signal(self):
        d=self.dialog;view=d._views[d.active_source]
        view.table.selectRow(1);self.events();chosen=d.selected_candidate
        d.accept();view.table.selectRow(2);self.events()
        self.assertEqual(d.selected_candidate,chosen)

    def test_fullscreen_two_families_three_cycles_thresholds_and_late_result(self):
        d=self.dialog;pending=[]
        def request(c,add,callback):
            r=SimpleNamespace(threshold=.4 if add else .5);pending.append((c,callback,r));return r
        d._adjust_threshold_async=request
        for source in ('superflip','deblurred'):
            d._apply_source(source);view=d._views[source]
            for row in (1,0,2):
                view.table.selectRow(row);self.events();c=d.selected_candidate
                d._open_fullscreen();self.events()
                try:
                    for add in (True,False):
                        d._change_threshold(add)
                        original,callback,r=pending[-1]
                        changed=engine.seal_result_candidate(replace(original,edma_sigma=r.threshold))
                        callback(changed,None,r);self.events()
                        self.assertEqual(d._resolved_preview.identity,d.selection_snapshot.identity)
                        self.assertEqual(d._detached_viewer.candidate_identity,d.selection_snapshot.identity)
                        expected=d._candidate_presentation(d.selected_candidate)
                        self.assertTrue(np.array_equal(np.asarray(d._resolved_preview.coordinates),expected[1]))
                        self.assertEqual(d._resolved_preview.detected_count,len(engine.parse_cif_atoms(Path(c.structure_path))))
                finally:d._detached_viewer.close()
            view.table.selectRow(2);d._change_threshold(True)
            original,callback,r=pending[-1]
            view.table.selectRow(1);self.events();selected=d.selected_candidate
            callback(engine.seal_result_candidate(replace(original,edma_sigma=r.threshold)),None,r)
            self.events()
            self.assertEqual(d.selected_candidate,selected)
            self.assertEqual(d._resolved_preview.identity,d.selection_snapshot.identity)

    def test_unready_scientific_winner_selects_best_ready_without_moving_star(self):
        backend=self.backend
        backend.results[-1].deblur_edma_cif=Path(backend.results[-1].deblur_edma_cif).with_name('unfinished.cif')
        def inspect(d):
            self.assertEqual(d.active_source,'deblurred')
            self.assertEqual(d.active_recommendation.recommended_candidate.cycle,3)
            self.assertEqual(d.selected_candidate.cycle,2)
            self.assertEqual(d.preview_candidate_id,d.selected_candidate.candidate_id)
            self.assertIn('not handoff-ready',d._selected_output_summary.text())
            self.assertTrue(d.selection_snapshot.ready)
            d._views['deblurred'].table.selectRow(2)
            self.assertFalse(d.selection_snapshot.ready)
            self.assertFalse(d._action_button.isEnabled())
            self.assertIn('No result is ready',d._selected_output_summary.text())
            return QDialog.Rejected
        with patch.object(engine.ResultSelectionDialog,'exec',inspect):
            backend.open_result_selector('jana')

    def test_metrics_only_rows_are_preserved_and_geometry_controls_disabled(self):
        backend=self.backend
        backend.results=[replace(r,superflip_map=Path(r.superflip_map).with_name('missing-sf.xplor'),
            deblur_map=Path(r.deblur_map).with_name('missing-ed.xplor')) for r in backend.results]
        self.assertEqual(engine.result_candidates_from_results(backend.results),[])
        def inspect(d):
            self.assertEqual(d._views['deblurred'].table.rowCount(),3)
            self.assertIsNotNone(d.selected_candidate.metrics.reference_f05)
            self.assertFalse(d.selection_snapshot.ready)
            self.assertEqual(d.preview_candidate_id,'')
            self.assertIn('No result is ready to pass to Jana2020',d._selected_output_summary.text())
            messages=[t.get_text() for t in d._preview_figure.texts]
            self.assertEqual(messages.count('No completed structure is available for this selection.'),1)
            self.assertNotIn('No completed structure',d._metadata_label.text())
            for b in (d._fit_button,d._fullscreen_button,d._add_atoms_button,d._remove_atoms_button,
                      d._molecule_button,d._cell_button,d._auto_rotate_button,d._action_button):
                self.assertFalse(b.isEnabled())
            self.assertIn('Map unavailable',d._views['deblurred'].table.item(0,1).toolTip())
            return QDialog.Rejected
        with patch.object(engine.ResultSelectionDialog,'exec',inspect):
            backend.open_result_selector('jana')

    def test_fallback_writing_distinguishes_first_open_from_return(self):
        backend=self.backend
        for result in backend.results:
            result.deblur_edma_cif=Path(result.deblur_edma_cif).with_name('missing-model.cif')
        def first(d):
            self.assertEqual(d.active_source,'superflip')
            self.assertIn('selected instead',d._warning_callout.text())
            self.assertTrue(d.selection_snapshot.ready)
            return QDialog.Rejected
        with patch.object(engine.ResultSelectionDialog,'exec',first):backend.open_result_selector('jana')
        def returned(d):
            self.assertIn('selected charge-flipping solution can be passed',d._warning_callout.text())
            self.assertNotIn('Select a completed',d._warning_callout.text())
            return QDialog.Rejected
        with patch.object(engine.ResultSelectionDialog,'exec',returned):backend.open_result_selector('jana')

    def test_wrong_threshold_and_cross_run_callbacks_are_rejected(self):
        d=self.dialog;pending=[]
        def request(c,add,callback):
            r=SimpleNamespace(threshold=.4);pending.append((c,callback,r));return r
        d._adjust_threshold_async=request
        for change in ({'edma_sigma':.3},{'run_id':'other-run','edma_sigma':.4}):
            original=d.selected_candidate
            d._change_threshold(True)
            c,callback,r=pending[-1]
            callback(replace(c,**change),None,r)
            self.assertEqual(d.selected_candidate,original)

    def test_table_is_authority_and_click_revalidates_changed_files(self):
        d=self.dialog;view=d._views[d.active_source]
        view.table.selectRow(0);self.events()
        c=d.selected_candidate
        self.assertEqual(d.selection_snapshot.identity,(c.run_id,c.source,c.cycle,c.candidate_id,
            c.map_sha256,c.edma_sigma,c.structure_sha256,c.jana_model_sha256))
        self.assertEqual(d.preview_candidate_id,c.candidate_id)
        Path(c.jana_model_path).write_bytes(Path(c.jana_model_path).read_bytes()+b'\n')
        d.accept()
        self.assertNotEqual(d.result(),QDialog.Accepted)
        self.assertFalse(d.selection_snapshot.ready)
        self.assertIn('identity changed',d._selected_output_summary.text())
        view.selected=None
        self.assertEqual(view.table.currentRow(),-1)
        self.assertIsNone(d.selected_candidate)

    def test_ui_unavailable_option_does_not_change_available_candidates_or_metrics(self):
        base=engine.result_candidates_from_results(self.backend.results)
        included=engine.result_candidates_from_results(self.backend.results,include_unavailable=True)
        self.assertEqual(base,included)
        self.assertEqual([c.metrics for c in base],[c.metrics for c in included])

    def test_stale_recommendation_selected_field_does_not_override_first_ready_ranking(self):
        from phase_studio.result_selection import _SourceView,result_selection_metric_columns
        d=self.dialog;original=d._views['deblurred']
        stale=original.recommendation.with_selected(original.ordered[0])
        view=_SourceView('deblurred',original.ordered,stale,
            result_selection_metric_columns(d._definition),False,'test',jana_context=True)
        self.assertEqual(view.selected,stale.recommended_candidate)
        self.assertEqual(view.table.currentRow(),2)
        view.container.deleteLater()

    def test_forced_accept_of_incomplete_row_never_starts_publication(self):
        backend=self.backend
        for r in backend.results:
            r.deblur_edma_cif=Path(r.deblur_edma_cif).with_name('no-completed-structure.cif')
            r.superflip_edma_cif=Path(r.superflip_edma_cif).with_name('no-completed-structure.cif')
        with patch.object(engine.ResultSelectionDialog,'exec',lambda d:QDialog.Accepted), patch.object(backend,'_start_jana_handoff') as publish:
            self.assertFalse(backend.open_result_selector('jana'))
            publish.assert_not_called()

class MetricTransparencyTests(unittest.TestCase):
    def test_imposed_amplitudes_cannot_validate_phases(self):
        good,amplitudes=synthetic_map()
        bad,_=synthetic_map(phases={h:.93*i*i for i,h in enumerate(HKLS)},amplitudes=amplitudes)
        context=context_for(amplitudes,free=HKLS[:3])
        first=compute_map_quality(good,GRID,CELL,'ZYX',context)
        second=compute_map_quality(bad,GRID,CELL,'ZYX',context)
        for metrics in (first,second):
            self.assertLess(metrics.amplitude_rf,1e-12)
            self.assertAlmostEqual(metrics.amplitude_cc,1,places=12)
        self.assertNotAlmostEqual(first.triplet_c3,second.triplet_c3,places=3)
    def test_amplitude_comparison_uses_frozen_measured_source(self):
        density,amplitudes=synthetic_map()
        context=context_for(amplitudes)
        changed=dict(amplitudes);changed[HKLS[0]]*=2
        adjusted,_=synthetic_map(amplitudes=changed)
        before=compute_map_quality(density,GRID,CELL,'ZYX',context)
        after=compute_map_quality(adjusted,GRID,CELL,'ZYX',context)
        self.assertLess(before.amplitude_rf,1e-12)
        self.assertGreater(after.amplitude_rf,.01)
        self.assertLess(after.amplitude_cc,.999)

if __name__=='__main__':unittest.main()
