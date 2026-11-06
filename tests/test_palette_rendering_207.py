"""Actual menu changes must recolor persistent scatters in every viewer."""
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def test_palette_artists_and_camera():
    result=subprocess.run([sys.executable,__file__,'--child'],cwd=ROOT,
        env=os.environ|{'QT_QPA_PLATFORM':'offscreen','PHASE_STUDIO_STARTUP_PROBE':'1'},capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr


def exercise():
    sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
    import tempfile
    from unittest.mock import patch
    import numpy as np
    from PySide6.QtCore import QSettings,QRect
    from PySide6.QtGui import QScreen
    from PySide6.QtWidgets import QApplication,QDialog,QToolButton
    from phase_studio import app as a,structure_camera as camera
    import test_jana_completion as fixture
    qt=QApplication([]);a.apply_phase_studio_style(qt);qt._phase_color_palette='phase'
    with tempfile.TemporaryDirectory() as tmp,patch.object(a.IterativeSuperflipPipelineQtGUI,'refresh_sharped_models',lambda self:None),patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,1920,1140)):
        settings=QSettings(str(Path(tmp)/'camera.ini'),QSettings.IniFormat)
        with patch.object(camera,'QSettings',lambda *args:settings):
            win,results=fixture.build_window(a,launch_mode='standalone',cycles=2);win.timer.stop()
            win.results=results
            win._structure_source_paths.update(reference=results[0].superflip_edma_cif,
                superflip=results[-1].superflip_edma_cif,deblur=results[-1].deblur_edma_cif)
            atoms=[a.AtomSite(e+str(i),e,np.array([.1+i*.1,.1,.1])) for i,e in enumerate(['C','N','O','S'])]
            win.reference_atoms_for_plot=list(atoms);win.superflip_atoms_for_plot=list(atoms);win.deblur_atoms_for_plot=list(atoms)
            win._update_structure_views();win.resize(1920,1140);win.show();qt.processEvents()
            fullscreen=[]
            for role in ('reference','superflip','deblur'):
                win._open_classic_structure_fullscreen(role)
                fullscreen.append(win._classic_detached_viewers[role])
            opened=[]
            win._show_error_report=lambda report: (_ for _ in ()).throw(AssertionError(str(report)))
            with patch.object(a.ResultSelectionDialog,'exec',lambda dialog:opened.append(dialog) or QDialog.Rejected):win.open_result_selector('standalone')
            selector=opened[0];selector.show()
            for _ in range(8):qt.processEvents()
            from types import SimpleNamespace
            from phase_studio import autosolve_window as aw
            execution=aw.AutosolveWindow(win,'A')
            execution._refresh_timer.stop();execution._rotate_timer.stop();execution._structure_fit_timer.stop()
            execution.structure_cell=win.structure_cell
            execution.structure_figure.clear();execution._structure_depth_artists.clear()
            execution._secondary_depth_artists.clear();execution._structure_interactive_axes.clear()
            coords=np.array([[0.,0,0],[1.,0,0],[2.,0,0],[3.,0,0]])
            view=SimpleNamespace(atoms=atoms,coords=coords,fit_center=np.array([1.5,0,0]),fit_radius=2.,
                secondary_atoms=atoms,secondary_coords=coords+.2,bonds=[])
            for index in range(3):
                axis=execution.structure_figure.add_subplot(1,3,index+1,projection='3d')
                if index==0:execution._plot_full_cell_panel(axis,atoms,'')
                else:
                    with patch.object(aw,'SHOW_SECONDARY_PEAKS_IN_MOLECULE_VIEW',True):
                        execution._plot_molecule_panel(axis,view,'')
            canvases=[win.structure_canvas,execution.structure_canvas]+[w.canvas for w in fullscreen]+[selector._preview_canvas]
            def artists(canvas):return [s for axis in canvas.figure.axes for s in axis.collections if getattr(s,'_phase_elements',())]
            assert len(artists(canvases[0]))==3
            assert len(artists(canvases[1]))==5  # Full cell, two molecular panels and two secondary layers.
            assert all(artists(canvas) for canvas in canvases)
            def state():
                return [(id(axis),axis.elev,axis.azim,axis.roll,axis.get_xlim3d(),axis.get_ylim3d(),axis.get_zlim3d()) for canvas in canvases for axis in canvas.figure.axes]
            for canvas in canvases:
                for axis in canvas.figure.axes:axis.view_init(27,61,roll=13)
                canvas.draw()
            snapshot=state();identities=[id(s) for c in canvases for s in artists(c)]
            before=[s.get_facecolors().copy() for c in canvases for s in artists(c)]
            button=win.findChild(QToolButton,'structureCameraMenu')
            palettes=next(action.menu() for action in button.menu().actions() if action.text()=='Element colors')
            win._run_status='RUNNING'  # Controlled active-run state; no external job.
            next(action for action in palettes.actions() if 'CPK' in action.text()).trigger()
            for canvas in canvases:canvas.draw()
            after=[s.get_facecolors().copy() for c in canvases for s in artists(c)]
            assert len(before)==len(after) and all(not np.array_equal(x,y) for x,y in zip(before,after))
            assert state()==snapshot and identities==[id(s) for c in canvases for s in artists(c)]
            for depth in win._structure_depth_artists:
                from matplotlib.colors import to_rgb
                np.testing.assert_allclose(depth.atom_base_colors,[to_rgb(a.element_color(e)) for e in depth.scatter._phase_elements])
            camera.camera_settings_button(win)  # Another menu must not reset application state.
            assert qt._phase_color_palette=='cpk' and settings.value('viewer/elementPalette')=='cpk'
            next(action for action in palettes.actions() if 'Current' in action.text()).trigger()
            for canvas in canvases:canvas.draw()
            assert state()==snapshot
            next(action for action in palettes.actions() if 'CPK' in action.text()).trigger()
            win._update_structure_views()  # New result arrives while CPK is selected.
            assert all(np.allclose(d.atom_base_colors,[to_rgb(a.element_color(e)) for e in d.scatter._phase_elements]) for d in win._structure_depth_artists)
            restarted=subprocess.run([sys.executable,__file__,'--restart',str(Path(tmp)/'camera.ini')],cwd=ROOT,
                env=os.environ|{'QT_QPA_PLATFORM':'offscreen'},capture_output=True,text=True,timeout=30)
            assert restarted.returncode==0,restarted.stdout+restarted.stderr
            selector.close()
            execution.close()
            for window in fullscreen:window.close()
            win.close()


