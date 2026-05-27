from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from ai_linkedin_automation.config import CONFIG_DIR, Config, load_yaml_file
from ai_linkedin_automation.cost_guard import CostDecision, check_cost_allowed, load_cost_guard_config
from ai_linkedin_automation.locus_workflows import collect_locus_status


@dataclass
class IntegrationStatusItem:
    name: str
    enabled: bool
    mode: str
    paid_capable: bool
    cost_allowed: bool
    status: str
    reason: str


@dataclass
class IntegrationStatusReport:
    run_mode: str
    monthly_spend_cap_usd: float
    items: List[IntegrationStatusItem]

    @property
    def blocked_paid_capable_count(self) -> int:
        return sum(1 for item in self.items if item.paid_capable and not item.cost_allowed)


def _load_optional_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return load_yaml_file(path)


def _decision(provider: str, action: str, cost_config: Dict[str, Any]) -> CostDecision:
    return check_cost_allowed(provider, action, cost_config=cost_config)


def _status_for(enabled: bool, decision: CostDecision) -> str:
    if not enabled:
        return "disabled"
    return "available" if decision.allowed else "blocked"


def _item(
    *,
    name: str,
    enabled: bool,
    mode: str,
    paid_capable: bool,
    provider: str,
    action: str,
    cost_config: Dict[str, Any],
) -> IntegrationStatusItem:
    decision = _decision(provider, action, cost_config)
    return IntegrationStatusItem(
        name=name,
        enabled=enabled,
        mode=mode,
        paid_capable=paid_capable,
        cost_allowed=decision.allowed,
        status=_status_for(enabled, decision),
        reason=decision.reason,
    )


def collect_integration_status(config: Config) -> IntegrationStatusReport:
    """Return a local, zero-network status report for optional integrations."""
    cost_config = load_cost_guard_config()
    registry = _load_optional_yaml(CONFIG_DIR / "provider_registry.yaml")
    integration_config = _load_optional_yaml(CONFIG_DIR / "integrations.yaml")
    integrations = integration_config.get("integrations", {})
    providers = registry.get("providers", {})
    locus_status = collect_locus_status(config)

    items = [
        _item(
            name="Oracle Locus workflow engine",
            enabled=True,
            mode=locus_status.engine,
            paid_capable=False,
            provider="local_file",
            action="workflow_orchestration",
            cost_config=cost_config,
        ),
        _item(
            name="Local notification package",
            enabled=True,
            mode="local_file",
            paid_capable=False,
            provider="local_file",
            action="write_notification_package",
            cost_config=cost_config,
        ),
        _item(
            name="Google Sheets review queue CSV",
            enabled=True,
            mode="manual_csv",
            paid_capable=False,
            provider="local_file",
            action="write_review_queue_csv",
            cost_config=cost_config,
        ),
        _item(
            name="Google Sheets API write-back",
            enabled=bool(integrations.get("google_sheets_api", {}).get("enabled", False)),
            mode=integrations.get("google_sheets_api", {}).get("mode", "disabled"),
            paid_capable=True,
            provider="google_sheets_api",
            action="write_back",
            cost_config=cost_config,
        ),
        _item(
            name="Outlook local email files",
            enabled=True,
            mode="local_file",
            paid_capable=False,
            provider="local_file",
            action="write_outlook_email_files",
            cost_config=cost_config,
        ),
        _item(
            name="Microsoft Graph email sending",
            enabled=bool(integrations.get("microsoft_graph_email", {}).get("enabled", False)),
            mode=integrations.get("microsoft_graph_email", {}).get("mode", "disabled"),
            paid_capable=True,
            provider="microsoft_graph",
            action="send_email",
            cost_config=cost_config,
        ),
        _item(
            name="Apps Script approval webapp",
            enabled=config.review.approval_host == "google_apps_script",
            mode="manual_deploy",
            paid_capable=False,
            provider="apps_script_webapp",
            action="approval_page",
            cost_config=cost_config,
        ),
        _item(
            name="LinkedIn live API publishing",
            enabled=config.publishing.linkedin_api_enabled,
            mode="oauth_future_adapter",
            paid_capable=True,
            provider="linkedin_api",
            action="publish",
            cost_config=cost_config,
        ),
        _item(
            name="Media generation",
            enabled=bool(integrations.get("media_generation", {}).get("enabled", False)),
            mode=integrations.get("media_generation", {}).get("mode", "disabled"),
            paid_capable=True,
            provider="media_generation_api",
            action="generate_media",
            cost_config=cost_config,
        ),
    ]

    provider_labels = {
        "no_api": "No-API prompt packet provider",
        "openai": "OpenAI provider adapter",
        "claude": "Claude provider adapter",
        "gemini": "Gemini provider adapter",
    }
    for provider_name, provider_data in providers.items():
        provider_category = provider_data.get("provider_category", "local_file")
        items.append(
            _item(
                name=provider_labels.get(provider_name, f"{provider_name} provider adapter"),
                enabled=bool(provider_data.get("enabled", False)),
                mode=provider_name,
                paid_capable=bool(provider_data.get("paid_capable", False)),
                provider=provider_category if provider_category != "local_file" else "local_file",
                action="provider_call",
                cost_config=cost_config,
            )
        )

    return IntegrationStatusReport(
        run_mode=cost_config.get("run_mode", config.app.default_run_mode),
        monthly_spend_cap_usd=float(cost_config.get("monthly_spend_cap_usd", 0)),
        items=items,
    )


def format_integration_status(report: IntegrationStatusReport) -> str:
    lines = [
        "Integration Status",
        f"Run mode: {report.run_mode}",
        f"Monthly spend cap: ${report.monthly_spend_cap_usd:g}",
        "",
    ]
    for item in report.items:
        enabled_label = "enabled" if item.enabled else "disabled"
        paid_label = "paid-capable" if item.paid_capable else "zero-spend"
        lines.append(
            f"- {item.name}: {item.status} ({enabled_label}, {paid_label}, mode: {item.mode})"
        )
        lines.append(f"  Cost Guard: {item.reason}")
    return "\n".join(lines)
