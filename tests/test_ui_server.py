import json
import threading
import urllib.request
from http.server import HTTPServer

import pytest

from ai_linkedin_automation.ui_server import UIRequestHandler


def _start_test_server():
    try:
        server = HTTPServer(('127.0.0.1', 0), UIRequestHandler)
    except PermissionError as exc:
        pytest.skip(f"Local socket binding is not available in this environment: {exc}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _fetch_json(url: str):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def test_ui_server_status():
    server, thread = _start_test_server()
    port = server.server_port
    try:
        data = _fetch_json(f'http://127.0.0.1:{port}/api/status')
        assert isinstance(data, dict)
        assert 'app' in data
        assert 'database' in data
    finally:
        server.shutdown()
        server.server_close()


def test_ui_server_version_exposes_launcher_contract():
    server, thread = _start_test_server()
    port = server.server_port
    try:
        data = _fetch_json(f'http://127.0.0.1:{port}/api/version')
        assert data["launcher_contract"] == "touch_free_locus_v2"
        assert "locus_workbench_export" in data["features"]
    finally:
        server.shutdown()
        server.server_close()


def test_ui_server_config_files():
    server, thread = _start_test_server()
    port = server.server_port
    try:
        data = _fetch_json(f'http://127.0.0.1:{port}/api/config-files')
        assert isinstance(data, dict)
        assert 'files' in data
        assert 'app.yaml' in data['files']
    finally:
        server.shutdown()
        server.server_close()
