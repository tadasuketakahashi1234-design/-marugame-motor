"""Read saved pre-race surface evidence without inventing causal effects."""
from boat24_context import number
from boat24_integrity import timeparse

def build(s):
 fs=s.get('input_snapshot',{}).get('features',[]);wc=s.get('water_context') or {};raw=s.get('input_snapshot',{}).get('previews',{}).get('weather') or {};q=(s.get('input_quality') or {}).get('weather') or {};official=wc.get('latest_official_wind') or {}
 at=timeparse(raw.get('気象観測時刻') or official.get('measured_at'));created=timeparse(s.get('created_at'));age=(created-at).total_seconds() if at and created else None
 fresh=q.get('state')=='fresh' if q else age is not None and 0<=age<=600
 weather=raw or (fs[0].get('weather',{}) if fs else {});bits=[]
 for k,label,unit in [('風速(m)','風速','m'),('波の高さ(cm)','波高','cm'),('気温(℃)','気温','℃'),('水温(℃)','水温','℃')]:
  v=number(weather.get(k))
  if v is not None:bits.append(f'{label}{v:g}{unit}')
 direction=official.get('wind_direction_literal') if not raw.get('気象観測時刻') or raw.get('気象観測時刻')==official.get('measured_at') else None
 direction=direction or {1:'北',2:'北東',3:'東',4:'南東',5:'南',6:'南西',7:'西',8:'北西'}.get(number(weather.get('風向')))
 if direction:bits.insert(0,direction+'風')
 tide=wc.get('tide') or {};tidal=tide.get('status');phase={'rising':'上げ潮','falling':'下げ潮','slack':'潮止まり'}.get(tide.get('phase'),'潮位推算')
 def effect(f,group):
  if group=='wind' and not fresh:return {'label':'観測が古い・未確認','n':0,'delta':None}
  if wc.get('condition_history_valid') is False:return {'label':'履歴の基準日未確認','n':0,'delta':None}
  if group=='tide' and tidal!='available':return {'label':'干満差なし' if tidal=='not_applicable' else '潮位未取得','n':0,'delta':None}
  v=f.get(group) or {};n=number(v.get('同条件標本数')) or 0;delta=number(v.get('同場コース平均との差'))
  if n<20 or delta is None:return {'label':'標本不足','n':int(n),'delta':None}
  return {'label':'良化傾向' if delta>=.25 else '悪化傾向' if delta<=-.25 else '差が小さい','n':int(n),'delta':delta}
 rows=[{'lane':i,'course':f.get('start',{}).get('展示進入'),'wind':effect(f,'wind'),'tide':effect(f,'tide')} for i,f in enumerate(fs,1)]
 alpha=(s.get('feature_usage') or {}).get('odds',{}).get('market_blend')
 return {'conditions':'・'.join(bits) or '風・波の観測なし','fresh':fresh,'observed_at':at.isoformat() if at else None,'age_minutes':round(age/60,1) if age is not None else None,'tide':phase+'（推算）' if tidal=='available' else '干満差なし' if tidal=='not_applicable' else '潮位未取得','rows':rows,'through':wc.get('trained_through'),'prediction_use':'市場のみの順位計算・水面比較は参考' if alpha==1 else '水面比較は過去傾向の参考情報','scope':'同場・同進入コースの平均着順比較。風は8方位×風速帯、潮は上げ下げ×相対潮位。選手個人の適性や因果効果ではありません。','missing':'波高別・天候別・風と潮と波を合わせた比較は未集計。潮位推算は競走水面の実測流速ではありません。'}
