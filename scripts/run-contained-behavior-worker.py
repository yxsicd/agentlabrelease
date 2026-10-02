#!/usr/bin/env python3
"""Operator-owned network-disabled Docker executor for a pinned worker adapter."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read_regular(path, maximum_bytes=4*1024*1024):
    path = Path(path)
    require(path.is_absolute(), 'worker dependency path must be absolute')
    require(all(not part.is_symlink() for part in (path, *path.parents)), 'worker dependency symlink')
    require(path.is_file() and path.stat().st_size <= maximum_bytes, 'worker dependency budget or type invalid')
    return path, path.read_bytes()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    started=time.monotonic()
    launcher_sha256=sha(Path(__file__).read_bytes())
    descriptor_path, descriptor_bytes = read_regular(sys.argv[1])
    request_path, request_bytes = read_regular(sys.argv[2])
    descriptor = json.loads(descriptor_bytes)
    request = json.loads(request_bytes)
    require(descriptor.get('schema') == 'agentlab.contained_behavior_executor.v1' and
            descriptor.get('reviewed') is True and descriptor.get('automaticPromotion') is False,
            'worker descriptor not reviewed')
    require(request.get('schema') == 'agentlab.behavior_executor_request.v1', 'worker request schema differs')
    require(sha(request['submittedSource'].encode()) == request['submittedSourceSha256'], 'worker submitted source differs')
    image = descriptor['imageId']
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', image), 'worker image must be an exact local ID')
    inspected = subprocess.run(['docker','image','inspect',image],capture_output=True,check=True,timeout=10)
    rows = json.loads(inspected.stdout)
    require(len(rows)==1 and rows[0]['Id']==image, 'worker image differs')
    names = {entry.split('=',1)[0] for entry in (rows[0].get('Config',{}).get('Env') or [])}
    require(not any(re.search(r'(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)',name,re.I) for name in names),
            'worker image contains credential-like environment names')
    dependencies = {}
    for role in ('worker','compiler','support'):
        path, raw = read_regular(descriptor[role+'Path'],16*1024*1024 if role=='compiler' else 4*1024*1024)
        require(sha(raw)==descriptor[role+'Sha256'], 'worker dependency digest differs')
        dependencies[role]=(path,raw)
    timeout = descriptor['timeoutMs']
    require(type(timeout) is int and 0 < timeout <= 60000, 'worker deadline invalid')
    support = json.loads(dependencies['support'][1])
    require(support['compilerSha256']==descriptor['compilerSha256'], 'worker compiler binding differs')
    # Only this staging directory is mounted: no parent capture or operator state.
    stage = Path(tempfile.mkdtemp(prefix='contained-input-',dir=Path.cwd()))
    stage.chmod(0o755)
    (stage/'request.json').write_bytes(request_bytes)
    (stage/'support.json').write_bytes(dependencies['support'][1])
    for path in stage.iterdir(): path.chmod(0o444)
    name = 'agentlab-behavior-'+uuid.uuid4().hex
    command = ['docker','run','--rm','--name',name,'--network','none','--read-only',
               '--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','64',
               '--memory','256m','--cpus','1','--user',f'{os.getuid()}:{os.getgid()}',
               '--tmpfs','/tmp:rw,nosuid,nodev,size=16m',
               '--mount',f'type=bind,source={stage},target=/input,readonly',
               '--mount',f'type=bind,source={dependencies["worker"][0]},target=/worker.cjs,readonly',
               '--mount',f'type=bind,source={dependencies["compiler"][0]},target=/typescript.js,readonly',
               '--entrypoint','node',image,'/worker.cjs','/input/request.json','/input/support.json','/typescript.js']
    (stage/'operator-command.json').write_text(json.dumps(command,indent=2)+'\n')
    timed_out=False
    log_budget_exceeded=False
    stdout_path,stderr_path=stage/'worker-stdout.log',stage/'worker-stderr.log'
    try:
        with stdout_path.open('xb') as stdout_file,stderr_path.open('xb') as stderr_file:
            process=subprocess.Popen(command,stdout=stdout_file,stderr=stderr_file,stdin=subprocess.DEVNULL)
            while process.poll() is None:
                log_budget_exceeded=any(path.stat().st_size>1024*1024 for path in (stdout_path,stderr_path))
                # Descriptor budget includes preflight; reserve two seconds for
                # exact-container removal before the outer controller deadline.
                timed_out=time.monotonic()-started>=max(0.1,timeout/1000-2)
                if log_budget_exceeded or timed_out:
                    process.kill()
                    break
                time.sleep(0.02)
            code=process.wait(timeout=2)
    finally:
        try:
            cleanup=subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=2)
            cleanup_stdout,cleanup_stderr,cleanup_code=cleanup.stdout,cleanup.stderr,cleanup.returncode
        except subprocess.TimeoutExpired as error:
            cleanup_stdout,cleanup_stderr,cleanup_code=error.stdout or b'',error.stderr or b'',None
        (stage/'cleanup-stdout.log').write_bytes(cleanup_stdout)
        (stage/'cleanup-stderr.log').write_bytes(cleanup_stderr)
    def file_sha(path):
        value=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):value.update(chunk)
        return value.hexdigest()
    (stage/'process.json').write_text(json.dumps({'schema':'agentlab.contained_behavior_process.v1',
        'descriptorSha256':sha(descriptor_bytes),'requestSha256':sha(request_bytes),
        'launcherSha256':launcher_sha256,
        'imageId':image,'containerName':name,'exitCode':code,'timedOut':timed_out,
        'durationMs':max(1,round((time.monotonic()-started)*1000)),
        'stdoutSha256':file_sha(stdout_path),'stderrSha256':file_sha(stderr_path),'network':'none',
        'logBudgetExceeded':log_budget_exceeded,'cleanupExitCode':cleanup_code,
        'rootFilesystemReadOnly':True,'capabilitiesDropped':True,'qualified':False},indent=2)+'\n')
    require(not timed_out and not log_budget_exceeded and code==0, 'contained worker infrastructure failure; raw evidence retained')
    require(cleanup_code==0 or (cleanup_code==1 and b'No such container' in cleanup_stderr and name.encode() in cleanup_stderr),
            'owned-container cleanup unconfirmed; manual recovery required')
    require(all(path.stat().st_size<=1024*1024 for path in (stdout_path,stderr_path)), 'worker log budget exceeded')
    stdout=stdout_path.read_bytes()
    value=json.loads(stdout)
    require(value['submittedSource']==request['submittedSource'] and value['id']==request['id'], 'worker output identity differs')
    sys.stdout.buffer.write(stdout)


if __name__ == '__main__':
    main()
