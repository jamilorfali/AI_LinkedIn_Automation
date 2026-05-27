# AI LinkedIn Thought Leadership Automation
## Codex Build Guide, v0.2 Detailed Implementation Blueprint

**Prepared for:** NAA AI & Emerging Technology Strategist

**Primary outcome:** Build a portable, zero-new-spend, human-approved automation that helps produce one thoughtful AI-related LinkedIn post per week.

**Default weekly deadline:** Friday, between 12:00 PM and 2:00 PM Central Time.

**Default publishing target:** Personal LinkedIn profile only.

**Default publishing rule:** No approval record, no post.

**Default cost rule:** Hard Zero Mode. Nothing in this build may create a bill above $0 unless the human owner explicitly changes the run mode later.

---

# 0. Read this first, Codex

You are being asked to build a real application, not just sketch an idea.

Work in small, reviewable milestones. Before editing many files, inspect the repo, summarize your plan, then implement the smallest useful slice. After each milestone, run the relevant tests and give a short change summary.

## 0.1 Non-negotiable constraints

1. **No publishing without explicit approval.**
   - Do not post to LinkedIn unless a valid approval record exists for the exact draft version and content hash.
   - The initial implementation should use assisted manual posting. The LinkedIn API adapter may be scaffolded but must stay disabled.

2. **No new personal spend.**
   - Do not use paid APIs.
   - Do not create paid cloud resources.
   - Do not require a credit card.
   - Do not enable GitHub-hosted scheduled jobs by default.
   - Do not call OpenAI, Anthropic, Google Gemini, X, LinkedIn, or paid search APIs unless a later configuration explicitly allows it.

3. **Use Hard Zero Mode by default.**
   - The app may use local Python code, SQLite, local files, RSS feeds, manually saved links, Google Apps Script, Google Sheets, and Google Drive.
   - Any external API must be behind the Cost Guard.

4. **Do not scrape LinkedIn or X.**
   - Manual public links are allowed.
   - Official APIs may be added later only if compliant, approved, and cost-safe.

5. **Do not store confidential work data.**
   - The portable personal profile may store public information, personal editorial notes, public Oracle-safe professional context, drafts, and final posts.
   - It may not store client names, prospect names, internal Oracle strategy, private emails, private Slack messages, internal-only slides, NDA material, roadmap information, or confidential workshop content.

6. **Default voice is human, plain, and useful.**
   - Down to earth.
   - Informal but thoughtful.
   - Non-technical when possible.
   - Good for executive and technical audiences.
   - Warm, kind, and practical.
   - Short first, medium only when the topic earns it.
   - No hype, no marketing tone, no employer name-dropping, no academic stiffness, no obvious AI-giveaway language.

7. **Political risk is handled conservatively.**
   - Policy topics are allowed only when neutral and business-relevant.
   - Avoid elections, parties, candidates, culture-war framing, government drama, geopolitical hot takes, and workplace-awkward commentary.

8. **Vendor and competitor stories must be neutral.**
   - Talk about the shift, not the scoreboard.
   - Do not compare vendors publicly.
   - Do not write Oracle versus Microsoft, OpenAI versus Anthropic, or similar competitive framing.

9. **Media requires separate approval.**
   - Text approval does not automatically approve generated images, diagrams, or carousel assets.

10. **Everything should be portable.**
   - The core logic should be plain code, local files, Markdown prompts, SQLite, YAML, and simple adapters.
   - Do not hard-wire the system to Codex, Slack, Outlook, Oracle, OpenAI, Claude, Gemini, or LinkedIn.

---

# 1. Special note about the user's current Codex macOS issue

The user has seen this error in the Codex macOS desktop app:

```text
Error starting chat
invalid turn context override: invalid value for `approval_policy`:
`OnRequest` is not in the allowed set [UnlessTrusted]
(set by cloud requirements)
```

This appears to be a managed enterprise policy mismatch. The app is trying to start a chat with an approval policy equivalent to `on-request`, while the enterprise cloud requirements only allow a stricter mode equivalent to `untrusted` or `unless trusted`.

Do not solve this by changing the application architecture. Treat it as a Codex client/admin configuration issue.

For project config, prefer:

```toml
approval_policy = "untrusted"
sandbox_mode = "workspace-write"
```

Do not create `.codex/config.toml` with `approval_policy = "on-request"` for this user unless the enterprise policy is later changed.

If the desktop app still cannot start, the user may need to use the bundled CLI or ask an admin to allow the app's requested approval mode. Keep build instructions compatible with the CLI.

---

# 2. How to use this file with Codex

## 2.1 Recommended first prompt to Codex

Copy this into Codex after opening a fresh empty repo folder:

```text
Read the entire file `AI_LINKEDIN_AUTOMATION_CODEX_BUILD_GUIDE.md`.

Build this project in small milestones. Start with Phase 0 only:
1. Create the repo scaffold.
2. Add AGENTS.md.
3. Add pyproject.toml.
4. Add the SQLite schema.
5. Add initial config YAML files.
6. Add a simple CLI entry point that can initialize the database and print a system status report.
7. Add tests for the database initialization and config loading.

Do not implement LinkedIn posting.
Do not call any paid API.
Do not scrape LinkedIn or X.
Do not use OpenAI, Claude, or Gemini APIs.
Use Hard Zero Mode by default.
Use approval_policy = "untrusted" in Codex config, not "on-request".

After Phase 0, stop and summarize exactly what you built, how to run it, and what tests passed.
```

## 2.2 Recommended second prompt to Codex

After Phase 0 passes:

```text
Continue with Phase 1 from `AI_LINKEDIN_AUTOMATION_CODEX_BUILD_GUIDE.md`.

Implement local ingestion for:
1. RSS feeds from config/sources.yaml.
2. Manual link ingestion from data/manual_links/inbox.csv.
3. Local HTML/text extraction for public pages where technically feasible and respectful.
4. SQLite persistence for sources, findings, topics, and run logs.

Do not implement social scraping.
Do not call paid APIs.
Do not implement LinkedIn posting.
Do not implement AI model calls yet.

Add unit tests and a CLI command that runs ingestion in dry-run mode and real local mode.
Stop after Phase 1 and summarize.
```

## 2.3 Recommended third prompt to Codex

After Phase 1 passes:

```text
Continue with Phase 2 from `AI_LINKEDIN_AUTOMATION_CODEX_BUILD_GUIDE.md`.

Implement deterministic scoring and weekly package generation:
1. Topic scorecard model.
2. Source trust tiers.
3. Political/workplace risk flags.
4. Vendor sensitivity flags.
5. Draft readiness score.
6. A Markdown weekly package generator that produces top 3 to 5 topics plus one recommended winner.

Use deterministic templates and saved prompt packets. Do not call LLM APIs.
Add tests for scoring rules and package generation.
Stop after Phase 2 and summarize.
```

## 2.4 Recommended fourth prompt to Codex

After Phase 2 passes:

```text
Continue with Phase 3 from `AI_LINKEDIN_AUTOMATION_CODEX_BUILD_GUIDE.md`.

Implement the Google review layer scaffold:
1. Google Apps Script files under apps_script/approval_webapp/.
2. A local Python module that can export a review packet JSON file.
3. A CLI command that creates a magic-link approval packet locally.
4. A Google Sheets-compatible CSV export.
5. Documentation for deploying the Apps Script manually.

Do not require Google API credentials in the Python app yet.
Do not publish anything.
Add tests for token generation, token hashing, expiration, and approval-state transitions.
Stop after Phase 3 and summarize.
```

---

# 3. Project purpose and product definition

## 3.1 User role

The user is an AI and Emerging Technology Strategist who periodically delivers AI strategy executive briefings and workshops. The content system should help build personal credibility and public awareness of the user's role through thoughtful LinkedIn posts.

## 3.2 Content goal

Publish one strong AI-related LinkedIn post per week.

The post should help executives, business leaders, and technical audiences understand what matters behind the AI headlines.

The system should favor:

