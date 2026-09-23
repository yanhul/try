#!/usr/bin/env python3
"""Persist a strict discovery absorption receipt.

ABSORBED means the scanned source survived provenance/executable-lane gates,
was durably represented in the research queue, and is eligible for the
autonomous frontier. It does not imply strategy validity or promotion.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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
    for source in records:
        sid = str(source.get("source_id") or "")
        family = str(source.get("family") or "")
        lineage = source.get("lineage") or {}
        rounds = lineage.get("rounds") or []
        decisions = {str(x.get("decision")) for x in rounds if isinstance(x, dict)}
        candidate = by_url.get(str(source.get("url") or ""))
        if not source.get("is_system"):
            continue
        if not source.get("url"):
            blocked.append({"source_id": sid, "reason": "missing_source_url"})
            continue
        if not {"PASS_SOURCE","PASS_EXECUTABLE_DATA_LANE","PASS_DIVERSITY_DEDUP"} <= decisions:
            blocked.append({"source_id": sid, "reason": "source_gates_incomplete"})
            continue
        if family not in EXECUTABLE_FAMILIES:
            blocked.append({"source_id": sid, "reason": f"non_executable_family:{family}"})
            continue
        if not candidate:
            blocked.append({"source_id": sid, "reason": "not_present_in_research_frontier"})
            continue
        if not candidate.get("lineage"):
            blocked.append({"source_id": sid, "reason": "candidate_lineage_missing"})
            continue
        absorbed.append({
            "source_id": sid,
            "candidate_id": sid,
            "family": family,
            "source_url": source["url"],
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
