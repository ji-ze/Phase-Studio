"""Read-only observations of authoritative feedback stages; never changes values.

Intensity statistics use changed, finite, matched records. A change is meaningful
unless isclose(before, after, rel_tol=1e-12, abs_tol=1e-12). Relative changes use
only positive before intensities >1e-12. Legacy engine percentages remain separate.
"""
from contextvars import ContextVar
from pathlib import Path
import csv
import json
import math
import os
import statistics

_active = ContextVar('phase_feedback_observer', default=None)
OPERATIONS = ('missing', 'intensity', 'powder')
TITLES = {'missing':'Missing-reflection completion', 'intensity':'Intensity correction',
          'powder':'Powder overlap repartitioning'}


def record_feedback_observation(kind, state):
    observer = _active.get()
    if observer is not None:
        try:
            observer.observe(kind, state)
        except Exception as exc:
            observer.errors.append(f'{kind}: {type(exc).__name__}: {exc}')
            for name in (('intensity','missing') if kind=='map' else ('powder',)):
                if observer.operations[name]['status']!='Disabled':
                    observer.operations[name].update(status='Unavailable',reason='Diagnostic observation failed; scientific values were not changed.')


def _finite(value):
    return value is not None and math.isfinite(value)


def compare_stage(before, after, mode, *, eligible=None, groups=None):
    """Compare actual arrays using the existing authoritative intensity conversion."""
    from .app import reflection_value_as_intensity,reflection_mode_is_amplitude
    key = lambda r: (int(r.h), int(r.k), int(r.l))
    def intensity(r):
        value=float(r.value)
        if not math.isfinite(value):return None
        return reflection_value_as_intensity(r,mode) if reflection_mode_is_amplitude(mode) else value
    old = {key(r):intensity(r) for r in before}
    new = {key(r):intensity(r) for r in after}
    if len(old) != len(before) or len(new) != len(after):
        raise ValueError('Duplicate HKL records prevent an unambiguous feedback comparison.')
    rows = []
    changes = []
    percentages = []
    changed_keys = set()
    for hkl in sorted(old.keys() | new.keys()):
        b, a = old.get(hkl), new.get(hkl)
        finite = _finite(b) and _finite(a)
        delta = a-b if finite else None
        if delta is not None and not math.isfinite(delta):delta=None
        changed = finite and not math.isclose(b, a, rel_tol=1e-12, abs_tol=1e-12)
        percent = 100*(abs(delta)/b) if delta is not None and b>1e-12 else None
        if percent is not None and not math.isfinite(percent):percent=None
        if changed:
            changed_keys.add(hkl)
            if delta is not None:changes.append(abs(delta))
            if percent is not None: percentages.append(percent)
        rows.append(dict(h=hkl[0], k=hkl[1], l=hkl[2], before=b, after=a,
            delta=delta, absolute_delta=abs(delta) if delta is not None else None,
            relative_percent=percent, added=hkl not in old,
            eligible=hkl in eligible if eligible is not None else None,
            group=groups.get(hkl,0) if groups is not None else None))
    result = dict(input_reflections=len(before), eligible_reflections=len(eligible) if eligible is not None else None,
        modified_reflections=len(changed_keys),
        unchanged_eligible=len(eligible-changed_keys) if eligible is not None else None,
        added_reflections=len(new.keys()-old.keys()), removed_reflections=len(old.keys()-new.keys()),
        mean_absolute_delta=statistics.mean(changes) if changes else None,
        median_absolute_delta=statistics.median(changes) if changes else None,
        maximum_absolute_delta=max(changes) if changes else None,
        mean_absolute_relative_percent=statistics.mean(percentages) if percentages else None,
        relative_population=len(percentages), changed_population=len(changes), rows=rows)
    if groups is not None:
        group_ids = sorted(set(groups.values())-{0})
        errors=[]
        unavailable=0
        for gid in group_ids:
            keys={hkl for hkl,g in groups.items() if g==gid}
            if any(not _finite(old.get(hkl)) or not _finite(new.get(hkl)) for hkl in keys):
                unavailable+=1
                continue
            b=math.fsum(old[hkl] for hkl in keys);a=math.fsum(new[hkl] for hkl in keys)
            errors.append(dict(group=gid,before=b,after=a,error=a-b,
                conserved=math.isclose(b,a,rel_tol=1e-12,abs_tol=1e-9)))
        result.update(overlap_groups=len(group_ids), modified_groups=len({groups.get(hkl) for hkl in changed_keys if groups.get(hkl)}),
            conservation=all(g['conserved'] for g in errors) if not unavailable and errors else None,
            maximum_group_conservation_error=max((abs(g['error']) for g in errors),default=None),
            unavailable_conservation_groups=unavailable,group_conservation=errors)
    return result