def restarted_palette():
    sys.path.insert(0,str(ROOT))
    import numpy as np
    from types import SimpleNamespace
    from unittest.mock import patch
    from matplotlib.colors import to_rgba
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication,QWidget
    from phase_studio import app as a,structure_camera as camera
    from phase_studio.fullscreen_viewer import SingleStructureViewerWindow
    qt=QApplication([]);settings=QSettings(sys.argv[2],QSettings.IniFormat)
    data={'atoms':[SimpleNamespace(element=e,label=e) for e in ('C','N','O','S')],
        'coords':np.array([[0.,0,0],[1.,0,0],[0,1.,0],[0,0,1.]]),'bonds':[]}
    with patch.object(camera,'QSettings',lambda *args:settings):
        owner=QWidget();window=SingleStructureViewerWindow(owner,'Restart fixture',lambda:data,color_for=a.element_color)
        assert qt._phase_color_palette=='cpk'
        scatter=next(s for axis in window.figure.axes for s in axis.collections if getattr(s,'_phase_elements',()))
        np.testing.assert_allclose(scatter._facecolors,[to_rgba(a.element_color(e)) for e in ('C','N','O','S')])
        window.close();owner.close()


if __name__=='__main__':
    restarted_palette() if '--restart' in sys.argv else exercise()
