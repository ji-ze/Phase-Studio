"""Read-only review of the existing persisted run model and event stream."""
from pathlib import Path
import json


def workflow_status_text(manifest):
    if not manifest:return 'Persisted workflow state unavailable.'
    status = manifest.get('status', 'unavailable')
    count = manifest.get('completed_cycles')
    completed = int(count) if isinstance(count,(int,float)) and count>=0 else 'unavailable'
    planned = manifest.get('configured_cycles')
    planned = planned if planned is not None else 'unavailable'
    available = ('Completed-result count unavailable.' if completed=='unavailable' else f'Results from {completed} completed cycle(s) are available.' if completed else 'No completed results are recorded.')
    if status == 'stopped':
        return f'Stopped by user after cycle {completed} of {planned}. {available}'
    if status in ('stopping_after_current_cycle', 'stop_requested'):
        return f'Stop requested; finishing the current cycle. {completed} of {planned} cycles completed.'
    if status in ('prepared','running','resuming'):
        return f'Last persisted status: {status} ? {completed} of {planned} cycles completed. Current process liveness and a terminal outcome are not verified by this saved record.'
    if status == 'cancelling':
        return f'Immediate cancellation requested; stopping unfinished work. {available}'
    labels = dict(completed='Completed normally', cancelled='Cancelled immediately', failed='Failed', interrupted='Interrupted unexpectedly')
    return f'{labels.get(status, status)} · {completed} of {planned} cycles completed. {available}'


