"""Keep the previously deployed collector running during a model version rebuild."""
from contextlib import contextmanager
import json,os,subprocess,tempfile
from pathlib import Path

CHILD='''import json,sys,time
from pathlib import Path
import boat24_daily,boat24_compare,boat24_full_update,boat24_full_publish
from boat24_integrity import atomic_write
stop=Path(sys.argv[1])
while not stop.exists():
 try:
  boat24_daily.main();boat24_compare.main();boat24_full_update.main()
  m=json.loads(boat24_full_update.MANIFEST.read_text())
  for name in ('omura/docs/boat24_ledger.json','omura/docs/boat24_comparison.json'):
   if Path(name).is_file() and name not in m['paths']:m['paths'].append(name)
  atomic_write(boat24_full_update.MANIFEST,m);boat24_full_publish.main()
 except Exception as e:print('Previous collector retry:',str(e),flush=True)
 for _ in range(30):
  if stop.exists():break
  time.sleep(1)
'''

def needs_previous_collector(model_path,version,marker):
 if os.environ.get('GITHUB_ACTIONS')!='true' or not Path(model_path).exists() or not Path(marker).exists():return None
 from boat24_model_io import read_json
 try:
  old=read_json(model_path);meta=json.loads(Path(marker).read_text());sha=meta.get('previous_source_commit','')
  if old.get('version')!=version and len(sha)==40 and all(c in 'abcdef0123456789' for c in sha):return sha
 except (OSError,ValueError):pass
 return None

@contextmanager
def preserve_collection_during_rebuild(model_path,version):
 sha=needs_previous_collector(model_path,version,'boat24_full_install.json')
 if not sha:
  yield;return
 root=Path.cwd();child=None;work=None
 with tempfile.TemporaryDirectory(prefix='boat24-model-migration-') as temp:
  temp=Path(temp);stop=temp/'stop';work=temp/'old-source'
  subprocess.run(['git','worktree','add','--detach',str(work),sha],check=True)
  try:
   child=subprocess.Popen(['python','-u','-c',CHILD,str(stop)],cwd=work)
   print('Keeping the previous collector active while the new model is rebuilt',flush=True)
   yield
  finally:
   stop.touch()
   if child:
    try:child.wait(timeout=120)
    except subprocess.TimeoutExpired:
     child.terminate()
     try:child.wait(timeout=15)
     except subprocess.TimeoutExpired:child.kill();child.wait()
   subprocess.run(['git','worktree','remove','--force',str(work)],cwd=root,check=True)
