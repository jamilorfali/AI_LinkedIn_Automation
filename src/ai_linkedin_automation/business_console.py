import hashlib
import json
import math
import os
import shutil
import struct
import urllib.error
import urllib.request
import zlib
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ai_linkedin_automation.approval import ALLOWED_APPROVAL_ACTIONS, record_approval
from ai_linkedin_automation.approval_webapp.deployment import (
    SYNC_TOKEN_ENV_KEY,
    SYNC_TOKEN_PLACEHOLDER,
    SYNC_TOKEN_PROPERTY,
    ensure_approval_sync_token,
    build_deployment_package,
)
from ai_linkedin_automation.approval_webapp.qa import run_local_approval_qa
from ai_linkedin_automation.article_package import extract_section, is_article_package
from ai_linkedin_automation.config import Config, project_root, resolve_project_path
from ai_linkedin_automation.drafting import generate_draft_from_topic, save_draft
from ai_linkedin_automation.ingestion.sources import load_sources_from_config
from ai_linkedin_automation.integrations.status import collect_integration_status
from ai_linkedin_automation.locus_workflows import (
    build_locus_workbench_package,
    collect_locus_status,
    run_locus_capability_check,
)
from ai_linkedin_automation.operations.preflight import run_preflight
from ai_linkedin_automation.operations.schedule import build_local_schedule_package
from ai_linkedin_automation.operations.workflows import run_daily_scan, run_friday_package
from ai_linkedin_automation.pilot.checklist import build_pilot_checklist, update_pilot_checklist_item
from ai_linkedin_automation.pilot.live_pilot import run_production_pilot
from ai_linkedin_automation.pilot.production_test import build_production_test_package
from ai_linkedin_automation.pilot.readiness import build_readiness_report
from ai_linkedin_automation.pilot.sheet_validation import (
    ReviewQueueValidationReport,
    validate_review_queue_csv,
)
from ai_linkedin_automation.notifications.packages import build_notification_package
from ai_linkedin_automation.publishing.archive import archive_manual_post
from ai_linkedin_automation.publishing.manual import build_manual_posting_package
from ai_linkedin_automation.publishing.safety_gate import evaluate_manual_posting_gate
from ai_linkedin_automation.review import create_approval_packet, export_review_queue_csv, import_review_queue_csv
from ai_linkedin_automation.storage.db import connect_db, transaction
from ai_linkedin_automation.intelligence.common import stable_id, tokenize


