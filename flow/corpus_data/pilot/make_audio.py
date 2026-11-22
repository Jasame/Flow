"""Builds the pilot's synthetic audio (developer machine, macOS `say` + `afconvert`).

The spoken text is the clip text from the pilot JSON: production markers are never present there,
numbers are written as words so the reading is fixed. Output files are named by a hash, so a
file name never reveals an answer. A manifest records duration and words per minute for review.
Usage: python3 make_audio.py [pilot.json]
"""
import json,hashlib,subprocess,sys,tempfile,re
from pathlib import Path
HERE=Path(__file__).resolve().parent
VOICE='Samantha';RATE=60  # embedded [[rate]]: `say -r` is ignored here; long notices measure ~125–135 words/min

def paced(text):
 # Short pauses after commas and sentence ends; the voice otherwise runs short clips together.
 return re.sub(r'([.!?])\s+',r'\1 [[slnc 450]] ',re.sub(r',\s+',', [[slnc 200]] ',text))

def clip_file(pilot_id,name,text):return hashlib.sha256(f'{pilot_id}|{name}|{text}'.encode()).hexdigest()[:20]+'.m4a'

def main(path):
 data=json.loads(Path(path).read_text(encoding='utf-8'));out=HERE/'audio';out.mkdir(exist_ok=True);manifest={}
 for name,clip in data['clips'].items():
  text=clip['text'];assert '[' not in text and ']' not in text,name
  f=out/clip_file(data['pilot_id'],name,text)
  with tempfile.TemporaryDirectory() as t:
   aiff=Path(t)/'x.aiff'
   subprocess.run(['say','-v',VOICE,'-o',str(aiff),f'[[rate {RATE}]] '+paced(text)],check=True)
   subprocess.run(['afconvert','-f','m4af','-d','aac','-b','64000',str(aiff),str(f)],check=True)
  info=subprocess.run(['afinfo',str(f)],capture_output=True,text=True).stdout
  seconds=float(re.search(r'estimated duration: ([0-9.]+)',info).group(1));words=len(re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*",re.sub(r'\b([ap])\.m\.',r'\1m',text)))
  manifest[name]={'file':f.name,'seconds':round(seconds,2),'words':words,'wpm':round(words/seconds*60) if seconds else None,'voice':VOICE,'rate':RATE,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
 (HERE/(data['pilot_id'].lower()+'-audio.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=1),encoding='utf-8')
 print(json.dumps(manifest,ensure_ascii=False,indent=1))

if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else HERE/'flow-pack-001.json')