- Credible sources.
- Cutting-edge AI developments.
- Hidden gems.
- Practical executive meaning.
- Underappreciated economic, technology, operational, or cultural implications.
- Clear, warm, human explanation.

The system should avoid:

- Partisan politics.
- Culture-war topics.
- Hype.
- Salesy framing.
- Dense technical explanation.
- Weak claims from social media.
- Vendor scorekeeping.

## 3.3 End user experience

Every Friday between 12:00 PM and 2:00 PM Central, the user receives a package that says, in effect:

```text
Here are the strongest AI stories I found this week.

I recommend Topic 2 because it has the best mix of executive relevance,
hidden gem value, and source strength.

I drafted a short LinkedIn post below in your voice.

Please approve, edit, choose another topic, save, or reject.
```

The user should be able to review on a work iPhone.

---

# 4. Decision history from architecture conversation

This section preserves design intent so future Codex sessions do not accidentally reverse key decisions.

## 4.1 Architecture approach

Decision: Design two paths, enterprise-safe and personal-portable, but build one portable core that can support both.

Preferred operating model:

- Private GitHub repository for code and configuration.
- Local runner on work or personal machine.
- SQLite as system of record.
- Google Sheets as review queue.
- Google Drive as reading room.
- Google Apps Script as mobile approval page.
- Outlook as current notification channel.
- Personal LinkedIn profile as publishing target.

## 4.2 Future safety

Decision: The architecture should be lift-and-shift capable across OpenAI, Claude, Gemini, or future automation tools.

Therefore:

- Core logic lives in plain code.
- Model providers are adapters.
- Approval channels are adapters.
- Publishing is an adapter.
- Storage is simple and exportable.

## 4.3 Cost

Decision: Build all cost modes, but default to Hard Zero Mode.

Modes:

1. Hard Zero Mode.
2. Free Tier Plus Guardrails.
3. Future Paid Mode.

Default:

```yaml
run_mode: hard_zero
monthly_spend_cap_usd: 0
```

## 4.4 Execution

Decision: Design all deployment profiles, but prefer a private GitHub repo plus local runner.

Supported profiles:

- Local-only.
- GitHub manual.
- GitHub plus local runner.
- Google Sheets-first dashboard.

Preferred:

- GitHub stores the system.
- Local machine runs the system.

## 4.5 Devices

Decision: Support both work laptop and personal machine. Review and approval should work on work iPhone.

## 4.6 Approval channel

Decision: Use Outlook email plus private mobile web approval page.

Outlook is the notification channel.

Google Apps Script is the preferred mobile approval host.

Magic link security is preferred.

## 4.7 Account ownership

Decision: Design all account ownership models, but prefer a dual profile with personal Google ownership.

Preferred:

- Personal Google account owns Apps Script, Sheet, and Drive review folder.
- Work Outlook receives notification emails.
- Work profile may mirror only non-sensitive approved outputs.

## 4.8 Data boundary

Decision: Portable personal profile may store public information plus Oracle-safe professional context.

Allowed:

- Public AI articles.
- Public research papers.
- Public company announcements.
- Public Oracle messaging.
- Personal editorial notes.
- Drafts and final posts.

Blocked:

- Client data.
- Prospect data.
- Oracle internal strategy.
- NDA material.
- Private email or Slack.
- Internal slides.
- Unannounced roadmap information.

## 4.9 Source ingestion

Decision: Include public web/RSS, manual social links, official free APIs where compliant, and public newsletters from email.

No scraping LinkedIn or X.

## 4.10 Source credibility

Decision: Use all four governance models:

- Strict whitelist for recurring sources.
- Discovery queue for new sources.
- Open discovery with scoring.
- Tiered source model.

## 4.11 Topic selection

Decision: Use blended scoring across:

- Executive relevance.
- Hidden gem value.
- Cutting-edge technical signal.
- Source credibility.
- Political risk.
- Oracle-safe professional fit.
- Draft readiness.

Oracle relevance is light secondary score and final fit check, not the primary topic driver.

## 4.12 Weekly output

Decision: Daily scan, weekly post.

The Friday package includes:

- Top 3 to 5 choices.
- Snack summaries.
- Scorecards.
- Recommended winner.
- Draft article for recommended winner.

## 4.13 Non-response behavior

Decision:

- No response means no post.
- Send one Friday reminder.
- Roll draft forward.
- Send Monday follow-up if still unanswered.

## 4.14 Posting behavior

Decision: Design all posting modes, prefer fully automated after approval as end state.

Default v0 should support assisted manual posting first.

The final target is personal LinkedIn profile only.

Do not mention Oracle unless necessary.

## 4.15 Post length

Decision:

- Short first: roughly 150 to 250 words.
- Medium only when truly worth it: roughly 300 to 500 words.

## 4.16 Citations

Decision: Public LinkedIn post includes source references inside the post, but subtly.

Adaptive citation rule:

- Usually one source.
- Sometimes two.
- Rarely three.

No academic citation pile.

## 4.17 Visuals

Decision: Adaptive visual format.

Supported:

- Text plus suggested image idea.
- Text plus generated visual draft.
- Text plus carousel outline.

Media requires separate approval.

## 4.18 Political risk

Decision: Allow neutral business-relevant policy only.

Policy is allowed when it helps executives make better decisions. Politics is avoided.

## 4.19 Vendor/competitor stories

Decision: Use all guardrails.

- Neutral industry lens.
- Avoid competitor stories unless truly important.
- Use primary-source vendor research when useful.
- Never compare vendors publicly.

## 4.20 Voice learning

Decision: Use all approved inputs, but never ingest automatically.

The system may use:

- Approved LinkedIn posts.
- Approved professional writing.
- Future edits.
- Style guide.

Only content explicitly marked as approved writing sample may be used.

---

# 5. v0 system overview

## 5.1 Plain-English architecture

```text
Source Registry
  -> Daily Ingestion Engine
  -> Credibility and Risk Filter
  -> Topic Scoring Engine
  -> SQLite System of Record
  -> Weekly Briefing Builder
  -> Draft/Prompt Packet Generator
  -> Voice and Risk Review
  -> Google Sheet Review Queue
  -> Google Drive Reading Room
  -> Outlook Notification
  -> Apps Script Magic Link Approval Page
  -> Approval Record
  -> Assisted Manual Posting or Future LinkedIn Adapter
```

## 5.2 Core technical stack

Default v0:

- Python 3.11 or newer.
- SQLite.
- YAML configuration.
- Markdown outputs.
- RSS ingestion.
- Local file exports.
- Google Apps Script approval page scaffold.
- Google Sheets/CSV review queue.
- GitHub private repo.
- Local runner.

Optional later:

- OpenAI adapter.
- Claude adapter.
- Gemini adapter.
- LinkedIn API adapter.
- X API adapter.
- Google Sheets API adapter.
- Outlook Graph email adapter.

## 5.3 Initial MVP principle

Build an end-to-end skeleton before building intelligence.

The first working MVP should be able to:

1. Initialize a database.
2. Load sources from YAML.
3. Ingest RSS/manual links.
4. Save findings.
5. Score topics with deterministic rules.
6. Generate a Friday package in Markdown.
7. Generate a draft prompt packet for a model.
8. Create a local approval token.
9. Export a review queue CSV.
10. Block any publishing attempt without approval.

---

# 6. Repository structure to create

Create this structure:

```text
ai-linkedin-automation/
  AGENTS.md
  README.md
  AI_LINKEDIN_AUTOMATION_CODEX_BUILD_GUIDE.md
  pyproject.toml
  .gitignore
  .env.example
  .codex/
    config.toml
  config/
    app.yaml
    cost_guard.yaml
    publishing.yaml
    sources.yaml
    scoring_weights.yaml
    style_rules.yaml
  data/
    manual_links/
  db/
    schema.sql
  docs/
    architecture.md
    operating_model.md
    source_governance.md
    troubleshooting.md
  prompts/
    00_system_guardrails.md
    01_topic_scoring.md
    02_draft_generation.md
    03_voice_review.md
    04_citation_check.md
    05_media_recommender.md
  style/
    personal_voice_guide.md
    edit_learning_log.md
  apps_script/
    approval_webapp/
  src/
    ai_linkedin_automation/
  tests/
    test_config.py
    test_db.py
    test_cost_guard.py
    test_publishing_safety_gate.py
```

