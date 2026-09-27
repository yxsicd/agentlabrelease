import json
import math
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BENCHMARK = (
    ROOT
    / "release/qualifications/harmony-real-multi-repo-34661ff/component-cache-benchmark.json"
)


class MultiRepoComponentCacheBenchmarkTests(unittest.TestCase):
    def test_retained_benchmark_is_internally_consistent(self) -> None:
        value = json.loads(BENCHMARK.read_text(encoding="utf-8"))
        self.assertEqual(
            value["schema"], "agentlab.multi_repo_component_cache_benchmark.v1"
        )
        self.assertEqual(value["status"], "machine-local-preliminary")
        self.assertRegex(value["methodRevision"], r"^[0-9a-f]{40}$")
        self.assertRegex(value["source"]["sourceSetSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(value["source"]["files"], 12711)
        self.assertEqual(
            value["source"]["changedRepositoryFiles"]
            + value["source"]["reusedRepositoryFiles"],
            value["source"]["files"],
        )
        self.assertEqual(value["cache"]["mode"], "exact-repository-projection")
        self.assertFalse(value["cache"]["authority"])
        self.assertFalse(value["cache"]["fileCacheEnabled"])
        self.assertTrue(value["cache"]["crossRepositoryResolutionRecomputed"])
        self.assertTrue(value["cache"]["exactSourceSetBundleRemainsPreferred"])

        reused = value["pairedChangedRevisionTrial"]["componentReuse"]
        control = value["pairedChangedRevisionTrial"]["uncachedControl"]
        self.assertEqual((reused["componentHits"], reused["componentMisses"]), (1, 1))
        self.assertEqual(reused["componentWrites"], 1)
        self.assertTrue(
            math.isclose(
                value["pairedChangedRevisionTrial"]["wallSpeedup"],
                control["wallSeconds"] / reused["wallSeconds"],
                rel_tol=5e-3,
            )
        )
        self.assertTrue(
            math.isclose(
                value["pairedChangedRevisionTrial"]["userCpuSpeedup"],
                control["userCpuSeconds"] / reused["userCpuSeconds"],
                rel_tol=5e-3,
            )
        )
        expected_reduction = (
            1
            - reused["maximumResidentBytes"] / control["maximumResidentBytes"]
        ) * 100
        self.assertTrue(
            math.isclose(
                value["pairedChangedRevisionTrial"][
                    "maximumResidentReductionPercent"
                ],
                expected_reduction,
                rel_tol=5e-3,
            )
        )
        self.assertGreater(
            control["maximumResidentBytes"], reused["maximumResidentBytes"]
        )

        for artifact in value["artifacts"].values():
            self.assertGreater(artifact["bytes"], 0)
            self.assertRegex(artifact["sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(value["artifactDigestsByteIdenticalAgainstUncachedControl"])
        self.assertEqual(value["trialCountPerPairedProfile"], 1)
        self.assertFalse(value["automaticPromotion"])
        self.assertIn(
            "population-level performance or variance",
            value["qualificationBoundary"]["notQualified"],
        )


if __name__ == "__main__":
    unittest.main()