class FeedbackCapture:
    def __init__(self, cycle, mode, reflections, cfg):
        self.cycle=cycle;self.mode=mode;self.cfg=cfg;self.errors=[]
        self.output_file=None;self.written_reflections=None
        self.operations={}
        for name,enabled,start in (
            ('missing',cfg.map_feedback_missing_enabled,cfg.map_feedback_missing_from_cycle),
            ('intensity',cfg.map_feedback_intensity_enabled,cfg.map_feedback_intensity_from_cycle),
            ('powder',cfg.redistribute_overlaps,cfg.powder_redistribution_from_cycle)):
            status,reason=('Disabled','Not selected') if not enabled else (
                ('Not yet reached',f'Starts after cycle {start}') if cycle<start else (
                ('Not eligible','No next-cycle input is required') if cycle>=cfg.cycles else
                ('Not eligible','No eligible stage was executed')))
            if enabled and cycle>=start and cycle<cfg.cycles:
                if name=='intensity' and cfg.map_feedback_intensity_damping<=0:
                    status,reason='No numerical change','Correction damping is zero'
                if name=='missing' and cfg.map_feedback_missing_percent_limit<=0:
                    reason='Addition limit is zero'
                if name=='powder' and cfg.powder_wavelength<=0:
                    reason='Measured wavelength is unavailable'
            self.operations[name]=dict(operation=name,status=status,reason=reason,input_reflections=len(reflections),rows=[])

    def __enter__(self):
        self.token=_active.set(self)
        return self

    def __exit__(self,*args):
        _active.reset(self.token)

    def _store(self,name,data,reason=''):
        data.update(operation=name,status='Applied' if data['modified_reflections'] or data['added_reflections'] else 'No numerical change',reason=reason)
        if name=='powder' and data.get('eligible_groups')==0:
            data.update(status='Not eligible',reason='No usable map predictions in detected groups; observed ratios retained.')
        if name=='intensity' and data.get('eligible_reflections')==0:
            data.update(status='Not eligible',reason='No reflections meet the significance and positive-map criteria.')
        if data.get('conservation') is False:
            data.update(status='Scientific error',reason='Group-wise intensity conservation failed; values were not repaired by diagnostics.')
        self.operations[name]=data

    def observe(self,kind,s):
        from .app import map_feedback_intensity_significance
        key=lambda r:(int(r.h),int(r.k),int(r.l))
        if kind=='map':
            before=s['reflections'];after=s.get('corrected_reflections',before)
            if s['correct_intensities'] and s['damping']>0:
                eligible={key(r) for r in before if s['predictions'].get(key(r),(0,0))[0]>0 and
                    (s['max_i_over_sigma']<=0 or ((sig:=map_feedback_intensity_significance(r,self.mode)) is not None and sig<s['max_i_over_sigma']))}
                data=compare_stage(before,after,self.mode,eligible=eligible)
                data['legacy_mean_percent']=s['avg_change_percent']
                data['map_path']=str(s['feedback_map'])
                data['parameters']=dict(damping=s['damping'],significance_limit=s['max_i_over_sigma'])
                data['significance_eligible']=sum(s['max_i_over_sigma']<=0 or ((sig:=map_feedback_intensity_significance(r,self.mode)) is not None and sig<s['max_i_over_sigma']) for r in before)
                self._store('intensity',data,'Eligible: significance rule and positive map prediction. Absolute statistics: changed finite matched records; relative: changed records with I before > 1e-12.')
            if s['add_missing'] and s['missing_percent_limit']>0:
                data=compare_stage(after,s['current'],self.mode)
                predictions=s.get('candidate_predictions')
                data['proposed_reflections']=sum(value[0]>0 for value in predictions.values()) if predictions is not None else None
                data['percentage_increase']=100*data['added_reflections']/len(after) if after else None
                self._store('missing',data,'No additions: no positive candidates or the integer addition cap is zero.' if not data['added_reflections'] else 'Percentage increase uses the reflection count immediately before completion.')
        else:
            groups=s['groups']
            if not groups:
                self.operations['powder'].update(reason='No valid FWHM overlap groups detected',overlap_groups=0,eligible_groups=0)
                return
            eligible=set()
            for members in s['by_group'].values():
                if sum(max(0.,s['predictions'].get(key(r),(0,0))[0]) for r in members)>1e-30:
                    eligible.update(key(r) for r in members)
            data=compare_stage(s['current'],s['updated'],self.mode,eligible=eligible,groups=groups)
            data['eligible_groups']=len(s['by_group'])-s['fallback_groups']
            data['legacy_mean_percent']=s['avg_change_percent']
            data['map_path']=str(s['feedback_map'])
            data['parameters']=dict(wavelength=s['wavelength'],separation_factor=s['separation_factor'],mix=s['mix'])
            self._store('powder',data,'Mix is zero.' if s['mix']==0 else 'Eligible groups have usable map signal. Statistics describe actual changed finite records; relative denominators require I before > 1e-12.')

    def report(self):
        return dict(schema=1,source_cycle=self.cycle,target_cycle=self.cycle+1 if self.cycle<self.cfg.cycles else None,
            next_cycle_reflection_file=self.output_file,written_reflections=self.written_reflections,
            data_mode=self.mode,operations=list(self.operations.values()),errors=self.errors,
            definitions='Counts and deltas describe each operation before reflection-file filtering. Written-reflection count and path identify the separately filtered next-cycle file. I before is the actual stage input, possibly derived from earlier cycles or preceding operations, not necessarily the original measurement. Changed: not isclose(rtol=1e-12, atol=1e-12). ΔI = I after − I before; amplitudes use the existing nonnegative intensity conversion. Absolute statistics: changed finite matched records. Relative: 100|ΔI|/I before, changed records with I before >1e-12. Overflow is unavailable. Conservation: per-group stage-input/output sums, rtol=1e-12, atol=1e-9; unavailable for nonfinite/missing members. Legacy intensity mean: corrected map-supported records with positive I before >1e-12, including unchanged records. Legacy powder mean: unweighted mean of group means of member |ΔI|/I before ×100 for members with I before >1e-12, including unchanged members; empty groups omitted.')


