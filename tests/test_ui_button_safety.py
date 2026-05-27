import re
from pathlib import Path


def _ui_html() -> str:
    return Path("ui/index.html").read_text()


def test_all_bound_click_ids_exist_in_ui():
    html = _ui_html()
    ids = set(re.findall(r'id="([^"]+)"', html))
    bound_ids = re.findall(r"bindClick\('([^']+)'", html)

    assert bound_ids
    assert [button_id for button_id in bound_ids if button_id not in ids] == []


def test_approval_uses_current_draft_not_posting_override_field():
    html = _ui_html()
    start = html.index("async function approveLocally()")
    end = html.index("function requirePostingReady()", start)
    approve_function = html[start:end]

    assert "home?.draft_workspace?.draft_id" in approve_function
    assert "manualDraftId" not in approve_function


def test_posting_copy_and_linkedin_controls_require_approval():
    html = _ui_html()

    assert "function requirePostingReady()" in html
    assert "Approve the draft before copying final post text or opening LinkedIn." in html
    assert "bindClick('copyDraftBtn', copyApprovedPostText)" in html
    assert "bindClick('copyOpenLinkedInBtn', copyApprovedPostTextAndOpenLinkedIn)" in html
    assert "bindClick('openLinkedInBtn', openLinkedInAfterApproval)" in html
