"""Harness-owned CI evidence ingestion into the released runtime source tables.

This is observed-source coverage, not normalized Sandbox side-effect coverage.
Only selected evidence files are ingested, never the build Workspace/runtime.
"""
import base64
import hashlib
import json
from pathlib import Path
import time
import uuid

OBS = 'data/tables/agentlab/v3/runtime_observations'
CHUNKS = 'data/tables/agentlab/v3/runtime_payload_chunks'
PAGE = 8
CHUNK_BYTES = 16384


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ident(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_OID, '\0'.join(parts)))


def collect(root, session_id, operation_id, agent_kind="pi", context=None):
    root = Path(root)
    rows, objects = [], []
    inventory = []
    def observe(value, method, source, status='observed'):
        ordinal = len(objects)
        key = ident('agentlab.ci.observation.v1', operation_id, str(ordinal))
        raw = canonical(value)
        parts = [raw[i:i+CHUNK_BYTES] for i in range(0, len(raw), CHUNK_BYTES)]
        row = dict(schema='agentlab.runtime_observation.v1', observationId=key,
            operationId=operation_id, sessionId=session_id, agentKind=agent_kind, externalTurnId=source,
            ordinal=ordinal, sequence=ordinal, method=method, status=status,
            itemType=value.get('type', value.get('sourceKind', 'evidence')),
            payloadId=key, payloadDigest='sha256:'+sha(raw), payloadByteLength=len(raw),
            payloadChunkCount=len(parts))
        chunk_rows = []
        for number, part in enumerate(parts):
            chunk = dict(schema='agentlab.runtime_payload_chunk.v1',
                payloadChunkId=ident('agentlab.ci.chunk.v1',key,str(number)),
                operationId=operation_id, payloadId=key, ordinal=number,
                byteOffset=number*CHUNK_BYTES, byteLength=len(part), textUtf8=part.decode())
            chunk_rows.append(chunk)
            rows.append((CHUNKS,chunk['payloadChunkId'],chunk))
        rows.append((OBS,key,row))
        objects.append({'row':row,'chunks':chunk_rows,'value':value,'rawFile':method=='capture.file'})
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        inventory.append(dict(path=relative,bytes=len(raw),sha256=sha(raw)))
        # The raw file remains recoverable byte for byte, including JSONL and SSE.
        observe(dict(sourceKind='operator_captured_file',path=relative,byteLength=len(raw),
            sha256=sha(raw),bytesBase64=base64.b64encode(raw).decode()),
            'capture.file',relative)
        if path.parent.name == 'gateway' and path.suffix == '.json':
            value=json.loads(raw)
            method=('gateway.status' if path.name.endswith('.status.json') else
                    'gateway.upstream_request' if path.name.endswith('.upstream-request.json') else
                    'gateway.request')
            observe(dict(sourceKind='llm_gateway',path=relative,exchangeId=path.name.split('.')[0],
                         document=value),method,relative)
        if path.parent.name == 'gateway' and path.suffix == '.response':
            for line_number,line in enumerate(raw.splitlines(),1):
                if line.startswith(b'data:') and line[5:].strip() != b'[DONE]':
                    value=json.loads(line[5:].strip())
                    observe(dict(sourceKind='llm_gateway',path=relative,
                        exchangeId=path.name.split('.')[0],streamOrdinal=line_number,document=value),
                        'gateway.response_event',relative+':'+str(line_number))
        if path.name.endswith('-events.jsonl') or path.name=='events.jsonl':
            for line_number,line in enumerate(raw.splitlines(),1):
                if line.strip():
                    value=json.loads(line)
                    observe(value,agent_kind+'.'+str(value.get('type',value.get('kind','unknown'))),relative+':'+str(line_number))
    observe(dict(sourceKind='operator_capture_provenance',sessionId=session_id,
        operationId=operation_id,participantKind=agent_kind,context=context or {},
        inventoryDigest=sha(canonical(inventory)),fileCount=len(inventory)),
        'capture.provenance','operator')
    if not inventory:
        raise ValueError('No captured evidence files; missing capture is not a successful run')
    return rows,objects,inventory


