"""Provenance must survive interruption without altering scientific artifacts."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

from phase_studio.run_provenance import RunProvenance, file_identity, repair_event_stream, safe


def config(root):
    source=root/'observed.hkl';source.write_text('1 0 0 12 0.1\n')
    return SimpleNamespace(run_id='test-run',work_dir=root,hkl=source,cycles=2,
        sharped_api_token='private-test-token-207',sharped_base_url='https://user:password@example.test/api?token=secret',
        randomseed='AUTO',setting_provenance={'cycles':{'source':'User override'}})


def test_interruption_resume_and_no_false_completion(tmp_path):
    cfg=config(tmp_path);before=cfg.hkl.read_bytes()
    p=RunProvenance(tmp_path,cfg)
    p.operation('started','Superflip',1)
    first=p.session_id;p.close()
    assert json.loads((tmp_path/'run_manifest.json').read_text())['status']=='interrupted'
    p=RunProvenance(tmp_path,cfg)
    assert p.session_id!=first
    assert p.manifest['previous_session_status']=='interrupted'
    p.finish('complete')
    assert p.manifest['status']=='partial'
    assert '1' in p.manifest['incomplete_cycles']
    p.close()
    events=[json.loads(line) for line in (tmp_path/'events.jsonl').read_text().splitlines()]
    assert len({(e['session_id'],e['session_sequence']) for e in events})==len(events)
    assert all(e['run_id']=='test-run' and '+00:00' in e['timestamp'] for e in events)
    assert cfg.hkl.read_bytes()==before


def test_sanitized_bundle_valid_json_no_arrays_or_secrets(tmp_path):
    cfg=config(tmp_path);p=RunProvenance(tmp_path,cfg)
    p.event('test','SharpED',1,{'job_id':'private-job-123','api_token':cfg.sharped_api_token,'file':str(cfg.hkl)})
    target=tmp_path/'support.zip';p.export_sanitized(target);p.close()
    with zipfile.ZipFile(target) as archive:
        contents={name:archive.read(name) for name in archive.namelist()}
    combined=b'\n'.join(contents.values()).decode()
    assert cfg.sharped_api_token not in combined
    assert 'private-job-123' not in combined
    assert str(tmp_path) not in combined
    assert 'user:password' not in combined
    assert not any(name.endswith(('.hkl','.cif','.xplor')) for name in contents)
    json.loads(contents['run_manifest.json'])
    for line in contents['events.jsonl'].splitlines():json.loads(line)
    for line in contents['checksums.sha256'].decode().splitlines():
        digest,name=line.split('  ',1)
        assert hashlib.sha256(contents[name]).hexdigest()==digest


def test_interrupted_jsonl_repair_preserves_original(tmp_path):
    path=tmp_path/'events.jsonl';original=b'{"ok":1}\n{"broken"'
    path.write_bytes(original);recovery=repair_event_stream(path)
    assert recovery['invalid_lines']==1
    assert Path(recovery['original_archive']).read_bytes()==original
    assert json.loads(path.read_text())=={'ok':1}


def test_file_identity_and_unavailable_are_distinct(tmp_path):
    source=tmp_path/'empty';source.write_bytes(b'')
    assert file_identity(source)['sha256']==hashlib.sha256(b'').hexdigest()
    assert file_identity(tmp_path/'missing')['sha256'] is None
    assert safe({'password':'private','numeric':float('nan')})=={'password':'<redacted>','numeric':None}


def test_actual_parser_and_writer_bytes_unchanged_with_observer(tmp_path):
    from phase_studio import app as a
    from phase_studio.run_provenance import provenance_scope
    cfg=config(tmp_path)
    cfg.hkl.write_text('# comment\n\n0 0 0 1 1\n1 0 0 12 0.1\n1 0 0 13 0.2\ninvalid\n')
    plain=a.read_hkl(cfg.hkl)
    p=RunProvenance(tmp_path,cfg)
    with provenance_scope(p,1):observed=a.read_hkl(cfg.hkl)
    assert observed==plain
    inventory=p.manifest['reflection_reads'][-1]
    assert inventory['accepted']==2 and inventory['origin_excluded']==1
    assert inventory['blank']==1 and inventory['comments']==1 and inventory['unparsed']==1
    assert inventory['lines']==6 and inventory['status']=='completed'
    p.close()


def test_parallel_event_stream_is_complete_and_cycle_scoped(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    p=RunProvenance(tmp_path,config(tmp_path))
    def worker(cycle):
        for index in range(25):p.event('test','EDMA',cycle,{'index':index})
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(worker,range(1,5)))
    p.close()
    rows=[json.loads(line) for line in (tmp_path/'events.jsonl').read_text().splitlines()]
    selected=[row for row in rows if row['event_type']=='test']
    assert len(selected)==100
    assert len({row['session_sequence'] for row in rows})==len(rows)
    assert all({row['payload']['index'] for row in selected if row['cycle']==cycle}==set(range(25)) for cycle in range(1,5))


def test_cycle_feedback_lineage_and_actual_seed_keywords(tmp_path):
    from phase_studio import app as a
    cfg=config(tmp_path);cfg.cycles=2
    p=RunProvenance(tmp_path,cfg)
    state=SimpleNamespace(cfg=cfg,observed_hkls={'intensity':cfg.hkl},configured_data_mode='intensity')
    for cycle in (1,2):
        directory=tmp_path/f'cycle_{cycle:03d}';directory.mkdir()
        (directory/f'cycle_{cycle:03d}_superflip.inflip').write_text('perform AAR\nreferencefile reference.cif\nrandomseed AUTO\nbestdensities 1 symmetry\nfbegin\n1 0 0 12 0.1\nendf\n')
        result=a.CycleResult(cycle,'fixture',None,None,None,None,None,None,None,None)
        p.completed_cycle(state,result)
        assert p.manifest['cycles'][str(cycle)]['status']!='completed'
        if cycle==1:p.feedback({'source_cycle':1,'target_cycle':2,'operations':[],'next_cycle_reflection_file':str(cfg.hkl),'written_reflections':1})
        p.cycle_finished(cycle)
    p.finish('complete')
    assert p.manifest['status']=='completed'
    roles=p.manifest['cycles']['1']['reference_and_seed_roles']
    assert roles['reference_density_alignment'] is True and roles['initial_model_or_phases'] is False
    assert roles['reference_ranked_superflip_density'] is False and roles['randomseed']=='AUTO'
    assert p.manifest['cycles']['1']['map_feedback']['target_cycle']==2
    assert p.manifest['cycles']['2']['reflection_input']['records']==1
    p.close()


def test_remote_client_method_bodies_only_add_read_only_observers():
    import ast
    import subprocess
    root=Path(__file__).resolve().parents[1]
    path='phase_studio/sharped_server_client.py'
    before=subprocess.check_output(['git','show','a91d129:'+path],cwd=root).decode('utf8')
    after=(root/path).read_text(encoding='utf8')
    def methods(source,normalize=False):
        tree=ast.parse(source);count=0
        if normalize:
            for parent in ast.walk(tree):
                for field,value in ast.iter_fields(parent):
                    if isinstance(value,list):
                        hooks=[item for item in value if isinstance(item,ast.Expr) and isinstance(item.value,ast.Call)
                            and isinstance(item.value.func,ast.Name) and item.value.func.id=='observe_remote']
                        count+=len(hooks);value[:]=[item for item in value if item not in hooks]
            assert count==4
        return {(node.name,sub.name):ast.dump(sub) for node in tree.body if isinstance(node,ast.ClassDef)
                for sub in node.body if isinstance(sub,ast.FunctionDef)}
    assert methods(before)==methods(after,True)