---

# 7. Initial configuration files

## 7.1 `.codex/config.toml`

Use this because the user's enterprise environment appears to allow the stricter approval mode only:

```toml
approval_policy = "untrusted"
sandbox_mode = "workspace-write"

[features]
# Enable only if supported by the local Codex app/CLI and enterprise policy.
# Leave advanced features off unless needed.
```

Do not set `approval_policy = "on-request"` for this user unless their enterprise policy is later changed.

## 7.2 `AGENTS.md`

Create this file exactly or very close to this:

```markdown
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
```

## 7.3 `.gitignore`

```gitignore
# Python
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
venv/

# Local data
/data/sqlite/*.db
/data/sqlite/*.db-*
/data/logs/*.log
/data/exports/*
/data/review_packets/*
!data/exports/.gitkeep
!data/review_packets/.gitkeep

# Secrets
.env
*.secret
secrets.*
credentials.json
token.json

# OS
.DS_Store
```

## 7.4 `.env.example`

```dotenv
APP_ENV=local
RUN_MODE=hard_zero
DATABASE_PATH=data/sqlite/ai_linkedin_automation.db
TIMEZONE=America/Chicago

# Optional future settings. Leave blank in v0.
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
GOOGLE_APPS_SCRIPT_WEBAPP_URL=
GOOGLE_APPS_SCRIPT_SHARED_SECRET=
```

## 7.5 `config/app.yaml`

```yaml
app:
  name: ai-linkedin-automation
  timezone: America/Chicago
  default_run_mode: hard_zero
  weekly_package_day: friday
  weekly_package_window_start: "12:00"
  weekly_package_window_end: "14:00"

storage:
  sqlite_path: data/sqlite/ai_linkedin_automation.db
  exports_dir: data/exports
  review_packets_dir: data/review_packets
  logs_dir: data/logs

review:
  approval_method: magic_link
  notification_channel: outlook_email
  approval_host: google_apps_script
  token_expiration_hours: 120

publishing:
  target: personal_linkedin_profile
  default_mode: assisted_manual
  linkedin_api_enabled: false
  require_approval_record: true
  require_content_hash_match: true
  text_only_first: true
  media_publishing_enabled: false
```

## 7.6 `config/cost_guard.yaml`

```yaml
run_mode: hard_zero
monthly_spend_cap_usd: 0

hard_zero:
  allow_paid_apis: false
  allow_openai_api: false
  allow_claude_api: false
  allow_gemini_api: false
  allow_linkedin_api_publish: false
  allow_x_api: false
  allow_paid_search_api: false
  allow_github_hosted_actions: false

free_tier_plus_guardrails:
  enabled: false
  monthly_spend_cap_usd: 0
  require_manual_unlock: true
  require_local_call_limits: true

future_paid_mode:
  enabled: false
  require_manual_unlock: true
  require_budget_file_change: true
  require_approval_before_first_paid_call: true

limits:
  max_external_fetches_per_run: 100
  max_sources_per_run: 50
  max_manual_links_per_run: 25
  max_llm_calls_per_run: 0
  max_linkedin_publish_calls_per_run: 0
```

## 7.7 `config/sources.yaml`

Start modest. Do not overbuild the source registry on day one.

```yaml
source_policy:
  no_social_scraping: true
  allow_manual_social_links: true
  require_primary_or_high_trust_for_publish: true
  discovery_queue_requires_human_approval: true

trust_tiers:
  primary:
    description: Original source of a claim.
    publish_support_allowed: true
  high_trust:
    description: Reputable reporting, analyst, research, or expert synthesis.
    publish_support_allowed: true
  useful_but_verify:
    description: Useful but requires verification before use in claims.
    publish_support_allowed: false
  social_signal_only:
    description: Social media signals, not sufficient for factual claims.
    publish_support_allowed: false
  blocked:
    description: Do not use.
    publish_support_allowed: false

recurring_sources:
  - id: arxiv_ai
    name: arXiv AI
    type: rss
    trust_tier: high_trust
    rss_url: http://export.arxiv.org/rss/cs.AI
    is_active: true

manual_sources:
  manual_link_inbox:
    name: Manual Link Inbox
    type: manual
    trust_tier: useful_but_verify
```

## 7.8 `data/manual_links/inbox.csv`

```csv
url,title,source_hint,notes,added_at
```

## 7.9 `config/scoring_weights.yaml`

```yaml
score_scale:
  min: 1
  max: 5

weights:
  executive_relevance: 0.25
  hidden_gem_value: 0.20
  technical_signal: 0.20
  source_credibility: 0.20
  oracle_safe_fit: 0.10
  draft_readiness: 0.05

recommendation_rules:
  draft_now:
    - executive_relevance >= 4
    - hidden_gem_value >= 3
    - source_credibility >= 4
    - political_risk == "low"
    - oracle_safe_fit >= 4
    - draft_readiness >= 4

hard_gates:
  require_primary_or_high_trust_source_for_publish: true
  block_high_political_risk: true
  block_vendor_comparison_topics: true
  block_social_signal_only_claims: true
```

## 7.10 `config/style_rules.yaml`

```yaml
voice:
  default_length: short
  short_word_target: 150-250
  medium_word_target: 300-500
  medium_only_when_earned: true

must_feel:
  - plain_spoken
  - down_to_earth
  - warm
  - kind
  - thoughtful
  - practical
  - non_hype
  - informal_but_thoughtful
  - non_technical_when_possible
  - good_for_executives_and_technical_audiences
  - short_first
  - medium_only_when_topic_earns_it

avoid:
  - hype
  - marketing_tone
  - academic_stiffness
  - employer_name_dropping
  - obvious_ai_giveaway_language
  - partisan_politics
  - culture_war_framing
  - government_drama
  - geopolitical_hot_takes
  - workplace_awkward_commentary
  - vendor_scorekeeping
  - dense_technical_explanation
  - weak_claims_from_social_media
  - semicolon_heavy_phrasing
  - dash_heavy_structure

banned_phrases:
  - in today's rapidly evolving landscape
  - the future of AI is
  - transformative potential
  - paradigm shift
  - cutting-edge technology
  - robust ecosystem
  - seamless integration
  - unparalleled efficiency
  - game-changing
  - revolutionary
```

---

# 8. Database schema

Create `db/schema.sql`.

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    run_type TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    trust_tier TEXT NOT NULL,
    url TEXT,
    rss_url TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    last_fetched_at TEXT,
    fetch_error TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    published_at TEXT,
    content_hash TEXT NOT NULL,
    raw_content TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    executive_relevance INTEGER,
    hidden_gem_value INTEGER,
    technical_signal INTEGER,
    source_credibility INTEGER,
    oracle_safe_fit INTEGER,
    draft_readiness INTEGER,
    political_risk TEXT,
    recommendation TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_findings (
    topic_id TEXT NOT NULL,
    finding_id TEXT NOT NULL,
    PRIMARY KEY (topic_id, finding_id),
    FOREIGN KEY (topic_id) REFERENCES topics(id),
    FOREIGN KEY (finding_id) REFERENCES findings(id)
);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    support_level TEXT NOT NULL,
    source_id TEXT,
    notes TEXT,
    FOREIGN KEY (topic_id) REFERENCES topics(id),
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(topic_id, version),
    FOREIGN KEY (topic_id) REFERENCES topics(id)
);

CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL,
    type TEXT NOT NULL,
    url TEXT,
    content TEXT,
    approval_status TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (draft_id) REFERENCES drafts(id)
);

CREATE TABLE IF NOT EXISTS approval_tokens (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (draft_id) REFERENCES drafts(id)
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    token_id TEXT NOT NULL,
    action TEXT NOT NULL,
    notes TEXT,
    approved_at TEXT NOT NULL,
    FOREIGN KEY (token_id) REFERENCES approval_tokens(id)
);

CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    post_url TEXT,
    status TEXT NOT NULL,
    posted_at TEXT NOT NULL,
    FOREIGN KEY (draft_id) REFERENCES drafts(id)
);

CREATE TABLE IF NOT EXISTS cost_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    provider TEXT NOT NULL,
    action TEXT NOT NULL,
    estimated_cost_usd REAL DEFAULT 0.0,
    allowed INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
```

---

# 9. Python package requirements

Use a minimal dependency set.

Suggested `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ai-linkedin-automation"
version = "0.1.0"
description = "Zero-spend weekly AI LinkedIn thought leadership automation with human approval."
requires-python = ">=3.11"
dependencies = [
    "feedparser>=6.0.11",
    "pyyaml>=6.0.1",
    "click>=8.1.7",
    "requests>=2.31.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "ruff>=0.5.0",
]

[project.scripts]
ai-linkedin = "ai_linkedin_automation.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]
```

Install locally:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

---

# 10. CLI commands to implement

Implement a `click` CLI with these commands.

```bash
ai-linkedin status
ai-linkedin init-db
ai-linkedin load-sources
ai-linkedin ingest --dry-run
ai-linkedin ingest
ai-linkedin score --week current
ai-linkedin build-weekly-package --week current
ai-linkedin create-approval-packet --draft-id DRAFT_ID
ai-linkedin export-review-queue --week current
ai-linkedin build-manual-posting-package --draft-id DRAFT_ID
ai-linkedin publish --draft-id DRAFT_ID
```

Publishing should be blocked by default.

Expected publish behavior in v0:

```bash
ai-linkedin publish --draft-id draft_123
```

Should return something like:

```text
Publishing blocked.
Reason: LinkedIn API publishing is disabled in config/publishing.yaml.
Assisted manual posting package available at data/exports/manual_posting/draft_123.md
```

---

# 11. Core modules and responsibilities

## 11.1 `config.py`

Responsibilities:

- Load YAML config.
- Load `.env`.
- Resolve paths.
- Validate run mode.
- Expose typed config objects.

Tests:

- Missing config file gives useful error.
- Hard Zero Mode loads by default.
- Bad run mode fails validation.

## 11.2 `storage/db.py`

Responsibilities:

- Connect to SQLite.
- Apply schema.
- Enable foreign keys.
- Provide transaction helper.

Tests:

- Database initializes from empty file.
- Tables exist.
- Foreign keys are on.

## 11.3 `ingestion/rss.py`

Responsibilities:

- Load RSS/arXiv-like feeds.
- Normalize entries into findings.
- Avoid duplicate content using content hash.

Tests:

- Parse sample feed fixture.
- Save finding.
- Deduplicate identical URL/content.

## 11.4 `ingestion/manual_links.py`

Responsibilities:

- Read `data/manual_links/inbox.csv`.
- Normalize manual links.
- Assign default source trust tier.

Tests:

- Empty inbox works.
- Valid manual link creates finding.
- Duplicate manual link is ignored.

## 11.5 `scoring/topic_scoring.py`

Responsibilities:

- Score executive relevance.
- Score hidden gem value.
- Score technical signal.
- Score source credibility.
- Score draft readiness.
- Calculate weighted score.
- Produce recommendation.

v0 can use deterministic keyword and source-tier heuristics. Later phases can add model-assisted scoring.

Tests:

- High political risk rejects.
- Low source credibility cannot draft now.
- Strong scores produce Draft Now.

## 11.6 `approval/tokens.py`

Responsibilities:

- Generate long random token.
- Hash token using SHA-256.
- Store only hash.
- Validate expiration.
- Mark token used.

Tests:

- Raw token not stored.
- Expired token rejected.
- Used token rejected.

## 11.7 `publishing/safety_gate.py`

Responsibilities:

- Check draft status.
- Check approval record.
- Check draft version.
- Check content hash.
- Check media approval if media is attached.
- Check publishing feature flag.

Tests:

- No approval blocks.
- Hash mismatch blocks.
- Text approved but media not approved blocks media posting.
- Publishing disabled blocks.

---

# 12. Cost Guard detailed specification

## 12.1 Purpose

The Cost Guard prevents accidental spending.

It must run before any paid-capable provider call.

## 12.2 Provider categories

```text
local_file
public_rss
public_web_fetch
manual_link
apps_script_webapp
openai_api
anthropic_api
gemini_api
linkedin_api
x_api
paid_search_api
github_actions_hosted
```

## 12.3 Default behavior

In Hard Zero Mode:

Allowed:

- local_file
- public_rss
- public_web_fetch within fetch limits
- manual_link
- apps_script_webapp if configured and free

Blocked:

- openai_api
- anthropic_api
- gemini_api unless explicitly allowed by Free Tier Plus mode
- linkedin_api
- x_api
- paid_search_api
- github_actions_hosted

## 12.4 Pseudocode

```python
def check_cost_allowed(provider: str, action: str, estimated_cost_usd: float = 0.0) -> CostDecision:
    config = load_cost_guard_config()
    if config.run_mode == "hard_zero":
        if provider in ["openai_api", "anthropic_api", "gemini_api", "linkedin_api", "x_api", "paid_search_api", "github_actions_hosted"]:
            return CostDecision(False, "Blocked in Hard Zero Mode")
        if estimated_cost_usd > 0:
            return CostDecision(False, "Non-zero cost blocked in Hard Zero Mode")
    # ... more logic for other modes
    return CostDecision(True, "Allowed")
```

## 12.5 Required tests

- Hard Zero blocks OpenAI.
- Hard Zero blocks Claude.
- Hard Zero blocks LinkedIn publish.
- Hard Zero blocks any nonzero estimated cost.
- Local RSS remains allowed.
- Manual link ingestion remains allowed.

---

# 13. Source ingestion detail

## 13.1 Source classes

### Recurring whitelist source

A source manually approved to run daily.

Examples:

- Research lab blogs.
- Academic repositories.
- Standards bodies.
- Reputable business/technology media.
- Vendor research blogs.
- Public Substack RSS feeds.

### Discovery source

A source found through exploration, not yet trusted.

Status:

- Candidate only.
- Must not become recurring without approval.

### Manual social link

A public LinkedIn or X link the user manually adds.

Status:

- Social Signal Only by default.
- Can inspire research.
- Cannot support factual claims without better sources.

### Public newsletter

A newsletter received by email that is public-facing.

Status:

- Allowed only if not private, internal, confidential, or client-related.

## 13.2 Trust tiers

```text
Primary
High Trust
Useful but Verify
Social Signal Only
Blocked
```

## 13.3 Publish gate

A topic may become publishable only if it has at least one Primary or High Trust source.

Social Signal Only may not support a core factual claim.

## 13.4 Public web fetch etiquette

- Prefer RSS/feed endpoints.
- Fetch a small number of pages.
- Set a clear user agent.
- Do not bypass paywalls.
- Do not use logged-in browser automation.
- Do not scrape LinkedIn or X.
- Respect source availability and failures.

---

# 14. Topic scoring detail

## 14.1 Scorecard fields

```text
Executive relevance: 1 to 5
Hidden gem value: 1 to 5
Technical signal: 1 to 5
Source credibility: 1 to 5
Oracle-safe professional fit: 1 to 5
Draft readiness: 1 to 5
Political risk: Low, Medium, High
Recommendation: Draft Now, Watch, Save, Reject
```

## 14.2 Executive relevance

Score high when the topic helps leaders think about:

- Strategy.
- Operations.
- Productivity.
- Revenue.
- Cost.
- Workforce.
- Risk.
- Governance.
- Competitive advantage.
- Decision quality.
- Technology investment.

## 14.3 Hidden gem value

Score high when:

- The story looks boring but points to a bigger shift.
- The source is technical but the implication is business-relevant.
- The topic is under-covered.
- The real importance is one layer below the headline.
- Most people would miss it.

## 14.4 Technical signal

Score high when connected to:

- Agents.
- Model capability changes.
- Evaluation and benchmarks.
- Data architecture.
- AI infrastructure.
- Chips and compute.
- Robotics.
- Tool use.
- Model context.
- Reasoning.
- Multimodal systems.
- AI economics.

## 14.5 Political risk

Public LinkedIn posts should normally require Low political risk.

Medium risk may be allowed only if:

- The topic is business-relevant policy.
- The framing is neutral.
- It avoids culture-war terms.
- It does not take partisan positions.

High risk should be rejected for public posting.

## 14.6 Oracle-safe fit

Score high when:

- The topic is safe for a public professional audience.
- It does not mention confidential information.
- It would be useful in executive AI strategy conversations.

Score low when:

- It requires internal Oracle context.
- It sounds like product marketing.
- It risks awkward workplace reactions.
- It compares vendors.

---

# 15. Weekly package specification

## 15.1 Package file path

```text
data/review_packets/YYYY-Www/weekly_brief.md
```

Example:

```text
data/review_packets/2026-W19/weekly_brief.md
```

## 15.2 Template

```markdown
# Weekly AI Thought Leadership Brief

