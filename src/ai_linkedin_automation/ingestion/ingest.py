import csv
import hashlib
import time

from ai_linkedin_automation.config import Config, project_root
from ai_linkedin_automation.cost_guard import require_cost_allowed
from ai_linkedin_automation.storage.db import connect_db, transaction


def _stable_finding_id(source_id: str, url: str, content_hash: str) -> str:
    digest = hashlib.sha256(f"{source_id}|{url}|{content_hash}".encode()).hexdigest()[:24]
    return f"finding_{digest}"


def _content_hash(title: str, summary: str, url: str = "") -> str:
    normalized = " ".join([title.strip(), summary.strip(), url.strip()]).lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def _rss_published_at(entry) -> str:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if parsed:
        return time.strftime("%Y-%m-%dT%H:%M:%S", parsed)
    return getattr(entry, "published", "") or getattr(entry, "updated", "")

def ingest_rss_feed(config: Config, source_id: str, rss_url: str, dry_run: bool = False):
    """Ingest findings from an RSS feed"""
    if dry_run:
        print(f"Would fetch RSS: {rss_url}")
        return []

    require_cost_allowed("public_rss", f"fetch:{source_id}", 0.0)

    try:
        import feedparser
        feed = feedparser.parse(rss_url)
        findings = []

        for entry in feed.entries:
            title = getattr(entry, "title", "").strip()
            summary = getattr(entry, "summary", None) or getattr(entry, "description", "")
            url = getattr(entry, "link", "").strip()
            if not title or not url:
                continue
            content_hash = _content_hash(title, summary, url)

            finding = {
                'id': _stable_finding_id(source_id, url, content_hash),
                'source_id': source_id,
                'url': url,
                'title': title,
                'summary': summary,
                'published_at': _rss_published_at(entry),
                'content_hash': content_hash,
                'raw_content': f"{title}\n\n{summary}"
            }
            findings.append(finding)

        return findings
    except Exception as e:
        print(f"Error fetching RSS {rss_url}: {e}")
        return []

def ingest_manual_links(config: Config, dry_run: bool = False):
    """Ingest findings from manual links CSV"""
    require_cost_allowed("manual_link", "read_inbox", 0.0)
    inbox_file = project_root() / "data" / "manual_links" / "inbox.csv"

    if not inbox_file.exists():
        return []

    findings = []
    with open(inbox_file, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get("url") or "").strip()
            title = (row.get("title") or "").strip()
            notes = (row.get("notes") or "").strip()
            added_at = (row.get("added_at") or "").strip()
            if not url or not title:
                continue

            content_hash = _content_hash(title, notes, url)
            finding = {
                'id': _stable_finding_id("manual_link_inbox", url, content_hash),
                'source_id': 'manual_link_inbox',
                'url': url,
                'title': title,
                'summary': notes,
                'published_at': added_at,
                'content_hash': content_hash,
                'raw_content': f"{title} {notes}"
            }
            findings.append(finding)

    if dry_run:
        print(f"Would ingest {len(findings)} manual links")

    return findings

def save_findings(config: Config, findings: list):
    """Save findings to database with deduplication"""
    with transaction(config.storage.sqlite_path) as conn:
        saved_count = 0
        for finding in findings:
            # Check if finding already exists
            existing = conn.execute(
                'SELECT id FROM findings WHERE content_hash = ? OR url = ?',
                (finding['content_hash'], finding['url']),
            ).fetchone()
            if existing:
                continue  # Skip duplicate

            # Insert finding
            conn.execute('''
                INSERT INTO findings
                (
                    id, source_id, url, title, summary, published_at, discovered_at,
                    content_hash, raw_content, raw_excerpt, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?, 'new', datetime('now'))
            ''', (
                finding['id'],
                finding['source_id'],
                finding['url'],
                finding['title'],
                finding['summary'],
                finding['published_at'],
                finding['content_hash'],
                finding['raw_content'],
                (finding['summary'] or finding['raw_content'] or '')[:500],
            ))
            saved_count += 1

        return saved_count

def run_ingestion(config: Config, dry_run: bool = False):
    """Run full ingestion process"""
    conn = connect_db(config.storage.sqlite_path)
    try:
        # Get active sources
        cursor = conn.execute('SELECT id, type, rss_url FROM sources WHERE is_active = 1')
        sources = cursor.fetchall()

        all_findings = []

        for source_id, source_type, rss_url in sources:
            if source_type == 'rss' and rss_url:
                findings = ingest_rss_feed(config, source_id, rss_url, dry_run)
                all_findings.extend(findings)
            elif source_type == 'manual':
                findings = ingest_manual_links(config, dry_run)
                all_findings.extend(findings)
        
        if dry_run:
            print(f"Would save {len(all_findings)} findings")
        else:
            saved = save_findings(config, all_findings)
            print(f"Saved {saved} new findings")

            # Log the run
            conn.execute('''
                INSERT INTO runs (started_at, completed_at, run_type, status, notes)
                VALUES (datetime('now'), datetime('now'), 'ingestion', 'completed', ?)
            ''', (f"Saved {saved} findings",))
            conn.commit()
            
    finally:
        conn.close()
