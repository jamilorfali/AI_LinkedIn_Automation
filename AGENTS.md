# AGENTS.md

## Project mission

Build a portable, zero-new-spend AI thought leadership workflow that produces one weekly LinkedIn draft for human approval.

## Hard rules

1. Do not post to LinkedIn.
2. Do not automate publishing unless the publishing adapter is explicitly enabled and a valid approval record exists.
3. Do not call paid APIs.
4. Do not scrape LinkedIn or X.
5. Do not ingest internal Oracle, client, prospect, NDA, private email, or private Slack content.
6. Do not store secrets in the repo.
7. Do not add cloud resources that can bill the user.
8. Default run mode is Hard Zero Mode.
9. Keep code portable across OpenAI, Claude, Gemini, and local/manual workflows.
10. Build small, testable increments.

## Coding style

- Use Python 3.11+.
- Prefer standard library where reasonable.
- Use SQLite as the source of truth.
- Use YAML for config.
- Use Markdown for generated briefings and drafts.
- Keep adapters separate from business logic.
- Add tests for every safety-critical path.

## Safety-critical paths needing tests

- Cost Guard blocks paid calls in Hard Zero Mode.
- Publishing Safety Gate blocks posting without approval.
- Token generation stores only token hashes.
- Expired approval tokens are rejected.
- Text approval does not automatically approve media.
- Source trust tiers prevent weak social signals from becoming publishable facts.

## Writing voice

Drafts should be plain-spoken, kind, practical, non-technical when possible, and useful for executives.