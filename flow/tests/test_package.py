import unittest,re,tempfile,shutil,subprocess,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class UpgradePackageTests(unittest.TestCase):
 def test_upgrade_copies_a_bootable_application_and_all_frontend_assets(self):
  script=(ROOT/'upgrade.sh').read_text();lists=re.findall(r'for name in ([^;]+); do',script)
  self.assertGreaterEqual(len(lists),2)
  with tempfile.TemporaryDirectory() as tmp:
   target=Path(tmp)
   for name in lists[0].split():
    (target/name).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target/name)
   (target/'public').mkdir()
   for name in lists[1].split():shutil.copy2(ROOT/'public'/name,target/'public'/name)
   page=(target/'public/index.html').read_text()
   for asset in re.findall(r'(?:src|href)="/([^"?]+)',page):self.assertTrue((target/'public'/asset).is_file(),asset)
   env={**os.environ,'FLOW_DATA_DIR':str(target/'data')}
   result=subprocess.run([sys.executable,'-c',"import app; app.init(); c=app.db(); assert c.execute('SELECT COUNT(*) FROM questions').fetchone()[0]==72; assert c.execute('SELECT COUNT(*) FROM lab_packs').fetchone()[0]==262; assert c.execute('SELECT COUNT(*) FROM lexicon').fetchone()[0]==107; assert c.execute('SELECT COUNT(*) FROM kg_edges').fetchone()[0]>500; assert c.execute('SELECT COUNT(*) FROM reference_terms').fetchone()[0]==17634"],cwd=target,env=env,capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
if __name__=='__main__':unittest.main()
