import asyncio
import importlib.util
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from ai_linkedin_automation.config import Config, resolve_project_path


SDK_PACKAGE = "locus-sdk"
SDK_IMPORT_NAME = "locus"


@dataclass
class LocusAgentSpec:
    key: str
    name: str
    responsibility: str
    pattern_role: str
    local_tooling: str


@dataclass
class LocusWorkflowEvent:
    sequence: int
    timestamp: str
    workflow: str
    agent: str
    event_type: str
    status: str
    message: str


@dataclass
class LocusWorkflowTrace:
    workflow: str
    pattern: str
    engine: str
    sdk_installed: bool
    hard_zero_mode: bool
    provider_mode: str
    generated_at: str
    human_gates: List[str] = field(default_factory=list)
    agents: List[LocusAgentSpec] = field(default_factory=list)
    events: List[LocusWorkflowEvent] = field(default_factory=list)
    output_paths: Dict[str, str] = field(default_factory=dict)
    sdk_runs: List[Dict[str, object]] = field(default_factory=list)
    install_commands: List[str] = field(default_factory=list)
    markdown_path: str = ""
    json_path: str = ""


@dataclass
class LocusStatus:
    sdk_installed: bool
    engine: str
    hard_zero_safe: bool
    provider_mode: str
    install_commands: List[str]
    enabled_workflows: List[str]
    active_primitives: List[str]
    sdk_capabilities: Dict[str, bool]
    notes: List[str]


@dataclass
class LocusSDKNodeSpec:
    node_id: str
    agent: str
    event_type: str
    executor: Callable[[Dict[str, Any]], Any]
    description: str = ""


@dataclass
class LocusSDKRun:
    used_sdk: bool
    primitive: str
    success: bool
    graph_id: str = ""
    run_id: str = ""
    execution_order: List[str] = field(default_factory=list)
    node_statuses: Dict[str, str] = field(default_factory=dict)
    node_errors: Dict[str, str] = field(default_factory=dict)
    final_state: Dict[str, Any] = field(default_factory=dict)
    observability_event_count: int = 0
    observability_events: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0
    error: str = ""


@dataclass
class LocusCapabilityCheck:
    name: str
    status: str
    details: str


@dataclass
class LocusCapabilityReport:
    status: str
    generated_at: str
    sdk_installed: bool
    checks: List[LocusCapabilityCheck] = field(default_factory=list)
    markdown_path: str = ""
    json_path: str = ""


@dataclass
class LocusWorkflowDefinition:
    workflow: str
    purpose: str
    pattern: str
    nodes: List[str]
    human_gates: List[str] = field(default_factory=list)


@dataclass
class LocusWorkbenchPackage:
    status: str
    generated_at: str
    output_dir: str
    manifest_path: str
    readme_path: str
    diagrams: Dict[str, str] = field(default_factory=dict)
    json_path: str = ""


def locus_sdk_installed() -> bool:
    return importlib.util.find_spec(SDK_IMPORT_NAME) is not None


def locus_install_commands() -> List[str]:
    return [
        ".venv/bin/python -m pip install locus-sdk",
        '.venv/bin/python -m pip install -e ".[locus]"',
        ".venv/bin/python -m ai_linkedin_automation.cli locus-status",
    ]


def locus_sdk_capabilities() -> Dict[str, bool]:
    capabilities = {
        "StateGraph": False,
        "GraphConfig": False,
        "SequentialPipeline": False,
        "ParallelPipeline": False,
        "tool_idempotent": False,
        "GroundingEvaluator": False,
        "Reflector": False,
        "functional_entrypoint": False,
        "functional_task": False,
        "EventBus": False,
        "run_context": False,
        "Send": False,
        "EvalRunner": False,
        "oci_describe_use_tools": False,
        "WorkbenchManifest": True,
    }
    if not locus_sdk_installed():
        capabilities["WorkbenchManifest"] = True
        return capabilities
    try:
        import locus  # type: ignore
        from locus.multiagent import functional  # type: ignore
        from locus import observability  # type: ignore

        try:
            from locus.tools import tool as locus_tool  # type: ignore
        except Exception:
            locus_tool = getattr(locus, "tool", None)

        capabilities["StateGraph"] = hasattr(locus, "StateGraph")
        capabilities["GraphConfig"] = hasattr(locus, "GraphConfig")
        capabilities["SequentialPipeline"] = hasattr(locus, "SequentialPipeline")
        capabilities["ParallelPipeline"] = hasattr(locus, "ParallelPipeline")
        capabilities["tool_idempotent"] = locus_tool is not None
        capabilities["GroundingEvaluator"] = hasattr(locus, "GroundingEvaluator")
        capabilities["Reflector"] = hasattr(locus, "Reflector")
        capabilities["functional_entrypoint"] = hasattr(functional, "entrypoint")
        capabilities["functional_task"] = hasattr(functional, "task")
        capabilities["EventBus"] = hasattr(observability, "EventBus")
        capabilities["run_context"] = hasattr(observability, "run_context")
        capabilities["Send"] = importlib.util.find_spec("locus.core.send") is not None
        capabilities["EvalRunner"] = importlib.util.find_spec("locus.evaluation") is not None
        oci_spec = importlib.util.find_spec("locus.tools.oci")
        if oci_spec is not None:
            from locus.tools import oci as locus_oci_tools  # type: ignore

            capabilities["oci_describe_use_tools"] = all(
                hasattr(locus_oci_tools, name) for name in {"describe_oci", "use_oci"}
            )
    except Exception:
        return capabilities
    return capabilities


