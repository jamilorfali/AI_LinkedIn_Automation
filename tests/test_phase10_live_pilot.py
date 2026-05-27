import json
import threading
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.ingestion.sources import load_sources_from_config
from ai_linkedin_automation.pilot.live_test import build_live_test_package
from ai_linkedin_automation.pilot.readiness import build_readiness_report, latest_artifacts
from ai_linkedin_automation.storage.db import init_db
from ai_linkedin_automation.ui_server import UIRequestHandler


def _config(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()
    config.storage.sqlite_path = db_path
    config.storage.review_packets_dir = str(tmp_path / "review_packets")
    config.storage.exports_dir = str(tmp_path / "exports")
    config.storage.logs_dir = str(tmp_path / "logs")
    monkeypatch.delenv("GOOGLE_APPS_SCRIPT_WEBAPP_URL", raising=False)
    init_db(config.storage.sqlite_path)
    load_sources_from_config(config)
    return config


def _start_test_server():
    try:
        server = HTTPServer(("127.0.0.1", 0), UIRequestHandler)
    except PermissionError as exc:
        pytest.skip(f"Local socket binding is not available in this environment: {exc}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _fetch_json(url: str):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def test_readiness_report_allows_local_live_pilot_with_approval_url_warning(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    report = build_readiness_report(config)

    assert report.ok_for_live_testing is True
    assert report.live_testing_stage == "ready_for_local_live_pilot"
    assert any(item.name == "Approval web app URL" and item.status == "warn" for item in report.items)
    assert Path(report.markdown_path).exists()
    assert Path(report.json_path).exists()


def test_live_test_package_builds_runbook_manifest_and_guarded_artifacts(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    package = build_live_test_package(config, week="2026-W20", include_dry_run=True)

    assert package.status == "passed"
    assert Path(package.runbook_path).exists()
    assert Path(package.manifest_path).exists()
    assert Path(package.readiness_report_path).exists()
    assert Path(package.approval_qa_report_path).exists()
    runbook = Path(package.runbook_path).read_text()
    manifest = json.loads(Path(package.manifest_path).read_text())

    assert "Live testing uses real public RSS/manual sources" in runbook
    assert "No action means no post" in runbook
    assert manifest["status"] == "passed"
    assert any(step["name"] == "load-sources" for step in manifest["steps"])


def test_latest_artifacts_reports_created_pilot_files(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    package = build_live_test_package(config, week="2026-W20", include_dry_run=False)

    artifacts = latest_artifacts(config)

    assert artifacts["approval_qa_report"]
    assert artifacts["approval_deployment_package"]
    assert artifacts["manual_posting_package"]
    assert Path(package.runbook_path).exists()


def test_ui_dashboard_exposes_overview_readiness_and_artifacts():
    server, thread = _start_test_server()
    port = server.server_port
    try:
        overview = _fetch_json(f"http://127.0.0.1:{port}/api/overview")
        readiness = _fetch_json(f"http://127.0.0.1:{port}/api/live-readiness")
        artifacts = _fetch_json(f"http://127.0.0.1:{port}/api/artifacts")
        integrations = _fetch_json(f"http://127.0.0.1:{port}/api/integration-status")

        assert "counts" in overview
        assert "stage" in readiness
        assert "items" in readiness
        assert "review_packets" in artifacts
        assert integrations["blocked_paid_capable_count"] >= 1
    finally:
        server.shutdown()
        server.server_close()


def test_ui_html_contains_live_testing_controls():
    html = Path("ui/index.html").read_text()

    assert "Live Testing Readiness" in html
    assert "Build Live Test Package" in html
    assert "/api/live-readiness" in html
    assert "/api/build-live-test-package" in html
