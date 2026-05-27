import json
from pathlib import Path

from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.ingestion.sources import load_sources_from_config
from ai_linkedin_automation.integrations.status import collect_integration_status
from ai_linkedin_automation.locus_workflows import (
    build_locus_workbench_package,
    collect_locus_status,
    locus_sdk_installed,
    render_locus_status,
    run_locus_capability_check,
)
from ai_linkedin_automation.operations.workflows import run_daily_scan
from ai_linkedin_automation.pilot.live_pilot import run_production_pilot
from ai_linkedin_automation.storage.db import init_db


def _config(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    config = load_config()
    config.storage.sqlite_path = db_path
    config.storage.review_packets_dir = str(tmp_path / "review_packets")
    config.storage.exports_dir = str(tmp_path / "exports")
    config.storage.logs_dir = str(tmp_path / "logs")
    init_db(config.storage.sqlite_path)
    return config


def test_locus_status_reports_install_commands_without_requiring_sdk(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    status = collect_locus_status(config)
    text = render_locus_status(status)

    assert status.engine in {
        "locus_compatible_local_adapter",
        "locus_sdk_available_local_adapter",
        "locus_sdk_stategraph_local_tools",
    }
    assert status.hard_zero_safe is True
    assert status.provider_mode == "deterministic_local_tools"
    assert any("locus-sdk" in command for command in status.install_commands)
    assert "daily_scan" in status.enabled_workflows
    assert "Locus Workflow Engine Status" in text
    assert "SDK capabilities" in text
    if locus_sdk_installed():
        assert status.engine == "locus_sdk_stategraph_local_tools"
        assert status.sdk_capabilities["StateGraph"] is True
        assert "StateGraph" in status.active_primitives


def test_daily_scan_writes_locus_trace_and_orchestration_metadata(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    calls = []

    import ai_linkedin_automation.ingestion.ingest as ingest_module
    import ai_linkedin_automation.ingestion.sources as sources_module
    import ai_linkedin_automation.scoring.scoring as scoring_module

    def fake_load_sources(config):
        calls.append("load-sources")

    def fake_run_ingestion(config, dry_run=False):
        calls.append(f"ingest:{dry_run}")
        print("Saved 4 new findings")

    def fake_score_all_findings(config):
        calls.append("score")
        return 4

    monkeypatch.setattr(sources_module, "load_sources_from_config", fake_load_sources)
    monkeypatch.setattr(ingest_module, "run_ingestion", fake_run_ingestion)
    monkeypatch.setattr(scoring_module, "score_all_findings", fake_score_all_findings)

    report = run_daily_scan(config)

    assert calls == ["load-sources", "ingest:False", "score"]
    assert "locus_trace" in report.output_paths
    assert Path(report.output_paths["locus_trace"]).exists()
    assert report.orchestration["workflow"] == "daily_scan"
    assert report.orchestration["agent_count"] >= 3
    if locus_sdk_installed():
        assert report.orchestration["sdk_graph_used"] is True
        assert report.orchestration["sdk_graph_success"] is True
        assert report.orchestration["sdk_observability_event_count"] >= 4
        assert report.orchestration["sdk_execution_order"] == [
            "init_db",
            "load_sources",
            "ingest",
            "score",
        ]
    trace = json.loads(Path(report.orchestration["trace_json"]).read_text())
    assert trace["provider_mode"] == "deterministic_local_tools"
    assert any(event["agent"] == "ingestion" for event in trace["events"])
    if locus_sdk_installed():
        assert trace["sdk_runs"][0]["used_sdk"] is True
        assert trace["sdk_runs"][0]["success"] is True


def test_production_pilot_embeds_locus_trace(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    load_sources_from_config(config)

    report = run_production_pilot(config, week="2026-W20", dry_run=True)

    assert report.status in {"passed", "passed_with_warnings"}
    assert "locus_trace" in report.output_paths
    assert Path(report.output_paths["locus_trace"]).exists()
    assert report.orchestration["workflow"] == "production_pilot"
    if locus_sdk_installed():
        assert report.orchestration["sdk_graph_used"] is True
        assert report.orchestration["sdk_graph_success"] is True
        assert report.orchestration["sdk_observability_event_count"] >= 8
        assert report.orchestration["sdk_execution_order"] == [
            "load_sources",
            "preflight",
            "approval_url_gate",
            "daily_scan",
            "friday_package",
            "source_audit",
            "readiness",
            "checklist",
        ]
    manifest = json.loads(Path(report.json_path).read_text())
    assert manifest["orchestration"]["workflow"] == "production_pilot"
    assert manifest["orchestration"]["human_gates"]


def test_integration_status_includes_oracle_locus_workflow_engine(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    report = collect_integration_status(config)

    by_name = {item.name: item for item in report.items}
    assert "Oracle Locus workflow engine" in by_name
    assert by_name["Oracle Locus workflow engine"].paid_capable is False
    assert by_name["Oracle Locus workflow engine"].cost_allowed is True


def test_locus_capability_check_exercises_sdk_when_installed(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    report = run_locus_capability_check(config)

    assert Path(report.markdown_path).exists()
    assert Path(report.json_path).exists()
    check_names = {check.name for check in report.checks}
    assert "SDK primitives" in check_names or "SDK import" in check_names
    if locus_sdk_installed():
        assert report.status == "passed"
        assert {
            "StateGraph execution",
            "GroundingEvaluator",
            "Reflector",
            "Composition pipelines",
            "Send primitive",
            "Evaluation framework",
            "Workbench package",
        }.issubset(check_names)
    else:
        assert report.status == "failed"


def test_locus_workbench_package_exports_manifest_and_diagrams(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    package = build_locus_workbench_package(config)

    assert package.status == "ready"
    assert Path(package.manifest_path).exists()
    assert Path(package.readme_path).exists()
    assert {"daily_scan", "friday_package", "production_pilot", "production_test_package"}.issubset(
        package.diagrams
    )
    for path in package.diagrams.values():
        assert Path(path).read_text().startswith("graph LR")
    manifest = json.loads(Path(package.manifest_path).read_text())
    assert manifest["provider_mode"] == "deterministic_local_tools"
    assert manifest["safety_policy"]["linkedin_publishing"] == "manual copy/paste only"


def test_ui_html_contains_locus_workflow_controls():
    html = Path("ui/index.html").read_text()

    assert "AI Workflow Engine" in html
    assert "View Locus Status" in html
    assert "Test Locus" in html
    assert "Export Locus Map" in html
    assert "/api/locus-status" in html
    assert "/api/locus-capability-check" in html
    assert "/api/locus-workbench-package" in html
