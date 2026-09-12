import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys
import types
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('capture',Path(__file__).parents[1]/'examples/tablegit-session/capture.py')
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)

class MemoryService:
    def __init__(self): self.rows={};self.revision='a'*40;self.requests=[]
    def call(self,method,payload):
        self.requests.append((method,payload))
        if method=='table.worktree.open': return {'revision':self.revision}
        if method=='table.transact_many':
            assert payload['expected_revision']==self.revision
            for table in payload['tables']:
                for op in table['operations']: self.rows[(table['path'],op['key'])]=op['row']
            self.revision=capture.sha(capture.canonical(payload))[:40]
            return {'applied':True,'conflicts':[],'revision':self.revision}
        return {'revision':payload['view']['revision'],'dirty':False,'truncated':False,
            'source_kind':'revision_tree','rows':[{'key':key,'row':self.rows[(payload['path'],key)],
            'row_version':1,'deleted':False} for key in payload['keys']]}

class CaptureTests(unittest.TestCase):
    def fixture(self,root):
        (root/'gateway').mkdir()
        (root/'gateway/0001.request.json').write_text(json.dumps({'messages':[{'role':'user','content':'完整输入'}]}))
        (root/'gateway/0001.response').write_bytes(b'data: {"choices":[{"delta":{"content":"OK"}}]}\n\ndata: [DONE]\n')
        (root/'iteration-events.jsonl').write_text(json.dumps({'type':'tool_execution_end','result':{'large':'数据'*20000}})+'\n')
        (root/'selected.hap').write_bytes(bytes(range(256))*50)
        (root/'failed.log').write_bytes(b'compiler failed\n\xff\x00')
    def test_full_committed_source_and_binary_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';root.mkdir();self.fixture(root)
            rows,objects,inventory=capture.collect(root,'session','operation')
            service=MemoryService();revision,commits=capture.ingest(service,'repo',rows,'operation')
            result=capture.recover(service,'repo',revision,rows,objects,inventory,Path(tmp)/'recovered')
            self.assertTrue(result['exactFiles']);self.assertFalse(result['fullWhiteboxQualified'])
            methods={obj['row']['method'] for obj in objects}
            self.assertTrue({'gateway.request','gateway.response_event','pi.tool_execution_end'}<=methods)
            for obj in objects:
                self.assertTrue(all(c['byteLength']<=capture.CHUNK_BYTES for c in obj['chunks']))
            self.assertTrue(all(len(p.get('keys',[]))<=capture.PAGE for m,p in service.requests))
    def test_corruption_fails_reconstruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';root.mkdir();self.fixture(root)
            rows,objects,inventory=capture.collect(root,'session','operation')
            service=MemoryService();revision,_=capture.ingest(service,'repo',rows,'operation')
            key=next(k for k in service.rows if k[0]==capture.CHUNKS)
            service.rows[key]={**service.rows[key],'textUtf8':'changed'}
            with self.assertRaises(RuntimeError):
                capture.recover(service,'repo',revision,rows,objects,inventory,Path(tmp)/'out')
    def test_unknown_outcome_retains_request_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            module=types.SimpleNamespace(create_connection=lambda *args,**kwargs: (_ for _ in ()).throw(TimeoutError('test outage')))
            service=capture.Service('ws://example.invalid','Bearer test-transport-credential',Path(tmp))
            with patch.dict(sys.modules,{'websocket':module}):
                with self.assertRaises(TimeoutError):service.call('table.transact_many',{'transaction_id':'exact-operation'})
            record=json.loads((Path(tmp)/'capture-rpc-0001.json').read_text())
            self.assertEqual(record['request']['message']['payload']['transaction_id'],'exact-operation')
            self.assertTrue(record['transportError']['outcomeUnknown'])
            self.assertNotIn('test-transport-credential',json.dumps(record))
    def test_no_fake_success_without_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):capture.collect(Path(tmp),'session','operation')
    def test_mock_source_preserves_implementation_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'events.jsonl').write_text('{"kind":"operator_test_result","verdict":"failed"}\n')
            rows,objects,_=capture.collect(root,'session','operation','mock')
            self.assertTrue(all(obj['row']['agentKind']=='mock' for obj in objects))
            self.assertIn('mock.operator_test_result',{obj['row']['method'] for obj in objects})
    def test_malformed_events_do_not_veto_complete_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';root.mkdir();(root/'gateway').mkdir()
            (root/'events.jsonl').write_bytes(b'{"type":"start"}\n{"truncated":\n[]\n{"type":"end"}\n')
            (root/'gateway/0001.response').write_bytes(b'data: {broken\ndata: {"choices":[]}\n')
            (root/'gateway/0001.request.json').write_bytes(b'\xff')
            rows,objects,inventory=capture.collect(root,'session','operation')
            errors=[o for o in objects if o['row']['method']=='capture.parse_error']
            self.assertEqual(len(errors),4)
            self.assertTrue({'pi.start','pi.end','gateway.response_event'} <= {o['row']['method'] for o in objects})
            service=MemoryService();revision,_=capture.ingest(service,'repo',rows,'operation')
            self.assertTrue(capture.recover(service,'repo',revision,rows,objects,inventory,Path(tmp)/'out')['exactFiles'])

    def test_stable_rows_for_same_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            self.assertEqual(capture.collect(root,'session','operation'),capture.collect(root,'session','operation'))

if __name__=='__main__': unittest.main()
