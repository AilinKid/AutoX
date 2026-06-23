# AGENTS.md

## Purpose

Maintain a small, read-only Skill workflow that takes a TiDB Cloud
`cluster_id`, analyzes slow queries, and outputs optimization suggestions.

## Non-negotiables

1. Keep the first version read-only. Do not apply bindings, indexes,
   configuration changes, or other production mutations.
2. Require only `cluster_id`; treat time range, SQL digest, local TiDB, and
   source checkout as optional inputs.
3. Assume the execution environment is prepared externally. Do not build
   environment provisioning into AutoX.
4. Keep optimizer behavior version-aware. Do not assume current TiDB behavior
   applies to an older cluster.
5. Do not invent Clinic or TiDB APIs. Verify contracts from source,
   documentation, or captured responses.
6. Distinguish observed evidence from inference and state missing evidence.
7. Keep Skill instructions concise. Add structure only after real use proves it
   necessary.

## Validation

Run `quick_validate.py` for every changed Skill. Check for unresolved template
markers and broken Skill references. Verify the workflow never requires case
state, environment creation, or production mutation.
