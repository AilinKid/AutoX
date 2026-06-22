---
name: autox-optimize-sql
description: Orchestrate the complete serial AutoX workflow for TiDB slow SQL diagnosis, optimizer reproduction, candidate exploration, binding or index recommendations, guarded implementation, outcome verification, and file-based audit. Use when a user asks AutoX to diagnose or optimize a SQL, investigate a plan regression, recommend a binding or index, or run an end-to-end SQL optimization case.
---

# AutoX Optimize SQL

Run all stages serially through `.autox/current/`. Do not require the user or
subskills to pass `case_id`.

## Start or resume

Read [case-contract.md](references/case-contract.md).

- If `.autox/current/manifest.yaml` exists, resume its `current_stage`.
- Otherwise copy the templates from `assets/case-template/`, generate one UTC
  `case_id`, and fill the known target fields.
- Refuse to overwrite an active case. Archive or explicitly abandon it first.
- Keep raw and sanitized evidence separate.

## Workflow

Invoke these Skills in order:

1. `$autox-audit-optimization` to initialize the audit.
2. `$autox-sanitize-context`.
3. `$autox-prepare-lab`.
4. `$autox-verify-reproduction`.
5. `$autox-explore-sql`.
6. `$autox-compare-plans`.
7. `$autox-audit-optimization` to record the recommendation decision.
8. `$autox-apply-binding` only for an approved binding action.
9. `$autox-verify-outcome` after implementation.
10. `$autox-audit-optimization` to finalize and archive.

Do not run stages in parallel. After each stage, require its output files and
manifest transition before proceeding.

For recommendation-only work, finalize after step 7. Do not manufacture
implementation or outcome stages.

## Gates

- If production plan reproduction fails, continue exploration only as
  advisory analysis. Mark every recommendation `unvalidated`.
- Never interpret a lower estimated cost alone as proof of improvement.
- Do not mutate production without explicit approval at action time.
- Require apply and rollback SQL before applying a binding.
- Require a defined observation window and rollback threshold before mutation.
- Record collection failures as unknown data, never as zero.

## Completion

Return the recommendation, evidence quality, reproduction status, applied
action if any, measured outcome, rollback status, and audit directory.
