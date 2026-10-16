"""Opt-in numerical acceptance on existing ochlor maps, in an isolated project.

Runs installed EDMA and Superflip format conversion, never SharpED inference.
Does not open Jana GUI or write to the original ochlor project.
"""
import json
import os
import shutil
import sys
import time
import numpy as np
import gemmi
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from phase_studio import app as engine
from phase_studio.map_quality import ResultCandidate, MapQualityMetrics
from phase_studio.result_selection import candidate_selection
from test_jana_completion import make_run_config
from phase_studio.displacement import normalize_jana_m40_isotropic_displacements, IsotropicDisplacementKind


def main():
    project = Path(os.environ.get('PHASE_STUDIO_JANA_PROJECT', str(ROOT / 'build/acceptance-inputs/ochlor')))
    old_run = Path(os.environ.get('PHASE_STUDIO_ACCEPTANCE_RUN',str(ROOT / 'build/oauth-2.0.4-ochlor-run/calculation/run_0001')))
    root = ROOT / 'build/selection-integrity-real'
    root.mkdir(exist_ok=True)
    binary = next(p for p in (
        ROOT / 'build/real_jana_protocol_probe/bin/superflip_original.exe',
        Path('C:/Jana2020/backup/superflip.exe'),
    ) if p.is_file())
    edma = Path('C:/Jana2020/SUPERFLIP/EDMA.exe')
    originals = {p: engine.file_sha256(p) for p in project.iterdir() if p.is_file()}
    reports = []
    for source, cycle, sigma in (('deblurred', 3, .5), ('deblurred', 3, .4), ('superflip', 3, .5)):
        case = root / f'{source}-{cycle}-{sigma:.2f}'
        case.mkdir(exist_ok=True)
        for name in ('ochlor.inflip', 'ochlor.m50', 'ochlor.m40'):
            shutil.copy2(project / name, case / name)
        inflip = case / 'ochlor.inflip'
        metadata = engine.resolve_crystal_metadata(engine.METADATA_SOURCE_INFLIP, jana_inflip=inflip)
        context = engine.reference_context_from_metadata(metadata, None, case)
        source_map = old_run / f'cycle_{cycle:03d}' / f'cycle_{cycle:03d}_{source}.xplor'
        map_hash = engine.file_sha256(source_map)
        messages = []
        generation_started = time.time()
        merge_distance = .75  # Current normal GUI Merge distance default, unchanged.
        cif = engine.run_edma_on_xplor(source_map, case / 'edma', 'selected', context,
            sigma, merge_distance, str(edma), messages.append)
        assert cif.with_suffix('.m40').stat().st_mtime >= generation_started
        assert (case/'edma/selected_edma.coo').stat().st_mtime >= generation_started
        candidate = engine.seal_result_candidate(ResultCandidate(cycle, source, str(source_map),
            str(cif), MapQualityMetrics(), edma_sigma=sigma, run_id='selection-integrity-real'))
        assert candidate_selection(candidate).ready
        cfg = make_run_config(engine, case, inflip)
        cfg = replace(cfg, crystal_metadata=metadata, superflip_exe=str(binary),
                      run_id=candidate.run_id, run_sharped=True)
        result = engine.CycleResult(cycle, 'none', None, None, source_map, cif, None,
            source_map, cif, None, run_id=candidate.run_id,
            superflip_edma_sigma=sigma, deblur_edma_sigma=sigma)
        engine.perform_jana_handoff(cfg, result, candidate, messages.append)
        (case / 'audit.log').write_text('\n'.join(messages), encoding='utf8')
        alignment_file = next((case / 'jana_handoff').glob('*/density_alignment.json'))
        alignment = json.loads(alignment_file.read_text(encoding='utf8'))
        lines = inflip.read_text(encoding='utf8').splitlines()
        model = engine._jana_protocol_keyword_path(lines, case, 'writem40')
        m80, m81 = engine._jana_protocol_output_paths(lines, case)
        outputbase = engine._jana_protocol_keyword_path(lines, case, 'outputbase')
        m50 = outputbase.with_suffix('.m50')
        assert engine.file_sha256(model) == candidate.jana_model_sha256
        inspected = case / 'inspected-model.m40'
        shutil.copy2(model, inspected)
        model_records = normalize_jana_m40_isotropic_displacements(inspected, source_kind=IsotropicDisplacementKind.UISO)
        assert all(.010 <= record.uiso_angstrom2 <= .150 for record in model_records)
        # Use the configured production EDMA merge distance, not a new alignment
        # tolerance. Coordinates are compared through the actual space group.
        atoms = engine.parse_cif_atoms(cif)
        images = [np.asarray(op.apply_to_xyz(atom.frac)) for atom in atoms for op in metadata.spacegroup.operations()]
        distances = []
        for record in model_records:
            deltas = [np.asarray(record.fractional) - point for point in images]
            distances.append(min(metadata.cell.orthogonalize(gemmi.Fractional(*(d-np.round(d)))).length() for d in deltas))
        assert max(distances) <= merge_distance, distances
        raw_coordinates,_ = engine.parse_edma_coo(case/'edma/selected_edma.coo')
        raw_images=[np.asarray(op.apply_to_xyz(frac)) for frac in raw_coordinates for op in metadata.spacegroup.operations()]
        raw_distances=[min(metadata.cell.orthogonalize(gemmi.Fractional(*(d-np.round(d)))).length()
            for point in raw_images for d in [np.asarray(record.fractional)-point]) for record in model_records]
        assert max(raw_distances) <= merge_distance
        selected_density=engine.read_xplor_map(source_map)
        nx,ny,nz=(selected_density.grid[i] for i in (0,3,6))
        returned=np.memmap(m81,mode='r',dtype='<f4',offset=4*nx*ny,shape=(nx*ny*nz,))
        original_to_m81=float(np.linalg.norm(returned-selected_density.data)/max(np.linalg.norm(selected_density.data),1e-30))
        assert original_to_m81 <= 5e-4  # Existing jana_density.py acceptance bound.
        def sample(values,frac):
            grid=values.reshape(nz,ny,nx);position=np.mod(frac,1)*[nx,ny,nz]
            low=np.floor(position).astype(int);weight=position-low
            return sum(grid[(low[2]+z)%nz,(low[1]+y)%ny,(low[0]+x)%nx]
                * (weight[0] if x else 1-weight[0]) * (weight[1] if y else 1-weight[1])
                * (weight[2] if z else 1-weight[2]) for x in (0,1) for y in (0,1) for z in (0,1))
        at_model=np.array([sample(selected_density.data,r.fractional) for r in model_records])
        returned_at_model=np.array([sample(returned,r.fractional) for r in model_records])
        model_density_error=float(np.linalg.norm(at_model-returned_at_model)/max(np.linalg.norm(at_model),1e-30))
        assert model_density_error <= 5e-4
        assert engine.file_sha256(source_map) == map_hash
        assert alignment['fractional_origin_shift'] == [0, 0, 0]
        engine._validate_jana_m50(m50, 'real acceptance m50')
        lineage = json.loads(cif.with_name(cif.stem + '_site_counts.json').read_text())
        reports.append(dict(source=source, cycle=cycle, sigma=sigma,
            candidate_id=candidate.candidate_id, map_sha256=map_hash,
            cif_sha256=candidate.structure_sha256, m40_sha256=candidate.jana_model_sha256,
            asu=candidate.edma_asu_composition, lineage=lineage, alignment=alignment,
            model_coordinate_max_distance_to_edma_angstrom=max(distances),
            model_coordinate_max_distance_to_raw_edma_angstrom=max(raw_distances),
            original_to_returned_m81_relative_l2=original_to_m81,
            density_at_model_coordinates_relative_error=model_density_error,
            uiso_range=[min(r.uiso_angstrom2 for r in model_records),max(r.uiso_angstrom2 for r in model_records)],
            exact_model_bytes_coordinates_labels_occupancies_preserved=True,
            merge_distance_angstrom=merge_distance, fresh_edma_generation_verified=True,
            files={role:dict(path=str(path),bytes=path.stat().st_size,sha256=engine.file_sha256(path))
                   for role,path in (('m40',model),('m50',m50),('m80',m80),('m81',m81))}))
    assert all(engine.file_sha256(p) == digest for p,digest in originals.items())
    report = dict(real_project=True, original_project_unchanged=True,
                  real_jana_gui_tested=False, inference_submitted=False, cases=reports)
    (root / 'acceptance.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print('Real ochlor numerical handoff acceptance passed:', len(reports), 'cases')


if __name__ == '__main__':
    main()
