"""Exercise the real publisher against a local bare remote, including a race."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_boat24 import record

PUBLISH = Path(__file__).resolve().parents[1] / 'boat24_publish.py'


class PublisherTests(unittest.TestCase):
    def test_concurrent_push_retries_without_losing_forecasts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);remote=root/'remote.git';local=root/'local';other=root/'other'
            def git(*args, cwd=None):
                return subprocess.check_output(['git', *map(str,args)],cwd=cwd,text=True,stderr=subprocess.DEVNULL).strip()
            git('init','--bare','--initial-branch=main',remote)
            git('clone',remote,local)
            for repo in [local]:
                git('config','user.name','Test',cwd=repo);git('config','user.email','test@example.com',cwd=repo)
            path='ledger.json';initial={'predictions': {'original':record()}}
            (local/path).write_text(json.dumps(initial));git('add',path,cwd=local);git('commit','-m','seed',cwd=local);git('push','origin','main',cwd=local)
            git('clone',remote,other);git('config','user.name','Test',cwd=other);git('config','user.email','test@example.com',cwd=other)
            # A server hook rejects the first attempted publish, forcing a retry.
            hook=remote/'hooks/pre-receive'
            hook.write_text('#!/bin/sh\nif test ! -f "$GIT_DIR/rejected-once"; then\n touch "$GIT_DIR/rejected-once"\n exit 1\nfi\n')
            hook.chmod(0o755)
            concurrent={'predictions':{'original':record(),'remote-only':record()}}
            (other/path).write_text(json.dumps(concurrent));git('add',path,cwd=other);git('commit','-m','concurrent',cwd=other)
            # Advance the remote before publish; the publisher must also preserve this record.
            hook.unlink();git('push','origin','main',cwd=other)
            hook.write_text('#!/bin/sh\nif test ! -f "$GIT_DIR/rejected-once"; then\n touch "$GIT_DIR/rejected-once"\n exit 1\nfi\n');hook.chmod(0o755)
            (local/path).write_text(json.dumps({'predictions':{'original':record(),'local-only':record()}}))
            result=subprocess.run([sys.executable,str(PUBLISH),path],cwd=local,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            saved=json.loads(git('--git-dir',remote,'show','main:'+path))
            self.assertEqual(set(saved['predictions']),{'original','local-only','remote-only'})
            self.assertIn('attempt 2',result.stdout)
            self.assertEqual(json.loads((local/path).read_text())['predictions']['original'],record())
            self.assertEqual(len(git('worktree','list','--porcelain',cwd=local).split('worktree '))-1,1)
