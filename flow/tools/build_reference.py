#!/usr/bin/env python3
"""Read XLSX using stdlib; preserve all original rows. No workbook mutation."""
import sys,json,re,hashlib,collections
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as E
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def extract(path):
 with ZipFile(path) as z:
  strings=[''.join(s.itertext()) for s in E.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',NS)]
  raw=[]
  for row in E.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('m:sheetData/m:row',NS)[1:]:
   cells={}
   for cell in row.findall('m:c',NS):
    v=cell.find('m:v',NS);text=v.text if v is not None else ''
    if cell.get('t')=='s':text=strings[int(text)]
    cells[re.sub(r'\d','',cell.get('r'))]=text or ''
   if not cells.get('B'):continue
   raw.append({'row':int(row.get('r')),'rank':int(cells['A']),'word':cells['B'],'phonetic':cells.get('C',''),'meaning':cells.get('D',''),'examples':cells.get('E',''),'forms':cells.get('F',''),'synonyms':cells.get('G','')})
 groups=collections.OrderedDict()
 for r in raw:groups.setdefault(r['word'].strip().casefold(),[]).append(r)
 terms=[]
 for norm,variants in groups.items():
  best=min(variants,key=lambda r:(not bool(r['examples']),r['rank']))
  flags=[]
  if not re.fullmatch(r"[a-zA-Z][a-zA-Z '\-]{0,79}",norm):flags.append('词形含数字或斜线，需要人工拆分后再学习')
  if norm in ('be','to'):flags.append('原表词性与常见用法可能不一致，请核对')
  if len({v['meaning'] for v in variants})>1:flags.append('原表存在不同释义版本；词形合并不代表义项合并')
  terms.append({'id':'yl-'+hashlib.sha256(norm.encode()).hexdigest()[:20],'norm':norm,'word':best['word'],'rank':min(v['rank'] for v in variants),'variants':variants,'flags':flags})
 stats={'rows':len(raw),'terms':len(terms),'duplicate_rows':len(raw)-len(terms),'rows_with_examples':sum(bool(r['examples']) for r in raw),'terms_with_examples':sum(any(v['examples'] for v in t['variants']) for t in terms),'terms_flagged':sum(bool(t['flags']) for t in terms),'rows_with_forms':sum(bool(r['forms']) for r in raw),'rows_with_synonyms':sum(bool(r['synonyms']) for r in raw)}
 return {'source':{'file':path.name,'sheet':'Sheet1','sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'status':'用户提供，未经全面人工校对','grouping':'按去除首尾空格并忽略大小写的词形分组；保留每行原文、词频序号和表格行号'},'stats':stats,'terms':terms}
if __name__=='__main__':
 result=extract(Path(sys.argv[1]));Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print(json.dumps(result['stats'],ensure_ascii=False))
