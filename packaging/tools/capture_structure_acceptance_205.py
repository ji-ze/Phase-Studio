"""Actual offline Result Selection/3D windows; no scientific jobs or publication."""
import os,sys,tempfile,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QSettings,QEvent,QPoint,QRect
from PySide6.QtGui import QHelpEvent,QScreen
from PySide6.QtWidgets import QApplication,QLabel,QToolTip
from phase_studio import app as engine,result_selection as ui
from phase_studio.map_quality import MapQualityMetrics,ValidationProfile,profile_definition,recommend_best_result
from phase_studio.ui_style import apply_phase_studio_style
from test_result_selection_viewer import cif_text,large_cif
qt=QApplication([]);apply_phase_studio_style(qt)
OUT=ROOT/'build/acceptance-3d-viewer-2.0.5';OUT.mkdir(parents=True,exist_ok=True)
Renderer=type('FixtureRenderer',(),{name:getattr(engine.IterativeSuperflipPipelineQtGUI,name) for name in (
    '_structure_cartesian_geometry','_element_color','_plot_structure_atoms','_update_structure_depth_artist',
    '_update_structure_depth_cue','_structure_axis_limits','_apply_structure_axis_limits','_begin_structure_view_drag',
    '_apply_structure_view','_sync_structure_view_from_event','_finish_structure_view_drag')})
scale=float(os.environ.get('QT_SCALE_FACTOR','1'));records={}
def settle():
    for _ in range(30):qt.processEvents()
def snap(name,widget):
    settle();assert widget.grab().save(str(OUT/(name+'.png')))
    records[name]={'rect':widget.geometry().getRect(),'dpr':widget.devicePixelRatioF(),'fixture':'Existing CIF geometry or controlled model; synthetic candidate/map metadata; no publication'}
with tempfile.TemporaryDirectory() as temporary,patch.object(QScreen,'availableGeometry',return_value=QRect(0,0,1920,1080)):
    root=Path(temporary)
    factory=lambda *args:QSettings(str(root/'viewer.ini'),QSettings.IniFormat)
    ui.QSettings=factory
    from phase_studio import structure_camera
    structure_camera.QSettings=factory
    real=Path('C:/Users/honzi/Documents/ochlor/phase_studio_full_run_ochlor_Superflip/run_0009/cycle_003/edma_deblurred/cycle_003_deblurred_edma.cif')
    small=root/'ochlor.cif';small.write_bytes(real.read_bytes() if real.is_file() else cif_text().encode())
    boundary=root/'boundary.cif';boundary.write_text(cif_text('C2','C','C').replace('P -1','P 1').replace('0.10 0.10 0.10','.96 .1 .1').replace('0.20 0.10 0.10','.04 .1 .1'),encoding='utf8')
    large=root/'large.cif';large.write_text(large_cif(1400),encoding='utf8')
    def build(path):
        mp=root/'identity.xplor';mp.write_text('CONTROLLED MAP IDENTITY — NEVER HANDED OFF',encoding='utf8')
        results=[]
        for cycle,r in [(1,.45),(2,.40),(3,.44)]:
            quality=MapQualityMetrics(amplitude_rf=r,amplitude_cc=.61,triplet_c3=.28)
            results.append(engine.CycleResult(cycle=cycle,model_source='superflip',model_in=None,model_metric=None,
                superflip_map=mp,superflip_edma_cif=path,superflip_metric=None,deblur_map=mp,deblur_edma_cif=path,deblur_metric=None,
                superflip_quality=quality,deblur_quality=quality,superflip_edma_sigma=.5,deblur_edma_sigma=.5,
                sharped_model='SEED (cyclic CF)',run_id='controlled-viewer-fixture'))
        candidates=engine.result_candidates_from_results(results);sf=[c for c in candidates if c.source=='superflip'];db=[c for c in candidates if c.source=='deblurred']
        profile=ValidationProfile.REFERENCE_FREE
        dialog=ui.ResultSelectionDialog(None,sf,db,profile,profile_definition(profile),recommend_best_result(profile,sf),recommend_best_result(profile,db),
            superflip_tab_available=True,sharped_tab_available=True,initial_source='deblurred',map_feedback_intensity_enabled=False,jana_context=True,
            preview_host=ui.create_result_preview_host(Renderer(),None,20,35),parse_structure=engine.parse_cif_atoms,reference_atoms=[],source_title=engine.result_source_title,
            adjust_threshold_async=lambda *args:SimpleNamespace(threshold=.4))
        marker=QLabel('CONTROLLED VIEWER FIXTURE — SYNTHETIC CANDIDATE/MAP METADATA — NO JANA PUBLICATION')
        marker.setWordWrap(True);marker.setStyleSheet('color:#52658b; font-size:8pt;')
        dialog._preview_section.layout().insertWidget(0,marker)
        dialog._auto_rotate_button.setChecked(False);dialog.show();dialog.resize(1480,930);settle();dialog._request_preview_fit();settle()
        return dialog
    dialog=build(small)
    if scale!=1:
        snap('09-selection-dpi-125' if scale==1.25 else '10-selection-dpi-150',dialog)
    else:
        snap('01-structure-prediction',dialog)
        dialog._apply_source('superflip');settle();snap('02-charge-flipping',dialog)
        table=dialog._views['superflip'].table;header=table.horizontalHeader()
        pos=QPoint(header.sectionViewportPosition(3)+4,header.height()//2)
        event=QHelpEvent(QEvent.ToolTip,pos,header.mapToGlobal(pos));header.viewportEvent(event);settle()
        tip=next((w for w in qt.topLevelWidgets() if w.objectName()=='qtooltip_label'),None)
        if tip is not None:
            assert tip.width()<=table.width()
            snap('03-compact-metric-tooltip',tip)
        else:snap('03-metric-header',dialog)
        QToolTip.hideText()
        dialog._apply_source('deblurred');dialog._open_fullscreen();settle()
        detached=dialog._detached_viewer;detached.resize(1480,930);settle();snap('04-fullscreen-molecules',detached)
        dialog._set_view_mode('cell');settle();snap('05-fullscreen-cell',detached)
        detached.close();dialog.close()
        dialog=build(boundary);snap('06-boundary-crossing-molecule',dialog);dialog.close()
        dialog=build(large);dialog._set_view_mode('cell');settle();snap('07-large-full-cell',dialog);dialog.close()
        dialog=build(small);dialog._change_threshold(True);settle();assert not dialog._action_button.isEnabled()
        snap('08-threshold-pending',dialog)
    dialog.close();settle()
(OUT/f'capture-geometry-{scale}.json').write_text(json.dumps(records,indent=2),encoding='utf8')
print('Actual 3D viewer acceptance captures completed at',scale)
