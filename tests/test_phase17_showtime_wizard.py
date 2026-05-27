import re
from pathlib import Path

import pytest

from ai_linkedin_automation.online_search import OnlineSearchReport, OnlineSearchResult
from ai_linkedin_automation.business_console import (
    apply_draft_preset,
    build_safe_post_image,
    build_topic_package,
    business_home,
    full_refresh_topics,
    topic_board,
    undo_full_refresh_topics,
)
from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.pilot.checklist import update_pilot_checklist_item
from ai_linkedin_automation.pilot.production_test import build_production_test_package
from ai_linkedin_automation.storage.db import connect_db, init_db, transaction


def _config(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.delenv("GOOGLE_APPS_SCRIPT_WEBAPP_URL", raising=False)
    config = load_config()
    config.storage.sqlite_path = db_path
    config.storage.review_packets_dir = str(tmp_path / "review_packets")
    config.storage.exports_dir = str(tmp_path / "exports")
    config.storage.logs_dir = str(tmp_path / "logs")
    init_db(config.storage.sqlite_path)
    return config


def _insert_publish_ready_finding(config):
    with transaction(config.storage.sqlite_path) as conn:
        conn.execute(
            """
            INSERT INTO sources (id, name, type, trust_tier, url, is_active, recurring_enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "primary-ai-lab",
                "Primary AI Lab",
                "manual",
                "primary",
                "https://example.com/primary-ai-lab",
                1,
                1,
                "2026-05-18",
                "2026-05-18",
            ),
        )
        conn.execute(
            """
            INSERT INTO findings (
                id, source_id, url, title, summary, published_at, content_hash, raw_content, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "finding-primary-ready",
                "primary-ai-lab",
                "https://example.com/primary-ai-lab/research",
                "AI governance operating model for enterprise leaders",
                "A primary research note gives leaders a practical way to decide where AI belongs, who owns it, and how to check the work.",
                "2026-05-18",
                "finding-primary-ready-hash",
                "raw",
                "new",
                "2026-05-18",
            ),
        )


def test_business_home_exposes_showtime_wizard_state(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)
    package = build_production_test_package(config, week="2026-W21")

    home = business_home(config)

    assert len(home.journey_steps) == 7
    assert home.journey_steps[0]["label"] == "Get the app ready"
    assert home.draft_workspace["ready"] is True
    assert home.draft_workspace["draft_id"] == package.draft_id
    assert home.draft_workspace["article_body"]
    assert home.draft_workspace["article_word_count"] >= 1000
    assert home.draft_workspace["article_reference_count"] >= 10
    assert any(preset["key"] == "shorter" for preset in home.draft_workspace["edit_presets"])
    assert "terminal" not in home.next_action.description.lower()


def test_click_only_draft_revision_creates_new_unapproved_version(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)
    package = build_production_test_package(config, week="2026-W21")

    result = apply_draft_preset(config, "shorter", draft_id=package.draft_id, week="2026-W21")

    assert result.status == "revised"
    assert result.previous_draft_id == package.draft_id
    assert result.draft_id != package.draft_id
    assert Path(result.draft_path).exists()
    with connect_db(config.storage.sqlite_path) as conn:
        old_row = conn.execute("SELECT content FROM drafts WHERE id = ?", (package.draft_id,)).fetchone()
        new_row = conn.execute("SELECT content FROM drafts WHERE id = ?", (result.draft_id,)).fetchone()
    assert old_row["content"] != new_row["content"]

    home = business_home(config)
    assert home.draft_workspace["draft_id"] == result.draft_id
    assert home.draft_workspace["approved"] is False
    assert home.next_action.key in {"review_candidate", "approve_locally"}


def test_click_only_length_and_tone_presets_are_available(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)
    package = build_production_test_package(config, week="2026-W21")

    longer = apply_draft_preset(config, "longer", draft_id=package.draft_id, week="2026-W21")
    concise = apply_draft_preset(config, "more_concise", draft_id=longer.draft_id, week="2026-W21")

    assert longer.status == "revised"
    assert concise.status == "revised"
    home = business_home(config)
    preset_keys = {preset["key"] for preset in home.draft_workspace["edit_presets"]}
    assert {"longer", "deeper_detail", "more_concise", "less_detail", "business_friendly"} <= preset_keys


def test_ui_html_uses_start_to_finish_business_language():
    html = Path("ui/index.html").read_text()

    assert "Create a sourced LinkedIn article." in html
    assert "Search live public AI sources" in html
    assert "Search & Draft" in html
    assert "data-topic-search" in html
    assert "Build My Draft" in html
    assert "Source Looks OK" in html
    assert "Full Article" in html
    assert "articleBodyPreview" in html
    assert "articleQualityStatus" in html
    assert "copyArticleBtn" in html
    assert "copyReferencesBtn" in html
    assert "copyFirstCommentBtn" in html
    assert "copyImagePromptBtn" in html
    assert "Full Refresh Topics" in html
    assert "Undo Refresh" in html
    assert "Edit with buttons" in html
    assert "Approve Draft & Make Package" in html
    assert "/api/business/apply-draft-preset" in html
    assert "/api/business/topic-board" in html
    assert "/api/business/generate-post-image" in html
    assert "/api/business/full-refresh-topics" in html
    assert "/api/business/undo-topic-refresh" in html
    assert "progressSourceReviewBtn" in html
    assert "approvalCopyPreview" in html
    assert "runButtonAction" in html


def test_ui_html_has_unique_element_ids():
    html = Path("ui/index.html").read_text()
    ids = re.findall(r'id="([^"]+)"', html)

    duplicates = sorted({item for item in ids if ids.count(item) > 1})

    assert duplicates == []


def _online_search_report(query: str) -> OnlineSearchReport:
    return OnlineSearchReport(
        query=query,
        generated_at="2026-05-27T12:00:00",
        results=[
            OnlineSearchResult(
                provider="arXiv",
                title="AI governance operating model for enterprise leaders",
                summary="A public research result about AI governance, operations, evidence, and decision quality.",
                url="https://arxiv.org/abs/2605.12345",
                source_name="arXiv",
                trust_tier="primary",
                published_at="2026-05-20",
                result_type="research_paper",
            ),
            OnlineSearchResult(
                provider="Crossref",
                title="Enterprise AI workflow governance",
                summary="A published article about enterprise AI workflow governance and accountable review.",
                url="https://doi.org/10.5555/workflow-governance",
                source_name="Journal of AI Operations",
                trust_tier="high_trust",
                published_at="2026-05-01",
                result_type="journal-article",
            ),
        ],
    )


def test_topic_board_and_online_topic_build_package(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)
    build_production_test_package(config, week="2026-W21")
    monkeypatch.setattr(
        "ai_linkedin_automation.business_console.search_public_ai_sources",
        lambda query, limit=12: _online_search_report(query),
    )

    board = topic_board(config)
    assert board["topic_count"] >= 10
    assert board["categories"]

    package = build_topic_package(
        config,
        week="2026-W21",
        query="AI governance operating model for executives",
    )
    assert package["draft_id"]
    assert package["selected_topic_id"]
    assert package["online_search"]["source_count"] == 2
    with connect_db(config.storage.sqlite_path) as conn:
        rows = conn.execute(
            """
            SELECT findings.url, sources.source_type, sources.trust_tier
            FROM topic_findings
            JOIN findings ON findings.id = topic_findings.finding_id
            JOIN sources ON sources.id = findings.source_id
            WHERE topic_findings.topic_id = ?
            ORDER BY findings.url
            """,
            (package["selected_topic_id"],),
        ).fetchall()
    urls = {row["url"] for row in rows}
    assert "manual://ad-hoc-topic" not in "\n".join(urls)
    assert "https://arxiv.org/abs/2605.12345" in urls
    assert "https://doi.org/10.5555/workflow-governance" in urls
    assert {row["source_type"] for row in rows} == {"online_search"}
    assert {row["trust_tier"] for row in rows} >= {"primary", "high_trust"}


def test_online_topic_build_refuses_to_draft_without_verified_results(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)
    monkeypatch.setattr(
        "ai_linkedin_automation.business_console.search_public_ai_sources",
        lambda query, limit=12: OnlineSearchReport(
            query=query,
            generated_at="2026-05-27T12:00:00",
            results=[],
            provider_errors=["arXiv: offline"],
        ),
    )

    with pytest.raises(ValueError, match="No verified online source records"):
        build_topic_package(
            config,
            week="2026-W21",
            query="AI governance operating model for executives",
        )


def test_full_refresh_topics_replaces_board_and_undo_restores(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)
    package = build_production_test_package(config, week="2026-W21")
    update_pilot_checklist_item(config, "weekly_candidates_reviewed", "done", "source looked OK")

    refreshed = full_refresh_topics(config, week="2026-W21")
    board = topic_board(config)
    home = business_home(config)
    refreshed_sources = {
        topic["source_name"]
        for category in board["categories"]
        for topic in category["topics"]
    }

    assert refreshed["status"] == "refreshed"
    assert refreshed["seeded_topic_count"] >= 10
    assert board["refresh_state"]["available"] is True
    assert "arXiv AI search" not in refreshed_sources
    assert home.draft_workspace["ready"] is False
    assert home.next_action.key == "pick_topic"
    assert next(step for step in home.guided_steps if step["key"] == "weekly_candidates_reviewed")["status"] == "pending"

    undone = undo_full_refresh_topics(config)
    restored = business_home(config)

    assert undone["status"] == "undone"
    assert restored.draft_workspace["draft_id"] == package.draft_id
    assert next(step for step in restored.guided_steps if step["key"] == "weekly_candidates_reviewed")["status"] == "done"


def test_repeated_full_refresh_still_has_selectable_topic_cards(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)
    build_production_test_package(config, week="2026-W21")

    first = full_refresh_topics(config, week="2026-W21")
    second = full_refresh_topics(config, week="2026-W21")
    board = topic_board(config)
    selectable_topics = [
        topic
        for category in board["categories"]
        for topic in category["topics"]
        if topic["id"]
    ]

    assert first["seeded_topic_count"] >= 10
    assert second["seeded_topic_count"] >= 10
    assert len(selectable_topics) >= 10
    assert all(topic["source_name"] != "Starter idea" for topic in selectable_topics[:10])


def test_final_post_text_removes_internal_source_notes(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)
    build_production_test_package(config, week="2026-W21")

    final_text = business_home(config).draft_workspace["final_post_text"]

    assert "Source:" not in final_text
    assert "Source topic:" not in final_text
    assert "trust tier" not in final_text.lower()


def test_safe_post_image_package_is_original_png_with_manifest(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    _insert_publish_ready_finding(config)
    package = build_production_test_package(config, week="2026-W21")

    image = build_safe_post_image(config, draft_id=package.draft_id)

    assert image.status == "created"
    assert image.safety_status == "passed"
    assert image.alt_text.startswith("Original illustration")
    assert "Locus local image-planning agent" in image.prompt
    assert Path(image.image_path).read_bytes().startswith(b"\x89PNG")
    manifest = Path(image.safety_manifest_path).read_text()
    assert "No third-party or copyrighted source image used" in manifest
    assert "scene_plan" in manifest
