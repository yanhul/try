#!/usr/bin/env bash
set -euo pipefail

# Central AIOS boundary adapter for the bounded research workload. The actual
# autonomous campaign remains governed by bc-research-controller.yml; this
# adapter only exposes its already-tested contract as a machine-readable result.
if python research/aios_conformance.py >/tmp/try-aios-conformance.log 2>&1; then
  printf '%s\n' '{"status":"INCONCLUSIVE","artifact_refs":["/tmp/try-aios-conformance.log"],"evidence_refs":["research/AIOS_RESEARCH_CONTRACT.md"],"verification_refs":["research/aios_conformance.py"],"provenance":{"producer":"yanhul/try","adapter":"try.research@1"}}'
else
  printf '%s\n' '{"status":"BLOCKED","artifact_refs":["/tmp/try-aios-conformance.log"],"evidence_refs":["research/AIOS_RESEARCH_CONTRACT.md"],"verification_refs":["research/aios_conformance.py"],"provenance":{"producer":"yanhul/try","adapter":"try.research@1"}}'
  exit 0
fi