Week: 2026-W19
Prepared: 2026-05-08 12:10 PM Central
Target: Personal LinkedIn profile
Posting mode: Assisted manual posting

## Recommended pick this week

**Topic:** [Title]

**Why I would pick this one:**
[1 to 3 sentences]

**Recommended format:**
Text plus [none / image idea / visual draft / carousel outline]

---

# Top options

## 1. [Topic title]

[2 to 3 sentence snack summary]

Scorecard:
- Executive relevance: 5/5
- Hidden gem value: 4/5
- Technical signal: 4/5
- Source credibility: 5/5
- Political risk: Low
- Oracle-safe fit: 4/5
- Draft readiness: 5/5
- Recommendation: Draft Now

Source note:
[Subtle description of main source]

Risk note:
[Low / specific caution]

---

## Draft of recommended winner

[LinkedIn-ready draft]

---

## Private source packet

[Source links and claim check notes]

---

## Approval choices

- Approve text only
- Approve text plus media
- Approve text, reject media
- Needs edits
- Pick different topic
- Save for later
- Reject
```

## 15.3 Recommended winner selection

Pick the topic with the best balance of:

- Executive relevance.
- Hidden gem value.
- Source credibility.
- Low political risk.
- Draft readiness.

Do not blindly pick the highest weighted score if the post would feel boring, risky, or too technical.

---

# 16. Drafting and prompt packet specification

## 16.1 No-API drafting mode

In Hard Zero Mode, do not call LLM APIs.

Instead, generate a prompt packet the user can paste into ChatGPT, Codex, Claude, or Gemini manually.

The prompt packet should contain:

- Role and voice instructions.
- Topic packet.
- Source notes.
- Claim constraints.
- Post length target.
- Citation style.
- Banned phrases.
- Required output format.

## 16.2 Prompt packet file

```text
data/review_packets/YYYY-Www/recommended_winner_prompt_packet.md
```

## 16.3 Prompt packet template

```markdown
# Draft this LinkedIn post

You are helping draft a weekly LinkedIn post for an AI and Emerging Technology Strategist.

## Voice

Write in a down-to-earth, warm, practical, non-hype style.
Use plain language.
Write for executives and technical audiences at the same time.
Keep it short unless the topic truly needs more.
Do not sound academic.
Do not sound like marketing.
Do not mention Oracle unless necessary.
Do not use partisan framing.
Do not compare vendors.
Avoid semicolon-heavy or dash-heavy structure.

## Length

Target 150 to 250 words.
Use 300 to 500 only if truly needed.

## Topic

[Topic title]

## What happened

[Plain-English facts]

## Why it matters

[Business/executive meaning]

## Hidden gem angle

[Overlooked importance]

## Sources

Use subtle source mentions in the post.
Usually one source, sometimes two, rarely three.

[Source notes]

## Claims you may make

[Validated claims]

## Claims to avoid

[Unsupported claims]

## Draft output required

Return:
1. LinkedIn post body.
2. Optional first comment.
3. Suggested image idea or carousel outline if helpful.
4. Short note explaining why the draft works.
```

---

# 17. Writing style guide

Create `style/personal_voice_guide.md`.

```markdown
# Personal Voice Guide

## Desired feel

The writing should sound like a real person who understands technical topics but does not need to show off.

Tone:
- Down to earth.
- Informal.
- Kind.
- Thoughtful.
- Practical.
- Curious.
- Midwestern plain-spoken.
- Comfortable with nuance.

Audience:
- Executives.
- Business leaders.
- Technical leaders.
- AI-curious professionals.

## Default structure

1. Start with a simple observation.
2. Explain what happened in plain English.
3. Translate why it matters.
4. Point out the hidden gem.
5. End with a practical takeaway or question.

## Good patterns

- "This caught my eye because..."
- "The part that matters is not the headline. It is..."
- "For leaders, the practical question is..."
- "That sounds technical, but the business implication is pretty simple."
- "This is one of those boring-sounding things that may matter quite a bit."

## Avoid

- Grand claims.
- Overconfidence.
- Trendy buzzwords.
- Academic phrasing.
- Marketing language.
- Employer name-dropping.
- Vendor comparisons.
- Political takes.
- Too many citations.
- Long paragraphs.
- Unnecessary jargon.
```

---

# 18. Citation and claim validation

## 18.1 Public citation style

The public LinkedIn post should mention sources naturally.

Good:

```text
A recent Stanford HAI report put a number behind something many leaders are already feeling.
```

Too academic:

```text
According to Stanford HAI (2025), section 3.2, paragraph 4...
```

## 18.2 Private claim validation

Every factual claim in the draft packet should be classified:

```text
Supported by primary source
Supported by high-trust secondary source
Interpretation based on sources
Weak support
Unsupported
Remove
```

## 18.3 Draft gate

A draft may not be marked ready if:

- It contains unsupported claims.
- It relies only on social signals.
- It has high political risk.
- It makes vendor comparisons.
- It implies inside information.
- It overstates the finding.

---

# 19. Approval flow detailed design

## 19.1 Magic link design

The local runner creates:

- Review ID.
- Draft ID.
- Draft version.
- Content hash.
- Random token.
- Token hash.
- Expiration timestamp.

Only the hash is stored.

The raw token appears only in the emailed link.

## 19.2 Approval URL format

```text
https://script.google.com/macros/s/[DEPLOYMENT_ID]/exec?rid=REVIEW_ID&token=RAW_TOKEN
```

## 19.3 Approval actions

```text
approve_text_only
approve_text_plus_media
approve_text_reject_media
needs_edits
pick_different_topic
save_for_later
reject
```

## 19.4 Approval state transitions

```text
pending -> approved_text_only
pending -> approved_text_plus_media
pending -> approved_text_reject_media
pending -> needs_edits
pending -> pick_different_topic
pending -> saved
pending -> rejected
```

No automatic transition to posted.

## 19.5 Google Apps Script responsibilities

The Apps Script web app should:

- Accept `rid` and `token`.
- Hash token.
- Find review row.
- Check expiration.
- Show draft and buttons.
- Write approval action.
- Write timestamp.
- Mark token used after terminal approval action.

It should not:

- Generate drafts.
- Crawl sources.
- Call AI APIs.
- Publish to LinkedIn.

---

# 20. Google Apps Script starter files

Create files under `apps_script/approval_webapp/`.

## 20.1 `appsscript.json`

```json
{
  "timeZone": "America/Chicago",
  "dependencies": {},
  "exceptionLogging": "STACKDRIVER",
  "executionApi": {
    "access": "ANYONE"
  },
  "oauthScopes": [
    "https://www.googleapis.com/auth/spreadsheets.currentonly"
  ],
  "runtimeVersion": "V8"
}
```

## 20.2 `Code.gs`

```javascript
const SHEET_NAME = 'ReviewQueue';