READABLE_SUFFIXES = {
    ".csv",
    ".gs",
    ".html",
    ".json",
    ".md",
    ".plist",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass
class BusinessAction:
    key: str
    label: str
    description: str
    button_text: str
    endpoint: str
    method: str = "POST"
    required: bool = True


@dataclass
class BusinessHome:
    generated_at: str
    stage: str
    headline: str
    next_action: BusinessAction
    journey_steps: List[Dict[str, object]]
    draft_workspace: Dict[str, object]
    guided_steps: List[Dict[str, str]]
    desktop_launcher: Dict[str, object]
    counts: Dict[str, int]
    readiness: Dict[str, object]
    checklist: Dict[str, object]
    latest_production_test: Dict[str, object]
    latest_artifacts: Dict[str, str]
    locus_status: Dict[str, object]


@dataclass
class DesktopLauncherPackage:
    status: str
    app_path: str
    command_path: str
    executable_path: str
    info_plist_path: str
    readme_path: str
    instructions: str


@dataclass
class DesktopIconInstall:
    status: str
    desktop_icon_path: str
    source_app_path: str
    instructions: str


@dataclass
class TouchFreeSetupStep:
    key: str
    label: str
    status: str
    details: str
    output_path: str = ""


@dataclass
class TouchFreeSetupReport:
    status: str
    generated_at: str
    summary: str
    steps: List[TouchFreeSetupStep]
    output_paths: Dict[str, str]
    markdown_path: str = ""
    json_path: str = ""


@dataclass
class FunctionalDiagnosticCheck:
    name: str
    status: str
    details: str


@dataclass
class FunctionalDiagnosticsReport:
    status: str
    generated_at: str
    summary: str
    checks: List[FunctionalDiagnosticCheck]
    markdown_path: str = ""
    json_path: str = ""


@dataclass
class ApprovalSetupStep:
    key: str
    label: str
    status: str
    description: str
    action: str
    artifact_path: str = ""


@dataclass
class ApprovalSetupGuide:
    status: str
    generated_at: str
    summary: str
    approval_url_configured: bool
    apps_script_deployed: bool
    deployment_package_ready: bool
    local_approval_qa_ready: bool
    steps: List[ApprovalSetupStep]
    latest_bundle: Dict[str, object]
    markdown_path: str = ""
    json_path: str = ""


@dataclass
class LocalApprovalResult:
    status: str
    draft_id: str
    review_id: str
    approval_id: str
    action: str
    manual_package_path: str = ""
    checklist_path: str = ""


@dataclass
class DraftRevisionResult:
    status: str
    preset: str
    label: str
    previous_draft_id: str
    draft_id: str
    topic_id: str
    draft_path: str
    approval_packet_path: str = ""
    notification_text_path: str = ""
    review_queue_path: str = ""
    message: str = ""


@dataclass
class PostImagePackage:
    status: str
    draft_id: str
    image_path: str
    safety_manifest_path: str
    prompt: str
    alt_text: str
    safety_status: str


@dataclass
class TopicBoardCategory:
    key: str
    label: str
    description: str
    topics: List[Dict[str, object]]


@dataclass
class EndToEndAutomationStep:
    key: str
    label: str
    status: str
    details: str
    output_path: str = ""


@dataclass
class EndToEndAutomationReport:
    status: str
    generated_at: str
    mode: str
    summary: str
    steps: List[EndToEndAutomationStep]
    output_paths: Dict[str, str]
    markdown_path: str = ""
    json_path: str = ""


PLAIN_CHECKLIST_NEXT_ACTIONS = {
    "local_readiness_passed": "Press Prepare Everything. The console will check the local system for you.",
    "approval_deployment_package_built": "Optional for phone approval: press Prepare Phone Approval to create the Google files.",
    "apps_script_deployed": "Optional for phone approval. Day-to-day local approval can happen inside this console.",
    "approval_url_configured": "Optional for phone approval. Local approval does not require this URL.",
    "local_approval_qa_passed": "Press Run Safe Approval Test to prove the approval round trip works locally.",
    "live_source_scan_run": "Press Start Weekly Flow to collect and score current source items.",
    "friday_package_generated": "Press Start Weekly Flow to build the weekly brief and intelligence report.",
    "weekly_candidates_reviewed": "Open the shortlist and runbook. If the source looks acceptable, mark source review done.",
    "real_draft_created": "Press Make First Test Package. The console will pick a candidate and draft it.",
    "review_queue_validated": "Optional for phone approval: press Sync to Phone Approval in Approve.",
    "iphone_magic_link_tested": "Open the approval link on your phone and choose a test decision, then mark phone test done.",
    "approval_imported": "Press Import Phone Decision, or use Approve Locally if you are staying on this laptop.",
    "first_post_archived": "After posting manually on LinkedIn, paste the post URL and press Archive Post.",
}


def save_env_value(env_path: Path, key: str, value: str) -> str:
    """Update or append one .env key without disturbing unrelated values."""
    if not key or "=" in key or "\n" in key:
        raise ValueError("Invalid env key")
    if "\n" in value or "\r" in value:
        raise ValueError("Environment values must be a single line")

    lines = env_path.read_text().splitlines() if env_path.exists() else []
    replacement = f"{key}={value.strip()}"
    updated = False
    next_lines: List[str] = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            next_lines.append(replacement)
            updated = True
        else:
            next_lines.append(line)
    if not updated:
        if next_lines and next_lines[-1].strip():
            next_lines.append("")
        next_lines.append(replacement)

    env_path.write_text("\n".join(next_lines).rstrip() + "\n")
    os.environ[key] = value.strip()
    return str(env_path)


def save_approval_url(value: str, env_path: Optional[Path] = None) -> str:
    url = value.strip()
    if not url.startswith("https://"):
        raise ValueError("Approval web app URL must start with https://")
    return save_env_value(env_path or project_root() / ".env", "GOOGLE_APPS_SCRIPT_WEBAPP_URL", url)


def refresh_latest_approval_assets(config: Config, week: str = "current") -> Dict[str, object]:
    """Refresh the active draft approval packet after phone approval URL setup."""
    latest = latest_production_test(config)
    draft_id = str(latest.get("draft_id") or "").strip() or _latest_draft_id(config)
    notification = build_notification_package(config, draft_id, week=week)

    if latest:
        latest_path = resolve_project_path(config.storage.exports_dir) / "production_tests" / "latest.json"
        latest["draft_id"] = draft_id
        latest["approval_packet_path"] = notification.approval_packet_path
        latest["review_queue_path"] = notification.review_queue_path
        latest["notification_text_path"] = notification.text_path
        latest["notification_html_path"] = notification.html_path
        latest["approval_url_configured"] = notification.approval_url_configured
        latest_path.write_text(json.dumps(latest, indent=2))

    build_pilot_checklist(config, write_files=True)
    return {
        "status": "approval_assets_refreshed",
        "draft_id": draft_id,
        "review_id": notification.review_id,
        "approval_url_configured": notification.approval_url_configured,
        "approval_packet_path": notification.approval_packet_path,
        "review_queue_path": notification.review_queue_path,
        "notification_text_path": notification.text_path,
        "notification_html_path": notification.html_path,
    }


def _count_rows(config: Config) -> Dict[str, int]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        counts = {}
        for table in [
            "sources",
            "findings",
            "topics",
            "drafts",
            "approval_tokens",
            "approvals",
            "posts",
        ]:
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return counts
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        conn.close()


def _escape_zsh_double_quoted(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )


def _launcher_command_script(app_dir_expression: str, literal: bool = False) -> str:
    app_dir_value = _escape_zsh_double_quoted(app_dir_expression) if literal else app_dir_expression
    return f"""#!/bin/zsh
set -e

APP_DIR="{app_dir_value}"
cd "$APP_DIR"
LOG_DIR="$APP_DIR/data/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/desktop_console.log"
LAUNCHER_CONTRACT="touch_free_locus_v2"
echo "$(date '+%Y-%m-%d %H:%M:%S') launcher start" >> "$LOG_FILE"

is_current_console() {{
  curl -fsS "$1/api/version" 2>/dev/null | grep -q "\\\"launcher_contract\\\": \\\"$LAUNCHER_CONTRACT\\\""
}}

if [ ! -x ".venv/bin/python" ]; then
  osascript -e 'display dialog "The AI LinkedIn Python environment is missing. Ask Codex to run setup once, then open this app again." buttons {{"OK"}} default button "OK"'
  exit 1
fi

for PORT in 8766 8767 8768 8769 8770; do
  URL="http://127.0.0.1:$PORT/"
  if is_current_console "$URL"; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') reusing console at $URL" >> "$LOG_FILE"
    open "$URL"
    exit 0
  fi

  echo "$(date '+%Y-%m-%d %H:%M:%S') starting console at $URL" >> "$LOG_FILE"
  nohup "$APP_DIR/.venv/bin/python" -m ai_linkedin_automation.ui_server --host 127.0.0.1 --port "$PORT" >> "$LOG_FILE" 2>&1 &
  SERVER_PID=$!
  disown "$SERVER_PID" 2>/dev/null || true

  for ATTEMPT in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24; do
    if is_current_console "$URL"; then
      echo "$(date '+%Y-%m-%d %H:%M:%S') console ready at $URL" >> "$LOG_FILE"
      open "$URL"
      exit 0
    fi
    if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
      break
    fi
    sleep 0.25
  done
done

osascript -e 'display dialog "The AI LinkedIn Console could not start. Ask Codex to inspect data/logs/desktop_console.log." buttons {{"OK"}} default button "OK"'
exit 1
"""


def _desktop_info_plist() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>AI LinkedIn Console</string>
  <key>CFBundleIdentifier</key>
  <string>com.ai-linkedin.console</string>
  <key>CFBundleName</key>
  <string>AI LinkedIn Console</string>
  <key>CFBundleDisplayName</key>
  <string>AI LinkedIn Console</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
</dict>
</plist>
"""


def build_desktop_launcher_package(root_path: Optional[Path] = None) -> DesktopLauncherPackage:
    """Create double-clickable launchers so the user does not need Terminal."""
    root = (root_path or project_root()).resolve()
    app_path = root / "AI LinkedIn Console.app"
    macos_dir = app_path / "Contents" / "MacOS"
    resources_dir = app_path / "Contents" / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    executable_path = macos_dir / "AI LinkedIn Console"
    info_plist_path = app_path / "Contents" / "Info.plist"
    readme_path = resources_dir / "README.md"
    command_path = root / "Launch AI LinkedIn Console.command"

    app_script = _launcher_command_script('$(cd "$(dirname "$0")/../../.." && pwd)')
    command_script = _launcher_command_script('$(cd "$(dirname "$0")" && pwd)')

    executable_path.write_text(app_script)
    command_path.write_text(command_script)
    info_plist_path.write_text(_desktop_info_plist())
    readme_path.write_text(
        """# AI LinkedIn Console Desktop App

Double-click `AI LinkedIn Console.app` to open the browser console without typing commands.

What it does:
- Starts or reuses the local AI LinkedIn server on a predictable private localhost port.
- Opens the business console in your default browser.
- Writes launcher troubleshooting output to `data/logs/desktop_console.log`.
- Keeps all paid APIs, email sending, and LinkedIn publishing disabled.

If macOS blocks the app the first time, right-click it, choose Open, then confirm.
"""
    )

    os.chmod(executable_path, 0o755)
    os.chmod(command_path, 0o755)

    return DesktopLauncherPackage(
        status="ready",
        app_path=str(app_path),
        command_path=str(command_path),
        executable_path=str(executable_path),
        info_plist_path=str(info_plist_path),
        readme_path=str(readme_path),
        instructions="Double-click AI LinkedIn Console.app. No terminal needed.",
    )


def desktop_launcher_status(root_path: Optional[Path] = None) -> Dict[str, object]:
    root = (root_path or project_root()).resolve()
    app_path = root / "AI LinkedIn Console.app"
    command_path = root / "Launch AI LinkedIn Console.command"
    executable_path = app_path / "Contents" / "MacOS" / "AI LinkedIn Console"
    desktop_icon_path = Path.home() / "Desktop" / "AI LinkedIn Console.app"
    desktop_executable_path = desktop_icon_path / "Contents" / "MacOS" / "AI LinkedIn Console"
    return {
        "ready": app_path.exists() and executable_path.exists() and os.access(executable_path, os.X_OK),
        "desktop_icon_ready": desktop_executable_path.exists()
        and os.access(desktop_executable_path, os.X_OK),
        "app_path": str(app_path),
        "desktop_icon_path": str(desktop_icon_path),
        "command_path": str(command_path),
        "executable_path": str(executable_path),
        "instructions": "Double-click AI LinkedIn Console.app. No terminal needed.",
    }


def install_desktop_icon(
    root_path: Optional[Path] = None,
    desktop_dir: Optional[Path] = None,
) -> DesktopIconInstall:
    """Copy the app bundle to the user's Desktop for true one-click use."""
    root = (root_path or project_root()).resolve()
    launcher = build_desktop_launcher_package(root)
    source = Path(launcher.app_path).resolve()
    desktop = (desktop_dir or Path.home() / "Desktop").resolve()
    desktop.mkdir(parents=True, exist_ok=True)
    target = desktop / "AI LinkedIn Console.app"

    if source != target.resolve():
        shutil.copytree(source, target, dirs_exist_ok=True)

    executable = target / "Contents" / "MacOS" / "AI LinkedIn Console"
    if executable.exists():
        executable.write_text(_launcher_command_script(str(root), literal=True))
        os.chmod(executable, 0o755)

    return DesktopIconInstall(
        status="ready",
        desktop_icon_path=str(target),
        source_app_path=str(source),
        instructions="Double-click the AI LinkedIn Console app on your Desktop to start work.",
    )


def latest_production_test(config: Config) -> Dict[str, object]:
    latest_path = resolve_project_path(config.storage.exports_dir) / "production_tests" / "latest.json"
    if not latest_path.exists():
        return {}
    try:
        return json.loads(latest_path.read_text())
    except json.JSONDecodeError:
        return {"error": f"Could not read {latest_path}"}


def latest_approval_deployment_bundle(config: Config) -> Dict[str, object]:
    exports_root = resolve_project_path(config.storage.exports_dir)
    manifests = sorted(
        exports_root.glob("approval_webapp/*/deployment_manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not manifests:
        return {}
    manifest_path = manifests[0]
    output_dir = manifest_path.parent
    script_dir = output_dir / "approval_webapp"
    scripts: Dict[str, str] = {}
    for file_name in ["Code.gs", "Index.html", "appsscript.json", "README.md"]:
        path = script_dir / file_name
        content = path.read_text(errors="replace") if path.exists() else ""
        if file_name == "Code.gs" and SYNC_TOKEN_PLACEHOLDER in content:
            content = content.replace(SYNC_TOKEN_PLACEHOLDER, ensure_approval_sync_token())
        scripts[file_name] = content

    checklist = output_dir / "DEPLOYMENT_CHECKLIST.md"
    sheet_template = output_dir / "review_queue_sheet_template.csv"
    return {
        "output_dir": str(output_dir),
        "manifest_path": str(manifest_path),
        "checklist_path": str(checklist),
        "sheet_template_csv": str(sheet_template),
        "checklist": checklist.read_text(errors="replace") if checklist.exists() else "",
        "sheet_template": sheet_template.read_text(errors="replace") if sheet_template.exists() else "",
        "scripts": scripts,
    }


def approval_sync_setup(config: Optional[Config] = None) -> Dict[str, object]:
    """Return the local token setup values needed by the Google Apps Script web app."""
    _ = config
    token = ensure_approval_sync_token()
    return {
        "status": "ready",
        "summary": "Sync token is ready. Add it as an Apps Script property if Verify Phone App says the token is missing.",
        "property_name": SYNC_TOKEN_PROPERTY,
        "sync_token": token,
        "sync_token_masked": f"{token[:8]}...{token[-6:]}",
        "env_key": SYNC_TOKEN_ENV_KEY,
        "setup_steps": [
            "In Apps Script, click Project Settings.",
            "Scroll to Script properties.",
            "Click Add script property.",
            f"Property: {SYNC_TOKEN_PROPERTY}",
            "Value: paste the copied sync token.",
            "Click Save script properties.",
            "Run Verify Phone App again. A redeploy is not required for property-only changes.",
        ],
        "property_assignment": f"{SYNC_TOKEN_PROPERTY}={token}",
    }


def _approval_setup_output_dir(config: Config) -> Path:
    output_dir = resolve_project_path(config.storage.exports_dir) / "approval_setup"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _write_approval_setup_guide(config: Config, guide: ApprovalSetupGuide) -> ApprovalSetupGuide:
    output_dir = _approval_setup_output_dir(config)
    guide.markdown_path = str(output_dir / "APPROVAL_SETUP_GUIDE.md")
    guide.json_path = str(output_dir / "approval_setup_guide.json")

    lines = [
        "# Phone Approval Setup Guide",
        "",
        f"Generated: {guide.generated_at}",
        f"Status: {guide.status}",
        f"Summary: {guide.summary}",
        "",
        "## Steps",
        "",
    ]
    for step in guide.steps:
        lines.append(f"### {step.label}")
        lines.append("")
        lines.append(f"- Status: {step.status}")
        lines.append(f"- What this does: {step.description}")
        lines.append(f"- Next action: {step.action}")
        if step.artifact_path:
            lines.append(f"- Artifact: {step.artifact_path}")
        lines.append("")
    Path(guide.markdown_path).write_text("\n".join(lines))
    Path(guide.json_path).write_text(json.dumps(asdict(guide), indent=2))
    return guide


def build_approval_setup_guide(config: Config, write_files: bool = True) -> ApprovalSetupGuide:
    """Build the human setup gate for Google Apps Script phone approval."""
    checklist = build_pilot_checklist(config, write_files=False)
    bundle = latest_approval_deployment_bundle(config)
    apps_script_item = _checklist_item(checklist, "apps_script_deployed")
    approval_url_item = _checklist_item(checklist, "approval_url_configured")
    qa_item = _checklist_item(checklist, "local_approval_qa_passed")

    deployment_ready = bool(bundle)
    apps_script_deployed = apps_script_item.status == "done"
    approval_url_configured = approval_url_item.status == "done"
    local_qa_ready = qa_item.status == "done"

    steps = [
        ApprovalSetupStep(
            key="deployment_package",
            label="Prepare the approval files",
            status="done" if deployment_ready else "pending",
            description="Creates the Apps Script files, Sheet header template, manifest, and deployment checklist.",
            action="Press Prepare Phone Approval if these files are missing.",
            artifact_path=str(bundle.get("checklist_path", "")),
        ),
        ApprovalSetupStep(
            key="google_sheet",
            label="Create the background ReviewQueue Sheet",
            status="done" if apps_script_deployed else "pending",
            description="A Google Sheet named AI LinkedIn Review Queue with a ReviewQueue tab stores approval decisions in the background.",
            action="Create the Sheet once, rename the first tab ReviewQueue, then open Extensions -> Apps Script.",
            artifact_path=str(bundle.get("sheet_template_csv", "")),
        ),
        ApprovalSetupStep(
            key="apps_script",
            label="Deploy the mobile approval page",
            status="done" if apps_script_deployed else "pending",
            description="Copies Code.gs, Index.html, and appsscript.json into Apps Script and deploys a web app with queue sync endpoints.",
            action="Deploy the web app in Google, then press Mark Approval Page Deployed in this console.",
            artifact_path=str(bundle.get("output_dir", "")),
        ),
        ApprovalSetupStep(
            key="approval_url",
            label="Save the web app URL",
            status="done" if approval_url_configured else "pending",
            description="Saves GOOGLE_APPS_SCRIPT_WEBAPP_URL locally so magic links open the deployed approval page.",
            action="Paste the Apps Script web app URL into Approval Setup and press Save URL.",
        ),
        ApprovalSetupStep(
            key="local_qa",
            label="Run safe approval QA",
            status="done" if local_qa_ready else "pending",
            description="Proves the approval round trip without LinkedIn publishing.",
            action="Press Run Safe Approval Test. For phone approval, also press Sync to Phone Approval and Import Phone Decision.",
            artifact_path=qa_item.details if qa_item.status == "done" else "",
        ),
    ]

    if not deployment_ready:
        status = "needs_deployment_package"
        summary = "Create the local approval deployment package first."
    elif not apps_script_deployed:
        status = "needs_google_deployment"
        summary = "Copy the generated files into Google Apps Script and deploy the web app."
    elif not approval_url_configured:
        status = "needs_webapp_url"
        summary = "Paste and save the deployed Apps Script web app URL."
    elif not local_qa_ready:
        status = "needs_local_qa"
        summary = "Run the safe local approval QA before phone testing."
    else:
        status = "ready_for_phone_approval_test"
        summary = "Phone approval setup is ready for iPhone magic-link testing."

    guide = ApprovalSetupGuide(
        status=status,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        summary=summary,
        approval_url_configured=approval_url_configured,
        apps_script_deployed=apps_script_deployed,
        deployment_package_ready=deployment_ready,
        local_approval_qa_ready=local_qa_ready,
        steps=steps,
        latest_bundle=bundle,
    )
    return _write_approval_setup_guide(config, guide) if write_files else guide


def _checklist_item(checklist, key: str):
    for item in checklist.items:
        if item.key == key:
            return item
    raise KeyError(key)


DRAFT_EDIT_PRESETS = {
    "longer": {
        "label": "Make it longer",
        "description": "Adds more context and a clearer business implication.",
    },
    "deeper_detail": {
        "label": "Add more detail",
        "description": "Expands the post with practical examples and why it matters.",
    },
    "shorter": {
        "label": "Make it shorter",
        "description": "Cuts the draft down and removes extra caveats.",
    },
    "more_concise": {
        "label": "More concise",
        "description": "Turns it into a tight 100-150 word post.",
    },
    "less_detail": {
        "label": "Less detail",
        "description": "Keeps the point while removing technical specifics.",
    },
    "warmer": {
        "label": "Make it warmer",
        "description": "Adds a more human, conversational opening.",
    },
    "business_friendly": {
        "label": "Business friendly",
        "description": "Explains it for non-engineer LinkedIn readers.",
    },
    "sharper_tone": {
        "label": "Sharper tone",
        "description": "Makes the point more direct without hype.",
    },
    "executive": {
        "label": "Make it executive",
        "description": "Adds a clearer leadership takeaway.",
    },
    "safer": {
        "label": "Make it safer",
        "description": "Softens claims and removes overconfident wording.",
    },
    "plain": {
        "label": "Make it simpler",
        "description": "Uses plainer language for a broader audience.",
    },
    "stronger_hook": {
        "label": "Stronger first line",
        "description": "Makes the opening line more direct.",
    },
    "final_polish": {
        "label": "Ready-to-post polish",
        "description": "Removes source-review notes and formats the final post body.",
    },
    "regenerate": {
        "label": "Start over safely",
        "description": "Regenerates the starter draft from the selected topic.",
    },
}


def _draft_row(config: Config, draft_id: str):
    conn = connect_db(config.storage.sqlite_path)
    try:
        return conn.execute(
            """
            SELECT
                drafts.id,
                drafts.topic_id,
                drafts.version,
                drafts.content,
                drafts.content_hash,
                drafts.draft_length_type,
                drafts.source_reference_count,
                drafts.status,
                drafts.created_at,
                topics.title AS topic_title,
                topics.summary AS topic_summary,
                topics.political_risk,
                topics.recommendation,
                topics.draft_readiness,
                findings.url AS source_url,
                sources.name AS source_name,
                sources.trust_tier
            FROM drafts
            LEFT JOIN topics ON topics.id = drafts.topic_id
            LEFT JOIN topic_findings ON topic_findings.topic_id = topics.id
            LEFT JOIN findings ON findings.id = topic_findings.finding_id
            LEFT JOIN sources ON sources.id = findings.source_id
            WHERE drafts.id = ?
            LIMIT 1
            """,
            (draft_id,),
        ).fetchone()
    finally:
        conn.close()


def _latest_approval_for_draft(config: Config, draft_id: str) -> Dict[str, object]:
    conn = connect_db(config.storage.sqlite_path)
    try:
        row = conn.execute(
            """
            SELECT
                approvals.id,
                approvals.action,
                approvals.draft_version,
                approvals.content_hash,
                approvals.approved_at,
                approvals.approval_channel
            FROM approvals
            WHERE approvals.draft_id = ?
            ORDER BY approvals.approved_at DESC
            LIMIT 1
            """,
            (draft_id,),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def _draft_is_approved_for_posting(config: Config, draft_id: str) -> Dict[str, object]:
    decision = evaluate_manual_posting_gate(config, draft_id)
    approval = _latest_approval_for_draft(config, draft_id)
    return {
        "approved": decision.allowed,
        "reason": decision.reason,
        "approval_action": decision.approval_action or approval.get("action", ""),
        "approval_id": approval.get("id", ""),
        "approved_at": approval.get("approved_at", ""),
    }


def _draft_word_count(text: str) -> int:
    return len([part for part in text.replace("\n", " ").split(" ") if part.strip()])


def _clean_external_summary(value: str, max_chars: int = 460) -> str:
    text = (value or "").replace("\r", " ").replace("\n", " ")
    import re

    text = re.sub(r"arXiv:\s*\d+\.\d+v\d+\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"Announce Type:\s*[-\w]+\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bAbstract:\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip()
    if len(text) <= max_chars:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    selected = []
    total = 0
    for sentence in sentences:
        if total + len(sentence) > max_chars and selected:
            break
        selected.append(sentence)
        total += len(sentence) + 1
        if len(selected) >= 3:
            break
    result = " ".join(selected).strip()
    if len(result) > max_chars:
        result = result[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "."
    return result


def _linkedin_ready_copy(row, content: str) -> str:
    """Return only the final copy/paste LinkedIn body, with internal notes removed."""
    raw = (content or "").strip()
    if is_article_package(raw):
        feed_post = extract_section(raw, "Feed Post")
        if feed_post:
            return feed_post.strip()

    lines = []
    skip_next_blank = False
    for line in raw.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered.startswith("source topic:") or lowered.startswith("draft id:"):
            continue
        if "trust tier" in lowered and "current recommendation" in lowered:
            skip_next_blank = True
            continue
        if lowered.startswith("source:") and row and row["source_name"] and row["source_name"] in stripped:
            continue
        if skip_next_blank and not stripped:
            skip_next_blank = False
            continue
        lines.append(line.rstrip())
    cleaned = _squash_blank_lines("\n".join(lines)).strip()

    internal_markers = [
        "Announce Type:",
        "Abstract:",
        "source context",
        "draft readiness",
        "trust tier",
        "current recommendation",
    ]
    if cleaned and not any(marker.lower() in cleaned.lower() for marker in internal_markers):
        return cleaned

    if row:
        summary = _clean_external_summary(row["topic_summary"] or "", max_chars=420)
        title = row["topic_title"] or "this AI signal"
        source_name = row["source_name"] or "a public source"
        if not summary:
            summary = f"A public source surfaced a useful AI signal: {title}."
        return _squash_blank_lines(
            f"""A useful AI story this week is not about the model itself. It is about the operating habit it points to.

{summary}

What matters for leaders is the pattern underneath it: teams need clearer rules for where AI can act, who checks the work, and when a person must stay in the loop.

I would treat this as a practical signal from {source_name}, not a final conclusion.

The question I would bring back to the team is simple: if this kind of AI capability becomes normal, what decision or workflow should we redesign before it redesigns us?"""
        ).strip()
    return cleaned


def _source_abstract(row) -> str:
    if not row:
        return ""
    summary = _clean_external_summary(row["topic_summary"] or "", max_chars=700)
    return summary or row["topic_title"] or ""


def _available_edit_presets() -> List[Dict[str, str]]:
    return [
        {"key": key, "label": item["label"], "description": item["description"]}
        for key, item in DRAFT_EDIT_PRESETS.items()
    ]


def _draft_workspace(config: Config, latest_package: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    latest_package = latest_package if latest_package is not None else latest_production_test(config)
    draft_id = str((latest_package or {}).get("draft_id") or "").strip()
    if (latest_package or {}).get("status") == "topic_refresh_ready" and not draft_id:
        return {
            "ready": False,
            "message": "The topic board was refreshed. Pick a new topic to build the next draft.",
            "refresh_ready": True,
            "edit_presets": _available_edit_presets(),
        }
    if not draft_id:
        try:
            draft_id = _latest_draft_id(config)
        except Exception:
            return {
                "ready": False,
                "message": "No draft exists yet. Press Build My Draft to create one.",
                "edit_presets": _available_edit_presets(),
            }

    row = _draft_row(config, draft_id)
    if not row:
        return {
            "ready": False,
            "message": "The latest draft could not be found. Build a new draft package.",
            "edit_presets": _available_edit_presets(),
        }

    approval_state = _draft_is_approved_for_posting(config, draft_id)
    content = row["content"] or ""
    image = latest_post_image(config, draft_id)
    return {
        "ready": True,
        "draft_id": row["id"],
        "topic_id": row["topic_id"],
        "version": row["version"],
        "status": row["status"],
        "topic_title": row["topic_title"] or "Untitled topic",
        "topic_summary": row["topic_summary"] or "",
        "source_name": row["source_name"] or "Unknown source",
        "source_url": row["source_url"] or "",
        "trust_tier": row["trust_tier"] or "unknown",
        "political_risk": row["political_risk"] or "unknown",
        "recommendation": row["recommendation"] or "needs_review",
        "draft_readiness": row["draft_readiness"] or 0,
        "content": content,
        "final_post_text": _linkedin_ready_copy(row, content),
        "source_abstract": _source_abstract(row),
        "source_link_text": row["source_url"] or "",
        "draft_length_type": row["draft_length_type"] or "short",
        "source_reference_count": row["source_reference_count"] or 0,
        "word_count": _draft_word_count(content),
        "line_count": len([line for line in content.splitlines() if line.strip()]),
        "approved": approval_state["approved"],
        "approval": approval_state,
        "candidate_publish_ready": bool((latest_package or {}).get("candidate_publish_ready")),
        "draft_path": str((latest_package or {}).get("draft_path") or ""),
        "manual_package_path": str((latest_package or {}).get("manual_package_path") or ""),
        "post_image": image,
        "edit_presets": _available_edit_presets(),
    }


def _journey_steps(checklist, latest_package: Dict[str, object], draft: Dict[str, object]) -> List[Dict[str, object]]:
    source_review = _checklist_item(checklist, "weekly_candidates_reviewed")
    first_post = _checklist_item(checklist, "first_post_archived")
    refresh_ready = bool((latest_package or {}).get("status") == "topic_refresh_ready" and not draft.get("ready"))
    package_ready = bool(latest_package) and not refresh_ready
    draft_ready = bool(draft.get("ready"))
    source_ok = False if refresh_ready else source_review.status == "done"
    approved = bool(draft.get("approved"))
    archived = first_post.status == "done"

    return [
        {
            "key": "prepare",
            "number": 1,
            "label": "Get the app ready",
            "status": "done",
            "plain": "The local app, source list, safety checks, and Locus workflow engine are ready.",
            "button_text": "Check Again",
            "endpoint": "/api/business/run-functional-diagnostics",
        },
        {
            "key": "build",
            "number": 2,
            "label": "Build my draft",
            "status": "done" if package_ready and draft_ready else "ready",
            "plain": "The app picks a topic, checks sources, writes a draft, and prepares approval files.",
            "button_text": "Build My Draft",
            "endpoint": "/api/build-production-test-package",
        },
        {
            "key": "source_review",
            "number": 3,
            "label": "Check the source",
            "status": "done" if source_ok else "ready" if package_ready else "locked",
            "plain": "A human must confirm the topic is suitable before anything is posted.",
            "button_text": "Source Looks OK",
            "endpoint": "/api/update-pilot-checklist",
        },
        {
            "key": "edit",
            "number": 4,
            "label": "Tune the draft",
            "status": "ready" if draft_ready and not approved else "done" if approved else "locked",
            "plain": "Use buttons for shorter, warmer, safer, simpler, or more executive wording.",
            "button_text": "Use Edit Buttons",
            "endpoint": "/api/business/apply-draft-preset",
        },
        {
            "key": "approve",
            "number": 5,
            "label": "Approve this exact version",
            "status": "done" if approved else "ready" if draft_ready and source_ok else "locked",
            "plain": "Approval is tied to the exact draft version and content hash.",
            "button_text": "Approve Draft",
            "endpoint": "/api/business/approve-locally",
        },
        {
            "key": "package",
            "number": 6,
            "label": "Make the posting package",
            "status": "ready" if approved and not archived else "done" if archived else "locked",
            "plain": "The app creates final copy and source notes for manual LinkedIn posting.",
            "button_text": "Make Posting Package",
            "endpoint": "/api/business/build-manual-package",
        },
        {
            "key": "archive",
            "number": 7,
            "label": "Save the final URL",
            "status": "done" if archived else "ready" if approved else "locked",
            "plain": "After you manually post, paste the LinkedIn URL once so the app remembers it.",
            "button_text": "Archive URL",
            "endpoint": "/api/business/archive-post",
        },
    ]


def _next_action(
    checklist,
    latest_package: Dict[str, object],
    draft: Optional[Dict[str, object]] = None,
) -> BusinessAction:
    weekly_review = _checklist_item(checklist, "weekly_candidates_reviewed")
    first_post = _checklist_item(checklist, "first_post_archived")
    draft = draft or {}
    draft_ready = bool(draft.get("ready"))
    draft_approved = bool(draft.get("approved"))
    refresh_ready = bool((latest_package or {}).get("status") == "topic_refresh_ready" and not draft_ready)

    if not latest_package:
        return BusinessAction(
            key="build_test_package",
            label="Build your first draft",
            description="I will pick a candidate, check sources, create the draft, and prepare the approval files.",
            button_text="Build My Draft",
            endpoint="/api/build-production-test-package",
        )
    if refresh_ready:
        return BusinessAction(
            key="pick_topic",
            label="Pick one of the refreshed topics",
            description="Choose a topic card below, or type your own topic, and I will build the draft from there.",
            button_text="Show Topic Board",
            endpoint="/api/business/topic-board",
            method="GET",
        )
    if weekly_review.status != "done":
        return BusinessAction(
            key="review_candidate",
            label="Check the selected source",
            description="Read the topic card. If it looks appropriate for public LinkedIn, click Source Looks OK.",
            button_text="Review Source",
            endpoint="/api/business/latest-production-test",
            method="GET",
        )
    if draft_ready and not draft_approved:
        return BusinessAction(
            key="approve_locally",
            label="Approve this draft",
            description="Approve the exact version shown on screen, then I will build the final posting package.",
            button_text="Approve Draft",
            endpoint="/api/business/approve-locally",
        )
    if first_post.status != "done":
        return BusinessAction(
            key="manual_package",
            label="Create the posting package",
            description="Make the final copy-and-source package for manual LinkedIn posting.",
            button_text="Make Posting Package",
            endpoint="/api/business/build-manual-package",
        )
    return BusinessAction(
        key="weekly_loop_ready",
        label="Weekly loop is ready",
        description="The first post has been archived. Keep using the console for weekly runs.",
        button_text="Run Weekly Flow",
        endpoint="/api/run-production-pilot",
    )


def _guided_steps(checklist, refresh_ready: bool = False) -> List[Dict[str, str]]:
    steps = []
    for item in checklist.items:
        status = item.status
        notes = item.details
        if refresh_ready and item.key == "weekly_candidates_reviewed":
            status = "pending"
            notes = "Topic board was refreshed. Pick a topic and review its source."
        steps.append(
            {
                "key": item.key,
                "label": item.label,
                "status": status,
                "phase": item.phase,
                "details": notes,
                "next_action": PLAIN_CHECKLIST_NEXT_ACTIONS.get(item.key, item.next_action),
            }
        )
    return steps


def business_home(config: Config) -> BusinessHome:
    readiness = build_readiness_report(config, write_files=False)
    checklist = build_pilot_checklist(config, write_files=False)
    latest_package = latest_production_test(config)
    counts = _count_rows(config)
    draft = _draft_workspace(config, latest_package)
    refresh_ready = bool((latest_package or {}).get("status") == "topic_refresh_ready" and not draft.get("ready"))
    journey = _journey_steps(checklist, latest_package, draft)
    next_action = _next_action(checklist, latest_package, draft)
    headline = {
        "ready_for_live_source_pilot": "Start at step 1. I will guide you from topic to final LinkedIn package.",
        "ready_for_mobile_approval_pilot": "Phone approval is available, but local approval is the simple path.",
        "ready_for_first_manual_post": "Your approved draft is ready for the final posting package.",
        "blocked": "Something is blocked. Start with the checklist.",
        "setup_in_progress": "Setup is in progress. Follow the next action.",
    }.get(checklist.stage, checklist.summary)

    return BusinessHome(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        stage=checklist.stage,
        headline=headline,
        next_action=next_action,
        journey_steps=journey,
        draft_workspace=draft,
        guided_steps=_guided_steps(checklist, refresh_ready=refresh_ready),
        desktop_launcher=desktop_launcher_status(),
        counts=counts,
        readiness={
            "stage": readiness.live_testing_stage,
            "decision": readiness.decision,
            "warn_count": readiness.warn_count,
            "fail_count": readiness.fail_count,
        },
        checklist={
            "stage": checklist.stage,
            "summary": checklist.summary,
            "done_count": checklist.done_count,
            "pending_count": checklist.pending_count,
            "attention_count": checklist.attention_count,
            "blocked_count": checklist.blocked_count,
            "items": [asdict(item) for item in checklist.items],
        },
        latest_production_test=latest_package,
        latest_artifacts=readiness.latest_artifacts,
        locus_status=asdict(collect_locus_status(config)),
    )


def _setup_output_dir(config: Config) -> Path:
    output_dir = resolve_project_path(config.storage.exports_dir) / "business_console"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _setup_step(
    steps: List[TouchFreeSetupStep],
    key: str,
    label: str,
    status: str,
    details: str,
    output_path: str = "",
) -> None:
    steps.append(
        TouchFreeSetupStep(
            key=key,
            label=label,
            status=status,
            details=details,
            output_path=output_path,
        )
    )


def _write_touch_free_setup_report(config: Config, report: TouchFreeSetupReport) -> TouchFreeSetupReport:
    output_dir = _setup_output_dir(config)
    report.markdown_path = str(output_dir / "TOUCH_FREE_SETUP_REPORT.md")
    report.json_path = str(output_dir / "touch_free_setup_report.json")

    lines = [
        "# Touch-Free Business Console Setup",
        "",
        f"Generated: {report.generated_at}",
        f"Status: {report.status}",
        f"Summary: {report.summary}",
        "",
        "## Steps",
        "",
    ]
    for step in report.steps:
        lines.append(f"- [{step.status.upper()}] {step.label}: {step.details}")
        if step.output_path:
            lines.append(f"  Output: {step.output_path}")
    lines.extend(["", "## Outputs", ""])
    for key, path in sorted(report.output_paths.items()):
        lines.append(f"- {key}: {path}")

    Path(report.markdown_path).write_text("\n".join(lines) + "\n")
    Path(report.json_path).write_text(json.dumps(asdict(report), indent=2))
    return report


def _write_functional_diagnostics_report(
    config: Config,
    report: FunctionalDiagnosticsReport,
) -> FunctionalDiagnosticsReport:
    output_dir = _setup_output_dir(config)
    report.markdown_path = str(output_dir / "FUNCTIONAL_DIAGNOSTICS.md")
    report.json_path = str(output_dir / "functional_diagnostics.json")

    lines = [
        "# Functional Diagnostics",
        "",
        f"Generated: {report.generated_at}",
        f"Status: {report.status}",
        f"Summary: {report.summary}",
        "",
        "## Checks",
        "",
    ]
    for check in report.checks:
        lines.append(f"- [{check.status.upper()}] {check.name}: {check.details}")

    Path(report.markdown_path).write_text("\n".join(lines) + "\n")
    Path(report.json_path).write_text(json.dumps(asdict(report), indent=2))
    return report


def _diagnostic_check(
    checks: List[FunctionalDiagnosticCheck],
    name: str,
    status: str,
    details: str,
) -> None:
    checks.append(FunctionalDiagnosticCheck(name=name, status=status, details=details))


def run_functional_diagnostics(config: Config) -> FunctionalDiagnosticsReport:
    """Run a safe functional diagnostic sweep across local modules and integrations."""
    checks: List[FunctionalDiagnosticCheck] = []
    counts = _count_rows(config)
    readiness = build_readiness_report(config, write_files=False)
    checklist = build_pilot_checklist(config, write_files=False)
    integrations = collect_integration_status(config)
    launcher = desktop_launcher_status()
    latest_package = latest_production_test(config)
    deployment = latest_approval_deployment_bundle(config)

    _diagnostic_check(
        checks,
        "Desktop launcher",
        "pass" if launcher["ready"] else "fail",
        launcher["app_path"] if launcher["ready"] else "Desktop launcher has not been built.",
    )
    _diagnostic_check(
        checks,
        "Desktop icon",
        "pass" if launcher["desktop_icon_ready"] else "warn",
        launcher["desktop_icon_path"]
        if launcher["desktop_icon_ready"]
        else "Use Put App On Desktop from the console.",
    )
    _diagnostic_check(
        checks,
        "SQLite database",
        "pass" if "error" not in counts else "fail",
        f"{counts.get('sources', 0)} source(s), {counts.get('findings', 0)} finding(s), {counts.get('drafts', 0)} draft(s).",
    )
    _diagnostic_check(
        checks,
        "Readiness report",
        "pass" if readiness.fail_count == 0 else "fail",
        f"{readiness.fail_count} failure(s), {readiness.warn_count} warning(s). {readiness.decision}",
    )
    risky = [item.name for item in integrations.items if item.paid_capable and item.enabled and item.cost_allowed]
    _diagnostic_check(
        checks,
        "Integration guardrails",
        "fail" if risky else "pass",
        "Paid-capable integrations remain blocked." if not risky else ", ".join(risky),
    )
    _diagnostic_check(
        checks,
        "Approval deployment package",
        "pass" if deployment else "warn",
        deployment.get("checklist_path", "Run Prepare Phone Approval from the console."),
    )
    _diagnostic_check(
        checks,
        "Production test package",
        "pass" if latest_package else "warn",
        latest_package.get("runbook_path", "Run Make First Test Package from the console."),
    )
    _diagnostic_check(
        checks,
        "Pilot checklist",
        "pass" if checklist.stage != "blocked" else "fail",
        f"{checklist.summary} Done: {checklist.done_count}; attention: {checklist.attention_count}; pending: {checklist.pending_count}.",
    )
    _diagnostic_check(
        checks,
        "Touch-free setup report",
        "pass" if readiness.latest_artifacts.get("touch_free_setup_report") else "warn",
        readiness.latest_artifacts.get("touch_free_setup_report") or "Run Prepare Everything from the console.",
    )

    if any(check.status == "fail" for check in checks):
        status = "failed"
        summary = "One or more functional checks failed."
    elif any(check.status == "warn" for check in checks):
        status = "passed_with_warnings"
        summary = "Core functions are available; warning items are operator setup steps."
    else:
        status = "passed"
        summary = "Local launcher, workflow, guardrails, and artifacts are ready."

    return _write_functional_diagnostics_report(
        config,
        FunctionalDiagnosticsReport(
            status=status,
            generated_at=datetime.now().isoformat(timespec="seconds"),
            summary=summary,
            checks=checks,
        ),
    )


def _e2e_step(
    steps: List[EndToEndAutomationStep],
    key: str,
    label: str,
    status: str,
    details: str,
    output_path: str = "",
) -> None:
    steps.append(
        EndToEndAutomationStep(
            key=key,
            label=label,
            status=status,
            details=details,
            output_path=output_path,
        )
    )


def _write_e2e_report(config: Config, report: EndToEndAutomationReport) -> EndToEndAutomationReport:
    output_dir = _setup_output_dir(config)
    safe_mode = report.mode.replace("-", "_")
    report.markdown_path = str(output_dir / f"{safe_mode.upper()}_E2E_REPORT.md")
    report.json_path = str(output_dir / f"{safe_mode}_e2e_report.json")

    lines = [
        f"# {report.mode.replace('_', ' ').title()} E2E Report",
        "",
        f"Generated: {report.generated_at}",
        f"Status: {report.status}",
        f"Summary: {report.summary}",
        "",
        "## Steps",
        "",
    ]
    for step in report.steps:
        lines.append(f"- [{step.status.upper()}] {step.label}: {step.details}")
        if step.output_path:
            lines.append(f"  Output: {step.output_path}")
    if report.output_paths:
        lines.extend(["", "## Outputs", ""])
        for key, path in sorted(report.output_paths.items()):
            lines.append(f"- {key}: {path}")

    Path(report.markdown_path).write_text("\n".join(lines) + "\n")
    Path(report.json_path).write_text(json.dumps(asdict(report), indent=2))
    return report


def _e2e_status(steps: List[EndToEndAutomationStep]) -> str:
    if any(step.status == "fail" for step in steps):
        return "failed"
    if any(step.status == "warn" for step in steps):
        return "passed_with_warnings"
    return "passed"


def run_locus_e2e_test(config: Config, week: str = "current") -> EndToEndAutomationReport:
    """Exercise the local Locus control plane end to end without external side effects."""
    steps: List[EndToEndAutomationStep] = []
    output_paths: Dict[str, str] = {}

    try:
        status = collect_locus_status(config)
        _e2e_step(
            steps,
            "locus_status",
            "Check Locus engine",
            "pass" if status.hard_zero_safe else "fail",
            f"{status.engine}; provider mode {status.provider_mode}; SDK installed: {status.sdk_installed}.",
        )

        capability = run_locus_capability_check(config)
        output_paths["locus_capability_report"] = capability.markdown_path
        _e2e_step(
            steps,
            "capability_check",
            "Run Locus capability check",
            "pass" if capability.status == "passed" else "fail",
            f"{len(capability.checks)} check(s); status {capability.status}.",
            capability.markdown_path,
        )

        load_sources_from_config(config)
        daily = run_daily_scan(config, dry_run=True)
        output_paths["daily_scan_report"] = daily.report_path
        output_paths["daily_scan_trace"] = daily.output_paths.get("locus_trace", "")
        _e2e_step(
            steps,
            "daily_scan_graph",
            "Run daily scan graph",
            "pass" if daily.status == "completed" else "fail",
            f"{len(daily.steps)} node(s); trace events {daily.orchestration.get('event_count', 0)}.",
            daily.report_path,
        )

        friday = run_friday_package(config, week=week, dry_run=True)
        output_paths["friday_package_report"] = friday.report_path
        output_paths["friday_package_trace"] = friday.output_paths.get("locus_trace", "")
        _e2e_step(
            steps,
            "friday_package_graph",
            "Run Friday package graph",
            "pass" if friday.status == "completed" else "fail",
            f"{len(friday.steps)} node(s); trace events {friday.orchestration.get('event_count', 0)}.",
            friday.report_path,
        )

        pilot = run_production_pilot(config, week=week, dry_run=True)
        output_paths["production_pilot_report"] = pilot.markdown_path
        output_paths["production_pilot_trace"] = pilot.output_paths.get("locus_trace", "")
        _e2e_step(
            steps,
            "production_pilot_graph",
            "Run production pilot graph",
            "pass" if pilot.status in {"passed", "passed_with_warnings"} else "fail",
            f"{pilot.status}; checklist stage {pilot.checklist_stage}.",
            pilot.markdown_path,
        )

        workbench = build_locus_workbench_package(config)
        output_paths["locus_workbench_manifest"] = workbench.manifest_path
        _e2e_step(
            steps,
            "workbench_export",
            "Export Locus workflow map",
            "pass" if workbench.status == "ready" else "fail",
            f"{len(workbench.diagrams)} diagram(s) exported.",
            workbench.manifest_path,
        )
    except Exception as exc:
        _e2e_step(steps, "exception", "Locus E2E exception", "fail", str(exc))

    status_value = _e2e_status(steps)
    summary = (
        "Locus StateGraph, capability, trace, and Workbench paths passed."
        if status_value == "passed"
        else "One or more Locus E2E checks needs attention."
    )
    return _write_e2e_report(
        config,
        EndToEndAutomationReport(
            status=status_value,
            generated_at=datetime.now().isoformat(timespec="seconds"),
            mode="locus",
            summary=summary,
            steps=steps,
            output_paths=output_paths,
        ),
    )


def run_application_e2e_test(
    config: Config,
    week: str = "current",
    approval_action: str = "approve_text_only",
    archive_post_url: str = "",
) -> EndToEndAutomationReport:
    """Run the local app from setup through approved manual package creation."""
    steps: List[EndToEndAutomationStep] = []
    output_paths: Dict[str, str] = {}

    try:
        setup = run_touch_free_setup(config, week=week, include_approval_qa=True)
        output_paths["touch_free_setup_report"] = setup.markdown_path
        _e2e_step(
            steps,
            "touch_free_setup",
            "Prepare business console",
            "pass" if setup.status in {"ready_with_manual_approval_setup", "ready_for_touch_free_operation"} else "fail",
            setup.summary,
            setup.markdown_path,
        )

        pilot = run_production_pilot(config, week=week, dry_run=True)
        output_paths["production_pilot_report"] = pilot.markdown_path
        _e2e_step(
            steps,
            "production_pilot",
            "Run production pilot",
            "pass" if pilot.status in {"passed", "passed_with_warnings"} else "fail",
            f"{pilot.status}; checklist stage {pilot.checklist_stage}.",
            pilot.markdown_path,
        )

        package = build_production_test_package(config, week=week)
        output_paths["production_test_runbook"] = package.runbook_path
        output_paths["production_test_manifest"] = package.manifest_path
        _e2e_step(
            steps,
            "production_test_package",
            "Build production test package",
            "pass",
            f"Draft {package.draft_id}; selected topic {package.selected_topic_title}.",
            package.runbook_path,
        )

        if package.candidate_publish_ready:
            checklist = update_pilot_checklist_item(
                config,
                "weekly_candidates_reviewed",
                "done",
                "Automated E2E confirmed deterministic publish-readiness gates.",
            )
            output_paths["pilot_checklist"] = checklist.markdown_path
            _e2e_step(
                steps,
                "source_review_gate",
                "Auto-clear deterministic source gate",
                "pass",
                "Selected topic passed trust, risk, recommendation, and draft-readiness checks.",
                checklist.markdown_path,
            )
        else:
            _e2e_step(
                steps,
                "source_review_gate",
                "Keep source review human",
                "warn",
                "Selected topic is useful for flow testing, but source quality still needs human review before posting.",
            )

        approval = approve_latest_draft_locally(
            config,
            draft_id=package.draft_id,
            action=approval_action,
            notes="Approved by automated local E2E test.",
            build_package=True,
        )
        output_paths["manual_posting_package"] = approval.manual_package_path
        _e2e_step(
            steps,
            "local_approval",
            "Approve locally and build final package",
            "pass" if approval.manual_package_path else "warn",
            f"{approval.status}; action {approval.action}; review {approval.review_id}.",
            approval.manual_package_path,
        )

        if archive_post_url.strip():
            archive = archive_latest_post(config, archive_post_url, draft_id=package.draft_id)
            _e2e_step(
                steps,
                "archive_post",
                "Archive posted URL",
                "pass",
                f"Archived {archive['post_id']}.",
                str(archive.get("post_url") or ""),
            )
        else:
            _e2e_step(
                steps,
                "archive_post",
                "Wait for real LinkedIn URL",
                "warn",
                "LinkedIn posting is intentionally not automated; paste the final post URL after you publish.",
            )

        diagnostics = run_functional_diagnostics(config)
        output_paths["functional_diagnostics"] = diagnostics.markdown_path
        _e2e_step(
            steps,
            "functional_diagnostics",
            "Run functional diagnostics",
            "pass" if diagnostics.status in {"passed", "passed_with_warnings"} else "fail",
            diagnostics.summary,
            diagnostics.markdown_path,
        )
    except Exception as exc:
        _e2e_step(steps, "exception", "Application E2E exception", "fail", str(exc))

    status_value = _e2e_status(steps)
    summary = (
        "Application is ready through local approval and final manual package creation."
        if status_value == "passed"
        else "Application E2E completed with remaining human-only or warning gates."
        if status_value == "passed_with_warnings"
        else "Application E2E found a blocking issue."
    )
    return _write_e2e_report(
        config,
        EndToEndAutomationReport(
            status=status_value,
            generated_at=datetime.now().isoformat(timespec="seconds"),
            mode="application",
            summary=summary,
            steps=steps,
            output_paths=output_paths,
        ),
    )


def run_touch_free_setup(
    config: Config,
    week: str = "current",
    include_approval_qa: bool = True,
    launcher_root: Optional[Path] = None,
) -> TouchFreeSetupReport:
    """Prepare the local app for business-user operation without external side effects."""
    from ai_linkedin_automation.storage.db import init_db

    steps: List[TouchFreeSetupStep] = []
    output_paths: Dict[str, str] = {}

    init_db(config.storage.sqlite_path)
    _setup_step(
        steps,
        "init_db",
        "Prepare the local database",
        "done",
        "Database initialized or migrated.",
        config.storage.sqlite_path,
    )

    load_sources_from_config(config)
    counts = _count_rows(config)
    _setup_step(
        steps,
        "load_sources",
        "Load approved source list",
        "done",
        f"{counts.get('sources', 0)} source(s) loaded.",
    )

    launcher = build_desktop_launcher_package(root_path=launcher_root)
    output_paths["desktop_app"] = launcher.app_path
    output_paths["command_launcher"] = launcher.command_path
    _setup_step(
        steps,
        "desktop_launcher",
        "Create double-click desktop launcher",
        "done",
        launcher.instructions,
        launcher.app_path,
    )

    preflight = run_preflight(config)
    preflight_status = "done" if preflight.ok else "blocked"
    warning_count = sum(1 for check in preflight.checks if check.status == "warn")
    _setup_step(
        steps,
        "preflight",
        "Check local safety and readiness",
        preflight_status,
        f"{len(preflight.checks)} checks run; {warning_count} warning(s).",
    )

    deployment = build_deployment_package(config, week=week)
    output_paths["approval_deployment_checklist"] = deployment.checklist_path
    output_paths["approval_sheet_template"] = deployment.sheet_template_csv
    _setup_step(
        steps,
        "approval_deployment",
        "Prepare phone approval deployment files",
        "done",
        "Apps Script files, Sheet template, and checklist are ready to copy from the console.",
        deployment.checklist_path,
    )

    if include_approval_qa:
        qa = run_local_approval_qa(config, action="approve_text_only", week=week)
        output_paths["approval_qa_report"] = qa.report_path
        _setup_step(
            steps,
            "approval_qa",
            "Run safe approval round-trip test",
            "done" if qa.status == "passed" else "blocked",
            f"Approval QA status: {qa.status}.",
            qa.report_path,
        )

    schedule = build_local_schedule_package(config)
    output_paths["schedule_runbook"] = schedule.runbook_path
    _setup_step(
        steps,
        "schedule_package",
        "Prepare optional weekly schedule files",
        "done",
        "Schedule files were generated but not installed.",
        schedule.runbook_path,
    )

    readiness = build_readiness_report(config, write_files=True)
    output_paths["readiness_report"] = readiness.markdown_path
    readiness_status = "blocked" if readiness.fail_count else "attention" if readiness.warn_count else "done"
    _setup_step(
        steps,
        "readiness_report",
        "Build live testing readiness report",
        readiness_status,
        readiness.decision,
        readiness.markdown_path,
    )

    checklist = build_pilot_checklist(config, write_files=True)
    output_paths["pilot_checklist"] = checklist.markdown_path
    _setup_step(
        steps,
        "pilot_checklist",
        "Refresh plain-English pilot checklist",
        "done",
        checklist.summary,
        checklist.markdown_path,
    )

    if any(step.status == "blocked" for step in steps):
        status = "needs_attention"
        summary = "The business console is installed, but one or more setup checks need attention."
    elif any(step.status == "attention" for step in steps):
        status = "ready_with_manual_approval_setup"
        summary = "The console is ready; finish the manual approval URL step before phone approval testing."
    else:
        status = "ready_for_touch_free_operation"
        summary = "The console, local QA, approval files, and schedule package are ready."

    report = TouchFreeSetupReport(
        status=status,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        summary=summary,
        steps=steps,
        output_paths=output_paths,
    )
    return _write_touch_free_setup_report(config, report)


def _uploads_dir(config: Config) -> Path:
    output_dir = resolve_project_path(config.storage.exports_dir) / "review_queue_uploads"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def save_review_queue_csv_content(config: Config, csv_content: str) -> str:
    if not csv_content.strip():
        raise ValueError("CSV content is empty")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _uploads_dir(config) / f"{timestamp}_sheet_export.csv"
    path.write_text(csv_content)
    return str(path)


def validate_review_queue_content(config: Config, csv_content: str) -> ReviewQueueValidationReport:
    csv_path = save_review_queue_csv_content(config, csv_content)
    return validate_review_queue_csv(config, csv_path)


def import_review_queue_content(config: Config, csv_content: str) -> Dict[str, object]:
    validation = validate_review_queue_content(config, csv_content)
    if not validation.ok:
        return {
            "imported": 0,
            "skipped": 0,
            "errors": ["CSV validation failed."],
            "validation": asdict(validation),
        }
    if validation.decision_rows == 0:
        return {
            "imported": 0,
            "skipped": validation.pending_rows,
            "errors": ["No approval decision rows were found."],
            "validation": asdict(validation),
        }

    result = import_review_queue_csv(config, validation.csv_path)
    build_pilot_checklist(config, write_files=True)
    return {
        "imported": result.imported,
        "skipped": result.skipped,
        "errors": result.errors,
        "validation": asdict(validation),
    }


def _approval_webapp_url() -> str:
    url = os.environ.get("GOOGLE_APPS_SCRIPT_WEBAPP_URL", "").strip()
    if not url:
        raise RuntimeError("Save the Google Apps Script /exec URL before syncing phone approval.")
    if not url.startswith("https://"):
        raise RuntimeError("The Google Apps Script web app URL must start with https://.")
    return url


def _latest_review_queue_path(config: Config, week: str = "current") -> Path:
    latest = latest_production_test(config)
    configured_path = str(latest.get("review_queue_path") or "").strip()
    if configured_path:
        path = Path(configured_path)
        if not path.is_absolute():
            path = project_root() / path
        if path.exists():
            return path

    week_dir = resolve_project_path(config.storage.review_packets_dir)
    candidates = sorted(
        week_dir.glob("*/review_queue.csv"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]

    draft_id = str(latest.get("draft_id") or "").strip()
    if not draft_id:
        try:
            draft_id = _latest_draft_id(config)
        except Exception:
            return Path(export_review_queue_csv(config, week=week))
    return Path(build_notification_package(config, draft_id, week=week).review_queue_path)


def _clean_webapp_body(body: str) -> str:
    import re

    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", body or "", flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:360]


def _google_webapp_recovery_message(status_code: Optional[int], body: str = "") -> str:
    clean_body = _clean_webapp_body(body)
    lower_body = (body or "").lower()
    prefix = f"Google approval web app returned HTTP {status_code}." if status_code else "Google approval web app did not return JSON."

    if status_code in {401, 403} or "page not found" in lower_body or "service login" in lower_body:
        return (
            f"{prefix} The deployed Apps Script is not allowing this local console to call the sync API yet. "
            "In Apps Script, open Deploy -> Manage deployments -> pencil icon, set Access to Anyone if Google offers it, "
            "choose Version -> New version, and press Deploy. Your saved /exec URL can stay the same. "
            "If your Google account only offers Anyone with Google account, the server-side sync cannot use your browser login; "
            "use Approve Locally for this run or keep the manual CSV fallback until OAuth/clasp setup is added."
        )

    if "missing parameters" in lower_body:
        return (
            f"{prefix} The saved web app URL is still running the old approval script. "
            "Use Optional Phone Approval to copy the updated Code.gs and Index.html, then deploy a new version. "
            "The saved /exec URL can stay the same."
        )

    if "<html" in lower_body or "<!doctype" in lower_body:
        return (
            f"{prefix} Google returned an HTML page instead of the sync JSON. "
            "Re-copy the updated Apps Script files, deploy a new version of the existing web app, and confirm Access is set to Anyone if available. "
            f"Google page summary: {clean_body or 'HTML response'}"
        )

    return (
        f"{prefix} Re-copy the updated Code.gs and Index.html from Optional Phone Approval, deploy a new version, "
        f"then try again. Google response: {clean_body or 'empty response'}"
    )


def _post_approval_webapp_json(url: str, payload: Dict[str, object], timeout: int = 30) -> Dict[str, object]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(_google_webapp_recovery_message(exc.code, body)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach the Google approval web app: {exc.reason}") from exc

    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(_google_webapp_recovery_message(None, body)) from exc

    if not result.get("ok"):
        raise RuntimeError(str(result.get("error") or result.get("message") or "Google approval sync failed."))
    return result


def verify_approval_webapp(config: Optional[Config] = None) -> Dict[str, object]:
    """Check whether the saved Apps Script URL is running the sync-capable deployment."""
    _ = config
    url = _approval_webapp_url()
    separator = "&" if "?" in url else "?"
    health_url = f"{url}{separator}mode=health"
    try:
        with urllib.request.urlopen(health_url, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": "http_error",
            "summary": _google_webapp_recovery_message(exc.code, body),
            "health_url": health_url,
        }
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "status": "network_error",
            "summary": f"Could not reach the Google approval web app: {exc.reason}",
            "health_url": health_url,
        }

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        lower_body = body.lower()
        if "missing review parameters" in lower_body:
            status = "old_code_running"
            summary = (
                "The saved /exec URL is still running the old approval page code. "
                "Copy the newest Code.gs from Optional Phone Approval, confirm it contains function syncReviewQueue_, "
                "save, then Deploy -> Manage deployments -> pencil icon -> Version -> New version -> Deploy. "
                "The /exec URL can stay the same."
            )
        else:
            status = "not_json"
            summary = _google_webapp_recovery_message(None, body)
        return {
            "ok": False,
            "status": status,
            "summary": summary,
            "health_url": health_url,
            "response_preview": _clean_webapp_body(body),
        }

    ready = bool(payload.get("ok") and payload.get("sync_enabled"))
    return {
        "ok": ready,
        "status": "ready" if ready else "sync_token_missing",
        "summary": "Google approval web app is running the sync-capable deployment."
        if ready
        else (
            "Google approval web app is reachable, but its sync token is not configured. "
            "Click Copy Sync Token, then in Apps Script go to Project Settings -> Script properties, "
            f"add property {SYNC_TOKEN_PROPERTY}, paste the token as the value, and save. "
            "Run Verify Phone App again after saving; no redeploy is required for this property-only fix."
        ),
        "health_url": health_url,
        "webapp": payload,
    }


def _approval_link_from_text(text: str) -> str:
    for token in (text or "").replace("\n", " ").split():
        cleaned = token.strip().strip("<>()[]{}.,")
        if cleaned.startswith("https://script.google.com/"):
            return cleaned
    return ""


def _current_notification_link(config: Config, week: str = "current") -> Dict[str, str]:
    latest = latest_production_test(config)
    notification_path = str(latest.get("notification_text_path") or "").strip()
    if notification_path:
        path = Path(notification_path)
        if not path.is_absolute():
            path = project_root() / path
        if path.exists():
            text = path.read_text(errors="replace")
            return {"notification_text_path": str(path), "approval_link": _approval_link_from_text(text)}

    try:
        draft_id = str(latest.get("draft_id") or "").strip() or _latest_draft_id(config)
        notification = build_notification_package(config, draft_id, week=week)
        return {
            "notification_text_path": notification.text_path,
            "approval_link": _approval_link_from_text(Path(notification.text_path).read_text(errors="replace")),
        }
    except Exception:
        return {"notification_text_path": "", "approval_link": ""}


def sync_review_queue_to_webapp(config: Config, week: str = "current") -> Dict[str, object]:
    """Upload the current review queue to the deployed Apps Script web app."""
    url = _approval_webapp_url()
    sync_token = ensure_approval_sync_token()
    review_queue_path = _latest_review_queue_path(config, week=week)
    validation = validate_review_queue_csv(config, str(review_queue_path))
    if not validation.ok:
        return {
            "ok": False,
            "status": "validation_failed",
            "review_queue_path": str(review_queue_path),
            "validation": asdict(validation),
            "error": "Review queue failed validation before phone sync.",
        }

    result = _post_approval_webapp_json(
        url,
        {
            "mode": "sync_queue",
            "sync_token": sync_token,
            "csv_content": review_queue_path.read_text(),
        },
    )
    link = _current_notification_link(config, week=week)
    build_pilot_checklist(config, write_files=True)
    return {
        "ok": True,
        "status": "synced",
        "summary": "Review queue synced to the Google approval web app. Open the approval link on any device.",
        "review_queue_path": str(review_queue_path),
        "webapp_total_rows": result.get("total_rows", 0),
        "webapp_decision_rows": result.get("decision_rows", 0),
        "sync_token_env_key": SYNC_TOKEN_ENV_KEY,
        **link,
    }


def import_webapp_decisions(config: Config, week: str = "current", build_package: bool = True) -> Dict[str, object]:
    """Download approval decisions from Apps Script and import them locally."""
    url = _approval_webapp_url()
    sync_token = ensure_approval_sync_token()
    result = _post_approval_webapp_json(
        url,
        {
            "mode": "export_decisions",
            "sync_token": sync_token,
        },
    )
    csv_content = str(result.get("csv_content") or "")
    if not csv_content.strip():
        raise RuntimeError("The Google approval web app returned no review queue CSV.")

    imported = import_review_queue_content(config, csv_content)
    manual_package_path = ""
    package_error = ""
    if build_package and int(imported.get("imported", 0) or 0) > 0:
        try:
            manual_package_path = build_latest_manual_package(config, None)
        except Exception as exc:
            package_error = str(exc)

    if int(imported.get("imported", 0) or 0) > 0:
        update_pilot_checklist_item(
            config,
            "iphone_magic_link_tested",
            "done",
            "Phone approval decision imported from the Google web app.",
        )
        update_pilot_checklist_item(
            config,
            "approval_imported",
            "done",
            "Approval decision imported from the Google web app without manual CSV handling.",
        )

    return {
        "ok": True,
        "status": "imported",
        "summary": "Phone decision imported from the Google approval web app.",
        "webapp_total_rows": result.get("total_rows", 0),
        "webapp_decision_rows": result.get("decision_rows", 0),
        "manual_package_path": manual_package_path,
        "package_error": package_error,
        **imported,
    }


def _latest_review_id_for_draft(config: Config, draft_id: str) -> str:
    conn = connect_db(config.storage.sqlite_path)
    try:
        row = conn.execute(
            """
            SELECT approval_tokens.id
            FROM approval_tokens
            LEFT JOIN approvals ON approvals.token_id = approval_tokens.id
            WHERE approval_tokens.draft_id = ?
              AND approvals.id IS NULL
            ORDER BY approval_tokens.created_at DESC
            LIMIT 1
            """,
            (draft_id,),
        ).fetchone()
        return str(row["id"]) if row else ""
    finally:
        conn.close()


def approve_latest_draft_locally(
    config: Config,
    draft_id: Optional[str] = None,
    action: str = "approve_text_only",
    notes: str = "Approved inside the AI LinkedIn Console.",
    build_package: bool = True,
) -> LocalApprovalResult:
    """Record a local human approval without Google Sheets or Apps Script copy/paste."""
    if action not in ALLOWED_APPROVAL_ACTIONS:
        raise ValueError(f"Invalid approval action: {action}")

    selected_draft_id = draft_id or _latest_draft_id(config)
    review_id = _latest_review_id_for_draft(config, selected_draft_id)
    if not review_id:
        create_approval_packet(config, selected_draft_id)
        review_id = _latest_review_id_for_draft(config, selected_draft_id)
    if not review_id:
        raise RuntimeError("No approval review record is available for this draft.")

    conn = connect_db(config.storage.sqlite_path)
    try:
        existing = conn.execute(
            """
            SELECT approvals.id, approvals.action
            FROM approvals
            WHERE approvals.token_id = ?
            """,
            (review_id,),
        ).fetchone()
    finally:
        conn.close()
    if existing:
        if existing["action"] != action:
            raise RuntimeError(
                f"Draft already has approval action {existing['action']}; create a new draft for a different decision."
            )
        approval_id = str(existing["id"])
        status = "already_approved"
    else:
        approval_id = record_approval(config.storage.sqlite_path, review_id, action, notes)
        used_at = datetime.now().isoformat()
        with transaction(config.storage.sqlite_path) as conn:
            conn.execute(
                """
                UPDATE approval_tokens
                SET used_at = ?
                WHERE id = ?
                """,
                (used_at, review_id),
            )
            conn.execute(
                """
                UPDATE approvals
                SET approval_channel = ?
                WHERE id = ?
                """,
                ("local_console", approval_id),
            )
        status = "approved"

    manual_package_path = ""
    if build_package and action in {"approve", "approve_text_only", "approve_text_plus_media", "approve_text_reject_media"}:
        manual_package_path = build_latest_manual_package(config, selected_draft_id)

    checklist = build_pilot_checklist(config, write_files=True)
    return LocalApprovalResult(
        status=status,
        draft_id=selected_draft_id,
        review_id=review_id,
        approval_id=approval_id,
        action=action,
        manual_package_path=manual_package_path,
        checklist_path=checklist.markdown_path,
    )


def _latest_draft_id(config: Config) -> str:
    latest = latest_production_test(config)
    draft_id = str(latest.get("draft_id") or "").strip()
    if draft_id:
        return draft_id
    conn = connect_db(config.storage.sqlite_path)
    try:
        row = conn.execute("SELECT id FROM drafts ORDER BY created_at DESC LIMIT 1").fetchone()
        if not row:
            raise ValueError("No draft found. Build a production test package first.")
        return row["id"]
    finally:
        conn.close()


def _squash_blank_lines(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    output: List[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                output.append("")
            blank = True
        else:
            output.append(line)
            blank = False
    return "\n".join(output).strip() + "\n"


def _without_source_footer(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.strip().lower().startswith("source topic:"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _post_paragraphs(text: str) -> List[str]:
    return [part.strip() for part in text.strip().split("\n\n") if part.strip()]


def _replace_article_section(content: str, heading: str, replacement: str) -> str:
    lines = content.splitlines()
    output: List[str] = []
    index = 0
    replaced = False
    while index < len(lines):
        line = lines[index]
        output.append(line)
        if line.strip() == f"## {heading}":
            output.extend(["", replacement.strip(), ""])
            index += 1
            while index < len(lines) and not lines[index].startswith("## "):
                index += 1
            replaced = True
            continue
        index += 1
    if not replaced:
        output.extend(["", f"## {heading}", "", replacement.strip()])
    return _squash_blank_lines("\n".join(output))


def _apply_article_package_preset_text(text: str, preset: str, fallback: str = "") -> str:
    feed_post = extract_section(text, "Feed Post")
    article_title = extract_section(text, "Article Title").replace("*", "").strip()
    article_body = extract_section(text, "Article Body")
    if preset == "regenerate":
        return _squash_blank_lines(fallback or text)
    if preset == "stronger_hook":
        replacement = _squash_blank_lines(
            f"Most AI strategies fail at the handoff.\n\n{feed_post}"
        )
        return _replace_article_section(text, "Feed Post", replacement)
    if preset in {"shorter", "more_concise"}:
        first = feed_post.splitlines()[0] if feed_post else "AI needs better review moments."
        replacement = _squash_blank_lines(
            f"{first}\n\nThe real question is what must be true before AI output becomes action.\n\nFull article: [PASTE ARTICLE LINK]"
        )
        return _replace_article_section(text, "Feed Post", replacement)
    if preset in {"business_friendly", "plain"}:
        replacement = _squash_blank_lines(
            f"{feed_post}\n\nPlain-English frame: this is not a model story. It is a workflow ownership story."
        )
        return _replace_article_section(text, "Feed Post", replacement)
    if preset == "deeper_detail":
        addition = (
            "\n\n### The executive test\n\n"
            "A simple executive test is to ask whether the workflow makes its evidence visible. "
            "If a leader cannot see the source, the assumption, the recommended action, and the approval owner, "
            "the workflow is not ready for scaled use."
        )
        return _replace_article_section(text, "Article Body", article_body + addition)
    if preset == "less_detail":
        paragraphs = _post_paragraphs(article_body)
        trimmed = "\n\n".join(paragraphs[:10])
        return _replace_article_section(text, "Article Body", trimmed)
    if preset == "longer":
        addition = (
            "\n\n### Why this matters now\n\n"
            "The pressure to move quickly is real. But speed without review design creates a brittle kind of confidence: "
            "work appears to move faster while accountability gets harder to find. The better path is to make the control layer visible before the workflow scales."
        )
        return _replace_article_section(text, "Article Body", article_body + addition)
    if preset == "sharper_tone":
        replacement = _squash_blank_lines(
            f"{feed_post}\n\nMy take: AI governance that cannot be found inside the workflow is mostly theater."
        )
        return _replace_article_section(text, "Feed Post", replacement)
    if preset == "warmer":
        replacement = _squash_blank_lines(
            f"{feed_post}\n\nThe point is not to slow teams down. It is to make good judgment easier to repeat."
        )
        return _replace_article_section(text, "Feed Post", replacement)
    if preset == "executive":
        replacement = _squash_blank_lines(
            f"Executive takeaway: {article_title or 'AI needs better-designed approval moments'}.\n\n"
            "Before scaling AI, decide what the system can do, what evidence it must show, and who approves the output.\n\n"
            "Full article: [PASTE ARTICLE LINK]"
        )
        return _replace_article_section(text, "Feed Post", replacement)
    if preset == "safer":
        safer = article_body.replace("will ", "may ").replace("must ", "should ")
        if "This is a signal, not a final conclusion." not in safer:
            safer += "\n\nThis is a signal, not a final conclusion."
        return _replace_article_section(text, "Article Body", safer)
    if preset == "final_polish":
        return _squash_blank_lines(text)
    return text


def _technical_summary_to_business(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ["icu", "clinical", "patient", "health", "medical"]):
        return (
            "The business point is not the clinical detail. It is the approval pattern: "
            "when AI touches high-stakes decisions, teams need clear ownership, source checks, "
            "and a human review step before the output becomes action."
        )
    if any(word in lower for word in ["network", "6g", "infrastructure", "cloud", "platform"]):
        return (
            "The business point is control. As AI gets embedded into infrastructure, leaders need "
            "to know which parts of the workflow they can inspect, change, and govern."
        )
    if any(word in lower for word in ["benchmark", "evaluation", "eval", "test"]):
        return (
            "The business point is readiness. A benchmark can be useful, but it is not the same as "
            "knowing whether a workflow is safe, useful, and accountable in the real organization."
        )
    if any(word in lower for word in ["agent", "agentic", "autonomous", "automation"]):
        return (
            "The business point is delegation. The more AI can act across tools, the more important "
            "it becomes to decide where autonomy ends and human judgment begins."
        )
    return (
        "The business point is simple: the useful AI conversation is not only what the technology can do. "
        "It is which work habits, approval steps, and decision rights should change because of it."
    )


def _apply_draft_preset_text(text: str, preset: str, fallback: str = "") -> str:
    base = text.strip()
    if is_article_package(base):
        return _apply_article_package_preset_text(base, preset, fallback=fallback)

    if preset == "regenerate":
        return _squash_blank_lines(fallback or base)

    if preset == "longer":
        body = _without_source_footer(base)
        business_angle = _technical_summary_to_business(body)
        addition = (
            f"{business_angle}\n\n"
            "That is why I would not treat this as a tools conversation first. I would treat it as "
            "an operating-model conversation: what should AI be allowed to do, what evidence should "
            "it show, and what needs a person to approve before anything moves forward?"
        )
        return _squash_blank_lines(body + "\n\n" + addition)

    if preset == "deeper_detail":
        body = _without_source_footer(base)
        addition = (
            "A useful way to make this practical is to separate the workflow into three layers:\n\n"
            "1. The AI-assisted step: where the system can summarize, compare, draft, recommend, or route work.\n\n"
            "2. The evidence step: where the team checks sources, assumptions, and what the model may have missed.\n\n"
            "3. The decision step: where a person approves the final action, especially if the work affects customers, money, reputation, or policy.\n\n"
            "That separation keeps the conversation grounded. It lets teams use AI without pretending that every AI output is ready to become a decision."
        )
        return _squash_blank_lines(body + "\n\n" + addition)

    if preset == "shorter":
        paragraphs = _post_paragraphs(base)
        kept = [
            part
            for part in paragraphs
            if "trust tier" not in part.lower()
            and "current recommendation" not in part.lower()
            and not part.lower().startswith("source topic:")
        ]
        return _squash_blank_lines("\n\n".join(kept[:4]))

    if preset == "more_concise":
        paragraphs = _post_paragraphs(_without_source_footer(base))
        hook = paragraphs[0] if paragraphs else "The useful AI question is not whether the technology is impressive."
        business_angle = _technical_summary_to_business(base)
        close = "Before adopting it, I would ask: what workflow should change, and where does human approval still matter?"
        return _squash_blank_lines("\n\n".join([hook, business_angle, close]))

    if preset == "less_detail":
        paragraphs = _post_paragraphs(_without_source_footer(base))
        hook = paragraphs[0] if paragraphs else "This AI signal is worth watching."
        business_angle = _technical_summary_to_business(base)
        question = (
            "The practical question for leaders is not the technical mechanism. It is whether the team has "
            "clear rules for when AI can help, when it must show evidence, and when a person must approve."
        )
        return _squash_blank_lines("\n\n".join([hook, business_angle, question]))

    if preset == "warmer":
        body = _without_source_footer(base)
        body = body.replace(
            "This caught my eye because it points to a practical AI question leaders are already facing.",
            "I keep coming back to this because it is practical, not flashy.",
        )
        if body == base:
            body = "I keep coming back to this because it is practical, not flashy.\n\n" + body
        return _squash_blank_lines(body)

    if preset == "business_friendly":
        body = _without_source_footer(base)
        business_angle = _technical_summary_to_business(body)
        return _squash_blank_lines(
            "Here is the plain-English version.\n\n"
            + business_angle
            + "\n\nFor a business team, the next step is not to debate the model architecture. "
            "It is to pick one workflow, define what AI is allowed to do, and decide what a human must approve."
        )

    if preset == "sharper_tone":
        body = _without_source_footer(base)
        close = (
            "My take: AI adoption will stall when teams keep treating governance as a policy document. "
            "It has to become a workflow design choice."
        )
        return _squash_blank_lines(body + "\n\n" + close)

    if preset == "executive":
        body = _without_source_footer(base)
        takeaway = (
            "My executive takeaway: the useful question is not whether the technology is impressive. "
            "It is what decision, control, or operating habit should change if this pattern keeps showing up."
        )
        return _squash_blank_lines(body + "\n\n" + takeaway)

    if preset == "safer":
        replacements = {
            " will ": " may ",
            " proves ": " suggests ",
            " proof ": " signal ",
            " definitely ": " likely ",
            " always ": " often ",
            " never ": " rarely ",
        }
        body = f" {base} "
        for source, target in replacements.items():
            body = body.replace(source, target)
        body = body.strip()
        if "This is worth treating as a signal, not a conclusion." not in body:
            body += "\n\nThis is worth treating as a signal, not a conclusion."
        return _squash_blank_lines(body)

    if preset == "plain":
        body = _without_source_footer(base)
        replacements = {
            "evaluate, govern, and apply AI in real work": "decide where AI belongs, who owns it, and how to check it",
            "operating habit": "work habit",
            "source context": "source",
            "political risk": "public risk",
            "draft readiness": "draft score",
        }
        for source, target in replacements.items():
            body = body.replace(source, target)
        return _squash_blank_lines(body)

    if preset == "stronger_hook":
        paragraphs = [part.strip() for part in base.split("\n\n") if part.strip()]
        hook = "The most useful AI stories are the ones that change how a team actually works."
        if paragraphs:
            paragraphs[0] = hook
        else:
            paragraphs = [hook]
        return _squash_blank_lines("\n\n".join(paragraphs))

    if preset == "final_polish":
        return _squash_blank_lines(_linkedin_ready_copy(None, base))

    raise ValueError(f"Unknown draft edit preset: {preset}")


def _draft_revision_output_dir(config: Config, latest: Dict[str, object]) -> Path:
    if latest.get("output_dir"):
        output_dir = Path(str(latest["output_dir"]))
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = resolve_project_path(config.storage.exports_dir) / "draft_revisions" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _update_latest_package_after_draft_revision(
    config: Config,
    latest: Dict[str, object],
    result: DraftRevisionResult,
) -> None:
    if not latest:
        return
    latest_path = resolve_project_path(config.storage.exports_dir) / "production_tests" / "latest.json"
    latest["draft_id"] = result.draft_id
    latest["draft_path"] = result.draft_path
    latest["approval_packet_path"] = result.approval_packet_path
    if result.notification_text_path:
        latest["notification_text_path"] = result.notification_text_path
    if result.review_queue_path:
        latest["review_queue_path"] = result.review_queue_path
    latest["status"] = "draft_revised_needs_approval"
    latest["next_actions"] = [
        "Review the revised draft shown in the console.",
        "Use another edit button if needed.",
        "Click Approve Draft only when this exact version is ready.",
        "Manual LinkedIn posting still happens after approval.",
    ]
    latest_path.write_text(json.dumps(latest, indent=2))


def apply_draft_preset(
    config: Config,
    preset: str,
    draft_id: Optional[str] = None,
    week: str = "current",
) -> DraftRevisionResult:
    """Create a new draft version from a click-only editing preset."""
    if preset not in DRAFT_EDIT_PRESETS:
        raise ValueError(f"Unknown draft edit preset: {preset}")

    latest = latest_production_test(config)
    previous_draft_id = draft_id or _latest_draft_id(config)
    row = _draft_row(config, previous_draft_id)
    if not row:
        raise ValueError(f"Draft not found: {previous_draft_id}")

    fallback = generate_draft_from_topic(config, str(row["topic_id"])) if preset == "regenerate" else ""
    if preset == "final_polish":
        revised_text = _linkedin_ready_copy(row, str(row["content"] or ""))
    else:
        revised_text = _apply_draft_preset_text(str(row["content"] or ""), preset, fallback=fallback)
    if revised_text.strip() == str(row["content"] or "").strip():
        revised_text = _squash_blank_lines(
            revised_text
            + "\n\nSmall edit: keep this practical, specific, and easy to read before approval."
        )

    new_draft_id = save_draft(config.storage.sqlite_path, str(row["topic_id"]), revised_text)
    output_dir = _draft_revision_output_dir(config, latest)
    draft_path = output_dir / f"{new_draft_id}_draft.md"
    draft_path.write_text(revised_text)

    approval_packet_path = ""
    notification_text_path = ""
    review_queue_path = ""
    try:
        approval_packet_path, _ = create_approval_packet(config, new_draft_id, week=week)
        notification = build_notification_package(config, new_draft_id, week=week)
        notification_text_path = notification.text_path
        review_queue_path = notification.review_queue_path
    except Exception as exc:
        approval_packet_path = approval_packet_path or ""
        message = f"Draft revised, but approval packet refresh needs attention: {exc}"
    else:
        message = "Draft revised and approval files refreshed. Approval is required for this new version."

    result = DraftRevisionResult(
        status="revised",
        preset=preset,
        label=DRAFT_EDIT_PRESETS[preset]["label"],
        previous_draft_id=previous_draft_id,
        draft_id=new_draft_id,
        topic_id=str(row["topic_id"]),
        draft_path=str(draft_path),
        approval_packet_path=approval_packet_path,
        notification_text_path=notification_text_path,
        review_queue_path=review_queue_path,
        message=message,
    )
    _update_latest_package_after_draft_revision(config, latest, result)
    build_pilot_checklist(config, write_files=True)
    return result


def build_next_topic_package(config: Config, week: str = "current") -> Dict[str, object]:
    """Build a package for the next ranked topic so the operator can avoid a bad fit."""
    from ai_linkedin_automation.scoring.scoring import top_topics
    from ai_linkedin_automation.pilot.production_test import build_production_test_package

    latest = latest_production_test(config)
    current_topic_id = str(latest.get("selected_topic_id") or "")
    candidates = top_topics(config, limit=20)
    if not candidates:
        package = build_production_test_package(config, week=week)
        reset_source_review_for_new_candidate(config, "New draft built; source review is required again.")
        return asdict(package)

    next_topic = candidates[0]
    for index, candidate in enumerate(candidates):
        if candidate.get("id") == current_topic_id:
            next_topic = candidates[(index + 1) % len(candidates)]
            break

    package = build_production_test_package(config, week=week, topic_id=str(next_topic["id"]))
    reset_source_review_for_new_candidate(config, "Different topic selected; source review is required again.")
    return asdict(package)


TOPIC_CATEGORY_DEFS = [
    (
        "ready",
        "Ready To Draft",
        "Higher-confidence candidates that are closest to post-ready.",
        {"draft", "governance", "enterprise", "leaders", "operations", "strategy"},
    ),
    (
        "agentic",
        "Agentic AI",
        "Autonomous workflows, multi-agent systems, tool use, and human gates.",
        {"agent", "agentic", "autonomous", "workflow", "tool", "multi"},
    ),
    (
        "governance",
        "AI Governance",
        "Risk, policy, approvals, controls, and operating model topics.",
        {"governance", "risk", "policy", "safety", "approval", "control", "secure"},
    ),
    (
        "enterprise",
        "Enterprise AI",
        "Business operations, productivity, architecture, and leadership adoption.",
        {"enterprise", "business", "leader", "operation", "productivity", "architecture"},
    ),
    (
        "hidden_gems",
        "Hidden Gems",
        "Less obvious topics with a useful executive angle.",
        {"benchmark", "evaluation", "retrieval", "reasoning", "data", "quality"},
    ),
    (
        "research_watch",
        "Research Watch",
        "Early research worth watching, but likely needing human source review.",
        {"arxiv", "paper", "model", "training", "reasoning", "benchmark"},
    ),
]


STARTER_TOPIC_SUGGESTIONS = {
    "agentic": [
        (
            "Agentic workflows with human approval gates",
            "A practical post on where autonomous AI agents should act alone and where people should approve the work.",
        ),
        (
            "Why agentic AI needs audit trails, not just better prompts",
            "A leadership angle on traceability, approvals, and accountability in multi-step AI workflows.",
        ),
    ],
    "governance": [
        (
            "AI governance that business teams can actually follow",
            "A non-technical post about turning policy into simple operating habits for everyday teams.",
        ),
        (
            "The approval moments that matter most in enterprise AI",
            "A practical way to decide which AI actions need human review before they affect customers, money, or reputation.",
        ),
    ],
    "enterprise": [
        (
            "The quiet productivity gain from redesigning work around AI",
            "A business-user-friendly post about changing the workflow, not just adding another tool.",
        ),
        (
            "How leaders can spot AI work that is ready for production",
            "A checklist-style topic on quality, ownership, source support, and operational readiness.",
        ),
    ],
    "hidden_gems": [
        (
            "The hidden cost of AI pilots that never become workflows",
            "A post about why organizations need repeatable approval and measurement loops, not isolated demos.",
        ),
        (
            "What AI teams can learn from boring operational controls",
            "A hidden-gem leadership angle on logs, handoffs, checklists, and exception handling.",
        ),
    ],
    "research_watch": [
        (
            "What new AI research means after the demo fades",
            "A plain-English research-watch topic that turns technical progress into a leadership question.",
        ),
        (
            "The difference between an AI benchmark win and business readiness",
            "A practical post on why evaluation results still need context, workflow fit, and human judgment.",
        ),
    ],
}


DIVERSE_REFRESH_TOPIC_SEEDS = [
    {
        "source_id": "refresh_mit_sloan_ai",
        "source_name": "MIT Sloan Management Review",
        "trust_tier": "high_trust",
        "url": "https://sloanreview.mit.edu/tag/artificial-intelligence/",
        "title": "Why AI projects need workflow redesign, not just better tools",
        "summary": "A business-friendly angle on why AI value often comes from changing handoffs, approvals, and decision rights rather than adding another model to an existing process.",
        "category": "enterprise",
    },
    {
        "source_id": "refresh_hbr_ai",
        "source_name": "Harvard Business Review",
        "trust_tier": "high_trust",
        "url": "https://hbr.org/topic/subject/artificial-intelligence-and-machine-learning",
        "title": "The manager's role when AI starts drafting, summarizing, and recommending",
        "summary": "A practical leadership topic about how managers should review AI-assisted work, set quality expectations, and avoid turning every output into a trust exercise.",
        "category": "enterprise",
    },
    {
        "source_id": "refresh_mckinsey_ai",
        "source_name": "McKinsey QuantumBlack",
        "trust_tier": "high_trust",
        "url": "https://www.mckinsey.com/capabilities/quantumblack/our-insights",
        "title": "The hidden operating model behind successful generative AI adoption",
        "summary": "A post for business readers on ownership, measurement, workflow fit, and why pilots need a path into repeatable work.",
        "category": "enterprise",
    },
    {
        "source_id": "refresh_nist_ai_rmf",
        "source_name": "NIST AI Risk Management Framework",
        "trust_tier": "primary",
        "url": "https://www.nist.gov/itl/ai-risk-management-framework",
        "title": "AI governance works best when it becomes a checklist people can use",
        "summary": "A non-technical governance topic about translating risk principles into simple review steps for real business workflows.",
        "category": "governance",
    },
    {
        "source_id": "refresh_stanford_hai_index",
        "source_name": "Stanford HAI",
        "trust_tier": "high_trust",
        "url": "https://hai.stanford.edu/ai-index",
        "title": "What AI adoption metrics miss about everyday business readiness",
        "summary": "A business-reader topic on why adoption numbers matter less than whether teams have clear use cases, source checks, and human approval habits.",
        "category": "hidden_gems",
    },
    {
        "source_id": "refresh_pew_ai",
        "source_name": "Pew Research Center",
        "trust_tier": "high_trust",
        "url": "https://www.pewresearch.org/topic/internet-technology/artificial-intelligence/",
        "title": "Why employee trust matters as much as AI capability",
        "summary": "A post about trust, transparency, and why business users need to understand where AI is helping, where it is guessing, and who is accountable.",
        "category": "enterprise",
    },
    {
        "source_id": "refresh_brookings_ai",
        "source_name": "Brookings Institution",
        "trust_tier": "high_trust",
        "url": "https://www.brookings.edu/topics/artificial-intelligence/",
        "title": "The public-risk questions business leaders should ask before AI rollout",
        "summary": "A grounded governance topic on reputation, fairness, oversight, and the gap between useful automation and responsible deployment.",
        "category": "governance",
    },
    {
        "source_id": "refresh_microsoft_worklab",
        "source_name": "Microsoft WorkLab",
        "trust_tier": "primary",
        "url": "https://www.microsoft.com/en-us/worklab/",
        "title": "The AI productivity question leaders should ask their teams",
        "summary": "A business-user post about moving from individual productivity hacks to shared team workflows that make work easier to review and reuse.",
        "category": "enterprise",
    },
    {
        "source_id": "refresh_google_cloud_ai",
        "source_name": "Google Cloud AI Blog",
        "trust_tier": "primary",
        "url": "https://cloud.google.com/blog/products/ai-machine-learning",
        "title": "Why AI agents need permissions, logs, and approval gates",
        "summary": "A practical agentic AI topic for non-engineers: before agents act across business systems, teams need clear permissions and visible handoffs.",
        "category": "agentic",
    },
    {
        "source_id": "refresh_mit_news_ai",
        "source_name": "MIT News",
        "trust_tier": "high_trust",
        "url": "https://news.mit.edu/topic/artificial-intelligence2",
        "title": "The useful AI story is often the boring workflow change",
        "summary": "A plain-English topic on how research and product advances become valuable only when the surrounding business process changes too.",
        "category": "hidden_gems",
    },
    {
        "source_id": "refresh_wef_ai",
        "source_name": "World Economic Forum",
        "trust_tier": "high_trust",
        "url": "https://www.weforum.org/topics/artificial-intelligence/",
        "title": "How AI changes the skills conversation for business teams",
        "summary": "A post on training, judgment, and the new habit of reviewing AI-assisted work instead of treating AI as a separate technical specialty.",
        "category": "enterprise",
    },
    {
        "source_id": "refresh_bcg_ai",
        "source_name": "Boston Consulting Group",
        "trust_tier": "high_trust",
        "url": "https://www.bcg.com/capabilities/artificial-intelligence",
        "title": "Why AI scale depends on decisions leaders make before the model is chosen",
        "summary": "A leadership topic about sponsorship, workflow ownership, measurement, risk, and the cost of letting every team invent its own AI process.",
        "category": "enterprise",
    },
    {
        "source_id": "refresh_venturebeat_ai",
        "source_name": "VentureBeat AI",
        "trust_tier": "high_trust",
        "url": "https://venturebeat.com/category/ai/",
        "title": "What business readers should look for in AI product announcements",
        "summary": "A media-literacy topic about separating useful workflow implications from demo hype, feature lists, and vendor scorekeeping.",
        "category": "hidden_gems",
    },
    {
        "source_id": "refresh_the_verge_ai",
        "source_name": "The Verge AI",
        "trust_tier": "high_trust",
        "url": "https://www.theverge.com/ai-artificial-intelligence",
        "title": "Why consumer AI habits eventually show up inside companies",
        "summary": "A relatable post about how everyday AI behavior changes expectations for internal tools, support processes, and knowledge work.",
        "category": "enterprise",
    },
]


def _topic_card(topic: Dict[str, object], category_key: str) -> Dict[str, object]:
    return {
        "id": topic.get("id", ""),
        "title": topic.get("title", ""),
        "summary": _clean_external_summary(str(topic.get("summary") or ""), max_chars=240),
        "query": topic.get("query", topic.get("title", "")),
        "recommendation": topic.get("recommendation", ""),
        "political_risk": topic.get("political_risk", ""),
        "draft_readiness": topic.get("draft_readiness", 0),
        "trust_tier": topic.get("trust_tier", "unknown"),
        "source_name": topic.get("source_name", ""),
        "source_url": topic.get("source_url", ""),
        "category": category_key,
    }


def _starter_topic(title: str, summary: str, category_key: str) -> Dict[str, object]:
    return {
        "id": "",
        "title": title,
        "summary": summary,
        "query": title,
        "recommendation": "starter_prompt",
        "political_risk": "low",
        "draft_readiness": 2,
        "trust_tier": "needs_verification",
        "source_name": "Starter idea",
        "source_url": "",
        "category": category_key,
    }


def _with_starter_topics(categories: List[TopicBoardCategory], minimum: int = 12) -> List[TopicBoardCategory]:
    total = sum(len(category.topics) for category in categories)
    if total >= minimum:
        return categories

    by_key = {category.key: category for category in categories}
    seen_titles = {
        str(topic.get("title") or "").strip().lower()
        for category in categories
        for topic in category.topics
    }
    descriptions = {key: (label, description) for key, label, description, _ in TOPIC_CATEGORY_DEFS}
    for key, suggestions in STARTER_TOPIC_SUGGESTIONS.items():
        if total >= minimum:
            break
        if key not in by_key:
            label, description = descriptions[key]
            category = TopicBoardCategory(key=key, label=label, description=description, topics=[])
            categories.append(category)
            by_key[key] = category
        category = by_key[key]
        for title, summary in suggestions:
            if total >= minimum:
                break
            normalized = title.strip().lower()
            if normalized in seen_titles:
                continue
            category.topics.append(_starter_topic(title, summary, key))
            seen_titles.add(normalized)
            total += 1
    return categories


def _refresh_state_dir(config: Config) -> Path:
    path = resolve_project_path(config.storage.exports_dir) / "topic_refreshes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _latest_refresh_path(config: Config) -> Path:
    return _refresh_state_dir(config) / "latest_refresh.json"


def _pilot_checklist_state_path(config: Config) -> Path:
    return resolve_project_path(config.storage.exports_dir) / "pilot" / "pilot_checklist_state.json"


def _read_pilot_checklist_state_json(config: Config) -> str:
    path = _pilot_checklist_state_path(config)
    return path.read_text() if path.exists() else ""


def _restore_pilot_checklist_state_json(config: Config, state_json: str) -> None:
    path = _pilot_checklist_state_path(config)
    if state_json:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(state_json)
    elif path.exists():
        path.unlink()
    build_pilot_checklist(config, write_files=True)


def reset_source_review_for_new_candidate(config: Config, notes: str = "New topic selected; source review is required again.") -> None:
    """Reset the human source-review gate without touching other manual checklist items."""
    path = _pilot_checklist_state_path(config)
    try:
        payload = json.loads(path.read_text()) if path.exists() else {}
    except json.JSONDecodeError:
        payload = {}
    items = payload.get("items", {})
    if not isinstance(items, dict):
        items = {}
    now = datetime.now().isoformat(timespec="seconds")
    items["weekly_candidates_reviewed"] = {
        "status": "pending",
        "notes": notes,
        "updated_at": now,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"updated_at": now, "items": items}, indent=2))
    build_pilot_checklist(config, write_files=True)


def _current_week_label(week: str) -> str:
    if week != "current":
        return week
    year, week_num, _ = datetime.now().isocalendar()
    return f"{year}-W{week_num:02d}"


def _topic_refresh_state(config: Config) -> Dict[str, object]:
    path = _latest_refresh_path(config)
    if not path.exists():
        return {"available": False}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"available": False}
    return {
        "available": bool(data.get("active")),
        "snapshot_id": data.get("snapshot_id", ""),
        "refreshed_at": data.get("created_at", ""),
        "hidden_topic_count": len(data.get("topic_statuses", {})),
        "seeded_topic_count": len(data.get("seeded_topic_ids", [])),
    }


def _clear_latest_package_for_refresh(
    config: Config,
    snapshot_id: str,
    latest_text: str,
    seeded_topic_ids: List[str],
) -> None:
    latest_path = resolve_project_path(config.storage.exports_dir) / "production_tests" / "latest.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(
        json.dumps(
            {
                "status": "topic_refresh_ready",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "snapshot_id": snapshot_id,
                "selected_topic_id": "",
                "selected_topic_title": "",
                "draft_id": "",
                "previous_package_saved": bool(latest_text),
                "seeded_topic_ids": seeded_topic_ids,
                "next_actions": [
                    "Pick one of the refreshed topic cards.",
                    "Or use Undo Refresh to restore the previous build.",
                    "The old topic board is hidden so refreshed suggestions do not repeat it.",
                ],
            },
            indent=2,
        )
    )


def _seed_diverse_refresh_topics(
    config: Config,
    week: str,
    snapshot_id: str,
    avoid_titles: set[str],
    max_count: int = 12,
) -> List[str]:
    now = datetime.now().isoformat(timespec="seconds")
    seeded_topic_ids: List[str] = []
    selected: List[Dict[str, str]] = []
    seen_titles = {title.strip().lower() for title in avoid_titles}

    def add_seed(item: Dict[str, str], title: str, summary: str) -> None:
        if len(selected) >= max_count:
            return
        normalized = title.strip().lower()
        if not normalized or normalized in seen_titles:
            return
        selected.append({**item, "title": title, "summary": summary})
        seen_titles.add(normalized)

    for item in DIVERSE_REFRESH_TOPIC_SEEDS:
        add_seed(item, str(item["title"]), str(item["summary"]))

    # Repeated full refreshes can exhaust the base seed titles because the
    # previous board is intentionally hidden. Keep the replacement board
    # selectable by creating fresh business angles from the same trusted sources.
    variant_prefixes = [
        "Practical angle",
        "Leadership angle",
        "Workflow angle",
        f"Fresh angle {snapshot_id}",
    ]
    for prefix in variant_prefixes:
        if len(selected) >= max_count:
            break
        for item in DIVERSE_REFRESH_TOPIC_SEEDS:
            title = f"{prefix}: {item['title']}"
            summary = (
                f"{item['summary']} This refreshed angle keeps the post focused on what "
                "leaders can inspect, decide, and approve in real workflows."
            )
            add_seed(item, title, summary)
            if len(selected) >= max_count:
                break

    with transaction(config.storage.sqlite_path) as conn:
        for item in selected:
            source_id = str(item["source_id"])
            title = str(item["title"])
            summary = str(item["summary"])
            topic_id = stable_id("topic_refresh", snapshot_id, title)
            finding_id = stable_id("finding_refresh", snapshot_id, title)
            content_hash = hashlib.sha256(f"{snapshot_id}|{title}|{summary}".encode()).hexdigest()
            conn.execute(
                """
                INSERT OR IGNORE INTO sources (
                    id, name, type, source_type, trust_tier, url, is_active,
                    recurring_enabled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    item["source_name"],
                    "manual",
                    "curated_public_web",
                    item["trust_tier"],
                    item["url"],
                    1,
                    0,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO findings (
                    id, source_id, url, title, summary, published_at,
                    content_hash, raw_content, raw_excerpt, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding_id,
                    source_id,
                    item["url"],
                    title,
                    summary,
                    now,
                    content_hash,
                    f"{title}\n\n{summary}",
                    summary[:500],
                    "new",
                    now,
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO topics (
                    id, week_id, title, summary, plain_english_summary,
                    hidden_gem_angle, executive_relevance, hidden_gem_value,
                    technical_signal, source_credibility, oracle_safe_fit,
                    draft_readiness, weighted_score, political_risk,
                    recommendation, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    topic_id,
                    week,
                    title,
                    summary,
                    summary,
                    "Business-user friendly angle from a high-trust public source.",
                    5,
                    4,
                    3,
                    4 if item["trust_tier"] == "high_trust" else 5,
                    4,
                    4,
                    86.0,
                    "low",
                    "draft_now",
                    "candidate",
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO topic_findings (topic_id, finding_id, relationship)
                VALUES (?, ?, ?)
                """,
                (topic_id, finding_id, "refresh_seed"),
            )
            seeded_topic_ids.append(topic_id)
    return seeded_topic_ids


def full_refresh_topics(config: Config, week: str = "current") -> Dict[str, object]:
    """Hide the current weekly board/build and seed a new diverse business-friendly board."""
    load_sources_from_config(config)
    snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    resolved_week = _current_week_label(week)
    latest_path = resolve_project_path(config.storage.exports_dir) / "production_tests" / "latest.json"
    latest_text = latest_path.read_text() if latest_path.exists() else ""
    checklist_state_json = _read_pilot_checklist_state_json(config)

    with transaction(config.storage.sqlite_path) as conn:
        rows = conn.execute(
            """
            SELECT id, status, title
            FROM topics
            WHERE COALESCE(status, 'candidate') NOT IN ('replaced_by_refresh', 'undone_refresh')
              AND recommendation != 'reject'
            """
        ).fetchall()
        topic_statuses = {row["id"]: row["status"] or "candidate" for row in rows}
        avoid_titles = {str(row["title"] or "").strip().lower() for row in rows}
        if topic_statuses:
            conn.executemany(
                "UPDATE topics SET status = 'replaced_by_refresh', updated_at = datetime('now') WHERE id = ?",
                [(topic_id,) for topic_id in topic_statuses],
            )

    seeded_topic_ids = _seed_diverse_refresh_topics(
        config,
        resolved_week,
        snapshot_id,
        avoid_titles,
    )
    _clear_latest_package_for_refresh(config, snapshot_id, latest_text, seeded_topic_ids)

    snapshot = {
        "active": True,
        "snapshot_id": snapshot_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "week": resolved_week,
        "latest_package_json": latest_text,
        "pilot_checklist_state_json": checklist_state_json,
        "topic_statuses": topic_statuses,
        "seeded_topic_ids": seeded_topic_ids,
    }
    snapshot_path = _refresh_state_dir(config) / f"{snapshot_id}.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2))
    _latest_refresh_path(config).write_text(json.dumps(snapshot, indent=2))
    reset_source_review_for_new_candidate(
        config,
        "Topic board was fully refreshed; review the new selected source before approval.",
    )
    return {
        "status": "refreshed",
        "snapshot_id": snapshot_id,
        "hidden_topic_count": len(topic_statuses),
        "seeded_topic_count": len(seeded_topic_ids),
        "snapshot_path": str(snapshot_path),
        "summary": "Current board hidden and a diverse replacement board is ready. Undo is available.",
    }


def undo_full_refresh_topics(config: Config) -> Dict[str, object]:
    """Restore the board/build hidden by the last full refresh."""
    path = _latest_refresh_path(config)
    if not path.exists():
        raise ValueError("There is no topic refresh to undo.")
    snapshot = json.loads(path.read_text())
    topic_statuses = snapshot.get("topic_statuses", {})
    seeded_topic_ids = snapshot.get("seeded_topic_ids", [])
    with transaction(config.storage.sqlite_path) as conn:
        for topic_id, status in topic_statuses.items():
            conn.execute(
                "UPDATE topics SET status = ?, updated_at = datetime('now') WHERE id = ?",
                (status or "candidate", topic_id),
            )
        if seeded_topic_ids:
            conn.executemany(
                "UPDATE topics SET status = 'undone_refresh', updated_at = datetime('now') WHERE id = ?",
                [(topic_id,) for topic_id in seeded_topic_ids],
            )
    latest_path = resolve_project_path(config.storage.exports_dir) / "production_tests" / "latest.json"
    latest_text = snapshot.get("latest_package_json", "")
    if latest_text:
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path.write_text(latest_text)
    elif latest_path.exists():
        latest_path.unlink()
    if "pilot_checklist_state_json" in snapshot:
        _restore_pilot_checklist_state_json(config, str(snapshot.get("pilot_checklist_state_json") or ""))
    snapshot["active"] = False
    snapshot["undone_at"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(snapshot, indent=2))
    return {
        "status": "undone",
        "snapshot_id": snapshot.get("snapshot_id", ""),
        "restored_topic_count": len(topic_statuses),
        "hidden_seeded_topic_count": len(seeded_topic_ids),
        "summary": "Previous topic board and build restored.",
    }


def _category_score(topic: Dict[str, object], keywords: set[str], key: str) -> int:
    text = " ".join(
        str(topic.get(field) or "")
        for field in ["title", "summary", "source_name", "recommendation"]
    ).lower()
    tokens = tokenize(text)
    score = len(tokens & keywords)
    if key == "ready" and topic.get("recommendation") == "draft_now":
        score += 4
    if key == "hidden_gems" and int(topic.get("hidden_gem_value") or 0) >= 4:
        score += 3
    if key == "research_watch" and str(topic.get("source_name") or "").lower().find("arxiv") >= 0:
        score += 2
    return score


def topic_board(config: Config, limit: int = 48) -> Dict[str, object]:
    """Return a grouped topic board for the Start page."""
    from ai_linkedin_automation.scoring.scoring import top_topics

    candidates = top_topics(config, limit=limit)
    categories: List[TopicBoardCategory] = []
    used: set[str] = set()
    for key, label, description, keywords in TOPIC_CATEGORY_DEFS:
        scored = sorted(
            candidates,
            key=lambda topic: (
                _category_score(topic, keywords, key),
                int(topic.get("draft_readiness") or 0),
                int(topic.get("executive_relevance") or 0),
                int(topic.get("hidden_gem_value") or 0),
            ),
            reverse=True,
        )
        topics = []
        for topic in scored:
            topic_id = str(topic.get("id") or "")
            if not topic_id or topic_id in used:
                continue
            if _category_score(topic, keywords, key) <= 0 and len(topics) >= 2:
                continue
            topics.append(_topic_card(topic, key))
            used.add(topic_id)
            if len(topics) >= 4:
                break
        if topics:
            categories.append(TopicBoardCategory(key=key, label=label, description=description, topics=topics))

    uncategorized = [
        _topic_card(topic, "more")
        for topic in candidates
        if str(topic.get("id") or "") not in used
    ][:6]
    if uncategorized:
        categories.append(
            TopicBoardCategory(
                key="more",
                label="More Options",
                description="Additional ranked topics from this week's scan.",
                topics=uncategorized,
            )
        )
    categories = _with_starter_topics(categories)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "category_count": len(categories),
        "topic_count": sum(len(category.topics) for category in categories),
        "refresh_state": _topic_refresh_state(config),
        "categories": [asdict(category) for category in categories],
    }


def _word_limited_query(query: str, max_words: int = 50) -> str:
    words = [word.strip() for word in (query or "").split() if word.strip()]
    return " ".join(words[:max_words]).strip()


def _best_matching_topic(config: Config, query: str) -> Optional[str]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return None
    conn = connect_db(config.storage.sqlite_path)
    try:
        rows = conn.execute(
            """
            SELECT
                topics.id,
                topics.title,
                topics.summary,
                findings.title AS finding_title,
                findings.summary AS finding_summary
            FROM topics
            LEFT JOIN topic_findings ON topic_findings.topic_id = topics.id
            LEFT JOIN findings ON findings.id = topic_findings.finding_id
            WHERE COALESCE(topics.status, 'candidate') NOT IN ('replaced_by_refresh', 'undone_refresh')
            LIMIT 1000
            """
        ).fetchall()
    finally:
        conn.close()

    best_id = None
    best_score = 0
    for row in rows:
        text = " ".join(str(row[field] or "") for field in row.keys() if field != "id")
        overlap = len(query_tokens & tokenize(text))
        if overlap > best_score:
            best_score = overlap
            best_id = row["id"]
    return best_id if best_score >= max(1, min(3, len(query_tokens) // 3)) else None


def _create_ad_hoc_topic(config: Config, query: str, week: str) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    topic_id = stable_id("topic_custom", query, week)
    finding_id = stable_id("finding_custom", query, week)
    source_id = "ad_hoc_operator_topic"
    content_hash = hashlib.sha256(f"{query}|{week}".encode()).hexdigest()
    with transaction(config.storage.sqlite_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO sources (
                id, name, type, source_type, trust_tier, url, is_active,
                recurring_enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                "User-provided topic",
                "manual",
                "manual",
                "needs_verification",
                "manual://ad-hoc-topic",
                1,
                0,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO findings (
                id, source_id, url, title, summary, published_at,
                content_hash, raw_content, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding_id,
                source_id,
                f"manual://ad-hoc-topic/{topic_id}",
                query,
                f"User requested an ad-hoc LinkedIn draft on: {query}. This topic needs source verification before public posting.",
                now,
                content_hash,
                query,
                "new",
                now,
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO topics (
                id, week_id, title, summary, plain_english_summary,
                hidden_gem_angle, executive_relevance, hidden_gem_value,
                technical_signal, source_credibility, oracle_safe_fit,
                draft_readiness, weighted_score, political_risk,
                recommendation, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                topic_id,
                week,
                query,
                f"Ad-hoc topic requested by the operator: {query}. Add or verify public sources before posting.",
                f"Ad-hoc topic: {query}",
                "Useful if a public source can be attached.",
                3,
                3,
                2,
                1,
                4,
                2,
                52.0,
                "low",
                "save_for_verification",
                "candidate",
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO topic_findings (topic_id, finding_id, relationship)
            VALUES (?, ?, ?)
            """,
            (topic_id, finding_id, "operator_requested"),
        )
    return topic_id


def build_topic_package(
    config: Config,
    week: str = "current",
    topic_id: str = "",
    query: str = "",
) -> Dict[str, object]:
    """Build a package from a chosen topic card or an ad-hoc operator topic."""
    from ai_linkedin_automation.pilot.production_test import build_production_test_package

    selected_topic_id = topic_id.strip()
    if not selected_topic_id:
        cleaned_query = _word_limited_query(query)
        if not cleaned_query:
            raise ValueError("Choose a topic or enter up to 50 words for an ad-hoc topic.")
        selected_topic_id = _best_matching_topic(config, cleaned_query) or _create_ad_hoc_topic(
            config,
            cleaned_query,
            week,
        )
    package = build_production_test_package(config, week=week, topic_id=selected_topic_id)
    reset_source_review_for_new_candidate(config, "Topic selected; review the source before approval.")
    return asdict(package)


def latest_post_image(config: Config, draft_id: str) -> Dict[str, str]:
    output_dir = resolve_project_path(config.storage.exports_dir) / "post_assets" / draft_id
    image_path = output_dir / "linkedin_post_image.png"
    manifest_path = output_dir / "image_safety_manifest.json"
    if not image_path.exists():
        return {}
    return {
        "image_path": str(image_path),
        "safety_manifest_path": str(manifest_path) if manifest_path.exists() else "",
    }


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _write_rgb_png(path: Path, width: int, height: int, pixels: bytes) -> None:
    raw_rows = []
    stride = width * 3
    for y in range(height):
        raw_rows.append(b"\x00" + pixels[y * stride : (y + 1) * stride])
    payload = b"".join(raw_rows)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(payload, 9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def _topic_palette(seed: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    digest = hashlib.sha256(seed.encode()).digest()
    base = (24 + digest[0] % 70, 72 + digest[1] % 80, 86 + digest[2] % 90)
    accent = (88 + digest[3] % 120, 154 + digest[4] % 80, 140 + digest[5] % 90)
    warm = (150 + digest[6] % 80, 90 + digest[7] % 80, 90 + digest[8] % 80)
    return base, accent, warm


def _put_pixel(pixels: bytearray, width: int, height: int, x: int, y: int, color: tuple[int, int, int]) -> None:
    if x < 0 or y < 0 or x >= width or y >= height:
        return
    offset = (y * width + x) * 3
    pixels[offset] = max(0, min(255, color[0]))
    pixels[offset + 1] = max(0, min(255, color[1]))
    pixels[offset + 2] = max(0, min(255, color[2]))


def _fill_rect(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    rect_width: int,
    rect_height: int,
    color: tuple[int, int, int],
) -> None:
    for yy in range(max(0, y), min(height, y + rect_height)):
        start = (yy * width + max(0, x)) * 3
        end_x = min(width, x + rect_width)
        for xx in range(max(0, x), end_x):
            offset = start + (xx - max(0, x)) * 3
            pixels[offset] = color[0]
            pixels[offset + 1] = color[1]
            pixels[offset + 2] = color[2]


def _stroke_rect(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    rect_width: int,
    rect_height: int,
    color: tuple[int, int, int],
    thickness: int = 4,
) -> None:
    _fill_rect(pixels, width, height, x, y, rect_width, thickness, color)
    _fill_rect(pixels, width, height, x, y + rect_height - thickness, rect_width, thickness, color)
    _fill_rect(pixels, width, height, x, y, thickness, rect_height, color)
    _fill_rect(pixels, width, height, x + rect_width - thickness, y, thickness, rect_height, color)


def _fill_circle(
    pixels: bytearray,
    width: int,
    height: int,
    cx: int,
    cy: int,
    radius: int,
    color: tuple[int, int, int],
) -> None:
    radius2 = radius * radius
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            dx = x - cx
            dy = y - cy
            if dx * dx + dy * dy <= radius2:
                _put_pixel(pixels, width, height, x, y, color)


def _draw_line(
    pixels: bytearray,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
    thickness: int = 4,
) -> None:
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        _fill_circle(pixels, width, height, x0, y0, max(1, thickness // 2), color)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _image_scene_plan(title: str, summary: str) -> Dict[str, object]:
    text = f"{title} {summary}".lower()
    if any(word in text for word in ["icu", "clinical", "patient", "health", "medical"]):
        return {
            "theme": "healthcare_oversight",
            "motifs": ["patient monitor", "approval gate", "checklist"],
            "alt": "Original illustration of an AI-assisted healthcare workflow with a monitoring panel and approval checklist.",
        }
    if any(word in text for word in ["governance", "risk", "policy", "safety", "compliance", "approval"]):
        return {
            "theme": "governance_gate",
            "motifs": ["shield", "checklist", "approval gate"],
            "alt": "Original illustration of AI governance with a shield, checklist, and approval gate.",
        }
    if any(word in text for word in ["agent", "agentic", "autonomous", "workflow", "tool"]):
        return {
            "theme": "agentic_workflow",
            "motifs": ["connected workflow nodes", "tool cards", "human approval gate"],
            "alt": "Original illustration of connected AI workflow nodes moving through a human approval gate.",
        }
    if any(word in text for word in ["benchmark", "evaluation", "eval", "research", "paper", "study"]):
        return {
            "theme": "research_to_readiness",
            "motifs": ["research document", "readiness dashboard", "evidence checks"],
            "alt": "Original illustration of research evidence being translated into a business readiness dashboard.",
        }
    if any(word in text for word in ["productivity", "business", "enterprise", "manager", "team", "operations"]):
        return {
            "theme": "business_workflow",
            "motifs": ["dashboard", "work queue", "approval checkpoint"],
            "alt": "Original illustration of a business workflow dashboard with an AI approval checkpoint.",
        }
    return {
        "theme": "ai_operating_model",
        "motifs": ["AI workflow", "evidence panel", "decision checkpoint"],
        "alt": "Original illustration of an AI operating model with evidence review and a decision checkpoint.",
    }


def _draw_dashboard(
    pixels: bytearray,
    width: int,
    height: int,
    accent: tuple[int, int, int],
    warm: tuple[int, int, int],
) -> None:
    panel = (238, 244, 246)
    line = (64, 86, 96)
    _fill_rect(pixels, width, height, 120, 120, 430, 310, panel)
    _stroke_rect(pixels, width, height, 120, 120, 430, 310, line, 6)
    for idx, bar_height in enumerate([92, 145, 118, 186]):
        x = 165 + idx * 82
        _fill_rect(pixels, width, height, x, 360 - bar_height, 46, bar_height, accent)
        _fill_rect(pixels, width, height, x + 12, 360 - bar_height + 18, 22, bar_height - 18, warm)
    _draw_line(pixels, width, height, 160, 210, 240, 190, line, 5)
    _draw_line(pixels, width, height, 240, 190, 315, 235, line, 5)
    _draw_line(pixels, width, height, 315, 235, 450, 170, line, 5)


def _draw_checklist(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    accent: tuple[int, int, int],
) -> None:
    paper = (250, 252, 252)
    line = (58, 74, 86)
    _fill_rect(pixels, width, height, x, y, 270, 300, paper)
    _stroke_rect(pixels, width, height, x, y, 270, 300, line, 5)
    for idx in range(4):
        yy = y + 55 + idx * 54
        _stroke_rect(pixels, width, height, x + 28, yy, 28, 28, accent, 4)
        _draw_line(pixels, width, height, x + 32, yy + 15, x + 41, yy + 24, line, 4)
        _draw_line(pixels, width, height, x + 41, yy + 24, x + 56, yy + 5, line, 4)
        _fill_rect(pixels, width, height, x + 78, yy + 9, 130, 10, (162, 178, 185))


def _draw_workflow_nodes(
    pixels: bytearray,
    width: int,
    height: int,
    accent: tuple[int, int, int],
    warm: tuple[int, int, int],
) -> None:
    nodes = [(655, 180), (805, 145), (780, 305), (940, 245), (1030, 385)]
    for (x0, y0), (x1, y1) in zip(nodes, nodes[1:]):
        _draw_line(pixels, width, height, x0, y0, x1, y1, (74, 96, 108), 6)
    for index, (x, y) in enumerate(nodes):
        color = accent if index < 3 else warm
        _fill_circle(pixels, width, height, x, y, 42, color)
        _fill_circle(pixels, width, height, x, y, 22, (245, 249, 250))
    _stroke_rect(pixels, width, height, 890, 330, 210, 125, warm, 8)


def _draw_health_monitor(
    pixels: bytearray,
    width: int,
    height: int,
    accent: tuple[int, int, int],
    warm: tuple[int, int, int],
) -> None:
    _fill_rect(pixels, width, height, 145, 155, 425, 240, (235, 243, 246))
    _stroke_rect(pixels, width, height, 145, 155, 425, 240, (58, 74, 86), 6)
    points = [(185, 285), (240, 285), (265, 245), (300, 330), (340, 205), (385, 285), (520, 285)]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        _draw_line(pixels, width, height, x0, y0, x1, y1, accent, 7)
    _fill_rect(pixels, width, height, 190, 185, 110, 16, warm)
    _fill_rect(pixels, width, height, 320, 185, 180, 16, (160, 178, 185))


def _draw_scene(path: Path, title: str, summary: str, plan: Dict[str, object]) -> None:
    width, height = 1200, 630
    base, accent, warm = _topic_palette(title + summary)
    pixels = bytearray(width * height * 3)
    for y in range(height):
        for x in range(width):
            t = x / max(1, width - 1)
            u = y / max(1, height - 1)
            wave = int(8 * math.sin(x / 78) + 6 * math.cos(y / 62))
            r = int(base[0] * (1 - t) + accent[0] * t + wave)
            g = int(base[1] * (1 - u) + accent[1] * u + wave)
            b = int(base[2] * (1 - t) + 210 * t + wave)
            offset = (y * width + x) * 3
            pixels[offset] = max(0, min(255, r))
            pixels[offset + 1] = max(0, min(255, g))
            pixels[offset + 2] = max(0, min(255, b))
    _fill_rect(pixels, width, height, 75, 70, 1050, 490, (226, 237, 240))
    _stroke_rect(pixels, width, height, 75, 70, 1050, 490, (48, 66, 76), 8)
    theme = str(plan.get("theme") or "")
    if theme == "healthcare_oversight":
        _draw_health_monitor(pixels, width, height, accent, warm)
        _draw_checklist(pixels, width, height, 740, 150, accent)
        _draw_workflow_nodes(pixels, width, height, accent, warm)
    elif theme == "governance_gate":
        _draw_dashboard(pixels, width, height, accent, warm)
        _draw_checklist(pixels, width, height, 745, 150, accent)
        _stroke_rect(pixels, width, height, 650, 220, 150, 210, warm, 10)
        _fill_circle(pixels, width, height, 725, 325, 38, warm)
    elif theme == "agentic_workflow":
        _draw_workflow_nodes(pixels, width, height, accent, warm)
        _draw_checklist(pixels, width, height, 135, 155, accent)
    elif theme == "research_to_readiness":
        _draw_checklist(pixels, width, height, 125, 145, accent)
        _draw_dashboard(pixels, width, height, accent, warm)
        _draw_workflow_nodes(pixels, width, height, accent, warm)
    else:
        _draw_dashboard(pixels, width, height, accent, warm)
        _draw_checklist(pixels, width, height, 790, 150, accent)
        _draw_workflow_nodes(pixels, width, height, accent, warm)
    _write_rgb_png(path, width, height, bytes(pixels))


def build_safe_post_image(config: Config, draft_id: Optional[str] = None) -> PostImagePackage:
    """Create a zero-spend original PG visual asset for the LinkedIn post."""
    selected_draft_id = draft_id or _latest_draft_id(config)
    row = _draft_row(config, selected_draft_id)
    if not row:
        raise ValueError(f"Draft not found: {selected_draft_id}")

    output_dir = resolve_project_path(config.storage.exports_dir) / "post_assets" / selected_draft_id
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / "linkedin_post_image.png"
    manifest_path = output_dir / "image_safety_manifest.json"
    title = row["topic_title"] or "AI leadership workflow"
    summary = _source_abstract(row)
    package_prompt = extract_section(str(row["content"] or ""), "Advanced Image Brief")
    package_alt = extract_section(str(row["content"] or ""), "Image Alt Text")
    scene_plan = _image_scene_plan(title, summary)
    prompt = (
        "Locus local image-planning agent / advanced image model brief:\n"
        + package_prompt
        if package_prompt
        else (
        "Locus local image-planning agent: create an original, PG-rated LinkedIn visual that is "
        f"representative of the topic '{title}'. Use the scene theme "
        f"{scene_plan['theme']} with motifs {', '.join(scene_plan['motifs'])}. "
        "No people, faces, logos, trademarks, text, violence, political symbols, stereotypes, "
        "or copyrighted source imagery."
        )
    )
    _draw_scene(image_path, title, summary, scene_plan)
    manifest = {
        "status": "passed",
        "mode": "locus_local_scene_planner_original_png",
        "draft_id": selected_draft_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "prompt": prompt,
        "scene_plan": scene_plan,
        "alt_text": package_alt or scene_plan["alt"],
        "guardrails": [
            "No third-party or copyrighted source image used.",
            "No people, faces, logos, trademarks, or public figures.",
            "No violence, nudity, hate, harassment, political symbols, or stereotypes.",
            "PG-rated topic-representative business visual only.",
        ],
        "image_path": str(image_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return PostImagePackage(
        status="created",
        draft_id=selected_draft_id,
        image_path=str(image_path),
        safety_manifest_path=str(manifest_path),
        prompt=prompt,
        alt_text=str(manifest["alt_text"]),
        safety_status="passed",
    )


def build_latest_manual_package(config: Config, draft_id: Optional[str] = None) -> str:
    path = build_manual_posting_package(config, draft_id or _latest_draft_id(config))
    build_pilot_checklist(config, write_files=True)
    return path


def archive_latest_post(
    config: Config,
    post_url: str,
    draft_id: Optional[str] = None,
    final_text: Optional[str] = None,
    engagement_snapshot: Optional[str] = None,
) -> Dict[str, object]:
    if not post_url.strip():
        raise ValueError("Post URL is required")
    result = archive_manual_post(
        config,
        draft_id or _latest_draft_id(config),
        post_url=post_url.strip(),
        final_text=final_text or None,
        engagement_snapshot=engagement_snapshot or None,
    )
    build_pilot_checklist(config, write_files=True)
    return asdict(result)


def read_artifact(path_value: str) -> Dict[str, str]:
    root = project_root().resolve()
    path = Path(path_value)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if root not in path.parents and path != root:
        raise ValueError("Artifact path must be inside the project folder")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Artifact not found: {path}")
    if path.suffix not in READABLE_SUFFIXES:
        raise ValueError(f"Artifact type is not previewable: {path.suffix}")
    content = path.read_text(errors="replace")
    return {
        "path": str(path),
        "name": path.name,
        "content": content,
    }
