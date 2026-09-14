"""Losslessly compact raw participant JSONL streams after all live analysis is complete."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
rows = []
for source in sorted(root.glob('**/*-events.jsonl')):
    raw_sha = hashlib.sha256()
    raw_bytes = raw_lines = 0
    with source.open('rb') as handle:
        for line in handle:
            raw_sha.update(line)
            raw_bytes += len(line)
            raw_lines += 1
    target = Path(str(source) + '.zst')
    subprocess.run(['zstd', '-q', '-T0', '-6', '-f', str(source), '-o', str(target)], check=True)
    subprocess.run(['zstd', '-q', '-t', str(target)], check=True)
    compressed = target.read_bytes()
    rows.append(dict(
        path=str(source.relative_to(root)), rawBytes=raw_bytes, rawLines=raw_lines,
        rawSha256=raw_sha.hexdigest(), compressedPath=str(target.relative_to(root)),
        compressedBytes=len(compressed), compressedSha256=hashlib.sha256(compressed).hexdigest(),
        codec='zstd-6', lossless=True))
    source.unlink()

(root/'event-streams-manifest.json').write_text(json.dumps(dict(
    schema='agentlab.event_stream_compaction.v1', streams=rows,
    rawBytes=sum(x['rawBytes'] for x in rows), compressedBytes=sum(x['compressedBytes'] for x in rows),
    reconstructable=True), indent=2) + '\n')
