import contextlib
import io
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from ai_linkedin_automation.config import Config, resolve_project_path
from ai_linkedin_automation.locus_workflows import (
    LocusSDKNodeSpec,
    execute_state_graph,
    record_event,
    start_trace,
    trace_metadata,
    write_trace,
)


@dataclass
class WorkflowStep:
    name: str
    status: str
    details: str


@dataclass
class WorkflowReport:
    workflow: str
    dry_run: bool
    status: str
    generated_at: str
    steps: List[WorkflowStep] = field(default_factory=list)
    output_paths: Dict[str, str] = field(default_factory=dict)
    orchestration: Dict[str, object] = field(default_factory=dict)
    report_path: str = ""
    json_path: str = ""


def _capture(func, *args, **kwargs):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = func(*args, **kwargs)
    return result, buffer.getvalue().strip()


def _report_dir(config: Config) -> Path:
    output_dir = resolve_project_path(config.storage.exports_dir) / "operations"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _write_report(config: Config, report: WorkflowReport) -> WorkflowReport:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = _report_dir(config)
    report_file = output_dir / f"{timestamp}_{report.workflow}.md"
    json_file = output_dir / f"{timestamp}_{report.workflow}.json"

    lines = [
        f"# {report.workflow.replace('_', ' ').title()}",
        "",
        f"Generated: {report.generated_at}",
        f"Dry run: {report.dry_run}",
        f"Status: {report.status}",
        "",
        "## Steps",
        "",
    ]
    for step in report.steps:
        lines.append(f"- {step.name}: {step.status} - {step.details}")
    if report.output_paths:
        lines.extend(["", "## Outputs", ""])
        for name, path in report.output_paths.items():
            lines.append(f"- {name}: {path}")
    if report.orchestration:
        lines.extend(["", "## Locus Orchestration", ""])
        lines.append(f"- Engine: {report.orchestration.get('engine')}")
        lines.append(f"- Pattern: {report.orchestration.get('pattern')}")
        lines.append(f"- Provider mode: {report.orchestration.get('provider_mode')}")
        lines.append(f"- Agent count: {report.orchestration.get('agent_count')}")
        lines.append(f"- Event count: {report.orchestration.get('event_count')}")
        if report.orchestration.get("trace_markdown"):
            lines.append(f"- Trace: {report.orchestration.get('trace_markdown')}")

    report.report_path = str(report_file)
    report.json_path = str(json_file)
    report_file.write_text("\n".join(lines) + "\n")
    json_file.write_text(json.dumps(asdict(report), indent=2))
    return report


