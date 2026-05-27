import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ai_linkedin_automation.approval_webapp.deployment import build_deployment_package
from ai_linkedin_automation.config import Config, resolve_project_path
from ai_linkedin_automation.drafting import generate_draft_from_topic, save_draft
from ai_linkedin_automation.intelligence.report import build_intelligence_report
from ai_linkedin_automation.locus_workflows import (
    LocusSDKNodeSpec,
    execute_state_graph,
    record_event,
    start_trace,
    trace_metadata,
    write_trace,
)
from ai_linkedin_automation.notifications.packages import build_notification_package
from ai_linkedin_automation.pilot.checklist import build_pilot_checklist
from ai_linkedin_automation.pilot.sheet_validation import validate_review_queue_csv
from ai_linkedin_automation.scoring.scoring import score_all_findings, top_topics
from ai_linkedin_automation.storage.db import connect_db, init_db
from ai_linkedin_automation.weekly.weekly import generate_weekly_package


@dataclass
class ProductionTestPackage:
    status: str
    generated_at: str
    week: str
    output_dir: str
    selected_topic_id: str
    selected_topic_title: str
    candidate_publish_ready: bool
    draft_id: str
    approval_url_configured: bool
    deployment_package_path: str
    weekly_brief_path: str
    prompt_packet_path: str
    intelligence_report_path: str
    draft_path: str
    approval_packet_path: str
    review_queue_path: str
    review_queue_validation_path: str
    notification_text_path: str
    notification_html_path: str
    pilot_checklist_path: str
    candidate_shortlist_path: str
    runbook_path: str
    manifest_path: str
    next_actions: List[str]
    orchestration: Dict[str, object] = field(default_factory=dict)


