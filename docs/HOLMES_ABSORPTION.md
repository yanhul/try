# Holmes-Kit absorption into TRY

TRY consumes Holmes-Kit ideas through the AIOS boundary; it does not add Holmes-Kit as a runtime dependency.

## Adopted

- **Evidence-first test semantics:** a test that did not execute is not a RED signal and cannot be promoted to PASS.
- **Spec-to-implementation traceability:** research code and experiments should retain explicit linkage to the hypothesis/strategy specification that authorized them.
- **Advisory vs gate separation:** graph/scope/architecture findings are observations until independently validated; they must not silently become strategy promotion criteria.
- **Durable ledgering:** every campaign transition keeps enough provenance to explain why the next BC was entered, blocked, resumed, or terminated.
- **Execution-boundary enforcement:** authorization must be checked immediately before effects, not only when the campaign is planned.

## TRY-specific interpretation

`REQ -> SPEC -> TEST -> RUN -> VALIDATE -> OOS LOCKED -> PROMOTION` is the research analogue of Holmes' spec chain, but the actual authority remains AIOS.

The research agent may generate hypotheses and candidate experiments. It may not rewrite the campaign policy, evidence requirements, OOS lock, terminal states, or promotion criteria.

## Rejected

- No Holmes-specific dependency.
- No numeric architecture/complexity gate copied from Holmes.
- No CPG/taint result is treated as proof of trading edge.
- No advisory graph finding can create `EDGE_FOUND` by itself.