class PersistedRunReview:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.manifest = {}
        self.records = []
        self.incomplete_records = 0
        self.reload()

    def reload(self):
        try:
            self.manifest = json.loads((self.directory/'run_manifest.json').read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            self.manifest = {}
        self.records = []
        self.incomplete_records = 0
        try:
            lines = (self.directory/'events.jsonl').read_bytes().splitlines()
        except OSError:
            lines = []
        for line in lines:
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    self.records.append(event)
                else:self.incomplete_records += 1
            except ValueError:
                self.incomplete_records += 1

    @staticmethod
    def family(event):
        payload = event.get('payload') or {}
        declared = payload.get('family') or payload.get('source')
        if declared in ('superflip', 'deblurred', 'sharped'):
            return 'deblurred' if declared == 'sharped' else declared
        component = str(event.get('component', '')).casefold()
        if component in ('superflip', 'sharped'):
            return 'superflip' if component == 'superflip' else 'deblurred'
        # Unknown family stays unknown; GUI selection never fabricates history.
        return None

    def events(self, *, cycle=None, family=None, kind='all', search=''):
        result = []
        for event in self.records:
            if cycle is not None and event.get('cycle') != cycle:
                continue
            if family and self.family(event) != family:
                continue
            payload = event.get('payload') or {}
            category = payload.get('category', '')
            if kind == 'important' and event.get('severity') not in ('STEP','SUCCESS','WARNING','ERROR','CRITICAL') and category != 'SCIENTIFIC_RESULT':
                continue
            if kind == 'warnings' and event.get('severity') not in ('WARNING', 'ERROR', 'CRITICAL'):
                continue
            if kind == 'scientific' and category != 'SCIENTIFIC_RESULT' and event.get('component') not in ('Validation', 'Map Feedback', 'Results', 'EDMA'):
                continue
            if search.casefold() not in json.dumps(event, ensure_ascii=False).casefold():
                continue
            result.append(event)
        return result

    def original_log(self):
        for name in ('diagnostic.log', 'log.txt'):
            path = self.directory/name
            if path.is_file():
                return path
        return None

    def export_sanitized(self, destination):
        from .run_provenance import export_persisted_diagnostics
        export_persisted_diagnostics(self.directory, destination)


def recommendation_details(recommendation):
    from .map_quality import profile_definition
    definition = profile_definition(recommendation.profile)
    candidate = recommendation.recommended_candidate
    lines = [recommendation.reason, 'Ranking within this result family, in order:']
    for index, metric in enumerate(definition.primary_metrics, 1):
        value = candidate.metrics.value(metric.key) if candidate else None
        lines.append(f'{index}. {metric.label}: {value if value is not None else "Unavailable"} ({"higher" if metric.higher_is_better else "lower"} is better).')
    lines.append('Later metrics break ties only (tolerance 1e-12); unavailable tie-breakers are skipped. Remaining ties prefer complete artifacts, then the earliest cycle. This view does not rerank candidates.')
    if 'reference' in definition.profile.value:
        lines.append('Reference-dependent assessment is not independent validation. A recommendation does not certify a crystal structure.')
    return '\n'.join(lines)


def uncertainty_description(mode):
    from . import app as a
    if a.reflection_mode_has_fwhm(mode):
        return 'FWHM is measured peak width, not sigma(I) or sigma(F).'
    if mode == a.REFLECTION_DATA_MODE_AMPLITUDE_DUMMY_SIGMA:
        return 'Amplitude with auxiliary/dummy column. Genuine experimental sigma(F) provenance is unavailable; a populated fifth column is not proof of measured uncertainty.'
    if mode == a.REFLECTION_DATA_MODE_AMPLITUDE_MEASURED_SIGMA:
        return 'Explicitly declared measured σ(F). Direct F/σ(F) and the documented first-order derived intensity significance are distinct.'
    if mode in (a.REFLECTION_DATA_MODE_INTENSITY, a.REFLECTION_DATA_MODE_INTENSITY_PHASE_SIGMA):
        return 'Declared sigma(I) input. Experimental origin must be established from the input provenance, not from the presence of a numeric column.'
    if mode == a.REFLECTION_DATA_MODE_FOBS_ZERO_PHASE_SIGMA:
        return 'Declared sigma(F) input with phases. Experimental origin must be established from the input provenance.'
    return 'Uncertainty provenance unavailable.'


def disabled_feedback_summary(manifest, record):
    cfg = manifest.get('effective_config') or {}
    keys = ('map_feedback_missing_enabled', 'map_feedback_intensity_enabled', 'redistribute_overlaps')
    if not all(key in cfg for key in keys) or any(cfg.get(key) for key in keys):
        return None
    inventory = manifest.get('reflection_inventory') or {}
    original = (inventory.get('actual_input') or {}).get('sha256')
    consumed = (record.get('reflection_input') or {}).get('sha256')
    if original and original == consumed and inventory.get('absent_from_written') == 0 and inventory.get('duplicates_merged') == 0 and inventory.get('parser_rejections') == 0:
        return 'Map Feedback: Disabled. Original measured reflection input retained.'
    return 'Map Feedback: Disabled. Retention of the complete original reflection population is not established by the available provenance.'


def candidate_transfer_rows(candidate, cfg=None, destination=None, *, jana=False):
    from . import app as a
    rows = [('Selected cycle', candidate.cycle), ('Result family', candidate.source),
        ('Map source', candidate.map_path), ('Structure source', candidate.structure_path),
        ('Model source', candidate.jana_model_path or 'Unavailable'),
        ('EDMA threshold', candidate.edma_sigma if candidate.edma_sigma is not None else 'Unavailable'),
        ('Reflection input', candidate.reflection_input_provenance or 'Unavailable'),
        ('Map SHA-256', candidate.map_sha256 or 'Unavailable'),
        ('Structure SHA-256', candidate.structure_sha256 or 'Unavailable')]
    manifest = PersistedRunReview(cfg.work_dir).manifest if cfg else {}
    record = (manifest.get('cycles') or {}).get(str(candidate.cycle), {})
    mode = record.get('reflection_mode') or ((manifest.get('reflection_inventory') or {}).get('filter_rules') or {}).get('data_mode')
    rows += [('Uncertainty interpretation', uncertainty_description(mode)),
        ('Map Feedback', disabled_feedback_summary(manifest, record) or 'See the persisted cycle N-1 -> N operation history; no unavailable change is interpreted as zero.')]
    if jana and cfg and cfg.jana_inflip:
        path = Path(cfg.jana_inflip)
        try:
            lines = path.read_text(encoding='utf8').splitlines()
            density = a._jana_protocol_output_paths(lines, path.parent)
            base = a._jana_protocol_keyword_path(lines, path.parent, 'outputbase')
            model = a._jana_protocol_keyword_path(lines, path.parent, 'writem40')
            map_target = path.parent/(f'{path.stem}-phase-studio-superflip-cycle_{candidate.cycle:03d}.xplor' if candidate.source == 'superflip' else f'{path.stem}-deb.xplor')
            targets = [map_target, *density, *([base.with_suffix('.m40'), base.with_suffix('.m50')] if base else []), *([model] if model else [])]
            rows += [('Actual destination', str(path.parent)), ('Intended Jana files', '\n'.join(map(str, dict.fromkeys(targets)))),
                ('Formats', 'XPLOR density; Jana m80/m81 density and m40/m50 model/context as declared by the input protocol.'),
                ('Outcome', 'Passing files to Jana2020 does not establish successful refinement.')]
        except (OSError, ValueError, RuntimeError) as exc:
            rows += [('Destination protocol', 'Unavailable: '+str(exc))]
    else:
        names = [Path(candidate.map_path).name]
        if candidate.usable_structure:
            names.append(Path(candidate.structure_path).name)
        rows += [('Actual destination', str(destination) if destination else 'Choose the destination after Save; review the exact path before confirming export.'),
            ('Intended output filenames', '\n'.join(names)), ('Formats', ', '.join(Path(name).suffix for name in names))]
    return rows