def _topic_by_id(config: Config, topic_id: str) -> Optional[Dict[str, object]]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        row = conn.execute(
            """
            SELECT
                topics.*,
                findings.url AS source_url,
                findings.source_id,
                sources.name AS source_name,
                sources.trust_tier,
                findings.score AS finding_score
            FROM topics
            LEFT JOIN topic_findings ON topic_findings.topic_id = topics.id
            LEFT JOIN findings ON findings.id = topic_findings.finding_id
            LEFT JOIN sources ON sources.id = findings.source_id
            WHERE topics.id = ?
            ORDER BY
                CASE sources.trust_tier
                    WHEN 'primary' THEN 1
                    WHEN 'high_trust' THEN 2
                    ELSE 3
                END,
                CASE topic_findings.relationship
                    WHEN 'lead_source' THEN 1
                    ELSE 2
                END
            LIMIT 1
            """,
            (topic_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _candidate_publish_ready(topic: Dict[str, object]) -> bool:
    trust_tier = topic.get("trust_tier")
    return (
        topic.get("recommendation") == "draft_now"
        and trust_tier in {"primary", "high_trust"}
        and (topic.get("political_risk") or "") == "low"
        and int(topic.get("draft_readiness") or 0) >= 4
    )


def _package_status(candidate_ready: bool, approval_url_configured: bool) -> str:
    if candidate_ready and approval_url_configured:
        return "ready_for_mobile_approval_test"
    if candidate_ready:
        return "ready_for_apps_script_deployment"
    if approval_url_configured:
        return "ready_for_flow_test_needs_source_review"
    return "ready_for_local_flow_test_needs_apps_script"


def _candidate_shortlist_markdown(candidates: List[Dict[str, object]], selected_topic_id: str) -> str:
    lines = [
        "# Production Test Candidate Shortlist",
        "",
        "Use this as an operator review aid. A test package may be suitable for approval-flow testing even when the selected topic still needs source verification before public posting.",
        "",
    ]
    if not candidates:
        lines.append("No topic candidates found.")
        return "\n".join(lines) + "\n"

    for index, topic in enumerate(candidates, start=1):
        selected = " selected" if topic["id"] == selected_topic_id else ""
        lines.extend(
            [
                f"## {index}. {topic['title']}{selected}",
                "",
                f"- Topic ID: `{topic['id']}`",
                f"- Recommendation: {topic.get('recommendation')}",
                f"- Political risk: {topic.get('political_risk')}",
                f"- Draft readiness: {topic.get('draft_readiness')}/5",
                f"- Source: {topic.get('source_name')} ({topic.get('trust_tier')})",
                f"- Source URL: {topic.get('source_url')}",
                "",
                str(topic.get("summary") or "No summary available."),
                "",
            ]
        )
    return "\n".join(lines)


def _next_actions(
    candidate_ready: bool,
    approval_url_configured: bool,
    draft_id: str,
    topic_id: str,
) -> List[str]:
    actions: List[str] = []
    if not candidate_ready:
        actions.append(
            "Treat this as an approval-flow test until a human confirms source quality or attaches a primary/high-trust source."
        )
    if not approval_url_configured:
        actions.append("Use local approval in the console for the lowest-maintenance path.")
        actions.append("Optional: deploy the Apps Script package only if you want iPhone magic-link approval.")
    actions.extend(
        [
            "Press Approve Locally in the console to record the decision and build the final package.",
            "Post manually on LinkedIn after source review is complete.",
            "Paste the final LinkedIn post URL into the console and press Archive Post.",
        ]
    )
    return actions


def _write_runbook(package: ProductionTestPackage) -> None:
    lines = [
        "# Production Test Runbook",
        "",
        f"Generated: {package.generated_at}",
        f"Status: {package.status}",
        f"Selected topic: {package.selected_topic_title}",
        f"Topic ID: `{package.selected_topic_id}`",
        f"Draft ID: `{package.draft_id}`",
        "",
        "## Artifacts",
        "",
        f"- Apps Script deployment package: {package.deployment_package_path}",
        f"- Candidate shortlist: {package.candidate_shortlist_path}",
        f"- Weekly brief: {package.weekly_brief_path}",
        f"- Prompt packet: {package.prompt_packet_path}",
        f"- Intelligence report: {package.intelligence_report_path}",
        f"- Draft text: {package.draft_path}",
        f"- Approval packet: {package.approval_packet_path}",
        f"- Review queue CSV: {package.review_queue_path}",
        f"- Review queue validation: {package.review_queue_validation_path}",
        f"- Notification text: {package.notification_text_path}",
        f"- Notification HTML: {package.notification_html_path}",
        f"- Pilot checklist: {package.pilot_checklist_path}",
        "",
        "## Guardrails",
        "",
        "- No email was sent.",
        "- No Google API write-back was performed.",
        "- No LinkedIn API publishing was attempted.",
        "- Approval still does not publish.",
        "- Manual posting package creation still requires an imported approval record.",
        "",
        "## Locus Orchestration",
        "",
        f"- Engine: {package.orchestration.get('engine')}",
        f"- Pattern: {package.orchestration.get('pattern')}",
        f"- Provider mode: {package.orchestration.get('provider_mode')}",
        f"- Agent count: {package.orchestration.get('agent_count')}",
        f"- Event count: {package.orchestration.get('event_count')}",
        f"- Trace: {package.orchestration.get('trace_markdown')}",
        "",
        "## Next Actions",
        "",
    ]
    for action in package.next_actions:
        lines.append(f"- {action}")
    Path(package.runbook_path).write_text("\n".join(lines) + "\n")


def build_production_test_package(
    config: Config,
    week: str = "current",
    topic_id: Optional[str] = None,
) -> ProductionTestPackage:
    """Build the first-post production testing package without external side effects."""
    init_db(config.storage.sqlite_path)
    trace = start_trace(
        "production_test_package",
        "Orchestrator(candidate -> intelligence fan-out -> draft -> approval packet -> human gate)",
        human_gates=[
            "Human source-quality review before public posting.",
            "Apps Script deployment and mobile approval before import.",
            "Manual LinkedIn copy/paste and archive after approval import.",
        ],
        config=config,
    )
    record_event(trace, "guardrail", "init_db", "completed", "Database initialized or migrated.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = resolve_project_path(config.storage.exports_dir) / "production_tests" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_shortlist_path = output_dir / "candidate_shortlist.md"

    candidates: List[Dict[str, object]] = []
    selected: Optional[Dict[str, object]] = None
    weekly_brief = ""
    prompt_packet = ""
    intelligence = None
    deployment = None
    draft_id = ""
    draft_path = output_dir / "draft.md"
    notification = None
    validation = None
    checklist = None

    def candidate_node(state):
        nonlocal candidates, selected
        scored_count = score_all_findings(config)
        record_event(
            trace,
            "candidate_selector",
            "score_findings",
            "completed",
            f"Finding scores refreshed; {scored_count} finding(s) scored.",
        )

        candidates = top_topics(config, limit=10)
        if topic_id:
            selected = _topic_by_id(config, topic_id)
            if not selected:
                raise ValueError(f"Topic not found: {topic_id}")
            if selected["id"] not in {candidate["id"] for candidate in candidates}:
                candidates.append(selected)
        elif candidates:
            selected = candidates[0]
        else:
            record_event(
                trace,
                "candidate_selector",
                "select_candidate",
                "failed",
                "No topic candidates found.",
            )
            raise RuntimeError("No topic candidates found. Run ai-linkedin run-production-pilot first.")
        record_event(
            trace,
            "candidate_selector",
            "select_candidate",
            "completed",
            f"Selected topic {selected['id']}: {selected['title']}",
        )
        return {
            **state,
            "candidate_count": len(candidates),
            "selected_topic_id": selected["id"],
        }

    def weekly_package_node(state):
        nonlocal weekly_brief, prompt_packet
        weekly_brief, prompt_packet = generate_weekly_package(config, week=week, dry_run=False) or ("", "")
        record_event(trace, "intelligence", "weekly_package", "completed", weekly_brief or "No weekly brief path.")
        return {**state, "weekly_brief": weekly_brief, "prompt_packet": prompt_packet}

    def intelligence_node(state):
        nonlocal intelligence
        if not selected:
            raise RuntimeError("No selected topic is available for intelligence report.")
        intelligence = build_intelligence_report(config, week=week, topic_id=str(selected["id"]))
        record_event(trace, "intelligence", "build_intelligence_report", "completed", intelligence.markdown_path)
        return {**state, "intelligence_report": intelligence.markdown_path}

    def deployment_node(state):
        nonlocal deployment
        deployment = build_deployment_package(config, week=week)
        record_event(
            trace,
            "approval_packet",
            "build_deployment_package",
            "completed",
            deployment.checklist_path,
        )
        return {**state, "deployment_package": deployment.output_dir}

    def drafting_node(state):
        nonlocal draft_id, draft_path
        if not selected:
            raise RuntimeError("No selected topic is available for drafting.")
        draft_text = generate_draft_from_topic(config, str(selected["id"]))
        draft_id = save_draft(config.storage.sqlite_path, str(selected["id"]), draft_text)
        draft_path = output_dir / f"{draft_id}_draft.md"
        draft_path.write_text(draft_text)
        record_event(trace, "drafting", "generate_draft", "completed", f"Draft saved as {draft_id}.")
        return {**state, "draft_id": draft_id, "draft_path": str(draft_path)}

    def approval_packet_node(state):
        nonlocal notification, validation
        if not draft_id:
            raise RuntimeError("No draft is available for approval packet creation.")
        notification = build_notification_package(config, draft_id, week=week)
        record_event(
            trace,
            "approval_packet",
            "build_notification_package",
            "completed",
            notification.text_path,
        )
        validation = validate_review_queue_csv(config, notification.review_queue_path)
        record_event(
            trace,
            "approval_packet",
            "validate_review_queue",
            "passed" if validation.ok else "failed",
            validation.markdown_path,
        )
        return {
            **state,
            "review_queue": notification.review_queue_path,
            "review_queue_validation_ok": validation.ok,
        }

    def checklist_node(state):
        nonlocal checklist
        checklist = build_pilot_checklist(config, write_files=True)
        record_event(trace, "operator", "pilot_checklist", "completed", checklist.markdown_path)
        return {**state, "checklist_stage": checklist.stage}

    def shortlist_node(state):
        if not selected:
            raise RuntimeError("No selected topic is available for shortlist creation.")
        candidate_shortlist_path.write_text(_candidate_shortlist_markdown(candidates, str(selected["id"])))
        record_event(
            trace,
            "operator",
            "candidate_shortlist",
            "completed",
            str(candidate_shortlist_path),
        )
        return {**state, "candidate_shortlist": str(candidate_shortlist_path)}

    nodes = [
        LocusSDKNodeSpec("candidate", "candidate_selector", "select_candidate", candidate_node),
        LocusSDKNodeSpec("weekly_package", "intelligence", "weekly_package", weekly_package_node),
        LocusSDKNodeSpec("intelligence", "intelligence", "build_intelligence_report", intelligence_node),
        LocusSDKNodeSpec("deployment", "approval_packet", "build_deployment_package", deployment_node),
        LocusSDKNodeSpec("drafting", "drafting", "generate_draft", drafting_node),
        LocusSDKNodeSpec("approval_packet", "approval_packet", "build_notification_package", approval_packet_node),
        LocusSDKNodeSpec("checklist", "operator", "pilot_checklist", checklist_node),
        LocusSDKNodeSpec("shortlist", "operator", "candidate_shortlist", shortlist_node),
    ]
    sdk_run = execute_state_graph(
        "production_test_package",
        nodes,
        initial_state={"week": week, "topic_id": topic_id or ""},
        parallel=False,
    )
    trace.sdk_runs.append(asdict(sdk_run))
    if not sdk_run.used_sdk:
        for node in nodes:
            node.executor({"week": week, "topic_id": topic_id or ""})
    elif not sdk_run.success:
        record_event(trace, "guardrail", "locus_stategraph", "failed", sdk_run.error)
        raise RuntimeError(f"Locus production test package workflow failed: {sdk_run.error}")

    if not selected:
        raise RuntimeError("No topic candidates found. Run ai-linkedin run-production-pilot first.")
    if not intelligence or not deployment or not notification or not validation or not checklist:
        raise RuntimeError("Production test package workflow did not create all required artifacts.")

    candidate_ready = _candidate_publish_ready(selected)
    approval_url_configured = bool(os.environ.get("GOOGLE_APPS_SCRIPT_WEBAPP_URL", "").strip())
    status = _package_status(candidate_ready, approval_url_configured)
    runbook_path = output_dir / "PRODUCTION_TEST_RUNBOOK.md"
    manifest_path = output_dir / "production_test_manifest.json"

    package = ProductionTestPackage(
        status=status,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        week=week,
        output_dir=str(output_dir),
        selected_topic_id=selected["id"],
        selected_topic_title=selected["title"],
        candidate_publish_ready=candidate_ready,
        draft_id=draft_id,
        approval_url_configured=approval_url_configured,
        deployment_package_path=deployment.output_dir,
        weekly_brief_path=weekly_brief,
        prompt_packet_path=prompt_packet,
        intelligence_report_path=intelligence.markdown_path,
        draft_path=str(draft_path),
        approval_packet_path=notification.approval_packet_path,
        review_queue_path=notification.review_queue_path,
        review_queue_validation_path=validation.markdown_path,
        notification_text_path=notification.text_path,
        notification_html_path=notification.html_path,
        pilot_checklist_path=checklist.markdown_path,
        candidate_shortlist_path=str(candidate_shortlist_path),
        runbook_path=str(runbook_path),
        manifest_path=str(manifest_path),
        next_actions=_next_actions(candidate_ready, approval_url_configured, draft_id, selected["id"]),
    )
    record_event(
        trace,
        "guardrail",
        "workflow_complete",
        status,
        "Production test package created without external side effects.",
    )
    trace = write_trace(
        config,
        trace,
        {
            "candidate_shortlist": str(candidate_shortlist_path),
            "draft": str(draft_path),
            "intelligence_report": intelligence.markdown_path,
            "review_queue": notification.review_queue_path,
            "validation": validation.markdown_path,
        },
    )
    package.orchestration = trace_metadata(trace)
    _write_runbook(package)
    manifest_path.write_text(json.dumps(asdict(package), indent=2))

    latest_path = resolve_project_path(config.storage.exports_dir) / "production_tests" / "latest.json"
    latest_path.write_text(json.dumps(asdict(package), indent=2))
    return package
