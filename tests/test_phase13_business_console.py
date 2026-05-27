import json
import os
import sqlite3
import threading
import urllib.error
import urllib.request
from io import BytesIO
from http.server import HTTPServer
from pathlib import Path

import pytest

from ai_linkedin_automation.approval_webapp.qa import run_local_approval_qa
from ai_linkedin_automation.approval_webapp.qa import _insert_fixture, _simulate_sheet_action
from ai_linkedin_automation.business_console import (
    business_home,
    import_webapp_decisions,
    import_review_queue_content,
    read_artifact,
    refresh_latest_approval_assets,
    save_env_value,
    save_approval_url,
    sync_review_queue_to_webapp,
    verify_approval_webapp,
)
from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.ingestion.sources import load_sources_from_config
from ai_linkedin_automation.notifications.packages import build_notification_package
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


def _qa_config(base_config, qa_dir: str):
    config = load_config()
    config.storage.sqlite_path = str(Path(qa_dir) / "qa.db")
    config.storage.review_packets_dir = str(Path(qa_dir) / "review_packets")
    config.storage.exports_dir = base_config.storage.exports_dir
    config.storage.logs_dir = base_config.storage.logs_dir
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


class _JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class _JsonResponseRaw:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def test_save_env_value_updates_existing_key_without_touching_others(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("OTHER=value\nGOOGLE_APPS_SCRIPT_WEBAPP_URL=https://old.example\n")

    save_env_value(env_path, "GOOGLE_APPS_SCRIPT_WEBAPP_URL", "https://new.example")

    assert env_path.read_text().splitlines() == [
        "OTHER=value",
        "GOOGLE_APPS_SCRIPT_WEBAPP_URL=https://new.example",
    ]


def test_save_approval_url_rejects_non_https(tmp_path):
    with pytest.raises(ValueError):
        save_approval_url("http://not-safe.example", env_path=tmp_path / ".env")


def test_refresh_latest_approval_assets_adds_magic_link_to_notification(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    conn = sqlite3.connect(config.storage.sqlite_path)
    try:
        conn.execute(
            """
            INSERT INTO sources (
                id, name, type, source_type, trust_tier, url, rss_url,
                is_active, recurring_enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "source-url-refresh",
                "Pew Research Center",
                "public_web",
                "public_web",
                "high_trust",
                "https://www.pewresearch.org/topic/internet-technology/artificial-intelligence/",
                None,
                1,
                1,
                "2026-05-18",
                "2026-05-18",
            ),
        )
        conn.execute(
            """
            INSERT INTO findings (
                id, source_id, url, title, summary, content_hash, raw_content,
                score, category, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "finding-url-refresh",
                "source-url-refresh",
                "https://www.pewresearch.org/topic/internet-technology/artificial-intelligence/",
                "Why employee trust matters as much as AI capability",
                "A business friendly source about AI trust and accountability.",
                "finding-url-refresh-hash",
                "A business friendly source about AI trust and accountability.",
                18,
                "high_impact",
                "2026-05-18",
            ),
        )
        conn.execute(
            """
            INSERT INTO topics (
                id, week_id, title, summary, executive_relevance, hidden_gem_value,
                technical_signal, source_credibility, oracle_safe_fit, draft_readiness,
                weighted_score, political_risk, recommendation, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "topic-url-refresh",
                "2026-W21",
                "Why employee trust matters as much as AI capability",
                "A business friendly source about AI trust and accountability.",
                5,
                4,
                3,
                5,
                5,
                4,
                4.6,
                "low",
                "draft_now",
                "candidate",
                "2026-05-18",
                "2026-05-18",
            ),
        )
        conn.execute(
            "INSERT INTO topic_findings (topic_id, finding_id) VALUES (?, ?)",
            ("topic-url-refresh", "finding-url-refresh"),
        )
        conn.execute(
            """
            INSERT INTO drafts (id, topic_id, version, content, content_hash, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "draft-url-refresh",
                "topic-url-refresh",
                1,
                "AI trust matters because teams need clear human approval habits.",
                "draft-url-refresh-hash",
                "pending_approval",
                "2026-05-18",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    latest_dir = Path(config.storage.exports_dir) / "production_tests"
    latest_dir.mkdir(parents=True, exist_ok=True)
    (latest_dir / "latest.json").write_text(json.dumps({"draft_id": "draft-url-refresh"}, indent=2))
    save_approval_url("https://script.google.com/macros/s/test-refresh/exec", env_path=tmp_path / ".env")

    result = refresh_latest_approval_assets(config, week="2026-W21")

    assert result["approval_url_configured"] is True
    notification_text = Path(result["notification_text_path"]).read_text()
    assert "https://script.google.com/macros/s/test-refresh/exec?rid=" in notification_text
    latest = json.loads((latest_dir / "latest.json").read_text())
    assert latest["approval_url_configured"] is True
    assert latest["notification_text_path"] == result["notification_text_path"]


def test_business_home_returns_non_terminal_next_action(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    home = business_home(config)

    assert home.next_action.button_text
    assert home.next_action.endpoint.startswith("/api/")
    assert "terminal" not in home.next_action.description.lower()


def test_import_review_queue_content_accepts_pasted_sheet_csv(tmp_path, monkeypatch):
    base_config = _config(tmp_path, monkeypatch)
    qa = run_local_approval_qa(base_config, action="approve_text_only", week="2026-W20")
    config = _qa_config(base_config, qa.qa_dir)
    csv_content = Path(qa.simulated_sheet_csv).read_text()

    result = import_review_queue_content(config, csv_content)

    assert result["imported"] == 0
    assert result["errors"] == []
    assert result["validation"]["decision_rows"] == 1


def test_sync_review_queue_to_webapp_posts_current_csv(tmp_path, monkeypatch):
    base_config = _config(tmp_path, monkeypatch)
    qa = run_local_approval_qa(base_config, action="approve_text_only", week="2026-W20")
    config = _qa_config(base_config, qa.qa_dir)
    monkeypatch.setenv("GOOGLE_APPS_SCRIPT_WEBAPP_URL", "https://script.google.com/macros/s/test/exec")
    monkeypatch.setenv("GOOGLE_APPS_SCRIPT_SYNC_TOKEN", "test-sync-token")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _JsonResponse({"ok": True, "total_rows": 1, "decision_rows": 0})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = sync_review_queue_to_webapp(config, week="2026-W20")

    assert result["status"] == "synced"
    assert captured["payload"]["mode"] == "sync_queue"
    assert captured["payload"]["sync_token"] == "test-sync-token"
    assert "review_id,draft_id,draft_version" in captured["payload"]["csv_content"]


def test_sync_review_queue_to_webapp_turns_google_401_html_into_plain_english(
    tmp_path,
    monkeypatch,
):
    base_config = _config(tmp_path, monkeypatch)
    qa = run_local_approval_qa(base_config, action="approve_text_only", week="2026-W20")
    config = _qa_config(base_config, qa.qa_dir)
    monkeypatch.setenv("GOOGLE_APPS_SCRIPT_WEBAPP_URL", "https://script.google.com/macros/s/test/exec")
    monkeypatch.setenv("GOOGLE_APPS_SCRIPT_SYNC_TOKEN", "test-sync-token")
    html = b'<!DOCTYPE html><html><head><title>Page Not Found</title></head><body>Page Not Found</body></html>'

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            hdrs=None,
            fp=BytesIO(html),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as excinfo:
        sync_review_queue_to_webapp(config, week="2026-W20")

    message = str(excinfo.value)
    assert "Access to Anyone" in message
    assert "saved /exec URL can stay the same" in message
    assert "<!DOCTYPE" not in message
    assert "<html" not in message


def test_verify_approval_webapp_detects_old_code_html(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch)
    monkeypatch.setenv("GOOGLE_APPS_SCRIPT_WEBAPP_URL", "https://script.google.com/macros/s/test/exec")
    html = b"<html><body><h1>Error</h1><p>Missing review parameters.</p></body></html>"

    def fake_urlopen(url, timeout):
        assert "mode=health" in url
        return _JsonResponseRaw(html)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = verify_approval_webapp()

    assert result["ok"] is False
    assert result["status"] == "old_code_running"
    assert "function syncReviewQueue_" in result["summary"]


def test_verify_approval_webapp_accepts_sync_capable_health(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch)
    monkeypatch.setenv("GOOGLE_APPS_SCRIPT_WEBAPP_URL", "https://script.google.com/macros/s/test/exec")

    def fake_urlopen(url, timeout):
        assert "mode=health" in url
        return _JsonResponse({"ok": True, "sync_enabled": True, "sheet_name": "ReviewQueue"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = verify_approval_webapp()

    assert result["ok"] is True
    assert result["status"] == "ready"


def test_import_webapp_decisions_imports_without_manual_csv(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    draft_id = _insert_fixture(config)
    notification = build_notification_package(config, draft_id, week="2026-W20")
    approved_csv = tmp_path / "approved_review_queue.csv"
    _simulate_sheet_action(notification.review_queue_path, approved_csv, "approve_text_only", "Approved by phone.")
    monkeypatch.setenv("GOOGLE_APPS_SCRIPT_WEBAPP_URL", "https://script.google.com/macros/s/test/exec")
    monkeypatch.setenv("GOOGLE_APPS_SCRIPT_SYNC_TOKEN", "test-sync-token")

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["mode"] == "export_decisions"
        assert payload["sync_token"] == "test-sync-token"
        return _JsonResponse(
            {
                "ok": True,
                "total_rows": 1,
                "decision_rows": 1,
                "csv_content": approved_csv.read_text(),
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = import_webapp_decisions(config, week="2026-W20", build_package=True)

    assert result["imported"] == 1
    assert result["errors"] == []
    assert Path(result["manual_package_path"]).exists()


def test_read_artifact_rejects_paths_outside_project():
    with pytest.raises(ValueError):
        read_artifact("/etc/hosts")


def test_business_console_html_and_launcher_exist():
    html = Path("ui/index.html").read_text()
    launcher = Path("Launch AI LinkedIn Console.command")

    assert "Next Best Action" in html
    assert "Phone Approval Sync" in html
    assert "Verify Phone App" in html
    assert "Copy Sync Token" in html
    assert "/api/business/home" in html
    assert "/api/business/approval-deployment" in html
    assert "/api/business/import-review-queue-content" in html
    assert "/api/business/sync-review-queue-to-webapp" in html
    assert "/api/business/import-webapp-decisions" in html
    assert "/api/business/verify-approval-webapp" in html
    assert "/api/business/approval-sync-setup" in html
    assert launcher.exists()
    assert os.access(launcher, os.X_OK)


def test_business_home_endpoint_contract():
    server, thread = _start_test_server()
    port = server.server_port
    try:
        data = _fetch_json(f"http://127.0.0.1:{port}/api/business/home")

        assert "next_action" in data
        assert "checklist" in data
        assert "latest_artifacts" in data
    finally:
        server.shutdown()
        server.server_close()
