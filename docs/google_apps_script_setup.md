# Google Apps Script Setup

Use the browser console for this. No Terminal or code editor is required.

## In The AI LinkedIn Console

1. Click **Prepare Phone Approval**.
2. Click **View Approval Setup**.
3. Click **Open New Google Sheet**.
4. Click **Copy Sheet Header**.

## In Google Sheets

1. Rename the spreadsheet to `AI LinkedIn Review Queue`.
2. Rename the first tab to `ReviewQueue`.
3. Select cell A1.
4. Paste the copied header row.
5. Open **Extensions -> Apps Script**.

## In Google Apps Script

1. Delete the default placeholder code in `Code.gs`.
2. Return to the AI LinkedIn Console and click **Copy Code.gs**.
3. Paste it into the Apps Script `Code.gs` file.
4. Create a new HTML file named `Index`.
5. Return to the AI LinkedIn Console and click **Copy Index.html**.
6. Paste it into `Index.html`.
7. Open Apps Script **Project Settings**.
8. Enable **Show appsscript.json manifest file in editor**.
9. Open `appsscript.json`.
10. Return to the AI LinkedIn Console and click **Copy appsscript.json**.
11. Replace the manifest contents with the copied text.
12. Click **Save project**.

## Deploy As Web App

1. Click **Deploy -> New deployment**.
2. Choose **Web app** as the deployment type.
3. Set **Execute as** to yourself.
4. Set **Who has access** according to your Google account constraints.
5. Click **Deploy** and authorize the requested spreadsheet-only permission.
6. Copy the deployed web app URL.

## Back In The AI LinkedIn Console

1. Paste the web app URL into **Approval Setup**.
2. Click **Save URL**.
3. Click **Mark Approval Page Deployed**.
4. Click **Run Safe Approval Test**.
5. Continue with iPhone magic-link testing.

Security notes:
- Do not store raw tokens in the Sheet.
- Do not put confidential content in the Sheet.
- Tokens should expire and be one-time use.
- The Apps Script does not generate drafts, crawl sources, call AI APIs, or publish to LinkedIn.

The deployment package is local only. It does not deploy anything to Google by itself.
