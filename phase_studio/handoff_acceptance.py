"""Explicit offline native handoff acceptance, with synthetic data and isolated output."""
from dataclasses import fields,replace
from pathlib import Path
import json,os
from . import app as a
from .jana_handoff_io import filesystem_path,JanaProjectMetadataError
CONTEXT='Version Jana2020\ncell 10 10 10 90 90 90\nspgroup P1 1 1\natlist C\nend\n'

def _controlled_config(engine,work,inflip):
    values={}
    for field in fields(engine.RunConfig):
        kind=str(field.type)
        values[field.name]=(None if kind.startswith('Optional') else work/'unused' if kind=='Path' else False if kind=='bool' else 1 if kind=='int' else 0.0 if kind=='float' else '')
    values.update(jana_inflip=inflip,work_dir=work,jana_return_to_jana=True)
    return engine.RunConfig(**values)

def make_native_case(folder, source, cycles, context=True):
    """Controlled completed CF/SharpED-shaped candidate; no network prediction."""
    import gemmi
    import numpy as np
    from phase_studio.xplor_io import XplorMap, write_xplor_map
    from phase_studio.map_quality import ResultCandidate, MapQualityMetrics
    sf = Path(os.environ['PHASE_STUDIO_NATIVE_SUPERFLIP'])
    edma = Path(os.environ['PHASE_STUDIO_NATIVE_EDMA'])
    folder.mkdir(parents=True)
    project = folder / 'original project'; project.mkdir()
    inflip = project / 'measurement_Superflip.inflip'
    inflip.write_text('title controlled_native_handoff\noutputfile measurement_Superflip.m81 measurement_Superflip.m80\n'
        'outputbase measurement_Superflip\nwritem40 measurement_Superflip_tmp.m40\nm40forjana yes\n'
        'outputformat jana\ndimension 3\ncell 10 10 10 90 90 90\nspacegroup P1\n'
        'centro no\ncenters\n0 0 0\nendcenters\nsymmetry\nx1 x2 x3\nendsymmetry\n'
        'perform CF\nfbegin\n1 0 0 10 1\nendf\n', encoding='utf8')
    (project / 'measurement.m90').write_text('controlled sidecar anchor', encoding='utf8')
    if context:(project / 'measurement.m50').write_text(CONTEXT, encoding='utf8')
    work = folder / ('Full Configuration ' + 'long_project_' * 8) / 'run_0001'
    work=filesystem_path(work);work.mkdir(parents=True)
    grid = np.indices((16,16,16)).astype(float)
    data = np.zeros((16,16,16))
    for point in [(3,5,7),(10,11,4),(12,3,12)]:
        d = sum(np.minimum(abs(grid[i]-point[i]),16-abs(grid[i]-point[i]))**2 for i in range(3))
        data += np.exp(-d/2)
    map_path = folder / 'selected_map.xplor'
    write_xplor_map(map_path, XplorMap('controlled', (16,0,15,16,0,15,16,0,15), (10,10,10,90,90,90), 'ZYX', data.ravel()))
    metadata = a.CrystalMetadata(gemmi.UnitCell(10,10,10,90,90,90),gemmi.SpaceGroup('P 1'),'P 1','C3','test',inflip)
    ref = a.reference_context_from_metadata(metadata, None, folder)
    cif = a.run_edma_on_xplor(map_path, folder/'edma', 'selected', ref, .5, .3, str(edma), lambda _s:None)
    map_path=map_path.rename(folder/'selected scientific map.xplor')
    cfg = replace(_controlled_config(a,work,inflip),run_id='controlled-run',cycles=cycles,
                  superflip_exe=str(sf),edma_exe=str(edma),crystal_metadata=metadata)
    candidate = a.seal_result_candidate(ResultCandidate(cycles,source,str(map_path),str(cif),MapQualityMetrics(),edma_sigma=.5,run_id=cfg.run_id))
    result = a.CycleResult(cycles,'none',None,None,map_path,cif,None,map_path,cif,None,run_id=cfg.run_id,
                          superflip_edma_sigma=.5,deblur_edma_sigma=.5)
    return cfg,result,candidate

def run(directory):
    from .version import VERSION
    out=Path(directory).absolute();out.mkdir(parents=True,exist_ok=False)
    for name in ['PHASE_STUDIO_NATIVE_SUPERFLIP','PHASE_STUDIO_NATIVE_EDMA']:
        if not os.environ.get(name) or not Path(os.environ[name]).is_file():raise ValueError('Explicit installed native executable required: '+name)
    report=dict(version=VERSION,controlled_fixture=True,remote_inference=False,interactive_jana=False,cases=[])
    for source in ['superflip','deblurred']:
        for cycles in [1,3]:
            for partial in [False,True]:
                folder=out/(source+'-cycles-'+str(cycles)+('-partial' if partial else '-complete'))
                cfg,result,candidate=make_native_case(folder,source,cycles)
                if partial:cfg=replace(cfg,cycles=cycles+2)
                paths=[Path(candidate.map_path),Path(candidate.structure_path),Path(candidate.jana_model_path),Path(cfg.jana_inflip).parent/'measurement.m50']
                before={p:a.file_sha256(p) for p in paths}
                messages=[];a.perform_jana_handoff(cfg,result,candidate,messages.append)
                assert all(a.file_sha256(p)==digest for p,digest in before.items())
                project=Path(cfg.jana_inflip).parent
                assert a.file_sha256(project/'measurement_Superflip_tmp.m40')==candidate.jana_model_sha256
                assert a.file_sha256(project/'measurement_Superflip.m50')==before[paths[-1]]
                alignment=next(filesystem_path(cfg.work_dir/'jana_handoff').glob('*/density_alignment.json'))
                data=json.loads(alignment.read_text(encoding='utf8'))
                assert data['source_map_sha256']==candidate.map_sha256 and data['selected_cif_sha256']==candidate.structure_sha256
                assert data['selected_m40_sha256']==candidate.jana_model_sha256
                outputs={p.name:dict(bytes=p.stat().st_size,sha256=a.file_sha256(p)) for p in project.iterdir() if p.suffix in ('.m40','.m50','.m80','.m81','.cif','.xplor')}
                report['cases'].append(dict(source=source,completed_cycle=cycles,configured_cycles=cfg.cycles,partial_candidate_fixture=partial,passed=True,candidate_id=candidate.candidate_id,source_map_sha256=candidate.map_sha256,source_cif_sha256=candidate.structure_sha256,source_m40_sha256=candidate.jana_model_sha256,original_files_unchanged=True,outputs=outputs))
                (folder/'handoff.log').write_text('\n'.join(messages),encoding='utf8')
    cfg,result,candidate=make_native_case(out/'missing-context','deblurred',1,context=False)
    try:a.perform_jana_handoff(cfg,result,candidate,lambda _s:None)
    except JanaProjectMetadataError:report['missing_context_rejected']=True
    else:raise AssertionError('Missing original metadata must be rejected')
    report['passed']=True
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    return 0
