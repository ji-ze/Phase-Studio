"""Offline, opt-in real-widget fixtures for functional GUI acceptance."""


def capture(main, directory, snap, rows, *, jana=False):
    import json
    from pathlib import Path
    import gemmi
    import numpy as np
    from . import app as a
    from .map_quality import (ResultCandidate, MapQualityMetrics, ValidationProfile,
                              profile_definition, recommend_best_result)
    from .result_selection import ResultSelectionDialog, create_result_preview_host
    from .recommendation_ui import RecommendationDialog
    from .run_log_viewer import RunLogViewer
    from .xplor_io import XplorMap, write_xplor_map

    folder = Path(directory) / 'controlled-partial-run'
    folder.mkdir(exist_ok=True)
    cif = folder / 'controlled.cif'
    cif.write_text("data_controlled\n_cell_length_a 10\n_cell_length_b 10\n_cell_length_c 10\n"
                   "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n"
                   "_space_group_name_H-M_alt 'P 1'\nloop_\n_atom_site_label\n_atom_site_type_symbol\n"
                   "_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\nC1 C .1 .1 .1\n", encoding='utf8')
    density = folder / 'controlled.xplor'
    write_xplor_map(density, XplorMap('Controlled UI fixture', (4,0,3,4,0,3,4,0,3),
                                    (10,10,10,90,90,90), 'ZYX', np.arange(64).reshape(4,4,4)/63))
    model = folder / 'controlled.m40'
    model.write_text('    1    0    0    0\nC1        1  1     1.000000 0.100000 0.100000 0.100000\n',encoding='utf8')
    assert a._m40_model_count(model) == 1
    candidates = [ResultCandidate(cycle=i, source='superflip', map_path=str(density),
                  structure_path=str(cif), metrics=MapQualityMetrics(amplitude_rf=value),
                  candidate_id='controlled-partial-'+str(i), edma_sigma=1.,
                  map_sha256=a.file_sha256(density),structure_sha256=a.file_sha256(cif),
                  jana_model_path=str(model),jana_model_sha256=a.file_sha256(model),jana_model_site_count=1,
                  unit_cell=(10,10,10,90,90,90), space_group='P 1', edma_asu_composition='C1')
                  for i,value in enumerate((.4,.3,.1,.2),1)]
    profile = ValidationProfile.REFERENCE_FREE
    recommendation = recommend_best_result(profile, candidates)
    assert recommendation.recommended_candidate.cycle == 3
    (folder/'run_manifest.json').write_text(json.dumps(dict(status='stopped', configured_cycles=5,
        completed_cycles=4, cycles={str(i):dict(status='completed') for i in range(1,5)})), encoding='utf8')
    events = [dict(timestamp='2026-11-10T11:00:00.123456+01:00', session_id='controlled',
              session_sequence=i, event_type='log', cycle=cycle, component=component, severity=severity,
              payload=dict(message=message, native_command=['superflip', 'controlled.inflip']))
              for i,(cycle,component,severity,message) in enumerate([
                  (None,'Application','INFO','Controlled offline fixture; no scientific execution'),
                  (3,'Superflip','SUCCESS','Candidate 3 completed'),
                  (4,'Application','WARNING','Stopped with four completed cycles out of five')])]
    (folder/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events), encoding='utf8')
    selector = ResultSelectionDialog(main,candidates,[],profile,profile_definition(profile),recommendation,
        recommend_best_result(profile,[]),superflip_tab_available=True,sharped_tab_available=False,
        initial_source='superflip',map_feedback_intensity_enabled=False,jana_context=jana,
        preview_host=create_result_preview_host(main,gemmi.UnitCell(10,10,10,90,90,90),30,-60),
        parse_structure=a.parse_cif_atoms,reference_atoms=[],source_title=lambda source:'Superflip',
        feedback_directory=folder)
    selector.show(); selector.resize(1150,700); snap('results-stopped-four-of-five',selector)
    assert selector.selected_candidate.cycle == 3 and selector._views['superflip'].table.rowCount() == 4
    assert selector._action_button.isEnabled()
    selector._content_scroll.ensureWidgetVisible(selector._preview_canvas,0,0)
    snap('results-preview-scrolled',selector)
    why = RecommendationDialog(selector,recommendation); why.show();snap('why-cycle-three',why)
    why.details.show();snap('why-cycle-full-precision',why);why.close()
    log = RunLogViewer(selector,folder);log.show();snap('execution-log-table',log)
    log.kind.setCurrentIndex(log.kind.findData('important'));snap('execution-log-important',log)
    log.raw_view.setChecked(True);snap('execution-log-original-payload',log);log.close();selector.close()
    rows['partial_results'] = dict(controlled_fixture=True,configured=5,completed=4,candidates=4,
                                   recommended_cycle=3,scientific_execution=False)
    # Reproduce the dense real-world count/layout distinction with synthetic
    # artifacts: a 70-site CIF preview and a one-site native EDMA selection.
    # These are intentionally distinct representations, not a rewritten model.
    from dataclasses import replace
    text=cif.read_text(encoding='utf8').split('C1 C .1 .1 .1')[0]
    text+=''.join(f'C{i+1} C {(.1+(i%5)*.16):.6f} {(.1+((i//5)%5)*.16):.6f} {(.1+(i//25)*.25):.6f}\n' for i in range(70))
    dense=folder/'controlled-70-sites.cif';dense.write_text(text,encoding='utf8')
    dense.with_suffix('.m40').write_bytes(model.read_bytes())
    dense_candidates=[a.seal_result_candidate(replace(c,structure_path=str(dense),structure_sha256='',
        jana_model_path='',jana_model_sha256='',jana_model_site_count=None,detected_atom_count=None,
        edma_asu_composition='C70',candidate_id='controlled-70-'+str(c.cycle))) for c in candidates]
    predicted=[replace(c,source='deblurred',sharped_model='PEAK A (controlled offline fixture)',
        candidate_id='controlled-sharped-70-'+str(c.cycle)) for c in dense_candidates]
    selector=ResultSelectionDialog(main,dense_candidates,predicted,profile,profile_definition(profile),
        recommend_best_result(profile,dense_candidates),recommend_best_result(profile,predicted),
        superflip_tab_available=True,sharped_tab_available=True,initial_source='deblurred',
        map_feedback_intensity_enabled=False,jana_context=jana,
        preview_host=create_result_preview_host(main,gemmi.UnitCell(10,10,10,90,90,90),30,-60),
        parse_structure=a.parse_cif_atoms,reference_atoms=[],source_title=lambda source:'Superflip' if source=='superflip' else 'SharpED')
    selector.show();selector.resize(1120,680);snap('results-70-cif-one-jana',selector)
    assert selector.selected_candidate.detected_atom_count==70 and selector.selected_candidate.jana_model_site_count==1
    assert selector._action_button.isEnabled()
    selector.showMaximized();snap('results-dense-maximized',selector);selector.showNormal();selector.resize(1120,680)
    for width,height in [(760,520),(1000,450)]:
        selector.resize(width,height);snap(f'results-dense-{width}x{height}',selector)
        selector._content_scroll.verticalScrollBar().setValue(selector._content_scroll.verticalScrollBar().maximum())
        snap(f'results-dense-{width}x{height}-scrolled',selector)
    selector._cell_button.click();snap('results-dense-full-cell',selector)
    selector._molecule_button.click();selector._request_preview_fit();snap('results-dense-fit',selector)
    selector._superflip_btn.click();snap('results-dense-charge-flipping',selector)
    assert selector.selected_candidate.source=='superflip'
    selector._sharped_btn.click();snap('results-dense-sharped',selector)
    assert selector.selected_candidate.source=='deblurred'
    selector.close()
    rows['count_distinction']=dict(controlled_fixture=True,cif_sites=70,native_edma_selected_sites=1,
                                  model_not_rewritten=True,scientific_execution=False)
