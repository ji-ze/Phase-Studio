"""Real ResultSelection QtAgg workload; optional original module for paired baseline."""
import os,sys,time,json,importlib.util,tempfile,hashlib
from pathlib import Path
from dataclasses import replace
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from phase_studio import app as engine
from phase_studio import result_selection as current
from phase_studio.map_quality import MapQualityMetrics,ValidationProfile,profile_definition,recommend_best_result
from test_result_selection_viewer import large_cif,cif_text
from phase_studio.ui_style import apply_phase_studio_style
label=sys.argv[1] if len(sys.argv)>1 else 'after'
OUT=ROOT/'build/acceptance-3d-viewer-2.0.5';OUT.mkdir(parents=True,exist_ok=True)
module=current
if label=='before':
    spec=importlib.util.spec_from_file_location('phase_studio._baseline_selection',OUT/'result_selection.before.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
qt=QApplication([]);apply_phase_studio_style(qt)
Renderer=type('FixtureRenderer',(),{name:getattr(engine.IterativeSuperflipPipelineQtGUI,name) for name in (
    '_structure_cartesian_geometry','_element_color','_plot_structure_atoms','_update_structure_depth_artist',
    '_update_structure_depth_cue','_structure_axis_limits','_apply_structure_axis_limits','_begin_structure_view_drag',
    '_apply_structure_view','_sync_structure_view_from_event','_finish_structure_view_drag')})
records=[]
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary);QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,temporary)
    sources={}
    for name,text in [('small',cif_text()),('dense',large_cif(320)),('large',large_cif(1400))]:
        path=root/(name+'.cif');path.write_text(text,encoding='utf8');sources[name]=path
    real=Path('C:/Users/honzi/Documents/ochlor/phase_studio_full_run_ochlor_Superflip/run_0009/cycle_003/edma_deblurred/cycle_003_deblurred_edma.cif')
    if real.is_file():sources['ochlor-real-edma']=real
    for name,path in sources.items():
        original=hashlib.sha256(path.read_bytes()).hexdigest()
        mp=root/'identity.xplor';mp.write_text('CONTROLLED MAP IDENTITY ONLY; NO HANDOFF')
        result=engine.CycleResult(cycle=2,model_source='none',model_in=None,model_metric=None,
            superflip_map=mp,superflip_edma_cif=path,superflip_metric=None,deblur_map=mp,deblur_edma_cif=path,deblur_metric=None,
            superflip_quality=MapQualityMetrics(),deblur_quality=MapQualityMetrics(),superflip_edma_sigma=.5,deblur_edma_sigma=.5,run_id='offline-benchmark')
        all_candidates=engine.result_candidates_from_results([result]);sf=[c for c in all_candidates if c.source=='superflip'];db=[c for c in all_candidates if c.source=='deblurred']
        profile=ValidationProfile.REFERENCE_FREE
        dialog=module.ResultSelectionDialog(None,sf,db,profile,profile_definition(profile),recommend_best_result(profile,sf),recommend_best_result(profile,db),
            superflip_tab_available=True,sharped_tab_available=True,initial_source='deblurred',map_feedback_intensity_enabled=False,jana_context=False,
            preview_host=module.create_result_preview_host(Renderer(),None,20,35),parse_structure=lambda p:engine.parse_cif_atoms(p),reference_atoms=[],source_title=engine.result_source_title)
        dialog._rotate_timer.stop();dialog.show();dialog.activateWindow();dialog.resize(1400,900)
        for mode in ('molecule','cell'):
            start=time.perf_counter();dialog._set_view_mode(mode)
            for _ in range(8):qt.processEvents()
            dialog._preview_canvas.draw();construction=(time.perf_counter()-start)*1000
            atoms,coords,bonds,formula,detected,fit,edges=dialog._candidate_presentation(dialog.selected_candidate)
            axis=dialog._preview_host._structure_interactive_axes[0]
            if not len(atoms):continue
            artists=tuple(map(id,axis.collections));frames=[];latencies=[];cpu=time.process_time();start=time.perf_counter()
            dialog._auto_rotate_enabled=True
            if hasattr(dialog._camera,'_last_input'):dialog._camera._last_input=-float('inf')
            for index in range(40):
                dialog._preview_host.structure_azim=35+index*.4
                frame=time.perf_counter();dialog._auto_rotate_tick();dialog._preview_canvas.draw();frames.append((time.perf_counter()-frame)*1000)
            elapsed=time.perf_counter()-start
            assert artists==tuple(map(id,axis.collections))
            records.append(dict(scene=name,mode=mode,atoms=len(atoms),bonds=len(bonds),cell_edges=len(edges),artists=len(artists),construction_ms=construction,
                median_frame_ms=float(np.median(frames)),p95_frame_ms=float(np.percentile(frames,95)),effective_fps=40/elapsed,cpu_one_core_percent=(time.process_time()-cpu)/elapsed*100,
                source_sha256=original,geometry_sha256=hashlib.sha256(np.asarray(coords).tobytes()).hexdigest(),backend='Matplotlib QtAgg CPU',frames=40))
        dialog.close();dialog.deleteLater();qt.processEvents()
        assert hashlib.sha256(path.read_bytes()).hexdigest()==original
(OUT/f'selection-benchmark-{label}.json').write_text(json.dumps(records,indent=2),encoding='utf8')
print(label,len(records),'real-draw Result Selection scene/mode measurements')
