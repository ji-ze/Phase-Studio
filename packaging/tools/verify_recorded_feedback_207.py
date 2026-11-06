"""Local verification only: replay saved maps; no phasing or inference jobs."""
import sys,json,csv,hashlib,math,argparse
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from phase_studio import app as a
from phase_studio.hkl_diagnostics import read_diagnostic_reflections
from phase_studio.feedback_diagnostics import FeedbackCapture,save_report,save_original_reflections,input_comparison,written_input_difference
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('run',type=Path)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--wavelength',type=float,required=True)
parser.add_argument('--cycles',type=int,required=True)
parser.add_argument('--start',type=int,required=True)
parser.add_argument('--separation',type=float,required=True)
parser.add_argument('--mix',type=float,required=True)
args=parser.parse_args();root=args.run.resolve();out=args.output.resolve()
if out==root or root in out.parents:parser.error('Output must be outside the recorded run.')
if args.wavelength<=0 or args.cycles<2 or not 1<=args.start<args.cycles:
 parser.error('Require positive wavelength, at least two cycles and a feedback start before the last cycle.')
out.mkdir(parents=True,exist_ok=True)
mode=a.REFLECTION_DATA_MODE_INTENSITY_FWHM
input_path=root/'cycle_001_superflip_embedded_reflections.hkl'
rows=list(read_diagnostic_reflections(input_path,mode)[0])
save_original_reflections(out,rows,mode)
cell=a.parse_cif_cell_and_sg(root/'phase_studio_reference_for_metrics.cif')[0]
cfg=SimpleNamespace(cycles=args.cycles,map_feedback_missing_enabled=False,map_feedback_missing_from_cycle=1,
 map_feedback_missing_percent_limit=0,map_feedback_intensity_enabled=False,map_feedback_intensity_from_cycle=1,
 map_feedback_intensity_damping=0,redistribute_overlaps=True,powder_redistribution_from_cycle=args.start,powder_wavelength=args.wavelength)
recorded=list(csv.DictReader((root/'metrics.csv').open()))
evidence=[]
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [input_path,root/'metrics.csv',root/'phase_studio_reference_for_metrics.cif']}
for cycle in range(1,args.cycles):
 current_input=(root/f'cycle_{cycle:03d}_map_feedback_for_superflip.hkl') if cycle>args.start else root/'observed_unique_for_superflip.hkl'
 with FeedbackCapture(cycle,mode,rows,cfg) as capture:
  if cycle>=args.start:
   path=root/f'cycle_{cycle:03d}'/f'cycle_{cycle:03d}_deblurred.xplor'
   hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
   after,legacy=a.redistribute_overlap_reflections(rows,mode,path,cell,args.wavelength,args.separation,args.mix,lambda _:None)
   actual=root/f'cycle_{cycle+1:03d}_map_feedback_for_superflip.hkl'
   hashes[str(actual)]=hashlib.sha256(actual.read_bytes()).hexdigest()
   saved=read_diagnostic_reflections(actual,mode)[0]
   capture.output_file=str(actual);capture.written_reflections=len(saved)
   report=capture.report();powder=report['operations'][2]
   lookup={(r.h,r.k,r.l):r.value for r in after}
   discrepancies=[abs(r.value-lookup[(r.h,r.k,r.l)]) for r in saved if (r.h,r.k,r.l) in lookup]
   max_error=max(discrepancies,default=None)
   independent={}
   for row in powder['rows']:
    if row['group']:
     pair=independent.setdefault(row['group'],[[],[]]);pair[0].append(row['before']);pair[1].append(row['after'])
   conservation=[abs(math.fsum(aft)-math.fsum(bef)) for bef,aft in independent.values()]
   assert powder['conservation'] is True
   assert all(math.isclose(math.fsum(bef),math.fsum(aft),rel_tol=1e-12,abs_tol=1e-9)
              for bef,aft in independent.values())
   old_metric=next((float(r['powder_repartition_avg_change_percent']) for r in recorded if int(r['cycle'])==cycle+1 and r.get('powder_repartition_avg_change_percent')),None)
   item=dict(source_cycle=cycle,target_cycle=cycle+1,full_input=len(rows),persisted_records=len(saved),
     matched_records=len(discrepancies),maximum_persisted_error=max_error,legacy_replayed=legacy,
     legacy_recorded=old_metric,maximum_group_error=max(conservation,default=None),modified=powder['modified_reflections'])
   evidence.append(item);print(json.dumps(item),flush=True)
   # Persisted files use 7 decimal places. Missing/filtered records are not invented.
   assert len(discrepancies)==len(saved) and max_error<=5.1e-8,item
   assert all(value<=1e-8 for value in conservation),item
   if old_metric is not None:assert math.isclose(old_metric,legacy,rel_tol=1e-10,abs_tol=1e-10),item
   rows=after
  else:report=capture.report()
 report['cycle_input']=input_comparison(out,current_input,mode)
 report['target_input']=input_comparison(out,actual if cycle>=args.start else current_input,mode)
 report['written_input_difference']=written_input_difference(current_input,actual if cycle>=args.start else current_input,mode)
 report['origin']='Reconstructed using existing recorded maps; verified against persisted reflection values. Not newly captured historical in-memory arrays.'
 report['definitions']=report['origin']+' '+report['definitions']
 save_report(out,report)
for name,digest in hashes.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest
(out/'verification.json').write_text(json.dumps(evidence,indent=2))
(out/'unchanged-input-hashes.json').write_text(json.dumps(hashes,indent=2))
