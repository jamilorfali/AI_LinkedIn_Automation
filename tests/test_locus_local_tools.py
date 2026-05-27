import json
import sys
from pathlib import Path
from types import ModuleType

from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.locus_local_tools import (
    describe_locus_local_tools,
    locus_local_sdk_tools,
    use_locus_local_tool,
)
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


def test_describe_locus_local_tools_exposes_read_only_default():
    overview = describe_locus_local_tools()

    assert overview["pattern"] == "describe_then_dispatch"
    assert overview["default_mode"] == "read_only"
    assert {service["service"] for service in overview["services"]} == {
        "safety",
        "workflow_engine",
    }

    workflow = describe_locus_local_tools(service="workflow_engine")
    operations = {operation["operation"]: operation for operation in workflow["operations"]}

    assert operations["workflow_manifest"]["read_only"] is True
    assert operations["workbench_package"]["read_only"] is False
    assert operations["workbench_package"]["writes_local_files"] is True


def test_use_locus_local_tool_allows_read_only_manifest(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    result = use_locus_local_tool(config, "workflow_manifest")

    assert result.status == "completed"
    assert result.read_only is True
    assert result.external_side_effects is False
    assert result.paid_capable is False
    assert result.payload["provider_mode"] == "deterministic_local_tools"
    assert {workflow["workflow"] for workflow in result.payload["workflows"]} >= {
        "daily_scan",
        "friday_package",
        "production_pilot",
    }


def test_use_locus_local_tool_blocks_local_writes_by_default(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)

    result = use_locus_local_tool(config, "workbench_package")

    assert result.status == "blocked"
    assert result.blocked_by == "read_only_default"
    assert result.payload["spec"]["writes_local_files"] is True


def test_use_locus_local_tool_requires_hard_zero_for_local_writes(tmp_path, monkeypatch):
    config = _config(tmp_path, monkeypatch)
    config.app.default_run_mode = "future_paid_mode"

    result = use_locus_local_tool(config, "workbench_package", allow_local_writes=True)

    assert result.status == "blocked"
    assert result.blocked_by == "hard_zero_required"
    assert result.payload["run_mode"] == "future_paid_mode"


def test_use_locus_local_tool_can_export_workbench_with_explicit_local_write(
    tmp_path,
    monkeypatch,
):
    config = _config(tmp_path, monkeypatch)

    result = use_locus_local_tool(config, "workbench_package", allow_local_writes=True)

    assert result.status == "completed"
    assert result.read_only is False
    assert result.external_side_effects is False
    assert result.paid_capable is False

    manifest_path = Path(result.payload["manifest_path"])
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["local_describe_use_tools"]["pattern"] == "describe_then_dispatch"
    assert manifest["local_describe_use_tools"]["default_mode"] == "read_only"
    assert manifest["local_describe_use_tools"]["sdk_wrapper_function"] == "locus_local_sdk_tools"
    assert manifest["upstream_locus_repo_alignment"]["repository"].endswith(
        "/oracle-samples/locus"
    )
    assert "locus.tools.oci describe_oci/use_oci dispatch, even if installed" in manifest[
        "upstream_locus_repo_alignment"
    ]["intentionally_not_used"]
    assert manifest["safety_policy"]["oci_tools"] == "not used by this project"


def test_locus_local_sdk_tools_wrap_describe_use_as_idempotent_tools(
    tmp_path,
    monkeypatch,
):
    config = _config(tmp_path, monkeypatch)

    def fake_tool(func=None, *, idempotent=False):
        def decorate(inner):
            inner.idempotent = idempotent
            inner.name = inner.__name__
            return inner

        return decorate(func) if func else decorate

    fake_locus = ModuleType("locus")
    fake_locus.__path__ = []
    fake_tools = ModuleType("locus.tools")
    fake_tools.tool = fake_tool
    fake_locus.tools = fake_tools
    monkeypatch.setitem(sys.modules, "locus", fake_locus)
    monkeypatch.setitem(sys.modules, "locus.tools", fake_tools)

    tools = locus_local_sdk_tools(config)

    assert [tool.name for tool in tools] == [
        "describe_ai_linkedin_tools",
        "use_ai_linkedin_tool",
    ]
    assert all(tool.idempotent for tool in tools)

    description = tools[0](service="workflow_engine")
    assert description["status"] == "ok"
    assert description["service"] == "workflow_engine"

    blocked = tools[1](operation="workbench_package")
    assert blocked["status"] == "blocked"
    assert blocked["blocked_by"] == "read_only_default"

    invalid_args = tools[1](operation="workflow_manifest", arguments_json="[]")
    assert invalid_args["status"] == "failed"
    assert invalid_args["blocked_by"] == "invalid_arguments_json"
