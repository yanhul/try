import json
import unittest

from algorithm_runtime import (
    AlgorithmBudgetExceeded, AlgorithmInputError, execute,
)


class AlgorithmRuntimeTests(unittest.TestCase):
    def request(self, grid, budget=100):
        return {
            "spec": {"operation": "maze.shortest_path", "version": 1,
                     "max_expansions": budget},
            "input": {"grid": grid},
        }

    def test_shortest_path_and_content_addressed_artifact(self):
        result = execute(self.request(["S..", ".#.", "..G"]))
        self.assertEqual(result["artifact"]["path"], [[0, 0], [0, 1], [0, 2], [1, 2], [2, 2]])
        self.assertEqual(result["artifact_sha256"], result["output_sha256"])
        self.assertEqual(json.loads(result["artifact_bytes"]), result["artifact"])

    def test_unreachable_is_explicit_null_path(self):
        result = execute(self.request(["S#G"]))
        self.assertIsNone(result["artifact"]["path"])

    def test_budget_is_enforced(self):
        with self.assertRaises(AlgorithmBudgetExceeded):
            execute(self.request(["S..G"], budget=1))

    def test_unknown_fields_rejected(self):
        request = self.request(["SG"])
        request["spec"]["python"] = "arbitrary code"
        with self.assertRaisesRegex(AlgorithmInputError, "spec_fields_invalid"):
            execute(request)

    def test_grid_shape_and_marker_cardinality_rejected(self):
        for grid in (["S.", "G"], ["SSG"], ["S.."]):
            with self.subTest(grid=grid):
                with self.assertRaises(AlgorithmInputError):
                    execute(self.request(grid))

    def test_bool_budget_is_not_accepted_as_integer(self):
        with self.assertRaisesRegex(AlgorithmInputError, "expansion_budget_invalid"):
            execute(self.request(["SG"], budget=True))


if __name__ == "__main__":
    unittest.main()
