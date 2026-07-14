# AutoX Evaluation Records

This file tracks AutoX evaluation data, SQL digest diagnosis notes, outcomes,
and follow-up decisions. Keep it concise enough to update after every
evaluation.

## Scope

This document collects previously diagnosed SQL digest cases and uses them to
evaluate the AutoX read-only diagnosis workflow.

The main question is:

> Given a `cluster_id` and one or more known slow SQL digests, can AutoX collect
> enough evidence to produce a useful, review-only optimization suggestion?

## Rules

- Keep AutoX read-only. Record suggested bindings, indexes, DDL, or
  configuration changes as review-only outputs.
- Separate observed evidence from inference.
- Record missing evidence explicitly.
- Prefer redacted evidence summaries and retained artifact paths over raw
  customer-sensitive SQL, schema, statistics, credentials, or tenant data.
- Record the TiDB version used by the target cluster and any local validation
  environment. Mark version-mismatched validation as advisory.

## Evaluation Index

| Date | Digest / Case | Cluster | Diagnosis Type | Result | Follow-up |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

## Case Notes

### Case 1: SQL digest

**Context**

- `cluster_id`:
- Time range:
- SQL digest:
- TiDB version:
- Existing diagnosis doc or notes:

**Observed Evidence**

- Slow query symptoms:
- Current plan:
- Schema / statistics:
- TopSQL / metrics:
- Missing evidence:

**Diagnosis**

- Likely root cause:
- Evidence supporting the diagnosis:
- Alternative explanations:

**Recommendation**

- Type: binding / index / statistics / TiFlash-MPP / rewrite /
  non-optimizer investigation / no action
- Review-only SQL or action:
- Expected impact:
- Risk:
- Confidence:

**Validation**

- Level: `inferred` / `plan_verified` / `prod_verified`
- Baseline evidence:
- Candidate evidence:
- Version match:

**Learning**

- What this case proves about AutoX:
- Workflow gap:
- Skill or script follow-up:

## Full Record Template

Use this template when a case needs more detail than the short case note.

### YYYY-MM-DD: evaluation - short title

**Context**

- `cluster_id`:
- Time range:
- SQL digest or case:
- TiDB version:
- AutoX commit:
- Skill version or changed files:

**Evaluation Goal**

- What this evaluation is trying to prove:
- Success criteria:

**Inputs**

- Required input provided:
- Optional inputs provided:
- Local TiDB / source checkout:
- Evidence artifacts:

**Observed Evidence**

- Slow query symptoms:
- Plan evidence:
- Schema / statistics evidence:
- Metrics / TopSQL evidence:
- Collection errors:

**Inference**

- Likely root cause:
- Why the evidence supports it:
- Alternative explanations:

**Recommendation**

- Type: binding / index / statistics / TiFlash-MPP / rewrite /
  non-optimizer investigation / no action
- Review-only SQL or action:
- Expected impact:
- Risk:
- Confidence:

**Validation Result**

- Validation level: `inferred` / `plan_verified` / `prod_verified`
- Baseline plan source:
- Candidate plan source:
- Version match:
- Result summary:

**Outcome**

- What worked:
- What failed:
- Missing evidence:
- Follow-up tasks:

**Decision**

- Keep:
- Change:
- Defer:
