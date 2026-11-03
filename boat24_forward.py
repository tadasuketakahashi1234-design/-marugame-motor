"""Same-race, pre-deadline comparison. Immutable saved probabilities only."""
import math
from collections import defaultdict
from boat24_integrity import eligible, timeparse

def build_report(records,legacy=None):
 from boat24_full_update import latest
 buckets=defaultdict(list);unmatched=0
 for rec in records:
  result=rec.get('result');snap=rec.get('revisions',{}).get((result or {}).get('selection_snapshot_id')) or latest(rec)
  if not result or not snap or not snap.get('probabilities'):continue
  actual=result['combo'];payout=result['payout_100yen'];old=(legacy or {}).get('predictions',{}).get(rec['race_code']);baseline=snap.get('market_baseline')
  models={'new':{'probabilities':snap['probabilities'],'picks':snap['selection']['12']}}
  # The old snapshot must be genuinely pre-deadline; its different creation time is disclosed.
  if old and eligible(old):models['old']={'probabilities':old.get('probabilities',{}),'picks':old.get('selection',{}).get('12',[])}
  if baseline:models['market']=baseline
  if len(models)!=3:unmatched+=1
  ctx=snap.get('input_snapshot',{}).get('race_context',{});winner=int(actual.split('-')[0]);features=snap.get('input_snapshot',{}).get('features',[]);course=(features[winner-1].get('start',{}).get('展示進入',winner) if len(features)==6 else winner)
  groups=['all',f"date:{rec['date']}",f"venue:{rec['venue']}",f"field:{ctx.get('field_type','unknown')}",f"phase:{snap.get('phase','legacy')}",f"version:{snap.get('model','unknown')}",f'predicted_winner_entry:{course}']
  for group in groups:
   for name,m in models.items():
    picks=m['picks'];probs=m.get('probabilities',{});hit=actual in picks;stake=100*len(picks)
    buckets[(group,name,'available')].append((hit,stake,payout if hit else 0,-math.log(max(probs.get(actual,0),1e-12)) if probs else None))
    if len(models)==3:buckets[(group,name,'same_races')].append((hit,stake,payout if hit else 0,-math.log(max(probs.get(actual,0),1e-12)) if probs else None))
   allocation=snap.get('allocation',{}).get('tickets',[])
   if allocation:
    stake=sum(t['stake'] for t in allocation);returns=sum(t['stake']/100*payout for t in allocation if t['combo']==actual)
    buckets[(group,'allocated_paper','available')].append((returns>0,stake,returns,None))
 out=[]
 for (group,model,cohort),rows in sorted(buckets.items()):
  n=len(rows);hits=sum(r[0] for r in rows);stake=sum(r[1] for r in rows);returns=sum(r[2] for r in rows);losses=[r[3] for r in rows if r[3] is not None];rate=hits/n;z=1.96;den=1+z*z/n;center=(rate+z*z/(2*n))/den;margin=z*math.sqrt(rate*(1-rate)/n+z*z/(4*n*n))/den
  out.append({'group':group,'model':model,'cohort':cohort,'races':n,'hits':hits,'hit_rate':rate,'hit_rate_interval95':[max(0,center-margin),min(1,center+margin)],'stake':stake,'return':returns,'profit':returns-stake,'roi':returns/stake if stake else None,'logloss':sum(losses)/len(losses) if losses else None})
 return {'rows':out,'not_three_way_matched':unmatched,'comparison_note':'Same race and pre-deadline snapshots; old/new creation times differ. Market is captured with the new snapshot. No morning-market comparison is claimed when morning odds were unavailable. Winner-entry group uses the predicted exhibition course, not post-result actual entry. All allocations are paper only.'}
