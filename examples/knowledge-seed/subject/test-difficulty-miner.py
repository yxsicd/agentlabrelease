#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("difficulty_miner", HERE / "difficulty-miner.py")
M = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(M)


def decision(verdicts, process=None, infra=True, errors=None):
    return {"schema":"agentlab.harness_decision_package.v1","infrastructureAvailable":infra,
            "phaseVerdicts":verdicts,"participantProcess":process or [],"launchErrors":errors or []}


class DifficultyMinerTest(unittest.TestCase):
    def test_repeated_arkts_signature_becomes_reproducible(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); ev=root/'e'; ev.mkdir()
            (ev/'parent-turn-2-build-stderr.log').write_text('ERROR ArkTS: arkts-limited-throw at foo.ets:4:2\n')
            d=decision([{"phase":"parent-turn-2","behaviorPass":True,"buildPass":False}])
            p=root/'d.json'; p.write_text(json.dumps(d))
            obs=M.observations('r1',p,ev)+M.observations('r2',p,ev)
            rows=M.aggregate(obs)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['signature'],'arkts-limited-throw')
            self.assertTrue(rows[0]['reproducible'])
            self.assertEqual(rows[0]['runCount'],2)

    def test_parent_and_fresh_make_context_independent_candidate(self):
        d=decision([
            {"phase":"parent-turn-2","behaviorPass":False,"buildPass":True},
            {"phase":"fresh-fork-turn-2","behaviorPass":False,"buildPass":True},
        ])
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'d.json';p.write_text(json.dumps(d))
            row=M.aggregate(M.observations('r',p,None))[0]
            self.assertTrue(row['reproducible'])
            self.assertEqual(row['contextSensitivity']['classification'],'context-independent-observed')

    def test_transport_failure_is_not_task_difficulty(self):
        d=decision([{"phase":"turn-1","behaviorPass":False,"buildPass":False}], infra=False,
                   errors=[{"phase":"gateway-preflight","error":"gateway readiness failed"}])
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'d.json';p.write_text(json.dumps(d))
            self.assertEqual(M.observations('r',p,None),[])

    def test_timeout_before_mutation_is_localization_candidate(self):
        d=decision([{"phase":"turn-1","behaviorPass":False,"buildPass":True}],
                   [{"phase":"turn-1","timedOut":True,"firstSourceMutationMs":None}])
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'d.json';p.write_text(json.dumps(d))
            cats={x['category'] for x in M.aggregate(M.observations('r',p,None))}
            self.assertEqual(cats,{"localization-planning","semantic"})

    def test_checkpoint_candidate_is_linked_but_not_upgraded_to_formal_snapshot(self):
        d=decision([{"phase":"parent-turn-2","behaviorPass":True,"buildPass":False}])
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);ev=root/'e';cp=ev/'difficulty-checkpoints/parent-turn-2';cp.mkdir(parents=True)
            (cp/'checkpoint.json').write_text(json.dumps({"schema":"agentlab.difficulty_checkpoint_candidate.v1","formalSessionFsSnapshot":False,"readyForControlledFork":False,"nativeSession":{"sha256":"abc"}}))
            (ev/'parent-turn-2-build-stderr.log').write_text('arkts-limited-throw')
            p=root/'d.json';p.write_text(json.dumps(d))
            row=M.aggregate(M.observations('r',p,ev))[0]
            self.assertEqual(row['checkpointPolicy']['capturedCandidateCount'],1)
            self.assertEqual(row['checkpointPolicy']['formalSnapshotCount'],0)
            self.assertFalse(row['observations'][0]['checkpointCandidate']['readyForControlledFork'])


if __name__ == '__main__': unittest.main()
