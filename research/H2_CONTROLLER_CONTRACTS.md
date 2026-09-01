# H2 Controller Contract Boundary

The autonomous controller must validate lifecycle artifacts before accepting them and must use the deterministic transition function for BC state changes.

Required boundaries:

1. Candidate is validated before queue admission and before evaluation.
2. Evaluation evidence is validated after execution and before gate interpretation.
3. OOS contamination in IS/Validation evidence blocks the lifecycle.
4. BC transitions are performed through `transition()`; duplicate or out-of-sequence BCs are blocked.
5. Trading strategy logic and promotion thresholds are unchanged by H2.
