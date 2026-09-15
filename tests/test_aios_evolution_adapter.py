import os
import unittest

from engine.aios_evolution import TryEvaluation, admit, challenge, evaluate, make_candidate, promote


@unittest.skipUnless(os.environ.get("AIOS_ROOT"), "AIOS_ROOT is required for central integration")
class AIOSEvolutionAdapterTest(unittest.TestCase):
    def test_full_governed_lifecycle(self):
        root = os.environ["AIOS_ROOT"]
        candidate = make_candidate(
            {
                "strategy_id": "adapter-smoke",
                "hypothesis": "integration smoke",
                "market": {"symbol": "BTCUSDT"},
                "timeframe": "1h",
                "features": {},
                "entry": {"kind": "reference"},
                "exit": {"kind": "reference"},
                "risk": {"stop_fraction": 0.01},
                "execution": {"round_trip_cost": 0.0},
                "stop_fraction": 0.01,
                "reward_multiple": 2.0,
            },
            candidate_id="try-adapter-smoke",
            aios_root=root,
        )
        candidate = challenge(candidate, aios_root=root)
        evaluation = TryEvaluation(
            held_in={"status": "PASS", "stage": "validation", "metrics": {"profit_factor": 1.2}},
            held_out={"status": "PASS", "stage": "oos_locked", "metrics": {"profit_factor": 1.1}},
            evidence_refs=("try://result/test", "try://strategy/test"),
            evaluator_digest="adapter-test-evaluator-v1",
        )
        candidate = evaluate(candidate, evaluation, aios_root=root)
        candidate = admit(candidate, aios_root=root)
        candidate = promote(candidate, authorize=lambda c: None, aios_root=root)
        self.assertEqual(candidate.state, "ACTIVE")


if __name__ == "__main__":
    unittest.main()
