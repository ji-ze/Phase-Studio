import base64
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat

from phase_studio import update_runtime as r,update_manifest as m,update_download as transport


def metadata(version='2.0.99'):
    names=[f'PhaseStudio-{version}-x64.exe',f'PhaseStudio-Jana2020-{version}.zip',
        'release-manifest.json','release-manifest.sig','SHA256SUMS.txt',f'RELEASE_NOTES_{version}.md']
    return dict(tag_name='v'+version,draft=False,prerelease=False,published_at='2026-10-19T12:00:00Z',
        body='<b>Untrusted notes stay plain text</b>',assets=[dict(name=name,size=12,
            browser_download_url=f'https://github.com/ji-ze/Phase-Studio/releases/download/v{version}/{name}') for name in names])


def connection(data,requests):
    class Response:
        status=200
        def read(self,limit):return json.dumps(data).encode()[:limit]
    class Connection:
        def __init__(self,*args,**kwargs):pass
        def request(self,method,path,headers):requests.append((path,headers))
        def getresponse(self):return Response()
        def close(self):pass
    return Connection


def test_latest_api_exact_assets_without_authentication():
    requests=[];offer=r.fetch_offer('2.0.99',connection_factory=connection(metadata(),requests))
    assert offer.version=='2.0.99' and len(offer.assets)==6
    assert requests[0][0]=='/repos/ji-ze/Phase-Studio/releases/latest'
    assert set(requests[0][1])=={'User-Agent','Accept','X-GitHub-Api-Version'}


@pytest.mark.parametrize('change',[
    lambda d:d.update(draft=True),lambda d:d.update(prerelease=True),
    lambda d:d.update(tag_name='v2.0.99-rc.1'),lambda d:d.update(published_at=None),
    lambda d:d['assets'].pop(),lambda d:d['assets'][0].update(size=True),
    lambda d:d['assets'][0].update(browser_download_url='https://evil.invalid/update.exe'),
    lambda d:d['assets'][0].update(name='unexpected.exe'),
])
def test_bad_or_unavailable_metadata_rejected(change):
    data=metadata();change(data)
    with pytest.raises(m.UpdateVerificationError):r.fetch_offer('2.0.99',connection_factory=connection(data,[]))


@pytest.mark.parametrize('profile',['standalone-onefile','jana2020-onedir'])
def test_actual_profile_marker_controls_selection_not_executable_name(tmp_path,profile):
    target=tmp_path/('Phase_studio.exe' if profile=='jana2020-onedir' else 'Renamed shortcut target.exe')
    target.write_bytes(b'MZ fixture')
    resource=tmp_path/('_internal/phase_studio' if profile=='jana2020-onedir' else 'extracted/phase_studio')
    (resource/'updater').mkdir(parents=True)
    helper=resource/'updater/PhaseStudioUpdater.exe';helper.write_bytes(b'MZ updater fixture')
    (resource/'distribution.json').write_text(json.dumps(dict(schema=1,profile=profile,version=r.VERSION,
        helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest())))
    if profile=='jana2020-onedir':(resource/'installation.json').write_text('{}')
    actual=r.installation(executable=target,resource=resource,frozen=True)
    assert actual.profile==profile and actual.executable==target
    helper.write_bytes(b'corrupted')
    with pytest.raises(m.UpdateVerificationError):r.installation(executable=target,resource=resource,frozen=True)


def test_public_installation_without_pinned_key_fails_closed(monkeypatch):
    monkeypatch.setattr(r,'TRUSTED_KEYS',{})
    assert r.public_installation_status()[0] is False
    with pytest.raises(m.UpdateVerificationError):r.UpdateSession('2.0.99')


def test_environment_drops_authentication_and_startup_probe(monkeypatch):
    monkeypatch.setenv('SHARPED_API_TOKEN','mock-secret')
    monkeypatch.setenv('PHASE_STUDIO_UPDATE_SIGNING_KEY','mock-signing-secret')
    monkeypatch.setenv('PHASE_STUDIO_STARTUP_PROBE','1')
    assert not {'SHARPED_API_TOKEN','PHASE_STUDIO_UPDATE_SIGNING_KEY','PHASE_STUDIO_STARTUP_PROBE'}&r.clean_environment().keys()


