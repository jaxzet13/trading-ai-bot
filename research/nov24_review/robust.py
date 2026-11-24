import pandas as pd, numpy as np, math, pickle, time
D='/tmp/claude-0/-home-user-trading-ai-bot/c8d83796-5074-54b4-ac65-51ae66ae1912/scratchpad/diag/'
df=pd.read_pickle(D+'wf_pred.pkl'); FEall=pickle.load(open(D+'FE.pkl','rb'))
base=['dl','dl240','r1z','r3z','r5z','r10z','refz','refr1','refr3','prevz','zown']
def fit(X,y,off,lam=50.0,prior=None,iters=12):
    k=X.shape[1]; b=np.zeros(k) if prior is None else prior.copy(); pr=np.zeros(k) if prior is None else prior
    for _ in range(iters):
        p=1/(1+np.exp(-(off+X@b))); w=p*(1-p)
        g=X.T@(y-p)-lam*(b-pr); H=(X*w[:,None]).T@X+lam*np.eye(k)
        step=np.linalg.solve(H,g); b=b+step
        if np.abs(step).max()<1e-6: break
    return b
days=np.sort(df.day.unique()); WARM=28
y=df.y.to_numpy(); off=df.off.to_numpy(); dayv=df.day.to_numpy(); coinv=df.coin.to_numpy(); coins=sorted(df.coin.unique())
def wf(FE,roll=None,lam_c=300.0,refit=3):
    X=df[FE].to_numpy(); ph=np.full(len(df),np.nan)
    for i,d in enumerate(days):
        if i<WARM: continue
        if (i-WARM)%refit==0:
            tr=(dayv<d) if roll is None else ((dayv<d)&(dayv>=d-roll))
            bp=fit(X[tr],y[tr],off[tr],lam=20.0)
            bc={c:fit(X[tr&(coinv==c)],y[tr&(coinv==c)],off[tr&(coinv==c)],lam=lam_c,prior=bp) for c in coins}
        te=dayv==d
        for c in coins:
            mk=te&(coinv==c); ph[mk]=1/(1+np.exp(-(off[mk]+X[mk]@bc[c])))
    return ph
fee=lambda a: 0.07*a*(1-a)
def sim(o,col,th,jmin=1,jmax=13,coins_=None,pmin=0.05,pmax=0.95):
    o=o[(o.j>=jmin)&(o.j<=jmax)]
    if coins_ is not None: o=o[o.coin.isin(coins_)]
    na=1-o.yb
    ey=o[col]-o.ya-fee(o.ya); en=(1-o[col])-na-fee(na)
    yb_=o[(ey>=th)&(o.ya>=pmin)&(o.ya<=pmax)].assign(a=lambda x:x.ya,w=lambda x:x.y,side='yes')
    nb_=o[(en>=th)&(na>=pmin)&(na<=pmax)].assign(a=lambda x:1-x.yb,w=lambda x:1-x.y,side='no')
    b=pd.concat([yb_,nb_]).sort_values(['ots','j']); b['key']=b.coin+b.m.astype(str); b=b.drop_duplicates('key')
    b['pnl']=b.w-b.a-fee(b.a)
    return b
def line(name,b,o):
    alld=np.sort(o.day.unique()); dd=b.groupby('day').pnl.sum().reindex(alld,fill_value=0)
    h=len(alld)//2; t=lambda v: v.mean()/v.std(ddof=1)*math.sqrt(len(v)) if v.std(ddof=1)>0 else 0
    print(f"{name:38s} {len(b)/len(alld):6.1f}/day {100*b.pnl.mean():+5.2f}c/bet ${dd.mean():+.2f}/day t={t(dd):+.2f} up {int((dd>0).sum())}/{len(dd)} | 1st half ${dd[:h].mean():+.2f}/d t={t(dd[:h]):+.1f}  2nd half ${dd[h:].mean():+.2f}/d t={t(dd[h:]):+.1f}")
o=df.dropna(subset=['phat']).copy()
for th in (0.03,0.04,0.05): line(f'full model thr {th}',sim(o,'phat',th),o)
df['p_base']=wf(base); df['p_roll']=wf(FEall,roll=35); df['p_pool']=wf(FEall,lam_c=1e7); df['p_loose']=wf(FEall,lam_c=50.0)
o=df.dropna(subset=['phat']).copy()
for nm,col in (('base features only','p_base'),('rolling 35-day fit','p_roll'),('pooled only (no per-coin)','p_pool'),('loose per-coin','p_loose')):
    for th in (0.03,0.04,0.05): line(f'{nm} thr {th}',sim(o,col,th),o)
for th in (0.03,0.04,0.05): line(f'min 4-13 thr {th}',sim(o,'phat',th,jmin=4),o)
for th in (0.03,0.04): line(f'min 2-12 thr {th}',sim(o,'phat',th,jmin=2,jmax=12),o)
# walk-forward coin gate: trade a coin on day d only if its model bets (thr 0.02) over the prior 21 test days made money per bet
b2=sim(o,'phat',0.02)
cd=b2.groupby(['coin','day']).pnl.agg(['sum','size']).reset_index()
alld=np.sort(o.day.unique())
for th in (0.03,0.04,0.05):
    bb=sim(o,'phat',th); keep=[]
    for d in alld:
        prior=cd[(cd.day<d)&(cd.day>=d-21)]
        if prior.day.nunique()<10: ok=set(coins)
        else:
            s=prior.groupby('coin').agg(s=('sum','sum'),n=('size','sum')); ok=set(s.index[s.s/s.n>0.0])
        keep.append(bb[(bb.day==d)&bb.coin.isin(ok)])
    line(f'walk-fwd coin gate thr {th}',pd.concat(keep),o)
df.to_pickle(D+'wf_pred.pkl')
