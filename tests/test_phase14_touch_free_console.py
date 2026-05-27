import json
import os
import threading
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

from ai_linkedin_automation.business_console import (
    build_approval_setup_guide,
    build_desktop_launcher_package,
    business_home,
    install_desktop_icon,
    run_functional_diagnostics,
    run_touch_free_setup,
)
from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.ingestion.sources import load_sources_from_config
from ai_linkedin_automation.storage.db import init_db
from ai_linkedin_automation.ui_server import UIRequestHandler


def _config(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.delenv("GOOGLE_APPS_SCRIPT_WEBAPP_URL", raising=False)
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


def test_desktop_launcher_package_creates_app_bundle_without_terminal(tmp_path):
    package = build_desktop_launcher_package(root_path=tmp_path)

    executable = Path(package.executable_path)
    command = Path(package.command_path)

    assert Path(package.app_path).exists()
    assert executable.exists()
    assert command.exists()
    assert os.access(executable, os.X_OK)
    assert os.access(command, os.X_OK)
    launcher_text = executable.read_text()
    assert "--port \"$PORT\"" in launcher_text
    assert "desktop_console.log" in launcher_text
    assert "/api/version" in launcher_text
    assert "touch_free_locus_v2" in launcher_text
    assert "disown \"$SERVER_PID\"" in launcher_text
    assert "open \"$URL\"" in launcher_text
    assert "No terminal needed" in package.instructions


def test_install_desktop_icon_copies_app_bundle_to_desktop_folder(tmp_path):
    root = tmp_path / "project"
    desktop = tmp_path / "Desktop"
    root.mkdir()

    result = install_desktop_icon(root_path=root, desktop_dir=desktop)

    desktop_app = desktop / "AI LinkedIn Console.app"
    desktop_executable = desktop_app / "Contents" / "MacOS" / "AI LinkedIn Console"
    assert result.status == "ready"
    assert Path(result.desktop_icon_path) == desktop_app
    assert desktop_executable.exists()
    assert os.access(desktop_executable, os.X_OK)
    assert f'APP_DIR="{root}"' in desktop_executable.read_text()
    assert '../../..' not in desktop_executable.read_text()


def test_touch_free_setup_builds_console_testing_and_deployment_artifacts(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    report = run_touch_free_setup(
        config,
        week="2026-W20",
        include_approval_qa=True,
        launcher_root=tmp_path / "desktop",
    )

    assert report.status in {
        "ready_with_manual_approval_setup",
        "ready_for_touch_free_operation",
    }
    assert Path(report.markdown_path).exists()
    assert Path(report.output_paths["desktop_app"]).exists()
    assert Path(report.output_paths["approval_deployment_checklist"]).exists()
    assert Path(report.output_paths["approval_qa_report"]).exists()
    assert Path(report.output_paths["schedule_runbook"]).exists()
    assert {step.key for step in report.steps} >= {
        "desktop_launcher",
        "approval_deployment",
        "approval_qa",
        "schedule_package",
        "pilot_checklist",
    }


def test_approval_setup_guide_tracks_human_google_gate(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    run_touch_free_setup(
        config,
        week="2026-W20",
        include_approval_qa=True,
        launcher_root=tmp_path / "desktop",
    )

    guide = build_approval_setup_guide(config)

    assert guide.status == "needs_google_deployment"
    assert guide.deployment_package_ready is True
    assert guide.local_approval_qa_ready is True
    assert guide.apps_script_deployed is False
    assert guide.approval_url_configured is False
    assert Path(guide.markdown_path).exists()
    assert {step.key for step in guide.steps} >= {
        "deployment_package",
        "google_sheet",
        "apps_script",
        "approval_url",
        "local_qa",
    }


def test_functional_diagnostics_reports_core_modules_and_integrations(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    build_desktop_launcher_package(root_path=Path.cwd())

    report = run_functional_diagnostics(config)

    assert report.status in {"passed", "passed_with_warnings"}
    assert Path(report.markdown_path).exists()
    by_name = {check.name: check for check in report.checks}
    assert by_name["SQLite database"].status == "pass"
    assert by_name["Integration guardrails"].status == "pass"
    assert "Desktop launcher" in by_name


def test_business_home_exposes_plain_english_steps_and_desktop_status(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    home = business_home(config)

    assert home.guided_steps
    assert home.desktop_launcher["instructions"].endswith("No terminal needed.")
    assert all("ai-linkedin" not in step["next_action"] for step in home.guided_steps)


def test_ui_html_contains_touch_free_business_controls():
    html = Path("ui/index.html").read_text()

    assert "Touch-Free Control Center" in html
    assert "Workflow Navigation" in html
    assert 'id="sideNav"' in html
    assert 'id="start"' in html
    assert 'id="setup"' in html
    assert 'id="weekly-pilot"' in html
    assert 'id="approval"' in html
    assert 'id="posting"' in html
    assert 'id="progress"' in html
    assert 'id="artifacts"' in html
    assert 'id="activity"' in html
    assert "Weekly Pilot" in html
    assert "Artifact Viewer" in html
    assert "No terminal needed" in html
    assert "Prepare Everything" in html
    assert "Plain-English Steps" in html
    assert "/api/business/run-touch-free-setup" in html
    assert "/api/business/build-desktop-launcher" in html
    assert "/api/business/install-desktop-icon" in html
    assert "/api/business/run-functional-diagnostics" in html
    assert "/api/business/approval-setup-guide" in html
    assert "/api/business/run-approval-qa" in html
    assert "Copy Code.gs" in html
    assert "Copy Index.html" in html
    assert "Copy appsscript.json" in html
    assert "Open New Google Sheet" in html
    assert "Copy Sheet Header for Cell A1" in html
    assert "Rename the bottom tab from Sheet1 to ReviewQueue" in html
    assert "Sync to Phone Approval" in html
    assert "Verify Phone App" in html
    assert "Copy Sync Token" in html
    assert "Import Phone Decision" in html
    assert "Paste location:</strong> Apps Script editor -> Code.gs file." in html
    assert "Apps Script editor -> new HTML file named Index" in html
    assert "Web app URL that ends with /exec" in html
    assert "Approve Locally & Build Package" in html
    assert "Run Full E2E Test" in html
    assert "Run Locus E2E" in html
    assert "/api/business/approve-locally" in html
    assert "/api/business/sync-review-queue-to-webapp" in html
    assert "/api/business/import-webapp-decisions" in html
    assert "/api/business/verify-approval-webapp" in html
    assert "/api/business/approval-sync-setup" in html
    assert "/api/business/run-application-e2e-test" in html
    assert "/api/business/run-locus-e2e-test" in html
    assert "Use local approval for the least maintenance" in html


def test_desktop_launcher_endpoint_contract():
    server, thread = _start_test_server()
    port = server.server_port
    try:
        data = _fetch_json(f"http://127.0.0.1:{port}/api/business/desktop-launcher")

        assert "ready" in data
        assert data["app_path"].endswith("AI LinkedIn Console.app")
        assert "No terminal needed" in data["instructions"]
    finally:
        server.shutdown()
        server.server_close()
