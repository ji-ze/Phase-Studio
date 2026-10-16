"""Read-only real-project numerical, cache and worker responsiveness audit."""
import os
import sys
from pathlib import Path
import hashlib
import json
import threading
import time
import types

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from phase_studio import app as a
from phase_studio import hkl_diagnostics as d

out=ROOT/'build/hkl-modernization'
out.mkdir(parents=True,exist_ok=True)
qt=QApplication([])
baseline=types.ModuleType('phase_studio._hkl_before')
baseline.__file__=a.__file__
sys.modules[baseline.__name__]=baseline
exec(compile((out/'app_before.py').read_bytes(),a.__file__,'exec'),baseline.__dict__)
records={}


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


for name,path in [('ochlor',Path('C:/Users/honzi/Documents/ochlor/ochlor_Superflip.inflip')),
                  ('2int3total',Path('C:/Users/honzi/Documents/flipovani-phase-studio/2int3total.inflip'))]:
    original=digest(path)
    request=a.build_hkl_analysis_request_from_inflip(path,work_dir=out/name)
    ticks=[]
    timer=QTimer();timer.setInterval(25);timer.timeout.connect(lambda:ticks.append(time.perf_counter()));timer.start()
    box={}
    def work():
        try:
            t=time.perf_counter()
            load=a.build_hkl_load_result(request)
            box['load_seconds']=time.perf_counter()-t
            info_before=d._read_cached.cache_info()
            t=time.perf_counter()
            analysis=d.cached_analysis(request)
            box['analysis_seconds']=time.perf_counter()-t
            box['read_cache_misses_before_analysis']=info_before.misses
            box['read_cache_misses_after_analysis']=d._read_cached.cache_info().misses
            t=time.perf_counter();again=d.cached_analysis(request)
            box['cached_analysis_seconds']=time.perf_counter()-t
            box['same_cached_analysis']=again is analysis
            box['analysis']=analysis
        except BaseException as exc:box['error']=exc
    worker=threading.Thread(target=work)
    began=time.perf_counter();worker.start()
    while worker.is_alive():qt.processEvents();worker.join(.005)
    qt.processEvents();timer.stop()
    if 'error' in box:raise box['error']
    box['wall_seconds']=time.perf_counter()-began
    box['qt_heartbeat_count']=len(ticks)
    box['maximum_heartbeat_gap_seconds']=max([b-a0 for a0,b in zip(ticks,ticks[1:])],default=0)
    analysis=box.pop('analysis')
    before=baseline.analyze_hkl_data(analysis.hkl_path,analysis.data_mode,analysis.cell,analysis.spacegroup,analysis.spacegroup_hm,analysis.source_note)
    box['parsed_records']=len(analysis.reflections_raw)
    box['literal_unique']=len(analysis.reflections_unique)
    box['spacegroup']=analysis.spacegroup.xhm()
    box['data_mode']=analysis.data_mode
    box['before_d_min']=before.d_min;box['after_d_min']=analysis.d_min
    box['before_d98']=before.d_full_98;box['after_d98']=analysis.d_full_98
    assert before.d_min==analysis.d_min
    box['nonempty_shell_counts_and_coverage_identical']=all(
        old['observed']==new['observed'] and old['theory']==new['theory'] and
        (not old['theory'] or old['completeness']==new['completeness']) for old,new in zip(before.bins,analysis.bins))
    box['shell_differences']=[dict(shell=i,before=old,after=new) for i,(old,new) in enumerate(zip(before.bins,analysis.bins))
                            if old['observed']!=new['observed'] or old['theory']!=new['theory']]
    box['undefined_shells_changed_zero_to_na']=sum(not b['theory'] for b in analysis.bins)
    box['overall_input_orbits']=sum(b['observed'] for b in analysis.bins)
    box['overall_allowed_orbits']=sum(b['theory'] for b in analysis.bins)
    box['sha256_before']=original;box['sha256_after']=digest(path)
    assert box['sha256_before']==box['sha256_after']
    box['raw_values_identical']=all((x.h,x.k,x.l,x.value,x.sigma,x.phase)==(y.h,y.k,y.l,y.value,y.sigma,y.phase) for x,y in zip(before.reflections_raw,analysis.reflections_raw))
    assert box['raw_values_identical']
    analysis.diagnostics.export_json(out/(name+'-diagnostics.json'),analysis)
    d.export_shell_csv(out/(name+'-shells.csv'),analysis.diagnostics)
    records[name]=box
    print(name,json.dumps(box),flush=True)
    del before,analysis
(out/'real-acceptance.json').write_text(json.dumps(records,indent=2),encoding='utf8')
