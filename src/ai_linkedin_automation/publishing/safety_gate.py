from dataclasses import dataclass
from typing import Optional

from ai_linkedin_automation.config import Config
from ai_linkedin_automation.cost_guard import check_cost_allowed
from ai_linkedin_automation.storage.db import connect_db


TEXT_APPROVAL_ACTIONS = {
    "approve",
    "approve_text_only",
    "approve_text_plus_media",
    "approve_text_reject_media",
}

MEDIA_APPROVAL_ACTIONS = {
    "approve_text_plus_media",
}


@dataclass
class PublishingGateDecision:
    allowed: bool
    reason: str
    draft_id: str
    approval_action: Optional[str] = None


def _latest_approval(conn, draft_id: str):
    cursor = conn.execute(
        """
        SELECT
            approvals.action,
            approvals.draft_version,
            approvals.content_hash,
            approvals.approved_at,
            drafts.version AS current_version,
            drafts.content_hash AS current_content_hash
        FROM approvals
        JOIN approval_tokens ON approval_tokens.id = approvals.token_id
        JOIN drafts ON drafts.id = approval_tokens.draft_id
        WHERE approval_tokens.draft_id = ?
        ORDER BY approvals.approved_at DESC
        LIMIT 1
        """,
        (draft_id,),
    )
    return cursor.fetchone()


def evaluate_manual_posting_gate(config: Config, draft_id: str) -> PublishingGateDecision:
    """Check whether a draft may be packaged for assisted manual posting."""
    with connect_db(config.storage.sqlite_path) as conn:
        draft = conn.execute(
            "SELECT id, content_hash, version, status FROM drafts WHERE id = ?",
            (draft_id,),
        ).fetchone()
        if not draft:
            return PublishingGateDecision(False, "Draft not found.", draft_id)

        if config.publishing.require_approval_record:
            approval = _latest_approval(conn, draft_id)
            if not approval:
                return PublishingGateDecision(False, "No approval record exists for this draft.", draft_id)
            if approval["action"] not in TEXT_APPROVAL_ACTIONS:
                return PublishingGateDecision(
                    False,
                    f"Latest approval action does not authorize posting: {approval['action']}.",
                    draft_id,
                    approval["action"],
                )
            if config.publishing.require_content_hash_match:
                approved_hash = approval["content_hash"] or approval["current_content_hash"]
                approved_version = approval["draft_version"] or approval["current_version"]
                if approved_hash != draft["content_hash"]:
                    return PublishingGateDecision(
                        False,
                        "Draft content hash does not match the approval record.",
                        draft_id,
                        approval["action"],
                    )
                if approved_version != draft["version"]:
                    return PublishingGateDecision(
                        False,
                        "Draft version does not match the approval record.",
                        draft_id,
                        approval["action"],
                    )

        media_count = conn.execute(
            "SELECT COUNT(*) FROM media_assets WHERE draft_id = ?",
            (draft_id,),
        ).fetchone()[0]
        if media_count and not config.publishing.media_publishing_enabled:
            return PublishingGateDecision(
                False,
                "Media exists, but media publishing is disabled and requires separate approval.",
                draft_id,
            )

        return PublishingGateDecision(True, "Draft is approved for manual posting package.", draft_id)


def evaluate_live_publish_gate(config: Config, draft_id: str) -> PublishingGateDecision:
    """Check whether live LinkedIn API posting may run. v0 blocks by default."""
    manual_decision = evaluate_manual_posting_gate(config, draft_id)
    if not manual_decision.allowed:
        return manual_decision

    if not config.publishing.linkedin_api_enabled:
        return PublishingGateDecision(
            False,
            "LinkedIn API publishing is disabled in configuration.",
            draft_id,
            manual_decision.approval_action,
        )

    cost_decision = check_cost_allowed("linkedin_api", "publish", 0.0)
    if not cost_decision.allowed:
        return PublishingGateDecision(False, f"Cost Guard blocked publishing: {cost_decision.reason}", draft_id)

    return PublishingGateDecision(True, "Live publishing is enabled and approved.", draft_id)
