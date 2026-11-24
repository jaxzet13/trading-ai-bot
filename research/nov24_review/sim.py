import pandas as pd, numpy as np, math, pickle
D='/tmp/claude-0/-home-user-trading-ai-bot/c8d83796-5074-54b4-ac65-51ae66ae1912/scratchpad/diag/'
df=pd.read_pickle(D+'wf_pred.pkl').dropna(subset=['phat']).copy()
fee=lambda a: 0.07*a*(1-a)
df['na']=1-df.yb
df['ey']=df.phat-df.ya-fee(df.ya); df['en']=(1-df.phat)-df.na-fee(df.na)
df['key']=df.coin+':'+df.m.astype(str)
def sim(th, jmin=1, jmax=13, pmin=0.05, pmax=0.95, slip=0.0, coins=None):
    g=df[(df.j>=jmin)&(df.j<=jmax)]
    if coins: g=g[g.coin.isin(coins)]
    y=g[(g.ey>=th)&(g.ya>=pmin)&(g.ya<=pmax)].assign(side='yes',a=lambda x:x.ya,e=lambda x:x.ey,w=lambda x:x.y)
    n=g[(g.en>=th)&(g.na>=pmin)&(g.na<=pmax)].assign(side='no',a=lambda x:x.na,e=lambda x:x.en,w=lambda x:1-x.y)
    b=pd.concat([y,n]).sort_values(['ots','j'])
    b=b.drop_duplicates('key')          # first signal in each market
    b['a2']=b.a+slip
    b['pnl']=b.w-b.a2-fee(b.a2)
    return b
def rep(b,name):
    dd=b.groupby('day').pnl.sum(); nd=df.day.nunique()
    dd=dd.reindex(np.sort(df.day.unique()),fill_value=0)
    t=dd.mean()/dd.std(ddof=1)*math.sqrt(len(dd))
    print(f"{name:34s} bets={len(b):6d} ({len(b)/nd:5.1f}/day) c/bet={100*b.pnl.mean():+5.2f} total=${b.pnl.sum():+8.2f} $/day={dd.mean():+.2f} days up {int((dd>0).sum())}/{len(dd)} t={t:+.2f} avg px={b.a.mean():.2f} pred edge={100*b.e.mean():.1f}c")
print('test days',df.day.nunique())
for th in [0.0,0.01,0.015,0.02,0.025,0.03,0.04,0.05]:
    rep(sim(th),f'thr {th:.3f}')
print('--- +1c slippage')
for th in [0.02,0.03,0.04]: rep(sim(th,slip=0.01),f'thr {th:.3f} slip1c')
b=sim(0.02)
print('--- thr 0.02 by coin'); 
for c,g in b.groupby('coin'): rep(g,c)
print('--- by side'); 
for c,g in b.groupby('side'): rep(g,c)
b['per']=np.where(b.ots<1793491200,'Oct','Nov')
for c,g in b.groupby('per'): rep(g,c)
b['pb']=pd.cut(b.a,[0,0.2,0.4,0.6,0.8,1])
for c,g in b.groupby('pb',observed=True): rep(g,str(c))
b['jb']=pd.cut(b.j,[0,3,6,9,13])
for c,g in b.groupby('jb',observed=True): rep(g,'min '+str(c))
b['hb']=(b.ots%86400//3600//4*4)
for c,g in b.groupby('hb'): rep(g,f'hour {c:02d}-{c+4:02d}')
pickle.dump(b,open(D+'sim_b02.pkl','wb'))
