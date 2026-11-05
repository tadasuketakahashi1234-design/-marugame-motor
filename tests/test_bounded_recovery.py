import datetime as dt,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import boat24_recover as recover

class BoundedRecovery(unittest.TestCase):
 def test_unchanged_day_does_not_rewrite_views_statistics_or_publish(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);p=root/'full_history/2026-11-05.json';p.parent.mkdir();views=root/'day_views';views.mkdir();(views/'2026-11-05.pointer.json').write_text('{}')
   day={'records':{'code':{'offers':{'x':{}},'revisions':{}}}}
   with patch.object(recover,'DIRECTORY',p.parent),patch.object(recover,'register_offers',return_value=[]),patch.object(recover,'settle',return_value=False),patch.object(recover,'write_history') as write,patch.object(recover,'write_view') as view,patch.object(recover,'build_index') as stats,patch('boat24_full_publish.main') as pub:
    recover.publish([(p,day)],{}, {},{},'storage_and_saved_offers')
   write.assert_not_called();view.assert_not_called();stats.assert_not_called();pub.assert_not_called()

 def test_missing_view_still_restores_and_publishes(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);p=root/'full_history/2026-11-05.json';p.parent.mkdir();index=root/'index.json';manifest=root/'manifest.json'
   with patch.object(recover,'DIRECTORY',p.parent),patch.object(recover,'INDEX',index),patch.object(recover,'MANIFEST',manifest),patch.object(recover,'CACHE',root/'absent.json'),patch.object(recover,'write_history',return_value=p) as write,patch.object(recover,'write_view') as view,patch.object(recover,'build_index',return_value={'model':'test'}),patch('boat24_full_publish.main') as pub:
    recover.publish([(p,{'records':{}})],{}, {},{},'storage_and_saved_offers')
   write.assert_called_once();view.assert_called_once();pub.assert_called_once()

 def test_startup_today_only_does_not_read_old_archives(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);today=dt.datetime.now(recover.JST).date();a=root/(today.isoformat()+'.json');b=root/((today-dt.timedelta(days=1)).isoformat()+'.json')
   with patch.object(recover,'DIRECTORY',root),patch.object(recover,'day_paths',return_value=[b,a]),patch.object(recover,'read_history',return_value={'records':{}}) as read,patch.object(recover,'publish'),patch.object(recover,'collect_results',return_value=({},{})):
    recover.main(today_only=True)
   read.assert_called_once_with(a)

 def test_changed_record_is_the_only_dirty_shard(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);p=root/'full_history/2026-11-05.json';p.parent.mkdir();(root/'day_views').mkdir();(root/'day_views/2026-11-05.pointer.json').write_text('{}')
   with patch.object(recover,'DIRECTORY',p.parent),patch.object(recover,'INDEX',root/'index.json'),patch.object(recover,'MANIFEST',root/'manifest.json'),patch.object(recover,'CACHE',root/'none'),patch.object(recover,'register_offers',return_value=[]),patch.object(recover,'settle',side_effect=[False,True]),patch.object(recover,'write_history',return_value=p) as write,patch.object(recover,'write_view'),patch.object(recover,'build_index',return_value={'model':'test'}),patch('boat24_full_publish.main'):
    recover.publish([(p,{'records':{'old':{},'changed':{}}})],{}, {},{},'official_settlements')
   self.assertEqual(write.call_args.kwargs['changed_codes'],{'changed'})
