import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ai_linkedin_automation.config import Config
from ai_linkedin_automation.editorial.learning import record_final_text_delta
from ai_linkedin_automation.publishing.safety_gate import evaluate_manual_posting_gate
from ai_linkedin_automation.storage.db import transaction


@dataclass
class PostArchiveResult:
    post_id: str
    draft_id: str
    post_url: Optional[str]
    posting_mode: str


def archive_manual_post(
    config: Config,
    draft_id: str,
    post_url: Optional[str] = None,
    final_text: Optional[str] = None,
    engagement_snapshot: Optional[str] = None,
    posted_at: Optional[str] = None,
) -> PostArchiveResult:
    """Archive a manually posted LinkedIn draft after the user posts it."""
    gate = evaluate_manual_posting_gate(config, draft_id)
    if not gate.allowed:
        raise RuntimeError(f"Post archive blocked. Reason: {gate.reason}")

    post_id = f"post_{secrets.token_urlsafe(12)}"
    archived_at = datetime.now().isoformat()
    posted_at_value = posted_at or archived_at

    with transaction(config.storage.sqlite_path) as conn:
        draft = conn.execute(
            "SELECT id, content FROM drafts WHERE id = ?",
            (draft_id,),
        ).fetchone()
        if not draft:
            raise RuntimeError("Draft not found.")

        text = final_text if final_text is not None else draft["content"]
        if final_text is not None:
            record_final_text_delta(draft["content"], final_text)
        conn.execute(
            """
            INSERT INTO posts (
                id, draft_id, platform, post_url, linkedin_post_url, status,
                posted_at, posting_mode, final_text, engagement_snapshot, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id,
                draft_id,
                "linkedin",
                post_url,
                post_url,
                "posted",
                posted_at_value,
                "manual",
                text,
                engagement_snapshot,
                archived_at,
            ),
        )

    return PostArchiveResult(
        post_id=post_id,
        draft_id=draft_id,
        post_url=post_url,
        posting_mode="manual",
    )
