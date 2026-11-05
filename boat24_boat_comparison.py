"""Small six-column comparison from saved inputs, never inferred missing facts."""
from boat24_context import number
from boat24_integrity import timeparse

def build(s,records=None):
 raw=s.get('input_snapshot') or {};fs=raw.get('features') or [];card=raw.get('card') or {};ids={int(x['lane']):x for x in s.get('boat_identities',[]) if x.get('lane')};support={r['lane']:r for r in s.get('race_reasoning',{}).get('support',[])};at=timeparse(s.get('computed_at') or s.get('created_at'));code=s.get('race_code') or card.get('レースコード') or '';boats=[]
 for lane in range(1,7):
  f=fs[lane-1] if len(fs)>=lane else {};ident=ids.get(lane,{});rid=str(ident.get('racer') or card.get(f'艇{lane}_登録番号') or '');course=f.get('start',{}).get('展示進入');stats=f.get('course') or {};series=[]
  for rec in (records or {}).values():
   oldcode=rec.get('race_code','');result=rec.get('result') or {};rt=timeparse(result.get('settled_at'));source=result.get('result_source') or {}
   if not at or not rt or rt>at or not code or oldcode>=code or oldcode[:10]!=code[:10]:continue
   revisions=rec.get('revisions') or {};old=next(iter(revisions.values()),{});oldids=old.get('boat_identities',[]);ol=next((b.get('lane') for b in oldids if str(b.get('racer'))==rid and rid),None)
   if ol is None:continue
   actual=next((i for i in range(1,7) if str(source.get(f'{i}コース_艇番'))==str(ol)),None)
   if actual is None:continue
   value=number(source.get(f'{actual}コース_スタートタイミング'))
   if value is None or not -1<=value<=1:continue
   series.append({'race':int(oldcode[-2:]),'st':value,'f':str(source.get(f'{actual}コース_F','')).lower() in ('1','true','f') or value<0})
  series.sort(key=lambda r:r['race']);normal=[r['st'] for r in series if not r['f']]
  a=f.get('ability') or {};m=f.get('motor') or {};h=(raw.get('motor_history') or {}).get(str(lane),{});proof=support.get(lane,{})
  wins=number(proof.get('wins'));n=number(proof.get('races'));rawrate=wins/n if n and wins is not None else None
  boats.append({'lane':lane,'name':ident.get('name') or card.get(f'艇{lane}_選手名'),'racer':rid,'motor':ident.get('motor') or card.get(f'艇{lane}_モーター番号'),'motor_two':m.get('モーター2連対率'),'motor_three':m.get('モーター3連対率'),'motor_corrected':f.get('motor_history',{}).get('過去3節選手補正'),'motor_sessions':len(h.get('uses') or []),'average_st':a.get('全国平均ST'),'course_average_st':stats.get('平均ST'),'series_st':sum(normal)/len(normal) if normal else None,'series_normal_count':len(normal),'series_starts':series,'course':course,'course_points':stats.get('勝率得点'),'course_win_rate':rawrate,'course_races':int(n) if n is not None else None,'methods':{name:f.get('style',{}).get(name+'勝ち率') for name in ('逃げ','差し','まくり','まくり差し')}})
 return {'schema':'six-boat-1','snapshot_id':s.get('id'),'at':s.get('created_at'),'boats':boats,'course_scope':'展示進入コースの保存期間内実績。勝率得点・決まり手率は場平均へ補正、1着率は勝数÷走数。','series_scope':'今節STは保存済みの当日・当場の確認分。前日以前は未収集。展示STや推定STは含めず、Fは平均から除外。','through':s.get('learning_lineage',{}).get('trained_through')}
