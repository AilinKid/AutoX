# AGENTS.md

## Purpose

Maintain a Skill-first, evidence-driven TiDB SQL diagnosis and remediation
workflow.

## Non-negotiables

1. Keep the workflow serial through `.autox/current/manifest.yaml`.
2. Generate `case_id` once; do not require it as a stage argument.
3. Never recommend or execute a production mutation without evidence,
   validation, risk classification, approval, and rollback instructions.
4. Keep optimizer behavior version-aware. Do not assume current TiDB behavior
   applies to an older cluster.
5. Do not invent Clinic or TiDB APIs. Verify contracts from source,
   documentation, or captured responses.
6. Treat case data as sensitive and keep it out of Git unless explicitly
   redacted.
7. Keep Skill instructions concise and move detailed contracts into references.

## Validation

Run `quick_validate.py` for every changed Skill. Check for unresolved template
markers and broken relative references. For workflow changes, dry-run the
serial state transitions against a temporary `.autox/current/` case without
touching production.
