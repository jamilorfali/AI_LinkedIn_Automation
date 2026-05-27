import platform
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from ai_linkedin_automation.config import CONFIG_DIR, Config, load_yaml_file, resolve_project_path
from ai_linkedin_automation.cost_guard import check_cost_allowed
from ai_linkedin_automation.integrations.status import collect_integration_status
from ai_linkedin_automation.storage.db import resolve_db_path


@dataclass
class PreflightCheck:
    name: str
    status: str
    details: str


@dataclass
class PreflightReport:
    generated_at: str
    checks: List[PreflightCheck]

    @property
    def ok(self) -> bool:
        return not any(check.status == "fail" for check in self.checks)


def _check(status: str, name: str, details: str) -> PreflightCheck:
    return PreflightCheck(name=name, status=status, details=details)


def _python_check() -> PreflightCheck:
    version = sys.version_info
    details = f"Python {version.major}.{version.minor}.{version.micro} on {platform.system()}"
    if version >= (3, 11):
        return _check("pass", "Python runtime", details)
    return _check("fail", "Python runtime", f"{details}; Python 3.11+ is required")


def _db_check(config: Config) -> PreflightCheck:
    db_path = resolve_db_path(config.storage.sqlite_path)
    if not db_path.exists():
        return _check("warn", "SQLite database", f"Database does not exist yet: {db_path}")
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'runs'").fetchone()
        conn.close()
    except sqlite3.Error as exc:
        return _check("fail", "SQLite database", f"Could not open database: {exc}")
    if row:
        return _check("pass", "SQLite database", f"Database reachable: {db_path}")
    return _check("fail", "SQLite database", "Database exists but schema is incomplete")


def _sources_check() -> PreflightCheck:
    try:
        sources = load_yaml_file(CONFIG_DIR / "sources.yaml")
    except Exception as exc:
        return _check("fail", "Source registry", f"Could not load sources.yaml: {exc}")
    recurring_count = len(sources.get("recurring_sources", []))
    manual_count = len(sources.get("manual_sources", {}))
    if recurring_count or manual_count:
        return _check(
            "pass",
            "Source registry",
            f"{recurring_count} recurring source(s), {manual_count} manual source group(s)",
        )
    return _check("warn", "Source registry", "No sources are configured")


def _storage_dirs_check(config: Config) -> PreflightCheck:
    expected = [
        resolve_project_path(config.storage.exports_dir),
        resolve_project_path(config.storage.review_packets_dir),
        resolve_project_path(config.storage.logs_dir),
    ]
    missing = [str(path) for path in expected if not path.exists()]
    if missing:
        return _check("warn", "Storage directories", f"Missing directories: {', '.join(missing)}")
    return _check("pass", "Storage directories", "Exports, review packets, and logs dirs exist")


def _hard_zero_check(config: Config) -> PreflightCheck:
    if config.app.default_run_mode == "hard_zero":
        return _check("pass", "Run mode", "Hard Zero Mode is active")
    return _check("warn", "Run mode", f"Configured run mode is {config.app.default_run_mode}")


def _cost_guard_check() -> PreflightCheck:
    blocked = [
        check_cost_allowed("openai_api", "provider_call"),
        check_cost_allowed("linkedin_api", "publish"),
        check_cost_allowed("microsoft_graph", "send_email"),
    ]
    if all(not decision.allowed for decision in blocked):
        return _check("pass", "Cost Guard", "Paid-capable model, email, and publishing adapters are blocked")
    reasons = "; ".join(decision.reason for decision in blocked if decision.allowed)
    return _check("fail", "Cost Guard", f"Unexpected paid-capable adapter allowance: {reasons}")


def _publishing_check(config: Config) -> PreflightCheck:
    if not config.publishing.linkedin_api_enabled and config.publishing.require_approval_record:
        return _check("pass", "Publishing safety", "Live LinkedIn API disabled; approval records required")
    return _check("fail", "Publishing safety", "Publishing config is not in the safe v0 default posture")


def _integration_check(config: Config) -> PreflightCheck:
    report = collect_integration_status(config)
    risky = [item.name for item in report.items if item.paid_capable and item.enabled and item.cost_allowed]
    if risky:
        return _check("fail", "Optional integrations", f"Paid-capable integrations enabled: {', '.join(risky)}")
    return _check(
        "pass",
        "Optional integrations",
        f"{report.blocked_paid_capable_count} paid-capable integration(s) blocked by guardrails",
    )


def _approval_url_check() -> PreflightCheck:
    env_file = Path(".env")
    if env_file.exists() and "GOOGLE_APPS_SCRIPT_WEBAPP_URL" in env_file.read_text():
        return _check("pass", "Approval URL", ".env contains GOOGLE_APPS_SCRIPT_WEBAPP_URL")
    return _check(
        "warn",
        "Approval URL",
        "GOOGLE_APPS_SCRIPT_WEBAPP_URL is not configured; local tokens still work",
    )


def run_preflight(config: Config) -> PreflightReport:
    checks = [
        _python_check(),
        _hard_zero_check(config),
        _storage_dirs_check(config),
        _db_check(config),
        _sources_check(),
        _cost_guard_check(),
        _publishing_check(config),
        _integration_check(config),
        _approval_url_check(),
    ]
    return PreflightReport(generated_at=datetime.now().isoformat(timespec="seconds"), checks=checks)


def format_preflight_report(report: PreflightReport) -> str:
    lines = [
        "Preflight Report",
        f"Generated: {report.generated_at}",
        f"Overall: {'PASS' if report.ok else 'FAIL'}",
        "",
    ]
    for check in report.checks:
        lines.append(f"- [{check.status.upper()}] {check.name}: {check.details}")
    return "\n".join(lines)

