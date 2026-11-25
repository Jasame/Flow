#!/usr/bin/env python3
"""Root-only backup and explicit restore for the BaoTa installation.

The daily backup (flow-backup.service, 03:15) keeps the database as it is, so the copy 杭州 pulls every day can be
restored straight away. /etc/flow.env holds every key: with FLOW_BACKUP_AGE_RECIPIENT set (the owner's age public key,
age1…; several: comma-separated) it is kept only encrypted, as flow.env.age (age -r), and its private key never comes
to a server. Restoring /etc/flow.env from such a backup takes that private key, which only the user has, in their
password manager (the AGE-SECRET-KEY-1… line): ask the user for it, put it in a temporary file (chmod 600), then
  age -d -i <that file> -o /etc/flow.env <backup>/flow.env.age && chmod 600 /etc/flow.env
and delete the temporary file. Without FLOW_BACKUP_AGE_RECIPIENT, flow.env is copied as before."""
import argparse,datetime,json,os,re,secrets,sqlite3,tarfile,tempfile,time,subprocess,shutil
from pathlib import Path
ROOT=Path('/www/wwwroot/flow');BACKUPS=Path('/www/backup/flow/daily');ENV_FILE=Path('/etc/flow.env')
AGE_HEADER=b'age-encryption.org/v1\n'  # how every file age writes begins
def check(path):
 with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as c:
  if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('数据库完整性校验失败')
  if c.execute('PRAGMA foreign_key_check').fetchall():raise RuntimeError('数据库关联校验失败')
  if not c.execute("SELECT 1 FROM migrations WHERE version='2.1'").fetchone():raise RuntimeError('这不是 v2.1 备份，请使用对应版本的恢复工具')
def backup(env_required=True):
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
  env,env_error=save_env(folder)
  (folder/'manifest.json').write_text(json.dumps({'version':'2.1','created':time.time(),'integrity':'ok','restore_copy_checked':True,'env':env}))
  status={'ok':True,'created':time.time()};print('备份与恢复副本校验通过：'+str(folder))
  # Only remove completed backups created by this tool, keeping the most recent 14.
  completed=sorted([p for p in BACKUPS.glob('flow-*') if (p/'manifest.json').is_file()],key=lambda p:p.stat().st_mtime,reverse=True)
  for old in completed[14:]:shutil.rmtree(old)
  prune_deploy_copies(channel=channel())
  if env_error:
   print(env_error)
   # the database and the code are kept all the same; the daily backup still ends as failed, so someone looks at it
   # (the copy restore makes before it replaces the database goes on: a restore never waits for flow.env)
   if env_required:raise RuntimeError(env_error)
 except Exception:
  status={'ok':False,'created':time.time()};raise
 finally:
  status_file=ROOT/'data/backup-status.json';temp=status_file.with_suffix('.tmp');temp.write_text(json.dumps(status));temp.chmod(0o644);temp.replace(status_file)
 return folder

def age_recipients():
 """FLOW_BACKUP_AGE_RECIPIENT: from the environment, or else as systemd would read it from flow.env itself (the backup
 unit has no EnvironmentFile). One age public key, or several, comma-separated; [] when not set."""
 value=os.getenv('FLOW_BACKUP_AGE_RECIPIENT','')
 if not value.strip():
  try:lines=ENV_FILE.read_text(encoding='utf-8',errors='replace').splitlines()
  except OSError:lines=[]
  for line in lines:
   if line.startswith('FLOW_BACKUP_AGE_RECIPIENT='):value=line.split('=',1)[1]
 value=value.strip()
 if len(value)>1 and value[0]==value[-1] and value[0] in '"\'':value=value[1:-1]
 return [r.strip() for r in value.split(',') if r.strip()]

def save_env(folder):
 """/etc/flow.env into the backup folder: encrypted to FLOW_BACKUP_AGE_RECIPIENT as flow.env.age when that is set (no
 readable copy anywhere in the backup), else flow.env as before. Returns (the file's name or None, an error or None);
 when encrypting fails nothing of flow.env is kept and the error says why."""
 if not ENV_FILE.exists():return None,None
 recipients=age_recipients()
 if not recipients:
  shutil.copyfile(ENV_FILE,folder/'flow.env');return 'flow.env',None
 out=folder/'flow.env.age'
 try:
  subprocess.run(['age',*[a for r in recipients for a in ('-r',r)],'-o',str(out),str(ENV_FILE)],check=True,capture_output=True,timeout=120)
  with open(out,'rb') as f:
   if f.read(len(AGE_HEADER))!=AGE_HEADER:raise ValueError('age 的输出不是加密文件')
 except (OSError,ValueError,subprocess.SubprocessError) as exc:
  if out.exists():out.unlink()
  said=(getattr(exc,'stderr',None) or b'').decode('utf-8','replace').strip().splitlines()  # age's own words, if any
  return None,'flow.env 没有存进备份：age 加密失败（%s: %s）'%(type(exc).__name__,(said[-1] if said else str(exc))[:200])
 return 'flow.env.age',None

