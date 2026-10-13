import unittest


class CheckpointContractTests(unittest.TestCase):
    """Static contract checks for the Durable Object API contract.

    Runtime transition tests are exercised by the Worker integration workflow.
    """

    def test_worker_declares_durable_checkpoint_binding_and_routes(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        entry = (root / "src" / "entry.py").read_text(encoding="utf-8")
        config = (root / "wrangler.jsonc").read_text(encoding="utf-8")
        checkpoint = (root / "src" / "checkpoint.js").read_text(encoding="utf-8")
        self.assertIn("/v1/repair/checkpoint", entry)
        self.assertIn("REPAIR_CHECKPOINTS", entry)
        self.assertIn('"REPAIR_CHECKPOINTS"', config)
        self.assertIn("blockConcurrencyWhile", checkpoint)
        self.assertIn("checkpoint_identity_conflict", checkpoint)
        self.assertIn("done_requires_persisted_evidence_digest", checkpoint)
        self.assertIn("retry_requires_blocked_prior_and_resume_phase", checkpoint)


if __name__ == "__main__":
    unittest.main()
