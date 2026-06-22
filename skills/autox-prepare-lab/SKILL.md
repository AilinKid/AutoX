---
name: autox-prepare-lab
description: Prepare and clean up a local TiDB optimizer laboratory matching a production cluster version, schema, statistics, variables, and bindings. Use when AutoX needs a reproducible local environment before plan analysis or candidate experiments.
---

# AutoX Prepare Lab

Read `../autox-optimize-sql/references/case-contract.md`.

1. Require stage `context_sanitized`.
2. Resolve the exact production TiDB version and record binary provenance. Do
   not silently substitute the current source tree or latest release.
3. Start an isolated local TiDB environment. Record ports, data paths, process
   IDs, configuration, and cleanup procedure in `baseline/lab-environment.md`.
4. Create sanitized schemas before loading statistics. Restore plan-relevant
   variables and existing bindings explicitly.
5. Load statistics with the version-compatible TiDB mechanism and capture every
   warning or unsupported field.
6. Verify table definitions, index order, partition definitions, stats health,
   row counts, variables, SQL mode, isolation engines, and bindings.
7. Save verification queries and outputs under `baseline/`.
8. Append environment provenance and differences to `audit.md`.
9. Set `current_stage: lab_prepared`.

Keep the lab running for later stages. Clean it only after audit finalization or
explicit abandonment.
