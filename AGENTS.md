# AGENTS.md

## Purpose

Build an evidence-driven, optimizer-integrated SQL diagnosis and remediation
system for TiDB.

## Non-negotiables

1. Never recommend or execute a production mutation without structured
   evidence, validation results, risk classification, and a rollback plan.
2. Keep optimizer behavior version-aware. Do not assume current TiDB behavior
   applies to an older cluster.
3. Do not invent Clinic or TiDB APIs. Verify contracts from source,
   documentation, or captured responses.
4. Keep language-model output advisory. Deterministic code owns evidence
   normalization, scoring, policy checks, and action execution.
5. Every bug fix requires a regression test or replay case.
6. Keep diffs focused and report exact validation commands.

## Validation

Run at minimum:

```bash
gofmt -w <changed-go-files>
go test ./...
go vet ./...
```

For changes to a TiDB integration, also run the closest compatible TiDB
optimizer tests or replay fixture and record the tested TiDB version.
