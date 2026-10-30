"""Versioned graded situations; sibling levels are one learning context family."""
import json
from pathlib import Path
from content_v08 import all_materials as previous_materials,THEMES
GRADED=json.loads((Path(__file__).resolve().parent/'corpus_data'/'graded-packs.json').read_text(encoding='utf-8'))
def all_materials():return previous_materials()+GRADED
