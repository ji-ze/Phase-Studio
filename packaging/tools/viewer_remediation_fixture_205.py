"""Read-only stored ochlor candidates for viewer identity acceptance."""
import csv
from dataclasses import fields
from pathlib import Path
from phase_studio import app as engine,result_selection as ui
from phase_studio.map_quality import ResultCandidate,MapQualityMetrics,ValidationProfile,profile_definition,recommend_best_result

REAL_RUN=Path.home()/'Documents/ochlor/phase_studio_full_run_ochlor_Superflip/run_0010'


def real_candidates(run=REAL_RUN):
    rows=list(csv.DictReader((run/'metrics.csv').open(encoding='utf8')))
    result=[]
    metric_fields={field.name for field in fields(MapQualityMetrics)}
    for row in rows:
        if row['source'] not in ('superflip','sharped','deblurred'):continue
        source='superflip' if row['source']=='superflip' else 'deblurred'
        metrics={}
        for name in metric_fields:
            value=row.get(name,'')
            if not value:continue
            if name=='unavailable_reason':metrics[name]=value
            else:
                try:metrics[name]=int(value) if name.startswith('n_') else float(value)
                except ValueError:pass
        candidate=ResultCandidate(cycle=int(row['cycle']),source=source,
            map_path=row['map_path'],structure_path=row['structure_path'],metrics=MapQualityMetrics(**metrics),
            edma_sigma=.5,sharped_model='SEED (cyclic CF)' if source=='deblurred' else '',run_id=run.name)
        result.append(engine.seal_result_candidate(candidate))
    assert len(result)==6
    return result


def make_dialog(candidates):
    names=('_structure_cartesian_geometry','_element_color','_plot_structure_atoms','_update_structure_depth_artist',
        '_update_structure_depth_cue','_structure_axis_limits','_apply_structure_axis_limits','_begin_structure_view_drag',
        '_apply_structure_view','_sync_structure_view_from_event','_finish_structure_view_drag')
    Renderer=type('StoredCandidateRenderer',(),{name:getattr(engine.IterativeSuperflipPipelineQtGUI,name) for name in names})
    sf=[c for c in candidates if c.source=='superflip'];db=[c for c in candidates if c.source=='deblurred']
    profile=ValidationProfile.REFERENCE_FREE
    return ui.ResultSelectionDialog(None,sf,db,profile,profile_definition(profile),
        recommend_best_result(profile,sf),recommend_best_result(profile,db),
        superflip_tab_available=True,sharped_tab_available=True,initial_source='deblurred',
        map_feedback_intensity_enabled=False,jana_context=True,
        preview_host=ui.create_result_preview_host(Renderer(),None,20,35),parse_structure=engine.parse_cif_atoms,
        reference_atoms=[],source_title=engine.result_source_title)
