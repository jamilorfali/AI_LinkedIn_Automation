import csv
import json
import re
import secrets
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ai_linkedin_automation.approval import ALLOWED_APPROVAL_ACTIONS
from ai_linkedin_automation.config import Config, project_root, resolve_project_path
from ai_linkedin_automation.review import REVIEW_QUEUE_HEADERS


SCRIPT_DIR = project_root() / "apps_script" / "approval_webapp"
SCRIPT_FILES = ["Code.gs", "Index.html", "appsscript.json", "README.md"]
SYNC_TOKEN_ENV_KEY = "GOOGLE_APPS_SCRIPT_SYNC_TOKEN"
SYNC_TOKEN_PROPERTY = "AI_LINKEDIN_SYNC_TOKEN"
SYNC_TOKEN_PLACEHOLDER = "__AI_LINKEDIN_SYNC_TOKEN__"
REQUIRED_FUNCTIONS = [
    "doGet",
    "doPost",
    "parseRequest_",
    "recordApproval_",
    "syncReviewQueue_",
    "exportDecisions_",
    "requireSync_",
    "jsonOutput_",
    "reviewQueueCsv_",
    "validateToken_",
    "getReview_",
    "writeApproval_",
    "sha256Hex_",
    "isAllowedAction_",
    "columnIndexes_",
]
WEBAPP_ACTIONS = [
    "approve_text_only",
    "approve_text_plus_media",
    "approve_text_reject_media",
    "needs_edits",
    "pick_different_topic",
    "save_for_later",
    "reject",
]


@dataclass
class ValidationCheck:
    name: str
    status: str
    details: str


@dataclass
class WebappValidationReport:
    ok: bool
    generated_at: str
    checks: List[ValidationCheck]
    markdown_path: str = ""
    json_path: str = ""


@dataclass
class DeploymentPackage:
    output_dir: str
    script_dir: str
    sheet_template_csv: str
    checklist_path: str
    manifest_path: str
    validation_report_path: str


def _check(name: str, status: str, details: str) -> ValidationCheck:
    return ValidationCheck(name=name, status=status, details=details)


def _function_pattern(name: str) -> re.Pattern:
    return re.compile(rf"function\s+{re.escape(name)}\s*\(")


