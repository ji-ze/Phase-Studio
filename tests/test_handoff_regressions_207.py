"""Offline local handoff regressions; optional real native protocol conversion."""
from dataclasses import replace
import hashlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from phase_studio import app as a
from phase_studio.error_reporting import build_error_report
from phase_studio.jana_handoff_io import (
    copy_protocol_file, filesystem_path, handoff_staging, JanaProjectMetadataError,
)


CONTEXT = 'Version Jana2020\ncell 10 10 10 90 90 90\nspgroup P1 1 1\natlist C\nend\n'


def test_copy_long_target_preserves_original_bytes(tmp_path):
    source = tmp_path / 'source.m50'; source.write_text(CONTEXT, encoding='utf8')
    parent = tmp_path / ('project with spaces ' + 'x' * 35)
    parent.mkdir()
    length = max(262, len(str(parent)) + 30)
    target = parent / ('p' * (length - len(str(parent)) - 5) + '.m50')
    assert len(str(target)) == length
    copy_protocol_file(source, target)
    assert filesystem_path(target).read_bytes() == source.read_bytes()
    assert not list(parent.glob('.psj-*'))


@pytest.mark.parametrize('error,category', [
    (FileNotFoundError(2, 'Cannot open', 'SharpED/candidate/stage.m50'), 'jana_handoff_missing'),
    (PermissionError(13, 'Access denied', 'SharpED/candidate/stage.m50'), 'jana_handoff_permission'),
    (JanaProjectMetadataError('Missing original project m50'), 'jana_handoff_metadata'),
])
def test_local_handoff_does_not_become_remote_failure(error, category):
    report = build_error_report(error, subsystem='Jana2020', operation='Jana2020 handoff')
    assert report.category == category
    assert report.subsystem == 'Jana2020 handoff'
    assert 'server could not complete' not in report.summary


def test_missing_context_reports_search_and_never_fabricates(tmp_path):
    source = tmp_path / 'project_Superflip.inflip'; source.write_text('cell 10 10 10 90 90 90')
    with pytest.raises(JanaProjectMetadataError, match='Searched:'):
        a._jana_original_m50(source, tmp_path / 'solution.m50')
    assert not list(tmp_path.glob('*.m50'))


def test_canonical_m90_anchors_original_context_without_canonical_inflip(tmp_path):
    source = tmp_path / 'project_Superflip.inflip'; source.write_text('cell 10 10 10 90 90 90')
    (tmp_path / 'project.m90').write_text('controlled original Jana reflection sidecar')
    original = tmp_path / 'project.m50'; original.write_text(CONTEXT, encoding='utf8')
    assert a._jana_original_m50(source, tmp_path / 'project_Superflip.m50') == original


def test_retry_and_failure_preserve_existing_attempts(tmp_path):
    with handoff_staging(tmp_path, 'candidate', 20) as stage:
        first = stage; (stage / 'evidence.txt').write_text('preserve')
    with pytest.raises(PermissionError):
        with handoff_staging(tmp_path, 'candidate', 20) as stage:
            assert stage != first
            raise PermissionError('controlled denied write')
    assert (first / 'evidence.txt').read_text() == 'preserve'


def test_final_validation_failure_rolls_back_all_outputs_and_stale_model(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'new protocol')
    target=tmp_path/'target';target.write_bytes(b'original protocol')
    stale=tmp_path/'original.m40';stale.write_bytes(b'original post-import model')
    def reject():raise OSError('controlled snapshot validation failure')
    with pytest.raises(OSError):a._publish_protocol_transaction([(source,target)],remove=[stale],finalize=reject)
    assert target.read_bytes()==b'original protocol' and stale.read_bytes()==b'original post-import model'
    assert not list(tmp_path.glob('.psj-*'))


from phase_studio.handoff_acceptance import make_native_case as native_case


@pytest.mark.skipif(not os.environ.get('PHASE_STUDIO_NATIVE_SUPERFLIP'),reason='opt-in installed native Superflip/EDMA')
@pytest.mark.parametrize('source',['superflip','deblurred'])
@pytest.mark.parametrize('cycles',[1,3])
@pytest.mark.parametrize('stopped_resumed',[False,True])
def test_native_completed_handoff_with_long_staging(tmp_path,source,cycles,stopped_resumed):
    cfg,result,candidate = native_case(tmp_path/'case',source,cycles)
    if stopped_resumed:cfg=replace(cfg,cycles=cycles+2)
    protected={Path(p):a.file_sha256(Path(p)) for p in [candidate.map_path,candidate.structure_path,candidate.jana_model_path]}
    context=Path(cfg.jana_inflip).parent/'measurement.m50';protected[context]=a.file_sha256(context)
    messages=[]
    a.perform_jana_handoff(cfg,result,candidate,messages.append)
    project=Path(cfg.jana_inflip).parent
    assert (project/'measurement_Superflip.m81').is_file()
    assert (project/'measurement_Superflip.m80').is_file()
    assert a.file_sha256(project/'measurement_Superflip.m50')==protected[context]
    assert a.file_sha256(project/'measurement_Superflip_tmp.m40')==candidate.jana_model_sha256
    assert all(a.file_sha256(p)==digest for p,digest in protected.items())
    alignment=next(filesystem_path(cfg.work_dir/'jana_handoff').glob('*/density_alignment.json'))
    import json
    report=json.loads(alignment.read_text(encoding='utf8'))
    assert report['source_map_sha256']==candidate.map_sha256
    assert report['selected_cif_sha256']==candidate.structure_sha256
    assert report['selected_m40_sha256']==candidate.jana_model_sha256
    assert report['candidate_id']==candidate.candidate_id


