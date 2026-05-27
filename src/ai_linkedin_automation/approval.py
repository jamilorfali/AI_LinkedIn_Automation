import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from ai_linkedin_automation.storage.db import connect_db, transaction


ALLOWED_APPROVAL_ACTIONS = {
    "approve",
    "reject",
    "approve_text_only",
    "approve_text_plus_media",
    "approve_text_reject_media",
    "needs_edits",
    "pick_different_topic",
    "save_for_later",
}

ACTION_TO_DRAFT_STATUS = {
    "approve": "approved_text_only",
    "approve_text_only": "approved_text_only",
    "approve_text_plus_media": "approved_text_plus_media",
    "approve_text_reject_media": "approved_text_reject_media",
    "needs_edits": "needs_edits",
    "pick_different_topic": "pick_different_topic",
    "save_for_later": "saved",
    "reject": "rejected",
}


class ApprovalError(Exception):
    """Raised for approval workflow errors."""


def generate_approval_token(draft_id: str) -> str:
    """Generate a secure random token for draft approval."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash the token using SHA-256 for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def store_approval_token(db_path: str, draft_id: str, token_hash: str, expires_hours: int = 120) -> str:
    """Store approval token in database and return the token ID."""
    expires_at = datetime.now() + timedelta(hours=expires_hours)
    token_id = f"review_{secrets.token_urlsafe(12)}"

    try:
        with transaction(db_path) as conn:
            conn.execute(
                """
                INSERT INTO approval_tokens (id, draft_id, token_hash, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token_id, draft_id, token_hash, expires_at.isoformat(), datetime.now().isoformat()),
            )
        return token_id
    except Exception as exc:
        raise ApprovalError(f"Failed to store approval token: {exc}")


def validate_approval_token(db_path: str, token: str) -> Tuple[bool, Optional[str]]:
    """Validate an approval token and return (is_valid, draft_id)."""
    token_hash = hash_token(token)

    conn = connect_db(db_path)
    try:
        row = conn.execute(
            """
            SELECT draft_id, expires_at, used_at
            FROM approval_tokens
            WHERE token_hash = ?
            """,
            (token_hash,),
        ).fetchone()

        if not row:
            return False, None
        if row["used_at"]:
            return False, None
        if datetime.now() > datetime.fromisoformat(row["expires_at"]):
            return False, None
        return True, row["draft_id"]
    except Exception as exc:
        raise ApprovalError(f"Failed to validate token: {exc}")
    finally:
        conn.close()


def mark_token_used(db_path: str, token: str) -> None:
    """Mark an approval token as used."""
    token_hash = hash_token(token)

    try:
        with transaction(db_path) as conn:
            conn.execute(
                """
                UPDATE approval_tokens
                SET used_at = ?
                WHERE token_hash = ?
                """,
                (datetime.now().isoformat(), token_hash),
            )
    except Exception as exc:
        raise ApprovalError(f"Failed to mark token as used: {exc}")


def get_token_id_from_token(db_path: str, token: str) -> Optional[str]:
    """Get token_id from the token for recording approval."""
    token_hash = hash_token(token)

    conn = connect_db(db_path)
    try:
        row = conn.execute(
            """
            SELECT id
            FROM approval_tokens
            WHERE token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        return row["id"] if row else None
    except Exception as exc:
        raise ApprovalError(f"Failed to get token ID: {exc}")
    finally:
        conn.close()


def record_approval(db_path: str, token_id: str, action: str, notes: Optional[str] = None) -> str:
    """Record approval or rejection details for the exact draft version and content hash."""
    if action not in ALLOWED_APPROVAL_ACTIONS:
        raise ApprovalError(f"Invalid approval action: {action}")

    approval_id = f"approval_{secrets.token_urlsafe(12)}"
    try:
        with transaction(db_path) as conn:
            draft = conn.execute(
                """
                SELECT drafts.id, drafts.version, drafts.content_hash
                FROM approval_tokens
                JOIN drafts ON drafts.id = approval_tokens.draft_id
                WHERE approval_tokens.id = ?
                """,
                (token_id,),
            ).fetchone()
            if not draft:
                raise ApprovalError("Token is not attached to a draft")

            approved_at = datetime.now().isoformat()
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
                    token_id,
                    draft["id"],
                    draft["version"],
                    draft["content_hash"],
                    action,
                    action,
                    "local_cli",
                    notes,
                    approved_at,
                ),
            )
            conn.execute(
                """
                UPDATE drafts
                SET status = ?
                WHERE id = ?
                """,
                (ACTION_TO_DRAFT_STATUS[action], draft["id"]),
            )
            return approval_id
    except ApprovalError:
        raise
    except Exception as exc:
        raise ApprovalError(f"Failed to record approval: {exc}")


def approve_with_token(
    db_path: str,
    token: str,
    action: str,
    notes: Optional[str] = None,
) -> Tuple[str, str]:
    """Validate, record, and consume an approval token in one workflow call."""
    if action not in ALLOWED_APPROVAL_ACTIONS:
        raise ApprovalError(f"Invalid approval action: {action}")

    token_hash = hash_token(token)
    approval_id = f"approval_{secrets.token_urlsafe(12)}"
    approved_at = datetime.now().isoformat()
    try:
        with transaction(db_path) as conn:
            row = conn.execute(
                """
                SELECT
                    approval_tokens.id AS token_id,
                    approval_tokens.draft_id,
                    approval_tokens.expires_at,
                    approval_tokens.used_at,
                    drafts.version,
                    drafts.content_hash
                FROM approval_tokens
                JOIN drafts ON drafts.id = approval_tokens.draft_id
                WHERE approval_tokens.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if not row or row["used_at"] or datetime.now() > datetime.fromisoformat(row["expires_at"]):
                raise ApprovalError("Invalid, expired, or already used token")

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
                    row["token_id"],
                    row["draft_id"],
                    row["version"],
                    row["content_hash"],
                    action,
                    action,
                    "local_cli",
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
                (approved_at, row["token_id"]),
            )
            conn.execute(
                """
                UPDATE drafts
                SET status = ?
                WHERE id = ?
                """,
                (ACTION_TO_DRAFT_STATUS[action], row["draft_id"]),
            )
            return row["draft_id"], approval_id
    except ApprovalError:
        raise
    except Exception as exc:
        raise ApprovalError(f"Failed to approve with token: {exc}")
