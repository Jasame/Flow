"""Pre-generate Flow narration with Kokoro: every v5 material x 4 voices.

Output per voice/material: <out>/<voice>/<id>.m4a and <id>.json
  {"v":1,"voice":..,"duration":s,"sentences":[{"s":start,"e":end,"w":[[charOffset,start,end],...]}]}
Sentences come from flow's own next_service.sentences(), so indices match what the site shows.
Sentence times are exact (measured from synthesis); word times are spread inside each sentence by
phoneme count, which is close enough for read-along highlighting.

usage: uv run --with kokoro-onnx --with soundfile python tools/gen_audio.py flow <models dir> flow/audio [workers] [only-id ...]
Models: kokoro-v1.0.int8.onnx + voices-v1.0.bin from github.com/thewh1teagle/kokoro-onnx releases (Apache-2.0).
macOS only as written (uses afconvert for AAC).
"""
import json, os, re, subprocess, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

FLOW, MODELS, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
WORKERS = int(sys.argv[4]) if len(sys.argv) > 4 else 3
ONLY = set(sys.argv[5:])
sys.path.insert(0, str(FLOW))

VOICES = {  # key -> (kokoro voice, lang, accent, gender)
    'us-f': ('af_heart', 'en-us', 'us', 'f'),
    'us-m': ('am_michael', 'en-us', 'us', 'm'),
    'uk-f': ('bf_emma', 'en-gb', 'uk', 'f'),
    'uk-m': ('bm_george', 'en-gb', 'uk', 'm'),
}
# For other speakers in dialogues: second voice of each accent/gender so two same-gender speakers differ.
ALT = {('us', 'f'): ('af_bella', 'en-us'), ('us', 'm'): ('am_adam', 'en-us'), ('uk', 'f'): ('bf_isabella', 'en-gb'), ('uk', 'm'): ('bm_lewis', 'en-gb')}
FEMALE = set('Nadia Sara Amara Ella Chloe Sofia Lena Hannah Amira Yuqi Ruby Mei Tara Leila Xiaowen Mira Maya Priya Ines Giulia Mum Zoe Anna Mia Rosa Nina Lind Ana Farah Elif Mariana Ruth Bea Hana Esther Claire Marta'.split())
MALE = set('Tom Jun Ravi Daniel Arjun Kenji Dev Ben Ollie Hao Luca Dad Jake Leo Diego Kwame Josh Marco Leon Tomasz Rohan Yusuf Femi'.split()) | {'Mr Patel'}
LABEL = re.compile(r'([A-Z][a-z]+(?: [A-Z][a-z]+)?):\s+')
WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
GAP = 0.3


def gender(name):
    return 'f' if name in FEMALE else 'm' if name in MALE or name.startswith('Mr ') else None


def plan_voices(sentences, key):
    """speaker -> (voice, lang). Narration and the first speaker use the chosen voice."""
    voice, lang, accent, g0 = VOICES[key]
    other_accent = 'uk' if accent == 'us' else 'us'
    speakers = []
    for s in sentences:
        m = LABEL.match(s)
        if m and m.group(1) not in speakers:
            speakers.append(m.group(1))
    out, used = {}, []
    for who in speakers:
        g = gender(who)
        if g is None:  # unknown (Interviewer, Staff…): contrast with whoever is already speaking
            g = ('m' if used and used[-1][1] == 'f' else 'f') if used else g0
        same = [u for u in used if u[1] == g]
        if not used and g == g0:
            pick = (voice, lang)
        elif not same:
            base = next(v for k, v in VOICES.items() if v[2] == accent and v[3] == g)
            pick = (base[0], base[1])
        elif len(same) == 1:
            pick = ALT[(accent, g)]
        else:
            alt = next(v for k, v in VOICES.items() if v[2] == other_accent and v[3] == g)
            pick = (alt[0], alt[1])
        out[who] = pick
        used.append((who, g))
    return out


_kokoro = None
_phon = {}


def kokoro():
    global _kokoro
    if _kokoro is None:
        import onnxruntime as ort
        from kokoro_onnx import Kokoro
        opts = ort.SessionOptions()  # one process per worker: cap threads so workers don't thrash each other
        opts.intra_op_num_threads = int(os.getenv('KOKORO_THREADS', '3')); opts.inter_op_num_threads = 1
        session = ort.InferenceSession(str(MODELS / 'kokoro-v1.0.int8.onnx'), sess_options=opts, providers=['CPUExecutionProvider'])
        _kokoro = Kokoro.from_session(session, str(MODELS / 'voices-v1.0.bin'))
    return _kokoro


