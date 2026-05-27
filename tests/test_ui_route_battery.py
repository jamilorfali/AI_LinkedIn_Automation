import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

from ai_linkedin_automation.ui_server import UIRequestHandler


def _start_test_server():
    try:
        server = HTTPServer(("127.0.0.1", 0), UIRequestHandler)
    except PermissionError as exc:
        pytest.skip(f"Local socket binding is not available in this environment: {exc}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _request_json(base_url, method, path, payload=None, expected_status=200, timeout=120):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            assert response.status == expected_status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        assert exc.code == expected_status, body
    return json.loads(body) if body.strip().startswith(("{", "[")) else body


@pytest.fixture(autouse=True)
def _disable_external_phone_sync(monkeypatch):
    monkeypatch.setenv("GOOGLE_APPS_SCRIPT_WEBAPP_URL", "")
    monkeypatch.setenv("GOOGLE_APPS_SCRIPT_SYNC_TOKEN", "qa_redacted_existing_token")


def test_ui_route_battery_get_routes():
    server = _start_test_server()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        html = _request_json(base_url, "GET", "/")
        assert "AI LinkedIn" in html

        route_expectations = {
            "/api/status": "app",
            "/api/version": "launcher_contract",
            "/api/overview": "status",
            "/api/preflight": "checks",
            "/api/live-readiness": "items",
            "/api/integration-status": "items",
            "/api/locus-status": "engine",
            "/api/locus-capability-check": "checks",
            "/api/locus-workbench-package": "manifest_path",
            "/api/artifacts": "review_packets",
            "/api/business/home": "next_action",
            "/api/business/latest-production-test": None,
            "/api/business/approval-deployment": None,
            "/api/business/approval-setup-guide": "steps",
            "/api/business/desktop-launcher": "ready",
            "/api/business/topic-board": "categories",
            "/api/pilot-checklist": "items",
            "/api/config-files": "files",
            "/api/config?file=app.yaml": "content",
        }
        for route, expected_key in route_expectations.items():
            payload = _request_json(base_url, "GET", route)
            assert isinstance(payload, dict), route
            if expected_key:
                assert expected_key in payload, route

        sync = _request_json(base_url, "GET", "/api/business/approval-sync-setup")
        assert sync["status"] == "ready"
        assert sync["sync_token"] == "qa_redacted_existing_token"
    finally:
        server.shutdown()
        server.server_close()


def test_ui_route_battery_workflow_and_button_routes():
    server = _start_test_server()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert _request_json(base_url, "POST", "/api/init-db", {})["result"]
        assert _request_json(base_url, "POST", "/api/load-sources", {})["result"]
        assert _request_json(base_url, "POST", "/api/ingest", {"dry_run": True})["result"]
        assert _request_json(base_url, "POST", "/api/score", {})["result"]

        assert _request_json(
            base_url,
            "POST",
            "/api/run-daily-scan",
            {"dry_run": True},
        )["result"] == "completed"
        assert _request_json(
            base_url,
            "POST",
            "/api/run-friday-package",
            {"week": "current", "dry_run": True},
        )["result"] == "completed"
        assert _request_json(
            base_url,
            "POST",
            "/api/build-live-test-package",
            {"week": "current", "include_dry_run": True},
        )["result"] in {"passed", "ready", "ready_with_warnings"}
        assert _request_json(
            base_url,
            "POST",
            "/api/run-production-pilot",
            {"week": "current", "dry_run": True},
        )["result"] in {"passed", "passed_with_warnings"}

        package = _request_json(
            base_url,
            "POST",
            "/api/build-production-test-package",
            {"week": "current"},
            timeout=180,
        )
        assert package["draft_id"]

        runbook_route = "/api/business/artifact-content?" + urllib.parse.urlencode(
            {"path": package["runbook_path"]}
        )
        assert _request_json(base_url, "GET", runbook_route)["content"]

        preset = _request_json(
            base_url,
            "POST",
            "/api/business/apply-draft-preset",
            {"week": "current", "draft_id": package["draft_id"], "preset": "shorter"},
        )
        assert preset["status"] in {"revised", "updated", "unchanged"}

        checklist = _request_json(
            base_url,
            "POST",
            "/api/update-pilot-checklist",
            {"key": "weekly_candidates_reviewed", "status": "done", "notes": "QA source review."},
        )
        assert checklist["result"] == "updated"

        approval = _request_json(
            base_url,
            "POST",
            "/api/business/approve-locally",
            {
                "draft_id": "",
                "action": "approve_text_only",
                "notes": "QA local approval smoke.",
                "build_package": True,
            },
            timeout=180,
        )
        assert approval["manual_package_path"]
        assert _request_json(base_url, "POST", "/api/business/build-manual-package", {})["path"]
        assert _request_json(base_url, "POST", "/api/business/generate-post-image", {})[
            "image_path"
        ].endswith(".png")
        archive_block = _request_json(
            base_url,
            "POST",
            "/api/business/archive-post",
            {"draft_id": "", "post_url": "", "final_text": "", "engagement_snapshot": ""},
            expected_status=500,
        )
        assert "Post URL is required" in archive_block["error"]

        qa = _request_json(
            base_url,
            "POST",
            "/api/business/run-approval-qa",
            {"action": "approve_text_only", "week": "current"},
            timeout=180,
        )
        assert qa["status"] == "passed"
        csv_content = Path(qa["simulated_sheet_csv"]).read_text()
        validation = _request_json(
            base_url,
            "POST",
            "/api/business/validate-review-queue-content",
            {"csv_content": csv_content},
        )
        assert validation["decision_rows"] >= 1
        imported = _request_json(
            base_url,
            "POST",
            "/api/business/import-review-queue-content",
            {"csv_content": csv_content},
        )
        assert "validation" in imported
        assert imported["validation"]["decision_rows"] >= 1

        assert _request_json(
            base_url,
            "POST",
            "/api/business/build-approval-deployment-package",
            {"week": "current"},
        )["result"] == "created"
        assert _request_json(base_url, "POST", "/api/business/build-desktop-launcher", {})[
            "status"
        ] == "ready"
        assert _request_json(base_url, "POST", "/api/business/build-schedule-package", {})[
            "result"
        ] == "created"
        assert _request_json(base_url, "POST", "/api/business/run-functional-diagnostics", {})[
            "status"
        ] in {"failed", "passed", "passed_with_warnings"}
        assert _request_json(
            base_url,
            "POST",
            "/api/business/run-locus-e2e-test",
            {"week": "current"},
            timeout=240,
        )["status"] in {"passed", "passed_with_warnings"}
        assert _request_json(
            base_url,
            "POST",
            "/api/business/run-application-e2e-test",
            {"week": "current", "approval_action": "approve_text_only"},
            timeout=240,
        )["status"] in {"failed", "passed", "passed_with_warnings"}

        assert _request_json(
            base_url,
            "POST",
            "/api/business/build-next-topic-package",
            {"week": "current"},
            timeout=180,
        )["draft_id"]
        assert _request_json(
            base_url,
            "POST",
            "/api/business/build-topic-package",
            {"week": "current", "query": "QA smoke test topic on practical AI governance"},
            timeout=180,
        )["draft_id"]
        refresh = _request_json(
            base_url,
            "POST",
            "/api/business/full-refresh-topics",
            {"week": "current"},
        )
        assert refresh["status"] == "refreshed"
        assert _request_json(base_url, "POST", "/api/business/undo-topic-refresh", {})[
            "status"
        ] == "undone"

        # External/cloud-adjacent routes are safe-failure tested with env disabled.
        assert "Save the Google Apps Script" in _request_json(
            base_url,
            "GET",
            "/api/business/verify-approval-webapp",
            expected_status=500,
        )["error"]
        assert "Save the Google Apps Script" in _request_json(
            base_url,
            "POST",
            "/api/business/sync-review-queue-to-webapp",
            {"week": "current"},
            expected_status=500,
        )["error"]
        assert "Save the Google Apps Script" in _request_json(
            base_url,
            "POST",
            "/api/business/import-webapp-decisions",
            {"week": "current", "build_package": True},
            expected_status=500,
        )["error"]
    finally:
        server.shutdown()
        server.server_close()