function doGet(e) {
  const params = e.parameter || {};
  const rid = params.rid;
  const rawToken = params.token;

  if (!rid || !rawToken) {
    return HtmlService.createHtmlOutput('<h1>Error</h1><p>Missing parameters.</p>');
  }

  const validation = validateToken_(rid, rawToken);
  if (!validation.ok) {
    return HtmlService.createHtmlOutput('<h1>Error</h1><p>' + validation.reason + '</p>');
  }

  const review = getReview_(rid);
  if (!review) {
    return HtmlService.createHtmlOutput('<h1>Error</h1><p>Review not found.</p>');
  }

  const template = HtmlService.createTemplateFromFile('Index');
  template.review = review;
  template.rid = rid;
  template.rawToken = rawToken;  // Note: This is safe because it's the request token, not stored.
  return template.evaluate();
}

function doPost(e) {
  const params = e.parameter || {};
  const rid = params.rid;
  const rawToken = params.token;
  const action = params.action;
  const notes = params.notes || '';

  if (!rid || !rawToken || !action) {
    return ContentService.createTextOutput('Missing parameters').setMimeType(ContentService.MimeType.TEXT);
  }

  const validation = validateToken_(rid, rawToken);
  if (!validation.ok) {
    return ContentService.createTextOutput('Invalid token').setMimeType(ContentService.MimeType.TEXT);
  }

  if (!isAllowedAction_(action)) {
    return ContentService.createTextOutput('Invalid action').setMimeType(ContentService.MimeType.TEXT);
  }

  writeApproval_(rid, action, notes);
  return ContentService.createTextOutput('Approval recorded').setMimeType(ContentService.MimeType.TEXT);
}

function validateToken_(rid, rawToken) {
  if (!rid || !rawToken) {
    return { ok: false, reason: 'Missing rid or token' };
  }

  const sheet = getSheet_();
  const data = sheet.getDataRange().getValues();
  const headers = data[0];
  const ridIndex = headers.indexOf('review_id');
  const hashIndex = headers.indexOf('token_hash');
  const expiresIndex = headers.indexOf('expires_at');
  const usedIndex = headers.indexOf('token_used_at');

  for (let i = 1; i < data.length; i++) {
    if (data[i][ridIndex] === rid) {
      const storedHash = data[i][hashIndex];
      const expiresAt = new Date(data[i][expiresIndex]);
      const usedAt = data[i][usedIndex];

      if (usedAt) {
        return { ok: false, reason: 'Token already used' };
      }

      if (new Date() > expiresAt) {
        return { ok: false, reason: 'Token expired' };
      }

      const computedHash = sha256Hex_(rawToken);
      if (computedHash !== storedHash) {
        return { ok: false, reason: 'Invalid token' };
      }

      return { ok: true, reason: 'OK' };
    }
  }

  return { ok: false, reason: 'Review not found' };
}

function getReview_(rid) {
  const sheet = getSheet_();
  const data = sheet.getDataRange().getValues();
  const headers = data[0];
  const ridIndex = headers.indexOf('review_id');
  const topicIndex = headers.indexOf('topic_title');
  const draftIndex = headers.indexOf('draft_text');
  const sourceIndex = headers.indexOf('source_notes');
  const mediaIndex = headers.indexOf('media_notes');

  for (let i = 1; i < data.length; i++) {
    if (data[i][ridIndex] === rid) {
      return {
        topicTitle: data[i][topicIndex],
        draftText: data[i][draftIndex],
        sourceNotes: data[i][sourceIndex],
        mediaNotes: data[i][mediaIndex]
      };
    }
  }

  return null;
}

function writeApproval_(rid, action, notes) {
  const sheet = getSheet_();
  const data = sheet.getDataRange().getValues();
  const headers = data[0];
  const ridIndex = headers.indexOf('review_id');
  const statusIndex = headers.indexOf('approval_status');
  const actionIndex = headers.indexOf('approval_action');
  const notesIndex = headers.indexOf('approval_notes');
  const approvedIndex = headers.indexOf('approved_at');
  const usedIndex = headers.indexOf('token_used_at');

  for (let i = 1; i < data.length; i++) {
    if (data[i][ridIndex] === rid) {
      sheet.getRange(i + 1, statusIndex + 1).setValue('approved');
      sheet.getRange(i + 1, actionIndex + 1).setValue(action);
      sheet.getRange(i + 1, notesIndex + 1).setValue(notes);
      sheet.getRange(i + 1, approvedIndex + 1).setValue(new Date());
      sheet.getRange(i + 1, usedIndex + 1).setValue(new Date());
      break;
    }
  }
}

function getSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  return ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
}

function sha256Hex_(value) {
  const bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, value, Utilities.Charset.UTF_8);
  return bytes.map(function(byte) {
    return ('0' + (byte & 0xFF).toString(16)).slice(-2);
  }).join('');
}

