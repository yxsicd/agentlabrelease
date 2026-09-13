"""Observe projected source changes without mutating the participant's Git index."""
def capture_patch(git,baseline):
    patch=git(['diff','--binary',baseline])
    names=git(['ls-files','--others','--exclude-standard','-z']).split(b'\0')
    for raw in names:
        if raw:
            patch += git(['diff','--no-index','--binary','--src-prefix=a/','--dst-prefix=b/',
                          '/dev/null',raw.decode('utf-8')],allow_diff=True)
    return patch
