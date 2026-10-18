"""Stable version and public GitHub transport guards; no live requests."""
import http.client
import json
import socket
import ssl

import pytest

from phase_studio import update_checker as u


@pytest.mark.parametrize('latest,expected', [('2.0.3',False),('2.0.4',False),('2.0.5',True),
    ('v2.1.0',True),('3.0.0',True),('2.0.10',True),('1.99.99',False),('2.0.5+build.9',True)])
def test_numeric_comparison(latest, expected):
    assert u.is_newer(u.Release(u.parse_version(latest)), '2.0.4') is expected


@pytest.mark.parametrize('tag', ['',None,12,'dev','development/2.0.5','2.0','2.0.5rc1',
    '2.0.5-rc.1','2.0.05','2.00.5',' 2.0.5','2.0.5\n','<b>2.0.5</b>','9'*130])
def test_invalid_and_prerelease_tags(tag):
    assert u.parse_version(tag) is None


@pytest.mark.parametrize('changes', [{'draft':True},{'prerelease':True},{'draft':'false'},
    {'prerelease':0},{'tag_name':'2.0.5-beta'},{'tag_name':None}])
def test_excluded_releases(changes):
    assert u.release_from_json(dict(tag_name='v2.0.5',draft=False,prerelease=False)|changes) is None


def test_schema_and_untrusted_body():
    for value in (None,[],{},'2.0.5',{'tag_name':'v2.0.5'}):
        assert u.release_from_json(value) is None
    release=u.release_from_json(dict(tag_name='v2.0.5',draft=False,prerelease=False,
        body='<script>evil()</script>',html_url='https://untrusted.example/install.exe'))
    assert release.label=='2.0.5' and release.url==u.RELEASES_URL
    assert u.RELEASES_URL=='https://github.com/ji-ze/Phase-Studio/releases'


class Connection:
    status=200
    raw=json.dumps([dict(tag_name='v2.0.5',draft=False,prerelease=False,published_at='2026-10-17T12:00:00Z')]).encode()
    error=None
    instances=[]

    def __init__(self, host, **options):
        self.host=host;self.options=options;self.requests=[];self.closed=False
        self.__class__.instances.append(self)

    def request(self, *args, **kwargs):
        self.requests.append((args,kwargs))
        if self.error: raise self.error

    def getresponse(self): return self
    def read(self, limit):
        self.read_limit=limit
        return self.raw[:limit]
    def close(self): self.closed=True


def test_public_request_has_no_auth_or_scientific_data():
    release=u.fetch_latest_release(Connection)
    assert release.version==(2,0,5)
    connection=Connection.instances[-1]
    assert connection.host=='api.github.com'
    assert connection.options['timeout']==4
    context=connection.options['context']
    assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
    assert connection.requests==[(('GET',u.API_PATH+'&page=1'),
        {'headers':{'User-Agent':f'PhaseStudio/{u.VERSION}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}})]
    assert connection.closed and connection.read_limit==u.MAX_RESPONSE_BYTES+1


@pytest.mark.parametrize('status',[301,302,403,404,429,500,503])
def test_http_failures_do_not_retry_or_follow_redirects(status):
    class Failed(Connection): pass
    Failed.status=status
    assert u.fetch_latest_release(Failed) is None
    assert len(Failed.instances[-1].requests)==1 and Failed.instances[-1].closed


@pytest.mark.parametrize('error',[socket.gaierror('offline'),TimeoutError('timeout'),
    ssl.SSLError('TLS failure'),ConnectionError('offline'),http.client.HTTPException('bad response')])
def test_offline_timeout_tls_fail_safely(error):
    class Failed(Connection): pass
    Failed.error=error
    assert u.fetch_latest_release(Failed) is None
    assert Failed.instances[-1].closed


@pytest.mark.parametrize('raw',[b'invalid JSON',b'\xff',b'[{}]',b'{}',b'x'*(u.MAX_RESPONSE_BYTES+1)],
    ids=['malformed-json','invalid-encoding','array-schema','empty-schema','oversized'])
def test_invalid_or_oversized_response(raw):
    class Invalid(Connection): pass
    Invalid.raw=raw
    assert u.fetch_latest_release(Invalid) is None
