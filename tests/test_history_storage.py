import copy
import datetime as dt
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from boat24_history_io import day_paths,day_key,read_history,write_history,compact_day
from boat24_model_io import write_json
from boat24_replay import load_observations

DAY='2026-11-03';CODE='202611031901'
def snapshot(key,minute):
    at=f'{DAY}T17:{minute:02d}:00+09:00'
    return {'id':key,'created_at':at,'cutoff':f'{DAY}T18:00:00+09:00','phase':'preview','evaluation_eligible':True,
            'input_snapshot':{'captured_at':at,'features':[{} for _ in range(6)],'source_times':{'ex':at}},'selection':{'12':['1-2-3']}}
def document():
    return {'date':DAY,'updated_at':DAY+'T17:20:00+09:00','records':{CODE:{'race_code':CODE,'venue':19,'date':DAY,'race':1,'revisions':{'old':snapshot('old',10),'new':snapshot('new',20)}}}}

class HistoryStorage(unittest.TestCase):
    def test_migration_preserves_every_revision_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/(DAY+'.json');doc=document();write_json(p,doc)
            with patch('boat24_history_io.COMPRESS_AFTER_BYTES',1):z=write_history(p,doc)
            self.assertTrue(p.exists());self.assertEqual(z.name,DAY+'.json');self.assertEqual(json.loads(p.read_text())['history_storage']['schema'],2)
            self.assertEqual(read_history(z),doc);self.assertEqual(day_paths(tmp),[z]);self.assertEqual(day_key(z),DAY)
            selected,_=load_observations(dt.date(2026,11,4),directory=Path(tmp));self.assertEqual(selected[(CODE,'preview')]['id'],'new')

    def test_light_view_does_not_rewrite_archived_inputs(self):
        doc=document();original=copy.deepcopy(doc)
        for i in range(30):doc['records'][CODE]['revisions'][str(i)]=snapshot(str(i),i)
        before=copy.deepcopy(doc);view=compact_day(doc);record=view['records'][CODE]
        self.assertEqual(doc,before);self.assertEqual(record['revision_count'],32)
        self.assertLess(len(record['revisions']),len(doc['records'][CODE]['revisions']))
        self.assertEqual(len(record['revision_history']),32)

    def test_many_offers_do_not_copy_every_large_input_into_view(self):
        doc=document();record=doc['records'][CODE];record['offers']={}
        for i in range(30):
            key=str(i);record['revisions'][key]=snapshot(key,i)
            record['offers'][key]={'snapshot_id':key,'created_at':record['revisions'][key]['created_at'],'tickets':[{'combo':'1-2-3','stake':100}]}
        view=compact_day(doc)['records'][CODE]
        self.assertEqual(len(view['offers']),30)
        self.assertLessEqual(len(view['revisions']),3)
        self.assertIn('0',view['revisions'])

    def test_sharded_manifest_and_legacy_gzip_are_both_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/(DAY+'.json');doc=document()
            with patch('boat24_history_io.COMPRESS_AFTER_BYTES',1):write_history(p,doc)
            legacy=copy.deepcopy(doc);legacy['records'][CODE]['revisions']={'extra':snapshot('extra',30)}
            legacy['updated_at']=DAY+'T17:30:00+09:00';write_json(str(p)+'.gz',legacy)
            self.assertEqual(set(read_history(str(p)+'.gz')['records'][CODE]['revisions']),{'old','new','extra'})

    def test_quote_only_update_gets_an_immutable_public_url(self):
        import hashlib
        from boat24_history_io import write_view
        from boat24_full_update import build_index
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)/'full_history';path=directory/(DAY+'.json');doc=document()
            write_history(path,doc);write_view(path,doc)
            first=build_index(directory)['days'][DAY]
            self.assertNotEqual(first['view_path'],'day_views/'+DAY+'.json')
            first_file=Path(tmp)/first['view_path'];before=first_file.read_bytes()
            self.assertEqual(hashlib.sha256(before).hexdigest(),first['view_sha256'])
            doc['quote_health']={'attempt_at':DAY+'T17:21:00+09:00'}
            write_history(path,doc);write_view(path,doc)
            second=build_index(directory)['days'][DAY]
            self.assertNotEqual(first['view_path'],second['view_path'])
            self.assertEqual(first_file.read_bytes(),before)
            self.assertEqual(json.loads((Path(tmp)/second['view_path']).read_text())['quote_health'],doc['quote_health'])

    def test_publisher_replaces_large_plain_file_with_archive_and_view(self):
        from boat24_full_publish import main,git as actual_git
        def run(*args,cwd):return subprocess.check_output(['git',*args],cwd=cwd,text=True,stderr=subprocess.DEVNULL).strip()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);remote=root/'remote.git';local=root/'local'
            run('init','--bare','--initial-branch=main',str(remote),cwd=root)
            run('clone',str(remote),str(local),cwd=root)
            run('config','user.name','Test',cwd=local);run('config','user.email','test@example.com',cwd=local)
            history='omura/docs/full_history/'+DAY+'.json';index='omura/docs/boat24_full_index.json'
            doc=document();old=copy.deepcopy(doc);old['records'][CODE]['revisions'].pop('new')
            write_json(local/history,old);write_json(local/index,{})
            run('add','.',cwd=local);run('commit','-m','original immutable history',cwd=local);run('push','origin','main',cwd=local)
            write_json(local/(history+'.gz'),doc)
            manifest=local/'boat24_full_pending.json';write_json(manifest,{'paths':[history+'.gz'],'index':index})
            with patch('boat24_full_publish.MANIFEST',Path('boat24_full_pending.json')),patch('boat24_history_io.COMPRESS_AFTER_BYTES',1),patch('boat24_full_publish.git',side_effect=lambda *args,cwd=None:actual_git(*args,cwd=cwd or local)):
                main()
            run('fetch','origin','main',cwd=local)
            archived=run('ls-tree','-r','--name-only','origin/main',cwd=local).splitlines()
            self.assertIn(history,archived);self.assertIn('omura/docs/full_history/'+DAY+'/'+CODE+'.json.gz',archived)
            self.assertIn('omura/docs/day_views/'+DAY+'.json',archived)
            raw=subprocess.check_output(['git','show','origin/main:omura/docs/full_history/'+DAY+'/'+CODE+'.json.gz'],cwd=local)
            import gzip
            restored=json.loads(gzip.decompress(raw));self.assertEqual(restored['revisions'],doc['records'][CODE]['revisions'])

if __name__=='__main__':unittest.main()
