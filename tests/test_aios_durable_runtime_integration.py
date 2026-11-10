"""Cross-repository integration against the pinned AIOS authority/effect APIs.

Uses a fake provider/runtime so the test proves boundary wiring and identity
checks, not live provider behavior or production scheduling.
"""
from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

import engine.aios_path  # noqa: F401  (pins AIOS as `core`)
from core.authority import persist_contract, persist_permit
from core.capabilities import Capability, CapabilityRegistry
from core.contract import contract_identity
from core.durable_runtime import RuntimeSubmission
from core.policy_registry import persist_policy
from core.runtime import ProviderReceipt, execute


class FakeProvider:
    name = "try-integration-fixture"

    def __init__(self, *, fail: bool = False):
        self.calls = 0
        self.fail = fail

    def execute(self, *, contract, effect, attempt_id):
        self.calls += 1
        if self.fail:
            raise TimeoutError("fixture provider timeout")
        return ProviderReceipt(
            provider=self.name,
            effect_id=effect["effect_id"],
            attempt_id=attempt_id,
            provider_operation_id="fixture-op-1",
            outcome="OBSERVED_SUCCESS",
            observation={"fixture": True},
        )


class RecordingRuntime:
    name = "try-recording-runtime"

    def __init__(self):
        self.submissions = []

    def submit(self, *, effect, attempt_id):
        self.submissions.append((effect["effect_id"], attempt_id))
        return RuntimeSubmission(effect["effect_id"], attempt_id, FakeProvider.name)

    def resume(self, *, effect, attempt_id):
        return RuntimeSubmission(effect["effect_id"], attempt_id, FakeProvider.name)

    def retry(self, *, effect, attempt_id, attempt):
        return RuntimeSubmission(effect["effect_id"], attempt_id, FakeProvider.name)


def make_authority(root: str) -> tuple[str, str]:
    registry = CapabilityRegistry()
    registry.register(
        Capability(
            "try-integration-fixture",
            "1",
            "TRY integration test",
            "provider",
            status="ACTIVE",
        )
    )
    registry.persist(root, "TRY integration test")
    policy_digest = persist_policy(
        root,
        {"policy_type": "GOVERNING_POLICY", "name": "try-durable-runtime-integration"},
    )
    contract = {
        "contract_type": "EXECUTION_CONTRACT",
        "task_id": "try-durable-runtime-integration",
        "scope": "cross-repository-test",
        "actor": "agent:try-integration",
        "capabilities": ["try-integration-fixture@1"],
        "input_digest": "fixture-input-v1",
        "allowed_effects": ["external_effect"],
        "evidence_required": ["provider_receipt"],
        "max_attempts": 1,
        "terminal_states": ["SUCCESS", "FAILURE"],
        "policy_digest": policy_digest,
    }
    contract_id = contract_identity(contract)
    persist_contract(root, contract)
    permit = persist_permit(root, contract, "root")
    return contract_id, permit["permit_id"]


class DurableRuntimeIntegrationTest(unittest.TestCase):
    def test_try_provider_submission_is_bound_to_aios_effect_and_attempt(self):
        with TemporaryDirectory() as root:
            contract_id, permit_id = make_authority(root)
            provider = FakeProvider()
            runtime = RecordingRuntime()

            result = execute(
                root,
                contract_id,
                permit_id,
                "try-operation-1",
                "agent:try-integration",
                provider,
                runtime,
            )

            self.assertEqual(result["state"], "OBSERVED_SUCCESS")
            self.assertEqual(provider.calls, 1)
            self.assertEqual(len(runtime.submissions), 1)
            effect_id, attempt_id = runtime.submissions[0]
            self.assertEqual(effect_id, result["effect_id"])
            self.assertEqual(attempt_id, result["attempt_id"])
            self.assertEqual(attempt_id, f"{effect_id}:attempt:1")
            self.assertIn("provider_observation", result)

    def test_ambiguous_provider_failure_remains_unknown_not_pass(self):
        with TemporaryDirectory() as root:
            contract_id, permit_id = make_authority(root)
            provider = FakeProvider(fail=True)
            runtime = RecordingRuntime()

            result = execute(
                root,
                contract_id,
                permit_id,
                "try-operation-timeout",
                "agent:try-integration",
                provider,
                runtime,
            )

            self.assertEqual(result["state"], "UNKNOWN")
            self.assertNotEqual(result["state"], "PASS")
            self.assertEqual(provider.calls, 1)
            self.assertEqual(len(runtime.submissions), 1)


if __name__ == "__main__":
    unittest.main()
