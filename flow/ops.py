#!/usr/bin/env python3
"""Root-only backup and explicit restore for the BaoTa installation."""
import argparse,datetime,json,os,secrets,sqlite3,tarfile,tempfile,time,subprocess,shutil
from pathlib import Path
ROOT=Path('/www/wwwroot/flow');BACKUPS=Path('/www/backup/flow/daily')
def check(path):
 with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as c:
  if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('数据库完整性校验失败')
  if c.execute('PRAGMA foreign_key_check').fetchall():raise RuntimeError('数据库关联校验失败')
  if not c.execute("SELECT 1 FROM migrations WHERE version='2.1'").fetchone():raise RuntimeError('这不是 v2.1 备份，请使用对应版本的恢复工具')
def backup():
 os.umask(0o077);BACKUPS.mkdir(parents=True,exist_ok=True,mode=0o700)
 stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid())+'-'+secrets.token_hex(3);folder=BACKUPS/('flow-'+stamp);folder.mkdir(mode=0o700)
 source=ROOT/'data/flow.sqlite3'
 try:
  if not source.is_file():raise RuntimeError('数据库不存在，拒绝创建空备份')
  with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as c,sqlite3.connect(folder/'flow.sqlite3') as dst:c.backup(dst)
  check(folder/'flow.sqlite3')
  # Restore drill to an isolated temporary copy; never touches the live database.
  with tempfile.TemporaryDirectory() as tmp:
   restored=Path(tmp)/'restore.sqlite3';shutil.copy2(folder/'flow.sqlite3',restored);check(restored)
  with tarfile.open(folder/'source.tar.gz','w:gz') as archive:
   for path in ROOT.rglob('*'):
    rel=path.relative_to(ROOT)
    if path.is_relative_to(BACKUPS):continue
    if any(x in rel.parts for x in ('data','.venv','__pycache__','.git')) or path.is_symlink():continue
    if path.is_file():archive.add(path,arcname=str(rel),recursive=False)
  if Path('/etc/flow.env').exists():shutil.copyfile('/etc/flow.env',folder/'flow.env')
  (folder/'manifest.json').write_text(json.dumps({'version':'2.1','created':time.time(),'integrity':'ok','restore_copy_checked':True}))
  status={'ok':True,'created':time.time()};print('备份与恢复副本校验通过：'+str(folder))
  # Only remove completed backups created by this tool, keeping the most recent 14.
  completed=sorted([p for p in BACKUPS.glob('flow-*') if (p/'manifest.json').is_file()],key=lambda p:p.stat().st_mtime,reverse=True)
  for old in completed[14:]:shutil.rmtree(old)
 except Exception:
  status={'ok':False,'created':time.time()};raise
 finally:
  status_file=ROOT/'data/backup-status.json';temp=status_file.with_suffix('.tmp');temp.write_text(json.dumps(status));temp.chmod(0o644);temp.replace(status_file)
 return folder

def restore(folder,apply):
 folder=Path(folder).resolve();source=folder/'flow.sqlite3';check(source)
 if not apply:
  print('备份有效。执行恢复需要明确加入 --apply。服务和配置均未改动。');return
 # Stage the selected snapshot before retention rotates the oldest backup.
 with tempfile.TemporaryDirectory(prefix='flow-restore-') as tmp:
  staged=Path(tmp)/'selected.sqlite3';shutil.copy2(source,staged);check(staged)
  subprocess.run(['systemctl','stop','flow'],check=True)
  timer_active=subprocess.run(['systemctl','is-active','--quiet','flow-daily.timer'],capture_output=True).returncode==0
  subprocess.run(['systemctl','stop','flow-daily.timer','flow-daily.service'],check=False,capture_output=True)
  try:
   safety=backup();target=ROOT/'data/flow.sqlite3';temporary=target.with_suffix('.restore');shutil.copy2(staged,temporary);check(temporary)
   import pwd
   www=pwd.getpwnam('www');os.chown(temporary,www.pw_uid,www.pw_gid);temporary.chmod(0o600)
   for suffix in ('-wal','-shm'):
    extra=Path(str(target)+suffix)
    if extra.exists():extra.unlink()
   temporary.replace(target)
   print('数据库已恢复；恢复前副本：'+str(safety))
   print('程序及 /etc/flow.env 未更换；若需回滚代码，请使用对应 source.tar.gz 并核对配置。')
  finally:
   if timer_active:subprocess.run(['systemctl','start','flow-daily.timer'],check=True)
   subprocess.run(['systemctl','start','flow'],check=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['backup','restore']);parser.add_argument('folder',nargs='?');parser.add_argument('--apply',action='store_true');args=parser.parse_args()
 if os.geteuid()!=0:raise SystemExit('请使用 root 运行，以保护备份与配置。')
 if args.action=='backup':backup()
 elif args.folder:restore(args.folder,args.apply)
 else:parser.error('restore 需要指定备份目录')
