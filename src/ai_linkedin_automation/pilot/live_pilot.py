import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from ai_linkedin_automation.config import Config, resolve_project_path
from ai_linkedin_automation.ingestion.sources import load_sources_from_config
from ai_linkedin_automation.intelligence.source_audit import audit_sources
from ai_linkedin_automation.locus_workflows import (
    LocusSDKNodeSpec,
    execute_state_graph,
    record_event,
    start_trace,
    trace_metadata,
    write_trace,
)
from ai_linkedin_automation.operations.preflight import run_preflight
from ai_linkedin_automation.operations.workflows import run_daily_scan, run_friday_package
from ai_linkedin_automation.pilot.checklist import build_pilot_checklist
from ai_linkedin_automation.pilot.readiness import build_readiness_report
from ai_linkedin_automation.storage.db import connect_db, init_db


@dataclass
class ProductionPilotStep:
    name: str
    status: str
    details: str


@dataclass
class ProductionPilotReport:
    status: str
    generated_at: str
    week: str
    dry_run: bool
    output_dir: str
    readiness_stage: str
    checklist_stage: str
    counts_before: Dict[str, int]
    counts_after: Dict[str, int]
    deltas: Dict[str, int]
    source_audit_summary: Dict[str, int]
    next_actions: List[str]
    steps: List[ProductionPilotStep] = field(default_factory=list)
    output_paths: Dict[str, str] = field(default_factory=dict)
    orchestration: Dict[str, object] = field(default_factory=dict)
    markdown_path: str = ""
    json_path: str = ""


def _count_rows(config: Config) -> Dict[str, int]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        counts = {}
        for table in [
            "sources",
            "findings",
            "topics",
            "drafts",
            "approvals",
            "posts",
            "discovery_queue",
            "content_clusters",
        ]:
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return counts
    except Exception:
        return {}
    finally:
        conn.close()


def _deltas(before: Dict[str, int], after: Dict[str, int]) -> Dict[str, int]:
    keys = set(before) | set(after)
    return {key: after.get(key, 0) - before.get(key, 0) for key in sorted(keys)}


def _status_from_steps(steps: List[ProductionPilotStep], warning_count: int) -> str:
    if any(step.status == "failed" for step in steps):
        return "failed"
    if warning_count:
        return "passed_with_warnings"
    return "passed"


def _next_actions(checklist_stage: str, checklist_items) -> List[str]:
    pending = [
        item
        for item in checklist_items
        if item.status in {"pending", "blocked", "attention"}
    ]
    actions = [f"{item.label}: {item.next_action}" for item in pending[:6]]
    if not actions:
        actions.append("Archive the first manually posted URL and review engagement notes.")
    if checklist_stage == "ready_for_live_source_pilot":
        actions.insert(0, "Deploy Apps Script and configure GOOGLE_APPS_SCRIPT_WEBAPP_URL for mobile QA.")
    return actions


def _write_report(config: Config, report: ProductionPilotReport) -> ProductionPilotReport:
    report.markdown_path = str(Path(report.output_dir) / "PRODUCTION_PILOT_REPORT.md")
    report.json_path = str(Path(report.output_dir) / "production_pilot_report.json")
    Path(report.markdown_path).write_text(render_production_pilot_report(report))
    Path(report.json_path).write_text(json.dumps(asdict(report), indent=2))

    latest_path = resolve_project_path(config.storage.exports_dir) / "pilot" / "latest_production_pilot.json"
    latest_path.write_text(json.dumps(asdict(report), indent=2))
    return report


