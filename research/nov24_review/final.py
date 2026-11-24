import pandas as pd, numpy as np, math, pickle
D='/tmp/claude-0/-home-user-trading-ai-bot/c8d83796-5074-54b4-ac65-51ae66ae1912/scratchpad/diag/'
df=pd.read_pickle(D+'wf_pred.pkl'); o=df.dropna(subset=['p_roll']).copy()
fee=lambda a: 0.07*a*(1-a)
def sim(o,col,th,jmin=4,jmax=13,pmin=0.05,pmax=0.95):
    o=o[(o.j>=jmin)&(o.j<=jmax)]
    na=1-o.yb
    ey=o[col]-o.ya-fee(o.ya); en=(1-o[col])-na-fee(na)
    yb_=o[(ey>=th)&(o.ya>=pmin)&(o.ya<=pmax)].assign(a=lambda x:x.ya,w=lambda x:x.y,side='yes',e=ey)
    nb_=o[(en>=th)&(na>=pmin)&(na<=pmax)].assign(a=lambda x:1-x.yb,w=lambda x:1-x.y,side='no',e=en)
    b=pd.concat([yb_,nb_]).sort_values(['ots','j']); b['key']=b.coin+b.m.astype(str); b=b.drop_duplicates('key')
    b['pnl']=b.w-b.a-fee(b.a)
    return b
alld=np.sort(o.day.unique())
def line(name,b):
    dd=b.groupby('day').pnl.sum().reindex(alld,fill_value=0)
    h=len(alld)//2; t=lambda v: v.mean()/v.std(ddof=1)*math.sqrt(len(v)) if v.std(ddof=1)>0 else 0
    print(f"{name:26s} {len(b)/len(alld):6.1f}/day win%={100*b.w.mean():4.1f} px={b.a.mean():.2f} {100*b.pnl.mean():+5.2f}c/bet ${dd.mean():+.2f}/day t={t(dd):+.2f} up {int((dd>0).sum())}/{len(dd)} | halves ${dd[:h].mean():+.2f} / ${dd[h:].mean():+.2f}  worst day ${dd.min():+.2f} maxDD ${(dd.cumsum().cummax()-dd.cumsum()).max():.2f}")
for th in (0.03,0.04,0.05,0.06):
    b=sim(o,'p_roll',th); line(f'ALL thr {th}',b)
b=sim(o,'p_roll',0.04)
for c,g in b.groupby('coin'): line(c,g)
for c,g in b.groupby('side'): line(c,g)
b['pb']=pd.cut(b.a,[0,0.2,0.4,0.6,0.8,1])
for c,g in b.groupby('pb',observed=True): line('px '+str(c),g)
b['eb']=pd.cut(b.e,[0,0.05,0.06,0.08,1])
for c,g in b.groupby('eb',observed=True): line('pred edge '+str(c),g)
for c,g in b.groupby(b.ots%86400//3600//4*4): line(f'hour {c:02d}-{c+4:02d}',g)
good=['NEAR','SOL','ZEC','XRP','HYPE']
for th in (0.03,0.04,0.05): line(f'5 coins thr {th}',sim(o[o.coin.isin(good)],'p_roll',th))
# concurrency: bets per 15-min window
w=b.groupby('ots').size(); print('bets per window: mean',w.mean().round(2),'max',w.max(),'p95',w.quantile(0.95))
# weekly pnl
b['wk']=(b.day-alld[0])//7
print(b.groupby('wk').pnl.agg(['size','sum']).round(2).T)