def collect_locus_status(config: Optional[Config] = None) -> LocusStatus:
    installed = locus_sdk_installed()
    run_mode = config.app.default_run_mode if config else "hard_zero"
    hard_zero = run_mode == "hard_zero"
    capabilities = locus_sdk_capabilities()
    engine = "locus_sdk_stategraph_local_tools" if installed else "locus_compatible_local_adapter"
    active_primitives = [
        name
        for name, enabled in capabilities.items()
        if enabled
        and name
        in {
            "StateGraph",
            "GraphConfig",
            "tool_idempotent",
            "GroundingEvaluator",
            "Reflector",
            "functional_entrypoint",
            "functional_task",
            "EventBus",
            "run_context",
            "Send",
            "EvalRunner",
            "WorkbenchManifest",
        }
    ]
    notes = [
        "The console uses Locus StateGraph execution for daily, Friday, production-pilot, and production-test workflows when the SDK is installed.",
        "A local describe/use dispatcher exposes safe workflow operations with read-only defaults.",
        "Production-test package runs now route candidate selection, intelligence, drafting, approval packet creation, checklist, and shortlist work through local Locus nodes.",
        "Hard Zero Mode keeps paid model/provider calls disabled even when the SDK is installed.",
        "Current agents use deterministic local tools until you intentionally enable a paid-capable provider.",
        "If Locus OCI describe/use tools are installed, they remain outside this app's active tool surface.",
    ]
    if not installed:
        notes.insert(0, "Install locus-sdk to activate the Oracle Locus SDK runtime surface.")

    return LocusStatus(
        sdk_installed=installed,
        engine=engine,
        hard_zero_safe=hard_zero,
        provider_mode="deterministic_local_tools",
        install_commands=locus_install_commands(),
        enabled_workflows=[
            "daily_scan",
            "friday_package",
            "production_pilot",
            "production_test_package",
        ],
        active_primitives=active_primitives,
        sdk_capabilities=capabilities,
        notes=notes,
    )


def render_locus_status(status: LocusStatus) -> str:
    lines = [
        "Locus Workflow Engine Status",
        f"SDK installed: {status.sdk_installed}",
        f"Engine: {status.engine}",
        f"Hard Zero safe: {status.hard_zero_safe}",
        f"Provider mode: {status.provider_mode}",
        "",
        "Enabled workflows:",
    ]
    lines.extend(f"- {workflow}" for workflow in status.enabled_workflows)
    lines.extend(["", "Active SDK primitives:"])
    if status.active_primitives:
        lines.extend(f"- {primitive}" for primitive in status.active_primitives)
    else:
        lines.append("- none yet; install locus-sdk to activate SDK-backed primitives")
    lines.extend(["", "SDK capabilities:"])
    lines.extend(
        f"- {name}: {'available' if enabled else 'not available'}"
        for name, enabled in sorted(status.sdk_capabilities.items())
    )
    lines.extend(["", "Setup commands:"])
    lines.extend(f"- {command}" for command in status.install_commands)
    lines.extend(["", "Notes:"])
    lines.extend(f"- {note}" for note in status.notes)
    return "\n".join(lines)


def locus_workflow_definitions() -> List[LocusWorkflowDefinition]:
    return [
        LocusWorkflowDefinition(
            workflow="daily_scan",
            purpose="Load sources, ingest public findings, and score them without paid APIs.",
            pattern="StateGraph",
            nodes=["init_db", "load_sources", "ingest", "score"],
            human_gates=["No external publishing or email side effects are allowed."],
        ),
        LocusWorkflowDefinition(
            workflow="friday_package",
            purpose="Refresh scores, build the weekly brief, and produce intelligence artifacts.",
            pattern="StateGraph",
            nodes=["init_db", "score", "weekly_package", "intelligence"],
            human_gates=[
                "Unsupported claims must be surfaced before approval.",
                "Public posting requires later human approval and manual archive.",
            ],
        ),
        LocusWorkflowDefinition(
            workflow="production_pilot",
            purpose="Run the end-to-end local readiness loop for live-source pilot operation.",
            pattern="StateGraph with nested subworkflow traces",
            nodes=[
                "load_sources",
                "preflight",
                "approval_url_gate",
                "daily_scan",
                "friday_package",
                "source_audit",
                "readiness",
                "checklist",
            ],
            human_gates=[
                "Apps Script deployment remains a manual Google account gate.",
                "Approval import is required before manual posting package creation.",
                "LinkedIn publishing remains human copy/paste only.",
            ],
        ),
        LocusWorkflowDefinition(
            workflow="production_test_package",
            purpose="Select a candidate, draft, create approval assets, validate the queue, and hand off to the operator.",
            pattern="StateGraph with local deterministic tools",
            nodes=[
                "candidate",
                "weekly_package",
                "intelligence",
                "deployment",
                "drafting",
                "approval_packet",
                "checklist",
                "shortlist",
            ],
            human_gates=[
                "Human source-quality review before public posting.",
                "Apps Script deployment and mobile approval before import.",
                "Manual LinkedIn copy/paste and archive after approval import.",
            ],
        ),
    ]


