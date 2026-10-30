"""Question revisions are new materials; historical versions remain readable."""
import json
from pathlib import Path
from content_v09 import all_materials as previous_materials
REVISED=json.loads((Path(__file__).resolve().parent/'corpus_data/revised-packs.json').read_text())
SUPERSEDED={p['revision_of'] for p in REVISED}
def all_materials():return previous_materials()+REVISED
