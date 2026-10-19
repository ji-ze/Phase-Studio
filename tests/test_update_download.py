import io
import threading

import pytest

from phase_studio import update_download as d

URL='https://github.com/ji-ze/Phase-Studio/releases/download/v2.0.6/test.exe'


class Response:
    def __init__(self,data=b'abc',status=200,headers=None):
        self.data=io.BytesIO(data);self.status=status;self.headers=headers or {}
    def getheader(self,key):return self.headers.get(key)
    def read(self,size):return self.data.read(size)


def factory(responses,requests):
    class Connection:
        def __init__(self,host,**kwargs):self.host=host
        def request(self,method,path,headers):requests.append((self.host,method,path,headers))
        def getresponse(self):return responses.pop(0)
        def close(self):pass
    return Connection


def test_download_progress_and_no_auth_headers(tmp_path):
    requests=[];progress=[];path=tmp_path/'new.exe'
    result=d.download(URL,path,expected_size=3,progress=lambda a,b:progress.append((a,b)),
        connection_factory=factory([Response(headers={'Content-Length':'3'})],requests))
    assert result.read_bytes()==b'abc' and progress==[(3,3)]
    assert set(requests[0][3])=={'User-Agent','Accept','Accept-Encoding'}
    assert not (tmp_path/'new.exe.part').exists()


@pytest.mark.parametrize('url',[
    'http://github.com/ji-ze/Phase-Studio/releases/download/v2.0.6/a.exe',
    'https://github.com/evil/Phase-Studio/releases/download/v2.0.6/a.exe',
    'https://github.com.evil/ji-ze/Phase-Studio/releases/download/v2.0.6/a.exe',
    'https://user:pass@github.com/ji-ze/Phase-Studio/releases/download/v2.0.6/a.exe',
    'https://github.com:444/ji-ze/Phase-Studio/releases/download/v2.0.6/a.exe',
    'https://objects.githubusercontent.com/untrusted-initial',
])
def test_untrusted_initial_url(url):
    with pytest.raises(d.UpdateVerificationError):d.validate_download_url(url)


def test_legitimate_cdn_redirect(tmp_path):
    requests=[]
    d.download(URL,tmp_path/'new.exe',expected_size=3,connection_factory=factory([
        Response(status=302,headers={'Location':'https://release-assets.githubusercontent.com/path?signature=public'}),
        Response()],requests))
    assert [r[0] for r in requests]==['github.com','release-assets.githubusercontent.com']


def test_redirect_to_untrusted_host(tmp_path):
    requests=[]
    with pytest.raises(d.UpdateVerificationError):
        d.download(URL,tmp_path/'new.exe',expected_size=3,connection_factory=factory([
            Response(status=302,headers={'Location':'https://evil.invalid/payload'})],requests))
    assert len(requests)==1 and not (tmp_path/'new.exe').exists()


@pytest.mark.parametrize('response',[Response(b'ab'),Response(b'abcd'),
    Response(headers={'Content-Length':'4'}),Response(status=404),
    Response(headers={'Content-Encoding':'gzip'})])
def test_invalid_download_leaves_no_payload(tmp_path,response):
    with pytest.raises(d.UpdateVerificationError):
        d.download(URL,tmp_path/'new.exe',expected_size=3,
            connection_factory=factory([response],[]))
    assert list(tmp_path.iterdir())==[]


def test_cancelled(tmp_path):
    cancel=threading.Event();cancel.set()
    with pytest.raises(d.DownloadCancelled):d.download(URL,tmp_path/'new.exe',expected_size=3,cancel=cancel)
    assert list(tmp_path.iterdir())==[]


def test_existing_destination_not_overwritten(tmp_path):
    target=tmp_path/'new.exe';target.write_bytes(b'old')
    with pytest.raises(d.UpdateVerificationError):d.download(URL,target,expected_size=3)
    assert target.read_bytes()==b'old'