def run_daily_scan(config: Config, dry_run: bool = False) -> WorkflowReport:
    """Run the local daily source-load, ingestion, and scoring workflow."""
    from ai_linkedin_automation.ingestion.ingest import run_ingestion
    from ai_linkedin_automation.ingestion.sources import load_sources_from_config
    from ai_linkedin_automation.scoring.scoring import score_all_findings
    from ai_linkedin_automation.storage.db import init_db

    report = WorkflowReport(
        workflow="daily_scan",
        dry_run=dry_run,
        status="completed",
        generated_at=datetime.now().isoformat(timespec="seconds"),
    )
    trace = start_trace(
        "daily_scan",
        "Locus StateGraph(init_db -> source_loader -> ingestion -> scoring)",
        human_gates=["No external publishing or email side effects are allowed."],
        config=config,
    )

    def init_node(state: Dict[str, object]) -> Dict[str, object]:
        init_db(config.storage.sqlite_path)
        report.steps.append(WorkflowStep("init-db", "completed", "Database initialized or migrated"))
        record_event(trace, "guardrail", "init_db", "completed", "Database initialized or migrated.")
        return {"init_db": "completed", **state}

    def load_sources_node(state: Dict[str, object]) -> Dict[str, object]:
        if dry_run:
            report.steps.append(WorkflowStep("load-sources", "skipped", "Dry run; no source rows updated"))
            record_event(
                trace,
                "source_loader",
                "load_sources",
                "skipped",
                "Dry run; source rows not updated.",
            )
            return {"load_sources": "skipped", **state}
        load_sources_from_config(config)
        report.steps.append(WorkflowStep("load-sources", "completed", "Sources loaded from config"))
        record_event(trace, "source_loader", "load_sources", "completed", "Sources loaded from config.")
        return {"load_sources": "completed", **state}

    def ingest_node(state: Dict[str, object]) -> Dict[str, object]:
        _, ingest_output = _capture(run_ingestion, config, dry_run=dry_run)
        report.steps.append(WorkflowStep("ingest", "completed", ingest_output or "No ingestion output"))
        record_event(
            trace,
            "ingestion",
            "ingest",
            "completed",
            ingest_output or "Ingestion completed with no console output.",
        )
        return {"ingest": "completed", "ingest_output": ingest_output, **state}

    def score_node(state: Dict[str, object]) -> Dict[str, object]:
        if dry_run:
            report.steps.append(WorkflowStep("score", "skipped", "Dry run; findings were not scored"))
            record_event(trace, "scoring", "score", "skipped", "Dry run; findings were not scored.")
            return {"score": "skipped", **state}
        scored_count = score_all_findings(config)
        report.steps.append(WorkflowStep("score", "completed", f"Scored {scored_count} finding(s)"))
        record_event(trace, "scoring", "score", "completed", f"Scored {scored_count} finding(s).")
        return {"score": "completed", "scored_count": scored_count, **state}

    nodes = [
        LocusSDKNodeSpec("init_db", "guardrail", "init_db", init_node),
        LocusSDKNodeSpec("load_sources", "source_loader", "load_sources", load_sources_node),
        LocusSDKNodeSpec("ingest", "ingestion", "ingest", ingest_node),
        LocusSDKNodeSpec("score", "scoring", "score", score_node),
    ]
    sdk_run = execute_state_graph(
        "daily_scan",
        nodes,
        initial_state={"dry_run": dry_run},
        parallel=False,
    )
    trace.sdk_runs.append(asdict(sdk_run))
    if not sdk_run.used_sdk:
        for node in nodes:
            node.executor({"dry_run": dry_run})
    elif not sdk_run.success:
        report.status = "failed"
        report.steps.append(WorkflowStep("locus-stategraph", "failed", sdk_run.error))
        record_event(trace, "guardrail", "locus_stategraph", "failed", sdk_run.error)

    record_event(trace, "guardrail", "workflow_complete", report.status, "Daily scan complete.")
    trace = write_trace(config, trace, report.output_paths)
    report.output_paths["locus_trace"] = trace.markdown_path
    report.orchestration = trace_metadata(trace)

    return _write_report(config, report)


