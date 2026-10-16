"""Exercise real http.client serialization without production credentials."""
import http.client
import json
import threading
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from phase_studio.sharped_server_client import SharpEDServerClient, SharpEDServerError
from phase_studio.error_reporting import build_error_report


def test_unicode_metadata_binary_upload_and_authenticated_download():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            received.append((self.path, self.headers, body))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'job_id': 1, 'token': 'mock-job'}).encode())

        def do_GET(self):
            received.append((self.path, self.headers, b''))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'XPLOR\x00\xff\x80\r\n')

    server = HTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'ochlor.xplor'
            payload = b'XPLOR\x00\xff\x80\r\n'
            source.write_bytes(payload)
            client = SharpEDServerClient(f'http://127.0.0.1:{server.server_port}')
            metadata = 'σ Å α β č ř ž'
            result = client.upload(source, 'mock-access._~+/-==', metadata, metadata, .2)
            path, headers, body = received[0]
            assert path == '/api/user/sharp-ed/upload'
            assert headers['Authorization'] == 'Bearer mock-access._~+/-=='
            assert int(headers['Content-Length']) == len(body)
            message = BytesParser(policy=default).parsebytes(
                ('Content-Type: ' + headers['Content-Type'] + '\r\n\r\n').encode('ascii') + body)
            parts = {part.get_param('name', header='content-disposition'): part for part in message.iter_parts()}
            assert parts['file'].get_filename() == 'ochlor.xplor'
            assert parts['file'].get_payload(decode=True) == payload
            for field in ('elements', 'model'):
                assert parts[field].get_payload(decode=True).decode('utf-8') == metadata
            assert parts['outres'].get_payload(decode=True) == b'0.2'
            destination = Path(directory) / 'download.xplor'
            client.download(client._url('/api/user/sharp-ed/download/' + result.token), destination,
                            primary_token='mock-job', fallback_token='mock-access')
            assert destination.read_bytes() == source.read_bytes() == payload
    finally:
        server.shutdown()
        worker.join()
        server.server_close()


def test_original_sigma_failure_becomes_safe_actionable_error():
    polluted = 'a' * 304 + 'σ copied instructions'
    connection = http.client.HTTPConnection('127.0.0.1')
    connection.putrequest('POST', '/api/user/sharp-ed/upload')
    with pytest.raises(UnicodeEncodeError) as old:
        connection.putheader('Authorization', 'Bearer ' + polluted)
    assert old.value.start == 311
    client = SharpEDServerClient()
    with patch('phase_studio.sharped_server_client.urlopen') as transport:
        with pytest.raises(SharpEDServerError) as caught:
            client._request_bytes('POST', client._url('/api/user/sharp-ed/upload'),
                                  headers={'Authorization': 'Bearer ' + polluted})
        transport.assert_not_called()
    assert caught.value.category == 'authentication'
    assert polluted not in str(caught.value)
    assert 'Authorization' in str(caught.value)
    assert build_error_report(caught.value).category == 'sharped_authentication'


@pytest.mark.parametrize('header,value', [
    ('Authorization', 'Bearer σ'), ('Authorization', 'Bearer Å'),
    ('Authorization', 'Bearer čřž'), ('Authorization', 'Bearer key\r\nX: bad'),
    ('Authorization', 'Bearer key instructions'), ('User-Agent', 'PhaseStudio σ'),
    ('X-Metadata', 'αβ'), ('X-Metadata', 'bad\x00'), ('Bad\nName', 'value'),
])
def test_invalid_headers_rejected_without_values(header, value):
    with pytest.raises(SharpEDServerError):
        SharpEDServerClient._validate_request_headers({header: value})


def test_compatible_latin1_header_and_ascii_credentials():
    SharpEDServerClient._validate_request_headers({'User-Agent': 'PhaseStudio Å',
                                                  'Authorization': 'Bearer mock._~+/-=='})
