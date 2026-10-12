---
name: maintain-alpha-ficc-terminal
description: Use when Ubuntu Hermes is running scheduled or incident-driven maintenance for Alpha-FICC services, APIs, providers, refresh jobs, data freshness, deployment drift, or maintenance reporting.
---

# Maintain Alpha-FICC Terminal

## Core contract

Operate as `hermes` with record role `scoped_agent`. Severity describes impact; it never grants authority. A technically successful repair is not complete until its durable report and append-only run record exist.

**Violating a phase gate is violating the maintenance boundary.** Urgency, a one-line apparent fix, a healthy service, or an imminent cron run never widens authority or removes reporting.

## Scheduled passive fast path

For the scheduled `passive` cron fast path, the pre-run script's structured JSON is
the only source of truth. Report only from that JSON in no more than 12 Chinese
lines, listing status, failed/timeout/warning, whether actions is empty, `A2=false`,
and the next step. This path reports only: it does not run ordinary phase gates,
and A1/A2 do not apply. 不得调用任何工具，不得读取文件、仓库或 Agent-KB，不得重复探测、
不得等待，不得修复，不得提交，不得部署，不得发布或调用 `send_message`；不得返回
`[SILENT]`。可追溯面仅为 Hermes scheduler durable run history 和 output artifact；
不得声称 MaintenanceStore ledger 已持久化。最终响应只输出 Discord 维修站的报告。
安装器将 scheduler 的 `--max-turns` 固定为 passive=1、active A1/A2=12；active 不是无限制模式。

Read these before acting:

- [check-matrix.md](references/check-matrix.md) for probes, confirmation and real verification.
- [repair-authority-policy.md](references/repair-authority-policy.md) and [repair-policy.json](references/repair-policy.json) before selecting A1, A2 or A3.
- [reporting-contract.md](references/reporting-contract.md) before persisting or returning any result.
- [ubuntu-hermes-runtime.md](references/ubuntu-hermes-runtime.md) for cron, paths, lease and Discord reconciliation.

## Mandatory phase gates

Run these phases in order. Do not skip ahead or combine severity with authority.

```text
preflight identity/version/lease
→ read deterministic probe output
→ confirm anomaly inside the same run
→ assign severity separately from authority
→ A1/A2/A3 route
→ execute at most one repair class
→ real service and data verification
→ rollback when required
→ A3 only: publish and verify deduplicated Agent-KB report
→ persist final immutable ledger and durable report artifacts
→ render final Discord report
```

### 1. Preflight identity, version and lease

1. Require executor `hermes` and record role `scoped_agent`. Use only Hermes's existing scoped secret reference. Never elevate to `operator/admin`, borrow another Agent identity, or record secret values, lengths, hashes, prefixes, fragments, cookies, authorization material or raw command environments.
2. Resolve the installed Skill, production root, maintenance source clone and runtime root from installer state; do not guess them. Production and source clone are different roots.
3. Reconcile the previous run's Discord result using Hermes job state and `MaintenanceStore.pending_delivery_run_id()`; append `delivered` or `failed` with `append_delivery_event()`. Never rewrite the original run.
4. Acquire the single maintenance lease. If another run owns it, record `skipped_due_to_active_run`, produce the normal reports, and stop without probing or repairing.
5. Record source `HEAD`, fetched `origin/main`, production `.deployed-head` and mode. A2 requires a clean source clone and exact agreement before any edit.

### 2. Read deterministic probe output

Use `scripts/run_maintenance_probe.py` or `collect_probe()` with the configured roots. Treat its output as bounded evidence, not repair authorization. Use `sanitize()` before any persistence or rendering.

Never call `GET /api/terminal-chart-actions/pending`; it drains the browser queue. Never inspect browser state or call Provider APIs directly. A five-minute deadline does not change these prohibitions.

### 3. Confirm the anomaly in the same run

For a first abnormal sample, wait 1–3 minutes and repeat only the affected bounded checks, at most twice. Correlate task failure with real service/data impact. Do not wait for the next 30-minute cron boundary. Do not repair a single transient sample.

Treat the configured attempts and 1–3 minute window as ceilings, not quotas. Before each wait, compute the remaining hard deadline and reserve at least 60 seconds for classification, A3 publication outcome when routed, ledger/local report persistence, cron final output and Discord rendering. Start a confirmation only when the remaining time covers the selected wait, a 25-second targeted-check budget and that reporting reserve. Otherwise stop confirmation, record `unconfirmed`, and report within the deadline. For a five-minute run after a 100-second initial probe, this permits at most one 60-second wait plus one targeted check; never promise two three-minute waits.

