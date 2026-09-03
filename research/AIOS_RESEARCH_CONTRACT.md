# AIOS research execution boundary

Research execution is permitted only when an external AIOS authority supplies a
contract and permit bound to the exact research input/policy.

## Required binding

- `contract_type = EXECUTION_CONTRACT`
- contract identity is the canonical SHA-256 identity used by AIOS
- permit is bound to that contract identity
- `task_id` identifies the research run
- `input_digest` identifies the frozen candidate/dataset/config bundle
- `allowed_effects` must be research-only; no live-order effect is permitted
- `evidence_required` and `terminal_states` come from governing policy
- `policy_digest` identifies the governing policy outside agent authority
- the agent MUST NOT issue, rewrite, broaden, or replace the contract/permit

## Terminal rule

A persisted `terminal=true` flag is not authoritative by itself. A terminal
transition must be supported by an externally authorized contract/permit and
verified evidence. A forged or missing authority record is a BLOCKED/HOLD
condition, never success.

This file defines the integration protocol only. The governing authority lives
in AIOS; this repository does not mint permits or change promotion criteria.