def _fallback_mermaid(definition: LocusWorkflowDefinition) -> str:
    lines = ["graph LR", "    START([Start])"]
    previous = "START"
    for node in definition.nodes:
        safe = node.replace("-", "_").replace(" ", "_")
        lines.append(f"    {safe}[{node}]")
        lines.append(f"    {previous} --> {safe}")
        previous = safe
    lines.append("    END([End])")
    lines.append(f"    {previous} --> END")
    return "\n".join(lines) + "\n"


def _workflow_mermaid(definition: LocusWorkflowDefinition) -> str:
    if not locus_sdk_installed():
        return _fallback_mermaid(definition)
    try:
        from locus import END, START, GraphConfig, StateGraph  # type: ignore
        from locus.multiagent.visualize import draw_mermaid  # type: ignore

        graph = StateGraph(
            name=definition.workflow,
            description=definition.purpose,
            config=GraphConfig(parallel=False),
        )
        for node in definition.nodes:
            graph.add_node(node, lambda state: state, description=f"{definition.workflow}:{node}")
        if definition.nodes:
            graph.add_edge(START, definition.nodes[0])
            for previous, current in zip(definition.nodes, definition.nodes[1:], strict=False):
                graph.add_edge(previous, current)
            graph.add_edge(definition.nodes[-1], END)
        return draw_mermaid(graph, direction="LR") + "\n"
    except Exception:
        return _fallback_mermaid(definition)


def _compact_sdk_value(value: Any, depth: int = 0) -> Any:
    if depth > 1:
        return type(value).__name__
    if isinstance(value, str):
        return value if len(value) <= 500 else value[:500] + "... [truncated]"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        if len(value) <= 10 and all(isinstance(item, (str, int, float, bool)) for item in value):
            return value
        return f"{len(value)} item(s)"
    if isinstance(value, dict):
        return {
            str(key): _compact_sdk_value(item, depth + 1)
            for key, item in value.items()
            if not str(key).startswith("_node_")
        }
    return str(value)


def _compact_sdk_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        str(key): _compact_sdk_value(value)
        for key, value in state.items()
        if not str(key).startswith("_node_")
    }


def _node_error_text(node_result: Any) -> str:
    for attr in ["error", "exception", "message", "traceback"]:
        value = getattr(node_result, attr, "")
        if value:
            return str(value)
    if isinstance(node_result, dict):
        for key in ["error", "exception", "message", "traceback"]:
            value = node_result.get(key)
            if value:
                return str(value)
    return ""


async def _execute_state_graph_async(
    workflow: str,
    nodes: List[LocusSDKNodeSpec],
    initial_state: Optional[Dict[str, Any]] = None,
    parallel: bool = False,
) -> LocusSDKRun:
    try:
        from locus import END, START, GraphConfig, StateGraph  # type: ignore
        from locus.observability import get_event_bus, run_context  # type: ignore
    except Exception as exc:
        return LocusSDKRun(
            used_sdk=False,
            primitive="StateGraph",
            success=False,
            error=f"Locus StateGraph unavailable: {exc}",
        )

    try:
        graph = StateGraph(
            name=workflow,
            description=f"{workflow} executed by AI LinkedIn Automation local tools",
            config=GraphConfig(parallel=parallel),
        )
        for node in nodes:
            graph.add_node(node.node_id, node.executor, description=node.description)
        if nodes:
            graph.add_edge(START, nodes[0].node_id)
            for previous, current in zip(nodes, nodes[1:], strict=False):
                graph.add_edge(previous.node_id, current.node_id)
            graph.add_edge(nodes[-1].node_id, END)

        run_id = f"ai-linkedin-{workflow}-{uuid4().hex[:10]}"
        async with run_context(run_id):
            result = await graph.execute(initial_state or {})
        bus = get_event_bus()
        await bus.close_stream(run_id)
        observability_events: List[Dict[str, Any]] = []
        async for event in bus.subscribe(run_id):
            observability_events.append(event.to_dict())
        node_statuses = {
            node_id: str(node_result.status) for node_id, node_result in result.node_results.items()
        }
        node_errors = {
            node_id: error
            for node_id, node_result in result.node_results.items()
            if (error := _node_error_text(node_result))
        }
        error = ""
        if not result.success:
            failed_nodes = [
                node_id
                for node_id, status in node_statuses.items()
                if status.lower() not in {"success", "succeeded", "completed", "passed"}
            ]
            detail = "; ".join(f"{node_id}: {message}" for node_id, message in node_errors.items())
            if detail:
                error = detail
            elif failed_nodes:
                error = f"StateGraph failed in node(s): {', '.join(failed_nodes)}"
            else:
                error = "StateGraph execution returned unsuccessful status without node error details."
        return LocusSDKRun(
            used_sdk=True,
            primitive="StateGraph",
            success=result.success,
            graph_id=result.graph_id,
            run_id=run_id,
            execution_order=list(result.execution_order),
            node_statuses=node_statuses,
            node_errors=node_errors,
            final_state=_compact_sdk_state(dict(result.final_state)),
            observability_event_count=len(observability_events),
            observability_events=observability_events[:40],
            duration_ms=float(result.duration_ms or 0),
            error=error,
        )
    except Exception as exc:
        return LocusSDKRun(
            used_sdk=True,
            primitive="StateGraph",
            success=False,
            error=str(exc),
        )


