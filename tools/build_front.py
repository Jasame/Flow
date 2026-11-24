#!/usr/bin/env python3
"""Join the front end's source parts into the two files the browser loads.

    python3 tools/build_front.py           # write flow/public/next.js and flow/public/next.css
    python3 tools/build_front.py --check   # exit 1 if either is out of date with its parts (tests and release builds run this)

flow/public/src/next/*.js   -> flow/public/next.js
flow/public/src/next/*.css  -> flow/public/next.css

Parts are joined in file-name order, byte for byte: no wrapper, no transform, no build tool. The script is still
one closure (00-head.js opens it, 99-boot.js closes it), so every part sees the others' names exactly as before;
the 2x parts are consecutive slices of study(). Edit the parts and run this; commit only the parts: git ignores
next.js and next.css, and a release builds them from the commit's parts (tools/build_release.py). One file per feature means
two people (or two sessions) working on different features no longer edit the same file.
"""
import subprocess, shutil, sys
from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[1] / 'flow' / 'public'
SRC = PUBLIC / 'src' / 'next'
OUT = {'.js': PUBLIC / 'next.js', '.css': PUBLIC / 'next.css'}


def joined(ext):
    parts = sorted(SRC.glob('*' + ext))
    if not parts:
        sys.exit(f'no {ext} parts in {SRC}')
    return b''.join(p.read_bytes() for p in parts), parts


def main():
    check = '--check' in sys.argv
    stale = []
    for ext, out in OUT.items():
        data, parts = joined(ext)
        if out.exists() and out.read_bytes() == data:
            continue
        if check:
            stale.append(out.name)
        else:
            out.write_bytes(data)
            print(f'{out.name}: {len(parts)} parts, {len(data)} bytes')
    if check and stale:
        sys.exit(f"{', '.join(stale)} out of date with flow/public/src/next: run python3 tools/build_front.py")
    if shutil.which('node') and not check:
        subprocess.run(['node', '--check', str(OUT['.js'])], check=True)


if __name__ == '__main__':
    main()
