# Business Console

The business console is the primary way to run the product without Terminal or VS Code.

## Open It

Best option:

```text
AI LinkedIn Console.app
```

Fallback option:

```text
Launch AI LinkedIn Console.command
```

The desktop app starts the local server on a private localhost port and opens the console in your browser. No terminal is required for normal use.

If the launcher ever needs to be rebuilt, open the console and press **Repair Desktop App**.

## Main Jobs

- Press **Prepare Everything** to create the desktop launcher, approval deployment files, local QA report, schedule package, readiness report, and pilot checklist.
- Press **Put App On Desktop** to copy the app bundle to the macOS Desktop for true double-click operation.
- Press **Run System Check** to create a functional diagnostics report covering the launcher, database, guardrails, readiness, approval package, pilot package, and setup artifacts.
- Run the weekly source and package flow.
- Build the first-post test package.
- View the selected draft, shortlist, runbook, and approval setup files.
- Save the Apps Script approval URL into `.env`.
- Paste the exported ReviewQueue CSV back into the browser.
- Validate and import approval decisions.
- Build the manual posting package.
- Archive the final LinkedIn post URL.

## External Boundary

Google Apps Script deployment still happens in Google because Hard Zero Mode does not use Google API deployment credentials. The console shows the deployment checklist, Sheet header, `Code.gs`, `Index.html`, and `appsscript.json` in the browser so no code editor is needed.

The optional schedule files are generated but not installed automatically. This keeps background automation explicit while the product is still in production testing.

## Safety

- Approval does not publish to LinkedIn.
- The console does not send email.
- Google Sheets API write-back remains disabled.
- LinkedIn API publishing remains disabled.
- The final LinkedIn post remains a human copy/paste action.

## Appearance

The console follows the system/browser color preference automatically. If macOS or the browser is in dark mode, the console opens in dark mode.