If confirmation cannot be obtained, set an observed/unconfirmed state, persist and report it; do not invent a diagnosis.

### 4. Assign severity, then authority

Use `classify_checks()` for the advisory severity candidate. Independently evaluate authority against the locked policy.

| Route | Meaning | Action |
| --- | --- | --- |
| A0 | Healthy or observation only | No repair; still persist and report. |
| A1 | One allowlisted runtime recovery | Execute one fixed action ID only. |
| A2 | One small, reversible code defect inside every gate | One production file plus its allowed test, one descendant commit. |
| A3 | Any boundary, evidence, version, rollback or authority gate fails | Stop all mutation and publish a deduplicated Agent-KB handoff. |

An `authority_candidate` from the classifier is advisory only. P0/P1 can still be A3.

### 5. Execute at most one repair class

Do not mix A1 and A2 in one run. Do not execute more than one action. If the deterministic A1 executor or A2 patch/deployment gate is absent or unvalidated, route A3 instead of substituting shell commands.

- **A1:** select an exact ID from `repair-policy.json`; record action version, fixed argv category, start/end, exit code and capped output. Arbitrary shell, PostgreSQL restart, host reboot and cleanup are unavailable.
- **A2:** follow every gate in `repair-authority-policy.md`. If a forbidden path or remote drift is known before editing, do not edit, stage or prepare a patch. If drift appears later, do not rebase, merge, cherry-pick, force push, deploy or auto-resolve; preserve evidence and route A3.
- **A3:** perform no code, Git, deployment, service or identity mutation. Read-only evidence gathering may continue within limits.

### 6. Verify real service and data behavior

Repeat the relevant bounded probe and the task-specific checks from `check-matrix.md`. Process success or `/api/health` alone is insufficient. Verify the affected service, Provider/refresh lane, representative data advance, frequency-aware freshness and next scheduled state.

### 7. Roll back when required

If A1/A2 post-action verification fails, use only the predeclared exact rollback. Verify the restored version and service/data state. If rollback is unavailable, fails, or the defect still reproduces, route A3 and report the production state honestly.

### 8. Publish and verify A3 handoff before final reporting

**REQUIRED SUB-SKILL:** Use `agent-kb-workflow` before any Agent-KB read or write.

For A3, use `MaintenanceStore.open_incident()` with a stable, sanitized failure identity. In the actual Agent-KB clone, run `configure_agent_instance.py check Hermes` and use its clone-local registered instance ID. The only new summary path is `outputs/review/agent_task_summaries/Hermes/<registered-instance-id>/TASK-<stable-incident-id>.md`; never write at the flat `Hermes/` family root.

Pull/rebase the canonical Agent-KB checkout before writing, then close out through `agent_finish.sh Hermes TASK-<stable-incident-id> <summary-file.md>`. Repeated unchanged observations reuse the incident and report; only material facts append an update. A local file or local commit is not a handoff.

Resolve the publication outcome before building the final immutable run:

- remote path verified visible: `agent_kb.status=remote_visible`, record `canonical_path`, and use technical `final_status=builder_required`;
- push fails or conflicts: do not force or rewrite history; record `agent_kb.status=handoff_push_failed` with `local_path`;
- push returns but remote visibility cannot be verified: record `agent_kb.status=remote_not_visible` with `local_path`; do not claim `builder_required`.

Before persistence, call `validate_agent_kb_publication(record)`. This is the same executable gate used by `validate_run_record()` and `completion_status()`: `builder_required` requires `remote_visible` plus the exact registered-instance canonical task-summary path; either failure status must match `agent_kb.status` and carry a safe instance-aware local path. Missing, unknown, contradictory, swapped or flat family-root publication data is invalid and fails closed to `reporting_failed`.

Hermes never creates or wakes a Mac Codex task. The user performs that handoff.

Every A3 decision response and actual finalization includes this explicit handoff block in this order:

```text
instance_check: python3 ops/scripts/configure_agent_instance.py check Hermes
registered_instance_id: <clone-local registered value>
canonical_summary_path: outputs/review/agent_task_summaries/Hermes/<registered-instance-id>/TASK-<stable-incident-id>.md
closeout: bash ops/scripts/agent_finish.sh Hermes TASK-<stable-incident-id> <summary-file.md>
publication_status: remote_visible | handoff_push_failed | remote_not_visible
publication_path: <canonical path when remote_visible; local path otherwise>
finalization_order: publish/verify -> immutable ledger -> Discord render
```

