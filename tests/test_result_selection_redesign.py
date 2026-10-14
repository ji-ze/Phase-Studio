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
        self.assertIn('EDMA candidate: 9 sites',d._metadata_label.text())
        self.assertIn('Jana model: 2 atomic sites',d._metadata_label.text())
        absent=replace(updated,jana_model_sha256='',jana_model_site_count=None)
        d._render_preview(absent)
        self.assertIn('prepared during handoff',d._metadata_label.text())
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