def run_friday_package(config: Config, week: str = "current", dry_run: bool = False) -> WorkflowReport:
    """Run the local Friday package workflow and write an operations report."""
    from ai_linkedin_automation.intelligence.report import build_intelligence_report
    from ai_linkedin_automation.scoring.scoring import score_all_findings
    from ai_linkedin_automation.storage.db import init_db
    from ai_linkedin_automation.weekly.weekly import generate_weekly_package

    report = WorkflowReport(
        workflow="friday_package",
        dry_run=dry_run,
        status="completed",
        generated_at=datetime.now().isoformat(timespec="seconds"),
    )
    trace = start_trace(
        "friday_package",
        "Locus StateGraph(init_db -> scoring -> weekly_brief -> intelligence)",
        human_gates=[
            "Unsupported claims must be surfaced before approval.",
            "Public posting requires later human approval and manual archive.",
        ],
        config=config,
    )

    def init_node(state: Dict[str, object]) -> Dict[str, object]:
        init_db(config.storage.sqlite_path)
        report.steps.append(WorkflowStep("init-db", "completed", "Database initialized or migrated"))
        record_event(trace, "guardrail", "init_db", "completed", "Database initialized or migrated.")
        return {"init_db": "completed", **state}

    def score_node(state: Dict[str, object]) -> Dict[str, object]:
        if dry_run:
            report.steps.append(WorkflowStep("score", "skipped", "Dry run; findings were not scored"))
            record_event(trace, "scoring", "score", "skipped", "Dry run; findings were not scored.")
            return {"score": "skipped", **state}
        scored_count = score_all_findings(config)
        report.steps.append(WorkflowStep("score", "completed", f"Scored {scored_count} finding(s)"))
        record_event(trace, "scoring", "score", "completed", f"Scored {scored_count} finding(s).")
        return {"score": "completed", "scored_count": scored_count, **state}

    def weekly_node(state: Dict[str, object]) -> Dict[str, object]:
        if dry_run:
            _, output = _capture(generate_weekly_package, config, week=week, dry_run=True)
            report.steps.append(
                WorkflowStep("build-weekly-package", "dry_run", output or "Dry run completed")
            )
            record_event(
                trace,
                "weekly_editor",
                "build_weekly_package",
                "dry_run",
                output or "Weekly dry run completed.",
            )
            return {"weekly_package": "dry_run", **state}

        result = generate_weekly_package(config, week=week, dry_run=False)
        if not result:
            report.status = "failed"
            report.steps.append(WorkflowStep("build-weekly-package", "failed", "No package was created"))
            record_event(
                trace,
                "weekly_editor",
                "build_weekly_package",
                "failed",
                "No package was created.",
            )
            return {"weekly_package": "failed", **state}

        weekly_file, prompt_file = result
        report.output_paths["weekly_brief"] = weekly_file
        report.output_paths["prompt_packet"] = prompt_file
        report.steps.append(
            WorkflowStep("build-weekly-package", "completed", "Weekly brief and prompt packet created")
        )
        record_event(
            trace,
            "weekly_editor",
            "build_weekly_package",
            "completed",
            "Weekly brief and prompt packet created.",
        )
        return {
            "weekly_package": "completed",
            "weekly_brief": weekly_file,
            "prompt_packet": prompt_file,
            **state,
        }

    def intelligence_node(state: Dict[str, object]) -> Dict[str, object]:
        if dry_run or report.status == "failed":
            return {"intelligence_report": "skipped", **state}
        intelligence_report = build_intelligence_report(config, week=week)
        report.output_paths["intelligence_report"] = intelligence_report.markdown_path
        report.steps.append(
            WorkflowStep(
                "build-intelligence-report",
                "completed",
                "Source audit, topic clusters, and discovery queue created",
            )
        )
        record_event(
            trace,
            "source_governance",
            "source_audit",
            "completed",
            intelligence_report.source_audit_path,
        )
        record_event(
            trace,
            "topic_cluster",
            "cluster_topics",
            "completed",
            intelligence_report.cluster_report_path,
        )
        record_event(
            trace,
            "discovery",
            "build_discovery_queue",
            "completed",
            intelligence_report.discovery_queue_path,
        )
        return {
            "intelligence_report": intelligence_report.markdown_path,
            "source_audit": intelligence_report.source_audit_path,
            "topic_clusters": intelligence_report.cluster_report_path,
            "discovery_queue": intelligence_report.discovery_queue_path,
            **state,
        }

    nodes = [
        LocusSDKNodeSpec("init_db", "guardrail", "init_db", init_node),
        LocusSDKNodeSpec("score", "scoring", "score", score_node),
        LocusSDKNodeSpec("weekly_package", "weekly_editor", "build_weekly_package", weekly_node),
        LocusSDKNodeSpec("intelligence", "discovery", "build_intelligence_report", intelligence_node),
    ]
    sdk_run = execute_state_graph(
        "friday_package",
        nodes,
        initial_state={"dry_run": dry_run, "week": week},
        parallel=False,
    )
    trace.sdk_runs.append(asdict(sdk_run))
    if not sdk_run.used_sdk:
        for node in nodes:
            node.executor({"dry_run": dry_run, "week": week})
    elif not sdk_run.success:
        report.status = "failed"
        report.steps.append(WorkflowStep("locus-stategraph", "failed", sdk_run.error))
        record_event(trace, "guardrail", "locus_stategraph", "failed", sdk_run.error)

    record_event(trace, "guardrail", "workflow_complete", report.status, "Friday package workflow complete.")
    trace = write_trace(config, trace, report.output_paths)
    report.output_paths["locus_trace"] = trace.markdown_path
    report.orchestration = trace_metadata(trace)

    return _write_report(config, report)
