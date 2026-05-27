import csv
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ai_linkedin_automation.approval import (
    ACTION_TO_DRAFT_STATUS,
    ALLOWED_APPROVAL_ACTIONS,
    generate_approval_token,
    hash_token,
    store_approval_token,
)
from ai_linkedin_automation.config import Config, resolve_project_path
from ai_linkedin_automation.storage.db import connect_db, init_db, transaction


REVIEW_QUEUE_HEADERS = [
    "review_id",
    "draft_id",
    "draft_version",
    "content_hash",
    "topic_title",
    "recommendation",
    "political_risk",
    "draft_readiness",
    "draft_text",
    "source_notes",
    "media_notes",
    "token_hash",
    "expires_at",
    "token_used_at",
    "approval_status",
    "approval_action",
    "approval_notes",
    "approved_at",
    "created_at",
]


@dataclass
class ReviewImportResult:
    imported: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _week_slug(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _target_week(week: str) -> str:
    if week == "current":
        return _week_slug(datetime.now())
    return week


def _packet_dir(config: Config, week: str) -> Path:
    output_dir = resolve_project_path(config.storage.review_packets_dir) / _target_week(week)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _draft_context(config: Config, draft_id: str) -> Dict[str, object]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        row = conn.execute(
            """
            SELECT
                drafts.id AS draft_id,
                drafts.version,
                drafts.content,
                drafts.content_hash,
                drafts.created_at,
                topics.title AS topic_title,
                topics.recommendation,
                topics.political_risk,
                topics.draft_readiness
            FROM drafts
            LEFT JOIN topics ON topics.id = drafts.topic_id
            WHERE drafts.id = ?
            """,
            (draft_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Draft not found: {draft_id}")
        return dict(row)
    finally:
        conn.close()


def _approval_url(review_id: str, raw_token: str) -> Optional[str]:
    base_url = os.environ.get("GOOGLE_APPS_SCRIPT_WEBAPP_URL", "").strip()
    if not base_url:
        return None
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}rid={review_id}&token={raw_token}"


def create_approval_packet(config: Config, draft_id: str, week: str = "current") -> Tuple[str, str]:
    """Create a local JSON review packet and return (packet_path, raw_token)."""
    init_db(config.storage.sqlite_path)
    draft = _draft_context(config, draft_id)
    from ai_linkedin_automation.editorial.review import review_draft
    from ai_linkedin_automation.intelligence.citations import build_citation_matrix

    editorial = review_draft(config, draft_id, week=week)
    citation_matrix = build_citation_matrix(config, draft_id=draft_id, week=week)
    raw_token = generate_approval_token(draft_id)
    token_hash = hash_token(raw_token)
    review_id = store_approval_token(
        config.storage.sqlite_path,
        draft_id,
        token_hash,
        expires_hours=config.review.token_expiration_hours,
    )

    conn = connect_db(config.storage.sqlite_path)
    try:
        token_row = conn.execute(
            """
            SELECT expires_at, created_at
            FROM approval_tokens
            WHERE id = ?
            """,
            (review_id,),
        ).fetchone()
    finally:
        conn.close()

    packet = {
        "review_id": review_id,
        "draft_id": draft_id,
        "draft_version": draft["version"],
        "content_hash": draft["content_hash"],
        "topic_title": draft["topic_title"],
        "recommendation": draft["recommendation"],
        "political_risk": draft["political_risk"],
        "draft_readiness": draft["draft_readiness"],
        "draft_text": draft["content"],
        "source_notes": "See weekly brief private source packet.",
        "media_notes": "No media attached. Media requires separate approval.",
        "token_hash": token_hash,
        "expires_at": token_row["expires_at"],
        "token_used_at": "",
        "approval_status": "pending",
        "approval_action": "",
        "approval_notes": "",
        "approved_at": "",
        "created_at": token_row["created_at"],
        "approval_url": _approval_url(review_id, raw_token),
        "editorial_status": editorial.status,
        "editorial_review_path": editorial.review_path,
        "claim_notes": [
            {
                "claim": claim.text,
                "support_status": claim.support_status,
                "support_level": claim.support_level,
                "notes": claim.notes,
            }
            for claim in editorial.claim_assessments
        ],
        "voice_checklist": [
            {
                "name": check.name,
                "passed": check.passed,
                "notes": check.notes,
            }
            for check in editorial.voice_checks
        ],
        "citation_matrix_path": citation_matrix.markdown_path,
        "citation_matrix_summary": {
            "publishable_support_count": citation_matrix.publishable_support_count,
            "unsupported_count": citation_matrix.unsupported_count,
            "rows": len(citation_matrix.rows),
        },
    }

    output_file = _packet_dir(config, week) / f"review_packet_{draft_id}.json"
    output_file.write_text(json.dumps(packet, indent=2))
    return str(output_file), raw_token


def _review_queue_rows(config: Config) -> List[Dict[str, object]]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        rows = conn.execute(
            """
            SELECT
                approval_tokens.id AS review_id,
                approval_tokens.token_hash,
                approval_tokens.expires_at,
                approval_tokens.used_at AS token_used_at,
                approval_tokens.created_at,
                drafts.id AS draft_id,
                drafts.version AS draft_version,
                drafts.content_hash,
                drafts.content AS draft_text,
                topics.title AS topic_title,
                topics.recommendation,
                topics.political_risk,
                topics.draft_readiness,
                approvals.action AS approval_action,
                approvals.notes AS approval_notes,
                approvals.approved_at
            FROM approval_tokens
            JOIN drafts ON drafts.id = approval_tokens.draft_id
            LEFT JOIN topics ON topics.id = drafts.topic_id
            LEFT JOIN approvals ON approvals.token_id = approval_tokens.id
            ORDER BY approval_tokens.created_at DESC
            """
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["source_notes"] = "See weekly brief private source packet."
            item["media_notes"] = "No media attached. Media requires separate approval."
            item["approval_status"] = "completed" if item.get("approval_action") else "pending"
            result.append(item)
        return result
    finally:
        conn.close()


def export_review_queue_csv(config: Config, week: str = "current") -> str:
    output_file = _packet_dir(config, week) / "review_queue.csv"
    rows = _review_queue_rows(config)
    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_QUEUE_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in REVIEW_QUEUE_HEADERS})
    return str(output_file)


def _parse_int(value: str, field_name: str, row_number: int) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Row {row_number}: invalid {field_name}: {value}") from exc


def _csv_action(row: Dict[str, str]) -> str:
    action = (row.get("approval_action") or "").strip()
    if action:
        return action
    status = (row.get("approval_status") or "").strip()
    if status in ALLOWED_APPROVAL_ACTIONS:
        return status
    return ""


def import_review_queue_csv(config: Config, csv_path: str) -> ReviewImportResult:
    """Import approval state from a Google Sheets-compatible review queue CSV."""
    result = ReviewImportResult()
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Review queue CSV not found: {csv_path}")

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row_number, row in enumerate(reader, start=2):
            review_id = (row.get("review_id") or "").strip()
            action = _csv_action(row)
            if not review_id:
                result.skipped += 1
                result.errors.append(f"Row {row_number}: missing review_id")
                continue
            if not action:
                result.skipped += 1
                continue
            if action not in ALLOWED_APPROVAL_ACTIONS:
                result.skipped += 1
                result.errors.append(f"Row {row_number}: invalid approval action: {action}")
                continue

            try:
                requested_version = _parse_int(
                    (row.get("draft_version") or "").strip(),
                    "draft_version",
                    row_number,
                )
                imported = _import_review_row(config, row, review_id, action, requested_version, row_number)
                if imported:
                    result.imported += 1
                else:
                    result.skipped += 1
            except ValueError as exc:
                result.skipped += 1
                result.errors.append(str(exc))

    return result


def _import_review_row(
    config: Config,
    row: Dict[str, str],
    review_id: str,
    action: str,
    requested_version: Optional[int],
    row_number: int,
) -> bool:
    with transaction(config.storage.sqlite_path) as conn:
        token = conn.execute(
            """
            SELECT id, draft_id, expires_at, used_at
            FROM approval_tokens
            WHERE id = ?
            """,
            (review_id,),
        ).fetchone()
        if not token:
            raise ValueError(f"Row {row_number}: review_id not found in approval_tokens: {review_id}")

        draft = conn.execute(
            """
            SELECT id, version, content_hash
            FROM drafts
            WHERE id = ?
            """,
            (token["draft_id"],),
        ).fetchone()
        if not draft:
            raise ValueError(f"Row {row_number}: draft not found for review_id: {review_id}")

        csv_draft_id = (row.get("draft_id") or "").strip()
        if csv_draft_id and csv_draft_id != draft["id"]:
            raise ValueError(
                f"Row {row_number}: draft_id mismatch for {review_id}: "
                f"CSV has {csv_draft_id}, database has {draft['id']}"
            )

        if requested_version is not None and requested_version != draft["version"]:
            raise ValueError(
                f"Row {row_number}: draft_version mismatch for {draft['id']}: "
                f"CSV has {requested_version}, database has {draft['version']}"
            )

        csv_hash = (row.get("content_hash") or "").strip()
        if csv_hash and csv_hash != draft["content_hash"]:
            raise ValueError(
                f"Row {row_number}: content_hash mismatch for {draft['id']}: "
                "CSV does not match database"
            )

        existing = conn.execute(
            """
            SELECT id, action
            FROM approvals
            WHERE token_id = ?
            """,
            (review_id,),
        ).fetchone()
        if existing:
            if existing["action"] != action:
                raise ValueError(
                    f"Row {row_number}: approval for {review_id} already exists "
                    f"with action {existing['action']}"
                )
            return False
        if token["used_at"]:
            raise ValueError(f"Row {row_number}: review_id already used: {review_id}")
        if datetime.now() > datetime.fromisoformat(token["expires_at"]):
            raise ValueError(f"Row {row_number}: review_id expired: {review_id}")

        approved_at = (row.get("approved_at") or "").strip() or datetime.now().isoformat()
        token_used_at = (row.get("token_used_at") or "").strip() or approved_at
        notes = (row.get("approval_notes") or "").strip() or None
        approval_id = f"approval_{secrets.token_urlsafe(12)}"

        conn.execute(
            """
            INSERT INTO approvals (
                id, token_id, draft_id, draft_version, content_hash,
                action, approval_action, approval_channel, notes, approved_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                review_id,
                draft["id"],
                draft["version"],
                draft["content_hash"],
                action,
                action,
                "google_sheets_csv",
                notes,
                approved_at,
            ),
        )
        conn.execute(
            """
            UPDATE approval_tokens
            SET used_at = ?
            WHERE id = ?
            """,
            (token_used_at, review_id),
        )
        conn.execute(
            """
            UPDATE drafts
            SET status = ?
            WHERE id = ?
            """,
            (ACTION_TO_DRAFT_STATUS[action], draft["id"]),
        )
        return True