def phonemes(word, lang):
    k = (word.lower(), lang)
    if k not in _phon:
        try:
            _phon[k] = len(kokoro().tokenizer.phonemize(word, lang).strip()) or len(word)
        except Exception:
            _phon[k] = len(word)
    return _phon[k]


def render(job):
    import numpy as np, soundfile as sf
    pid, key, sentences = job
    out_dir = OUT / key
    out_dir.mkdir(parents=True, exist_ok=True)
    m4a, meta = out_dir / f'{pid}.m4a', out_dir / f'{pid}.json'
    if m4a.exists() and meta.exists():
        return pid, key, 'skip', 0
    t0 = time.time()
    voice, lang = VOICES[key][0], VOICES[key][1]
    speakers = plan_voices(sentences, key)
    current = (voice, lang)
    chunks, timeline, clock, sr = [], [], 0.0, 24000
    for s in sentences:
        m = LABEL.match(s)
        start_char = 0
        if m and m.group(1) in speakers:
            current = speakers[m.group(1)]
            start_char = m.end()
        spoken = s[start_char:].strip()
        if not WORD.search(spoken):
            timeline.append({'s': round(clock, 3), 'e': round(clock, 3), 'w': []})
            continue
        samples, sr = kokoro().create(spoken, voice=current[0], speed=1.0, lang=current[1])
        dur = len(samples) / sr
        words = [w for w in WORD.finditer(s) if w.start() >= start_char]
        weights = []
        for w in words:
            wt = phonemes(w.group(), current[1]) + 1.5
            tail = s[w.end():w.end() + 2]
            if tail[:1] in ',;:' or tail[:1] in '—–-' and tail[1:2] == ' ':
                wt += 3
            weights.append(wt)
        total = sum(weights) or 1
        acc, wl = 0.0, []
        for w, wt in zip(words, weights):
            a = clock + dur * acc / total
            acc += wt
            wl.append([w.start(), round(a, 3), round(clock + dur * acc / total, 3)])
        timeline.append({'s': round(clock, 3), 'e': round(clock + dur, 3), 'w': wl})
        chunks += [samples, np.zeros(int(sr * GAP), dtype=samples.dtype)]
        clock += dur + GAP
    audio = np.concatenate(chunks)
    wav = out_dir / f'{pid}.wav'
    sf.write(wav, audio, sr, subtype='PCM_16')
    subprocess.run(['afconvert', '-f', 'm4af', '-d', 'aac', str(wav), str(m4a)], check=True, capture_output=True)
    wav.unlink()
    meta.write_text(json.dumps({'v': 1, 'voice': key, 'duration': round(len(audio) / sr, 3), 'sentences': timeline,
                                'speakers': {k: v[0] for k, v in speakers.items()}}, ensure_ascii=False, separators=(',', ':')))
    return pid, key, 'ok', time.time() - t0


def main():
    import next_service as nx
    from content_v50 import v5_materials
    jobs = [(p['id'], key, nx.sentences(p['body'])) for p in v5_materials() if not ONLY or p['id'] in ONLY for key in VOICES]
    print(f'{len(jobs)} jobs, {WORKERS} workers', flush=True)
    t0, done = time.time(), 0
    with ProcessPoolExecutor(WORKERS) as ex:
        for pid, key, state, secs in ex.map(render, jobs):
            done += 1
            if state == 'ok' and (done % 20 == 0 or ONLY):
                print(f'{done}/{len(jobs)} {key} {pid} {secs:.1f}s  elapsed {time.time() - t0:.0f}s', flush=True)
    index = {}
    for key in VOICES:
        for f in sorted((OUT / key).glob('*.json')):
            index.setdefault(f.stem, []).append(key)
    (OUT / 'index.json').write_text(json.dumps(index, separators=(',', ':')))
    print(f'DONE {done} jobs in {time.time() - t0:.0f}s, {len(index)} materials indexed', flush=True)


if __name__ == '__main__':
    os.environ.setdefault('OMP_NUM_THREADS', '2')
    main()
