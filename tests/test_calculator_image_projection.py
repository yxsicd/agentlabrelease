import importlib.util
import base64
import json
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).resolve().parents[1] / 'examples/benchmark-report/calculator-timeline/project.py'
spec = importlib.util.spec_from_file_location('calculator_projection', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ImageProjectionTest(unittest.TestCase):
    def test_observed_evidence_is_counted_without_private_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); gateway=root/'gateway';gateway.mkdir()
            event={'type':'response.output_item.done','item':{'type':'function_call','name':'view_image','call_id':'private-id'}}
            (gateway/'0001.response').write_text('data: '+json.dumps(event)+'\n\n')
            payload=base64.b64encode(b'private-image').decode()
            request={'input':[{'type':'function_call_output','call_id':'private-id','output':[{'type':'input_image','image_url':'data:image/jpeg;base64,'+payload}]}]}
            for name in ('0002.request.json','0002.upstream-request.json'):
                (gateway/name).write_text(json.dumps(request))
            (gateway/'0002.status.json').write_text(json.dumps({'status':200}))
            image_path=path.parents[1]/'image_evidence.py';image_spec=importlib.util.spec_from_file_location('image_evidence',image_path);image=importlib.util.module_from_spec(image_spec);image_spec.loader.exec_module(image)
            doc=image.reconcile(gateway);doc.update(analysisStatus='completed',captureInventoryStatus='complete')
            receipt=root/'receipt.json';receipt.write_text(json.dumps(doc))
            result = module.image_projection(receipt,gateway)
            (gateway/'0002.upstream-request.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'differs'): module.image_projection(receipt,gateway)
        self.assertEqual(result['view_image_calls'], 1)
        self.assertEqual(result['forwarded_to_intermediate'], 1)
        self.assertEqual(result['provider_delivery'], 'unknown')
        self.assertNotIn('private-id', json.dumps(result))
        self.assertNotIn('private-image', json.dumps(result))

    def test_missing_and_failed_analysis_are_not_zero(self):
        self.assertIsNone(module.image_projection(None)['view_image_calls'])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'receipt.json'
            path.write_text(json.dumps({'schema':'agentlab.image_evidence_reconciliation.v1',
                'analysisStatus':'error','captureInventoryStatus':'incomplete','calls':[]}))
            result = module.image_projection(path)
        self.assertIsNone(result['view_image_calls'])
        self.assertEqual(result['capture_inventory'], 'incomplete')

    def test_unproven_provider_delivery_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'receipt.json'
            path.write_text(json.dumps({'schema':'agentlab.image_evidence_reconciliation.v1',
                'analysisStatus':'completed','captureInventoryStatus':'complete',
                'calls':[{'forwarded_to_intermediate':'observed','provider_delivery':'observed'}]}))
            with self.assertRaises(ValueError): module.image_projection(path)


if __name__ == '__main__':
    unittest.main()
