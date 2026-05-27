import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import io
import contextlib
import argparse
import threading
import webbrowser

from ai_linkedin_automation.approval import (
    generate_approval_token,
    get_token_id_from_token,
    hash_token,
    mark_token_used,
    record_approval,
    store_approval_token,
    validate_approval_token,
)
from ai_linkedin_automation.approval_webapp.deployment import build_deployment_package
from ai_linkedin_automation.business_console import (
    approval_sync_setup,
    apply_draft_preset,
    approve_latest_draft_locally,
    archive_latest_post,
    build_safe_post_image,
    build_next_topic_package,
    build_topic_package,
    build_approval_setup_guide,
    build_desktop_launcher_package,
    build_latest_manual_package,
    business_home,
    desktop_launcher_status,
    full_refresh_topics,
    import_review_queue_content,
    install_desktop_icon,
    import_webapp_decisions,
    latest_approval_deployment_bundle,
    latest_production_test,
    read_artifact,
    refresh_latest_approval_assets,
    reset_source_review_for_new_candidate,
    run_application_e2e_test,
    run_functional_diagnostics,
    run_locus_e2e_test,
    run_touch_free_setup,
    save_approval_url,
    sync_review_queue_to_webapp,
    topic_board,
    undo_full_refresh_topics,
    validate_review_queue_content,
    verify_approval_webapp,
)
from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.drafting import generate_draft_from_weekly_package, save_draft
from ai_linkedin_automation.integrations.status import collect_integration_status
from ai_linkedin_automation.ingestion.ingest import run_ingestion
from ai_linkedin_automation.ingestion.sources import load_sources_from_config
from ai_linkedin_automation.locus_workflows import (
    build_locus_workbench_package,
    collect_locus_status,
    render_locus_status,
    run_locus_capability_check,
)
from ai_linkedin_automation.operations.preflight import format_preflight_report, run_preflight
from ai_linkedin_automation.operations.workflows import run_daily_scan, run_friday_package
from ai_linkedin_automation.pilot.checklist import build_pilot_checklist, update_pilot_checklist_item
from ai_linkedin_automation.pilot.live_test import build_live_test_package
from ai_linkedin_automation.pilot.live_pilot import run_production_pilot
from ai_linkedin_automation.pilot.production_test import build_production_test_package
from ai_linkedin_automation.pilot.readiness import build_readiness_report
from ai_linkedin_automation.pilot.sheet_validation import validate_review_queue_csv
from ai_linkedin_automation.scoring.scoring import score_all_findings
from ai_linkedin_automation.storage.db import init_db

REPO_ROOT = Path(__file__).parents[2]
UI_DIR = REPO_ROOT / "ui"
CONFIG_DIR = REPO_ROOT / "config"
LAUNCHER_CONTRACT = "touch_free_locus_v2"
ALLOWED_CONFIG_FILES = [
    "app.yaml",
    "blocked_topics.yaml",
    "cost_guard.yaml",
    "integrations.yaml",
    "provider_registry.yaml",
    "publishing.yaml",
    "scoring.yaml",
    "scoring_weights.yaml",
    "sources.yaml",
    "style_rules.yaml",
    "trusted_domains.yaml",
    "weekly_schedule.yaml",
]


def capture_call(func, *args, **kwargs):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = func(*args, **kwargs)
    return result, buffer.getvalue().strip()


def resolve_config_file(name: str) -> Path:
    if name not in ALLOWED_CONFIG_FILES:
        raise ValueError(f"Config file not allowed: {name}")
    return CONFIG_DIR / name


def read_json_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    body = handler.rfile.read(length).decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return parse_qs(body)


