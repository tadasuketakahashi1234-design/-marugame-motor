import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from boat24_history_io import write_history,read_history

class PublicationConcurrencyTests(unittest.TestCase):
 def git(self,*args,cwd):return subprocess.check_output(['git',*args],cwd=cwd,text=True,stderr=subprocess.DEVNULL).strip()
 def init(self,p):
  p.mkdir();self.git('init','--initial-branch=main',cwd=p);self.git('config','user.name','Test',cwd=p);self.git('config','user.email','test@example.com',cwd=p)
  (p/'README').write_text('fixture');self.git('add','README',cwd=p);self.git('commit','-m','fixture',cwd=p)
 def test_two_worktrees_share_one_publication_lock(self):
  import boat24_full_publish as pub
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);root=p/'main';other=p/'worker';self.init(root);self.git('worktree','add','--detach',str(other),'HEAD',cwd=root)
   actual_git=pub.git;barrier=threading.Barrier(2);counter=threading.Lock();active=peak=0;errors=[]
   def git(*args,cwd=None):return actual_git(*args,cwd=cwd or (root if threading.current_thread().name=='main-writer' else other))
   def critical():
    nonlocal active,peak
    with counter:active+=1;peak=max(peak,active)
    time.sleep(.15)
    with counter:active-=1
   def runner():
    try:barrier.wait();pub.main()
    except Exception as exc:errors.append(exc)
   with patch.object(pub,'git',side_effect=git),patch.object(pub,'_publish',side_effect=critical):
    threads=[threading.Thread(target=runner,name=n) for n in ('main-writer','quote-writer')]
    for t in threads:t.start()
    for t in threads:t.join(timeout=10)
   self.assertEqual(errors,[]);self.assertEqual(peak,1);self.assertTrue(all(not t.is_alive() for t in threads))
 def test_fetch_updates_tracking_ref_when_checkout_has_no_default_fetch_mapping(self):
  import boat24_full_publish as pub
  from test_history_storage import document,DAY,CODE,snapshot
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);remote=p/'remote.git';local=p/'local';other=p/'other'
   self.git('init','--bare','--initial-branch=main',str(remote),cwd=p);self.git('clone',str(remote),str(local),cwd=p)
   self.git('config','user.name','Test',cwd=local);self.git('config','user.email','test@example.com',cwd=local)
   history='omura/docs/full_history/'+DAY+'.json';index='omura/docs/boat24_full_index.json'
   doc=document();old=copy.deepcopy(doc);old['records'][CODE]['revisions'].pop('new')
   write_history(local/history,old);(local/index).write_text('{}');self.git('add','.',cwd=local);self.git('commit','-m','old',cwd=local);self.git('push','origin','main',cwd=local)
   self.git('clone',str(remote),str(other),cwd=p);self.git('config','user.name','Test',cwd=other);self.git('config','user.email','test@example.com',cwd=other)
   advanced=copy.deepcopy(old);advanced['records'][CODE]['revisions']['remote']=snapshot('remote',15);write_history(other/history,advanced)
   self.git('add','.',cwd=other);self.git('commit','-m','concurrent observation',cwd=other);self.git('push','origin','main',cwd=other)
   self.git('config','--unset-all','remote.origin.fetch',cwd=local)
   write_history(local/history,doc);(local/'boat24_full_pending.json').write_text(json.dumps({'paths':[history],'index':index}))
   actual_git=pub.git
   with patch.object(pub,'MANIFEST',Path('boat24_full_pending.json')),patch.object(pub,'git',side_effect=lambda *args,cwd=None:actual_git(*args,cwd=cwd or local)):
    pub.main()
   raw=self.git('show','main:'+history,cwd=remote);merged=json.loads(raw)
   self.assertEqual(set(merged['records'][CODE]['revisions']),{'old','remote','new'})

if __name__=='__main__':unittest.main()
