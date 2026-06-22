---
name: autox-apply-binding
description: Safely generate, review, apply, verify, and roll back an approved TiDB SQL binding for an AutoX case. Use only after candidate comparison selects a binding and the user asks to implement it in a specific cluster.
---

# AutoX Apply Binding

Read `../autox-optimize-sql/references/case-contract.md`.

1. Require stage `decision_recorded`, a selected binding candidate, successful
   reproduction for validated actions, and an identified target cluster.
2. Generate exact apply, verification, and rollback SQL under `decision/`.
3. Check TiDB version syntax, normalized SQL match, existing bindings,
   privileges, scope, current plan, conflicting hints, and rollback viability.
4. Define observation window and rollback thresholds before execution.
5. Present target, apply SQL, expected effect, risks, verification, and rollback
   SQL. Obtain explicit action-time approval before production execution.
6. Record approver identity as provided, time, command, response, and binding
   state in `audit.md`; never record credentials.
7. Verify the binding exists and affected SQL selects the intended plan.
8. On failed preconditions or verification, stop and execute rollback only when
   authorized by the agreed policy.
9. Update implementation status and set
   `current_stage: implementation_completed`.

This Skill does not apply indexes or configuration changes.
