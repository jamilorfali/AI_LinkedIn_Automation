# Local Mac Setup

Prerequisites:
- macOS.
- Python 3.11 or newer.
- Git.

Setup:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
ai-linkedin init-db
ai-linkedin preflight
```

## Optional Local Schedule Package

Do not schedule until manual runs are stable. When ready, generate local macOS launchd files and instructions:

```bash
ai-linkedin build-local-schedule-package
```

This creates files under `data/exports/schedule/` but does not install or load them.