def execute_state_graph(
    workflow: str,
    nodes: List[LocusSDKNodeSpec],
    initial_state: Optional[Dict[str, Any]] = None,
    parallel: bool = False,
) -> LocusSDKRun:
    if not locus_sdk_installed():
        return LocusSDKRun(
            used_sdk=False,
            primitive="StateGraph",
            success=False,
            error="locus-sdk is not installed",
        )
    return asyncio.run(_execute_state_graph_async(workflow, nodes, initial_state, parallel))


def _write_capability_report(config: Config, report: LocusCapabilityReport) -> LocusCapabilityReport:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = _trace_dir(config)
    report.markdown_path = str(output_dir / f"{timestamp}_capability_check.md")
    report.json_path = str(output_dir / f"{timestamp}_capability_check.json")

    lines = [
        "# Locus Capability Check",
        "",
        f"Generated: {report.generated_at}",
        f"Status: {report.status}",
        f"SDK installed: {report.sdk_installed}",
        "",
        "## Checks",
        "",
    ]
    for check in report.checks:
        lines.append(f"- [{check.status.upper()}] {check.name}: {check.details}")

    Path(report.markdown_path).write_text("\n".join(lines) + "\n")
    Path(report.json_path).write_text(json.dumps(asdict(report), indent=2))
    latest_path = output_dir / "latest_capability_check.json"
    latest_path.write_text(json.dumps(asdict(report), indent=2))
    return report


