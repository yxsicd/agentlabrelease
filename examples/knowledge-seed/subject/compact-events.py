"""Losslessly compact or restore participant JSONL streams with exact digests."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def compact(root):
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
        rows.append(dict(
            path=str(source.relative_to(root)), rawBytes=raw_bytes, rawLines=raw_lines,
            rawSha256=raw_sha.hexdigest(), compressedPath=str(target.relative_to(root)),
            compressedBytes=target.stat().st_size, compressedSha256=sha256_file(target),
            codec='zstd-6', lossless=True))
        source.unlink()
    (root/'event-streams-manifest.json').write_text(json.dumps(dict(
        schema='agentlab.event_stream_compaction.v1', streams=rows,
        rawBytes=sum(x['rawBytes'] for x in rows), compressedBytes=sum(x['compressedBytes'] for x in rows),
        reconstructable=True), indent=2) + '\n')


def restore(root):
    manifest_path = root/'event-streams-manifest.json'
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text())
    assert manifest['schema'] == 'agentlab.event_stream_compaction.v1' and manifest['reconstructable'] is True
    for row in manifest['streams']:
        compressed = root/row['compressedPath']
        target = root/row['path']
        assert compressed.is_file()
        assert compressed.stat().st_size == row['compressedBytes']
        assert sha256_file(compressed) == row['compressedSha256']
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['zstd', '-q', '-d', '-f', str(compressed), '-o', str(target)], check=True)
        assert target.stat().st_size == row['rawBytes']
        assert sha256_file(target) == row['rawSha256']
        with target.open('rb') as handle:
            assert sum(1 for _ in handle) == row['rawLines']


parser = argparse.ArgumentParser()
parser.add_argument('root', type=Path)
parser.add_argument('--restore', action='store_true')
args = parser.parse_args()
root = args.root.resolve()
restore(root) if args.restore else compact(root)
