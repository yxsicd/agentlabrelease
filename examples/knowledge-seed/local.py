#!/usr/bin/env python3
"""Real local TableGit development experiment, independent of formal AL Session gates."""
import argparse
import importlib.util
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid
from store import persist,verify,analyze,roundtrip

sys.path.insert(0,str(Path(__file__).parents[1]/'tablegit-session'))
from capture import Service
from fixture import init_volume,write_agent_config
spec=importlib.util.spec_from_file_location('builder',Path(__file__).with_name('run.py'))
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

def main():
    p=argparse.ArgumentParser();p.add_argument('--image',required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--keep',action='store_true');a=p.parse_args()
    import websocket  # Runtime dependency preflight before creating infrastructure.
    root=a.root.absolute();root.mkdir(parents=True,exist_ok=False);state=root/'private';state.mkdir(mode=0o700);evidence=root/'evidence';evidence.mkdir()
    package=builder.build(root/'builder');prefix='al-knowledge-'+uuid.uuid4().hex[:10]
    containers=[];network=prefix;volume=prefix+'-data';created_volume=False;made_network=False
    def docker(*args):return subprocess.check_output(['docker',*args],stderr=subprocess.PIPE,text=True).strip()
    def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
    caller,agent=secrets.token_hex(32),secrets.token_hex(32)
    save(state/'gateway.json',dict(gateway_id='public-demo',bind='0.0.0.0:8002',allowed_organizations=['org:demo'],default_organization_id='org:demo',lease_ttl_ms=30000,heartbeat_interval_ms=5000,max_frame_payload_bytes=262144,max_concurrent_streams=64,required_capabilities={},required_organization_capabilities={'org:demo':{'workspace':'v1'}}))
    save(state/'credentials.json',dict(agents=[dict(agent_id='demo',bearer_token=agent)],callers=[dict(bearer_token=caller,organizations=['org:demo'],provider_id='public-demo',subject_fingerprint='hmac-sha256:'+'a'*64,person_id='11111111-1111-4111-8111-111111111111',actor_id=None)]))
    (state/'caller.authorization').write_text('Bearer '+caller+'\n');(state/'agent.authorization').write_text('Bearer '+agent+'\n')
    for f in state.iterdir():f.chmod(0o600)
    write_agent_config(state/'mcpgit.toml')
    summary=dict(scope='real-local-tablegit-development; not formal Session qualification',ok=False,image=a.image)
    try:
        summary['imageId']=docker('image','inspect',a.image,'--format','{{.Id}}')
        docker('network','create',network);made_network=True;docker('volume','create',volume);created_volume=True
        init_volume(a.image,volume)
        docker('run','-d','--name',prefix+'-gw','--network',network,'--network-alias','gateway','-p','127.0.0.1::8002','--mount',f'type=bind,src={state},dst=/demo,readonly','--entrypoint','/opt/mcpgit/program/bin/mcpgitgw',a.image,'--config','/demo/gateway.json','--credentials','/demo/credentials.json');containers.append(prefix+'-gw')
        docker('run','-d','--name',prefix+'-agent','--network',network,'--mount',f'type=bind,src={state},dst=/demo,readonly','--mount',f'type=volume,src={volume},dst=/data','--env','MCPGIT_AGENT_GATEWAY_URL=ws://gateway:8002','--env','MCPGIT_AGENT_ID=demo','--env','MCPGIT_AGENT_ORG_ID=org:demo','--env','MCPGIT_MANAGED_REPOSITORY_ROOT=/data/managed','--env','MCPGIT_DATA_FORMAT=agentlab-e2e-v1','--entrypoint','/bin/sh',a.image,'-lc','export MCPGIT_AGENT_AUTHORIZATION="$(cat /demo/agent.authorization)"; exec /opt/mcpgit/program/bin/mcpgit --config /demo/mcpgit.toml --transport streamable-http --bind 0.0.0.0:8001');containers.append(prefix+'-agent')
        service=Service('',(state/'caller.authorization').read_text().strip(),evidence)
        def wait_route():
            port=docker('inspect','--format','{{(index (index .NetworkSettings.Ports "8002/tcp") 0).HostPort}}',prefix+'-gw')
            service.url='ws://127.0.0.1:'+port+'/__mcpgit/service-ws'
            deadline=time.monotonic()+45
            while True:
                try:service.call('repository.list',{});return service.url
                except Exception:
                    if time.monotonic()>=deadline:raise
                    time.sleep(.25)
        url=wait_route()
        cuts=persist(service,'session',{'topic_id':None},package)
        save(evidence/'knowledge-cuts.json',cuts)
        docker('restart',prefix+'-agent');docker('restart',prefix+'-gw')
        url=wait_route()
        summary['history']=verify(service,'session',package,cuts)
        revision,result=analyze(service,'session',{'topic_id':None},cuts['updatedRevision']);save(evidence/'analysis.json',result)
        final,proof=roundtrip(service,'session',{'topic_id':None},revision,evidence/'export');summary.update(ok=True,roundtrip=proof,finalRevision=final)
        save(state/'development.json',dict(url=url,repo='session',revision=final,authorizationFile=str(state/'caller.authorization'),imageId=summary['imageId'],volume=volume))
    except Exception as error:summary['error']=str(error);raise
    finally:
        save(evidence/'summary.json',summary)
        for name in containers:
            logs=subprocess.run(['docker','logs',name],capture_output=True);(evidence/(name+'.stdout')).write_bytes(logs.stdout);(evidence/(name+'.stderr')).write_bytes(logs.stderr)
        if not a.keep:
            for name in reversed(containers):docker('rm','-f',name)
            if made_network:docker('network','rm',network)
            if created_volume:docker('volume','rm',volume)
        print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
