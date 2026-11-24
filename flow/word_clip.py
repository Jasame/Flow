"""One word's pronunciation as a small file of its own, cut from a word sprite, with silence in front.

Why: a word sprite (/audio/words/<accent>/<sprite>.m4a) holds about 100 words; the page used to play a word by
jumping to its place and stopping at its end. On an iPhone, above all as an app on the home screen, play() first wakes
the system's audio, which takes a moment; the sprite's clock runs meanwhile, so the start of the word was lost (the
owner heard half a word, 2026-11-24). A file that starts with silence lets that moment pass in the silence: the page
plays it from its start, with no jump, and the whole word is heard.

How: the sprite is AAC in MP4 (moov first). Its sample tables give each AAC frame's place and time; the frames from a
little before the word to a little after it are copied out as ADTS (a 7-byte header per frame, which every browser
plays as audio/aac), after enough frames of silence taken from the gap between words to make LEAD seconds in all.
Words in a sprite are 0.2 s apart (tools/gen_word_audio.py), so the margins stay inside those gaps. Nothing is
decoded or re-encoded: the clip is the sprite's own frames, a few KB.
"""
import struct
from bisect import bisect_right
from functools import lru_cache

LEAD = 0.25  # seconds before the word starts: an iPhone waking its audio fits in this (try others with ?lead=)
LEADS = (0.05, 0.4)  # the range a request may ask for
PAD = 0.12   # seconds of the sprite's own gap kept before the word (the gap is 0.2 s), and after a sentence
MAX = 5.0    # a word clip is never longer than this (a sentence of a narration: SENTENCE)
SENTENCE = 40.0


def _boxes(buf, start, end):
    i = start
    while i + 8 <= end:
        size, kind = struct.unpack('>I4s', buf[i:i + 8])
        head = 8
        if size == 1:
            size, head = struct.unpack('>Q', buf[i + 8:i + 16])[0], 16
        elif size == 0:
            size = end - i
        if size < head or i + size > end:
            return
        yield kind, i + head, i + size
        i += size


def _child(buf, start, end, kind):
    return next(((a, b) for k, a, b in _boxes(buf, start, end) if k == kind), None)


def _path(buf, start, end, *kinds):
    span = (start, end)
    for k in kinds:
        span = _child(buf, span[0], span[1], k)
        if not span:
            return None
    return span


def _descriptor(buf, i):
    """(tag, payload start, payload end) of an MPEG-4 descriptor at i (the length is a 7-bit varint)."""
    tag, n, i = buf[i], 0, i + 1
    for _ in range(4):
        b = buf[i]; i += 1
        n = (n << 7) | (b & 0x7F)
        if not b & 0x80:
            break
    return tag, i, i + n


def _asc(buf, start, end):
    """(object type, sampling frequency index, channel configuration) from the esds box's AudioSpecificConfig."""
    tag, a, b = _descriptor(buf, start + 4)  # after version and flags: the ES_Descriptor
    if tag != 3:
        raise ValueError('no ES descriptor')
    flags, i = buf[a + 2], a + 3
    if flags & 0x80:
        i += 2
    if flags & 0x40:
        i += 1 + buf[i]
    if flags & 0x20:
        i += 2
    tag, a, b = _descriptor(buf, i)  # DecoderConfigDescriptor
    if tag != 4:
        raise ValueError('no decoder config')
    tag, a, b = _descriptor(buf, a + 13)  # DecoderSpecificInfo
    if tag != 5:
        raise ValueError('no AudioSpecificConfig')
    bits = int.from_bytes(buf[a:b], 'big'), (b - a) * 8
    get = lambda pos, n: (bits[0] >> (bits[1] - pos - n)) & ((1 << n) - 1)
    aot, sfi, ch = get(0, 5), get(5, 4), get(9, 4)
    if aot == 31 or sfi == 15:
        raise ValueError('unusual AudioSpecificConfig')
    return aot, sfi, ch


