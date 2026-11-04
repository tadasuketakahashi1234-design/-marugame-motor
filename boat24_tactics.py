"""Prior-day tactical labels with explicit denominators, never current outcomes."""
from boat24_integrity import timeparse
from boat24_methods import normalize_method

class Tactics:
    def __init__(self,state=None):self.state=state or {'through':None,'racer':{},'pairs':{}}
    def add(self,data):
        from boat24_context import number
        for code,res in data.get('results',{}).items():
            card=data.get('cards',{}).get(code);at=timeparse(res.get('取得日時'))
            if not card or not at or at.strftime('%Y%m%d')!=code[:8]:continue
            from boat24_settlement import refund_boats
            try:
                if refund_boats(res):continue
            except ValueError:continue
            courses={str(res.get(f'{c}コース_艇番')):c for c in range(1,7)}
            winners=[str(res.get(f'{p}着_艇番')) for p in range(1,7)]
            if set(courses)!=set('123456') or set(winners)!=set('123456'):continue
            wc=courses[winners[0]];method=normalize_method(res.get('決まり手'));venue=int(code[8:10]);day=at.date().isoformat()
            # Joint second/third courses preserve dependence. Missing method
            # labels count in coverage, never as zero-rate escape observations.
            joint=self.state.setdefault('joint_methods',{'seen':{},'groups':{}})
            if code not in joint['seen']:
                joint['seen'][code]=day
                j=joint['groups'].setdefault(f'{venue}|{wc}',{'total':0,'known':0,'methods':{}});j['total']+=1
                if method:
                    j['known']+=1;m=j['methods'].setdefault(method,{'n':0,'pairs':{}});m['n']+=1
                    pair=f'{courses[winners[1]]}-{courses[winners[2]]}';m['pairs'][pair]=m['pairs'].get(pair,0)+1
            for lane in range(1,7):
                rid=str(card.get(f'艇{lane}_登録番号'));course=courses[str(lane)]
                key=f'{rid}|{course}';a=self.state['racer'].setdefault(key,{'n':0,'second':0,'third':0,'escaped':0,'in_losses':0,'lost_sashi':0,'lost_makuri':0,'st':[]})
                a['n']+=1;a['second']+=winners[1]==str(lane);a['third']+=winners[2]==str(lane)
                if method:
                    a['method_n']=a.get('method_n',0)+1
                    a['labelled_escaped']=a.get('labelled_escaped',0)+int(wc==1 and method=='逃げ')
                    if course==1 and winners[0]!=str(lane):
                        a['known_in_losses']=a.get('known_in_losses',0)+1
                        a['labelled_lost_sashi']=a.get('labelled_lost_sashi',0)+int(method in ('差し','まくり差し'))
                        a['labelled_lost_makuri']=a.get('labelled_lost_makuri',0)+int(method=='まくり')
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
        courses=[f.get('start',{}).get('展示進入') for f in features]
        entry=sorted(range(1,7),key=lambda i:courses[i-1]) if set(courses)==set(range(1,7)) else None
        for lane,f in enumerate(features,1):
            f['tactical_detail']={};g=f['tactical_detail'];course=int(f.get('start',{}).get('展示進入',lane));rid=str(card.get(f'艇{lane}_登録番号'));a=self.state['racer'].get(f'{rid}|{course}',{});n=a.get('n',0)
            if n:
                g['実進入確認走数']=n;g['2着率']=a['second']/n;g['3着率']=a['third']/n
                if a.get('method_n'):g['決まり手確認走数']=a['method_n']
                if course==2 and a.get('method_n')==n:g['2コースイン逃げ許容率']=a.get('labelled_escaped',0)/n
                if course==1 and a.get('known_in_losses') and a['known_in_losses']==a['in_losses']:
                    g['イン敗戦確認数']=a['known_in_losses'];g['イン敗戦中差され率']=a.get('labelled_lost_sashi',0)/a['known_in_losses'];g['イン敗戦中まくられ率']=a.get('labelled_lost_makuri',0)/a['known_in_losses']
                if len(a['st'])>=2:g['本番ST標準偏差']=statistics.pstdev(a['st']);g['本番ST中央値']=statistics.median(a['st'])
            for wc in range(1,7):
                for p in (2,3):
                    counts=self.state['pairs'].get(f'{venue}|{wc}|{p}',[])
                    if counts and sum(counts)>=20:g[f'{wc}コース勝利時の{p}着コース率']=(counts[course-1]+1)/(sum(counts)+6)
                    for method in ('逃げ','差し','まくり','まくり差し'):
                        counts=self.state['pairs'].get(f'{venue}|{wc}|{method}|{p}',[])
                        if counts and sum(counts)>=20:g[f'{wc}コース{method}勝利時の{p}着コース率']=(counts[course-1]+1)/(sum(counts)+6)
            ref=method_reference(self.state,venue,entry,lane,day)
            if ref['status']=='historical_reference':
                g['同場決まり手連動確認数']=ref['known']
                for method in ref['methods']:
                    g['同場同コース勝利時_'+method['method']+'構成率']=method['share_among_course_wins']
                    for pair in method['pairs']:g[f"同場同コース{method['method']}勝利時_{pair['second_course']}-{pair['third_course']}_連動率"]=pair['rate']

def method_reference(state,venue,entry,winner,day):
    """Conditional historical reference, never an estimated current attack rate."""
    if state.get('through') and state['through']>=day:return {'status':'future_history_rejected'}
    if not entry or set(entry)!=set(range(1,7)):return {'status':'entry_unconfirmed'}
    course=entry.index(winner)+1;g=state.get('joint_methods',{}).get('groups',{}).get(f'{venue}|{course}',{})
    n=g.get('known',0);total=g.get('total',0)
    if n<20 or n!=total:return {'status':'insufficient_verified_labels','known':n,'total':total,'minimum':20}
    rows=[]
    for name,m in sorted(g.get('methods',{}).items(),key=lambda x:-x[1]['n']):
        pairs=[]
        for key,count in sorted(m['pairs'].items(),key=lambda x:-x[1]):
            second,third=map(int,key.split('-'))
            if len({course,second,third})!=3:continue
            pairs.append({'combo':f'{winner}-{entry[second-1]}-{entry[third-1]}','second_course':second,'third_course':third,'count':count,'rate':count/m['n']})
        rows.append({'method':name,'races':m['n'],'share_among_course_wins':m['n']/n,'pairs':pairs[:3]})
    return {'status':'historical_reference','course':course,'known':n,'total':total,'through':state.get('through'),'methods':rows,
            'notice':'同場・同コース勝利時の過去内訳。今回の決まり手の成立確率ではありません。2・3着は同時に観測した組合せです。'}
