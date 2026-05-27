import plistlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

from ai_linkedin_automation.config import Config, project_root, resolve_project_path


@dataclass
class SchedulePackage:
    output_dir: str
    daily_plist_path: str
    friday_plist_path: str
    runbook_path: str


def _ai_linkedin_executable() -> str:
    venv_executable = project_root() / ".venv" / "bin" / "ai-linkedin"
    if venv_executable.exists():
        return str(venv_executable)
    return str(Path(sys.executable).parent / "ai-linkedin")


def _plist(label: str, args: List[str], hour: int, minute: int, weekday: int | None = None) -> bytes:
    schedule = {"Hour": hour, "Minute": minute}
    if weekday is not None:
        schedule["Weekday"] = weekday
    payload = {
        "Label": label,
        "ProgramArguments": args,
        "StartCalendarInterval": schedule,
        "WorkingDirectory": str(project_root()),
        "StandardOutPath": str(resolve_project_path("data/logs") / f"{label}.out.log"),
        "StandardErrorPath": str(resolve_project_path("data/logs") / f"{label}.err.log"),
        "RunAtLoad": False,
    }
    return plistlib.dumps(payload, sort_keys=False)


def build_local_schedule_package(config: Config) -> SchedulePackage:
    """Generate launchd plist files and instructions without installing them."""
    output_dir = resolve_project_path(config.storage.exports_dir) / "schedule"
    output_dir.mkdir(parents=True, exist_ok=True)
    resolve_project_path(config.storage.logs_dir).mkdir(parents=True, exist_ok=True)

    executable = _ai_linkedin_executable()
    daily_plist = output_dir / "com.ai-linkedin.daily-scan.plist"
    friday_plist = output_dir / "com.ai-linkedin.friday-package.plist"
    runbook = output_dir / "README.md"

    daily_plist.write_bytes(
        _plist(
            "com.ai-linkedin.daily-scan",
            [executable, "run-daily-scan"],
            hour=8,
            minute=30,
        )
    )
    friday_plist.write_bytes(
        _plist(
            "com.ai-linkedin.friday-package",
            [executable, "run-friday-package", "--week", "current"],
            hour=12,
            minute=15,
            weekday=5,
        )
    )

    runbook.write_text(
        f"""# Local Schedule Package

These files are generated for optional macOS `launchd` setup. They have not been installed or loaded.

Generated files:
- `{daily_plist}`
- `{friday_plist}`

Daily scan command:

```bash
{executable} run-daily-scan
```

Friday package command:

```bash
{executable} run-friday-package --week current
```

Manual install, only after manual runs are stable:

```bash
mkdir -p ~/Library/LaunchAgents
cp "{daily_plist}" ~/Library/LaunchAgents/
cp "{friday_plist}" ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ai-linkedin.daily-scan.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ai-linkedin.friday-package.plist
```

Manual unload:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.ai-linkedin.daily-scan.plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.ai-linkedin.friday-package.plist
```

Safety notes:
- No paid API providers are enabled by this package.
- No email is sent by this package.
- No LinkedIn publishing is performed by this package.
- Approval and manual posting remain separate human actions.
"""
    )

    return SchedulePackage(
        output_dir=str(output_dir),
        daily_plist_path=str(daily_plist),
        friday_plist_path=str(friday_plist),
        runbook_path=str(runbook),
    )
