import sys, numpy as np, pandas as pd, math, pickle
sys.path.insert(0,'/home/user/trading-ai-bot')
from tennis import lab, api
ms=lab.load()
print(len(ms),'markets')
TOUR={"KXATPMATCH":"atp","KXWTAMATCH":"wta","KXATPCHALLENGERMATCH":"chal","KXWTACHALLENGERMATCH":"chal","KXITFMATCH":"itf","KXITFWMATCH":"itf"}
rows=[]
for k,m in enumerate(ms):
    rel,mid=m['rel'],m['mid']
    for M in (-180,-120,-90,-60,-30,-10,0,15,30,60):
        i=np.searchsorted(rel,M,side='right')-1
        if i<0 or M-rel[i]>10 or not np.isfinite(mid[i]): continue
        j=i+1
        if j>=len(rel) or rel[j]-rel[i]>3.01: continue
        a=m['askhi'][j]; bl=m['bidlo'][j]
        if not (np.isfinite(a) and np.isfinite(bl)): continue
        def chg(L):
            i0=np.searchsorted(rel,M-L,side='right')-1
            return mid[i]-mid[i0] if i0>=0 and (M-L)-rel[i0]<=10 and np.isfinite(mid[i0]) else np.nan
        rows.append((k,m['event'],m['series'],TOUR.get(m['series'],'oth'),m['day'],M,mid[i],a,bl,m['value'],chg(30),chg(60),chg(120),chg(240)))
df=pd.DataFrame(rows,columns=['k','event','series','tour','day','M','mid','ask','bidlo','value','c30','c60','c120','c240'])
df=df[(df.value==0)|(df.value==1)]
df['fee']=np.ceil(0.07*df.ask*(1-df.ask)*100-1e-9)/100
df['pnl_yes']=df.value-df.ask-df.fee
df['res']=df.value-df.mid
df['spread']=df.ask-df.bidlo
df.to_pickle('/tmp/claude-0/-home-user-trading-ai-bot/c8d83796-5074-54b4-ac65-51ae66ae1912/scratchpad/diag/ten_rows.pkl')
print(len(df), df.day.nunique(),'days', df.groupby('M').size().to_dict())
def tab(g,by):
    r=g.groupby(by,observed=True).agg(n=('res','size'),mid=('mid','mean'),win=('value','mean'),res_c=('res',lambda x:100*x.mean()),buy_yes_c=('pnl_yes',lambda x:100*x.mean()),spread=('spread','mean'))
    dd=g.groupby([*([by] if isinstance(by,str) else by),'day'],observed=True).res.mean().reset_index()
    return r.round(3)
df['pb']=pd.cut(df.mid,[0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.85,0.9,0.95,1])
pre=df[df.M<=0]
print('== pre-match, all tours: value - mid by price'); print(tab(pre,'pb'))
for t in ('atp','wta','chal','itf'):
    print('==',t); print(tab(pre[pre.tour==t],'pb')[['n','mid','win','res_c','buy_yes_c','spread']])
print('== in-play (M>0) by price'); print(tab(df[df.M>0],'pb'))
