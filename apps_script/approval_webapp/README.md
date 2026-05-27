# Approval Web App

This folder contains the Google Apps Script scaffold for mobile review.

## Sheet Headers

```csv
review_id,draft_id,draft_version,content_hash,topic_title,recommendation,political_risk,draft_readiness,draft_text,source_notes,media_notes,token_hash,expires_at,token_used_at,approval_status,approval_action,approval_notes,approved_at,created_at
```

## One-Time Deployment

1. Create a Google Sheet with a `ReviewQueue` tab.
2. Open Extensions -> Apps Script.
3. Add `Code.gs`, `Index.html`, and `appsscript.json` from the generated deployment package.
4. Use the packaged `Code.gs` because it includes the local console sync token.
5. Click Save in Apps Script.
6. If this is the existing approval app, click Deploy -> Manage deployments -> pencil icon -> Version -> New version -> Deploy. This keeps the same saved `/exec` URL.
7. If this is the first deployment, click Deploy -> New deployment.
8. For a first deployment, click the gear icon beside Select type and choose Web app.
9. If you only see API Executable, save, reload Apps Script, confirm `Code.gs` contains `doGet`, and confirm `appsscript.json` contains a `webapp` block.
10. Set Execute as to Me. Set access according to your Google account constraints.
11. Put the web app URL in `.env` as `GOOGLE_APPS_SCRIPT_WEBAPP_URL`, or paste it into the Approve tab and press Save URL.

After deployment, the AI LinkedIn Console can upload the review queue and import phone decisions through the web app. You should not need to review or export the Sheet manually.

The Apps Script does not call AI APIs and does not publish to LinkedIn.