def run_locus_capability_check(config: Config) -> LocusCapabilityReport:
    report = LocusCapabilityReport(
        status="passed",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        sdk_installed=locus_sdk_installed(),
    )

    def add(name: str, status: str, details: str) -> None:
        report.checks.append(LocusCapabilityCheck(name, status, details))
        if status == "failed":
            report.status = "failed"

    capabilities = locus_sdk_capabilities()
    if not report.sdk_installed:
        add("SDK import", "failed", "locus-sdk is not installed")
        return _write_capability_report(config, report)

    add(
        "SDK primitives",
        "passed" if all(capabilities.values()) else "warning",
        ", ".join(
            f"{name}={'yes' if enabled else 'no'}"
            for name, enabled in sorted(capabilities.items())
        ),
    )

    graph_run = execute_state_graph(
        "locus_capability_check",
        [
            LocusSDKNodeSpec(
                "prepare",
                "capability",
                "prepare",
                lambda state: {"prepared": True, **state},
                "Prepare local deterministic state",
            ),
            LocusSDKNodeSpec(
                "finish",
                "capability",
                "finish",
                lambda state: {"finished": state.get("prepared") is True, **state},
                "Finish local deterministic graph",
            ),
        ],
        initial_state={"input": "local"},
    )
    add(
        "StateGraph execution",
        "passed" if graph_run.used_sdk and graph_run.success else "failed",
        "order="
        f"{graph_run.execution_order}; observability_events={graph_run.observability_event_count}; "
        f"error={graph_run.error or 'none'}",
    )

    try:
        from locus import GroundingEvaluator, ParallelPipeline, SequentialPipeline  # type: ignore
        from locus.agent.composition import LoopAgent  # type: ignore
        from locus.core.send import Send  # type: ignore
        from locus.core.state import AgentState, ToolExecution  # type: ignore
        from locus.evaluation import EvalCase, EvalRunner  # type: ignore
        from locus.multiagent.functional import entrypoint, task  # type: ignore
        from locus.observability import get_event_bus, run_context  # type: ignore
        from locus.reasoning.reflexion import Reflector  # type: ignore

        try:
            from locus.tools import tool  # type: ignore
        except Exception:
            from locus import tool  # type: ignore

        class _LocalAgentResult:
            def __init__(self, message: str):
                self.message = message
                self.iterations = 1
                self.tool_executions: List[Any] = []

        class _LocalAgent:
            def __init__(self, name: str):
                self.name = name

            def run_sync(self, prompt: str) -> _LocalAgentResult:
                return _LocalAgentResult(f"{self.name}: {prompt} APPROVED")

        @tool(idempotent=True)
        def local_status_probe(name: str) -> Dict[str, str]:
            """Return local zero-spend status for a named component."""
            return {"component": name, "status": "available"}

        add(
            "Idempotent tool decorator",
            "passed" if local_status_probe.idempotent else "failed",
            f"tool={local_status_probe.name}; idempotent={local_status_probe.idempotent}",
        )

        grounding = GroundingEvaluator().evaluate(
            claims=["Hard Zero Mode blocks paid model calls"],
            evidence=["Hard Zero Mode blocks paid model calls unless a future guarded mode is enabled"],
        )
        add(
            "GroundingEvaluator",
            "passed" if grounding.score >= 0.5 and not grounding.requires_replan else "failed",
            f"score={grounding.score:.2f}; ungrounded={len(grounding.ungrounded_claims)}",
        )

        state = AgentState().with_tool_execution(
            ToolExecution(
                tool_name="local_status_probe",
                tool_call_id="capability-check",
                arguments={"name": "locus"},
                result="available",
            )
        )
        reflection = Reflector().reflect(state)
        add(
            "Reflector",
            "passed",
            f"assessment={reflection.assessment}; confidence_delta={reflection.confidence_delta:.2f}",
        )

        async def _run_composition_checks() -> Dict[str, Any]:
            run_id = f"ai-linkedin-capability-composition-{uuid4().hex[:8]}"
            async with run_context(run_id):
                sequential = await SequentialPipeline(
                    agents=[_LocalAgent("source"), _LocalAgent("editor")]
                ).run("check local workflow")
                parallel = await ParallelPipeline(
                    agents=[_LocalAgent("audit"), _LocalAgent("readiness")]
                ).run("fan out checks")
                loop_result = await LoopAgent(
                    agent=_LocalAgent("reviewer"),
                    condition=lambda output: "APPROVED" in output,
                    max_loops=3,
                ).run("review once")
            bus = get_event_bus()
            await bus.close_stream(run_id)
            observed = []
            async for event in bus.subscribe(run_id):
                observed.append(event.to_dict())
            return {
                "sequential": sequential.success,
                "parallel": parallel.success,
                "loop": loop_result.success and len(loop_result.outputs) == 1,
                "events": len(observed),
            }

        composition = asyncio.run(_run_composition_checks())
        add(
            "Composition pipelines",
            "passed"
            if composition["sequential"] and composition["parallel"] and composition["loop"]
            else "failed",
            f"sequential={composition['sequential']}; parallel={composition['parallel']}; "
            f"loop={composition['loop']}; events={composition['events']}",
        )

        send = Send(node="worker", payload={"task": "verify"}, metadata={"workflow": "capability"})
        add(
            "Send primitive",
            "passed" if send.node == "worker" and send.payload["task"] == "verify" else "failed",
            f"node={send.node}; send_id={send.send_id}",
        )

        eval_report = EvalRunner(_LocalAgent("eval")).run(
            [
                EvalCase(
                    name="local_agent_contract",
                    prompt="Say APPROVED",
                    expected_output_contains=["APPROVED"],
                    max_iterations=2,
                    max_duration_ms=1000,
                )
            ]
        )
        add(
            "Evaluation framework",
            "passed" if eval_report.failed == 0 else "failed",
            eval_report.summary().splitlines()[0],
        )

        @task
        async def increment(value: int) -> int:
            return value + 1

        @entrypoint
        async def local_functional_workflow(value: int) -> int:
            return await increment(value)

        functional_result = asyncio.run(local_functional_workflow(1))
        task_result = local_functional_workflow.get_result()
        add(
            "Functional task/entrypoint",
            "passed" if functional_result == 2 and task_result and task_result.success else "failed",
            f"result={functional_result}; task_count={len(task_result.tasks) if task_result else 0}",
        )
    except Exception as exc:
        add("SDK reasoning/tooling primitives", "failed", str(exc))

    try:
        package = build_locus_workbench_package(config)
        add(
            "Workbench package",
            "passed" if package.status == "ready" else "failed",
            package.output_dir,
        )
    except Exception as exc:
        add("Workbench package", "failed", str(exc))

    return _write_capability_report(config, report)


