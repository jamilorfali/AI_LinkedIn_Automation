import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ai_linkedin_automation.approval import ALLOWED_APPROVAL_ACTIONS
from ai_linkedin_automation.config import Config, resolve_project_path
from ai_linkedin_automation.review import REVIEW_QUEUE_HEADERS
from ai_linkedin_automation.storage.db import connect_db


@dataclass
class ReviewQueueValidationIssue:
    severity: str
    row_number: int
    field: str
    detail: str
    recommendation: str


@dataclass
class ReviewQueueValidationReport:
    ok: bool
    generated_at: str
    csv_path: str
    header_status: str
    total_rows: int = 0
    decision_rows: int = 0
    pending_rows: int = 0
    issues: List[ReviewQueueValidationIssue] = field(default_factory=list)
    markdown_path: str = ""
    json_path: str = ""

    @property
    def fail_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "fail")

    @property
    def warn_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warn")


def _action_from_row(row: Dict[str, str]) -> str:
    action = (row.get("approval_action") or "").strip()
    if action:
        return action
    status = (row.get("approval_status") or "").strip()
    if status in ALLOWED_APPROVAL_ACTIONS:
        return status
    return ""


def _issue(
    severity: str,
    row_number: int,
    field: str,
    detail: str,
    recommendation: str,
) -> ReviewQueueValidationIssue:
    return ReviewQueueValidationIssue(
        severity=severity,
        row_number=row_number,
        field=field,
        detail=detail,
        recommendation=recommendation,
    )


