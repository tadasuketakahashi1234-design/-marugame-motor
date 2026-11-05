import copy,datetime as dt,json,unittest
from unittest.mock import patch
from boat24_integrity import JST
from boat24_risk import robust_plan
from boat24_context import COMBOS
from boat24_decisions import update,report,attach_arms,POLICY
AT=dt.datetime(2026,11,5,12,4,tzinfo=JST);CUT=AT+dt.timedelta(minutes=6);FREEZE=CUT-dt.timedelta(minutes=2);CODE='202611051901'
def plan():
 p={c:0. for c in COMBOS};q={c:10. for c in COMBOS}
 for c in COMBOS[:4]:p[c]=.25
 out=robust_plan(p,q);out['odds_observed_at']=AT.isoformat();return out,p,q

def snapshot(sid='buy',status=None):
 p,probs,q=plan()
 if status:p.update(status=status,tickets=[])
 return {'id':sid,'phase':'preview','evaluation_eligible':True,'created_at':AT.isoformat(),'computed_at':AT.isoformat(),'cutoff':CUT.isoformat(),'model_id':'m','probabilities':probs,'purchase_plan':p,'research':{'baseline':{'probabilities':probs},'candidate':{'probabilities':probs}}}
def view(rec):return {'catalog':{CODE:{'cutoff':CUT.isoformat(),'venue':19,'race':1}},'records':{CODE:copy.deepcopy(rec)}}
def observe(doc,rec,at):return update(doc,view(rec),{CODE:rec},at.isoformat(),{'source_commit':'a'*40,'sha256':'b'*64,'view_url':'https://example.test/view'})
class FrozenDecisions(unittest.TestCase):
 def test_latest_public_skip_replaces_earlier_buy_and_is_immutable(self):
  s=snapshot();r={'revisions':{s['id']:s}};doc=observe({},r,AT+dt.timedelta(seconds=10));later=snapshot('skip','risk_no_positive_value');later['created_at']=(AT+dt.timedelta(minutes=1)).isoformat();later['computed_at']=later['created_at'];r['revisions']['skip']=later
  doc=observe(doc,r,AT+dt.timedelta(minutes=1,seconds=10));doc=observe(doc,r,FREEZE+dt.timedelta(seconds=1));d=copy.deepcopy(doc['records'][CODE]['decision']);self.assertEqual(d['state'],'skip');self.assertEqual(d['snapshot_id'],'skip')
  newest=snapshot('late');newest['created_at']=(FREEZE-dt.timedelta(seconds=1)).isoformat();newest['computed_at']=newest['created_at'];r['revisions']['late']=newest
  doc=observe(doc,r,FREEZE+dt.timedelta(seconds=20));self.assertEqual(doc['records'][CODE]['decision'],d)
 def test_unobserved_newer_snapshot_never_selected(self):
  s=snapshot();r={'revisions':{'buy':s}};doc=observe({},r,AT+dt.timedelta(seconds=10));late=snapshot('late');late['created_at']=(AT+dt.timedelta(minutes=1)).isoformat();late['computed_at']=late['created_at'];r['revisions']['late']=late
  doc=observe(doc,r,FREEZE+dt.timedelta(seconds=1));self.assertEqual(doc['records'][CODE]['decision']['snapshot_id'],'buy')
 def test_past_data_never_backdated_into_prospective_cohort(self):
  r={'revisions':{'buy':snapshot()}};doc=observe({},r,FREEZE+dt.timedelta(seconds=1));self.assertEqual(doc['records'][CODE]['decision']['state'],'historical_unverified');self.assertFalse(doc['records'][CODE]['receipts'])
 def test_missing_publication_after_start_is_counted(self):
  doc={'protocol':{'id':POLICY,'started_at':AT.isoformat()},'records':{}};r={'revisions':{'buy':snapshot()}};doc=observe(doc,r,FREEZE+dt.timedelta(seconds=1));self.assertEqual(doc['records'][CODE]['decision']['state'],'unavailable')
 def test_quote_expiring_before_freeze_is_pending_even_for_skip(self):
  s=snapshot(status='risk_no_positive_value');s['purchase_plan']['odds_observed_at']=(AT-dt.timedelta(minutes=2)).isoformat();r={'revisions':{'buy':s}};doc=observe({},r,AT+dt.timedelta(seconds=10));doc=observe(doc,r,FREEZE);self.assertEqual(doc['records'][CODE]['decision']['reason'],'quote_expired_at_freeze')
 def test_exact_freeze_publication_is_too_late(self):
  r={'revisions':{'buy':snapshot()}};doc={'protocol':{'id':POLICY,'started_at':AT.isoformat()},'records':{}};doc=observe(doc,r,FREEZE);self.assertEqual(doc['records'][CODE]['decision']['state'],'unavailable')
 def test_public_payload_mismatch_produces_no_receipt(self):
  r={'revisions':{'buy':snapshot()}};v=view(r);v['records'][CODE]['revisions']['buy']['purchase_plan']['budget']+=100
  doc=update({},v,{CODE:r},(AT+dt.timedelta(seconds=10)).isoformat(),{});self.assertFalse(doc['records'][CODE]['receipts'])
 def test_result_settlement_does_not_change_fixed_decision_or_archive(self):
  s=snapshot();r={'revisions':{'buy':s}};doc=observe({},r,AT+dt.timedelta(seconds=10));doc=observe(doc,r,FREEZE);fixed=copy.deepcopy(doc['records'][CODE]['decision']);r['result']={'id':'res','combo':COMBOS[0],'payout_100yen':900,'refund_verified':True,'refund_boats':[]};original=copy.deepcopy(r)
  doc=observe(doc,r,CUT+dt.timedelta(minutes=10));self.assertEqual(r,original);self.assertEqual(doc['records'][CODE]['decision'],fixed);self.assertEqual(doc['records'][CODE]['settlement']['actual_rule']['profit'],500);self.assertEqual(report(doc)['model_rows'][0]['races'],1)
  r['result'].update(id='correction',payout_100yen=300);doc=observe(doc,r,CUT+dt.timedelta(minutes=11));self.assertEqual(doc['records'][CODE]['decision'],fixed);self.assertEqual(report(doc)['model_rows'][0]['gami'],1)
 def test_unverified_refund_does_not_create_final_profit(self):
  r={'revisions':{'buy':snapshot()}};doc=observe({},r,AT+dt.timedelta(seconds=10));r['result']={'id':'r','combo':COMBOS[0],'payout_100yen':900,'refund_verified':False};doc=observe(doc,r,CUT);self.assertNotIn('actual_rule',doc['records'][CODE]['settlement']);self.assertFalse(report(doc)['model_rows'])
 def test_candidate_arms_saved_before_result_with_same_controls(self):
  s=snapshot();_,_,q=plan();attach_arms(s,q,True);arms=s['research']['decision_arms']['arms'];self.assertEqual(set(arms),{'baseline','candidate'});self.assertEqual(arms['baseline']['plan']['risk_controls'],arms['candidate']['plan']['risk_controls'])
  r={'revisions':{'buy':s}};doc=observe({},r,AT+dt.timedelta(seconds=10));r['result']={'id':'r','combo':COMBOS[0],'payout_100yen':900,'refund_verified':True};doc=observe(doc,r,CUT);p=report(doc)['paired_rows'];self.assertEqual(p['baseline']['comparable_races'],p['candidate']['comparable_races']);self.assertEqual(p['baseline']['return'],p['candidate']['return'])
 def test_repeated_display_gets_new_receipt_without_rewriting_old(self):
  r={'revisions':{'buy':snapshot()}};doc=observe({},r,AT+dt.timedelta(seconds=10));old=copy.deepcopy(doc['records'][CODE]['receipts']);doc=observe(doc,r,AT+dt.timedelta(seconds=20));self.assertEqual(len(doc['records'][CODE]['receipts']),2)
  for k,v in old.items():self.assertEqual(doc['records'][CODE]['receipts'][k],v)