def build_locus_workbench_package(config: Config) -> LocusWorkbenchPackage:
    """Export a local Locus/Workbench package without starting external services."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = resolve_project_path(config.storage.exports_dir) / "locus" / "workbench" / timestamp
    diagrams_dir = output_dir / "diagrams"
    output_dir.mkdir(parents=True, exist_ok=True)
    diagrams_dir.mkdir(parents=True, exist_ok=True)

    status = collect_locus_status(config)
    definitions = locus_workflow_definitions()
    diagrams: Dict[str, str] = {}
    for definition in definitions:
        diagram_path = diagrams_dir / f"{definition.workflow}.mmd"
        diagram_path.write_text(_workflow_mermaid(definition))
        diagrams[definition.workflow] = str(diagram_path)

    manifest = {
        "name": "AI LinkedIn Automation Locus Workbench Package",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "hard_zero_mode": status.hard_zero_safe,
        "provider_mode": status.provider_mode,
        "engine": status.engine,
        "sdk_installed": status.sdk_installed,
        "active_primitives": status.active_primitives,
        "sdk_capabilities": status.sdk_capabilities,
        "workflows": [asdict(definition) for definition in definitions],
        "diagrams": diagrams,
        "safety_policy": {
            "paid_model_calls": "blocked in hard_zero mode",
            "email_sending": "disabled; local files only",
            "google_writeback": "manual CSV/App Script gate only",
            "linkedin_publishing": "manual copy/paste only",
            "local_tool_dispatch": "read-only by default; local writes require explicit allow_local_writes",
            "oci_tools": "not used by this project",
        },
        "local_describe_use_tools": {
            "pattern": "describe_then_dispatch",
            "describe_function": "describe_locus_local_tools",
            "dispatch_function": "use_locus_local_tool",
            "sdk_wrapper_function": "locus_local_sdk_tools",
            "sdk_tool_decorator": "locus.tools.tool(idempotent=True)",
            "default_mode": "read_only",
            "write_gate": "allow_local_writes",
            "external_side_effects": False,
        },
        "upstream_locus_repo_alignment": {
            "repository": "https://github.com/oracle-samples/locus",
            "applied_patterns": [
                "StateGraph local workflow control plane",
                "run_context/EventBus trace metadata for observable workflow runs",
                "plain Python tools wrapped with locus.tools.tool(idempotent=True) when the SDK is installed",
                "offline/local workflow operation without mandatory cloud credentials",
            ],
            "intentionally_not_used": [
                "OCI tenancy operations and locus-sdk[oci] extras",
                "locus.tools.oci describe_oci/use_oci dispatch, even if installed",
                "provider-backed LLM agents in Hard Zero Mode",
                "cloud memory, A2A, or deployment paths that could add operational cost",
            ],
        },
        "recommended_next_locus_steps": [
            "Keep StateGraph as the production control plane for local workflows.",
            "Use the local describe/use dispatcher when an agent needs to discover and run project workflow tools.",
            "Use EventBus run IDs and trace artifacts for operator/debug observability.",
            "Use Workbench diagrams/manifests as the visual workflow map.",
            "Do not add the OCI tool adapter to this repo; the useful pattern is introspection plus guarded dispatch.",
            "Do not enable Router/LLM/A2A/provider-backed agents until a non-zero spend mode is intentionally approved.",
        ],
    }

    manifest_path = output_dir / "locus_workbench_manifest.json"
    json_path = output_dir / "locus_workbench_package.json"
    readme_path = output_dir / "README.md"

    manifest_path.write_text(json.dumps(manifest, indent=2))
    lines = [
        "# AI LinkedIn Automation Locus Workbench Package",
        "",
        f"Generated: {manifest['generated_at']}",
        f"Engine: {status.engine}",
        f"Provider mode: {status.provider_mode}",
        f"Hard Zero Mode: {status.hard_zero_safe}",
        "",
        "## What This Package Is",
        "",
        "This is a local, zero-spend workflow map for the AI LinkedIn Console. It exports the Locus workflow definitions, Mermaid diagrams, active SDK capability matrix, and safety policy for Workbench-style review.",
        "",
        "## Workflows",
        "",
    ]
    for definition in definitions:
        lines.extend(
            [
                f"### {definition.workflow}",
                f"- Purpose: {definition.purpose}",
                f"- Pattern: {definition.pattern}",
                f"- Nodes: {', '.join(definition.nodes)}",
                f"- Diagram: {diagrams[definition.workflow]}",
                "",
            ]
        )
    lines.extend(
        [
            "## Guardrails",
            "",
            "- No paid model/provider calls are enabled.",
            "- No Google API write-back is performed by this app.",
            "- No email is sent.",
            "- No LinkedIn API publishing is attempted.",
            "- Local describe/use dispatch is read-only by default; local writes require explicit opt-in.",
            "- OCI tools are not part of this project workflow.",
            "",
            "## Files",
            "",
            f"- Manifest: {manifest_path}",
            f"- Package JSON: {json_path}",
        ]
    )
    readme_path.write_text("\n".join(lines) + "\n")

    package = LocusWorkbenchPackage(
        status="ready",
        generated_at=str(manifest["generated_at"]),
        output_dir=str(output_dir),
        manifest_path=str(manifest_path),
        readme_path=str(readme_path),
        diagrams=diagrams,
        json_path=str(json_path),
    )
    json_path.write_text(json.dumps(asdict(package), indent=2))

    latest_dir = resolve_project_path(config.storage.exports_dir) / "locus" / "workbench"
    (latest_dir / "latest_workbench_package.json").write_text(json.dumps(asdict(package), indent=2))
    return package


def default_agents(workflow: str) -> List[LocusAgentSpec]:
    shared = {
        "guardrail": LocusAgentSpec(
            key="guardrail",
            name="Guardrail Agent",
            responsibility="Keep Hard Zero Mode, approval gates, and no-publish safety rules in force.",
            pattern_role="approval_gate",
            local_tooling="cost_guard, publishing safety gate, integration status",
        ),
        "operator": LocusAgentSpec(
            key="operator",
            name="Operator Handoff Agent",
            responsibility="Surface the next plain-English human action for the business console.",
            pattern_role="human_handoff",
            local_tooling="pilot checklist, business console state",
        ),
    }
    workflow_agents = {
        "daily_scan": [
            LocusAgentSpec(
                key="source_loader",
                name="Source Loader Agent",
                responsibility="Synchronize configured recurring and manual source definitions.",
                pattern_role="tool_worker",
                local_tooling="source registry loader",
            ),
            LocusAgentSpec(
                key="ingestion",
                name="Ingestion Agent",
                responsibility="Fetch source items and normalize findings without paid API calls.",
                pattern_role="tool_worker",
                local_tooling="RSS/manual ingestion, normalizer",
            ),
            LocusAgentSpec(
                key="scoring",
                name="Scoring Agent",
                responsibility="Score findings for executive relevance, source quality, and publish readiness.",
                pattern_role="tool_worker",
                local_tooling="deterministic scoring modules",
            ),
            shared["guardrail"],
        ],
        "friday_package": [
            LocusAgentSpec(
                key="scoring",
                name="Scoring Agent",
                responsibility="Refresh topic and finding scores before weekly packaging.",
                pattern_role="tool_worker",
                local_tooling="deterministic scoring modules",
            ),
            LocusAgentSpec(
                key="weekly_editor",
                name="Weekly Brief Agent",
                responsibility="Build the weekly brief and no-API prompt packet.",
                pattern_role="tool_worker",
                local_tooling="weekly package builder",
            ),
            LocusAgentSpec(
                key="source_governance",
                name="Source Governance Agent",
                responsibility="Audit source quality and governance gaps.",
                pattern_role="fanout_worker",
                local_tooling="source audit",
            ),
            LocusAgentSpec(
                key="topic_cluster",
                name="Topic Cluster Agent",
                responsibility="Group related topics for stronger editorial decisions.",
                pattern_role="fanout_worker",
                local_tooling="topic clustering",
            ),
            LocusAgentSpec(
                key="discovery",
                name="Discovery Agent",
                responsibility="Identify verification/discovery work needed before public posting.",
                pattern_role="fanout_worker",
                local_tooling="discovery queue",
            ),
            shared["guardrail"],
        ],
        "production_pilot": [
            LocusAgentSpec(
                key="preflight",
                name="Preflight Agent",
                responsibility="Check runtime, storage, source registry, guardrails, and publishing safety.",
                pattern_role="entry_gate",
                local_tooling="preflight checks",
            ),
            LocusAgentSpec(
                key="daily_scan",
                name="Daily Scan Agent",
                responsibility="Run the daily scan subworkflow.",
                pattern_role="subworkflow",
                local_tooling="daily scan workflow",
            ),
            LocusAgentSpec(
                key="friday_package",
                name="Friday Package Agent",
                responsibility="Run the Friday package subworkflow.",
                pattern_role="subworkflow",
                local_tooling="Friday package workflow",
            ),
            LocusAgentSpec(
                key="readiness",
                name="Readiness Agent",
                responsibility="Build readiness and checklist artifacts.",
                pattern_role="approval_gate",
                local_tooling="readiness report, pilot checklist",
            ),
            shared["operator"],
            shared["guardrail"],
        ],
        "production_test_package": [
            LocusAgentSpec(
                key="candidate_selector",
                name="Candidate Selection Agent",
                responsibility="Choose the strongest topic candidate or validate a requested topic.",
                pattern_role="orchestrator",
                local_tooling="topic scoring and top topics",
            ),
            LocusAgentSpec(
                key="intelligence",
                name="Intelligence Crew",
                responsibility="Build source audit, cluster, discovery, and citation artifacts.",
                pattern_role="fanout_group",
                local_tooling="intelligence report",
            ),
            LocusAgentSpec(
                key="drafting",
                name="Drafting Agent",
                responsibility="Create a LinkedIn draft from the selected topic.",
                pattern_role="tool_worker",
                local_tooling="deterministic no-API draft generator",
            ),
            LocusAgentSpec(
                key="approval_packet",
                name="Approval Packet Agent",
                responsibility="Create review queue, notification copy, token, and validation artifacts.",
                pattern_role="approval_gate",
                local_tooling="approval packet, notification package, sheet validation",
            ),
            shared["operator"],
            shared["guardrail"],
        ],
    }
    return workflow_agents.get(workflow, [shared["operator"], shared["guardrail"]])


def start_trace(
    workflow: str,
    pattern: str,
    human_gates: Optional[List[str]] = None,
    config: Optional[Config] = None,
) -> LocusWorkflowTrace:
    status = collect_locus_status(config)
    trace = LocusWorkflowTrace(
        workflow=workflow,
        pattern=pattern,
        engine=status.engine,
        sdk_installed=status.sdk_installed,
        hard_zero_mode=status.hard_zero_safe,
        provider_mode=status.provider_mode,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        human_gates=human_gates or [],
        agents=default_agents(workflow),
        install_commands=status.install_commands,
    )
    record_event(
        trace,
        "guardrail",
        "workflow_start",
        "started",
        f"{workflow} started with {trace.engine}; provider mode is {trace.provider_mode}.",
    )
    return trace


def record_event(
    trace: LocusWorkflowTrace,
    agent: str,
    event_type: str,
    status: str,
    message: str,
) -> None:
    trace.events.append(
        LocusWorkflowEvent(
            sequence=len(trace.events) + 1,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            workflow=trace.workflow,
            agent=agent,
            event_type=event_type,
            status=status,
            message=message,
        )
    )


def _trace_dir(config: Config) -> Path:
    output_dir = resolve_project_path(config.storage.exports_dir) / "locus"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_trace(
    config: Config,
    trace: LocusWorkflowTrace,
    output_paths: Optional[Dict[str, str]] = None,
) -> LocusWorkflowTrace:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = _trace_dir(config)
    trace.output_paths.update(output_paths or {})
    trace.markdown_path = str(output_dir / f"{timestamp}_{trace.workflow}_trace.md")
    trace.json_path = str(output_dir / f"{timestamp}_{trace.workflow}_trace.json")

    lines = [
        f"# Locus Workflow Trace: {trace.workflow}",
        "",
        f"Generated: {trace.generated_at}",
        f"Engine: {trace.engine}",
        f"SDK installed: {trace.sdk_installed}",
        f"Pattern: {trace.pattern}",
        f"Provider mode: {trace.provider_mode}",
        f"Hard Zero Mode: {trace.hard_zero_mode}",
        "",
        "## Agent Roster",
        "",
    ]
    for agent in trace.agents:
        lines.extend(
            [
                f"### {agent.name}",
                f"- Key: `{agent.key}`",
                f"- Pattern role: {agent.pattern_role}",
                f"- Responsibility: {agent.responsibility}",
                f"- Local tooling: {agent.local_tooling}",
                "",
            ]
        )

    if trace.human_gates:
        lines.extend(["## Human Gates", ""])
        lines.extend(f"- {gate}" for gate in trace.human_gates)
        lines.append("")

    lines.extend(["## Events", ""])
    for event in trace.events:
        lines.append(
            f"{event.sequence}. [{event.status}] {event.agent}/{event.event_type}: {event.message}"
        )

    if trace.output_paths:
        lines.extend(["", "## Output Paths", ""])
        for key, path in sorted(trace.output_paths.items()):
            lines.append(f"- {key}: {path}")

    if trace.sdk_runs:
        lines.extend(["", "## SDK Runs", ""])
        for run in trace.sdk_runs:
            lines.append(f"- Primitive: {run.get('primitive')}")
            lines.append(f"  Used SDK: {run.get('used_sdk')}")
            lines.append(f"  Success: {run.get('success')}")
            if run.get("run_id"):
                lines.append(f"  Run ID: {run.get('run_id')}")
            lines.append(f"  Execution order: {', '.join(run.get('execution_order') or [])}")
            lines.append(f"  Observability events: {run.get('observability_event_count', 0)}")
            if run.get("error"):
                lines.append(f"  Error: {run.get('error')}")

    lines.extend(["", "## Setup Commands", ""])
    lines.extend(f"- `{command}`" for command in trace.install_commands)

    Path(trace.markdown_path).write_text("\n".join(lines) + "\n")
    Path(trace.json_path).write_text(json.dumps(asdict(trace), indent=2))
    latest_path = output_dir / "latest_locus_trace.json"
    latest_path.write_text(json.dumps(asdict(trace), indent=2))
    return trace


def trace_metadata(trace: LocusWorkflowTrace) -> Dict[str, object]:
    return {
        "engine": trace.engine,
        "sdk_installed": trace.sdk_installed,
        "workflow": trace.workflow,
        "pattern": trace.pattern,
        "provider_mode": trace.provider_mode,
        "hard_zero_mode": trace.hard_zero_mode,
        "event_count": len(trace.events),
        "agent_count": len(trace.agents),
        "sdk_run_count": len(trace.sdk_runs),
        "sdk_graph_used": any(run.get("used_sdk") for run in trace.sdk_runs),
        "sdk_graph_success": all(run.get("success") for run in trace.sdk_runs)
        if trace.sdk_runs
        else False,
        "sdk_execution_order": trace.sdk_runs[-1].get("execution_order", []) if trace.sdk_runs else [],
        "sdk_run_id": trace.sdk_runs[-1].get("run_id", "") if trace.sdk_runs else "",
        "sdk_observability_event_count": trace.sdk_runs[-1].get("observability_event_count", 0)
        if trace.sdk_runs
        else 0,
        "human_gates": list(trace.human_gates),
        "trace_markdown": trace.markdown_path,
        "trace_json": trace.json_path,
        "install_commands": list(trace.install_commands),
    }
