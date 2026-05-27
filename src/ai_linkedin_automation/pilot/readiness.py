import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from ai_linkedin_automation.approval_webapp.deployment import validate_approval_webapp_scaffold
from ai_linkedin_automation.config import Config, resolve_project_path
from ai_linkedin_automation.integrations.status import collect_integration_status
from ai_linkedin_automation.operations.preflight import run_preflight
from ai_linkedin_automation.storage.db import connect_db


@dataclass
class ReadinessItem:
    name: str
    status: str
    details: str


@dataclass
class ReadinessReport:
    generated_at: str
    live_testing_stage: str
    decision: str
    items: List[ReadinessItem]
    counts: Dict[str, int]
    latest_artifacts: Dict[str, str]
    markdown_path: str = ""
    json_path: str = ""

    @property
    def fail_count(self) -> int:
        return sum(1 for item in self.items if item.status == "fail")

    @property
    def warn_count(self) -> int:
        return sum(1 for item in self.items if item.status == "warn")

    @property
    def ok_for_live_testing(self) -> bool:
        return self.fail_count == 0


def _item(name: str, status: str, details: str) -> ReadinessItem:
    return ReadinessItem(name=name, status=status, details=details)


def _count_rows(config: Config) -> Dict[str, int]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        counts = {}
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
        return counts
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


def _latest_file(root: Path, patterns: List[str]) -> str:
    candidates: List[Path] = []
    for pattern in patterns:
        candidates.extend(root.glob(pattern))
    candidates = [path for path in candidates if path.is_file()]
    if not candidates:
        return ""
    return str(max(candidates, key=lambda path: path.stat().st_mtime))


def latest_artifacts(config: Config) -> Dict[str, str]:
    review_root = resolve_project_path(config.storage.review_packets_dir)
    exports_root = resolve_project_path(config.storage.exports_dir)
    return {
        "weekly_brief": _latest_file(review_root, ["*/weekly_brief.md"]),
        "prompt_packet": _latest_file(review_root, ["*/recommended_winner_prompt_packet.md"]),
        "intelligence_report": _latest_file(review_root, ["*/intelligence/intelligence_report.md"]),
        "source_audit": _latest_file(review_root, ["*/intelligence/source_governance_audit.md"]),
        "topic_clusters": _latest_file(review_root, ["*/intelligence/topic_clusters.md"]),
        "discovery_queue": _latest_file(review_root, ["*/intelligence/discovery_queue.md"]),
        "approval_deployment_package": _latest_file(
            exports_root,
            ["approval_webapp/*/DEPLOYMENT_CHECKLIST.md"],
        ),
        "approval_qa_report": _latest_file(exports_root, ["approval_qa/*/approval_qa_report.md"]),
        "review_queue_validation": _latest_file(
            exports_root,
            ["approval_import_validation/*_validation.md"],
        ),
        "pilot_checklist": _latest_file(exports_root, ["pilot/pilot_checklist.md"]),
        "production_pilot_report": _latest_file(
            exports_root,
            ["pilot/*_production/PRODUCTION_PILOT_REPORT.md"],
        ),
        "production_test_runbook": _latest_file(
            exports_root,
            ["production_tests/*/PRODUCTION_TEST_RUNBOOK.md"],
        ),
        "operations_report": _latest_file(exports_root, ["operations/*.md"]),
        "manual_posting_package": _latest_file(exports_root, ["**/*_final_post_package.md"]),
        "schedule_runbook": _latest_file(exports_root, ["schedule/README.md"]),
        "touch_free_setup_report": _latest_file(
            exports_root,
            ["business_console/TOUCH_FREE_SETUP_REPORT.md"],
        ),
        "approval_setup_guide": _latest_file(
            exports_root,
            ["approval_setup/APPROVAL_SETUP_GUIDE.md"],
        ),
        "locus_trace": _latest_file(exports_root, ["locus/*_trace.md"]),
        "locus_workbench_package": _latest_file(
            exports_root,
            ["locus/workbench/*/README.md"],
        ),
    }


def _approval_url_item() -> ReadinessItem:
    if os.environ.get("GOOGLE_APPS_SCRIPT_WEBAPP_URL", "").strip():
        return _item("Approval web app URL", "pass", "GOOGLE_APPS_SCRIPT_WEBAPP_URL is configured")
    return _item(
        "Approval web app URL",
        "warn",
        "Set GOOGLE_APPS_SCRIPT_WEBAPP_URL before mobile magic-link testing",
    )


