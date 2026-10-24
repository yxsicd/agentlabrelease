import copy
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('contract', Path(__file__).with_name('assess-declared-report.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class DeclaredReportTest(unittest.TestCase):
    def setUp(self):
        self.contract = {'schema': m.SCHEMA, 'observationIds': ['case-a', 'case-b'], 'referencePrefix': 'case-', 'rules': [
            {'id': 'coverage', 'kind': 'coverage'},
            {'id': 'value', 'kind': 'comparison', 'observationId': 'case-a', 'oracleKey': 'values', 'fieldTypes': {'actualResult': 'string'}},
            {'id': 'evidence', 'kind': 'evidence_path', 'observationId': 'case-a', 'oracleKey': 'path'},
            {'id': 'identity', 'kind': 'exact', 'oracleKey': 'identity', 'fieldTypes': {'executed': 'boolean'}}]}
        self.oracle = {'values': {'actualResult': 'Result: []'}, 'path': '/workspace/raw/a.json', 'identity': {'executed': False}}
        self.report = {'executed': False, 'observations': [
            {'selector': 'id=case-a (Button), checked via id=result-text', 'actualResult': 'Result: []', 'rawLayoutPath': '/workspace/raw/a.json'},
            {'selector': 'case-b'}]}

    def assess(self):
        return m.assess(json.dumps(self.report).encode(), self.contract, self.oracle)

    def test_bare_and_descriptive_references(self):
        self.assertEqual(self.assess()['verdict'], 'pass')
        self.report['observations'][0]['selector'] = 'case-a'
        self.assertEqual(self.assess()['verdict'], 'pass')
        self.assertIn(json.dumps(self.contract, indent=2), m.describe(self.contract))

    def test_wrong_ambiguous_or_duplicate_reference(self):
        for selector in ['case-unknown', 'case-a case-b', 'case-a case-unknown', 'xcase-a', 'case-a case-a']:
            with self.subTest(selector=selector):
                self.report['observations'][0]['selector'] = selector
                self.assertEqual(self.assess()['verdict'], 'fail')
        self.report['observations'][0]['selector'] = 'case-b'
        self.assertEqual(self.assess()['verdict'], 'fail')

    def test_wrong_value_or_provenance(self):
        for field, value in [('actualResult', 'Result: [2]'), ('rawLayoutPath', '/other/a.json'), ('rawLayoutPath', '/workspace/raw/../raw/a.json')]:
            with self.subTest(field=field, value=value):
                r = copy.deepcopy(self.report)
                self.report['observations'][0][field] = value
                self.assertEqual(self.assess()['verdict'], 'fail')
                self.report = r
        self.report['executed'] = 0
        self.assertEqual(self.assess()['verdict'], 'fail')

    def test_evaluator_missing_oracle_is_not_student_failure(self):
        del self.oracle['values']
        with self.assertRaises(KeyError):
            self.assess()

    def test_malformed_and_duplicate_json_fail(self):
        for raw in [b'[]', b'{', b'{"executed":false,"executed":false}', b'null']:
            self.assertEqual(m.assess(raw, self.contract, self.oracle)['verdict'], 'fail')

    def test_unknown_rule_and_missing_field(self):
        self.contract['rules'].append({'id': 'bad', 'kind': 'guess'})
        with self.assertRaises(ValueError):
            self.assess()
        self.contract['rules'].pop()
        del self.report['executed']
        self.assertEqual(self.assess()['verdict'], 'fail')


if __name__ == '__main__':
    unittest.main()
