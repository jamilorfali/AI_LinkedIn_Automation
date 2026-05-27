# GitHub Migration

This project can be moved to GitHub safely, but the repository must not include
local data, secrets, approval tokens, generated exports, databases, logs, or the
local desktop app bundle.

## What Should Be Tracked

- `src/`
- `tests/`
- `config/`
- `docs/`
- `prompts/`
- `style/`
- `apps_script/`
- `ui/`
- `db/schema.sql`
- `README.md`
- `AGENTS.md`
- `pyproject.toml`
- `setup.py`

## What Must Stay Local

- `.env`
- `.venv/`
- `.codex/`
- `AI LinkedIn Console.app/`
- `data/sqlite/*.db`
- `data/exports/*`
- `data/review_packets/*`
- `data/logs/*.log`
- `data/manual_links/*.csv`
- any OAuth token, API key, credential, or approval-token file

## First-Time Git Setup

From the project folder:

```bash
git init
git add .
git status --short
```

Before committing, confirm the status output does not include `.env`, `.venv`,
`data/exports`, `data/sqlite`, `data/review_packets`, `data/manual_links/*.csv`,
or `AI LinkedIn Console.app`.

Then commit:

```bash
git commit -m "Initial AI LinkedIn article studio"
```

## Create The GitHub Repo

Create an empty GitHub repository named something like:

```text
ai-linkedin-article-studio
```

Do not initialize it with a README, license, or `.gitignore` if you already
committed locally.

Then connect and push:

```bash
git remote add origin git@github.com:YOUR_USER/ai-linkedin-article-studio.git
git branch -M main
git push -u origin main
```

If you use HTTPS instead of SSH:

```bash
git remote add origin https://github.com/YOUR_USER/ai-linkedin-article-studio.git
git branch -M main
git push -u origin main
```

## Restore On Another Device

```bash
git clone git@github.com:YOUR_USER/ai-linkedin-article-studio.git
cd ai-linkedin-article-studio
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ai-linkedin init-db
```

Copy `.env` manually only if needed. Never commit it.