def build_readiness_report(config: Config, write_files: bool = True) -> ReadinessReport:
    preflight = run_preflight(config)
    webapp = validate_approval_webapp_scaffold()
    integrations = collect_integration_status(config)
    counts = _count_rows(config)
    artifacts = latest_artifacts(config)

    items: List[ReadinessItem] = []
    items.append(
        _item(
            "Preflight",
            "pass" if preflight.ok else "fail",
            f"{len(preflight.checks)} checks run; {sum(1 for check in preflight.checks if check.status == 'warn')} warning(s)",
        )
    )
    items.append(
        _item(
            "Approval web app scaffold",
            "pass" if webapp.ok else "fail",
            f"{len(webapp.checks)} contract checks run",
        )
    )
    items.append(_approval_url_item())
    risky = [item.name for item in integrations.items if item.paid_capable and item.enabled and item.cost_allowed]
    items.append(
        _item(
            "Paid/live integrations",
            "fail" if risky else "pass",
            "No paid-capable or live publishing integration is enabled" if not risky else ", ".join(risky),
        )
    )
    items.append(
        _item(
            "Source registry",
            "pass" if counts.get("sources", 0) > 0 else "fail",
            f"{counts.get('sources', 0)} source(s) loaded",
        )
    )
    items.append(
        _item(
            "Weekly package artifacts",
            "pass" if artifacts["weekly_brief"] else "warn",
            artifacts["weekly_brief"] or "Run ai-linkedin run-friday-package --week current",
        )
    )
    items.append(
        _item(
            "Intelligence artifacts",
            "pass" if artifacts["intelligence_report"] else "warn",
            artifacts["intelligence_report"] or "Run ai-linkedin build-intelligence-report --week current",
        )
    )
    items.append(
        _item(
            "Approval deployment package",
            "pass" if artifacts["approval_deployment_package"] else "warn",
            artifacts["approval_deployment_package"] or "Run ai-linkedin build-approval-deployment-package",
        )
    )
    items.append(
        _item(
            "Approval QA report",
            "pass" if artifacts["approval_qa_report"] else "warn",
            artifacts["approval_qa_report"] or "Run ai-linkedin run-approval-qa",
        )
    )

    fail_count = sum(1 for item in items if item.status == "fail")
    warn_count = sum(1 for item in items if item.status == "warn")
    if fail_count:
        stage = "not_ready"
        decision = "Fix failed checks before live testing."
    elif warn_count:
        stage = "ready_for_local_live_pilot"
        decision = "You can start local live-source testing; complete warning items before iPhone magic-link QA."
    else:
        stage = "ready_for_mobile_live_pilot"
        decision = "Ready for live-source and mobile approval pilot testing."

    report = ReadinessReport(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        live_testing_stage=stage,
        decision=decision,
        items=items,
        counts=counts,
        latest_artifacts=artifacts,
    )
    if write_files:
        output_dir = resolve_project_path(config.storage.exports_dir) / "pilot"
        output_dir.mkdir(parents=True, exist_ok=True)
        report.markdown_path = str(output_dir / "v1_readiness_report.md")
        report.json_path = str(output_dir / "v1_readiness_report.json")
        Path(report.markdown_path).write_text(render_readiness_report(report))
        Path(report.json_path).write_text(json.dumps(asdict(report), indent=2))
    return report


def render_readiness_report(report: ReadinessReport) -> str:
    lines = [
        "# v1.0 Live Testing Readiness Report",
        "",
        f"Generated: {report.generated_at}",
        f"Stage: {report.live_testing_stage}",
        f"Decision: {report.decision}",
        "",
        "## Checks",
        "",
    ]
    for item in report.items:
        lines.append(f"- [{item.status.upper()}] {item.name}: {item.details}")
    lines.extend(["", "## Counts", ""])
    for key, value in sorted(report.counts.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Latest Artifacts", ""])
    for key, value in sorted(report.latest_artifacts.items()):
        lines.append(f"- {key}: {value or 'not created yet'}")
    return "\n".join(lines) + "\n"
