#!/usr/bin/env python3
"""Governed implementation absorption for audited discovery candidates.

This stage does not copy untrusted external source code. It binds an audited
discovery candidate to an existing local executable implementation surface,
then persists an immutable implementation manifest. A candidate is only marked
IMPLEMENTED when its family/operator is already supported by the local runtime.
"""
from __future__ import annotations
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PROOF=ROOT/"research/discovery/absorption_proof.json"
OUT=ROOT/"research/discovery/implementation_absorption_proof.json"

SUPPORTED_FAMILIES={
    "momentum_trend","mean_reversion","smc_ict","fvg_imbalance",
    "wyckoff_vsa_vpa","vwap_volume_profile","regime","point_figure","gann_reference",
}
SUPPORTED_OPERATORS={
    "identity","difference","ratio","zscore","rolling_mean",
    "rolling_std","lag","delta","rank",
}

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def _spec(candidate):
    spec=candidate.get("discovery_spec") or {}
    if candidate.get("hypothesis_id")=="composite_primitive":
        return spec.get("mechanism_family"), [t for t in spec.get("terms",[]) if isinstance(t,dict)]
    return spec.get("mechanism_family"), [spec]

def main():
    if not PROOF.exists():
        raise SystemExit("IMPLEMENTATION_ABSORB_BLOCKED missing absorption proof")
    proof=json.loads(PROOF.read_text(encoding="utf-8"))
    if proof.get("status")!="PASS":
        raise SystemExit(f"IMPLEMENTATION_ABSORB_BLOCKED absorption_status={proof.get('status')}")
    implemented=[]; blocked=[]
    for candidate in proof.get("absorbed",[]):
        family,terms=_spec(candidate)
        if family not in SUPPORTED_FAMILIES:
            blocked.append({"candidate_id":candidate.get("candidate_id"),"reason":"local_family_runtime_missing"})
            continue
        bad=[t.get("operator") for t in terms if t.get("operator") not in SUPPORTED_OPERATORS]
        if bad:
            blocked.append({"candidate_id":candidate.get("candidate_id"),"reason":"local_operator_runtime_missing","operators":bad})
            continue
        implemented.append({
            "candidate_id":candidate.get("candidate_id"),
            "source_id":candidate.get("source_id"),
            "source_url":candidate.get("source_url"),
            "family":family,
            "hypothesis_id":candidate.get("hypothesis_id"),
            "source_digest":candidate.get("source_digest"),
            "implementation":"engine.autonomous_evaluator.discovered_predicate",
            "status":"IMPLEMENTED",
            "mode":"LOCAL_ADAPTER",
        })
    payload={
        "schema_version":1,
        "proof_type":"TRY_IMPLEMENTATION_ABSORPTION_PROOF",
        "status":"PASS" if implemented and not blocked else ("PARTIAL" if implemented else "BLOCKED"),
        "absorption_proof_digest":digest(proof),
        "implemented_count":len(implemented),
        "blocked_count":len(blocked),
        "implemented":implemented,
        "blocked":blocked,
        "negative_claim":"IMPLEMENTED means bound to an existing trusted local execution surface; it does not mean validated, OOS-passed, or promoted.",
    }
    OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"TRY_IMPLEMENTATION_ABSORPTION status={payload['status']} implemented={len(implemented)} blocked={len(blocked)}")
    # BLOCKED candidates are a governed negative outcome, not a controller failure.
    # Only a missing/invalid absorption proof above is fatal. The controller must
    # persist the blocked set and continue researching the executable subset.
    return 0

if __name__=="__main__":
    raise SystemExit(main())
