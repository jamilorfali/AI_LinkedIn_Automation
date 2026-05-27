#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [ ! -d ".venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install -e ".[dev]"

echo
echo "=== Status ==="
python -m ai_linkedin_automation.cli status

echo
echo "=== Initialize DB ==="
python -m ai_linkedin_automation.cli init-db

echo
echo "=== Load sources ==="
python -m ai_linkedin_automation.cli load-sources

echo
echo "=== Dry-run ingest ==="
python -m ai_linkedin_automation.cli ingest --dry-run

echo
echo "=== Ingest ==="
python -m ai_linkedin_automation.cli ingest

echo
echo "=== Score ==="
python -m ai_linkedin_automation.cli score

echo
mkdir -p data/weekly_packages
cat > data/weekly_packages/sample_weekly.md <<'EOF'
## Sample Weekly Insight
This is a test weekly package to validate draft generation.
It should produce a draft and allow approval testing.
EOF

echo "=== Generate draft and approval workflow ==="
python - <<'PY'
from pathlib import Path
from ai_linkedin_automation.config import load_config
from ai_linkedin_automation.drafting import generate_draft_from_weekly_package, save_draft
from ai_linkedin_automation.approval import (
    generate_approval_token,
    hash_token,
    store_approval_token,
    validate_approval_token,
    get_token_id_from_token,
    record_approval,
    mark_token_used,
)

config = load_config()
weekly = str(Path('data/weekly_packages/sample_weekly.md').resolve())
draft = generate_draft_from_weekly_package(weekly)
draft_id = save_draft(config.storage.sqlite_path, 'demo-topic', draft)
print(f'DRAFT_ID={draft_id}')
token = generate_approval_token(draft_id)
print(f'TOKEN={token}')
token_id = store_approval_token(config.storage.sqlite_path, draft_id, hash_token(token))
print(f'TOKEN_ID={token_id}')
valid, returned_draft = validate_approval_token(config.storage.sqlite_path, token)
print(f'VALID={valid}, DRAFT_ID={returned_draft}')
record_approval(config.storage.sqlite_path, token_id, 'approve', 'Demo approval')
mark_token_used(config.storage.sqlite_path, token)
print('Approval recorded successfully')
PY

echo
echo "=== Demo complete ==="
echo "Start the browser UI with: PYTHONPATH=src python3 -m ai_linkedin_automation.ui_server"