def env_note(folder):
 """How to put this backup's flow.env back (restore leaves /etc/flow.env as it is)."""
 if (folder/'flow.env.age').exists():
  print('这份备份里的 flow.env 是加密的（flow.env.age）：要还原 /etc/flow.env，先找用户从密码管理器拿 age 私钥'
        '（AGE-SECRET-KEY-1… 那一行），存进一个临时文件（chmod 600），再执行 '
        'age -d -i <临时文件> -o /etc/flow.env '+str(folder/'flow.env.age')+' && chmod 600 /etc/flow.env，用完把临时文件删掉。')

# tools/flow-pull.sh keeps a copy of the database from before each deploy, in one folder for both sites:
# backup-pull-<YYYYMMDD-HHMMSS> for 语流 (flow), backup-pull-beta-<…> for the 内测版 (flow-beta).
COPIES={'prod':re.compile(r'backup-pull-\d{8}-\d{6}'),'beta':re.compile(r'backup-pull-beta-\d{8}-\d{6}')}
def channel():
 return 'beta' if os.getenv('FLOW_CHANNEL','').strip().lower()=='beta' else 'prod'
def dry_default(chan):
 """FLOW_PRUNE_DRY_RUN=1 lists only, =0 deletes; unset: the 内测版 lists only, 语流 deletes."""
 v=os.getenv('FLOW_PRUNE_DRY_RUN','').strip()
 return v=='1' if v in ('0','1') else chan=='beta'
def prune_deploy_copies(ops=Path('/root/claude-ops'),days=14,now=None,channel='prod',dry_run=None,say=print):
 """The database copies of this site's deploys older than 14 days go (the code files stay, for a rollback), so an
 account deleted with 注销账号 is gone from every backup within 14 days, as the 隐私说明 says. Only this site's own
 folders (COPIES[channel], the whole name) are looked at; anything else is left alone. Each copy is logged with its
 size before it goes; dry_run lists them and deletes nothing. Returns [(path, bytes, mtime)]."""
 pattern=COPIES.get(channel)
 if pattern is None:say('prune: unknown site %r, nothing done'%channel);return []
 dry=dry_default(channel) if dry_run is None else dry_run
 now=now or time.time();found=[]
 try:folders=sorted(p for p in ops.iterdir() if p.is_dir() and pattern.fullmatch(p.name))
 except OSError:return []
 for d in folders:
  f=d/'flow-before.sqlite3'
  try:st=f.stat()
  except OSError:continue
  if now-st.st_mtime>days*86400:found.append((f,st.st_size,st.st_mtime))
 label='只列不删' if dry else '删除'
 for f,size,mtime in found:
  say('prune %s [%s] %s %.1f MB %s'%(channel,label,f,size/1048576,datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')))
  if not dry:
   try:f.unlink()
   except OSError as exc:say('prune %s: could not delete %s: %s'%(channel,f,exc))
 say('prune %s [%s]: %d 个超过 %d 天的旧数据库副本，共 %.1f MB'%(channel,label,len(found),days,sum(x[1] for x in found)/1048576))
 return found

def restore(folder,apply):
 folder=Path(folder).resolve();source=folder/'flow.sqlite3';check(source)
 if not apply:
  print('备份有效。执行恢复需要明确加入 --apply。服务和配置均未改动。');env_note(folder);return
 # Stage the selected snapshot before retention rotates the oldest backup.
 with tempfile.TemporaryDirectory(prefix='flow-restore-') as tmp:
  staged=Path(tmp)/'selected.sqlite3';shutil.copy2(source,staged);check(staged)
  subprocess.run(['systemctl','stop','flow'],check=True)
  timer_active=subprocess.run(['systemctl','is-active','--quiet','flow-daily.timer'],capture_output=True).returncode==0
  subprocess.run(['systemctl','stop','flow-daily.timer','flow-daily.service'],check=False,capture_output=True)
  try:
   safety=backup(env_required=False);target=ROOT/'data/flow.sqlite3';temporary=target.with_suffix('.restore');shutil.copy2(staged,temporary);check(temporary)
   import pwd
   www=pwd.getpwnam('www');os.chown(temporary,www.pw_uid,www.pw_gid);temporary.chmod(0o600)
   for suffix in ('-wal','-shm'):
    extra=Path(str(target)+suffix)
    if extra.exists():extra.unlink()
   temporary.replace(target)
   print('数据库已恢复；恢复前副本：'+str(safety))
   print('程序及 /etc/flow.env 未更换；若需回滚代码，请使用对应 source.tar.gz 并核对配置。');env_note(folder)
  finally:
   if timer_active:subprocess.run(['systemctl','start','flow-daily.timer'],check=True)
   subprocess.run(['systemctl','start','flow'],check=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['backup','restore','prune-deploy']);parser.add_argument('folder',nargs='?');parser.add_argument('--apply',action='store_true')
 parser.add_argument('--channel',choices=['prod','beta']);parser.add_argument('--dry-run',action='store_true');args=parser.parse_args()
 if os.geteuid()!=0:raise SystemExit('请使用 root 运行，以保护备份与配置。')
 if args.action=='backup':backup()
 elif args.action=='prune-deploy':prune_deploy_copies(channel=args.channel or channel(),dry_run=True if args.dry_run else None)
 elif args.folder:restore(args.folder,args.apply)
 else:parser.error('restore 需要指定备份目录')