In a decision simulation, show the command/path template and the status-selection rule without claiming execution. In a real finalization, replace every placeholder with the checked instance, stable incident and actual path/status.

### 9. Persist the final immutable run and all durable artifacts

Build the run with `new_run_record()`, validate with `validate_run_record()`, and append using `MaintenanceStore.append_run()`. Every run—including healthy, skipped, unconfirmed and failed runs—requires a maintenance ledger entry and local report. No business action does not mean no maintenance record.

Before append, persist the durable local report and cron final-output artifact, and set the current Discord target to `prepared` or `unconfigured`. For A3, the record must already contain the publication outcome and corresponding canonical/local path from phase 8.

Only after `MaintenanceStore.append_run()` returns successfully may the caller derive outward state with `completion_status(record, ledger_persisted=True)`. If append fails, call with `ledger_persisted=False`. A missing/failed local report, missing/failed cron output, invalid Discord target, or failed append yields `repaired_reporting_failed` for a repair and `reporting_failed` otherwise. Never substitute an error code, `healthy`, `repaired`, `complete` or a `*_report_ready` state.

The append result is a runtime fact, not record data. Pass that same keyword-only fact to the only final render calls: `render_builder_report(record, ledger_persisted=True)` and `render_discord(record, ledger_persisted=True)` after a successful append; pass `False` after append failure. Both renderers derive their outward status internally with `completion_status()` and never render technical `record.final_status` as the outward result.

When a repair succeeded but any report face failed, the current response includes this reporting-failure block:

```text
final_status: repaired_reporting_failed
local_report: persisted | failed
cron_output: persisted current warning/final-output artifact | failed
discord: prepared failure summary | unconfigured
repair_retry: no
next_run: reconcile/retry report faces only; do not repeat the successful repair
```

If local report persistence fails, still save the current cron warning/final-output artifact and render a Discord `prepared` failure summary. Current delivery is never `delivered`; the next run reconciles delivery and retries only failed report surfaces.

### 10. Render the final Discord report after ledger append

Call `render_discord(record, ledger_persisted=<append result>)` for every run, paired with the final `render_builder_report()` call using the identical append fact. Return a real Chinese message; never `[SILENT]`. The current run's Discord state is always `prepared` (or `unconfigured` when no target exists), never `delivered`. Hermes gateway delivers only after the final response; a later reconciliation appends the terminal delivery event.

Discord is a one-way report surface, not a command channel or Agent conversation. Do not call a send-message tool from the maintenance run.

For A3, `render_discord()` must include explicit `publication_status` and `publication_path` lines using the already-final `remote_visible`, `handoff_push_failed`, or `remote_not_visible` status and its canonical/local path. Never render first and “correct” it after publish.

## Rationalizations closed by RED testing

| Rationalization | Required response |
| --- | --- |
| “P1 and the fix is one line, so patch now.” | Severity never widens authority; forbidden path or drift routes A3 before any edit. |
| “Send it to a responsible person/channel.” | Generic notification is not a durable Agent-KB handoff. Use stable incident dedupe and remote visibility. |
| “Discord status is P1 handoff.” | P1 is event state. Discord delivery is separately `prepared`, then later `delivered` or `failed`. |
| “The service is healthy, so the run is complete.” | Service recovery and the four-surface reporting gate are separate. Any missing surface prevents a success outward state. |
| “No business action means no ledger or cron output.” | Every run writes the maintenance ledger, local report, cron final output and prepared Discord message. |
| “Peek at pending to verify the queue.” | `pending` drains state; never use it for maintenance probing. |
| “Temporarily elevate Hermes and restore it afterward.” | Temporary elevation is still elevation and is forbidden. |
| “The policy allows two 1–3 minute retries, so both fit any run.” | Attempts and waits are ceilings. Reserve reporting time and reduce retries to fit the actual hard deadline. |

## Stop and route A3

- Any forbidden path, dirty source clone, version mismatch or remote change.
- Missing failing test, real verification, exact rollback or required helper.
- Auth/scopes, API contract, schema, migration, financial identity/lineage/units/frequency, UI, dependency or cross-module work.
- Any proposal to force push, rewrite remote history, edit the Git-less production root, auto-resolve conflicts or widen policy during an incident.
- A repair or rollback that fails or still reproduces.

All of these mean: stop mutation, preserve sanitized evidence, publish and verify one deduplicated A3 handoff, persist the final run, then render Discord from that final truth.
