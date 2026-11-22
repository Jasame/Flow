"""Spoken test clips for the production end-to-end check (Kokoro, then AAC in an .m4a)."""
import subprocess, sys, json
from pathlib import Path
import soundfile as sf
from kokoro_onnx import Kokoro
FLOW, MODELS, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(FLOW))
import next_service as nx
from content_v50 import v5_materials
k = Kokoro(str(MODELS / 'kokoro-v1.0.int8.onnx'), str(MODELS / 'voices-v1.0.bin'))
p = next(x for x in v5_materials() if x['id'] == 'v5-science-b2-noise-cancelling')
clips = {
    'shadow_s0': (nx.sentences(p['body'])[0], 'am_michael', 'en-us'),
    'think_ok': ('think', 'bm_george', 'en-gb'),
    'think_as_sink': ('sink', 'bm_george', 'en-gb'),
    'retell': ('Noise cancelling headphones listen to the sound around you and make an opposite sound wave. The two waves cancel out, '
               'so the low roar of an engine almost disappears. They work best on steady, low sounds, not on voices.', 'af_bella', 'en-us'),
    'dialog': ('I would like to buy some headphones for my train journey. Which ones are the quietest?', 'af_heart', 'en-us'),
}
for name, (text, voice, lang) in clips.items():
    s, sr = k.create(text, voice=voice, speed=1.0, lang=lang)
    wav = OUT / f'{name}.wav'; sf.write(wav, s, sr, subtype='PCM_16')
    subprocess.run(['afconvert', '-f', 'm4af', '-d', 'aac', str(wav), str(OUT / f'{name}.m4a')], check=True, capture_output=True); wav.unlink()
    print(name, (OUT / f'{name}.m4a').stat().st_size, 'bytes', '|', text[:60])
