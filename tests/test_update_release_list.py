"""Published stable release selection, verified destinations and bounded requests."""
import json
import pytest
from phase_studio import update_checker as u


def release(tag,**extra):
    return dict(tag_name=tag,draft=False,prerelease=False,published_at='2026-10-17T12:00:00Z',
                html_url='https://github.com/ji-ze/Phase-Studio/releases/tag/'+tag)|extra


def connection(pages,status=200,headers=None):
    class Transport:
        instances=[]
        def __init__(self,host,**options):
            self.host,self.options=host,options;self.instances.append(self);self.closed=False
        def request(self,verb,path,**options):
            self.verb,self.path,self.request_options=verb,path,options
        def getresponse(self):self.status=status;return self
        def getheader(self,key):return (headers or {}).get(key)
        def read(self,limit):
            index=int(self.path.rsplit('=',1)[-1])-1
            data=pages[index] if index<len(pages) else []
            return data if isinstance(data,bytes) else json.dumps(data).encode()
        def close(self):self.closed=True
    return Transport


def test_highest_stable_across_pages_not_release_creation_order():
    transport=connection([[release('v2.0.6')]*99+[release('v9.0.0',draft=True)],
        [release('2.0.8'),release('v2.0.7'),release('v8.0.0',prerelease=True),release('v9.0.0',published_at=None)]])
    result=u.fetch_release_check(transport)
    assert not result.error and result.release.version==(2,0,8)
    assert result.release.url.endswith('/tag/2.0.8')
    assert len(transport.instances)==2 and all(c.closed for c in transport.instances)
    assert all(c.verb=='GET' and 'Authorization' not in c.request_options['headers'] and 'body' not in c.request_options for c in transport.instances)


@pytest.mark.parametrize('url',[
    None,'http://github.com/ji-ze/Phase-Studio/releases/tag/v2.0.6',
    'https://github.com.evil.test/ji-ze/Phase-Studio/releases/tag/v2.0.6',
    'https://user:password@github.com/ji-ze/Phase-Studio/releases/tag/v2.0.6',
    'https://github.com/other/project/releases/tag/v2.0.6',
    'https://github.com/ji-ze/Phase-Studio/releases/download/v2.0.6/installer.exe',
    'https://github.com/ji-ze/Phase-Studio/releases/tag/v2.0.6?install=1',
    'https://github.com/ji-ze/Phase-Studio/releases/tag/v2.0.7'])
def test_untrusted_missing_or_mismatched_link_falls_back_to_listing(url):
    result=u.fetch_release_check(connection([[release('v2.0.6',html_url=url)]]))
    assert not result.error and result.release.url==u.RELEASES_URL


@pytest.mark.parametrize('data,error',[
    ([],''),([release('v3.0.0',prerelease=True)],''),([release('v3.0.0',draft=True)],''),
    ([release('not-a-version')],'metadata-version'),([{}],'metadata-schema'),
    ([release('v2.0.6',published_at='not a date')],'metadata-publication'),
    ([release('v2.0.6',published_at='2026-10-17T12:00:00')],'metadata-publication'),
    (b'not json','metadata-json')])
def test_empty_excluded_and_invalid_metadata_are_distinct(data,error):
    result=u.fetch_release_check(connection([data]))
    assert result.release is None and result.error==error


def test_pagination_limit_is_an_error_not_an_arbitrary_partial_result():
    transport=connection([[release('v2.0.6')]*100]*u.MAX_PAGES)
    result=u.fetch_release_check(transport)
    assert result.error=='metadata-pagination' and result.release is None
    assert len(transport.instances)==u.MAX_PAGES


def test_rate_limit_retry_hint_and_safe_diagnostics():
    result=u.fetch_release_check(connection([],429,{'Retry-After':'3600'}))
    assert result.error=='rate-limit' and result.retry_after==3600 and result.detail=='HTTP 429'
