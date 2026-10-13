import unittest


class CheckpointContractTests(unittest.TestCase):
    def test_worker_declares_durable_checkpoint_binding_and_routes(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        entry = (root / "src" / "entry.py").read_text(encoding="utf-8")
        config = (root / "wrangler.jsonc").read_text(encoding="utf-8")
        self.assertIn("class RepairCheckpoint(DurableObject)", entry)
        self.assertIn("/v1/repair/checkpoint", entry)
        self.assertIn("REPAIR_CHECKPOINTS", entry)
        self.assertIn('"REPAIR_CHECKPOINTS"', config)
        self.assertIn('"new_sqlite_classes": [\n      "RepairCheckpoint"', config)
        self.assertIn("checkpoint_identity_conflict", entry)
        self.assertIn("done_requires_persisted_evidence_digest", entry)
        self.assertIn("retry_requires_blocked_prior_and_resume_phase", entry)


if __name__ == "__main__":
    unittest.main()
