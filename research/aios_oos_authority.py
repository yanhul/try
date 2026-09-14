from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AIOS_SOURCE = Path(os.environ.get("AIOS_SOURCE", "/tmp/aios")).resolve()
AUTHORITY_ROOT = ROOT / "research" / ".aios_authority"
WORKLOAD = ROOT / "aios" / "workload.json"
POLICY_DIGEST = "sha256:0640840b0d5ab455470a7069163a928bd6d14a79168e834bb218a79559ba46b7"


def provision(bc: int, candidate_hash: str) -> dict[str, str]:
    secret = os.environ.get("AIOS_AUTHORITY_SECRET", "")
    if not secret:
        raise RuntimeError("missing AIOS_AUTHORITY_SECRET deployment secret")
    if not AIOS_SOURCE.exists():
        raise RuntimeError(f"AIOS_SOURCE missing: {AIOS_SOURCE}")
    if not WORKLOAD.exists():
        raise RuntimeError("try workload manifest missing")

    sys.path.insert(0, str(AIOS_SOURCE))
    from core.authority import persist_attestation, persist_contract, persist_permit

    manifest = json.loads(WORKLOAD.read_text(encoding="utf-8"))
    terminal_states = list(manifest["terminal_states"])
    contract = {
        "contract_type": "EXECUTION_CONTRACT",
        "task_id": f"RESEARCH_BC{bc}",
        "scope": "try.research.oos",
        "actor": "yanhul/try",
        "capabilities": ["try.research@1"],
        "input_digest": candidate_hash,
        "allowed_effects": ["process_execution"],
        "evidence_required": ["adapter_result"],
        "max_attempts": 1,
        "terminal_states": terminal_states,
        "policy_digest": POLICY_DIGEST,
    }

    # The AIOS authority implementation is the sole issuer of durable
    # contract/permit/attestation records. Materialize every durable registry
    # input that the pinned AIOS authority actually consumes. registry.yaml is
    # descriptive; CapabilityRegistry.load() resolves capability authority
    # from capabilities/capability_registry.json.
    AUTHORITY_ROOT.mkdir(parents=True, exist_ok=True)
    (AUTHORITY_ROOT / "capabilities").mkdir(exist_ok=True)
    (AUTHORITY_ROOT / "policies").mkdir(exist_ok=True)
    capability_registry = AIOS_SOURCE / "capabilities" / "capability_registry.json"
    if not capability_registry.exists():
        raise RuntimeError(f"AIOS durable capability registry missing: {capability_registry}")
    shutil.copy2(capability_registry, AUTHORITY_ROOT / "capabilities" / "capability_registry.json")
    registry_yaml = AIOS_SOURCE / "capabilities" / "registry.yaml"
    if registry_yaml.exists():
        shutil.copy2(registry_yaml, AUTHORITY_ROOT / "capabilities" / "registry.yaml")
    policy_src = AIOS_SOURCE / "policies" / (POLICY_DIGEST + ".json")
    if not policy_src.exists():
        raise RuntimeError(f"AIOS governing policy missing: {policy_src}")
    shutil.copy2(policy_src, AUTHORITY_ROOT / "policies" / policy_src.name)

    stored_contract = persist_contract(str(AUTHORITY_ROOT), contract)
    permit = persist_permit(str(AUTHORITY_ROOT), stored_contract, "yanhul/AIOS")
    attestation = persist_attestation(str(AUTHORITY_ROOT), stored_contract, permit, secret)

    contract_path = AUTHORITY_ROOT / "authority" / "contracts" / f"{stored_contract['contract_id']}.json"
    permit_path = AUTHORITY_ROOT / "authority" / "permits" / f"{permit['permit_id']}.json"
    attestation_path = AUTHORITY_ROOT / "authority" / "attestations" / f"{permit['permit_id']}.json"
    return {
        "contract": str(contract_path),
        "permit": str(permit_path),
        "attestation": str(attestation_path),
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m research.aios_oos_authority BC CANDIDATE_HASH")
    result = provision(int(sys.argv[1]), sys.argv[2])
    print(json.dumps(result, sort_keys=True))
