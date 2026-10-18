"""Actual QtAgg drawing benchmark; controlled geometry and read-only local ochlor."""
import os, sys, time, json, tempfile, tracemalloc, hashlib
from pathlib import Path
from types import SimpleNamespace
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtCore import QSettings,QTimer
from phase_studio.fullscreen_viewer import SingleStructureViewerWindow
from phase_studio.autosolve_window import prepare_structure_presentation
from test_result_selection_viewer import cif_text,large_cif

qt=QApplication([])
out=ROOT/'build/acceptance-3d-viewer-2.0.5';out.mkdir(parents=True,exist_ok=True)
label=sys.argv[1] if len(sys.argv)>1 else 'after'
records=[]
with tempfile.TemporaryDirectory() as temporary:
    base=Path(temporary)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,temporary)
    sources={}
    for name,text in [('small',cif_text()),('sparse',large_cif(12)),('dense',large_cif(320)),('large',large_cif(1400))]:
        path=base/(name+'.cif');path.write_text(text,encoding='utf8');sources[name]=path
    real=ROOT/'build/workshop-ochlor/phase_studio_reference_for_metrics.cif'
    if real.is_file():sources['ochlor-existing-local']=real
    owner=QWidget();owner.show()
    for name,path in sources.items():
        for mode in ('molecule','cell'):
            before_hash=hashlib.sha256(path.read_bytes()).hexdigest()
            tracemalloc.start();start=time.perf_counter();cpu=time.process_time()
            data=prepare_structure_presentation(path,mode)
            construct=(time.perf_counter()-start)*1000
            window=SingleStructureViewerWindow(owner,'CONTROLLED BENCHMARK',lambda:data,color_for=lambda e:'#ce6677')
            window.resize(1200,800);window.show()
            for _ in range(10):qt.processEvents()
            window.canvas.draw();axis=window.figure.axes[0]
            artists=tuple(map(id,axis.collections))+tuple(map(id,axis.lines))
            times=[];dispatch=[];latency=[];draws=[]
            connection=window.canvas.mpl_connect('draw_event',lambda e:draws.append(time.perf_counter()))
            for index in range(20):
                frame=time.perf_counter()
                window._camera._press(SimpleNamespace(inaxes=axis,button=1,key='',x=600,y=350,dblclick=False))
                tick=time.perf_counter()
                for move in range(80):
                    window._camera._motion(SimpleNamespace(x=600+move*.25,y=350+np.sin(index*.2)*move*.1))
                dispatch.append((time.perf_counter()-tick)*1000)
                window._camera._release(None)
                window.canvas.draw()  # Real CPU projection/rasterization, not a timer-derived FPS.
                times.append((time.perf_counter()-frame)*1000)
                ready=[];tick=time.perf_counter();QTimer.singleShot(0,lambda:ready.append(time.perf_counter()))
                qt.processEvents();latency.append((ready[0]-tick)*1000)
            assert artists==tuple(map(id,axis.collections))+tuple(map(id,axis.lines))
            _current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            row=dict(scene=name,mode=mode,source_sha256=before_hash,atoms=len(data['atoms']),bonds=len(data.get('bonds',[])),cell_edges=len(data.get('cell_segments',[])),artists=len(artists),construction_ms=construct,median_frame_ms=float(np.median(times)),p95_frame_ms=float(np.percentile(times,95)),effective_fps=1000/float(np.mean(times)),median_dispatch_80_events_ms=float(np.median(dispatch)),event_loop_p95_ms=float(np.percentile(latency,95)),peak_python_bytes=peak,cpu_seconds=time.process_time()-cpu,draw_events=len(draws),backend=str(window.canvas.__class__.__name__),geometry_sha256=hashlib.sha256(np.asarray(data['coords']).tobytes()).hexdigest())
            tick=time.perf_counter();window.toggle_fullscreen();qt.processEvents();window.toggle_fullscreen();qt.processEvents();row['fullscreen_roundtrip_ms']=(time.perf_counter()-tick)*1000
            window.close();qt.processEvents()
            assert hashlib.sha256(path.read_bytes()).hexdigest()==before_hash
            records.append(row)
    owner.close()
(out/f'benchmark-{label}.json').write_text(json.dumps(records,indent=2),encoding='utf8')
print(label,len(records),'actual-draw benchmark scenes completed')
