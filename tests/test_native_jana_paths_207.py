"""Real native map/model handoff from Unicode directories; no service jobs."""
import os
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from phase_studio import app as a, jana_superflip as js
from phase_studio.xplor_io import XplorMap,write_xplor_map

SF=Path('C:/Jana2020/SUPERFLIP/superflip.exe')
EDMA=SF.with_name('EDMA.exe')


def project_fixture(tmp_path):
    project=tmp_path/'project žluťoučký 密度';project.mkdir()
    incoming=project/'job.inflip'
    incoming.write_text('title controlled Unicode protocol\nperform CF\noutputfile job.m81 job.m80\noutputformat jana\noutputbase job\nwritem40 job_tmp.m40\ndimension 3\ncell 10 10 10 90 90 90\nspacegroup P 1\ncentro no\nsymmetry\nx1 x2 x3\nendsymmetry\ncomposition C2\n# Keywords for charge flipping\nmaxcycles 1\nrandomseed 12345\ndataformat intensity\nfbegin\n1 0 0 10\nendf\n',encoding='utf8')
    (project/'job.m50').write_text('Version Jana2020\ntitle controlled context only\ncell 10 10 10 90 90 90\nspgroup P1 1 1\nend\n',encoding='utf8')
    coordinates=np.indices((16,16,16))/16
    data=sum(np.exp(-sum((coordinates[i]-center[i])**2 for i in range(3))/.0128) for center in ((.25,.25,.25),(.65,.5,.6)))
    selected=project/'selected.xplor'
    write_xplor_map(selected,XplorMap('controlled Gaussian fixture',(16,0,15,16,0,15,16,0,15),(10,10,10,90,90,90),'ZYX',data.ravel()))
    return project,incoming,selected


@pytest.mark.skipif(not SF.is_file() or not EDMA.is_file(),reason='Actual installed native programs required.')
def test_full_handoff_preserves_native_density_and_model_in_unicode_directory(tmp_path):
    project,incoming,selected=project_fixture(tmp_path)
    protected={p:a.file_sha256(p) for p in (incoming,selected,project/'job.m50')}
    cell=a.gemmi.UnitCell(10,10,10,90,90,90);sg=a.gemmi.SpaceGroup('P 1')
    context=a.ReferenceContext(project/'ref.cif',project/'ref.cif',cell,sg,'P 1','C2',[])
    cif=a.run_edma_on_xplor(selected,project/'edma','controlled',context,.5,.25,str(EDMA),lambda _:None)
    candidate=a.seal_result_candidate(a.ResultCandidate(1,'deblurred',str(selected),str(cif),a.MapQualityMetrics(),edma_sigma=.5,run_id='unicode-regression'))
    assert candidate.detected_atom_count>0 and candidate.jana_model_site_count>0
    result=a.CycleResult(1,'controlled',None,None,selected,cif,None,selected,cif,None,run_id=candidate.run_id)
    cfg=SimpleNamespace(jana_return_to_jana=True,jana_inflip=incoming,run_id=candidate.run_id,
        superflip_exe=SF,edma_exe=EDMA,work_dir=project/'run',cycles=2)
    cfg.work_dir.mkdir()
    a.perform_jana_handoff(cfg,result,candidate,lambda _:None)
    assert a.file_sha256(project/'job_tmp.m40')==candidate.jana_model_sha256
    assert a.file_sha256(project/'job-deb.xplor')==candidate.map_sha256
    a.validate_converted_density(selected,project/'job-ready.xplor')
    a.validate_jana_density_pair(project/'job-ready.xplor',project/'job.m81',project/'job.m80')
    assert all(a.file_sha256(p)==digest for p,digest in protected.items())


@pytest.mark.skipif(not SF.is_file(),reason='Actual installed native Superflip required.')
def test_wrapper_final_conversion_accepts_unicode_working_directory(tmp_path):
    project,incoming,selected=project_fixture(tmp_path)
    before=incoming.read_bytes()
    assert js.run_final_jana_handoff(SF,SF.parent,project,incoming.read_text().splitlines(),'job',selected,lambda _:None)==0
    a.validate_converted_density(selected,project/'job-ready.xplor')
    a.validate_jana_density_pair(project/'job-ready.xplor',project/'job.m81',project/'job.m80')
    assert incoming.read_bytes()==before


def test_wrapper_addresses_original_local_input_relative_to_existing_cwd(tmp_path,monkeypatch):
    project,incoming,selected=project_fixture(tmp_path)
    exe=tmp_path/'controlled-native.fixture';exe.write_bytes(b'Unit stub; not executed')
    monkeypatch.chdir(project)
    monkeypatch.setattr(js,'application_dir',lambda:tmp_path)
    monkeypatch.setattr(js,'resolve_active_jana_superflip',lambda _:exe)
    calls=[]
    monkeypatch.setattr(js,'run_process',lambda cmd,cwd,log:calls.append((cmd,cwd)) or 0)
    before=incoming.read_bytes()
    assert js.run_jana_superflip([str(incoming)],js.JanaRunOptions(action='run',next_cycle_modelfile='none'),lambda _:None)==0
    assert calls==[([str(exe),incoming.name],project)]
    assert incoming.read_bytes()==before
