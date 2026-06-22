---
name: autox-audit-optimization
description: Initialize, update, validate, finalize, or archive the file-based audit trail for the active serial AutoX SQL optimization case. Use whenever an AutoX stage changes state, records evidence, makes a recommendation, applies or rolls back a change, or completes a case.
---

# AutoX Audit Optimization

Read `../autox-optimize-sql/references/case-contract.md`.

## Initialize

If no current case exists, copy the case template, generate one `case_id`, fill
UTC timestamps and known target fields, and create all contract directories.
Do not accept `case_id` as a required user argument.

## Update

For every stage:

- append UTC time, stage, action, evidence path, and result to `audit.md`;
- update `updated_at`, `current_stage`, and the relevant manifest section;
- record evidence gaps, failed commands, retries, assumptions, candidate count,
  rejected candidates, approvals, SQL executed, and rollback state;
- reference artifacts by relative path rather than embedding large payloads;
- never record credentials or access keys.

After candidate comparison, record the selected or rejected decision and set
`current_stage: decision_recorded`.

## Validate

Check stage order, required files, stable `case_id`, production and local TiDB
versions, reproduction verdict, recommendation status, approval evidence,
apply and rollback SQL, outcome metrics, and unresolved assumptions.

## Finalize

Summarize baseline, candidates, selected recommendation, implementation,
measured outcome, and missing verification. Set stage `archived`, copy the
current directory to `cases/<case_id>/`, then remove `.autox/current/` only
after confirming the archive is complete.

Keep archived cases out of Git unless they are explicitly redacted and approved
for sharing.
