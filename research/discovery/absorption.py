#!/usr/bin/env python3
"""Persist a strict discovery absorption receipt.

ABSORBED means the scanned source survived provenance/executable-lane gates,
was durably represented in the research queue, and is eligible for the
autonomous frontier. It does not imply strategy validity or promotion.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "research/discovery/system_registry.json"
QUEUE = ROOT / "research/discovery/research_queue.json"
OUT = ROOT / "research/discovery/absorption_proof.json"

EXECUTABLE_FAMILIES = {
    "momentum_trend","mean_reversion","smc_ict","fvg_imbalance",
    "wyckoff_vsa_vpa","vwap_volume_profile","regime","point_figure",
    "gann_reference","volatility",
}

def digest(obj: object) -> str:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()

def main() -> int:
    if not REGISTRY.exists() or not QUEUE.exists():
        raise SystemExit("ABSORB_BLOCKED missing discovery registry or queue")
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    records = registry.get("records", [])
    candidates = queue.get("candidates", []) if isinstance(queue, dict) else queue
    by_url = {str(x.get("source_url")): x for x in candidates if isinstance(x, dict) and x.get("source_url")}

    absorbed = []
    blocked = []
    registry_by_url = {str(x.get("url")): x for x in records if isinstance(x, dict) and x.get("url")}

    # The durable frontier is the absorption scope: every executable candidate
    # in the queue must resolve back to a provenance registry record and carry
    # the three discovery-lane decisions. Non-executable/provenance-only
    # registry records are intentionally outside the absorption denominator.
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        family = str(candidate.get("family") or "")
        url = str(candidate.get("source_url") or "")
        if family not in EXECUTABLE_FAMILIES:
            continue
        sid = str((candidate.get("lineage") or {}).get("source") or "")
        source = registry_by_url.get(url)
        rounds = (candidate.get("lineage") or {}).get("rounds") or []
        decisions = {str(x.get("decision")) for x in rounds if isinstance(x, dict)}
        if not url:
            blocked.append({"candidate_id": candidate.get("candidate_id"), "reason": "missing_source_url"})
            continue
        if not source:
            blocked.append({"candidate_id": candidate.get("candidate_id"), "reason": "source_registry_match_missing"})
            continue
        if sid and str(source.get("source_id") or "") != sid:
            blocked.append({"candidate_id": candidate.get("candidate_id"), "reason": "source_lineage_mismatch"})
            continue
        if not source.get("is_system"):
            blocked.append({"candidate_id": candidate.get("candidate_id"), "reason": "registry_record_not_system"})
            continue
        if not {"PASS_SOURCE","PASS_EXECUTABLE_DATA_LANE","PASS_DIVERSITY_DEDUP"} <= decisions:
            blocked.append({"candidate_id": candidate.get("candidate_id"), "reason": "source_gates_incomplete"})
            continue
        absorbed.append({
            "source_id": source.get("source_id"),
            "candidate_id": candidate.get("candidate_id"),
            "family": family,
            "source_url": url,
            "source_digest": digest(source),
            "candidate_digest": digest(candidate),
            "status": "ABSORBED",
            "meaning": "persisted_discovery_frontier_eligible",
        })

    payload = {
        "schema_version": 1,
        "proof_type": "TRY_DISCOVERY_ABSORPTION_PROOF",
        "status": "PASS" if absorbed and not blocked else ("PARTIAL" if absorbed else "BLOCKED"),
        "source_registry_digest": digest(registry),
        "research_queue_digest": digest(queue),
        "absorbed_count": len(absorbed),
        "blocked_count": len(blocked),
        "absorbed": absorbed,
        "blocked": blocked,
        "negative_claim": "ABSORBED does not mean validated strategy, OOS pass, or promotion.",
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"TRY_ABSORPTION status={payload['status']} absorbed={len(absorbed)} blocked={len(blocked)}")
    return 0 if payload["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
