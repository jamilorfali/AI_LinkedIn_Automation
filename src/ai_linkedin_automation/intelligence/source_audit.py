import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional

from ai_linkedin_automation.config import CONFIG_DIR, Config, load_yaml_file
from ai_linkedin_automation.intelligence.common import domain_from_url, intelligence_dir, stable_id
from ai_linkedin_automation.storage.db import connect_db, transaction


TIER_RANK = {
    "blocked": 0,
    "social_signal_only": 1,
    "useful_but_verify": 2,
    "high_trust": 3,
    "primary": 4,
}


@dataclass
class SourceAuditIssue:
    source_id: str
    source_name: str
    severity: str
    issue_type: str
    detail: str
    recommendation: str


@dataclass
class SourceAuditReport:
    generated_at: str
    issues: List[SourceAuditIssue]
    markdown_path: str
    json_path: str

    @property
    def fail_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "fail")

    @property
    def warn_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warn")

    @property
    def info_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "info")


def _trusted_domain_tiers() -> Dict[str, str]:
    data = load_yaml_file(CONFIG_DIR / "trusted_domains.yaml")
    tiers: Dict[str, str] = {}
    for tier, domains in data.get("trusted_domains", {}).items():
        for domain in domains:
            tiers[str(domain).lower()] = tier
    return tiers


def _configured_domain_tier(domain: str, trusted: Dict[str, str]) -> Optional[str]:
    if not domain:
        return None
    for trusted_domain, tier in trusted.items():
        if domain == trusted_domain or domain.endswith(f".{trusted_domain}"):
            return tier
    return None


def _source_rows(config: Config) -> List[dict]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        rows = conn.execute(
            """
            SELECT id, name, type, source_type, trust_tier, url, rss_url, is_active, recurring_enabled
            FROM sources
            ORDER BY id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _issue(
    row: dict,
    severity: str,
    issue_type: str,
    detail: str,
    recommendation: str,
) -> SourceAuditIssue:
    return SourceAuditIssue(
        source_id=row["id"],
        source_name=row["name"],
        severity=severity,
        issue_type=issue_type,
        detail=detail,
        recommendation=recommendation,
    )


def _audit_row(row: dict, trusted: Dict[str, str]) -> List[SourceAuditIssue]:
    issues: List[SourceAuditIssue] = []
    url = row.get("url") or row.get("rss_url") or ""
    domain = domain_from_url(url)
    configured_tier = _configured_domain_tier(domain, trusted)
    source_tier = row.get("trust_tier") or "useful_but_verify"
    source_type = row.get("type") or row.get("source_type") or ""

    if source_tier == "blocked" and row.get("is_active"):
        issues.append(
            _issue(
                row,
                "fail",
                "active_blocked_source",
                "Source is active while marked blocked.",
                "Disable the source or lower it out of the recurring registry.",
            )
        )

    if domain and configured_tier is None:
        issues.append(
            _issue(
                row,
                "warn",
                "domain_not_whitelisted",
                f"Domain is not listed in trusted_domains.yaml: {domain}",
                "Review the source and add the domain only after human approval.",
            )
        )

    if configured_tier and TIER_RANK.get(source_tier, 0) > TIER_RANK.get(configured_tier, 0):
        issues.append(
            _issue(
                row,
                "warn",
                "trust_tier_above_domain_policy",
                f"Source tier {source_tier} is above configured domain tier {configured_tier}.",
                "Lower the source trust tier or update trusted_domains.yaml after review.",
            )
        )

    if domain in {"linkedin.com", "x.com", "twitter.com"} and source_type != "manual":
        issues.append(
            _issue(
                row,
                "fail",
                "social_source_registered_for_collection",
                "Social domains must not be scraped or collected automatically.",
                "Keep social links manual-only and use them as discovery signals.",
            )
        )

    if source_type == "public_web" and not row.get("rss_url"):
        issues.append(
            _issue(
                row,
                "info",
                "public_web_registered_for_later_extraction",
                "Public web source is registered but not automatically fetched in v0.",
                "Keep as a governed source until a compliant extractor is explicitly added.",
            )
        )

    return issues


def _persist_issues(config: Config, issues: List[SourceAuditIssue]) -> None:
    with transaction(config.storage.sqlite_path) as conn:
        conn.execute("DELETE FROM source_audit_findings")
        for issue in issues:
            conn.execute(
                """
                INSERT INTO source_audit_findings (
                    id, source_id, severity, issue_type, detail, recommendation, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stable_id("source_audit", issue.source_id, issue.issue_type, issue.detail),
                    issue.source_id,
                    issue.severity,
                    issue.issue_type,
                    issue.detail,
                    issue.recommendation,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )


def _render_markdown(report: SourceAuditReport) -> str:
    lines = [
        "# Source Governance Audit",
        "",
        f"Generated: {report.generated_at}",
        f"Failures: {report.fail_count}",
        f"Warnings: {report.warn_count}",
        f"Info: {report.info_count}",
        "",
    ]
    if not report.issues:
        lines.append("No source governance issues detected.")
    for issue in report.issues:
        lines.extend(
            [
                f"## {issue.source_name} ({issue.source_id})",
                "",
                f"- Severity: {issue.severity}",
                f"- Issue: {issue.issue_type}",
                f"- Detail: {issue.detail}",
                f"- Recommendation: {issue.recommendation}",
                "",
            ]
        )
    return "\n".join(lines)


def audit_sources(config: Config, week: str = "current") -> SourceAuditReport:
    trusted = _trusted_domain_tiers()
    issues: List[SourceAuditIssue] = []
    for row in _source_rows(config):
        issues.extend(_audit_row(row, trusted))

    _persist_issues(config, issues)

    generated_at = datetime.now().isoformat(timespec="seconds")
    output_dir = intelligence_dir(config, week)
    markdown_path = output_dir / "source_governance_audit.md"
    json_path = output_dir / "source_governance_audit.json"
    report = SourceAuditReport(
        generated_at=generated_at,
        issues=issues,
        markdown_path=str(markdown_path),
        json_path=str(json_path),
    )
    markdown_path.write_text(_render_markdown(report))
    json_path.write_text(json.dumps(asdict(report), indent=2))
    return report
