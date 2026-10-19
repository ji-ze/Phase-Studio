"""Actual QtAgg frame timings, same scientific geometry, before/after UI only."""
import os,sys,json,time,tempfile,platform,importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
label=sys.argv[1] if len(sys.argv)>1 else 'after'
if label=='before':
    import phase_studio
    for name in ('structure_camera','fullscreen_viewer','autosolve_window','result_selection'):
        spec=importlib.util.spec_from_file_location('phase_studio.'+name,ROOT/'build/viewer-remediation-205-before'/(name+'.py'))
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);setattr(phase_studio,name,module)
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from phase_studio import structure_camera as camera,result_selection as ui
from phase_studio.map_quality import ResultCandidate,MapQualityMetrics
from viewer_remediation_fixture_205 import make_dialog,real_candidates
from test_result_selection_viewer import large_cif
qt=QApplication([])
OUT=ROOT/'build/acceptance-viewer-remediation-2.0.5';OUT.mkdir(exist_ok=True,parents=True)
records=[]
def settle():
    for _ in range(5):qt.processEvents()
with tempfile.TemporaryDirectory() as temporary:
    base=Path(temporary);settings=QSettings(str(base/'camera.ini'),QSettings.IniFormat)
    ui.QSettings=lambda *args:settings;camera.QSettings=lambda *args:settings
    cases={'ochlor-cycle2':[c for c in real_candidates() if c.source=='deblurred' and c.cycle==2][0]}
    for name,count in (('dense',320),('large',1400)):
        path=base/(name+'.cif');path.write_text(large_cif(count),encoding='utf8')
        mp=base/(name+'.xplor');mp.write_text('Controlled rendering-only identity, never handed off',encoding='utf8')
        from phase_studio import app as engine
        cases[name]=engine.seal_result_candidate(ResultCandidate(1,'deblurred',str(mp),str(path),MapQualityMetrics(),edma_sigma=.5,run_id='benchmark-fixture'))
    for scene,candidate in cases.items():
        d=make_dialog([candidate]);d._auto_rotate_button.setChecked(False);d._rotate_timer.stop();d.resize(1200,850);d.show();d.activateWindow();settle()
        for mode in ('molecule','cell'):
            d._set_view_mode(mode);settle()
            for host in ('main','fullscreen'):
                if host=='fullscreen':
                    d._open_fullscreen();d._detached_viewer.showNormal();d._detached_viewer.resize(1200,850);settle()
                axis=d._preview_figure.axes[0];canvas=d._preview_canvas;canvas.draw()
                atom_count=len(d._candidate_presentation(candidate)[0]);coords=d._candidate_presentation(candidate)[1]
                import hashlib
                digest=hashlib.sha256(np.asarray(coords).tobytes()).hexdigest()
                for motion in ('manual','automatic'):
                    elapsed=[];artists=tuple(map(id,axis.collections))
                    with patch.object(d._camera,'allow_auto_rotation',return_value=True):
                        for index in range(12):
                            start=time.perf_counter()
                            if motion=='manual':
                                x,y=canvas.width()/2,canvas.height()/2
                                d._camera._press(SimpleNamespace(inaxes=axis,button=1,key='',x=x,y=y,dblclick=False))
                                for step in range(40):d._camera._motion(SimpleNamespace(x=x+step*.3,y=y+step*.1))
                                d._camera._release(None)
                            else:
                                d._auto_rotate_enabled=True;d._auto_rotate_tick()
                            canvas.draw();elapsed.append((time.perf_counter()-start)*1000)
                    assert tuple(map(id,axis.collections))==artists
                    records.append(dict(scene=scene,representation=mode,host=host,motion=motion,atoms=atom_count,
                        coordinate_sha256=digest,mean_frame_ms=float(np.mean(elapsed)),p95_frame_ms=float(np.percentile(elapsed,95))))
                    d._auto_rotate_enabled=False;d._rotate_timer.stop()
                before=tuple(map(id,axis.collections));elapsed=[]
                for _ in range(10):
                    start=time.perf_counter();d._render_preview(candidate);elapsed.append((time.perf_counter()-start)*1000)
                records[-1]['identical_refresh_mean_ms']=float(np.mean(elapsed))
                records[-1]['identical_refresh_reuses_artists']=before==tuple(map(id,d._preview_figure.axes[0].collections))
                if host=='fullscreen':d._detached_viewer.close();settle()
        d.close();settle()
result=dict(label=label,hardware=platform.processor() or os.environ.get('PROCESSOR_IDENTIFIER','unknown'),os=platform.platform(),
    renderer='Matplotlib QtAgg CPU projection and rasterization; no physical GPU/FPS claim',frames=records)
(OUT/('benchmark-'+label+'.json')).write_text(json.dumps(result,indent=2),encoding='utf8')
print('PASS',label,len(records),'actual main/fullscreen manual/automatic frame cases',flush=True)
