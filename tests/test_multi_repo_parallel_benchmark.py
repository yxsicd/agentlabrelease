import json
import math
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BENCHMARK = (
    ROOT
    / "release/qualifications/harmony-real-multi-repo-34661ff/parallel-analysis-benchmark.json"
)


class MultiRepoParallelBenchmarkTests(unittest.TestCase):
    def test_retained_benchmark_is_internally_consistent(self) -> None:
        value = json.loads(BENCHMARK.read_text(encoding="utf-8"))
        self.assertEqual(value["schema"], "agentlab.multi_repo_parallel_analysis_benchmark.v1")
        self.assertEqual(value["status"], "machine-local-preliminary")
        self.assertRegex(value["methodRevision"], r"^[0-9a-f]{40}$")
        self.assertRegex(value["source"]["sourceSetSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(value["source"]["gitObjectDatabase"], "warm")
        self.assertEqual(value["trialCountPerProfile"], 1)
        self.assertFalse(value["automaticPromotion"])

        artifacts = value["artifacts"]
        self.assertTrue(artifacts)
        for artifact in artifacts.values():
            self.assertGreater(artifact["bytes"], 0)
            self.assertRegex(artifact["sha256"], r"^[0-9a-f]{64}$")

        source_bytes = value["source"]["bytes"]
        files = value["source"]["files"]
        facts = value["source"]["facts"]
        trials = value["trials"]
        self.assertEqual([row["jobs"] for row in trials], [1, 4, 8])
        baseline = trials[0]["wallSeconds"]
        for row in trials:
            wall = row["wallSeconds"]
            self.assertEqual(row["processModel"], "fresh-process-warm-git-object-database")
            self.assertTrue(
                math.isclose(row["sourceMiBPerSecond"], source_bytes / 1048576 / wall, rel_tol=5e-4)
            )
            self.assertTrue(
                math.isclose(row["sourceNanosecondsPerByte"], wall * 1e9 / source_bytes, rel_tol=5e-4)
            )
            self.assertTrue(math.isclose(row["filesPerSecond"], files / wall, rel_tol=5e-4))
            self.assertTrue(math.isclose(row["factsPerSecond"], facts / wall, rel_tol=5e-4))
            self.assertTrue(
                math.isclose(row["speedupOverOneWorker"], baseline / wall, rel_tol=5e-3)
            )

        self.assertIn("population-level performance or variance", value["qualificationBoundary"]["notQualified"])


if __name__ == "__main__":
    unittest.main()
