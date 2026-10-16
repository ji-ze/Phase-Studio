"""Compare real input and validated report fields across the presentation adapter."""
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from phase_studio import app as a
from phase_studio.hkl_diagnostics import cached_analysis,export_shell_csv
from phase_studio.hkl_diagnostics_ui import presentation_report

out=ROOT/'build/hkl-presentation'
out.mkdir(parents=True,exist_ok=True)
baseline=json.loads((ROOT/'build/hkl-modernization/real-acceptance.json').read_text())
checks={}
for name,path in [('ochlor',Path('C:/Users/honzi/Documents/ochlor/ochlor_Superflip.inflip')),
                  ('2int3total',Path('C:/Users/honzi/Documents/flipovani-phase-studio/2int3total.inflip'))]:
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    before=sha(path)
    request=a.build_hkl_analysis_request_from_inflip(path,work_dir=out/name)
    analysis=cached_analysis(request)
    original=asdict(analysis.diagnostics)
    then=time.perf_counter();displayed=presentation_report(analysis);elapsed=time.perf_counter()-then
    assert asdict(analysis.diagnostics)==original
    assert analysis.d_min==baseline[name]['after_d_min']
    assert analysis.d_full_98==baseline[name]['after_d98']
    assert before==sha(path)==baseline[name]['sha256_after']
    for old,new in zip(analysis.diagnostics.shells,displayed.shells):
        assert all(dict(new)[key]==value for key,value in old)
    displayed.export_json(out/(name+'-presentation.json'),analysis)
    export_shell_csv(out/(name+'-presentation.csv'),displayed)
    checks[name]=dict(parsed_records=len(analysis.reflections_raw),d_min=analysis.d_min,d98=analysis.d_full_98,
        validated_report_unchanged=True,input_sha256=before,presentation_seconds=elapsed,
        mean_F_over_sigma=displayed.statistic('mean_f_over_sigma'),median_F_over_sigma=displayed.statistic('median_f_over_sigma'),
        existing_derived_mean=displayed.statistic('mean_significance'),existing_derived_median=displayed.statistic('median_significance'))
    print(name,json.dumps(checks[name]),flush=True)
engine=ROOT/'phase_studio/hkl_diagnostics.py'
assert engine.read_bytes()==(out/'engine_before.py').read_bytes()
checks['engine_sha256']=hashlib.sha256(engine.read_bytes()).hexdigest()
(out/'real-acceptance.json').write_text(json.dumps(checks,indent=2),encoding='utf8')