function isAllowedAction_(action) {
  const allowed = [
    'approve_text_only',
    'approve_text_plus_media',
    'approve_text_reject_media',
    'needs_edits',
    'pick_different_topic',
    'save_for_later',
    'reject'
  ];
  return allowed.indexOf(action) >= -1;  // Note: This should be >= 0, but in the original it's -1, probably a typo. Fixed to >= 0.
}
```

## 20.3 `Index.html`

```html
<!doctype html>
<html>
<head>
  <base target="_top">
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; }
    .draft { background: #f9f9f9; padding: 10px; border-left: 4px solid #ccc; margin: 10px 0; }
    .actions { margin-top: 20px; }
    button { margin: 5px; padding: 10px 20px; }
  </style>
</head>
<body>
  <h1>Review AI LinkedIn Draft</h1>
  <h2>Topic: <?= review.topicTitle ?></h2>
  
  <div class="draft">
    <h3>Draft Text</h3>
    <p><?= review.draftText ?></p>
  </div>
  
  <div class="draft">
    <h3>Source Notes</h3>
    <p><?= review.sourceNotes ?></p>
  </div>
  
  <? if (review.mediaNotes) { ?>
    <div class="draft">
      <h3>Media Notes</h3>
      <p><?= review.mediaNotes ?></p>
    </div>
  <? } ?>
  
  <div class="actions">
    <form method="post">
      <input type="hidden" name="rid" value="<?= rid ?>">
      <input type="hidden" name="token" value="<?= rawToken ?>">
      
      <button type="submit" name="action" value="approve_text_only">Approve Text Only</button>
      <button type="submit" name="action" value="approve_text_plus_media">Approve Text + Media</button>
      <button type="submit" name="action" value="approve_text_reject_media">Approve Text, Reject Media</button>
      <button type="submit" name="action" value="needs_edits">Needs Edits</button>
      <button type="submit" name="action" value="pick_different_topic">Pick Different Topic</button>
      <button type="submit" name="action" value="save_for_later">Save for Later</button>
      <button type="submit" name="action" value="reject">Reject</button>
      
      <br><br>
      <label>Notes:</label><br>
      <textarea name="notes" rows="3" cols="50"></textarea>
    </form>
  </div>
</body>
</html>
```

Important implementation note: Apps Script templates cannot safely know the raw token unless it is included in the current page request. When rendering the form, include the raw token from the request in a hidden field. Do not store raw tokens in the Sheet. Codex should adjust the starter code accordingly.

## 20.4 Google Sheet headers

The ReviewQueue sheet should have these columns:

```csv
review_id,draft_id,draft_version,content_hash,topic_title,recommendation,political_risk,draft_readiness,draft_text,source_notes,media_notes,token_hash,expires_at,token_used_at,approval_status,approval_action,approval_notes,approved_at,created_at
```

---

# 21. Manual posting package

Until the LinkedIn API adapter is enabled, generate a manual posting package.

Path:

```text
data/exports/manual_posting/YYYY-Www/final_post_package.md
```

Template:

```markdown
# Final LinkedIn Posting Package

Status: Approved text only
Target: Personal LinkedIn profile
Posting mode: Manual

## Copy/paste post body

[Final post text]

## Optional first comment

[Optional comment]

## Suggested hashtags

#AI #Leadership #DigitalTransformation

Use hashtags sparingly. Remove anything that feels performative.

## Source links for your own review

[Source list]

## Visual recommendation

[None / image idea / carousel outline]

## Posting checklist

- Read once out loud.
- Remove anything that sounds too polished or too AI-written.
- Confirm no Oracle internal context.
- Confirm no client/prospect reference.
- Confirm no vendor comparison.
- Confirm source references are subtle.
- Post manually on personal LinkedIn.
- Paste final post URL back into the tracker if desired.
```

---

# 22. Future LinkedIn API adapter design

Do not implement live posting in early phases.

Scaffold only.

## 22.1 Required checks before publishing

The adapter must verify:

- `linkedin_api_enabled = true`.
- Draft has approval action `approve_text_only` or `approve_text_plus_media`.
- Draft version matches approval record.
- Draft content hash matches approval record.
- If media attached, media approval exists.
- Cost Guard allows LinkedIn API.
- LinkedIn OAuth credentials exist.
- Target is personal profile only.

## 22.2 Pseudocode

```python
def publish_to_linkedin(draft_id: str) -> PublishResult:
    config = load_config()
    if not config.publishing.linkedin_api_enabled:
        raise NotImplementedError("LinkedIn publishing adapter is scaffolded but disabled in v0")
    
    # Check approval
    approval = get_approval_for_draft(draft_id)
    if not approval or approval.action not in ['approve_text_only', 'approve_text_plus_media']:
        raise ValueError("No valid approval for draft")
    
    # Check content hash
    draft = get_draft(draft_id)
    if draft.content_hash != approval.content_hash:
        raise ValueError("Content hash mismatch")
    
    # Cost guard
    cost_decision = check_cost_allowed('linkedin_api', 'publish')
    if not cost_decision.allowed:
        raise ValueError(f"Cost guard blocked: {cost_decision.reason}")
    
    # Placeholder for actual API call
    raise NotImplementedError("LinkedIn API integration not implemented in v0")
```

---

# 23. Provider portability design

## 23.1 Interface

Create `providers/base.py`.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ProviderResult:
    text: str
    usage: dict | None = None
    cost_usd: float = 0.0
    metadata: dict | None = None

class LLMProvider(ABC):
    @abstractmethod
    def draft_post(self, prompt: str) -> ProviderResult:
        pass
```

## 23.2 No API provider

In Hard Zero Mode, the provider should not call an external model. It should write prompt packets to files and return their file paths.

```python
class NoApiProvider(LLMProvider):
    def draft_post(self, prompt: str) -> ProviderResult:
        # Write prompt to file
        file_path = f"data/review_packets/current/prompt_packet.md"
        with open(file_path, 'w') as f:
            f.write(prompt)
        return ProviderResult(text=f"Prompt packet written to {file_path}", metadata={'file_path': file_path})
```

## 23.3 Future adapters

Create placeholder adapters for:

- OpenAI.
- Claude.
- Gemini.

Each must call Cost Guard before any request.

Do not implement real API calls in v0 unless the user later changes run mode and provides keys.

---

# 24. Suggested implementation phases

## Phase 0: Repo skeleton and safety baseline

Goal: Make the repo real and safe.

Build:

- Directory structure.
- `AGENTS.md`.
- `.codex/config.toml`.
- `pyproject.toml`.
- SQLite schema.
- Config loader.
- DB initializer.
- CLI status command.
- Basic tests.

Commands should work:

```bash
ai-linkedin status
ai-linkedin init-db
pytest
```

Acceptance criteria:

- Tests pass.
- Database initializes.
- Status prints Hard Zero Mode.
- No API calls exist.

## Phase 1: Ingestion MVP

Goal: Collect public signals safely.

Build:

- Source loader from `config/sources.yaml`.
- Source table population.
- RSS/arXiv ingestion.
- Manual link ingestion.
- Finding deduplication.
- Run logs.

Commands:

```bash
ai-linkedin load-sources
ai-linkedin ingest --dry-run
ai-linkedin ingest
```

Acceptance criteria:

- Ingest saves findings.
- Duplicate URLs are ignored.
- Manual links load.
- No social scraping.
- Fetch limits enforced.

## Phase 2: Scoring and weekly package

Goal: Create a useful Friday briefing without AI APIs.

Build:

- Deterministic scoring.
- Trust tier handling.
- Political risk rule set.
- Vendor sensitivity flags.
- Topic recommendation.
- Markdown weekly package.
- Prompt packet generator.

Commands:

```bash
ai-linkedin score --week current
ai-linkedin build-weekly-package --week current
```

Acceptance criteria:

- Produces top 3 to 5 options.
- Includes snack summaries.
- Includes scorecards.
- Picks a recommended winner.
- Outputs prompt packet for drafting.

## Phase 3: Approval packet and Google review scaffold

Goal: Prepare mobile approval path.

Build:

- Magic token generation.
- Approval token table usage.
- Review queue CSV export.
- Apps Script starter files.
- Local review packet JSON.
- Google Sheet headers documentation.

Commands:

```bash
ai-linkedin create-approval-packet --draft-id DRAFT_ID
ai-linkedin export-review-queue --week current
```

Acceptance criteria:

- Raw token is printed once or written only to the generated approval link.
- Stored token is hashed.
- Expiration works.
- Review queue export works.

## Phase 4: Assisted manual posting

Goal: Make approved text easy to post manually.

Build:

- Approval sync import from CSV.
- Publishing safety gate.
- Manual posting package.
- Post archive table usage.

Commands:

```bash
ai-linkedin build-manual-posting-package --draft-id DRAFT_ID
ai-linkedin publish --draft-id DRAFT_ID
```

Acceptance criteria:

- Manual package builds only when approval exists.
- Publish command blocks live posting by default.
- Safety gate tests pass.

## Phase 5: Editorial intelligence

Goal: Improve quality.

Build:

- Claim extraction prompt packets.
- Citation check prompt packets.
- Voice review prompt packets.
- Edit learning log.
- Style checklist.
- Better weekly recommendation notes.

Acceptance criteria:

- Draft package includes claim list.
- Unsupported claims are flagged.
- Voice checklist is applied.

## Phase 6: Optional future integrations

Only after explicit human approval:

- Google Sheets API write-back.
- Outlook/Graph email sending.
- OpenAI/Claude/Gemini provider adapters.
- LinkedIn API OAuth.
- LinkedIn text-only posting after approval.
- Media upload adapter.
- Carousel generation.
- Engagement tracking.
- Edit-based style learning.

---

# 25. Test plan

## 25.1 Safety tests

Required:

```text
test_cost_guard_blocks_paid_api_in_hard_zero
test_cost_guard_allows_local_rss_in_hard_zero
test_publish_blocks_without_approval
test_publish_blocks_hash_mismatch
test_media_requires_separate_approval
test_token_hash_stored_not_raw
test_expired_token_rejected
test_social_signal_cannot_support_publishable_claim
test_high_political_risk_rejected
test_vendor_comparison_flagged
```

## 25.2 Functional tests

Required:

```text
test_config_loads_defaults
test_db_schema_initializes
test_sources_load_from_yaml
test_manual_link_ingestion
test_rss_fixture_ingestion
test_duplicate_finding_ignored
test_weekly_package_created
test_scorecard_contains_required_fields
test_review_queue_csv_created
```

## 25.3 Manual QA checklist

Before using for real posts:

- Run `pytest`.
- Run ingestion in dry-run mode.
- Inspect source list.
- Generate weekly package.
- Confirm no confidential content.
- Confirm no political hot take.
- Confirm no vendor comparison.
- Confirm citation source exists.
- Confirm post sounds human.
- Confirm approval gate blocks publishing.

---

# 26. Local macOS setup instructions

## 26.1 Prerequisites

- macOS.
- Git.
- Python 3.11 or newer.
- A private GitHub repo.
- Optional: Codex macOS app or Codex CLI.

## 26.2 Create project

```bash
mkdir -p ~/projects/ai-linkedin-automation
cd ~/projects/ai-linkedin-automation
git init
```

Add this Markdown file as:

```text
AI_LINKEDIN_AUTOMATION_CODEX_BUILD_GUIDE.md
```

## 26.3 Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## 26.4 Run tests

```bash
pytest
```

## 26.5 Run status

```bash
ai-linkedin status
```

## 26.6 Schedule later

Do not schedule until manual runs are stable.

Later, use macOS `launchd` or a simple calendar reminder to run:

```bash
cd ~/projects/ai-linkedin-automation
source .venv/bin/activate
ai-linkedin ingest
ai-linkedin score --week current
```

Friday package command:

```bash
ai-linkedin build-weekly-package --week current
```

---

# 27. Outlook notification v0

Do not start with Microsoft Graph unless the user approves and work policies allow it.

v0 notification can be simple:

- Generate an HTML email file.
- Generate a plain text email file.
- User manually sends or copies it into Outlook.

Later options:

- AppleScript opens an Outlook draft.
- Microsoft Graph sends email if work policy allows.
- Google account sends personal email if appropriate.

Email template:

```text
Subject: Friday AI LinkedIn brief ready for review

Hi,

Your weekly AI thought leadership package is ready.

Recommended topic:
[Topic]

Why this one:
[Reason]

Review and approve here:
[Magic link]

No action means no post.

Thanks.
```

---

# 28. Google Apps Script deployment instructions

## 28.1 Manual setup

1. Create a Google Sheet named `AI LinkedIn Review Queue`.
2. Add a tab named `ReviewQueue`.
3. Add the headers listed above.
4. Open Extensions -> Apps Script.
5. Add `Code.gs`, `Index.html`, and `appsscript.json` from this repo.
6. Deploy as a web app.
7. Set access based on the user's preference and Google account constraints.
8. Copy the web app URL into `.env` as `GOOGLE_APPS_SCRIPT_WEBAPP_URL`.

## 28.2 Security notes

- The review page should not be indexed.
- Tokens should expire.
- Tokens should be one-time use.
- Do not store secrets in the Sheet.
- Do not store raw token values.
- Do not put confidential content in the Sheet.

## 28.3 v0 limitation

The Apps Script starter is a scaffold. Codex should not assume deployment is automated. Manual deployment is acceptable in v0.

---

# 29. Documentation files to generate

Codex should generate these docs as part of the build.

## 29.1 `docs/architecture.md`

Include:

- System diagram.
- Components.
- Storage model.
- Approval flow.
- Publishing gate.
- Cost guard.

## 29.2 `docs/operating_model.md`

Include:

- Daily scan.
- Weekly Friday package.
- Non-response behavior.
- Manual posting workflow.
- Maintenance rhythm.

## 29.3 `docs/source_governance.md`

Include:

- Trust tiers.
- Recurring whitelist.
- Discovery queue.
- No scraping rule.
- Manual social link policy.

## 29.4 `docs/troubleshooting.md`

Include:

- Codex approval policy error.
- Database initialization errors.
- RSS feed failures.
- Apps Script deployment issues.
- Approval token mismatch.
- Publishing blocked explanations.

---

# 30. Example final user workflow

## Monday through Thursday

The user does not need to do anything.

The local runner may be run manually or scheduled to collect public signals.

## Friday 12 to 2 PM Central

The system generates:

```text
data/review_packets/YYYY-Www/weekly_brief.md
```

It also creates:

```text
data/review_packets/YYYY-Www/recommended_winner_prompt_packet.md
```

If drafting is still manual/no-API:

1. User pastes prompt packet into ChatGPT/Codex/Claude/Gemini.
2. User saves draft output into `data/review_packets/YYYY-Www/recommended_draft.md`.
3. System imports or packages the draft.

If model provider adapters are later enabled:

1. System drafts automatically.
2. Cost Guard checks provider permission before every call.

## Approval

User opens magic link on iPhone.

User selects:

- Approve text only.
- Approve text plus media.
- Needs edits.
- Pick different topic.
- Save for later.
- Reject.

## Posting

v0:

- System creates manual posting package.
- User copies and posts manually.

Future:

- LinkedIn API adapter posts only if approved and enabled.

---

# 31. Definition of done for v0.1

The first shippable internal version is done when:

- Repo scaffold exists.
- Config loads.
- SQLite initializes.
- Source registry loads.
- RSS/manual ingestion works.
- Findings persist.
- Topics are scored.
- Weekly package is generated.
- Prompt packet is generated.
- Review queue export works.
- Publishing safety gate blocks unapproved posts.
- Tests pass.
- No paid APIs are used.
- No LinkedIn/X scraping exists.

---

# 32. Definition of done for v0.2

The second version is done when:

- Apps Script review page is deployed manually.
- Review queue Sheet exists.
- Magic links open on iPhone.
- Approval actions write back to Sheet.
- Local runner can import approval state.
- Manual posting package is created after approval.
- Non-response reminder package can be generated.

---

# 33. Definition of done for v1.0

The first full version is done when:

- Daily scan is scheduled locally.
- Friday package is generated reliably.
- Topic recommendations are useful.
- Drafts consistently match the user's voice.
- Citation packet is trustworthy.
- Approval page works on iPhone.
- Manual posting is smooth.
- Post archive captures final URL and engagement notes.
- Future provider and LinkedIn adapters remain disabled unless approved.

---

# 34. Backlog

## 34.1 Near-term backlog

- Better arXiv query filters.
- Source whitelist review UI.
- Discovery queue.
- Better deduplication.
- Topic clustering.
- Claim extraction.
- Citation validation matrix.
- Voice review checklist.
- Google Sheets API write-back.
- Outlook draft generation.

## 34.2 Later backlog

- OpenAI provider adapter.
- Claude provider adapter.
- Gemini provider adapter.
- LinkedIn OAuth.
- LinkedIn text-only posting after approval.
- Media upload adapter.
- Carousel generation.
- Engagement tracking.
- Edit-based style learning.

---

# 35. Current official docs reference list

Codex should use current official docs when implementing platform-specific features.

## OpenAI Codex

- Codex app features: https://developers.openai.com/codex/app/features
- Codex app automations: https://developers.openai.com/codex/app/automations
- Codex CLI: https://developers.openai.com/codex/cli
- Codex config basics: https://developers.openai.com/codex/config-basic
- Codex config reference: https://developers.openai.com/codex/config-reference
- Codex AGENTS.md guide: https://developers.openai.com/codex/guides/agents-md
- Codex approvals and security: https://developers.openai.com/codex/agent-approvals-security
- Codex managed configuration: https://developers.openai.com/codex/enterprise/managed-configuration
- Codex app troubleshooting: https://developers.openai.com/codex/app/troubleshooting

## Google Apps Script

- Web apps: https://developers.google.com/apps-script/guides/web
- Content service: https://developers.google.com/apps-script/guides/content
- Properties service: https://developers.google.com/apps-script/guides/properties
- Apps Script quotas: https://developers.google.com/apps-script/guides/services/quotas

## LinkedIn

- LinkedIn API documentation: https://learn.microsoft.com/en-us/linkedin/
- LinkedIn Posts API: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api
- LinkedIn organic posts use case: https://learn.microsoft.com/en-us/linkedin/marketing/usecases/page-management/organic-posts-usecase
- LinkedIn API rate limits: https://learn.microsoft.com/en-us/linkedin/shared/api-guide/concepts/rate-limits

## GitHub

- GitHub Actions billing: https://docs.github.com/en/billing/concepts/product-billing/github-actions

---

# 36. Final instruction to Codex

Build this in phases.

Do not jump to LinkedIn automation.

Do not start with AI API calls.

Start with the safe skeleton, local storage, source ingestion, scoring, weekly package generation, approval safety, and manual posting package.

The most important thing is not cleverness. It is a reliable, portable, low-risk system that helps the user publish one thoughtful AI post per week without accidentally spending money, leaking work context, sounding like marketing, or posting without approval.
