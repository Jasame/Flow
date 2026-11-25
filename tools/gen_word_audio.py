"""Pre-generate word pronunciations for Flow's word books with Kokoro (US and UK voice).

Words are packed 100 to a file ("sprites") so a day of reviews needs a few requests, not hundreds:
  <out>/<accent>/w000.m4a ...    and    <out>/index.json  {"us": {"word": ["w000", start, end]}, "uk": {...}}
Frequency-book words go in w### files, exam-only words in x###, pronunciation-practice extras in p###, so no group reshuffles another.
Run again on an <out> that already has an index.json and only the book words it lacks are made (words of the data books,
flow/corpus_data/wordbooks*.json, and of book lists that changed since): they go in new b### files after the last one, and
no earlier file is touched. Copy the new files and index.json to the server's audio/words (see tools/media/README.md).

usage: gen_word_audio.py <flow dir> <models dir> <out dir> [workers]
"""
import json, os, subprocess, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

FLOW, MODELS, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
WORKERS = int(sys.argv[4]) if len(sys.argv) > 4 else 3
sys.path.insert(0, str(FLOW))
ACCENTS = {'us': ('af_heart', 'en-us'), 'uk': ('bf_emma', 'en-gb')}
PER = 100
GAP, PAD = 0.2, 0.04  # silence between words; margin kept around each word when trimming
BITRATE = '24000'  # plenty for one voice saying one word; keeps ~17k words x 2 accents near 100 MB
_kokoro = None
SAY = {'dvd': 'DVD', 'cd': 'CD', 'tv': 'TV', 'pc': 'PC'}  # said as letters, not as a word


def kokoro():
    global _kokoro
    if _kokoro is None:
        import onnxruntime as ort
        from kokoro_onnx import Kokoro
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = int(os.getenv('KOKORO_THREADS', '2')); opts.inter_op_num_threads = 1
        session = ort.InferenceSession(str(MODELS / 'kokoro-v1.0.int8.onnx'), sess_options=opts, providers=['CPUExecutionProvider'])
        _kokoro = Kokoro.from_session(session, str(MODELS / 'voices-v1.0.bin'))
    return _kokoro


def trim(samples, sr):
    """Cut the model's leading/trailing silence, keeping a small margin so plosives aren't clipped."""
    import numpy as np
    loud = np.flatnonzero(np.abs(samples) > 0.012)
    if not len(loud):
        return samples
    a, b = max(0, loud[0] - int(PAD * sr)), min(len(samples), loud[-1] + int(PAD * sr))
    return samples[a:b]


def render(job):
    import numpy as np, soundfile as sf
    accent, sprite, words = job
    voice, lang = ACCENTS[accent]
    d = OUT / accent
    d.mkdir(parents=True, exist_ok=True)
    m4a, meta = d / f'{sprite}.m4a', d / f'{sprite}.json'
    if m4a.exists() and meta.exists():
        return accent, sprite, 'skip'
    sr, chunks, marks, clock = 24000, [], {}, 0.0
    for w in words:
        samples, sr = kokoro().create(SAY.get(w, w), voice=voice, speed=0.92, lang=lang)
        samples = trim(samples, sr)
        dur = len(samples) / sr
        marks[w] = [round(clock, 3), round(clock + dur, 3)]
        chunks += [samples, np.zeros(int(sr * GAP), dtype=samples.dtype)]
        clock += dur + GAP
    wav = d / f'{sprite}.wav'
    sf.write(wav, np.concatenate(chunks), sr, subtype='PCM_16')
    subprocess.run(['afconvert', '-f', 'm4af', '-d', 'aac', '-b', BITRATE, str(wav), str(m4a)], check=True, capture_output=True)
    # 隐式标识 (aigc_label, 2026-11-25): a synthetic voice, so the file says so; the audio frames are not touched
    import aigc_label
    m4a.write_bytes(aigc_label.mp4(m4a.read_bytes(), f'flow-words-{accent}-{sprite}'))
    wav.unlink()
    meta.write_text(json.dumps(marks, separators=(',', ':')))
    return accent, sprite, 'ok'


def known_words():
    """Words <out> already has a pronunciation for (US list; both accents are always made together)."""
    f = OUT / 'index.json'
    return set(json.loads(f.read_text()).get('us', {})) if f.exists() else set()


def main():
    import vocab_service as vs
    bw = vs.book_words()
    have = known_words()
    if have:  # top up: every book word still missing, in study order of the books, in new b### files
        missing = list(dict.fromkeys(w for k in bw for _, w in bw[k] if w not in have))
        first = 1 + max((int(f.stem[1:]) for f in (OUT / 'us').glob('b[0-9][0-9][0-9].json')), default=-1)
        jobs = [(a, f'b{first + k // PER:03d}', missing[k:k + PER]) for a in ACCENTS for k in range(0, len(missing), PER)]
        print(f'{len(have)} words already made; {len(missing)} missing, {len(jobs)} new files from b{first:03d}', flush=True)
        return run(jobs)
    freq = [w for _, w in sorted({(r, w) for k in vs.BOOKS for r, w in bw[k]})]
    seen = set(freq)
    exam = [w for _, w in sorted({(r, w) for k in vs.EXAM_BOOKS for r, w in bw[k] if w not in seen})]
    seen |= set(exam)
    import sounds  # 发音入门 minimal pairs that are not in any word book (inflected forms like "sat", "stood")
    extra = sorted({w for s in sounds.SETS for pair in s['pairs'] for w in pair if w not in seen})
    jobs = [(a, f'{prefix}{k // PER:03d}', words[k:k + PER]) for prefix, words in (('w', freq), ('x', exam), ('p', extra))
            for a in ACCENTS for k in range(0, len(words), PER)]
    print(f'{len(freq)} + {len(exam)} + {len(extra)} words, {len(jobs)} files, {WORKERS} workers', flush=True)
    run(jobs)


def run(jobs):
    t0 = time.time()
    with ProcessPoolExecutor(WORKERS) as ex:
        for n, (a, sprite, state) in enumerate(ex.map(render, jobs), 1):
            if n % 20 == 0:
                print(f'{n}/{len(jobs)} {a}/{sprite} {state} elapsed {time.time() - t0:.0f}s', flush=True)
    index = {a: {} for a in ACCENTS}
    for a in ACCENTS:
        for f in sorted((OUT / a).glob('[wxpb][0-9][0-9][0-9].json')):
            for w, (s, e) in json.loads(f.read_text()).items():
                index[a][w] = [f.stem, s, e]
    (OUT / 'index.json').write_text(json.dumps(index, separators=(',', ':')))
    print(f'DONE {sum(len(v) for v in index.values())} pronunciations in {time.time() - t0:.0f}s', flush=True)


if __name__ == '__main__':
    os.environ.setdefault('OMP_NUM_THREADS', '2')
    main()