class PublicReceiptPublisher(unittest.TestCase):
 def test_public_payload_digest_and_receipt_are_committed_to_bare_remote(self):
  import subprocess,tempfile,hashlib,types
  from pathlib import Path
  import boat24_public_receipts as pub
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);remote=root/'remote.git';local=root/'local'
   def git(*a,cwd=None):return subprocess.check_output(['git',*map(str,a)],cwd=cwd,text=True,stderr=subprocess.DEVNULL).strip()
   git('init','--bare','--initial-branch=main',remote);git('clone',remote,local);git('config','user.name','Test',cwd=local);git('config','user.email','test@example.com',cwd=local)
   docs=local/'omura/docs';(docs/'full_history').mkdir(parents=True);(docs/'day_views').mkdir();rec={'race_code':CODE,'revisions':{'buy':snapshot()}};v=view(rec);raw=json.dumps(v).encode();h=hashlib.sha256(raw).hexdigest();viewpath='day_views/2026-11-05-'+h[:16]+'.json';(docs/viewpath).write_bytes(raw)
   (docs/'full_history/2026-11-05.json').write_text(json.dumps({'catalog':v['catalog'],'records':{CODE:rec}}))
   index={'days':{'2026-11-05':{'view_path':viewpath,'view_sha256':h,'archive_path':'full_history/2026-11-05.json'}},'updated_at':AT.isoformat()};(docs/'boat24_full_index.json').write_text(json.dumps(index));git('add','.',cwd=local);git('commit','-m','published view',cwd=local);git('push','origin','main',cwd=local)
   actual=pub.git
   def observed_git(*args,cwd):
    if args[:3]==('remote','get-url','origin'):return 'https://github.com/tadasuketakahashi1234-design/-marugame-motor.git'
    return actual(*args,cwd=cwd)
   class Clock(dt.datetime):
    @classmethod
    def now(cls,tz=None):return AT+dt.timedelta(seconds=10)
   calls=[]
   def download(url):calls.append(url);return json.dumps(index).encode() if 'boat24_full_index.json' in url else raw
   with patch.object(pub,'git',side_effect=observed_git),patch.object(pub,'download',side_effect=download),patch.object(pub,'dt',types.SimpleNamespace(datetime=Clock)):pub.publish(local)
   saved=json.loads(git('--git-dir',remote,'show','main:omura/docs/boat24_decisions.json'));self.assertEqual(len(saved['records'][CODE]['receipts']),1);receipt=next(iter(saved['records'][CODE]['receipts'].values()));self.assertEqual(receipt['proof']['sha256'],h);self.assertEqual(receipt['observed_at'],(AT+dt.timedelta(seconds=10)).isoformat());self.assertTrue(any('main/omura/docs/boat24_full_index.json' in u for u in calls))
   updated=json.loads(git('--git-dir',remote,'show','main:omura/docs/boat24_full_index.json'));self.assertEqual(updated['decision_report']['counts']['awaiting_freeze'],1)
