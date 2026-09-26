import json
import math
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BENCHMARK = (
    ROOT
    / "release/qualifications/harmony-real-multi-repo-34661ff/aggregate-cache-benchmark.json"
)


class MultiRepoAggregateCacheBenchmarkTests(unittest.TestCase):
    def test_retained_benchmark_is_internally_consistent(self) -> None:
        value = json.loads(BENCHMARK.read_text(encoding="utf-8"))
        self.assertEqual(
            value["schema"], "agentlab.multi_repo_aggregate_cache_benchmark.v1"
        )
        self.assertEqual(value["status"], "machine-local-preliminary")
        self.assertRegex(value["methodRevision"], r"^[0-9a-f]{40}$")
        self.assertRegex(value["source"]["sourceSetSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(value["source"]["files"], 12711)
        self.assertEqual(value["cache"]["mode"], "exact-source-set-bundle")
        self.assertFalse(value["cache"]["authority"])
        self.assertFalse(value["cache"]["fileCacheEnabled"])
        self.assertEqual(value["cache"]["files"], 5)
        self.assertEqual(value["trialCountPerProfile"], 1)
        self.assertFalse(value["automaticPromotion"])

        artifact_bytes = 0
        for artifact in value["artifacts"].values():
            self.assertGreater(artifact["bytes"], 0)
            self.assertRegex(artifact["sha256"], r"^[0-9a-f]{64}$")
            artifact_bytes += artifact["bytes"]
        self.assertGreater(value["cache"]["logicalBytesIncludingIndex"], artifact_bytes)

        cold, warm = value["trials"]
        self.assertEqual(cold["profile"], "cold-bundle-miss")
        self.assertEqual(warm["profile"], "warm-exact-bundle-hit")
        self.assertEqual((cold["bundleHits"], cold["bundleMisses"]), (0, 1))
        self.assertEqual((warm["bundleHits"], warm["bundleMisses"]), (1, 0))
        self.assertTrue(
            math.isclose(
                warm["speedupOverColdBundleMiss"],
                cold["wallSeconds"] / warm["wallSeconds"],
                rel_tol=5e-3,
            )
        )
        self.assertTrue(value["artifactDigestsByteIdenticalAcrossTrials"])
        self.assertIn(
            "positive wall-time benefit from the opt-in changed-revision per-file cache",
            value["qualificationBoundary"]["notQualified"],
        )


if __name__ == "__main__":
    unittest.main()
