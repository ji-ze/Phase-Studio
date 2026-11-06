"""Exercise the actual shared camera menu across comparison hosts."""
import sys,os,tempfile,json,hashlib
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from PySide6.QtWidgets import QApplication,QDialog,QToolButton,QFileDialog
from PySide6.QtCore import QSettings,QRect,Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtGui import QScreen
from phase_studio import app as a,structure_camera as camera
from phase_studio.autosolve_window import AutosolveWindow
from phase_studio.viewer_alignment import present_structure
from phase_studio import autosolve_review as guided
from test_viewer_alignment_207 import cif,BASE
import test_jana_completion as fixture

qt=QApplication([]);a.apply_phase_studio_style(qt);qt._phase_comparison_policy='independent'
def events():
    for _ in range(6):qt.processEvents()
def ordered(values):return sorted(map(tuple,np.round(np.asarray(values),7)))
with tempfile.TemporaryDirectory() as tmp,patch.multiple(a.IterativeSuperflipPipelineQtGUI,
     load_settings=lambda self:None,save_settings=lambda self:None,refresh_sharped_models=lambda self:None),patch.object(
     QScreen,'availableGeometry',return_value=QRect(0,0,1920,1140)):
    root=Path(tmp);settings=QSettings(str(root/'viewer.ini'),QSettings.IniFormat)
    with patch.object(camera,'QSettings',lambda *args:settings):
        reference=cif(root/'reference.cif',BASE)
        candidate=cif(root/'partial_edma.cif',BASE[[0,1,3,4]]+[2,-1,3])
        backend,results=fixture.build_window(a,cycles=3);backend.timer.stop()
        backend.structure_cell=a.parse_cif_cell_and_sg(reference)[0]
        backend.last_run_config.reference_cif=reference
        backend.results=[replace(r,superflip_edma_cif=candidate,deblur_edma_cif=candidate) for r in results]
        backend._structure_source_paths.update(reference=reference,superflip=candidate,deblur=candidate)
        for role,attr in [('reference','reference_atoms_for_plot'),('superflip','superflip_atoms_for_plot'),('deblur','deblur_atoms_for_plot')]:
            setattr(backend,attr,backend._classic_structure_atoms(backend._structure_source_paths[role]))
        backend._update_structure_views();backend.show();events()
        backend._open_classic_structure_fullscreen('superflip');single=backend._classic_detached_viewers['superflip']
        single._rotation_timer.stop()
        opened=[]
        with patch.object(a.ResultSelectionDialog,'exec',lambda dialog:opened.append(dialog) or QDialog.Rejected):
            backend.open_result_selector('standalone')
        selector=opened[0];selector._rotate_timer.stop();selector._auto_rotate_enabled=False;selector.show();events()
        execution=AutosolveWindow(backend,'A',workflow_name='Superflip + SharpED')
        execution._refresh_timer.stop();execution._rotate_timer.stop()
        candidates=backend._result_candidates()
        sf=next(c for c in candidates if c.source=='superflip' and c.cycle==3)
        sh=next(c for c in candidates if c.source!='superflip' and c.cycle==3)
        observed=backend._autosolve_panel_for_candidate(guided.ROLE_OBSERVED,sf)
        predicted=backend._autosolve_panel_for_candidate(guided.ROLE_PREDICTED,sh)
        execution._render_structures(observed,predicted);events()
        selected=selector.selected_candidate
        protected=[reference,candidate,*[r.superflip_map for r in results],*[r.deblur_map for r in results]]
        hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
        canvases=[backend.structure_canvas,execution.structure_canvas,single.canvas,selector._preview_canvas]
        # Send real Qt mouse gestures through every host's controller.
        for canvas in canvases:
            canvas.draw();axis=canvas.figure.axes[0]
            axis.view_init(23,41,roll=17);canvas.draw()
            box=axis.get_window_extent();ratio=canvas.device_pixel_ratio
            point=QPoint(int((box.x0+box.width*.4)/ratio),int((canvas.figure.bbox.height-box.y0-box.height*.5)/ratio))
            QTest.mousePress(canvas,Qt.LeftButton,Qt.NoModifier,point)
            for dx,dy in ((12,8),(27,19),(42,26)):
                QTest.mouseMove(canvas,point+QPoint(dx,dy),30);events()
            QTest.mouseRelease(canvas,Qt.LeftButton,Qt.NoModifier,point+QPoint(42,26));events()
            assert (axis.elev,axis.azim,axis.roll)!=(23,41,17),'Host ignored real Qt drag'
        for canvas in canvases:
            for axis in canvas.figure.axes:axis.view_init(27,61,roll=13)
        button=backend.findChild(QToolButton,'structureCameraMenu')
        frames=next(action.menu() for action in button.menu().actions() if action.text()=='Comparison frame')
        next(action for action in frames.actions() if action.data()=='reference').trigger();events()
        expected=present_structure(candidate,policy='reference',reference_path=reference,metric_cell=backend.structure_cell)
        assert len(expected['atoms'])==4 and expected['alignment']['matched_reference_sites']==4
        assert ordered(backend._structure_depth_artists[1].atom_coordinates)==ordered(expected['coords'])
        assert ordered(execution._structure_depth_artists[1].atom_coordinates)==ordered(expected['coords'])
        assert ordered(selector._preview_fit_coords)==ordered(expected['coords'])
        for canvas in canvases:
            for axis in canvas.figure.axes:
                assert (axis.elev,axis.azim,axis.roll)==(27,61,13),(axis.elev,axis.azim,axis.roll)
        for axis in backend._structure_interactive_axes[1:]:
            np.testing.assert_allclose(axis.get_xlim3d(),backend._structure_interactive_axes[0].get_xlim3d())
        assert selector.selected_candidate==selected
        output=root/'presentation.json'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(output),'')):
            next(action for action in frames.actions() if action.text().startswith('Export presentation')).trigger()
        record=json.loads(output.read_text());assert record['presentation_only'] and record['panels']
        assert all(data['sites'] for data in record['panels'].values())
        assert hashes=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
        out=ROOT/'build/alignment207/gui';out.mkdir(parents=True,exist_ok=True)
        backend.grab().save(str(out/'reference-aligned.png'));selector.grab().save(str(out/'selector-aligned.png'))
        for window in [single,selector,execution,backend]:window.close()
print('PASS shared frame, actual artists, reference matches, camera, provenance export and scientific byte invariance')
