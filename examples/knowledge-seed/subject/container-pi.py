#!/usr/bin/env python3
"""Contained participant filesystem; supervisor capture stays outside its mounts."""
import json,os,subprocess,sys
from pathlib import Path
config=json.loads(Path(__file__).with_name('container-launch.json').read_text())
args=sys.argv[1:];i=args.index('--session');args[i+1]='/agent/session/session.jsonl'
command=['docker','run','--rm','--network=host','--workdir','/workspace',
 '--mount',f'type=bind,src={Path.cwd()},dst=/workspace',
 '--mount',f'type=bind,src={config["runtime"]},dst=/runtime,readonly',
 '--mount',f'type=bind,src={os.environ["PI_CODING_AGENT_DIR"]}/models.json,dst=/agent/models.json,readonly',
 '--mount',f'type=bind,src={config["session"]},dst=/agent/session',
 '--env','PI_CODING_AGENT_DIR=/agent','--env','HOME=/agent',
 '--entrypoint','node',config['image'],'/runtime/node_modules/@mariozechner/pi-coding-agent/dist/cli.js',*args]
sys.exit(subprocess.call(command))
