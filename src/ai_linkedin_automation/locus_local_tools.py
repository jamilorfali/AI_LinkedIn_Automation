import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ai_linkedin_automation.config import Config
from ai_linkedin_automation.locus_workflows import (
    build_locus_workbench_package,
    collect_locus_status,
    locus_workflow_definitions,
    render_locus_status,
)


@dataclass(frozen=True)
class LocusLocalToolSpec:
    operation: str
    service: str
    description: str
    read_only: bool
    writes_local_files: bool
    external_side_effects: bool
    paid_capable: bool
    parameters: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


@dataclass
class LocusLocalToolResult:
    operation: str
    status: str
    read_only: bool
    external_side_effects: bool
    paid_capable: bool
    blocked_by: str = ""
    message: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)


def _workflow_manifest(config: Config, arguments: Dict[str, Any]) -> Dict[str, Any]:
    del arguments
    status = collect_locus_status(config)
    return {
        "engine": status.engine,
        "provider_mode": status.provider_mode,
        "hard_zero_safe": status.hard_zero_safe,
        "workflows": [asdict(definition) for definition in locus_workflow_definitions()],
    }


def _locus_status(config: Config, arguments: Dict[str, Any]) -> Dict[str, Any]:
    del arguments
    status = collect_locus_status(config)
    return {**asdict(status), "text": render_locus_status(status)}


def _integration_status(config: Config, arguments: Dict[str, Any]) -> Dict[str, Any]:
    del arguments
    from ai_linkedin_automation.integrations.status import collect_integration_status

    report = collect_integration_status(config)
    return {
        "run_mode": report.run_mode,
        "monthly_spend_cap_usd": report.monthly_spend_cap_usd,
        "blocked_paid_capable_count": report.blocked_paid_capable_count,
        "items": [asdict(item) for item in report.items],
    }


def _capability_check(config: Config, arguments: Dict[str, Any]) -> Dict[str, Any]:
    del arguments
    from ai_linkedin_automation.locus_workflows import run_locus_capability_check

    return asdict(run_locus_capability_check(config))


def _workbench_package(config: Config, arguments: Dict[str, Any]) -> Dict[str, Any]:
    del arguments
    return asdict(build_locus_workbench_package(config))


def _locus_e2e_dry_run(config: Config, arguments: Dict[str, Any]) -> Dict[str, Any]:
    from ai_linkedin_automation.business_console import run_locus_e2e_test

    week = str(arguments.get("week") or "current")
    return asdict(run_locus_e2e_test(config, week=week))


_EXECUTORS: Dict[str, Callable[[Config, Dict[str, Any]], Dict[str, Any]]] = {
    "workflow_manifest": _workflow_manifest,
    "locus_status": _locus_status,
    "integration_status": _integration_status,
    "capability_check": _capability_check,
    "workbench_package": _workbench_package,
    "locus_e2e_dry_run": _locus_e2e_dry_run,
}


def _import_locus_tool_decorator() -> Optional[Callable[..., Any]]:
    try:
        from locus.tools import tool  # type: ignore

        return tool
    except Exception:
        try:
            from locus import tool  # type: ignore

            return tool
        except Exception:
            return None


def locus_local_sdk_tools(config: Config) -> List[Any]:
    """Return optional Locus @tool wrappers around the local describe/use surface."""
    tool_decorator = _import_locus_tool_decorator()
    if tool_decorator is None:
        return []

    @tool_decorator(idempotent=True)
    def describe_ai_linkedin_tools(service: str = "", operation: str = "") -> Dict[str, Any]:
        """Describe safe local workflow tools by service or operation."""
        return describe_locus_local_tools(
            service=service or None,
            operation=operation or None,
        )

    @tool_decorator(idempotent=True)
    def use_ai_linkedin_tool(
        operation: str,
        arguments_json: str = "{}",
        allow_local_writes: bool = False,
    ) -> Dict[str, Any]:
        """Dispatch a safe local workflow operation after discovery."""
        try:
            arguments = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as exc:
            return {
                "operation": operation,
                "status": "failed",
                "blocked_by": "invalid_arguments_json",
                "message": str(exc),
            }
        if not isinstance(arguments, dict):
            return {
                "operation": operation,
                "status": "failed",
                "blocked_by": "invalid_arguments_json",
                "message": "arguments_json must decode to an object.",
            }
        return asdict(
            use_locus_local_tool(
                config,
                operation,
                arguments,
                allow_local_writes=allow_local_writes,
            )
        )

    return [describe_ai_linkedin_tools, use_ai_linkedin_tool]