def run_production_pilot(
    config: Config,
    week: str = "current",
    dry_run: bool = False,
    require_approval_url: bool = False,
) -> ProductionPilotReport:
    """Run the production-pilot control loop without emailing, deploying, or publishing."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = resolve_project_path(config.storage.exports_dir) / "pilot" / f"{timestamp}_production"
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().isoformat(timespec="seconds")
    steps: List[ProductionPilotStep] = []

    init_db(config.storage.sqlite_path)
    steps.append(ProductionPilotStep("init-db", "passed", "Database initialized or migrated"))
    trace = start_trace(
        "production_pilot",
        "StateGraph(preflight -> daily_scan -> friday_package -> source_audit -> readiness -> checklist)",
        human_gates=[
            "Apps Script deployment remains a manual Google account gate.",
            "Approval import is required before manual posting package creation.",
            "LinkedIn publishing remains human copy/paste only.",
        ],
        config=config,
    )
    record_event(trace, "preflight", "init_db", "passed", "Database initialized or migrated.")

    counts_before = _count_rows(config)

    preflight = None
    daily = None
    friday = None
    source_audit = None
    readiness = None
    checklist = None

    def load_sources_node(state):
        load_sources_from_config(config)
        steps.append(ProductionPilotStep("load-sources", "passed", "Configured sources loaded"))
        record_event(trace, "daily_scan", "load_sources", "passed", "Configured sources loaded.")
        return {**state, "sources_loaded": True}

    def preflight_node(state):
        nonlocal preflight
        preflight = run_preflight(config)
        warn_count = sum(1 for check in preflight.checks if check.status == "warn")
        steps.append(
            ProductionPilotStep(
                "preflight",
                "passed" if preflight.ok else "failed",
                f"{len(preflight.checks)} checks; {warn_count} warning(s)",
            )
        )
        record_event(
            trace,
            "preflight",
            "preflight",
            "passed" if preflight.ok else "failed",
            f"{len(preflight.checks)} checks; {warn_count} warning(s).",
        )
        return {**state, "preflight_ok": preflight.ok, "preflight_warnings": warn_count}

    def approval_url_gate_node(state):
        if require_approval_url and not os.environ.get("GOOGLE_APPS_SCRIPT_WEBAPP_URL", "").strip():
            steps.append(
                ProductionPilotStep(
                    "approval-url-required",
                    "failed",
                    "GOOGLE_APPS_SCRIPT_WEBAPP_URL is required for this run.",
                )
            )
            record_event(
                trace,
                "guardrail",
                "approval_url_required",
                "failed",
                "GOOGLE_APPS_SCRIPT_WEBAPP_URL is required for this run.",
            )
            return {**state, "approval_url_gate": "failed"}
        return {**state, "approval_url_gate": "passed"}

    def daily_scan_node(state):
        nonlocal daily
        daily = run_daily_scan(config, dry_run=dry_run)
        steps.append(ProductionPilotStep("daily-scan", daily.status, daily.report_path))
        record_event(trace, "daily_scan", "subworkflow", daily.status, daily.report_path)
        return {
            **state,
            "daily_status": daily.status,
            "daily_report": daily.report_path,
            "daily_sdk_graph_used": daily.orchestration.get("sdk_graph_used", False),
        }

    def friday_package_node(state):
        nonlocal friday
        friday = run_friday_package(config, week=week, dry_run=dry_run)
        steps.append(ProductionPilotStep("friday-package", friday.status, friday.report_path))
        record_event(trace, "friday_package", "subworkflow", friday.status, friday.report_path)
        return {
            **state,
            "friday_status": friday.status,
            "friday_report": friday.report_path,
            "friday_sdk_graph_used": friday.orchestration.get("sdk_graph_used", False),
        }

    def source_audit_node(state):
        nonlocal source_audit
        source_audit = audit_sources(config, week=week)
        steps.append(
            ProductionPilotStep(
                "source-audit",
                "passed" if source_audit.fail_count == 0 else "failed",
                f"{len(source_audit.issues)} issue(s); "
                f"{source_audit.fail_count} fail, {source_audit.warn_count} warn",
            )
        )
        record_event(
            trace,
            "readiness",
            "source_audit",
            "passed" if source_audit.fail_count == 0 else "failed",
            f"{len(source_audit.issues)} issue(s); {source_audit.fail_count} fail, "
            f"{source_audit.warn_count} warn.",
        )
        return {
            **state,
            "source_audit_failures": source_audit.fail_count,
            "source_audit_warnings": source_audit.warn_count,
        }

    def readiness_node(state):
        nonlocal readiness
        readiness = build_readiness_report(config, write_files=True)
        steps.append(
            ProductionPilotStep(
                "v1-readiness",
                "passed" if readiness.ok_for_live_testing else "failed",
                readiness.markdown_path,
            )
        )
        record_event(
            trace,
            "readiness",
            "v1_readiness",
            "passed" if readiness.ok_for_live_testing else "failed",
            readiness.markdown_path,
        )
        return {
            **state,
            "readiness_stage": readiness.live_testing_stage,
            "readiness_warnings": readiness.warn_count,
        }

    def checklist_node(state):
        nonlocal checklist
        checklist = build_pilot_checklist(config, write_files=True)
        steps.append(ProductionPilotStep("pilot-checklist", "passed", checklist.markdown_path))
        record_event(trace, "operator", "pilot_checklist", "passed", checklist.markdown_path)
        return {
            **state,
            "checklist_stage": checklist.stage,
            "checklist_attention": checklist.attention_count,
        }

    nodes = [
        LocusSDKNodeSpec("load_sources", "daily_scan", "load_sources", load_sources_node),
        LocusSDKNodeSpec("preflight", "preflight", "preflight", preflight_node),
        LocusSDKNodeSpec("approval_url_gate", "guardrail", "approval_url_gate", approval_url_gate_node),
        LocusSDKNodeSpec("daily_scan", "daily_scan", "subworkflow", daily_scan_node),
        LocusSDKNodeSpec("friday_package", "friday_package", "subworkflow", friday_package_node),
        LocusSDKNodeSpec("source_audit", "readiness", "source_audit", source_audit_node),
        LocusSDKNodeSpec("readiness", "readiness", "v1_readiness", readiness_node),
        LocusSDKNodeSpec("checklist", "operator", "pilot_checklist", checklist_node),
    ]
    sdk_run = execute_state_graph(
        "production_pilot",
        nodes,
        initial_state={"dry_run": dry_run, "week": week},
        parallel=False,
    )
    trace.sdk_runs.append(asdict(sdk_run))
    if not sdk_run.used_sdk:
        for node in nodes:
            node.executor({"dry_run": dry_run, "week": week})
    elif not sdk_run.success:
        steps.append(ProductionPilotStep("locus-stategraph", "failed", sdk_run.error))
        record_event(trace, "guardrail", "locus_stategraph", "failed", sdk_run.error)

    counts_after = _count_rows(config)
    readiness_warning_count = readiness.warn_count if readiness else 0
    source_audit_warning_count = source_audit.warn_count if source_audit else 0
    checklist_attention_count = checklist.attention_count if checklist else 0
    warning_count = readiness_warning_count + source_audit_warning_count + checklist_attention_count
    status = _status_from_steps(steps, warning_count)
    readiness_stage = readiness.live_testing_stage if readiness else "not_run"
    checklist_stage = checklist.stage if checklist else "not_run"
    checklist_items = checklist.items if checklist else []

    report = ProductionPilotReport(
        status=status,
        generated_at=generated_at,
        week=week,
        dry_run=dry_run,
        output_dir=str(output_dir),
        readiness_stage=readiness_stage,
        checklist_stage=checklist_stage,
        counts_before=counts_before,
        counts_after=counts_after,
        deltas=_deltas(counts_before, counts_after),
        source_audit_summary={
            "issues": len(source_audit.issues) if source_audit else 0,
            "fail": source_audit.fail_count if source_audit else 0,
            "warn": source_audit.warn_count if source_audit else 0,
        },
        next_actions=_next_actions(checklist_stage, checklist_items),
        steps=steps,
        output_paths={
            "daily_scan_report": daily.report_path if daily else "",
            "friday_package_report": friday.report_path if friday else "",
            "weekly_brief": friday.output_paths.get("weekly_brief", "") if friday else "",
            "prompt_packet": friday.output_paths.get("prompt_packet", "") if friday else "",
            "intelligence_report": friday.output_paths.get("intelligence_report", "") if friday else "",
            "source_audit": source_audit.markdown_path if source_audit else "",
            "readiness_report": readiness.markdown_path if readiness else "",
            "pilot_checklist": checklist.markdown_path if checklist else "",
        },
    )
    record_event(trace, "guardrail", "workflow_complete", status, "Production pilot complete.")
    trace = write_trace(config, trace, report.output_paths)
    report.output_paths["locus_trace"] = trace.markdown_path
    report.orchestration = trace_metadata(trace)
    return _write_report(config, report)


def render_production_pilot_report(report: ProductionPilotReport) -> str:
    lines = [
        "# Production Pilot Run Report",
        "",
        f"Generated: {report.generated_at}",
        f"Week: {report.week}",
        f"Dry run: {report.dry_run}",
        f"Status: {report.status}",
        f"Readiness stage: {report.readiness_stage}",
        f"Checklist stage: {report.checklist_stage}",
        "",
        "## Guardrails",
        "",
        "- No email was sent.",
        "- No Google API write-back was performed.",
        "- No LinkedIn API publishing was attempted.",
        "- Manual posting still requires explicit approval and human copy/paste.",
        "",
        "## Steps",
        "",
    ]
    for step in report.steps:
        lines.append(f"- {step.name}: {step.status} - {step.details}")

    lines.extend(["", "## Count Deltas", ""])
    for key, value in report.deltas.items():
        lines.append(f"- {key}: {value:+d}")

    lines.extend(["", "## Source Audit", ""])
    for key, value in report.source_audit_summary.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Outputs", ""])
    for key, value in report.output_paths.items():
        lines.append(f"- {key}: {value or 'not created in this run'}")

    if report.orchestration:
        lines.extend(["", "## Locus Orchestration", ""])
        lines.append(f"- Engine: {report.orchestration.get('engine')}")
        lines.append(f"- Pattern: {report.orchestration.get('pattern')}")
        lines.append(f"- Provider mode: {report.orchestration.get('provider_mode')}")
        lines.append(f"- Agent count: {report.orchestration.get('agent_count')}")
        lines.append(f"- Event count: {report.orchestration.get('event_count')}")
        lines.append(f"- Trace: {report.orchestration.get('trace_markdown')}")

    lines.extend(["", "## Next Actions", ""])
    for action in report.next_actions:
        lines.append(f"- {action}")
    return "\n".join(lines) + "\n"
