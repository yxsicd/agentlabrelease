import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('capture_audit', Path(__file__).parents[1] / 'scripts/audit-llm-capture.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def fixture(self, root):
        root.mkdir()
        (root/'0001.request.json').write_text('{"input":"原文"}')
        (root/'0001.upstream-request.json').write_text('{"input":"原文","route":"selected"}')
        (root/'0001.response').write_bytes(b'error or completion')
        (root/'0001.status.json').write_text(json.dumps({'exchangeId':'0001','status':500,
            'responseBytes':19,'outcome':'completed','upstreamEof':True,'semanticComplete':False}))

    def test_failure_response_still_has_complete_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'source';self.fixture(source)
            result = audit.audit(source, 1)
            self.assertTrue(result['completeInventory'])
            self.assertEqual(result['exchanges'][0]['httpStatus'], 500)
            self.assertFalse(result['tablegitAuthorityVerified'])
            self.assertFalse(result['recoveryCompared'])

    def test_missing_or_corrupt_recovered_payload_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';back=Path(tmp)/'back';self.fixture(source);self.fixture(back)
            self.assertTrue(audit.audit(source,1,back)['recoveryMatches'])
            (back/'0001.response').write_bytes(b'changed')
            self.assertFalse(audit.audit(source,1,back)['recoveryMatches'])
            (back/'0001.request.json').unlink()
            self.assertFalse(audit.audit(source,1,back)['recoveryMatches'])

    def test_missing_exchange_cannot_look_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';self.fixture(source)
            self.assertFalse(audit.audit(source,2)['completeInventory'])
            (source/'0001.status.json').unlink()
            self.assertFalse(audit.audit(source,1)['completeInventory'])

if __name__ == '__main__': unittest.main()