def _token_context(config: Config, review_id: str) -> Optional[Dict[str, object]]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        row = conn.execute(
            """
            SELECT
                approval_tokens.id AS review_id,
                approval_tokens.draft_id,
                approval_tokens.used_at,
                drafts.version AS draft_version,
                drafts.content_hash,
                approvals.action AS existing_action
            FROM approval_tokens
            JOIN drafts ON drafts.id = approval_tokens.draft_id
            LEFT JOIN approvals ON approvals.token_id = approval_tokens.id
            WHERE approval_tokens.id = ?
            """,
            (review_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _header_issues(fieldnames: Optional[List[str]]) -> List[ReviewQueueValidationIssue]:
    if fieldnames == REVIEW_QUEUE_HEADERS:
        return []
    actual = fieldnames or []
    missing = [header for header in REVIEW_QUEUE_HEADERS if header not in actual]
    extra = [header for header in actual if header not in REVIEW_QUEUE_HEADERS]
    issues = [
        _issue(
            "fail",
            1,
            "headers",
            "CSV headers must exactly match the review queue contract.",
            "Export from the ReviewQueue tab without editing row 1, or rebuild the Sheet template.",
        )
    ]
    if missing:
        issues.append(
            _issue(
                "fail",
                1,
                "headers",
                f"Missing header(s): {', '.join(missing)}",
                "Restore the required header columns.",
            )
        )
    if extra:
        issues.append(
            _issue(
                "warn",
                1,
                "headers",
                f"Extra header(s): {', '.join(extra)}",
                "Remove extra columns before import to avoid operator confusion.",
            )
        )
    return issues


def _validate_decision_row(
    config: Config,
    row: Dict[str, str],
    row_number: int,
    seen_reviews: set,
) -> List[ReviewQueueValidationIssue]:
    issues: List[ReviewQueueValidationIssue] = []
    review_id = (row.get("review_id") or "").strip()
    action = _action_from_row(row)
    approval_status = (row.get("approval_status") or "").strip()

    if not review_id:
        return [
            _issue(
                "fail",
                row_number,
                "review_id",
                "Decision row is missing review_id.",
                "Re-export the row from the local review queue or approval Sheet.",
            )
        ]
    if review_id in seen_reviews:
        issues.append(
            _issue(
                "fail",
                row_number,
                "review_id",
                f"Duplicate decision row for {review_id}.",
                "Keep exactly one decision row per review_id before import.",
            )
        )
    seen_reviews.add(review_id)

    if approval_status == "completed" and not action:
        issues.append(
            _issue(
                "fail",
                row_number,
                "approval_action",
                "Row is marked completed but has no approval_action.",
                "Choose an explicit action in the approval page or Sheet.",
            )
        )
    if action and action not in ALLOWED_APPROVAL_ACTIONS:
        issues.append(
            _issue(
                "fail",
                row_number,
                "approval_action",
                f"Invalid approval action: {action}",
                "Use one of the approved action values from the Apps Script page.",
            )
        )
        return issues

    context = _token_context(config, review_id)
    if not context:
        issues.append(
            _issue(
                "fail",
                row_number,
                "review_id",
                f"review_id not found in the local database: {review_id}",
                "Confirm this CSV came from the active project database.",
            )
        )
        return issues

    csv_draft_id = (row.get("draft_id") or "").strip()
    if csv_draft_id and csv_draft_id != context["draft_id"]:
        issues.append(
            _issue(
                "fail",
                row_number,
                "draft_id",
                f"CSV draft_id {csv_draft_id} does not match local draft {context['draft_id']}.",
                "Do not import this row; regenerate the review queue from the active database.",
            )
        )

    csv_version = (row.get("draft_version") or "").strip()
    if csv_version:
        try:
            if int(csv_version) != context["draft_version"]:
                issues.append(
                    _issue(
                        "fail",
                        row_number,
                        "draft_version",
                        "CSV draft_version does not match the local draft version.",
                        "Regenerate the approval packet for the latest draft.",
                    )
                )
        except ValueError:
            issues.append(
                _issue(
                    "fail",
                    row_number,
                    "draft_version",
                    f"Invalid draft_version: {csv_version}",
                    "Keep draft_version as an integer.",
                )
            )

    csv_hash = (row.get("content_hash") or "").strip()
    if csv_hash and csv_hash != context["content_hash"]:
        issues.append(
            _issue(
                "fail",
                row_number,
                "content_hash",
                "CSV content_hash does not match the local draft content hash.",
                "Do not import; regenerate the review queue or investigate draft edits.",
            )
        )

    existing_action = context.get("existing_action")
    if existing_action and existing_action != action:
        issues.append(
            _issue(
                "fail",
                row_number,
                "approval_action",
                f"Local approval already exists with action {existing_action}.",
                "Do not overwrite an existing decision; create a new draft version if needed.",
            )
        )
    elif existing_action and existing_action == action:
        issues.append(
            _issue(
                "warn",
                row_number,
                "approval_action",
                "This approval action has already been imported.",
                "Import will skip this row as a duplicate.",
            )
        )

    return issues


def _write_report(config: Config, report: ReviewQueueValidationReport) -> ReviewQueueValidationReport:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = resolve_project_path(config.storage.exports_dir) / "approval_import_validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    report.markdown_path = str(output_dir / f"{timestamp}_validation.md")
    report.json_path = str(output_dir / f"{timestamp}_validation.json")
    Path(report.markdown_path).write_text(render_review_queue_validation(report))
    Path(report.json_path).write_text(json.dumps(asdict(report), indent=2))
    return report


def validate_review_queue_csv(
    config: Config,
    csv_path: str,
    write_files: bool = True,
) -> ReviewQueueValidationReport:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Review queue CSV not found: {csv_path}")

    issues: List[ReviewQueueValidationIssue] = []
    seen_reviews: set = set()
    total_rows = 0
    decision_rows = 0
    pending_rows = 0

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        issues.extend(_header_issues(reader.fieldnames))
        for row_number, row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in row.values()):
                continue
            total_rows += 1
            action = _action_from_row(row)
            approval_status = (row.get("approval_status") or "").strip()
            is_decision = bool(action or approval_status == "completed")
            if is_decision:
                decision_rows += 1
                issues.extend(_validate_decision_row(config, row, row_number, seen_reviews))
            else:
                pending_rows += 1

    if total_rows == 0:
        issues.append(
            _issue(
                "warn",
                1,
                "rows",
                "CSV contains no review rows.",
                "Export the ReviewQueue tab after creating an approval packet.",
            )
        )
    if decision_rows == 0:
        issues.append(
            _issue(
                "warn",
                1,
                "approval_action",
                "CSV contains no importable approval decisions.",
                "This is valid for inspection, but import-review-queue will not change state.",
            )
        )

    report = ReviewQueueValidationReport(
        ok=not any(issue.severity == "fail" for issue in issues),
        generated_at=datetime.now().isoformat(timespec="seconds"),
        csv_path=str(path),
        header_status="pass" if not _header_issues(reader.fieldnames) else "fail",
        total_rows=total_rows,
        decision_rows=decision_rows,
        pending_rows=pending_rows,
        issues=issues,
    )
    if write_files:
        report = _write_report(config, report)
    return report


def render_review_queue_validation(report: ReviewQueueValidationReport) -> str:
    lines = [
        "# Review Queue CSV Validation",
        "",
        f"Generated: {report.generated_at}",
        f"CSV: {report.csv_path}",
        f"Overall: {'PASS' if report.ok else 'FAIL'}",
        f"Header status: {report.header_status}",
        "",
        "## Counts",
        "",
        f"- Total rows: {report.total_rows}",
        f"- Decision rows: {report.decision_rows}",
        f"- Pending rows: {report.pending_rows}",
        f"- Failures: {report.fail_count}",
        f"- Warnings: {report.warn_count}",
        "",
        "## Issues",
        "",
    ]
    if not report.issues:
        lines.append("No validation issues found.")
    for issue in report.issues:
        lines.extend(
            [
                f"- [{issue.severity.upper()}] row {issue.row_number} `{issue.field}`: {issue.detail}",
                f"  Recommendation: {issue.recommendation}",
            ]
        )
    return "\n".join(lines) + "\n"