@lru_cache(maxsize=64)
def _tables(path, mtime):
    """The parts of a sprite a clip needs: its bytes, timescale, frame places and times, priming and ADTS fields."""
    buf = open(path, 'rb').read()
    moov = _child(buf, 0, len(buf), b'moov')
    trak = moov and _child(buf, moov[0], moov[1], b'trak')
    mdia = trak and _child(buf, trak[0], trak[1], b'mdia')
    stbl = mdia and _path(buf, mdia[0], mdia[1], b'minf', b'stbl')
    mdhd = mdia and _child(buf, mdia[0], mdia[1], b'mdhd')
    if not (stbl and mdhd):
        raise ValueError('not an audio MP4')
    v = buf[mdhd[0]]
    scale = struct.unpack('>I', buf[mdhd[0] + (20 if v == 1 else 12):][:4])[0]
    # the first sample entry (mp4a) and its esds
    stsd = _child(buf, stbl[0], stbl[1], b'stsd')
    entry = next(_boxes(buf, stsd[0] + 8, stsd[1]))
    if entry[0] != b'mp4a':
        raise ValueError('not AAC')
    ver = struct.unpack('>H', buf[entry[1] + 8:entry[1] + 10])[0]
    esds = _child(buf, entry[1] + 28 + {1: 16, 2: 36}.get(ver, 0), entry[2], b'esds')
    aot, sfi, ch = _asc(buf, *esds)
    # sizes, durations, chunks
    a, _ = _child(buf, stbl[0], stbl[1], b'stsz')
    fixed, count = struct.unpack('>II', buf[a + 4:a + 12])
    sizes = [fixed] * count if fixed else list(struct.unpack(f'>{count}I', buf[a + 12:a + 12 + 4 * count]))
    a, _ = _child(buf, stbl[0], stbl[1], b'stts')
    n = struct.unpack('>I', buf[a + 4:a + 8])[0]
    durs = []
    for k in range(n):
        c, d = struct.unpack('>II', buf[a + 8 + 8 * k:a + 16 + 8 * k])
        durs += [d] * c
    co = _child(buf, stbl[0], stbl[1], b'stco')
    if co:
        m = struct.unpack('>I', buf[co[0] + 4:co[0] + 8])[0]
        chunks = list(struct.unpack(f'>{m}I', buf[co[0] + 8:co[0] + 8 + 4 * m]))
    else:
        co = _child(buf, stbl[0], stbl[1], b'co64')
        m = struct.unpack('>I', buf[co[0] + 4:co[0] + 8])[0]
        chunks = list(struct.unpack(f'>{m}Q', buf[co[0] + 8:co[0] + 8 + 8 * m]))
    a, _ = _child(buf, stbl[0], stbl[1], b'stsc')
    n = struct.unpack('>I', buf[a + 4:a + 8])[0]
    runs = [struct.unpack('>III', buf[a + 8 + 12 * k:a + 20 + 12 * k]) for k in range(n)]
    offsets, s = [], 0
    for k, (first, per, _) in enumerate(runs):
        last = runs[k + 1][0] - 1 if k + 1 < len(runs) else len(chunks)
        for chunk in range(first, last + 1):
            pos = chunks[chunk - 1]
            for _ in range(per):
                if s >= count:
                    break
                offsets.append(pos); pos += sizes[s]; s += 1
    starts, t = [], 0
    for d in durs:
        starts.append(t); t += d
    # the encoder's priming: media time where the presentation (the timings in index.json) begins. Measured in
    # Chrome on b000 (2026-11-24): the sprite decodes without its first 2112 samples, the ADTS frames with them.
    elst = trak and _path(buf, trak[0], trak[1], b'edts', b'elst')
    prime = 0
    if elst:
        v = buf[elst[0]]
        if struct.unpack('>I', buf[elst[0] + 4:elst[0] + 8])[0]:
            prime = struct.unpack('>q' if v == 1 else '>i', buf[elst[0] + (16 if v == 1 else 12):][:8 if v == 1 else 4])[0]
            prime = max(0, prime)
    if not prime:  # no edit list: an iTunes-style note (iTunSMPB: priming, padding, length in hex) gives the priming
        k = buf.find(b'iTunSMPB', moov[0], moov[1])
        d = buf.find(b'data', k, moov[1]) if k > 0 else -1
        if d > 0:
            size = struct.unpack('>I', buf[d - 4:d])[0]
            try:
                prime = int(buf[d + 12:d - 4 + size].decode('ascii').split()[1], 16)
            except (ValueError, IndexError):
                prime = 0
    return buf, scale, offsets, sizes, starts, durs, prime, aot, sfi, ch


def _adts(frame, aot, sfi, ch):
    n = len(frame) + 7
    return bytes((0xFF, 0xF1, ((aot - 1) & 3) << 6 | sfi << 2 | (ch >> 2) & 1, (ch & 3) << 6 | (n >> 11) & 3,
                  (n >> 3) & 0xFF, (n & 7) << 5 | 0x1F, 0xFC)) + frame


def clip(path, start, end, longest=MAX, lead=LEAD, tail=0.0):
    """ADTS bytes of one word (or one sentence of a narration: longest 40): `lead` seconds before it (silence), and
    after it `tail` seconds of the file (a word: none, so the file stays short; see below). start/end: its place in the
    file in seconds, as index.json (or the narration's timings) gives it.
    A word ends with the frame that holds its end: on an iPhone an <audio> shorter than 0.95 s is never shown in Now
    Playing (WebKit MediaElementSession, YouveGotMailDuration), and a word's own timings already end in about 50 ms of
    quiet, so nothing of the word is lost (measured in Chrome)."""
    if not (0 <= start < end and end - start <= longest) or not LEADS[0] <= lead <= LEADS[1]:
        raise ValueError('not a word clip')
    from pathlib import Path
    p = Path(path)
    buf, scale, offsets, sizes, starts, durs, prime, aot, sfi, ch = _tables(str(p), p.stat().st_mtime_ns)
    frame = lambda t: max(0, min(len(starts) - 1, bisect_right(starts, t) - 1))  # the frame playing at media time t
    front = min(PAD, lead)
    m0, m1 = prime + (start - front) * scale, prime + (end + tail) * scale
    first, last = frame(max(0, m0)), frame(m1)
    # silence in front: copies of a frame from the middle of the gap before the word (or the first frame of the file)
    quiet = frame(max(0, prime + (start - 0.1) * scale))
    copies = max(0, round(((lead - front) * scale - (m0 - starts[first])) / (durs[quiet] or 1024)))
    out = [_adts(buf[offsets[quiet]:offsets[quiet] + sizes[quiet]], aot, sfi, ch)] * copies
    out += [_adts(buf[offsets[k]:offsets[k] + sizes[k]], aot, sfi, ch) for k in range(first, last + 1)]
    return b''.join(out)
