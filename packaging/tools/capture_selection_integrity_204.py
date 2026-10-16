"""Real Qt state captures: explicit synthetic fixtures and existing ochlor outputs.
No inference or publication; threshold callbacks are simulated using already
completed, numerically audited real EDMA generations from audit_selection_handoff_204.
"""
import csv
import json
import os
import sys
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QDialog
from phase_studio import app as engine
from phase_studio.map_quality import MapQualityMetrics,ResultCandidate,ValidationProfile,profile_definition,recommend_best_result
from phase_studio.result_selection import create_result_preview_host
from test_result_selection_redesign import ResultSelectionRedesignTests

ResultSelectionRedesignTests.setUpClass()
fixture=ResultSelectionRedesignTests('test_family_selection_warning_and_authoritative_model_count')
fixture.setUp(); d=fixture.dialog; backend=fixture.backend
out=ROOT/'docs/screenshots/2.0.4-selection-integrity'/('scale-'+os.environ.get('QT_SCALE_FACTOR','1'))
out.mkdir(parents=True,exist_ok=True)


def capture(name,synthetic=True,width=1500,height=900):
    d.resize(width,height); fixture.events(); d._request_preview_fit(); d._preview_canvas.draw();fixture.events()
    snapshot=d.selection_snapshot;c=snapshot.candidate
    if snapshot.geometry:
        assert d.preview_candidate_id==c.candidate_id
        assert d._views[d.active_source].current_row_candidate()==c
    assert d._footer.geometry().bottom()<d.height()
    if snapshot.ready:assert f'Cycle {c.cycle}' in d._selected_output_summary.text()
    pixmap=d.grab();pixmap.save(str(out/(name+'.png')))
    (out/(name+'.json')).write_text(json.dumps(dict(synthetic=synthetic,real_jana_gui_acceptance=False,
        logical_size=[d.width(),d.height()],dpr=pixmap.devicePixelRatio(),source=d.active_source,
        selected_cycle=c.cycle if c else None,recommended_cycle=d.active_recommendation.recommended_candidate.cycle if d.active_recommendation.recommended_candidate else None,
        row=d._views[d.active_source].table.currentRow(),identity=snapshot.identity,ready=snapshot.ready,
        geometry=snapshot.geometry,pending=snapshot.pending,reason=snapshot.reason,
        preview_id=d.preview_candidate_id,summary=d._selected_output_summary.text(),
        edma_sites=c.detected_atom_count if c else None,jana_sites=c.jana_model_site_count if c else None),indent=2),encoding='utf8')


def reopen():
    global d
    d.close()
    opened=[]
    with patch.object(engine.ResultSelectionDialog,'exec',lambda dialog:opened.append(dialog) or QDialog.Rejected):
        backend.open_result_selector('jana')
    d=opened[0];fixture.dialog=d
    d._rotate_timer.stop();d._auto_rotate_button.setChecked(False);d.show();fixture.events()


try:
    capture('01-first-opening-recommended-cycle-3')
    d._views['deblurred'].table.selectRow(0);capture('02-manual-cycle-1-star-stays-3')
    d._superflip_btn.setChecked(True);capture('03-manual-superflip')
    d._sharped_btn.setChecked(True);capture('04-return-to-manual-sharped-cycle-1')
    original_results=backend.results
    backend.results=[replace(r,deblur_edma_cif=Path(r.deblur_edma_cif).with_name('unavailable.cif')) for r in original_results]
    backend._result_selection_session=None;reopen();capture('05-automatic-superflip-fallback')
    reopen();capture('06-already-selected-superflip-neutral-message')
    backend.results=[replace(r,superflip_map=Path(r.superflip_map).with_name('missing-sf.xplor'),
        deblur_map=Path(r.deblur_map).with_name('missing-sharped.xplor')) for r in original_results]
    backend._result_selection_session=None;reopen();capture('07-metrics-only-no-map-no-handoff')
    backend.results=[replace(r,superflip_edma_cif=Path(r.superflip_edma_cif).with_name('missing-sf.cif'),
        deblur_edma_cif=Path(r.deblur_edma_cif).with_name('missing-sharped.cif')) for r in original_results]
    backend._result_selection_session=None;reopen();capture('08-maps-without-edma-structures')
    backend.results=list(original_results)
    backend.results[-1]=replace(original_results[-1],deblur_edma_cif=Path(original_results[-1].deblur_edma_cif).with_name('unfinished.cif'))
    backend._result_selection_session=None;reopen();capture('09-scientific-winner-unready-select-ready-cycle-2')

    root=ROOT/'build/selection-integrity-real'
    old=ROOT/'build/oauth-2.0.4-ochlor-run/calculation/run_0001'
    if (root/'acceptance.json').is_file():
        candidates={'superflip':[],'deblurred':[]}
        for row in csv.DictReader((old/'metrics.csv').open(encoding='utf8')):
            metrics={}
            for field in fields(MapQualityMetrics):
                value=row.get(field.name,'')
                if value:metrics[field.name]=value if field.name=='unavailable_reason' else int(value) if field.name.startswith('n_') else float(value)
            source='superflip' if row['source']=='superflip' else 'deblurred'
            path=Path(row['structure_path'])
            if int(row['cycle'])==3:path=root/f'{source}-3-0.50/edma/selected_edma.cif'
            c=engine.seal_result_candidate(ResultCandidate(int(row['cycle']),source,row['map_path'],str(path),
                MapQualityMetrics(**metrics),edma_sigma=.5,run_id='selection-integrity-real',
                reflection_input_provenance='Existing measured-map metrics; historical provenance not revalidated'))
            candidates[source].append(c)
        d.close()
        cell,_,_=engine.parse_cif_cell_and_sg(Path(candidates['deblurred'][-1].structure_path))
        profile=ValidationProfile.REFERENCE_FREE
        d=engine.ResultSelectionDialog(backend,candidates['superflip'],candidates['deblurred'],profile,
            profile_definition(profile),recommend_best_result(profile,candidates['superflip']),recommend_best_result(profile,candidates['deblurred']),
            superflip_tab_available=True,sharped_tab_available=True,initial_source='deblurred',
            map_feedback_intensity_enabled=False,jana_context=True,preview_host=create_result_preview_host(backend,cell,20.,35.),
            parse_structure=backend._safe_parse_structure,reference_atoms=[],source_title=engine.result_source_title)
        fixture.dialog=d;d._rotate_timer.stop();d._auto_rotate_button.setChecked(False);d.show();fixture.events()
        capture('10-ochlor-real-completed-050sigma',False)
        pending=[]
        def request(c,add,callback):
            r=SimpleNamespace(threshold=.4);pending.append((c,callback,r));return r
        d._adjust_threshold_async=request;d._change_threshold(True);capture('11-ochlor-edma-pending-last-completed-retained',False)
        original,callback,request=pending[-1]
        updated=engine.seal_result_candidate(replace(original,edma_sigma=.4,structure_path=str(root/'deblurred-3-0.40/edma/selected_edma.cif')))
        callback(updated,None,request);capture('12-ochlor-completed-040sigma-model-count-distinct',False)
        capture('13-final-selected-summary',False)
        capture('14-reduced-height',False,1100,640)
finally:
    fixture.tearDown();ResultSelectionRedesignTests.tearDownClass()