def _latest_files(root: Path, pattern: str, limit: int = 10):
    if not root.exists():
        return []
    files = sorted(
        [path for path in root.glob(pattern) if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return [
        {
            "path": str(path),
            "name": path.name,
            "modified_at": path.stat().st_mtime,
        }
        for path in files[:limit]
    ]


def _db_counts(config):
    from ai_linkedin_automation.storage.db import connect_db

    counts = {}
    try:
        conn = connect_db(config.storage.sqlite_path)
        for table in [
            "sources",
            "findings",
            "topics",
            "drafts",
            "approval_tokens",
            "approvals",
            "posts",
            "content_clusters",
            "discovery_queue",
            "citation_matrix_rows",
        ]:
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        conn.close()
    except Exception as exc:
        counts["error"] = str(exc)
    return counts


class UIRequestHandler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        payload = json.dumps(data, indent=2)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(payload.encode("utf-8"))

    def send_text(self, text, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(text.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(text.encode("utf-8"))

    def send_binary(self, data, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self.serve_ui_file("index.html")
        if parsed.path.startswith("/api/"):
            return self.handle_api_get(parsed)
        return self.send_error(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.handle_api_post(parsed)
        return self.send_error(404, "Not found")

    def serve_ui_file(self, filename: str):
        file_path = UI_DIR / filename
        if not file_path.exists():
            return self.send_error(404, "Page not found")
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def handle_api_get(self, parsed):
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path == "/api/status":
                config = load_config()
                self.send_json({
                    "app": config.app.name,
                    "run_mode": config.app.default_run_mode,
                    "timezone": config.app.timezone,
                    "database": config.storage.sqlite_path,
                })
            elif path == "/api/version":
                config = load_config()
                self.send_json(
                    {
                        "app": config.app.name,
                        "launcher_contract": LAUNCHER_CONTRACT,
                        "console": "AI LinkedIn Console",
                        "features": [
                            "touch_free_setup",
                            "approval_setup_coach",
                            "locus_stategraph",
                            "locus_workbench_export",
                        ],
                    }
                )
            elif path == "/api/overview":
                config = load_config()
                self.send_json(
                    {
                        "status": {
                            "app": config.app.name,
                            "run_mode": config.app.default_run_mode,
                            "timezone": config.app.timezone,
                            "database": config.storage.sqlite_path,
                        },
                        "counts": _db_counts(config),
                    }
                )
            elif path == "/api/preflight":
                config = load_config()
                report = run_preflight(config)
                self.send_json(
                    {
                        "ok": report.ok,
                        "generated_at": report.generated_at,
                        "checks": [check.__dict__ for check in report.checks],
                        "text": format_preflight_report(report),
                    }
                )
            elif path == "/api/live-readiness":
                config = load_config()
                report = build_readiness_report(config, write_files=False)
                self.send_json(
                    {
                        "stage": report.live_testing_stage,
                        "decision": report.decision,
                        "fail_count": report.fail_count,
                        "warn_count": report.warn_count,
                        "items": [item.__dict__ for item in report.items],
                        "counts": report.counts,
                        "latest_artifacts": report.latest_artifacts,
                    }
                )
            elif path == "/api/integration-status":
                config = load_config()
                report = collect_integration_status(config)
                self.send_json(
                    {
                        "run_mode": report.run_mode,
                        "monthly_spend_cap_usd": report.monthly_spend_cap_usd,
                        "blocked_paid_capable_count": report.blocked_paid_capable_count,
                        "items": [item.__dict__ for item in report.items],
                    }
                )
            elif path == "/api/locus-status":
                config = load_config()
                status = collect_locus_status(config)
                self.send_json({**asdict_safe(status), "text": render_locus_status(status)})
            elif path == "/api/locus-capability-check":
                config = load_config()
                report = run_locus_capability_check(config)
                self.send_json(asdict_safe(report))
            elif path == "/api/locus-workbench-package":
                config = load_config()
                package = build_locus_workbench_package(config)
                self.send_json(asdict_safe(package))
            elif path == "/api/artifacts":
                config = load_config()
                review_root = REPO_ROOT / config.storage.review_packets_dir
                exports_root = REPO_ROOT / config.storage.exports_dir
                self.send_json(
                    {
                        "review_packets": _latest_files(review_root, "**/*.md", 20),
                        "exports": _latest_files(exports_root, "**/*.md", 20),
                        "json_exports": _latest_files(exports_root, "**/*.json", 20),
                    }
                )
            elif path == "/api/business/home":
                config = load_config()
                self.send_json(asdict_safe(business_home(config)))
            elif path == "/api/business/latest-production-test":
                config = load_config()
                self.send_json(latest_production_test(config))
            elif path == "/api/business/approval-deployment":
                config = load_config()
                self.send_json(latest_approval_deployment_bundle(config))
            elif path == "/api/business/approval-setup-guide":
                config = load_config()
                self.send_json(asdict_safe(build_approval_setup_guide(config, write_files=True)))
            elif path == "/api/business/verify-approval-webapp":
                config = load_config()
                self.send_json(verify_approval_webapp(config))
            elif path == "/api/business/approval-sync-setup":
                config = load_config()
                self.send_json(approval_sync_setup(config))
            elif path == "/api/business/desktop-launcher":
                self.send_json(desktop_launcher_status())
            elif path == "/api/business/artifact-content":
                artifact_path = query.get("path", [""])[0]
                if not artifact_path:
                    raise ValueError("path is required")
                self.send_json(read_artifact(artifact_path))
            elif path == "/api/business/topic-board":
                config = load_config()
                self.send_json(topic_board(config))
            elif path == "/api/business/artifact-file":
                artifact_path = query.get("path", [""])[0]
                if not artifact_path:
                    raise ValueError("path is required")
                path_value = Path(artifact_path)
                if not path_value.is_absolute():
                    path_value = REPO_ROOT / path_value
                path_value = path_value.resolve()
                if REPO_ROOT.resolve() not in path_value.parents and path_value != REPO_ROOT.resolve():
                    raise ValueError("Artifact path must be inside the project folder")
                if path_value.suffix.lower() != ".png":
                    raise ValueError("Only PNG image previews are supported")
                self.send_binary(path_value.read_bytes(), "image/png")
            elif path == "/api/pilot-checklist":
                config = load_config()
                checklist = build_pilot_checklist(config, write_files=False)
                self.send_json(
                    {
                        "stage": checklist.stage,
                        "summary": checklist.summary,
                        "done_count": checklist.done_count,
                        "pending_count": checklist.pending_count,
                        "blocked_count": checklist.blocked_count,
                        "attention_count": checklist.attention_count,
                        "items": [item.__dict__ for item in checklist.items],
                    }
                )
            elif path == "/api/config":
                file_name = query.get("file", [""])[0]
                config_path = resolve_config_file(file_name)
                content = config_path.read_text()
                self.send_json({"file": file_name, "content": content})
            elif path == "/api/config-files":
                self.send_json({"files": ALLOWED_CONFIG_FILES})
            else:
                self.send_error(404, "API endpoint not found")
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def handle_api_post(self, parsed):
        path = parsed.path
        payload = read_json_body(self)
        try:
            if path == "/api/init-db":
                config = load_config()
                init_db(config.storage.sqlite_path)
                self.send_json({"result": "Database initialized"})
            elif path == "/api/load-sources":
                config = load_config()
                load_sources_from_config(config)
                self.send_json({"result": "Sources loaded"})
            elif path == "/api/ingest":
                config = load_config()
                dry_run = bool(payload.get("dry_run", False))
                result, output = capture_call(run_ingestion, config, dry_run=dry_run)
                self.send_json({"result": "Ingestion completed", "output": output})
            elif path == "/api/score":
                config = load_config()
                score, output = capture_call(score_all_findings, config)
                self.send_json({"result": "Scored findings", "score_count": score, "output": output})
            elif path == "/api/run-daily-scan":
                config = load_config()
                dry_run = bool(payload.get("dry_run", False))
                report = run_daily_scan(config, dry_run=dry_run)
                self.send_json({"result": report.status, "report_path": report.report_path, "json_path": report.json_path})
            elif path == "/api/run-friday-package":
                config = load_config()
                dry_run = bool(payload.get("dry_run", False))
                week = payload.get("week", "current")
                report = run_friday_package(config, week=week, dry_run=dry_run)
                self.send_json(
                    {
                        "result": report.status,
                        "report_path": report.report_path,
                        "json_path": report.json_path,
                        "output_paths": report.output_paths,
                    }
                )
            elif path == "/api/build-live-test-package":
                config = load_config()
                week = payload.get("week", "current")
                include_dry_run = bool(payload.get("include_dry_run", True))
                package = build_live_test_package(config, week=week, include_dry_run=include_dry_run)
                self.send_json(
                    {
                        "result": package.status,
                        "output_dir": package.output_dir,
                        "runbook_path": package.runbook_path,
                        "manifest_path": package.manifest_path,
                        "readiness_report_path": package.readiness_report_path,
                    }
                )
            elif path == "/api/run-production-pilot":
                config = load_config()
                report = run_production_pilot(
                    config,
                    week=payload.get("week", "current"),
                    dry_run=bool(payload.get("dry_run", False)),
                    require_approval_url=bool(payload.get("require_approval_url", False)),
                )
                self.send_json(
                    {
                        "result": report.status,
                        "readiness_stage": report.readiness_stage,
                        "checklist_stage": report.checklist_stage,
                        "report_path": report.markdown_path,
                        "json_path": report.json_path,
                        "output_paths": report.output_paths,
                    }
                )
            elif path == "/api/build-production-test-package":
                config = load_config()
                package = build_production_test_package(
                    config,
                    week=payload.get("week", "current"),
                    topic_id=payload.get("topic_id") or None,
                )
                reset_source_review_for_new_candidate(
                    config,
                    "Draft package built; review the selected source before approval.",
                )
                self.send_json(
                    {
                        "result": package.status,
                        "selected_topic_id": package.selected_topic_id,
                        "selected_topic_title": package.selected_topic_title,
                        "draft_id": package.draft_id,
                        "output_dir": package.output_dir,
                        "runbook_path": package.runbook_path,
                        "manifest_path": package.manifest_path,
                        "review_queue_path": package.review_queue_path,
                        "notification_text_path": package.notification_text_path,
                        "approval_url_configured": package.approval_url_configured,
                        "candidate_publish_ready": package.candidate_publish_ready,
                    }
                )
            elif path == "/api/business/save-approval-url":
                config = load_config()
                approval_url = payload.get("approval_url", "")
                env_path = save_approval_url(approval_url)
                refresh = refresh_latest_approval_assets(
                    config,
                    week=payload.get("week", "current"),
                )
                self.send_json(
                    {
                        "result": "saved",
                        "env_path": env_path,
                        "summary": "Approval URL saved and the current draft notification was refreshed.",
                        **refresh,
                    }
                )
            elif path == "/api/business/run-touch-free-setup":
                config = load_config()
                report = run_touch_free_setup(
                    config,
                    week=payload.get("week", "current"),
                    include_approval_qa=bool(payload.get("include_approval_qa", True)),
                )
                self.send_json(asdict_safe(report))
            elif path == "/api/business/build-desktop-launcher":
                package = build_desktop_launcher_package()
                self.send_json(asdict_safe(package))
            elif path == "/api/business/install-desktop-icon":
                package = install_desktop_icon()
                self.send_json(asdict_safe(package))
            elif path == "/api/business/run-functional-diagnostics":
                config = load_config()
                report = run_functional_diagnostics(config)
                self.send_json(asdict_safe(report))
            elif path == "/api/business/run-locus-e2e-test":
                config = load_config()
                report = run_locus_e2e_test(config, week=payload.get("week", "current"))
                self.send_json(asdict_safe(report))
            elif path == "/api/business/run-application-e2e-test":
                config = load_config()
                report = run_application_e2e_test(
                    config,
                    week=payload.get("week", "current"),
                    approval_action=payload.get("approval_action", "approve_text_only"),
                    archive_post_url=payload.get("archive_post_url", ""),
                )
                self.send_json(asdict_safe(report))
            elif path == "/api/business/run-approval-qa":
                from ai_linkedin_automation.approval_webapp.qa import run_local_approval_qa

                config = load_config()
                report = run_local_approval_qa(
                    config,
                    action=payload.get("action", "approve_text_only"),
                    week=payload.get("week", "current"),
                )
                self.send_json(asdict_safe(report))
            elif path == "/api/business/build-approval-deployment-package":
                config = load_config()
                package = build_deployment_package(config, week=payload.get("week", "current"))
                self.send_json(
                    {
                        "result": "created",
                        "output_dir": package.output_dir,
                        "script_dir": package.script_dir,
                        "checklist_path": package.checklist_path,
                        "sheet_template_csv": package.sheet_template_csv,
                    }
                )
            elif path == "/api/business/validate-review-queue-content":
                config = load_config()
                report = validate_review_queue_content(config, payload.get("csv_content", ""))
                self.send_json(asdict_safe(report))
            elif path == "/api/business/import-review-queue-content":
                config = load_config()
                result = import_review_queue_content(config, payload.get("csv_content", ""))
                self.send_json(result)
            elif path == "/api/business/sync-review-queue-to-webapp":
                config = load_config()
                result = sync_review_queue_to_webapp(config, week=payload.get("week", "current"))
                self.send_json(result)
            elif path == "/api/business/import-webapp-decisions":
                config = load_config()
                result = import_webapp_decisions(
                    config,
                    week=payload.get("week", "current"),
                    build_package=bool(payload.get("build_package", True)),
                )
                self.send_json(result)
            elif path == "/api/business/approve-locally":
                config = load_config()
                result = approve_latest_draft_locally(
                    config,
                    draft_id=payload.get("draft_id") or None,
                    action=payload.get("action", "approve_text_only"),
                    notes=payload.get("notes", "Approved inside the AI LinkedIn Console."),
                    build_package=bool(payload.get("build_package", True)),
                )
                self.send_json(asdict_safe(result))
            elif path == "/api/business/apply-draft-preset":
                config = load_config()
                result = apply_draft_preset(
                    config,
                    preset=payload.get("preset", ""),
                    draft_id=payload.get("draft_id") or None,
                    week=payload.get("week", "current"),
                )
                self.send_json(asdict_safe(result))
            elif path == "/api/business/build-next-topic-package":
                config = load_config()
                package = build_next_topic_package(config, week=payload.get("week", "current"))
                self.send_json(package)
            elif path == "/api/business/build-topic-package":
                config = load_config()
                package = build_topic_package(
                    config,
                    week=payload.get("week", "current"),
                    topic_id=payload.get("topic_id", ""),
                    query=payload.get("query", ""),
                )
                self.send_json(package)
            elif path == "/api/business/full-refresh-topics":
                config = load_config()
                result = full_refresh_topics(config, week=payload.get("week", "current"))
                self.send_json(result)
            elif path == "/api/business/undo-topic-refresh":
                config = load_config()
                result = undo_full_refresh_topics(config)
                self.send_json(result)
            elif path == "/api/business/build-manual-package":
                config = load_config()
                output_path = build_latest_manual_package(config, payload.get("draft_id") or None)
                self.send_json({"result": "created", "path": output_path})
            elif path == "/api/business/generate-post-image":
                config = load_config()
                result = build_safe_post_image(config, payload.get("draft_id") or None)
                self.send_json(asdict_safe(result))
            elif path == "/api/business/archive-post":
                config = load_config()
                result = archive_latest_post(
                    config,
                    post_url=payload.get("post_url", ""),
                    draft_id=payload.get("draft_id") or None,
                    final_text=payload.get("final_text") or None,
                    engagement_snapshot=payload.get("engagement_snapshot") or None,
                )
                self.send_json({"result": "archived", **result})
            elif path == "/api/business/build-schedule-package":
                from ai_linkedin_automation.operations.schedule import build_local_schedule_package

                config = load_config()
                package = build_local_schedule_package(config)
                self.send_json(
                    {
                        "result": "created",
                        "output_dir": package.output_dir,
                        "runbook_path": package.runbook_path,
                        "daily_plist_path": package.daily_plist_path,
                        "friday_plist_path": package.friday_plist_path,
                    }
                )
            elif path == "/api/update-pilot-checklist":
                config = load_config()
                key = payload.get("key", "")
                status = payload.get("status", "done")
                notes = payload.get("notes", "")
                if not key:
                    raise ValueError("key is required")
                checklist = update_pilot_checklist_item(config, key, status, notes)
                self.send_json(
                    {
                        "result": "updated",
                        "stage": checklist.stage,
                        "summary": checklist.summary,
                        "items": [item.__dict__ for item in checklist.items],
                    }
                )
            elif path == "/api/validate-review-queue":
                csv_path = payload.get("csv_path", "")
                if not csv_path:
                    raise ValueError("csv_path is required")
                candidate = Path(csv_path)
                if not candidate.is_absolute():
                    candidate = REPO_ROOT / candidate
                config = load_config()
                report = validate_review_queue_csv(config, str(candidate))
                self.send_json(
                    {
                        "ok": report.ok,
                        "fail_count": report.fail_count,
                        "warn_count": report.warn_count,
                        "decision_rows": report.decision_rows,
                        "pending_rows": report.pending_rows,
                        "report_path": report.markdown_path,
                        "json_path": report.json_path,
                        "issues": [issue.__dict__ for issue in report.issues],
                    }
                )
            elif path == "/api/draft":
                weekly_path = payload.get("weekly_package_path", "")
                topic_id = payload.get("topic_id", "")
                if not weekly_path or not topic_id:
                    raise ValueError("weekly_package_path and topic_id are required")
                weekly_file = Path(weekly_path)
                if not weekly_file.is_absolute():
                    weekly_file = REPO_ROOT / weekly_file
                draft = generate_draft_from_weekly_package(str(weekly_file))
                config = load_config()
                draft_id = save_draft(config.storage.sqlite_path, topic_id, draft)
                self.send_json({"draft_id": draft_id, "content": draft})
            elif path == "/api/generate-approval":
                draft_id = payload.get("draft_id", "")
                if not draft_id:
                    raise ValueError("draft_id is required")
                config = load_config()
                token = generate_approval_token(draft_id)
                token_hash = hash_token(token)
                token_id = store_approval_token(config.storage.sqlite_path, draft_id, token_hash)
                self.send_json({"draft_id": draft_id, "token": token, "token_id": token_id})
            elif path == "/api/approve":
                token = payload.get("token", "")
                action = payload.get("action", "")
                notes = payload.get("notes")
                if not token or not action:
                    raise ValueError("token and action are required")
                config = load_config()
                is_valid, draft_id = validate_approval_token(config.storage.sqlite_path, token)
                if not is_valid:
                    raise ValueError("Invalid or expired token")
                token_id = get_token_id_from_token(config.storage.sqlite_path, token)
                if token_id is None:
                    raise ValueError("Token record not found")
                record_approval(config.storage.sqlite_path, token_id, action, notes)
                mark_token_used(config.storage.sqlite_path, token)
                self.send_json({"result": f"Draft {draft_id} {action}d"})
            elif path == "/api/config":
                file_name = payload.get("file", "")
                content = payload.get("content", "")
                config_path = resolve_config_file(file_name)
                config_path.write_text(content)
                self.send_json({"result": f"Saved {file_name}"})
            else:
                self.send_error(404, "API endpoint not found")
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def log_message(self, format, *args):
        return


def asdict_safe(value):
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict

        return asdict(value)
    return value


def run_server(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = False):
    server = HTTPServer((host, port), UIRequestHandler)
    url = f"http://{host}:{server.server_port}/"
    print(f"Serving UI at {url}")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI LinkedIn Automation local console")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, open_browser=args.open_browser)
