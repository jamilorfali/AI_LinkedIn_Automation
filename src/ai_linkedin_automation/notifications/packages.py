import html
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from ai_linkedin_automation.config import Config, resolve_project_path
from ai_linkedin_automation.review import create_approval_packet, export_review_queue_csv
from ai_linkedin_automation.storage.db import connect_db


REMINDER_KINDS = {"friday", "monday"}


@dataclass
class NotificationPackage:
    draft_id: str
    review_id: str
    subject: str
    text_path: str
    html_path: str
    metadata_path: str
    approval_packet_path: str
    review_queue_path: str
    approval_url_configured: bool
    email_sent: bool = False


def _week_slug(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _target_week(week: str) -> str:
    if week == "current":
        return _week_slug(datetime.now())
    return week


def _output_dir(config: Config, week: str, draft_id: str) -> Path:
    output_dir = (
        resolve_project_path(config.storage.exports_dir)
        / "notifications"
        / _target_week(week)
        / draft_id
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _draft_has_decision(config: Config, draft_id: str) -> bool:
    conn = connect_db(config.storage.sqlite_path)
    try:
        row = conn.execute(
            """
            SELECT approvals.id
            FROM approvals
            JOIN approval_tokens ON approval_tokens.id = approvals.token_id
            WHERE approval_tokens.draft_id = ?
            LIMIT 1
            """,
            (draft_id,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _why_this_one(packet: dict) -> str:
    recommendation = (packet.get("recommendation") or "ready for review").replace("_", " ")
    risk = packet.get("political_risk") or "unknown"
    editorial_status = (packet.get("editorial_status") or "not reviewed").replace("_", " ")
    return (
        f"Recommendation: {recommendation}. "
        f"Editorial status: {editorial_status}. "
        f"Political risk: {risk}."
    )


def _review_target(packet: dict, raw_token: str) -> tuple[str, bool]:
    approval_url = packet.get("approval_url")
    if approval_url:
        return approval_url, True
    return f"Approval URL not configured. Local one-time approval token: {raw_token}", False


def _text_email(
    *,
    subject: str,
    greeting_line: str,
    packet: dict,
    review_target: str,
    approval_packet_path: str,
    review_queue_path: str,
    draft_id: str,
    week: str,
) -> str:
    topic = packet.get("topic_title") or draft_id
    return f"""Subject: {subject}

Hi,

{greeting_line}

Recommended topic:
{topic}

Why this one:
{_why_this_one(packet)}

Review and approve here:
{review_target}

Local approval packet:
{approval_packet_path}

Review queue CSV used by the phone approval sync:
{review_queue_path}

No action means no post.

No automatic LinkedIn publishing will happen from this notification. In the AI LinkedIn Console, use Approve -> Sync to Phone Approval, approve on any device, then press Import Phone Decision. The console will build the posting package after an approving decision.

Thanks.
"""


def _html_email(
    *,
    subject: str,
    greeting_line: str,
    packet: dict,
    review_target: str,
    approval_packet_path: str,
    review_queue_path: str,
    draft_id: str,
    week: str,
) -> str:
    topic = html.escape(packet.get("topic_title") or draft_id)
    why = html.escape(_why_this_one(packet))
    escaped_subject = html.escape(subject)
    escaped_greeting = html.escape(greeting_line)
    escaped_target = html.escape(review_target)
    escaped_packet_path = html.escape(approval_packet_path)
    escaped_queue_path = html.escape(review_queue_path)
    _ = week
    _ = draft_id

    if packet.get("approval_url"):
        review_html = f'<a href="{escaped_target}">{escaped_target}</a>'
    else:
        review_html = f"<code>{escaped_target}</code>"

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{escaped_subject}</title>
</head>
<body>
  <p><strong>Subject:</strong> {escaped_subject}</p>
  <p>Hi,</p>
  <p>{escaped_greeting}</p>
  <p><strong>Recommended topic:</strong><br>{topic}</p>
  <p><strong>Why this one:</strong><br>{why}</p>
  <p><strong>Review and approve here:</strong><br>{review_html}</p>
  <p><strong>Local approval packet:</strong><br><code>{escaped_packet_path}</code></p>
  <p><strong>Review queue CSV used by the phone approval sync:</strong><br><code>{escaped_queue_path}</code></p>
  <p><strong>No action means no post.</strong></p>
  <p>No automatic LinkedIn publishing will happen from this notification.</p>
  <p>In the AI LinkedIn Console, use Approve -> Sync to Phone Approval, approve on any device, then press Import Phone Decision. The console will build the posting package after an approving decision.</p>
  <p>Thanks.</p>
</body>
</html>
"""


def _write_package(
    *,
    config: Config,
    draft_id: str,
    week: str,
    package_type: str,
    subject: str,
    greeting_line: str,
    reminder_kind: Optional[str] = None,
) -> NotificationPackage:
    if _draft_has_decision(config, draft_id):
        raise RuntimeError(
            "Draft already has an approval decision. Create a new draft version before notifying again."
        )

    approval_packet_path, raw_token = create_approval_packet(config, draft_id, week=week)
    review_queue_path = export_review_queue_csv(config, week=week)
    packet = json.loads(Path(approval_packet_path).read_text())
    review_target, approval_url_configured = _review_target(packet, raw_token)
    review_id = packet["review_id"]
    target_week = _target_week(week)
    output_dir = _output_dir(config, week, draft_id)

    base_name = f"{review_id}_{package_type}"
    text_path = output_dir / f"{base_name}.txt"
    html_path = output_dir / f"{base_name}.html"
    metadata_path = output_dir / f"{base_name}.json"

    text_path.write_text(
        _text_email(
            subject=subject,
            greeting_line=greeting_line,
            packet=packet,
            review_target=review_target,
            approval_packet_path=approval_packet_path,
            review_queue_path=review_queue_path,
            draft_id=draft_id,
            week=target_week,
        )
    )
    html_path.write_text(
        _html_email(
            subject=subject,
            greeting_line=greeting_line,
            packet=packet,
            review_target=review_target,
            approval_packet_path=approval_packet_path,
            review_queue_path=review_queue_path,
            draft_id=draft_id,
            week=target_week,
        )
    )
    metadata = {
        "package_type": package_type,
        "reminder_kind": reminder_kind,
        "draft_id": draft_id,
        "review_id": review_id,
        "draft_version": packet.get("draft_version"),
        "content_hash": packet.get("content_hash"),
        "token_hash": packet.get("token_hash"),
        "approval_packet_path": approval_packet_path,
        "review_queue_path": review_queue_path,
        "approval_url_configured": approval_url_configured,
        "email_sent": False,
        "outlook_graph_email_enabled": False,
        "google_sheets_api_writeback_enabled": False,
        "linkedin_api_publish_enabled": config.publishing.linkedin_api_enabled,
        "note": "Local file package only. Copy into Outlook manually; no email was sent.",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2))

    return NotificationPackage(
        draft_id=draft_id,
        review_id=review_id,
        subject=subject,
        text_path=str(text_path),
        html_path=str(html_path),
        metadata_path=str(metadata_path),
        approval_packet_path=approval_packet_path,
        review_queue_path=review_queue_path,
        approval_url_configured=approval_url_configured,
    )


def build_notification_package(
    config: Config,
    draft_id: str,
    week: str = "current",
) -> NotificationPackage:
    """Create a local Outlook-copyable Friday review notification package."""
    return _write_package(
        config=config,
        draft_id=draft_id,
        week=week,
        package_type="notification",
        subject="Friday AI LinkedIn brief ready for review",
        greeting_line="Your weekly AI thought leadership package is ready.",
    )


def build_reminder_package(
    config: Config,
    draft_id: str,
    kind: str,
    week: str = "current",
) -> NotificationPackage:
    """Create a local reminder email package without sending anything."""
    if kind not in REMINDER_KINDS:
        raise ValueError(f"Invalid reminder kind: {kind}. Expected one of: friday, monday")

    if kind == "friday":
        subject = "Reminder: AI LinkedIn brief waiting for review"
        greeting_line = "This is the one Friday reminder for the pending AI LinkedIn draft."
        package_type = "friday_reminder"
    else:
        subject = "Monday follow-up: AI LinkedIn draft needs a decision"
        greeting_line = (
            "This is the Monday follow-up for last week's pending AI LinkedIn draft."
        )
        package_type = "monday_follow_up"

    return _write_package(
        config=config,
        draft_id=draft_id,
        week=week,
        package_type=package_type,
        subject=subject,
        greeting_line=greeting_line,
        reminder_kind=kind,
    )
