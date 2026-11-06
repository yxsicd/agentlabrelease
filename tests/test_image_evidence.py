import base64
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('image_evidence', Path(__file__).resolve().parents[1] / 'examples/benchmark-report/image_evidence.py')
image_evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image_evidence)


def put(path, value):
    path.write_text(json.dumps(value))


def response(path, call_id='call-1'):
    event = {'type': 'response.output_item.done', 'item': {'type': 'function_call', 'name': 'view_image', 'call_id': call_id}}
    path.write_text('data: ' + json.dumps(event) + '\n\n')


def request(call_id='call-1', payload=b'private image bytes'):
    return {'input': [{'type': 'function_call_output', 'call_id': call_id,
                      'output': [{'type': 'input_image', 'image_url': 'data:image/jpeg;base64,' + base64.b64encode(payload).decode()}]}]}


class ImageEvidenceTest(unittest.TestCase):
    def test_matches_call_to_forwarded_bytes_without_leaking_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); response(p / '0001.response')
            put(p / '0002.request.json', request()); put(p / '0002.upstream-request.json', request()); put(p / '0002.status.json', {'status': 200})
            row = image_evidence.reconcile(p)['calls'][0]
            self.assertEqual(row['request_exchange'], '0002')
            self.assertEqual(row['image_input'], 'observed')
            self.assertEqual(row['forwarded_to_intermediate'], 'observed')
            self.assertEqual(row['provider_delivery'], 'unknown')
            self.assertNotIn('private image bytes', json.dumps(row))
            self.assertNotIn('data:image', json.dumps(row))

    def test_unknown_when_no_status_or_different_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); response(p / '0001.response')
            put(p / '0002.request.json', request()); put(p / '0002.upstream-request.json', request())
            self.assertEqual(image_evidence.reconcile(p)['calls'][0]['forwarded_to_intermediate'], 'unknown')
            put(p / '0002.status.json', {'status': 200}); put(p / '0002.upstream-request.json', request(payload=b'other'))
            self.assertEqual(image_evidence.reconcile(p)['calls'][0]['forwarded_to_intermediate'], 'unknown')

    def test_request_without_response_and_unrelated_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); response(p / '0001.response')
            put(p / '0002.request.json', request('other'))
            self.assertEqual(image_evidence.reconcile(p)['calls'][0]['image_input'], 'not_observed')
            put(p / '0002.request.json', request())
            self.assertEqual(image_evidence.reconcile(p)['calls'][0]['image_input'], 'observed')

    def test_duplicate_call_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp); response(p / '0001.response'); response(p / '0002.response')
            with self.assertRaises(image_evidence.EvidenceError):
                image_evidence.reconcile(p)


if __name__ == '__main__':
    unittest.main()
