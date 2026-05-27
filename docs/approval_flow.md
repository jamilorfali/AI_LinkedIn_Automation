# Approval Flow

The local runner creates:
- Review ID.
- Draft ID.
- Draft version.
- Draft content hash.
- Random token.
- Token hash.
- Expiration timestamp.
- Editorial review notes.
- Claim support checklist.
- Voice/style checklist.

Only the token hash is stored. The raw token is shown once or included in the approval URL.

Allowed actions:
- `approve_text_only`
- `approve_text_plus_media`
- `approve_text_reject_media`
- `needs_edits`
- `pick_different_topic`
- `save_for_later`
- `reject`

No approval action automatically posts anything.

Approval packet creation runs deterministic editorial review first, then writes the review path, claim notes, and voice checklist into the local packet JSON.
It also writes a citation matrix and includes citation summary counts in the packet JSON.

## Notification Package

The local runner can also create copyable Outlook files:

```bash
ai-linkedin build-notification-package --draft-id DRAFT_ID --week current
```

This creates:
- Plain text email file.
- HTML email file.
- Metadata JSON.
- Approval packet JSON.
- Review queue CSV for the `ReviewQueue` sheet.

No email is sent automatically. No approval action automatically posts anything.

## Apps Script QA

Validate and package the approval web app locally:

```bash
ai-linkedin validate-approval-webapp
ai-linkedin build-approval-deployment-package --week current
```

Run the isolated local round-trip QA:

```bash
ai-linkedin run-approval-qa --action approve_text_only --week current
```

This creates a throwaway QA database, approval packet, review queue CSV, simulated Sheet export, imported approval record, and manual posting package. It does not call Google, send email, or publish to LinkedIn.

## CSV Sync

When the Google Sheet review queue is edited or the Apps Script writes an approval action, export the sheet as CSV and run:

```bash
ai-linkedin import-review-queue --csv path/to/review_queue.csv
```

The importer validates:
- Review ID exists.
- Draft ID matches.
- Draft version matches.
- Content hash matches.
- Approval action is allowed.

Rows without approval actions are skipped.
