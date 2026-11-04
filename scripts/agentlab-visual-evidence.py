#!/usr/bin/env python3
"""Derived visual previews. Never edits originals or grants evidence acceptance."""
import argparse, hashlib, io, json, os, platform, sys, tempfile
from pathlib import Path

SCHEMA = 'agentlab.visual_evidence_sequence.v1'
MAX_FRAMES = 64
MAX_INPUT_BYTES = 128 * 1024 * 1024

def check(ok, message):
    if not ok:
        raise ValueError(message)

def digest(b):
    return hashlib.sha256(b).hexdigest()

def relative(root, name):
    p = Path(name)
    check(not p.is_absolute() and '..' not in p.parts, 'path must stay inside artifact root')
    out = (root / p).resolve()
    check(out.is_relative_to(root.resolve()), 'path escapes artifact root')
    return out

def pillow():
    import PIL
    from PIL import Image, features
    check(features.check('avif'), 'tools pack lacks AVIF codec; run tools self-check')
    Image.MAX_IMAGE_PIXELS = 20_000_000
    return PIL, Image, features

def encode(manifest_path, output, width=256, quality=35, speed=6):
    PIL, Image, features = pillow()
    check(64 <= width <= 1024 and 1 <= quality <= 100 and 0 <= speed <= 10, 'invalid encoding policy')
    check(not output.exists(), 'output already exists; do not overwrite or replay')
    spec = json.loads(manifest_path.read_text())
    rows = spec.get('frames', [])
    check(1 <= len(rows) <= MAX_FRAMES, 'expected 1..64 frames; split longer evidence into batches')
    check(len({r['stepId'] for r in rows}) == len(rows), 'duplicate stepId')
    frames, refs, total = [], [], 0
    for row in rows:
        check(all(isinstance(row.get(k), str) and row[k] for k in ['stepId', 'caseId', 'operationId', 'observationRef', 'path', 'sha256']), 'missing source identity')
        src = relative(manifest_path.parent, row['path'])
        check(src.is_file() and src.stat().st_size <= MAX_INPUT_BYTES, 'source missing or too large')
        raw = src.read_bytes(); total += len(raw)
        check(total <= MAX_INPUT_BYTES, 'input byte budget exceeded')
        check(digest(raw) == row['sha256'], 'source SHA mismatch: ' + row['stepId'])
        with Image.open(io.BytesIO(raw)) as image:
            check(image.width * image.height <= 20_000_000, 'source pixel budget exceeded')
            check(not getattr(image, 'is_animated', False), 'input must be a single screenshot')
            target = (width, round(image.height * width / image.width))
            check(target[1] <= 4096, 'thumbnail too tall')
            image = image.convert('RGB').resize(target, Image.Resampling.LANCZOS)
            check(not frames or image.size == frames[0].size, 'mixed aspect ratios require separate sequences')
            frames.append(image)
        refs.append({k: row[k] for k in ['stepId', 'caseId', 'operationId', 'observationRef', 'path', 'sha256']})
        if 'capturedAt' in row:
            refs[-1]['capturedAt'] = row['capturedAt']
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.visual-stage-', dir=output.parent) as tmp:
        tmp = Path(tmp); media = tmp / 'sequence.avif'
        frames[0].save(media, 'AVIF', save_all=True, append_images=frames[1:], duration=1000,
                       quality=quality, speed=speed, codec='aom', max_threads=4, subsampling='4:4:4')
        decoded_hashes = []
        with Image.open(media) as decoded:
            check(decoded.n_frames == len(frames), 'encoder changed evidence frame count')
            for i in range(len(frames)):
                decoded.seek(i); decoded_hashes.append(digest(decoded.convert('RGB').tobytes()))
        for i, ref in enumerate(refs):
            ref.update(frameIndex=i, decodedRGBSHA256=decoded_hashes[i])
        index = {'schema': SCHEMA, 'derivedPreviewOnly': True, 'originalsDeleted': False,
                 'acceptanceOverride': False, 'media': {'path': 'sequence.avif', 'sha256': digest(media.read_bytes()), 'bytes': media.stat().st_size},
                 'frameSize': list(frames[0].size), 'frameDurationMs': 1000,
                 'timingMeaning': 'navigation interval only; NOT measured execution timing',
                 'policy': {'width': width, 'quality': quality, 'speed': speed, 'subsampling': '4:4:4', 'sharpen': False, 'maxThreads': 4, 'codec': 'aom'},
                 'versions': {'python': platform.python_version(), 'pillow': PIL.__version__, 'libavif': features.version('avif')},
                 'inputManifestSHA256': digest(manifest_path.read_bytes()), 'sourceBytes': total, 'frames': refs}
        (tmp / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n')
        verify(tmp / 'index.json')
        check(not output.exists(), 'output appeared during encoding')
        os.rename(tmp, output)
    return index

def verify(index_path):
    _, Image, _ = pillow()
    index = json.loads(index_path.read_text()); rows = index['frames']
    check(index['schema'] == SCHEMA and index['derivedPreviewOnly'] is True and index['acceptanceOverride'] is False, 'not a preview index')
    check(1 <= len(rows) <= MAX_FRAMES and len({r['stepId'] for r in rows}) == len(rows), 'invalid frame map')
    check([r['frameIndex'] for r in rows] == list(range(len(rows))), 'non-consecutive frame indices')
    media = relative(index_path.parent, index['media']['path']); raw = media.read_bytes()
    check(len(raw) == index['media']['bytes'] and digest(raw) == index['media']['sha256'], 'media integrity mismatch')
    with Image.open(io.BytesIO(raw)) as im:
        check(im.n_frames == len(rows) and list(im.size) == index['frameSize'], 'frame dimensions/count mismatch')
        for i in list(reversed(range(len(rows)))) + list(range(len(rows))):
            im.seek(i)
            check(digest(im.convert('RGB').tobytes()) == rows[i]['decodedRGBSHA256'], 'decoded frame identity mismatch')
    return {'verified': True, 'frames': len(rows), 'mediaBytes': len(raw), 'originalAcceptanceChanged': False}

def self_check():
    PIL, Image, _ = pillow()
    with tempfile.TemporaryDirectory(prefix='agentlab-visual-selfcheck-') as tmp:
        r = Path(tmp); rows = []
        for i in range(3):
            p = r / f'{i}.png'; im = Image.new('RGB', (96, 96), 'white')
            from PIL import ImageDraw
            ImageDraw.Draw(im).text((8, 12 + i * 20), str(i), fill='black'); im.save(p)
            rows.append({'stepId': str(i), 'caseId': 'self-check', 'operationId': 'private-fixture', 'observationRef': 'private-fixture', 'path': p.name, 'sha256': digest(p.read_bytes())})
        (r/'input.json').write_text(json.dumps({'frames': rows})); encode(r/'input.json', r/'out', width=96)
        result = verify(r/'out/index.json'); result['pillow'] = PIL.__version__; return result

def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='command', required=True)
    e = sub.add_parser('encode'); e.add_argument('--manifest', type=Path, required=True); e.add_argument('--output', type=Path, required=True)
    e.add_argument('--width', type=int, default=256); e.add_argument('--quality', type=int, default=35); e.add_argument('--speed', type=int, default=6)
    v = sub.add_parser('verify'); v.add_argument('--index', type=Path, required=True); sub.add_parser('self-check')
    a = p.parse_args()
    if a.command == 'encode':
        x = encode(a.manifest, a.output, a.width, a.quality, a.speed); result = {'frames': len(x['frames']), 'mediaBytes': x['media']['bytes'], 'index': str(a.output/'index.json')}
    elif a.command == 'verify': result = verify(a.index)
    else: result = self_check()
    print(json.dumps(result))

if __name__ == '__main__':
    try: main()
    except (ValueError, KeyError, OSError, ImportError) as e:
        print('visual evidence error: ' + str(e), file=sys.stderr); sys.exit(1)
