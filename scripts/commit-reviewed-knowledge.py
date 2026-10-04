#!/usr/bin/env python3
"""One fenced reviewed-lesson transaction; no bootstrap, rebase or write retry."""
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import threading
import urllib.request
from pathlib import Path


def read(path, limit=32 * 1024 * 1024):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('Absolute input required')
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise ValueError('Input symlink')
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Input file budget')
    data = path.read_bytes()
    if len(data) > limit:
        raise ValueError('Input grew beyond budget')
    return data


def save(root, name, value):
    with (root / name).open('x') as output:
        json.dump(value, output, ensure_ascii=False, indent=2)


class StrictTransport:
    def __init__(self, request, credentials, writer, root, stage):
        self.request, self.writer, self.root = request, writer, root
        self.current = request['expectedKnowledgeRevision']
        self.writes = self.counter = 0
        self.readbacks = {}
        self.postcommit_before = None
        self.lock = threading.RLock()
        self.allowed = {}
        for table, filename in writer.TABLE_FILES.items():
            before_rows = writer.load_jsonl(Path(request['knowledgeDirectory']) / filename)
            after_rows = writer.load_jsonl(stage / filename)
            before = {row['id']: row for row in before_rows}
            after = {row['id']: row for row in after_rows}
            if (len(before) != len(before_rows) or len(after) != len(after_rows)
                    or not before.keys() <= after.keys()
                    or any(writer.value_sha256(row) != writer.value_sha256(after[key])
                           for key, row in before.items())):
                raise ValueError('Reviewed stage is not insert-only')
            added = {key: writer.envelope(after[key]) for key in after.keys() - before.keys()}
            if added:
                self.allowed[table] = added
        if (set(self.allowed) != {'maintainer_skills', 'program_facts', 'maintainer_skill_refresh_rounds'}
                or any(len(rows) != 1 for rows in self.allowed.values())):
            raise ValueError('Reviewed lesson delta differs')
        private = {}
        for line in read(credentials).decode().splitlines():
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                private[key.strip()] = value.strip().strip('\"\'')
        self.auth = {key: private[name] for key, name in
                     [('basic_username', 'MCPGIT_BASIC_USERNAME'), ('basic_verify', 'MCPGIT_BASIC_VERIFY')]}
        save(root, 'service.json', self.rpc('service_metadata', {}))
        save(root, 'skills.json', self.rpc('skill_list', {}))
        self.versions = {}
        for skill, operations in [('table.author', ['worktree_table_batch_transaction']),
                                  ('table.query', ['table_status', 'table_query'])]:
            contract = self.rpc('skill_get', {'skill_id': skill})
            if contract['outcome'] != 'loaded':
                raise ValueError('Live contract absent')
            summary = contract['skill']['summary']
            if not all(operation in summary['operation_names'] for operation in operations):
                raise ValueError('Live operation absent')
            self.versions[skill] = summary['skill_version']
            save(root, skill + '-contract.json', contract)
        status = self.rpc('person_status', self.auth)
        name = request.get('personShowname') or private['MCPGIT_DEFAULT_PERSON_SHOWNAME']
        person = next(p for p in status['selectable_persons'] if p['showname'] == name)
        selected = self.rpc('person_select', {**self.auth, 'person_id': person['person_id'],
                                             'person_showname': name})
        if selected['outcome'] != 'person_context_validated':
            raise ValueError('Acting Person rejected')
        self.person = person['person_id']
        save(root, 'acting-person.json', {'person_id': self.person, 'showname': name})

    def rpc(self, name, arguments):
        self.counter += 1
        body = {'jsonrpc': '2.0', 'id': self.counter, 'method': 'tools/call',
                'params': {'name': name, 'arguments': arguments}}
        request = urllib.request.Request(self.request['endpoint'], json.dumps(body).encode(),
            headers={'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                     'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': 'tools/call', 'Mcp-Name': name})
        with urllib.request.urlopen(request, timeout=30) as response:
            packet = json.load(response)
        if packet.get('error') or packet.get('result', {}).get('isError'):
            raise RuntimeError('MCP rejected; no retry')
        result = packet['result']['structuredContent']
        if result.get('outcome') == 'error':
            raise RuntimeError('Business rejected; no retry')
        return result

    def one(self, runner, skill, operation, arguments):
        result = self.rpc(runner, {**self.auth, 'caller_person_id': self.person,
            'skill_id': skill, 'skill_version': self.versions[skill], 'operation': operation,
            'arguments': arguments})
        if result['outcome'] != 'executed':
            raise RuntimeError('Business execution rejected')
        return result['result']

    def call(self, runner, skill, operation, arguments, allow_error=False):
        # Own one complete paged query and its capture names at a time.
        with self.lock:
            return self.call_locked(runner, skill, operation, arguments)

    def call_locked(self, runner, skill, operation, arguments):
        if arguments.get('repo') != self.request['knowledgeRepository']:
            raise ValueError('Repository differs')
        if runner == 'skill_run_write':
            if (skill != 'table.author' or operation != 'worktree_table_batch_transaction'
                    or self.writes != 0 or arguments['expected_revision'] != self.current
                    or arguments['topic_id'] != 'main'):
                raise ValueError('Single-write fence rejected')
            actual = {}
            for group in arguments['tables']:
                if group['path'] in actual:
                    raise ValueError('Duplicate transaction table')
                rows = actual[group['path']] = {}
                for change in group['operations']:
                    if change['op'] != 'insert' or change['key'] in rows:
                        raise ValueError('Noninsert or duplicate operation')
                    rows[change['key']] = change['row']
            if actual != self.allowed:
                raise ValueError('Transaction differs from reconstructed lesson')
            if hasattr(self, 'prewrite'):
                self.prewrite()
            save(self.root, 'transaction-intent.json', arguments)
            self.writes = 1  # Before dispatch: uncertain outcome cannot reopen.
            result = self.one(runner, skill, operation, arguments)
            save(self.root, 'transaction-receipt.json', result)
            if (result['previous_revision'] != self.current or result['outcome'] != 'applied'
                    or result.get('conflicts') or result['revision'] == self.current
                    or not re.fullmatch('[0-9a-f]{40}', result['revision'])):
                raise RuntimeError('Commit receipt rejected; reconcile original intent')
            self.current = result['revision']
            return result
        if runner != 'skill_run_read' or skill != 'table.query':
            raise ValueError('Unsupported transport operation')
        if operation == 'table_status':
            result = self.one(runner, skill, operation, arguments)
            save(self.root, f'status-{self.counter}.json', result)
            if result['dirty'] or result['revision'] != self.current:
                raise ValueError('Authority drift')
            return result
        if operation != 'table_query' or arguments['view']['revision'] != self.current:
            raise ValueError('Read revision differs')
        if self.writes == 1 and self.postcommit_before is None:
            self.postcommit_before = self.call_locked('skill_run_read', 'table.query', 'table_status',
                {'repo': self.request['knowledgeRepository'], 'path': 'maintainer_skill_refresh_rounds'})
        rows, total, first = [], None, None
        for offset in range(0, 1050, 50):
            page = self.one(runner, skill, operation, {**arguments, 'limit': 50, 'offset': offset})
            save(self.root, f'query-{self.counter}.json', page)
            if (page['revision'] != self.current or page['dirty'] or page['offset'] != offset
                    or page['returned_count'] != len(page['rows'])
                    or page['matched_count'] != page['row_count']):
                raise ValueError('Incomplete page identity')
            if total is None:
                total, first = page['row_count'], page
            if total > 1000 or page['row_count'] != total:
                raise ValueError('Readback budget or count drift')
            rows.extend(page['rows'])
            if len(rows) == total:
                if page['truncated']:
                    raise ValueError('Terminal page truncated')
                break
            if len(rows) > total or len(page['rows']) != 50 or not page['truncated']:
                raise ValueError('Incomplete page coverage')
        if len(rows) != total or len({row['key'] for row in rows}) != total:
            raise ValueError('Incomplete or duplicate readback')
        joined = {**first, 'rows': rows, 'offset': 0, 'limit': total, 'returned_count': total,
                  'truncated': False, 'pagedReadback': True}
        save(self.root, f'complete-{self.counter}.json', joined)
        self.readbacks[(self.current, arguments['path'])] = joined
        return joined


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--credentials', type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(read(args.request))
    if (request['schema'] != 'agentlab.reviewed_knowledge_store_request.v1'
            or request['reviewed'] is not True or request['automaticPromotion'] is not False
            or not re.fullmatch('[0-9a-f]{40}', request['expectedKnowledgeRevision'])):
        raise ValueError('Reviewed request identity')
    from urllib.parse import urlsplit
    endpoint = urlsplit(request['endpoint'])
    if endpoint.scheme not in ('http', 'https') or not endpoint.hostname or endpoint.username or endpoint.password:
        raise ValueError('Endpoint identity')
    root, base = Path(request['outputDirectory']), Path(request['knowledgeDirectory'])
    for key in ['knowledgeDirectory', 'proposalDirectory', 'lessonSourceDirectory']:
        directory = Path(request[key])
        if (not directory.is_absolute() or not directory.is_dir()
                or any(part.is_symlink() for part in (directory, *directory.parents))):
            raise ValueError('Input directory identity')
    if not root.is_absolute() or root.exists() or root.is_symlink():
        raise ValueError('Fresh absolute output required')
    if any(parent.is_symlink() for parent in root.parents):
        raise ValueError('Output ancestor symlink')
    tool = Path(request['flywheelTool'])
    if hashlib.sha256(read(tool, 256 * 1024 * 1024)).hexdigest() != request['flywheelToolSha256']:
        raise ValueError('Native tool drift')
    cut = json.loads(read(base / 'maintainer-knowledge-cut.json'))
    if (cut['tableGitAuthority']['repo'] != request['knowledgeRepository']
            or cut['tableGitAuthority']['revision'] != request['expectedKnowledgeRevision']):
        raise ValueError('Baseline authority differs')
    root.mkdir()
    save(root, 'request.json', request)
    source_reference = request['lessonSourceReadback']
    source_bytes = read(Path(source_reference['path']))
    if hashlib.sha256(source_bytes).hexdigest() != source_reference['sha256']:
        raise ValueError('Operational source capture drift')
    snapshot = json.loads(source_bytes)
    if snapshot['schema'] != 'agentlab.observation_store_snapshot.v1':
        raise ValueError('Operational source snapshot schema')
    source_export = json.loads(read(Path(request['lessonSourceDirectory']) / 'export.json'))
    source_readback = {key: snapshot[key] for key in ['repository', 'revision', 'tablePrefix']}
    source_readback.update(schema='agentlab.reviewed_lesson_source_readback.v1',
                          tables={name: snapshot['tables'][name] for name in source_export['tables']})
    (root / 'original-source-snapshot.json').write_bytes(source_bytes)
    save(root, 'lesson-source-readback.json', source_readback)
    method_args = []
    if request.get('methodSource') is not None:
        reference = request['methodSource']
        method_bytes = read(Path(reference['path']), 1024 * 1024)
        if hashlib.sha256(method_bytes).hexdigest() != reference['sha256']:
            raise ValueError('Historical method drift')
        method_path = root / 'reviewed-method-source.md'
        method_path.write_bytes(method_bytes)
        method_args = ['--method-source', str(method_path)]
    guidance_args = []
    if request.get('nextGuidanceIntent') is not None:
        reference = request['nextGuidanceIntent']
        guidance_bytes = read(Path(reference['path']), 1024 * 1024)
        if hashlib.sha256(guidance_bytes).hexdigest() != reference['sha256']:
            raise ValueError('Reviewed guidance intent drift')
        guidance_path = root / 'reviewed-next-guidance-intent.json'
        guidance_path.write_bytes(guidance_bytes)
        guidance_args = ['--next-guidance-intent', str(guidance_path)]
    stage = root / 'staged-admission'
    common = ['--knowledge', str(base),
               '--proposal', request['proposalDirectory'], '--lesson-source', request['lessonSourceDirectory'],
               '--lesson-id', request['lessonId'], '--expected-knowledge-revision',
               request['expectedKnowledgeRevision'], *method_args, *guidance_args]
    command = [str(tool), '--verify-lesson-source-readback', *common,
               '--readback', str(root / 'lesson-source-readback.json'), '--output', str(stage)]
    result = subprocess.run(command, capture_output=True, timeout=60)
    (root / 'native-stage.stdout').write_bytes(result.stdout)
    (root / 'native-stage.stderr').write_bytes(result.stderr)
    if result.returncode:
        raise ValueError('Native lesson reconstruction rejected')
    writer_path = Path(__file__).resolve().with_name('maintainer-skill-tablegit.py')
    writer_bytes = read(writer_path)
    if hashlib.sha256(writer_bytes).hexdigest() != request['tablegitWriterSha256']:
        raise ValueError('TableGit writer dependency drift')
    spec = importlib.util.spec_from_file_location('tablegit_writer', writer_path)
    writer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(writer)
    client = StrictTransport(request, args.credentials, writer, root, stage)
    directories = [base, stage, Path(request['proposalDirectory']), Path(request['lessonSourceDirectory'])]
    retained = {file: read(file) for directory in directories for file in directory.rglob('*') if file.is_file()}
    retained[root / 'lesson-source-readback.json'] = read(root / 'lesson-source-readback.json')
    if method_args:
        retained[method_path] = method_bytes
    if guidance_args:
        retained[guidance_path] = guidance_bytes
    def prewrite():
        if (hashlib.sha256(read(tool, 256 * 1024 * 1024)).hexdigest() != request['flywheelToolSha256']
                or read(writer_path) != writer_bytes
                or any(read(file) != data for file, data in retained.items())):
            raise ValueError('Native tool or staged input drift')
    client.prewrite = prewrite
    writer.Inspector = lambda endpoint, person: client
    writer.command_sync(argparse.Namespace(base=base, snapshot=stage, export=root / 'committed-knowledge',
        receipt=root / 'sync-receipt.json', assessment=None, endpoint=request['endpoint'], person_id=client.person,
        repo=request['knowledgeRepository'], anchor_table='maintainer_skill_refresh_rounds', replicate=False,
        remote='origin', run_id=request['runId'], github_repository=request['githubRepository'],
        producer_kind='coordinator-native-admission', producer_url=request.get('producerUrl'), producer_host=None))
    if client.writes != 1:
        raise ValueError('Expected one reviewed lesson commit')
    final = client.call('skill_run_read', 'table.query', 'table_status',
                       {'repo': request['knowledgeRepository'], 'path': 'maintainer_skill_refresh_rounds'})
    save(root, 'final-status.json', final)
    readback = {'schema': 'agentlab.reviewed_lesson_committed_readback.v1',
        'knowledgeRepository': request['knowledgeRepository'],
        'previousRevision': request['expectedKnowledgeRevision'], 'revision': client.current,
        'before': client.postcommit_before, 'after': final,
        'tables': {name: client.readbacks[(client.current, name)] for name in writer.TABLE_FILES},
        'lessonSource': source_readback}
    save(root, 'committed-readback.json', readback)
    prewrite()  # No write: original reviewed inputs must still be byte-exact.
    result = subprocess.run([str(tool), '--verify-committed-lesson-return', *common,
        '--committed-knowledge', str(root / 'committed-knowledge'),
        '--readback', str(root / 'committed-readback.json'),
        '--output', str(root / 'return-reconstruction')], capture_output=True, timeout=60)
    (root / 'native-return.stdout').write_bytes(result.stdout)
    (root / 'native-return.stderr').write_bytes(result.stderr)
    if result.returncode:
        raise ValueError('Committed native return rejected; recover read-only, do not replay writer')
    outcome = {'revision': client.current, 'authorityWrites': client.writes,
         'committedExportExact': True, 'committedReadbackVerified': True,
         'sourceReadbackVerified': True, 'remoteCaptureAuthenticated': False,
         'nextGuidanceBound': bool(guidance_args), 'automaticFiveStageLoopCompleted': False}
    if guidance_args:
        for key, filename in [('nextGuidanceSelection', 'guidance-selection.json'),
                              ('nextGuidancePacket', 'guidance-packet.json')]:
            path = root / 'return-reconstruction' / filename
            outcome[key] = {'path': str(path), 'sha256': hashlib.sha256(read(path)).hexdigest()}
    save(root, 'result.json', outcome)
    print(json.dumps({'revision': client.current, 'authorityWrites': client.writes}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Reviewed admission stopped: ' + type(error).__name__ +
              '; retain original intent and receipts; no rerun.', flush=True)
        raise SystemExit(1)
