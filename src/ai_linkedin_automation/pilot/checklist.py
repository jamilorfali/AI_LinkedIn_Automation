import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from ai_linkedin_automation.config import Config, resolve_project_path
from ai_linkedin_automation.pilot.readiness import latest_artifacts
from ai_linkedin_automation.storage.db import connect_db


CHECKLIST_STATUSES = {"pending", "done", "blocked", "attention"}


@dataclass(frozen=True)
class PilotChecklistDefinition:
    key: str
    label: str
    phase: str
    required_for: str
    next_action: str
    auto_status: Optional[Callable[[Config, Dict[str, int], Dict[str, str]], str]] = None
    auto_details: Optional[Callable[[Config, Dict[str, int], Dict[str, str]], str]] = None


@dataclass
class PilotChecklistItem:
    key: str
    label: str
    phase: str
    required_for: str
    status: str
    details: str
    next_action: str
    notes: str = ""
    updated_at: str = ""
    manual_override: bool = False


@dataclass
class PilotChecklist:
    generated_at: str
    stage: str
    summary: str
    items: List[PilotChecklistItem]
    markdown_path: str = ""
    json_path: str = ""
    state_path: str = ""

    @property
    def done_count(self) -> int:
        return sum(1 for item in self.items if item.status == "done")

    @property
    def blocked_count(self) -> int:
        return sum(1 for item in self.items if item.status == "blocked")

    @property
    def attention_count(self) -> int:
        return sum(1 for item in self.items if item.status == "attention")

    @property
    def pending_count(self) -> int:
        return sum(1 for item in self.items if item.status == "pending")


def _count_rows(config: Config) -> Dict[str, int]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        counts = {}
        for table in ["sources", "findings", "topics", "drafts", "approvals", "posts"]:
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return counts
    except Exception:
        return {}
    finally:
        conn.close()


def _done_if_artifact(name: str) -> Callable[[Config, Dict[str, int], Dict[str, str]], str]:
    def _status(config: Config, counts: Dict[str, int], artifacts: Dict[str, str]) -> str:
        return "done" if artifacts.get(name) else "pending"

    return _status


def _artifact_detail(name: str, fallback: str) -> Callable[[Config, Dict[str, int], Dict[str, str]], str]:
    def _detail(config: Config, counts: Dict[str, int], artifacts: Dict[str, str]) -> str:
        return artifacts.get(name) or fallback

    return _detail


def _env_url_status(config: Config, counts: Dict[str, int], artifacts: Dict[str, str]) -> str:
    return "done" if os.environ.get("GOOGLE_APPS_SCRIPT_WEBAPP_URL", "").strip() else "pending"


def _env_url_details(config: Config, counts: Dict[str, int], artifacts: Dict[str, str]) -> str:
    if os.environ.get("GOOGLE_APPS_SCRIPT_WEBAPP_URL", "").strip():
        return "GOOGLE_APPS_SCRIPT_WEBAPP_URL is configured."
    return "Missing GOOGLE_APPS_SCRIPT_WEBAPP_URL in .env."


def _count_status(table: str) -> Callable[[Config, Dict[str, int], Dict[str, str]], str]:
    def _status(config: Config, counts: Dict[str, int], artifacts: Dict[str, str]) -> str:
        return "done" if counts.get(table, 0) > 0 else "pending"

    return _status


def _count_detail(table: str, noun: str) -> Callable[[Config, Dict[str, int], Dict[str, str]], str]:
    def _detail(config: Config, counts: Dict[str, int], artifacts: Dict[str, str]) -> str:
        return f"{counts.get(table, 0)} {noun} recorded in the active database."

    return _detail


def _daily_scan_status(config: Config, counts: Dict[str, int], artifacts: Dict[str, str]) -> str:
    exports_root = resolve_project_path(config.storage.exports_dir)
    return "done" if list(exports_root.glob("operations/*_daily_scan.md")) else "pending"


