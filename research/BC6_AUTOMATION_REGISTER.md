# BC6 Automation Register

Purpose: prevent lifecycle dead-end after a rejected candidate while preserving strict research controls.

Rules:
- One conceptual change per candidate.
- OOS remains reserved until IS + validation gates pass.
- Rejected candidates require failure analysis.
- Failure analysis may identify a candidate, but cannot tune parameters or use OOS.
- No automatic hypothesis invention from arbitrary data mining.
- Every candidate must be explicitly registered before its audit can run.

Current state:
- BC5: rejected.
- BC5 failure analysis: required/completed according to lifecycle state.
- Next candidate: NOT REGISTERED.
- OOS: reserved (2899..3624).

Automation requirement:
- The controller must stop with `HYPOTHESIS_REGISTRATION_REQUIRED` when no validated candidate is registered.
- It must never manufacture BC6 merely to keep the pipeline moving.