@pytest.mark.skipif(not os.environ.get('PHASE_STUDIO_NATIVE_SUPERFLIP'),reason='opt-in installed native Superflip/EDMA')
def test_native_missing_original_context_fails_before_copy_or_execution(tmp_path):
    cfg,result,candidate=native_case(tmp_path/'case','deblurred',1,context=False)
    with patch.object(a,'run_command',side_effect=AssertionError('Conversion must not start')), \
         patch('phase_studio.jana_handoff_io.copy_protocol_file',side_effect=AssertionError('No copy before context validation')):
        with pytest.raises(JanaProjectMetadataError):a.perform_jana_handoff(cfg,result,candidate,lambda _s:None)


@pytest.mark.skipif(not os.environ.get('PHASE_STUDIO_NATIVE_SUPERFLIP'),reason='opt-in installed native Superflip/EDMA')
def test_native_evidence_failure_rolls_back_publication(tmp_path):
    cfg,result,candidate=native_case(tmp_path/'case','deblurred',1)
    project=Path(cfg.jana_inflip).parent
    names=['measurement_Superflip.m50','measurement_Superflip.m80','measurement_Superflip.m81','measurement_Superflip_tmp.m40']
    for name in names:(project/name).write_bytes(b'existing '+name.encode())
    before={p.name:p.read_bytes() for p in project.iterdir() if p.is_file()}
    with patch('phase_studio.jana_handoff_io.archive_handoff_staging',side_effect=PermissionError('controlled evidence archive failure')):
        with pytest.raises(PermissionError):a.perform_jana_handoff(cfg,result,candidate,lambda _s:None)
    assert {p.name:p.read_bytes() for p in project.iterdir() if p.is_file()}==before
    assert not (project/'output').exists(), 'Archive failure must not leave a successful handoff receipt'


@pytest.mark.skipif(not os.environ.get('PHASE_STUDIO_NATIVE_SUPERFLIP'),reason='opt-in installed native Superflip/EDMA')
def test_native_unicode_and_long_final_project_paths(tmp_path):
    cfg,result,candidate=native_case(tmp_path/'generation','deblurred',3)
    project=filesystem_path(tmp_path/('Jana žluť密 '+ 'long_project_'*10)/'original project')
    project.mkdir(parents=True)
    original=Path(cfg.jana_inflip).parent
    for name in ['measurement_Superflip.inflip','measurement.m50','measurement.m90']:
        copy_protocol_file(original/name,project/name)
    cfg=replace(cfg,jana_inflip=project/'measurement_Superflip.inflip')
    assert len(str(cfg.jana_inflip))>260
    a.perform_jana_handoff(cfg,result,candidate,lambda _s:None)
    for suffix in ['m50','m80','m81']:
        assert (project/('measurement_Superflip.'+suffix)).stat().st_size>0
    assert a.file_sha256(project/'measurement_Superflip_tmp.m40')==candidate.jana_model_sha256
    assert a.file_sha256(project/'measurement_Superflip.m50')==a.file_sha256(original/'measurement.m50')


@pytest.mark.skipif(os.name!='nt' or not os.environ.get('PHASE_STUDIO_NATIVE_SUPERFLIP'),reason='opt-in Windows native file-lock rollback')
def test_native_publication_permission_failure_rolls_back_existing_project(tmp_path):
    import ctypes
    from ctypes import wintypes
    cfg,result,candidate=native_case(tmp_path/'generation','deblurred',1)
    project=Path(cfg.jana_inflip).parent
    names=['measurement_Superflip.m50','measurement_Superflip.m80','measurement_Superflip.m81','measurement_Superflip_tmp.m40','measurement_Superflip-deb.xplor']
    before={}
    for name in names:
        path=project/name;path.write_bytes(b'existing project output '+name.encode());before[path]=a.file_sha256(path)
    create=ctypes.windll.kernel32.CreateFileW
    create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    create.restype=wintypes.HANDLE
    handle=create(str(project/'measurement_Superflip.m80'),0x80000000,0,None,3,128,None)
    assert handle!=ctypes.c_void_p(-1).value
    try:
        with pytest.raises(PermissionError):a.perform_jana_handoff(cfg,result,candidate,lambda _s:None)
    finally:
        close=ctypes.windll.kernel32.CloseHandle;close.argtypes=[wintypes.HANDLE];close(handle)
    assert all(a.file_sha256(p)==digest for p,digest in before.items())
    assert not list(project.glob('*.publish-*')) and not list(project.glob('*.backup-*'))