def _daily_scan_details(config: Config, counts: Dict[str, int], artifacts: Dict[str, str]) -> str:
    exports_root = resolve_project_path(config.storage.exports_dir)
    candidates = sorted(
        exports_root.glob("operations/*_daily_scan.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return str(candidates[0]) if candidates else "Run ai-linkedin run-daily-scan."


def _validation_status(config: Config, counts: Dict[str, int], artifacts: Dict[str, str]) -> str:
    exports_root = resolve_project_path(config.storage.exports_dir)
    candidates = sorted(
        exports_root.glob("approval_import_validation/*_validation.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return "pending"
    try:
        payload = json.loads(candidates[0].read_text())
    except json.JSONDecodeError:
        return "attention"
    if payload.get("fail_count", 0) > 0 or payload.get("ok") is False:
        return "blocked"
    if payload.get("decision_rows", 0) > 0:
        return "done"
    if payload.get("total_rows", 0) > 0:
        return "attention"
    return "pending"


def _validation_details(config: Config, counts: Dict[str, int], artifacts: Dict[str, str]) -> str:
    exports_root = resolve_project_path(config.storage.exports_dir)
    candidates = sorted(
        exports_root.glob("approval_import_validation/*_validation.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return "Run ai-linkedin validate-review-queue --csv PATH after exporting a decision row."
    try:
        payload = json.loads(candidates[0].read_text())
    except json.JSONDecodeError:
        return f"Latest validation JSON is unreadable: {candidates[0]}"
    markdown_path = str(candidates[0]).replace(".json", ".md")
    return (
        f"{markdown_path} "
        f"({payload.get('decision_rows', 0)} decision row(s), "
        f"{payload.get('pending_rows', 0)} pending row(s))"
    )


CHECKLIST_DEFINITIONS = [
    PilotChecklistDefinition(
        key="local_readiness_passed",
        label="Local readiness report is passing",
        phase="local",
        required_for="live_source_pilot",
        next_action="Run ai-linkedin v1-readiness and fix any failed checks.",
        auto_status=_done_if_artifact("weekly_brief"),
        auto_details=_artifact_detail("weekly_brief", "Run ai-linkedin run-friday-package --week current."),
    ),
    PilotChecklistDefinition(
        key="approval_deployment_package_built",
        label="Approval deployment package exists",
        phase="approval_setup",
        required_for="mobile_approval_pilot",
        next_action="Run ai-linkedin build-approval-deployment-package --week current.",
        auto_status=_done_if_artifact("approval_deployment_package"),
        auto_details=_artifact_detail(
            "approval_deployment_package",
            "No Apps Script deployment package found.",
        ),
    ),
    PilotChecklistDefinition(
        key="apps_script_deployed",
        label="Apps Script web app is manually deployed",
        phase="approval_setup",
        required_for="mobile_approval_pilot",
        next_action="Deploy the latest package in Google Apps Script, then mark this item done.",
    ),
    PilotChecklistDefinition(
        key="approval_url_configured",
        label="GOOGLE_APPS_SCRIPT_WEBAPP_URL is configured",
        phase="approval_setup",
        required_for="mobile_approval_pilot",
        next_action="Add GOOGLE_APPS_SCRIPT_WEBAPP_URL=... to .env.",
        auto_status=_env_url_status,
        auto_details=_env_url_details,
    ),
    PilotChecklistDefinition(
        key="local_approval_qa_passed",
        label="Local approval QA round trip passed",
        phase="approval_setup",
        required_for="mobile_approval_pilot",
        next_action="Run ai-linkedin run-approval-qa --action approve_text_only.",
        auto_status=_done_if_artifact("approval_qa_report"),
        auto_details=_artifact_detail("approval_qa_report", "No local approval QA report found."),
    ),
    PilotChecklistDefinition(
        key="live_source_scan_run",
        label="Live or dry-run source scan has a run report",
        phase="live_content",
        required_for="live_source_pilot",
        next_action="Run ai-linkedin run-daily-scan.",
        auto_status=_daily_scan_status,
        auto_details=_daily_scan_details,
    ),
    PilotChecklistDefinition(
        key="friday_package_generated",
        label="Friday package and intelligence outputs exist",
        phase="live_content",
        required_for="live_source_pilot",
        next_action="Run ai-linkedin run-friday-package --week current.",
        auto_status=_done_if_artifact("intelligence_report"),
        auto_details=_artifact_detail("intelligence_report", "No intelligence report found."),
    ),
    PilotChecklistDefinition(
        key="weekly_candidates_reviewed",
        label="Human reviewed weekly candidates and source quality",
        phase="live_content",
        required_for="first_post",
        next_action="Review weekly_brief.md, intelligence_report.md, and discovery_queue.md.",
    ),
    PilotChecklistDefinition(
        key="real_draft_created",
        label="Real draft created in active database",
        phase="approval_flow",
        required_for="first_post",
        next_action="Run ai-linkedin draft WEEKLY_BRIEF --topic-id TOPIC_ID.",
        auto_status=_count_status("drafts"),
        auto_details=_count_detail("drafts", "draft(s)"),
    ),
    PilotChecklistDefinition(
        key="review_queue_validated",
        label="Google Sheet CSV validated before import",
        phase="approval_flow",
        required_for="first_post",
        next_action="Run ai-linkedin validate-review-queue --csv EXPORTED_SHEET.csv.",
        auto_status=_validation_status,
        auto_details=_validation_details,
    ),
    PilotChecklistDefinition(
        key="iphone_magic_link_tested",
        label="iPhone magic-link approval tested",
        phase="approval_flow",
        required_for="first_post",
        next_action="Open the approval link on iPhone and record a non-publishing action.",
    ),
    PilotChecklistDefinition(
        key="approval_imported",
        label="Approval imported into local database",
        phase="approval_flow",
        required_for="first_post",
        next_action="Run ai-linkedin import-review-queue --csv EXPORTED_SHEET.csv.",
        auto_status=_count_status("approvals"),
        auto_details=_count_detail("approvals", "approval(s)"),
    ),
    PilotChecklistDefinition(
        key="first_post_archived",
        label="First manual post URL and notes archived",
        phase="post_ops",
        required_for="production_weekly_loop",
        next_action="Run ai-linkedin archive-post --draft-id DRAFT_ID --post-url LINKEDIN_POST_URL.",
        auto_status=_count_status("posts"),
        auto_details=_count_detail("posts", "post(s)"),
    ),
]


def _state_path(config: Config) -> Path:
    output_dir = resolve_project_path(config.storage.exports_dir) / "pilot"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / "pilot_checklist_state.json"


def _load_state(config: Config) -> Dict[str, Dict[str, str]]:
    path = _state_path(config)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data.get("items", {})
    except json.JSONDecodeError:
        return {}


def _write_state(config: Config, items: Dict[str, Dict[str, str]]) -> str:
    path = _state_path(config)
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "items": items,
    }
    path.write_text(json.dumps(payload, indent=2))
    return str(path)


def update_pilot_checklist_item(
    config: Config,
    key: str,
    status: str,
    notes: str = "",
) -> PilotChecklist:
    if key not in {definition.key for definition in CHECKLIST_DEFINITIONS}:
        raise ValueError(f"Unknown pilot checklist item: {key}")
    if status not in CHECKLIST_STATUSES:
        raise ValueError(f"Invalid checklist status: {status}")

    items = _load_state(config)
    items[key] = {
        "status": status,
        "notes": notes,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    _write_state(config, items)
    return build_pilot_checklist(config, write_files=True)


def _stage_for_items(items: List[PilotChecklistItem]) -> str:
    by_key = {item.key: item for item in items}
    if any(item.status == "blocked" for item in items):
        return "blocked"
    live_ready = all(
        by_key[key].status == "done"
        for key in [
            "local_readiness_passed",
            "live_source_scan_run",
            "friday_package_generated",
        ]
    )
    mobile_ready = live_ready and all(
        by_key[key].status == "done"
        for key in [
            "approval_deployment_package_built",
            "apps_script_deployed",
            "approval_url_configured",
            "local_approval_qa_passed",
        ]
    )
    first_post_ready = mobile_ready and all(
        by_key[key].status == "done"
        for key in [
            "weekly_candidates_reviewed",
            "real_draft_created",
            "review_queue_validated",
            "iphone_magic_link_tested",
            "approval_imported",
        ]
    )
    if first_post_ready:
        return "ready_for_first_manual_post"
    if mobile_ready:
        return "ready_for_mobile_approval_pilot"
    if live_ready:
        return "ready_for_live_source_pilot"
    return "setup_in_progress"


def _summary_for_stage(stage: str) -> str:
    return {
        "blocked": "A pilot gate is blocked; clear it before continuing.",
        "setup_in_progress": "Continue setup before relying on the live pilot loop.",
        "ready_for_live_source_pilot": "Ready to run live public-source collection and Friday packaging.",
        "ready_for_mobile_approval_pilot": "Ready to test the mobile approval loop.",
        "ready_for_first_manual_post": "Ready to build a manual posting package after final review.",
    }[stage]


def build_pilot_checklist(config: Config, write_files: bool = True) -> PilotChecklist:
    counts = _count_rows(config)
    artifacts = latest_artifacts(config)
    state = _load_state(config)
    generated_at = datetime.now().isoformat(timespec="seconds")
    items: List[PilotChecklistItem] = []

    for definition in CHECKLIST_DEFINITIONS:
        auto_status = (
            definition.auto_status(config, counts, artifacts)
            if definition.auto_status
            else "pending"
        )
        auto_details = (
            definition.auto_details(config, counts, artifacts)
            if definition.auto_details
            else "Manual confirmation required."
        )
        saved = state.get(definition.key, {})
        manual_status = saved.get("status", "")
        status = manual_status or auto_status
        details = auto_details
        manual_override = bool(manual_status)
        if manual_status and definition.auto_status and auto_status == "done":
            status = "done"
            details = f"{auto_details} Manual note: {saved.get('notes', '')}".strip()

        items.append(
            PilotChecklistItem(
                key=definition.key,
                label=definition.label,
                phase=definition.phase,
                required_for=definition.required_for,
                status=status,
                details=details,
                next_action=definition.next_action,
                notes=saved.get("notes", ""),
                updated_at=saved.get("updated_at", ""),
                manual_override=manual_override,
            )
        )

    stage = _stage_for_items(items)
    checklist = PilotChecklist(
        generated_at=generated_at,
        stage=stage,
        summary=_summary_for_stage(stage),
        items=items,
        state_path=str(_state_path(config)),
    )
    if write_files:
        output_dir = resolve_project_path(config.storage.exports_dir) / "pilot"
        output_dir.mkdir(parents=True, exist_ok=True)
        checklist.markdown_path = str(output_dir / "pilot_checklist.md")
        checklist.json_path = str(output_dir / "pilot_checklist.json")
        Path(checklist.markdown_path).write_text(render_pilot_checklist(checklist))
        Path(checklist.json_path).write_text(json.dumps(asdict(checklist), indent=2))
    return checklist


def render_pilot_checklist(checklist: PilotChecklist) -> str:
    lines = [
        "# Production Pilot Checklist",
        "",
        f"Generated: {checklist.generated_at}",
        f"Stage: {checklist.stage}",
        f"Summary: {checklist.summary}",
        "",
        "## Progress",
        "",
        f"- Done: {checklist.done_count}",
        f"- Attention: {checklist.attention_count}",
        f"- Blocked: {checklist.blocked_count}",
        f"- Pending: {checklist.pending_count}",
        "",
        "## Items",
        "",
    ]
    for item in checklist.items:
        lines.extend(
            [
                f"### {item.label}",
                "",
                f"- Key: `{item.key}`",
                f"- Status: {item.status}",
                f"- Phase: {item.phase}",
                f"- Required for: {item.required_for}",
                f"- Details: {item.details}",
                f"- Next action: {item.next_action}",
            ]
        )
        if item.notes:
            lines.append(f"- Notes: {item.notes}")
        lines.append("")
    return "\n".join(lines)
