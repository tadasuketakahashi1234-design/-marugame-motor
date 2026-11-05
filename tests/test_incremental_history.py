import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from boat24_history_io import write_history,read_history
from boat24_model_io import write_json
class IncrementalHistory(unittest.TestCase):
 def test_only_changed_record_is_recompressed_and_archive_bytes_are_identical(self):
  records={f'2026110519{i:02d}':{'race_code':f'2026110519{i:02d}','revisions':{'s':{'data':'same'*200}}} for i in (1,2)};old={'records':records};new=copy.deepcopy(old);new['records']['202611051901']['revisions']['new']={'data':'added'}
  with tempfile.TemporaryDirectory() as tmp:
   a=Path(tmp)/'incremental';b=Path(tmp)/'baseline';a.mkdir();b.mkdir()
   for d in (a,b):(d/'2026-11-05').mkdir();write_history(d/'2026-11-05.json',old)
   with patch('boat24_history_io.write_json',wraps=write_json) as save:write_history(a/'2026-11-05.json',new,previous=old)
   self.assertEqual(save.call_count,2)
   write_history(b/'2026-11-05.json',new)
   for f in a.rglob('*'):
    if f.is_file():self.assertEqual(f.read_bytes(),(b/f.relative_to(a)).read_bytes())
   self.assertEqual(read_history(a/'2026-11-05.json'),new)
 def test_dirty_set_keeps_new_records_and_metadata(self):
  old={'records':{'202611051901':{'race_code':'202611051901','revisions':{}}}}
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'2026-11-05.json';(p.parent/'2026-11-05').mkdir();write_history(p,old);new=copy.deepcopy(old);new['health']={'at':'new'};new['records']['202611051902']={'race_code':'202611051902','revisions':{'x':{}}}
   with patch('boat24_history_io.write_json',wraps=write_json) as save:write_history(p,new,changed_codes=set())
   self.assertEqual(save.call_count,2);self.assertEqual(read_history(p),new)

 def test_legacy_fork_revisions_are_materialized_even_with_empty_dirty_set(self):
  from boat24_model_io import read_json
  code='202611051901';old={'records':{code:{'race_code':code,'revisions':{'old':{}}}}}
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'2026-11-05.json';(p.parent/'2026-11-05').mkdir();write_history(p,old)
   fork=copy.deepcopy(old);fork['records'][code]['revisions']['legacy']={};write_json(Path(str(p)+'.gz'),fork)
   merged=read_history(p);write_history(p,merged,previous=merged,changed_codes=set())
   shard=read_json(p.parent/'2026-11-05'/('202611051901.json.gz'));self.assertIn('legacy',shard['revisions'])

 def test_legacy_gzip_with_stale_orphan_shards_is_not_skipped(self):
  from boat24_model_io import read_json
  code='202611051901';old={'records':{code:{'race_code':code,'revisions':{'old':{}}}}}
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'2026-11-05.json';(p.parent/'2026-11-05').mkdir();write_history(p,old);p.unlink()
   new=copy.deepcopy(old);new['records'][code]['revisions']['new']={};zipped=Path(str(p)+'.gz');write_json(zipped,new)
   write_history(zipped,new,previous=new,changed_codes=set());self.assertIn('new',read_json(p.parent/'2026-11-05'/(code+'.json.gz'))['revisions'])
