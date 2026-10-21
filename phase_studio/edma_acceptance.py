"""Opt-in saved-map/native EDMA acceptance through --packaging-acceptance.

Inputs are copied into a fresh caller-owned evidence directory. No login,
inference, phasing, original-project writes or actual Jana handoff is performed.
"""
import json
import os
import shutil
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def run_saved_map_check(directory, configuration):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    from . import app as a
    from .map_quality import MapQualityMetrics, ValidationProfile, profile_definition, recommend_best_result
    from .result_selection import ResultSelectionDialog, create_result_preview_host
    from .ui_style import apply_phase_studio_style

    target = Path(directory).resolve()
    target.mkdir(parents=True, exist_ok=False)
    spec = json.loads(Path(configuration).read_text(encoding='utf-8'))
    source = Path(spec['run']).resolve()
    original = {str(p): a.file_sha256(p) for p in source.rglob('*') if p.is_file()}
    # Match the failing project's root length, while preserving user files.
    work = target / ('p' * max(1, len(str(source)) - len(str(target)) - 10)) / 'run_0002'
    work.mkdir(parents=True)
    for cycle_dir in source.glob('cycle_*'):
        if cycle_dir.is_dir():
            shutil.copytree(cycle_dir, work/cycle_dir.name)
    inflip = target / 'input.inflip'
    shutil.copyfile(spec['inflip'], inflip)
    cell, sg, hm, comp = a.parse_inflip_crystallography(inflip)
    context = a.ReferenceContext(inflip, inflip, cell, sg, hm, comp, [])
    cfg = SimpleNamespace(work_dir=work, jana_inflip=inflip, edma_exe=spec['edma'],
        edma_threshold_mode='manual', merge_distance=.75, edma_maxima='all',
        edma_fullcell='no', edma_numberofatoms='composition', edma_centerofcharge=True,
        edma_chlimit='0.2500', edma_chlimlist='0.0057 relative',
        extra_edma_keywords='', structure_export_format='pdb')
    qt = QApplication.instance() or QApplication([])
    apply_phase_studio_style(qt)
    rows = []
    with patch.multiple(a.IterativeSuperflipPipelineQtGUI,
            load_settings=lambda self: None, save_settings=lambda self: None,
            refresh_sharped_models=lambda self: None), \
            patch.object(a, 'run_superflip_cycle', side_effect=AssertionError('No phasing allowed')), \
            patch.object(a, 'run_sharped_deblur', side_effect=AssertionError('No inference allowed')):
        backend = a.IterativeSuperflipPipelineQtGUI()
        backend._active_run_id = 'run_0002'
        backend._resume_state = SimpleNamespace(run_id='run_0002', cfg=cfg, ref_ctx=context,
            sharped_models_by_map={}, performance_profiler=None)
        backend.results = []
        for cycle_dir in sorted(work.glob('cycle_*')):
            cycle = int(cycle_dir.name.split('_')[-1])
            sf = cycle_dir / f'cycle_{cycle:03d}_superflip.xplor'
            db = cycle_dir / f'cycle_{cycle:03d}_deblurred.xplor'
            backend.results.append(a.CycleResult(cycle=cycle, model_source='none',
                model_in=None, model_metric=None, superflip_map=sf,
                superflip_edma_cif=cycle_dir/'edma_superflip'/f'cycle_{cycle:03d}_superflip_edma.cif',
                superflip_metric=None, deblur_map=db,
                deblur_edma_cif=cycle_dir/'edma_deblurred'/f'cycle_{cycle:03d}_deblurred_edma.cif',
                deblur_metric=None, superflip_edma_sigma=.5, deblur_edma_sigma=.5,
                run_id='run_0002', sharped_model='SEED (cyclic CF)',
                superflip_quality=MapQualityMetrics(), deblur_quality=MapQualityMetrics()))
            backend._resume_state.sharped_models_by_map[str(db.resolve())] = 'SEED (cyclic CF)'
        profile = ValidationProfile.REFERENCE_FREE
        def request_retune(candidate, add, callback):
            def completed(updated, report, request):
                if report:
                    (target/'failure.txt').write_text(report.diagnostic_block(), encoding='utf-8')
                callback(updated, report, request)
            return backend.request_result_candidate_retune(candidate, add, completed)
        for source_name in ('deblurred', 'superflip'):
            candidates = a.result_candidates_from_results(backend.results)
            groups = [[c for c in candidates if c.source == name] for name in ('superflip', 'deblurred')]
            selector = ResultSelectionDialog(backend, *groups, profile, profile_definition(profile),
                *(recommend_best_result(profile, group) for group in groups),
                superflip_tab_available=True, sharped_tab_available=True,
                initial_source=source_name, map_feedback_intensity_enabled=False, jana_context=True,
                preview_host=create_result_preview_host(backend, cell, 30, -60),
                parse_structure=a.parse_cif_atoms, reference_atoms=[], source_title=lambda s: s,
                adjust_threshold_async=request_retune)
            view = selector._views[source_name]
            view.selected = next(c for c in view.ordered if c.cycle == 3)
            selector._render_preview(view.selected)
            selector._sync_action_button()
            selector.show()
            qt.processEvents()
            initial = selector.selected_candidate
            assert initial.cycle == 3 and initial.edma_sigma == .5
            selected_map_hash = a.file_sha256(Path(initial.map_path))
            untouched = [(r, r.superflip_edma_cif, r.deblur_edma_cif) for r in backend.results if r.cycle != 3]
            for step, (add, expected) in enumerate(((True, .4), (True, .3), (False, .4), (False, .5), (False, .6))):
                button = selector._add_atoms_button if add else selector._remove_atoms_button
                assert button.isEnabled()
                QTest.mouseClick(button, Qt.LeftButton)
                deadline = time.monotonic() + 30
                while selector._pending_thresholds and time.monotonic() < deadline:
                    backend._poll_queue()
                    qt.processEvents()
                    time.sleep(.01)
                assert not selector._pending_thresholds
                candidate = selector.selected_candidate
                (target/'execution.log').write_text(backend.log_text.toPlainText(), encoding='utf-8')
                assert abs(candidate.edma_sigma - expected) < 1e-9, selector._threshold_status.text()
                assert candidate.cycle == 3 and candidate.source == source_name
                assert candidate.map_path == initial.map_path and candidate.map_sha256 == selected_map_hash
                assert a.file_sha256(Path(candidate.jana_model_path)) == candidate.jana_model_sha256
                assert candidate.detected_atom_count == len(a.parse_cif_atoms(Path(candidate.structure_path)))
                assert all(atom.uiso_angstrom2 is None for atom in a.parse_cif_atoms(Path(candidate.structure_path)))
                result = backend._cycle_result_for_candidate(candidate)
                assert (result.superflip_edma_cif if source_name == 'superflip' else result.deblur_edma_cif) == Path(candidate.structure_path)
                assert all((r.superflip_edma_cif, r.deblur_edma_cif) == (sf, db) for r, sf, db in untouched)
                selector.grab().save(str(target / f'{source_name}-{step}-{expected:.2f}.png'))
                rows.append(dict(source=source_name, cycle=3, threshold=expected,
                    sites=candidate.detected_atom_count, jana_sites=candidate.jana_model_site_count,
                    map_sha256=candidate.map_sha256, model_sha256=candidate.jana_model_sha256,
                    structure=candidate.structure_path))
            selector.close()
        backend._poll_queue()
        (target/'execution.log').write_text(backend.log_text.toPlainText(), encoding='utf-8')
        backend.close()
    assert all(a.file_sha256(Path(p)) == digest for p, digest in original.items())
    (target/'report.json').write_text(json.dumps(dict(passed=True, frozen=bool(getattr(__import__('sys'),'frozen',False)),
        native_edma=spec['edma'], source_files_unchanged=len(original), adjustments=rows), indent=2), encoding='utf-8')
    return 0