def locus_local_tool_specs() -> Dict[str, LocusLocalToolSpec]:
    return {
        "workflow_manifest": LocusLocalToolSpec(
            operation="workflow_manifest",
            service="workflow_engine",
            description="Return the local workflow definitions and Hard Zero engine metadata.",
            read_only=True,
            writes_local_files=False,
            external_side_effects=False,
            paid_capable=False,
            notes=["Use this before choosing a workflow operation."],
        ),
        "locus_status": LocusLocalToolSpec(
            operation="locus_status",
            service="workflow_engine",
            description="Return Locus SDK availability, local engine mode, and setup notes.",
            read_only=True,
            writes_local_files=False,
            external_side_effects=False,
            paid_capable=False,
        ),
        "integration_status": LocusLocalToolSpec(
            operation="integration_status",
            service="safety",
            description="Return local integration and cost-guard status.",
            read_only=True,
            writes_local_files=False,
            external_side_effects=False,
            paid_capable=False,
        ),
        "capability_check": LocusLocalToolSpec(
            operation="capability_check",
            service="workflow_engine",
            description="Run the local Locus SDK capability check and write report artifacts.",
            read_only=False,
            writes_local_files=True,
            external_side_effects=False,
            paid_capable=False,
            notes=["Requires allow_local_writes because it writes Markdown/JSON reports."],
        ),
        "workbench_package": LocusLocalToolSpec(
            operation="workbench_package",
            service="workflow_engine",
            description="Export the local Workbench manifest and Mermaid diagrams.",
            read_only=False,
            writes_local_files=True,
            external_side_effects=False,
            paid_capable=False,
            notes=["Requires allow_local_writes because it writes export files."],
        ),
        "locus_e2e_dry_run": LocusLocalToolSpec(
            operation="locus_e2e_dry_run",
            service="workflow_engine",
            description="Run the local Locus E2E dry-run path and write diagnostics.",
            read_only=False,
            writes_local_files=True,
            external_side_effects=False,
            paid_capable=False,
            parameters={"week": "Optional ISO week such as 2026-W20; defaults to current."},
            notes=[
                "Requires allow_local_writes because it writes diagnostics and trace artifacts.",
                "This path uses dry-run workflow operations and does not publish or send email.",
            ],
        ),
    }


def describe_locus_local_tools(
    service: Optional[str] = None,
    operation: Optional[str] = None,
) -> Dict[str, Any]:
    """Progressively describe the safe local Locus tool surface."""
    specs = locus_local_tool_specs()
    if operation:
        spec = specs.get(operation)
        if not spec:
            return {
                "status": "not_found",
                "operation": operation,
                "available_operations": sorted(specs),
            }
        return {
            "status": "ok",
            "default_mode": "read_only",
            "safety_gate": "local writes require allow_local_writes=True",
            "spec": asdict(spec),
        }

    services = sorted({spec.service for spec in specs.values()})
    if service:
        service_specs = [spec for spec in specs.values() if spec.service == service]
        if not service_specs:
            return {
                "status": "not_found",
                "service": service,
                "available_services": services,
            }
        return {
            "status": "ok",
            "service": service,
            "default_mode": "read_only",
            "operations": [asdict(spec) for spec in service_specs],
        }

    return {
        "status": "ok",
        "pattern": "describe_then_dispatch",
        "default_mode": "read_only",
        "locus_sdk_tool_wrappers": "available" if _import_locus_tool_decorator() else "not_installed",
        "services": [
            {
                "service": service_name,
                "operation_count": sum(1 for spec in specs.values() if spec.service == service_name),
            }
            for service_name in services
        ],
        "next_steps": [
            "Call describe_locus_local_tools(service='workflow_engine') to inspect workflow operations.",
            "Call describe_locus_local_tools(operation='<name>') before dispatching a specific operation.",
            "Call use_locus_local_tool only after checking read_only and writes_local_files.",
        ],
    }


def use_locus_local_tool(
    config: Config,
    operation: str,
    arguments: Optional[Dict[str, Any]] = None,
    *,
    allow_local_writes: bool = False,
) -> LocusLocalToolResult:
    """Dispatch one local operation through a read-only-by-default safety gate."""
    specs = locus_local_tool_specs()
    spec = specs.get(operation)
    if not spec:
        return LocusLocalToolResult(
            operation=operation,
            status="failed",
            read_only=True,
            external_side_effects=False,
            paid_capable=False,
            blocked_by="unknown_operation",
            message=f"Unknown operation: {operation}",
            payload={"available_operations": sorted(specs)},
        )

    if spec.external_side_effects or spec.paid_capable:
        return LocusLocalToolResult(
            operation=operation,
            status="blocked",
            read_only=spec.read_only,
            external_side_effects=spec.external_side_effects,
            paid_capable=spec.paid_capable,
            blocked_by="external_or_paid_operation",
            message="This dispatcher only runs local zero-spend operations.",
        )

    if not spec.read_only and not allow_local_writes:
        return LocusLocalToolResult(
            operation=operation,
            status="blocked",
            read_only=spec.read_only,
            external_side_effects=spec.external_side_effects,
            paid_capable=spec.paid_capable,
            blocked_by="read_only_default",
            message="Local-write operation blocked. Re-run with allow_local_writes=True.",
            payload={"spec": asdict(spec)},
        )

    if not spec.read_only and config.app.default_run_mode != "hard_zero":
        return LocusLocalToolResult(
            operation=operation,
            status="blocked",
            read_only=spec.read_only,
            external_side_effects=spec.external_side_effects,
            paid_capable=spec.paid_capable,
            blocked_by="hard_zero_required",
            message="Local Locus write dispatch is only enabled in Hard Zero Mode.",
            payload={"run_mode": config.app.default_run_mode},
        )

    try:
        payload = _EXECUTORS[operation](config, arguments or {})
    except Exception as exc:
        return LocusLocalToolResult(
            operation=operation,
            status="failed",
            read_only=spec.read_only,
            external_side_effects=spec.external_side_effects,
            paid_capable=spec.paid_capable,
            message=str(exc),
        )

    return LocusLocalToolResult(
        operation=operation,
        status="completed",
        read_only=spec.read_only,
        external_side_effects=spec.external_side_effects,
        paid_capable=spec.paid_capable,
        message="Operation completed through local Locus dispatcher.",
        payload=payload,
    )


def write_locus_local_tool_description(path: Path) -> None:
    """Write the discovery manifest for agents that prefer a file artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(describe_locus_local_tools(), indent=2) + "\n")
