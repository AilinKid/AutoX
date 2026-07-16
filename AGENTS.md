# AGENTS.md

## Purpose

Maintain a small, read-only Skill workflow that takes a TiDB Cloud
`cluster_id`, analyzes slow queries, and outputs optimization suggestions.

## Non-negotiables

1. Keep the first version read-only. Do not apply bindings, indexes,
   configuration changes, or other production mutations.
2. Require only `cluster_id`; treat time range, SQL digest, existing local
   TiDB, and existing source checkout as optional inputs.
3. AutoX may prepare an isolated local TiDB validation environment under the
   diagnosis workspace by reusing or cloning `pingcap/tidb`, creating a
   per-diagnosis worktree, checking out the target cluster version, building it,
   and starting a local standalone instance.
4. Keep optimizer behavior version-aware. Do not assume current TiDB behavior
   applies to an older cluster.
5. Do not invent Clinic or TiDB APIs. Verify contracts from source,
   documentation, or captured responses. When TiDB behavior, syntax, or feature
   availability needs documentation, consult `pingcap/docs` or the TiDB official
   website and keep the reference target-version aware.
6. Distinguish observed evidence from inference and state missing evidence.
7. Keep Skill instructions concise. Add structure only after real use proves it
   necessary.

## Validation

Run `quick_validate.py` for every changed Skill. Check for unresolved template
markers and broken Skill references. Verify the workflow never requires case
state or production mutation.
