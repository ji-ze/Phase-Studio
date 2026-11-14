"""Read persisted feedback history for a candidate without changing its identity/rank."""
from pathlib import Path
from .feedback_diagnostics import load_report,load_summaries,TITLES

UNAVAILABLE='Detailed Map Feedback changes unavailable for this run.'


class FeedbackHistory:
    def __init__(self,directory=None,provider=None):
        self.directory=Path(directory) if directory is not None else None
        self.provider=provider
        self._stamp=None;self._reports=[];self.error=''

    def reports(self):
        try:
            paths=list((self.directory/'feedback_diagnostics').glob('*.json')) if self.directory else []
            stamp=tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in sorted(paths))
            if stamp!=self._stamp:
                self._reports=load_summaries(self.directory) if self.directory else []
                self._stamp=stamp
            reports={r['source_cycle']:r for r in self._reports}
            # Persisted records win: they are also used by completed-run review/exports.
            for r in self.provider() if self.provider else []:
                reports.setdefault(r['source_cycle'],r)
            self.error=''
            return list(reports.values())
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.error=str(exc)
            return []  # Never retain stale history after an unreadable replacement.

    def selected(self,cycle):
        return selected_input(self.reports(),cycle)


def selected_input(reports,cycle):
    """Only the step targeting N can explain input N; source N is a later step."""
    matches=[r for r in reports if r.get('target_cycle')==cycle and r.get('source_cycle')==cycle-1]
    step=matches[0] if len(matches)==1 else None
    current=next((r for r in reports if r.get('source_cycle')==cycle),None)
    input_data=step.get('target_input') if step else None
    current_input=current.get('cycle_input') if current else None
    mismatch=bool(input_data and current_input and input_data.get('sha256') and current_input.get('sha256')
                  and input_data['sha256']!=current_input['sha256'])
    if mismatch:step=None;input_data=current_input
    if input_data is None and current:input_data=current.get('cycle_input')
    if step is None:
        status='Original input' if cycle==1 and input_data and input_data.get('status')=='Available' else 'Unavailable'
    else:
        states={op['status'] for op in step['operations']}
        status=('Scientific error' if 'Scientific error' in states else
                'Unavailable' if 'Unavailable' in states else
                'Applied' if 'Applied' in states else
                'Disabled' if states=={'Disabled'} else
                'Not yet reached' if 'Not yet reached' in states else 'Unchanged')
    headline=(f'Map Feedback after cycle {cycle-1} → input for cycle {cycle}' if cycle>1
              else 'Input for cycle 1 · no preceding Map Feedback step')
    lines=[headline,f'Status: {status}. Cycle-level reflection lineage shared by Superflip and SharpED; SharpED consumes the Superflip map.']
    if step:
        if step.get('origin'):lines.append(step['origin'])
        for op in step['operations']:
            text=f'{TITLES[op["operation"]]}: {op["status"]}'
            if op.get('modified_reflections') is not None:
                text+=f'; modified {op["modified_reflections"]}/{op["input_reflections"]} feedback-stage input reflections (before file filtering)'
            if op.get('modified_groups') is not None:text+=f'; {op["modified_groups"]} modified groups'
            for key,label,unit in [('mean_absolute_delta','mean |ΔI|',' intensity units'),
                ('maximum_absolute_delta','max |ΔI|',' intensity units'),
                ('mean_absolute_relative_percent','mean absolute relative change','%'),
                ('maximum_absolute_relative_percent','max absolute relative change','%')]:
                value=op.get(key)
                if value is not None:text+=f'; {label} {value:.6g}{unit}'
            if op['operation']=='powder':
                conserved=op.get('conservation')
                text+='; group totals '+('conserved' if conserved is True else 'FAILED' if conserved is False else 'unavailable')
            lines.append(text)
    else:lines.append(UNAVAILABLE if status=='Unavailable' else 'No earlier feedback operation exists for the first cycle.')
    if mismatch:lines.append('Recorded preceding-step output does not match the actual cycle input hash. Step attribution unavailable.')
    if input_data:
        lines.append('Actual cycle input: '+str(input_data.get('file','unavailable')))
        if input_data.get('written_reflections') is not None:
            lines.append(f'Actual written cycle input: {input_data["written_reflections"]} reflections.')
        cumulative=input_data.get('cumulative')
        if cumulative:
            mean=cumulative.get('mean_absolute_relative_percent')
            lines.append(f'Cumulative vs original: {cumulative["modified_reflections"]} changed matched HKLs; '
                f'{cumulative["added_reflections"]} added, {cumulative["removed_reflections"]} absent; '
                + (f'mean absolute relative change {mean:.6g}%.' if mean is not None else 'relative mean unavailable.'))
        else:lines.append('Cumulative vs original: unavailable.')
        lines.append(input_data.get('reason',''))
    else:lines.append('Actual input file and cumulative difference vs original: unavailable.')
    written=step.get('written_input_difference') if step else None
    if written and written.get('status')=='Available':
        lines.append(f'Actual consecutive written inputs: {written["modified_reflections"]}/{written["input_reflections"]} changed matched reflections; '
                     f'{written["added_reflections"]} added, {written["removed_reflections"]} absent. '+written['reason'])
    lines.append(f'Changes after cycle {cycle} affect input {cycle+1}, not this result. Feedback magnitude is not a quality score. EDMA thresholds do not change this history.')
    return dict(status=status,headline=headline,text='\n'.join(lines),step=step,input=input_data)


def full_selected_report(summary):
    """Details/export always load the same persisted operation record."""
    return load_report(summary) if summary else None


def compact_summary(data):
    parts=[data['headline']+' · '+data['status']]
    metrics=[]
    for op in data['step']['operations'] if data['step'] else []:
        if op['status']=='Disabled':continue
        text=TITLES[op['operation']]+': '+op['status']
        if op.get('modified_reflections') is not None:text+=f' · {op["modified_reflections"]}/{op["input_reflections"]} stage reflections'
        if op.get('modified_groups') is not None:text+=f' · {op["modified_groups"]} groups'
        parts.append(text)
        mean=op.get('mean_absolute_relative_percent');maximum=op.get('maximum_absolute_relative_percent')
        if mean is not None:
            metrics.append(f'{op["operation"]} mean/max |ΔI|/I: {mean:.4g}% / '+(f'{maximum:.4g}%' if maximum is not None else 'unavailable'))
        if op['operation']=='powder' and op.get('conservation') is not None:
            metrics.append('group totals '+('conserved' if op['conservation'] else 'FAILED'))
    if not data['step']:parts.append(UNAVAILABLE if data['status']=='Unavailable' else 'Original measured input; no earlier feedback step.')
    cumulative=(data.get('input') or {}).get('cumulative')
    metrics.append(f'Cumulative: {cumulative["modified_reflections"]} changed HKLs' if cumulative else 'Cumulative unavailable')
    parts.append('; '.join(metrics))
    return '\n'.join(parts)