def _safe(value):
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,dict):return {k:_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [_safe(v) for v in value]
    return value


def save_report(directory, report):
    folder=Path(directory)/'feedback_diagnostics';folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'cycle_{report["source_cycle"]:04d}.json'
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(_safe(report),indent=2,allow_nan=False),encoding='utf8')
    os.replace(temporary,path)
    summary={k:v for k,v in report.items() if k!='operations'}
    summary['operations']=[{k:v for k,v in op.items() if k not in {'rows','group_conservation'}} for op in report['operations']]
    summary['detail_path']=str(path)
    return summary


def load_report(report):
    return json.loads(Path(report['detail_path']).read_text(encoding='utf8')) if 'detail_path' in report else report


def load_summaries(directory):
    summaries=[]
    for path in sorted((Path(directory)/'feedback_diagnostics').glob('cycle_*.json')):
        report=json.loads(path.read_text(encoding='utf8'))
        report['operations']=[{k:v for k,v in op.items() if k not in {'rows','group_conservation'}} for op in report['operations']]
        report['detail_path']=str(path);summaries.append(report)
    return summaries


def export_csv(path, report):
    fields=['h','k','l','before','after','delta','absolute_delta','relative_percent','eligible','group','added','operation','source_cycle','target_cycle']
    with Path(path).open('w',newline='',encoding='utf8') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for op in report['operations']:
            for row in op.get('rows',[]):
                writer.writerow(_safe(row)|dict(operation=op['operation'],source_cycle=report['source_cycle'],target_cycle=report['target_cycle']))
