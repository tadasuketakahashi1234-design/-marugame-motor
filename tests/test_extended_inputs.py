import copy,datetime as dt,unittest
from boat24_course import CourseStats,add_course_features
from boat24_official import parse_comments,parse_before,parse_tides,comment_signals,tide_features,attach,merge_cache
from boat24_context import predict,COMBOS,GROUPS,ALL_GROUPS,scales
from boat24_integrity import JST

CODE='202611031501'
def data(course_swap=False,method='逃げ'):
 card={f'艇{i}_登録番号':str(4000+i) for i in range(1,7)}
 res={'取得日時':'2026-11-02T18:00:00+09:00','決まり手':method}
 for i in range(1,7):
  res[f'{i}着_艇番']=str(i);res[f'{i}コース_艇番']=str(7-i if course_swap else i);res[f'{i}コース_スタートタイミング']=str(.1+i*.01)
 return {'cards':{'202611021501':card},'results':{'202611021501':res}}
class ExtendedTests(unittest.TestCase):
 def test_real_course_not_boat_number(self):
  d=data(True);s=CourseStats();s.add(d)
  f,style=s.features('4001',15,6);self.assertEqual(f['1着率'],1);self.assertEqual(s.features('4001',15,1),({},{}));self.assertGreater(style['逃げ勝ち率'],0)
 def test_shrinkage_small_samples(self):
  s=CourseStats();d=data();s.add(d)
  # Another racer loses from the same actual course; one win must not imply certainty.
  d['cards']['202611021501']['艇1_登録番号']='4999';d['results']['202611021501']['1着_艇番']='2';d['results']['202611021501']['2着_艇番']='1';s.add(d)
  f,_=s.features('4001',15,1);self.assertGreater(f['1着率'],.5);self.assertLess(f['1着率'],1)
 def test_late_result_observation_excluded(self):
  d=data();d['results']['202611021501']['取得日時']='2026-11-03T18:00:00+09:00';s=CourseStats();s.add(d);self.assertFalse(s.state['racer'])
 def test_missing_course_not_fabricated(self):
  d=data();d['results']['202611021501'].pop('6コース_艇番');s=CourseStats();s.add(d);self.assertFalse(s.state['racer'])
 def test_course_features_follow_exhibition_and_adjacent_opponents(self):
  d=data();s=CourseStats();s.add(d);f=[{g:{} for g in ALL_GROUPS} for _ in range(6)];f[0]['start']['展示進入']=2
  add_course_features(f,d['cards']['202611021501'],15,s);self.assertFalse(f[0]['course']);self.assertIn('平均ST',f[1]['course'])
 def test_comment_negation_and_uncertainty(self):
  self.assertLess(comment_signals('良くない'),0);self.assertGreater(comment_signals('悪くない'),0);self.assertGreater(comment_signals('悪くはない'),0);self.assertEqual(comment_signals('良いかどうか分からない'),0);self.assertEqual(comment_signals('伸びが良い。出足は弱い'),0)
 def test_tide_date_and_phase_no_extrapolation(self):
  doc='<div class="ym">2026.12.</div><tr><td>1/ 2</td><td>初日</td><td>18:58</td><td>11:42</td><td>小潮</td></tr>'
  rows=parse_tides(doc);self.assertIn('2027-01-02',rows);self.assertFalse(parse_tides(doc.replace('class="ym"','class="unknown"')))
  row=rows['2027-01-02'];f=tide_features(row,dt.datetime(2027,1,2,16,tzinfo=JST));self.assertEqual(f['上げ潮'],1)
  self.assertNotIn('上げ潮',tide_features(row,dt.datetime(2027,1,2,22,tzinfo=JST)))
 def test_comments_date_and_all_racer_ids_required(self):
  card={f'艇{i}_登録番号':str(4000+i) for i in range(1,7)}
  rows=''.join(f'<tbody><tr><td>{i}</td><td><a href="x?toban={4000+i}">名</a></td><td>悪くない</td></tr></tbody>' for i in range(1,7))
  doc='<iframe src="x?raceDate=20261103&raceNumber=1&x=1"></iframe><table><th>選手コメント</th>'+rows+'</table>'
  self.assertEqual(len(parse_comments(doc,CODE,card)),6);self.assertFalse(parse_comments(doc.replace('raceDate=20261103','raceDate=20261102'),CODE,card));card['艇6_登録番号']='9999';self.assertFalse(parse_comments(doc,CODE,card))
 def test_before_requires_selected_race_date_and_racer(self):
  card={f'艇{i}_登録番号':str(4000+i) for i in range(1,7)}
  head='<a href="x?hd=20261103"></a><li class="is-active2">11月3日</li><tr><td>締切予定時刻</td>'+''.join('<td class="'+('is-activeColor1' if i==1 else '')+'">15:22</td>' for i in range(1,13))+'</tr>'
  bodies=''.join(f'<tbody><tr><td class="is-boatColor{i}">{i}</td><td><a href="x?toban={4000+i}">写真</a></td><td>名前</td><td>52</td><td>6.8</td><td>0</td><td>新</td><td>リング×2</td></tr></tbody>' for i in range(1,7))
  doc=head+bodies;self.assertEqual(len(parse_before(doc,CODE,card)),6);self.assertFalse(parse_before(doc,CODE[:-1]+'2',card));self.assertFalse(parse_before(doc.replace('11月3日','11月2日'),CODE,card))
 def test_late_official_inputs_are_not_used(self):
  f=[{g:{} for g in ALL_GROUPS} for _ in range(6)];cache={'tide_observed_at':'2026-11-03T17:00:00+09:00','tides':{'2026-11-03':{'high':'18:58','low':'11:42','cycle':'小潮'}},'races':{CODE:{'observed_at':'2026-11-03T17:00:00+09:00','before':{'1':{'propeller':'新','parts':'リング'}},'comments':{'1':{'comment':'伸びが良い'}}}}}
  attach(f,CODE,dt.datetime(2026,11,3,16,tzinfo=JST),cache)
  self.assertFalse(f[0]['tide']);self.assertFalse(f[0]['maintenance']);self.assertFalse(f[0]['comments'])
 def test_unlearned_supplemental_rules_do_not_change_probabilities(self):
  samples=[]
  for lane in range(1,7):
   for n in range(10):samples.append({'venue':15,'course':lane,'lane':lane,'date':'2026-10-25','code':str(n),'finish':lane,'features':{g:{'x':1} for g in GROUPS}})
  m={'samples':samples,'scales':scales(samples),'market_alpha':.25};f=[{g:{'x':1} for g in GROUPS} for _ in range(6)]
  base=predict(f,15,'2026-11-03',m)['probabilities']
  for group,field,value in [('comments','コメント気配',1),('tide','上げ潮',1),('maintenance','部品交換あり',1),('wind','向かい風成分',5)]:
   with self.subTest(group=group):
    changed=copy.deepcopy(f);changed[0][group]={field:value};p=predict(changed,15,'2026-11-03',m)
    self.assertEqual(base,p['probabilities']);self.assertNotIn(field,p['feature_usage'][group]['used_fields']);self.assertFalse(p['neighbour_evidence'][0]['research_rules'])

 def test_official_cache_merge_keeps_both_races_and_newer_observation(self):
  a={'date':'2026-11-03','updated_at':'2026-11-03T12:00:00+09:00','races':{'a':{'observed_at':'12:00','v':1}}}
  b={'date':'2026-11-03','updated_at':'2026-11-03T12:01:00+09:00','races':{'a':{'observed_at':'11:00','v':0},'b':{'observed_at':'12:01','v':2}}}
  m=merge_cache(a,b);self.assertEqual(set(m['races']),{'a','b'});self.assertEqual(m['races']['a']['v'],1);self.assertEqual(a['races']['a']['v'],1)

 def test_refund_race_is_not_falsely_settled_as_normal_stakes(self):
  from boat24_full_update import settle,summary
  rec={'race_code':CODE,'revisions':{},'result':None}
  res={'レースコード':CODE,'1コース_F':'F'};pay={'レースコード':CODE}
  self.assertFalse(settle(rec,res,pay,dt.datetime(2026,11,3,16,tzinfo=JST)));self.assertIn('集計対象外',rec['result_pending_reason']);self.assertEqual(summary([rec])['excluded_refund'],1)

 def test_compressed_model_roundtrip_and_deterministic_bytes(self):
  import tempfile
  from pathlib import Path
  from boat24_model_io import read_json,write_json
  with tempfile.TemporaryDirectory() as d:
   a=Path(d)/'a.json.gz';b=Path(d)/'b.json.gz';value={'日本語':[1,2,3]}
   write_json(a,value);write_json(b,value);self.assertEqual(read_json(a),value);self.assertEqual(a.read_bytes(),b.read_bytes())
