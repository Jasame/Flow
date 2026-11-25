#!/usr/bin/env python3
"""Put the implicit AI-generation label (隐式标识, aigc_label.mp4) into word sprites made before it existed.

    python3 tools/label_word_audio.py <audio/words dir>            # count only: what would be labelled
    python3 tools/label_word_audio.py <audio/words dir> --write    # label them, each file replaced atomically

Each <accent>/<sprite>.m4a gets ProduceID flow-words-<accent>-<sprite>, the same as tools/gen_word_audio.py gives a new
one. The audio frames are not touched (a free box after moov gives up the bytes; the tests in flow/tests/test_word_clip.py
check that word_clip cuts the same clips). A file that already has the label is skipped; one this cannot read is left
as it is and named.

On a server this changes files the site serves (the 正式版 and the 内测版 each have their own audio/words) and that
learners' phones and the R2 copy (tools/push_media.py) keep in their caches: it is a server change, run by 语流 02 once
the owner has said yes, with the R2 copy pushed again after it. Run it as the site's user (www) so the files keep their
owner.
"""
import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'flow'))
import aigc_label  # noqa: E402


def main(argv):
    if not argv or argv[0].startswith('-'):
        sys.exit(__doc__)
    root, write = Path(argv[0]), '--write' in argv
    done = skipped = bad = 0
    for f in sorted(root.glob('*/*.m4a')):
        data = f.read_bytes()
        if aigc_label.read_mp4(data) is not None:
            skipped += 1
            continue
        out = aigc_label.mp4(data, f'flow-words-{f.parent.name}-{f.stem}')
        if out == data:
            bad += 1
            print('left as it is (boxes not read safely):', f)
            continue
        if write:
            tmp = f.with_suffix('.m4a.tmp')
            tmp.write_bytes(out)
            os.replace(tmp, f)
        done += 1
    print(f'{"labelled" if write else "to label"}: {done}, already labelled: {skipped}, left as they are: {bad}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
