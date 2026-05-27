# Oracle Locus Workflow Engine Setup

This project now has an SDK-backed Oracle Locus workflow layer behind the business console.

The console remains the main business-user interface. Locus is used as the workflow brain for agent rosters, StateGraph execution, event traces, orchestration metadata, and human gates.

## What Is Active Now

- Daily scan runs through Locus `StateGraph` when the SDK is installed.
- Friday package runs through Locus `StateGraph` when the SDK is installed.
- Production pilot runs through Locus `StateGraph` when the SDK is installed.
- Production test package runs through Locus `StateGraph` when the SDK is installed.
- Locus traces record SDK execution order, node status, EventBus observability event counts, and guardrail/human-gate events.
- The local capability check exercises StateGraph, idempotent tools, grounding, reflection, composition pipelines, Send, functional workflows, and the evaluation framework.
- A local Workbench package can be exported with workflow manifests, Mermaid diagrams, active SDK capabilities, and the Hard Zero safety policy.
- A local `describe_locus_local_tools` / `use_locus_local_tool` pair lets agents discover safe workflow operations first, then dispatch through a read-only-by-default safety gate.
- Integration status reports the Oracle Locus workflow engine.
- The business console has a Setup card named `AI Workflow Engine`.
- The business console can run a safe local Locus capability test.

## Hard Zero Mode

Installing Locus does not enable paid model calls.

The current provider mode is:

```text
deterministic_local_tools
```

That means the app continues using local deterministic tools until you intentionally enable a paid-capable provider in a future guarded mode.

## Install Commands

Run these from the project root:

```bash
.venv/bin/python -m pip install locus-sdk
```

Or install through this project optional dependency:

```bash
.venv/bin/python -m pip install -e ".[locus]"
```

Then verify:

```bash
.venv/bin/python -m ai_linkedin_automation.cli locus-status
.venv/bin/python -m ai_linkedin_automation.cli locus-capability-check
.venv/bin/python -m ai_linkedin_automation.cli build-locus-workbench-package
```

## Business Console Check

Open the Desktop app, go to `Setup`, then click `View Locus Status` or `Test Locus`.

You should see:

- whether the SDK is installed
- active engine mode
- enabled workflows
- setup commands
- Hard Zero safety notes
- SDK capability checks for StateGraph, idempotent tools, grounding, reflection, and functional tasks
- Workbench-style workflow manifest and Mermaid diagrams through `Export Locus Map`

## Fallback Behavior

- If Locus SDK is installed, use SDK-backed workflow primitives.
- If not installed, continue with local Locus-compatible traces.
- never enable paid/provider calls in Hard Zero Mode

## OCI Tooling Note

The useful lesson from the OCI demo is the pattern: discover available operations, dispatch through one guarded tool, and default to read-only behavior.

This project should not use the OCI adapter for the LinkedIn workflow. We do not need tenancy access, OCI credentials, or cloud-side operations to produce a weekly human-approved draft. The local dispatcher mirrors the pattern without adding OCI dependencies or billable cloud paths.

The implementation is aligned with the public `oracle-samples/locus` repo where it helps this app:

- workflows stay on local `StateGraph` execution when the SDK is installed
- traces keep `run_context` / EventBus style observability metadata
- optional SDK-facing tools are plain Python functions wrapped with `locus.tools.tool(idempotent=True)`
- provider-backed or cloud-backed features remain out of scope for Hard Zero Mode
- if a newer Locus install includes OCI `describe_oci` / `use_oci` tools, this app may report that capability but does not expose it through the active workflow surface

Local dispatcher rules:

- `describe_locus_local_tools` is read-only and safe for agents to call first.
- `use_locus_local_tool` blocks local file-writing operations unless `allow_local_writes=True`.
- dispatched operations never post to LinkedIn, send email, write back to Google APIs, or call paid model/provider APIs.