class Service:
    def __init__(self,url,authorization,evidence):
        self.url,self.authorization,self.evidence=url,authorization,Path(evidence)
        self.counter=0
    def call(self,method,payload):
        from websocket import create_connection
        request_id=str(uuid.uuid4())
        envelope={'kind':'request','message':{'protocol':'mcpgit.service.v2',
            'request_id':request_id,'invocation_id':str(uuid.uuid4()),'method':method,
            'deadline_unix_ms':int(time.time()*1000)+120000,'payload':payload}}
        self.counter+=1
        path=self.evidence/f'capture-rpc-{self.counter:04d}.json'
        record={'request':envelope}
        # Preserve operation identity before dispatch, including unknown outcomes.
        path.write_bytes(canonical(record)+b'\n')
        connection=None
        try:
            connection=create_connection(self.url,timeout=120,host='gateway',
                subprotocols=['mcpgit.service.ws.v1'],header={'Authorization':self.authorization})
            connection.send_binary(canonical(envelope))
            result=json.loads(connection.recv())
            record['response']=result
        except Exception as error:
            record['transportError']={'class':type(error).__name__,'message':str(error),
                                      'outcomeUnknown':True}
            raise
        finally:
            if connection is not None: connection.close()
            path.write_bytes(canonical(record)+b'\n')
        message=result['message']
        if message['request_id']!=request_id or message['outcome']!='success':
            raise RuntimeError(f'{method}: see capture RPC evidence')
        return message['payload']


def ingest(service,repo,rows,operation_id):
    worktree={'topic_id':'main'}
    revision=service.call('table.worktree.open',{'repo':repo,'worktree':worktree})['revision']
    commits=[]
    for start in range(0,len(rows),PAGE):
        group={}
        transaction=ident('agentlab.ci.capture.transaction.v1',operation_id,str(start))
        for table,key,row in rows[start:start+PAGE]:
            group.setdefault(table,[]).append({'op':'insert',
                'operation_id':ident(transaction,table,key),'key':key,'row':row})
        request={'repo':repo,'worktree':worktree,'expected_revision':revision,
            'transaction_id':transaction,'idempotency_key':transaction,'actor':None,
            'tables':[{'path':table,'operations':operations} for table,operations in group.items()],
            'message':'Harness-owned real Code Agent CI capture'}
        result=service.call('table.transact',request)
        if not result['applied'] or result.get('conflicts'):
            raise RuntimeError('Capture transaction did not apply; preserve exact request and reconcile')
        revision=result['revision']
        commits.append({'transactionId':transaction,'revision':revision})
    return revision,commits


def recover(service,repo,revision,rows,objects,inventory,destination):
    actual={}
    for table in (OBS,CHUNKS):
        selected=[(key,row) for path,key,row in rows if path==table]
        for start in range(0,len(selected),PAGE):
            keys=[key for key,row in selected[start:start+PAGE]]
            result=service.call('table.query',dict(repo=repo,
                view={'kind':'committed','revision':revision},path=table,keys=keys,limit=PAGE))
            if (result['revision']!=revision or result['dirty'] or result['truncated']
                    or result['source_kind']!='revision_tree'):
                raise RuntimeError('Capture read is not a complete immutable-revision read')
            for item in result['rows']:
                if item['row_version']<1 or item['deleted']:
                    raise RuntimeError('Capture row missing durable version')
                actual[(table,item['key'])]=item['row']
    if actual!={(table,key):row for table,key,row in rows}:
        raise RuntimeError('Committed capture rows differ from actual producer data')
    destination=Path(destination)
    destination.mkdir()
    for obj in objects:
        row=actual[(OBS,obj['row']['observationId'])]
        chunks=[actual[(CHUNKS,c['payloadChunkId'])] for c in obj['chunks']]
        raw=b''.join(c['textUtf8'].encode() for c in chunks)
        if len(raw)!=row['payloadByteLength'] or 'sha256:'+sha(raw)!=row['payloadDigest']:
            raise RuntimeError('Capture payload reconstruction failed')
        value=json.loads(raw)
        if value!=obj['value']:
            raise RuntimeError('Recovered observation differs from producer')
        if obj['rawFile']:
            path=destination/value['path'];path.parent.mkdir(parents=True,exist_ok=True)
            data=base64.b64decode(value['bytesBase64']);path.write_bytes(data)
            if len(data)!=value['byteLength'] or sha(data)!=value['sha256']:
                raise RuntimeError('Recovered file bytes differ from original capture')
    recovered=[dict(path=p.relative_to(destination).as_posix(),bytes=p.stat().st_size,
                    sha256=sha(p.read_bytes())) for p in sorted(destination.rglob('*')) if p.is_file()]
    if recovered!=inventory:
        raise RuntimeError('Recovered evidence inventory differs from captured inventory')
    return dict(revision=revision,rowCount=len(rows),observationCount=len(objects),
                fileCount=len(inventory),byteCount=sum(i['bytes'] for i in inventory),
                exactRows=True,exactPayloads=True,exactFiles=True,
                captureAuthority='operator_owned_ci_harness',
                normalizedSandboxSideEffects=False,fullWhiteboxQualified=False)