def test_authenticated_preparation_with_real_local_http_stream(tmp_path,monkeypatch):
    version='2.0.99';key=Ed25519PrivateKey.generate()
    public=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw);keys={'ephemeral-local-http':public}
    monkeypatch.setattr(r,'TRUSTED_KEYS',keys);monkeypatch.setattr(m,'TRUSTED_KEYS',keys)
    exe=f'PhaseStudio-{version}-x64.exe';zip_name=f'PhaseStudio-Jana2020-{version}.zip'
    package=b'MZ controlled executable fixture';other=b'controlled alternate profile'
    assets=[dict(profile=profile,name=name,size=len(data),sha256=hashlib.sha256(data).hexdigest())
        for profile,name,data in [('standalone-onefile',exe,package),('jana2020-onedir',zip_name,other)]]
    raw=m.canonical_manifest(dict(schema=1,application='Phase Studio',repository='ji-ze/Phase-Studio',
        version=version,channel='stable',os='windows',arch='x64',minimum_updater_protocol=1,
        signature_algorithm='Ed25519',key_id='ephemeral-local-http',assets=assets))
    blobs={exe:package,zip_name:other,'release-manifest.json':raw,'release-manifest.sig':key.sign(raw),
        'SHA256SUMS.txt':''.join(f'{a["sha256"]}  {a["name"]}\n' for a in assets).encode(),
        f'RELEASE_NOTES_{version}.md':b'Controlled fixture only'}
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_GET(self):
            name=self.path.rsplit('/',1)[-1];data=blobs[name];requests.append(self.path)
            self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        data=metadata(version)
        for asset in data['assets']:asset['size']=len(blobs[asset['name']])
        offer=r.fetch_offer(version,connection_factory=connection(data,[]))
        monkeypatch.setattr(r,'fetch_offer',lambda _:offer)
        monkeypatch.setattr(r,'installation',lambda:r.Installation('standalone-onefile',tmp_path/'installed.exe',tmp_path/'helper.exe','a'*64))
        from phase_studio import update_plan
        monkeypatch.setattr(update_plan,'create_workspace',lambda:tmp_path)
        def local_factory(host,**kwargs):return http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
        monkeypatch.setattr(r,'download',lambda url,path,**kwargs:transport.download(url,path,connection_factory=local_factory,**kwargs))
        session=r.UpdateSession(version);events=[]
        session.prepare(lambda *values:events.append(values))
        assert (tmp_path/exe).read_bytes()==package
        assert not any(path.endswith(zip_name) for path in requests)
        assert any(stage=='Verifying release signature' for stage,_,_ in events)
        assert events[-1][0]=='Ready to install'
        session.stop();assert (tmp_path/'cancelled').exists()
    finally:server.shutdown();server.server_close();worker.join(timeout=3)


def test_both_entrypoints_expose_frozen_runtime_check(tmp_path):
    """Exercise real dispatch without requiring a packaged GUI or credentials."""
    import subprocess
    import sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    for module in ('phase_studio.standalone','phase_studio.jana_superflip'):
        output=tmp_path/(module.rsplit('.',1)[-1]+'.json')
        result=subprocess.run([sys.executable,'-m',module,'--update-runtime-check',str(output)],
            cwd=root,capture_output=True,text=True,timeout=30)
        # Source distributions deliberately fail closed, but the dispatch must
        # reach the shared check and produce its structured report.
        assert result.returncode==1 and output.is_file(),result.stdout+result.stderr
        report=json.loads(output.read_text(encoding='utf8'))
        from phase_studio.version import VERSION
        assert report['version']==VERSION and report['ok'] is False
        assert 'Windows distribution only' in report['reason']
