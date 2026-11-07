#!/usr/bin/env python3
"""Private, task-scoped Docker /tmp backing for explicitly resumed sessions.

This preserves /tmp on the same host; it is not a portable checkpoint or a lock.
The operator must independently establish exclusive session ownership.
"""
import argparse
import json
import os
import pathlib
import stat
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('init', 'mount'))
    p.add_argument('--root', required=True, help='fresh private session directory')
    p.add_argument('--session', required=True, help='exact opaque session identity')
    a = p.parse_args()
    if not a.session or len(a.session) > 512 or '\x00' in a.session:
        p.error('invalid session identity')
    root = pathlib.Path(a.root)
    if not root.is_absolute() or ',' in str(root):
        p.error('root must be an absolute path without commas')
    if a.action == 'init':
        root.mkdir(mode=0o700)  # never adopt an existing or uncertain directory
        os.chmod(root, 0o700)
        tmp = root / 'tmp'
        tmp.mkdir(mode=0o700)
        os.chmod(tmp, 0o1777)
        fd = os.open(root / 'identity.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump({'schema': 'agentlab.session_tmp.v1', 'session': a.session}, f)
            f.write('\n')
        print(json.dumps({'status': 'initialized', 'scope': 'same-host-only'}))
        return
    if root.is_symlink() or not root.is_dir() or stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise ValueError('invalid session root')
    identity = root / 'identity.json'
    tmp = root / 'tmp'
    if identity.is_symlink() or tmp.is_symlink() or not tmp.is_dir():
        raise ValueError('invalid session files')
    if stat.S_IMODE(identity.stat().st_mode) != 0o600 or stat.S_IMODE(tmp.stat().st_mode) != 0o1777:
        raise ValueError('invalid session permissions')
    if json.loads(identity.read_text()) != {'schema': 'agentlab.session_tmp.v1', 'session': a.session}:
        raise ValueError('session identity mismatch')
    # One argument suitable for Docker's --mount flag. No shell interpolation.
    print('type=bind,source=' + str(tmp) + ',target=/tmp')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print('session tmp: ' + str(exc), file=sys.stderr)
        sys.exit(1)
