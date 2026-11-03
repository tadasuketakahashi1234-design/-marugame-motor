"""Prior-day tactical labels with explicit denominators, never current outcomes."""
from boat24_integrity import timeparse

class Tactics:
    def __init__(self,state=None):self.state=state or {'through':None,'racer':{},'pairs':{}}
    def add(self,data):
        from boat24_context import number
        for code,res in data.get('results',{}).items():
            card=data.get('cards',{}).get(code);at=timeparse(res.get('取得日時'))
            if not card or not at or at.strftime('%Y%m%d')!=code[:8]:continue
            courses={str(res.get(f'{c}コース_艇番')):c for c in range(1,7)}
            winners=[str(res.get(f'{p}着_艇番')) for p in range(1,7)]
            if set(courses)!=set('123456') or set(winners)!=set('123456'):continue
            wc=courses[winners[0]];method=res.get('決まり手','');venue=int(code[8:10]);day=at.date().isoformat()
            for lane in range(1,7):
                rid=str(card.get(f'艇{lane}_登録番号'));course=courses[str(lane)]
                key=f'{rid}|{course}';a=self.state['racer'].setdefault(key,{'n':0,'second':0,'third':0,'escaped':0,'in_losses':0,'lost_sashi':0,'lost_makuri':0,'st':[]})
                a['n']+=1;a['second']+=winners[1]==str(lane);a['third']+=winners[2]==str(lane)
                if course==2:a['escaped']+=wc==1 and method=='逃げ'
                if course==1 and winners[0]!=str(lane):
                    a['in_losses']+=1;a['lost_sashi']+=method in ('差し','まくり差し');a['lost_makuri']+=method=='まくり'
                st=number(res.get(f'{course}コース_スタートタイミング'))
                if st is not None and st>=0 and not res.get(f'{course}コース_F'):a['st'].append(st);a['st']=a['st'][-100:]
            for p in (2,3):
                key=f'{venue}|{wc}|{p}';counts=self.state['pairs'].setdefault(key,[0]*6);counts[courses[winners[p-1]]-1]+=1
                if method in ('逃げ','差し','まくり','まくり差し'):
                    key=f'{venue}|{wc}|{method}|{p}';counts=self.state['pairs'].setdefault(key,[0]*6);counts[courses[winners[p-1]]-1]+=1
            self.state['through']=max(self.state['through'] or '',day)
    def attach(self,features,card,venue,day):
        import statistics
        if self.state.get('through') and self.state['through']>=day:return
        for lane,f in enumerate(features,1):
            f['tactical_detail']={};g=f['tactical_detail'];course=int(f.get('start',{}).get('展示進入',lane));rid=str(card.get(f'艇{lane}_登録番号'));a=self.state['racer'].get(f'{rid}|{course}',{});n=a.get('n',0)
            if n:
                g['実進入確認走数']=n;g['2着率']=a['second']/n;g['3着率']=a['third']/n
                if course==2:g['2コースイン逃げ許容率']=a['escaped']/n
                if course==1 and a['in_losses']:
                    g['イン敗戦確認数']=a['in_losses'];g['イン敗戦中差され率']=a['lost_sashi']/a['in_losses'];g['イン敗戦中まくられ率']=a['lost_makuri']/a['in_losses']
                if len(a['st'])>=2:g['本番ST標準偏差']=statistics.pstdev(a['st']);g['本番ST中央値']=statistics.median(a['st'])
            for wc in range(1,7):
                for p in (2,3):
                    counts=self.state['pairs'].get(f'{venue}|{wc}|{p}',[])
                    if counts and sum(counts)>=20:g[f'{wc}コース勝利時の{p}着コース率']=(counts[course-1]+1)/(sum(counts)+6)
                    for method in ('逃げ','差し','まくり','まくり差し'):
                        counts=self.state['pairs'].get(f'{venue}|{wc}|{method}|{p}',[])
                        if counts and sum(counts)>=20:g[f'{wc}コース{method}勝利時の{p}着コース率']=(counts[course-1]+1)/(sum(counts)+6)