def _read(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _save_env_value(env_path: Path, key: str, value: str) -> None:
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


def _env_value(env_path: Path, key: str) -> str:
    if not env_path.exists():
        return ""
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return ""


def ensure_approval_sync_token(env_path: Optional[Path] = None) -> str:
    """Create the local token used by the console to sync with Apps Script."""
    import os

    env_path = env_path or project_root() / ".env"
    token = os.environ.get(SYNC_TOKEN_ENV_KEY, "").strip() or _env_value(env_path, SYNC_TOKEN_ENV_KEY)
    if not token:
        token = "aili_" + secrets.token_urlsafe(32)
        _save_env_value(env_path, SYNC_TOKEN_ENV_KEY, token)
    os.environ[SYNC_TOKEN_ENV_KEY] = token
    return token


def _headers_from_readme(readme: str) -> List[str]:
    match = re.search(r"```csv\s+([^`]+)```", readme, flags=re.MULTILINE)
    if not match:
        return []
    return [header.strip() for header in match.group(1).strip().split(",")]


def validate_approval_webapp_scaffold(
    script_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> WebappValidationReport:
    """Validate the local Apps Script scaffold without contacting Google."""
    script_dir = script_dir or SCRIPT_DIR
    checks: List[ValidationCheck] = []

    for file_name in SCRIPT_FILES:
        path = script_dir / file_name
        checks.append(
            _check(
                f"{file_name} exists",
                "pass" if path.exists() else "fail",
                str(path),
            )
        )

    code = _read(script_dir / "Code.gs")
    html = _read(script_dir / "Index.html")
    manifest_text = _read(script_dir / "appsscript.json")
    readme = _read(script_dir / "README.md")

    for function_name in REQUIRED_FUNCTIONS:
        checks.append(
            _check(
                f"Function {function_name}",
                "pass" if _function_pattern(function_name).search(code) else "fail",
                "Required by token validation, approval write-back, or header safety.",
            )
        )

    for header in REVIEW_QUEUE_HEADERS:
        checks.append(
            _check(
                f"Header {header}",
                "pass" if header in code else "fail",
                "Required in Apps Script header validation.",
            )
        )

    readme_headers = _headers_from_readme(readme)
    checks.append(
        _check(
            "README header contract",
            "pass" if readme_headers == REVIEW_QUEUE_HEADERS else "fail",
            "README CSV header list must match local review queue export.",
        )
    )

    for action in WEBAPP_ACTIONS:
        checks.append(
            _check(
                f"Action {action}",
                "pass" if action in code and action in html else "fail",
                "Action must be allowed in Code.gs and exposed in the mobile page.",
            )
        )

    sync_checks = {
        "Sync queue API": "sync_queue",
        "Export decisions API": "export_decisions",
        "Sync token property": SYNC_TOKEN_PROPERTY,
        "Script Properties": "PropertiesService",
        "Token placeholder": SYNC_TOKEN_PLACEHOLDER,
    }
    for name, marker in sync_checks.items():
        checks.append(
            _check(
                name,
                "pass" if marker in code else "fail",
                "Required for spreadsheet-free phone approval sync.",
            )
        )

    disallowed_actions = sorted(ALLOWED_APPROVAL_ACTIONS - set(WEBAPP_ACTIONS))
    checks.append(
        _check(
            "Webapp action subset",
            "pass" if disallowed_actions == ["approve"] else "warn",
            f"Local CLI has extra action(s): {', '.join(disallowed_actions)}",
        )
    )

    checks.append(
        _check(
            "Mobile viewport",
            "pass" if 'name="viewport"' in html else "fail",
            "Mobile approval page must render correctly on iPhone.",
        )
    )
    checks.append(
        _check(
            "No publish warning",
            "pass" if "No button on this page publishes to LinkedIn" in html else "fail",
            "Approval page must state that it does not publish.",
        )
    )

    try:
        manifest = json.loads(manifest_text)
        scopes = manifest.get("oauthScopes", [])
        scope_ok = scopes == ["https://www.googleapis.com/auth/spreadsheets.currentonly"]
        checks.append(
            _check(
                "Manifest scope",
                "pass" if scope_ok else "fail",
                "Only current spreadsheet scope should be requested.",
            )
        )
        checks.append(
            _check(
                "V8 runtime",
                "pass" if manifest.get("runtimeVersion") == "V8" else "fail",
                "Apps Script should use V8 runtime.",
            )
        )
        webapp = manifest.get("webapp", {})
        checks.append(
            _check(
                "Manifest web app resource",
                "pass"
                if webapp.get("executeAs") == "USER_DEPLOYING" and webapp.get("access")
                else "fail",
                "Use a webapp manifest resource, not executionApi, so New deployment offers Web app.",
            )
        )
        checks.append(
            _check(
                "No API executable manifest",
                "pass" if "executionApi" not in manifest else "fail",
                "Consumer Google users should deploy this approval page as a Web app, not API Executable.",
            )
        )
    except json.JSONDecodeError as exc:
        checks.append(_check("Manifest JSON", "fail", f"Invalid appsscript.json: {exc}"))

    generated_at = datetime.now().isoformat(timespec="seconds")
    ok = not any(check.status == "fail" for check in checks)
    report = WebappValidationReport(ok=ok, generated_at=generated_at, checks=checks)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        report.markdown_path = str(output_dir / "approval_webapp_validation.md")
        report.json_path = str(output_dir / "approval_webapp_validation.json")
        Path(report.markdown_path).write_text(render_validation_report(report))
        Path(report.json_path).write_text(json.dumps(asdict(report), indent=2))

    return report


def render_validation_report(report: WebappValidationReport) -> str:
    lines = [
        "# Approval Web App Validation",
        "",
        f"Generated: {report.generated_at}",
        f"Overall: {'PASS' if report.ok else 'FAIL'}",
        "",
    ]
    for check in report.checks:
        lines.append(f"- [{check.status.upper()}] {check.name}: {check.details}")
    return "\n".join(lines) + "\n"


def write_sheet_template(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(REVIEW_QUEUE_HEADERS)
    return str(path)


def build_deployment_package(config: Config, week: str = "current") -> DeploymentPackage:
    """Create local copy/paste deployment files; does not deploy or contact Google."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = resolve_project_path(config.storage.exports_dir) / "approval_webapp" / timestamp
    package_script_dir = output_dir / "approval_webapp"
    package_script_dir.mkdir(parents=True, exist_ok=True)
    sync_token = ensure_approval_sync_token()

    for file_name in SCRIPT_FILES:
        source_path = SCRIPT_DIR / file_name
        target_path = package_script_dir / file_name
        if file_name == "Code.gs":
            code = source_path.read_text()
            target_path.write_text(code.replace(SYNC_TOKEN_PLACEHOLDER, sync_token, 1))
        else:
            shutil.copy2(source_path, target_path)

    sheet_template = output_dir / "review_queue_sheet_template.csv"
    write_sheet_template(sheet_template)

    validation = validate_approval_webapp_scaffold(SCRIPT_DIR, output_dir)
    checklist = output_dir / "DEPLOYMENT_CHECKLIST.md"
    manifest = output_dir / "deployment_manifest.json"

    checklist.write_text(
        f"""# Approval Web App Deployment Checklist

This package is local only. Nothing has been deployed.

## Files To Copy Into Apps Script

- `{package_script_dir / "Code.gs"}`
- `{package_script_dir / "Index.html"}`
- `{package_script_dir / "appsscript.json"}`

## One-Time Google Setup

1. Create a Google Sheet named `AI LinkedIn Review Queue`.
2. Create a tab named `ReviewQueue`. You do not need to operate this Sheet on your phone.
3. Keep the Sheet open, then open Extensions -> Apps Script.

## Web App Setup

1. Add the copied files above.
2. Paste the packaged `Code.gs` from this folder. It already includes the console sync token.
3. Save the Apps Script project. This is required before Google shows the latest deployment types.
4. If you already have the web app URL, click Deploy -> Manage deployments -> pencil icon -> Version -> New version -> Deploy. This keeps the same saved `/exec` URL.
5. If this is the first deployment, click Deploy -> New deployment.
6. For a first deployment, click the gear icon next to Select type and choose Web app. If you only see API Executable, save the project, reload Apps Script, confirm `Code.gs` contains `doGet`, and confirm `appsscript.json` contains a `webapp` block.
7. Set Execute as to Me. For Who has access, choose Anyone if available, or Anyone with Google account if that is the only consumer-account option.
8. Copy the web app URL into the console Approve tab and press Save URL. This saves `GOOGLE_APPS_SCRIPT_WEBAPP_URL` for future runs.
9. In the console, press Sync to Phone Approval. This uploads the current review queue to the background Sheet.
10. Open the magic link on iPhone, laptop, or tablet and record one non-publishing approval action.
11. In the console, press Import Phone Decision. The console reads the decision back and builds the posting package when the decision approves the draft.

## Sync Token

- Local env key: `{SYNC_TOKEN_ENV_KEY}`
- Apps Script property name, if you choose Script properties instead of the packaged Code.gs token: `{SYNC_TOKEN_PROPERTY}`
- This token only authorizes review-queue sync. It does not authorize LinkedIn, paid AI, email, or other accounts.

## Safety

- No raw tokens are stored in the Sheet.
- The Apps Script does not call AI APIs.
- The Apps Script does not publish to LinkedIn.
- The local runner must import approval state before any posting package is created.
"""
    )

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "week": week,
        "script_dir": str(package_script_dir),
        "sheet_template_csv": str(sheet_template),
        "checklist_path": str(checklist),
        "validation_report_path": validation.markdown_path,
        "validation_ok": validation.ok,
        "sync_token_env_key": SYNC_TOKEN_ENV_KEY,
        "sync_token_property": SYNC_TOKEN_PROPERTY,
        "packaged_code_contains_sync_token": True,
        "no_google_deploy_performed": True,
        "no_email_sent": True,
        "no_linkedin_publish": True,
    }
    manifest.write_text(json.dumps(payload, indent=2))

    return DeploymentPackage(
        output_dir=str(output_dir),
        script_dir=str(package_script_dir),
        sheet_template_csv=str(sheet_template),
        checklist_path=str(checklist),
        manifest_path=str(manifest),
        validation_report_path=validation.markdown_path,
    )
