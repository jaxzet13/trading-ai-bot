import sys, numpy as np, pandas as pd, math
sys.path.insert(0,'/home/user/trading-ai-bot')
from kalshi15m.edge import fit
D='/tmp/claude-0/-home-user-trading-ai-bot/c8d83796-5074-54b4-ac65-51ae66ae1912/scratchpad/diag/'
df=pd.read_pickle(D+'ten_rows.pkl'); df=df[(df.M<=0)&(df.mid>=0.04)&(df.mid<=0.96)].copy()
lm=np.log(df.mid/(1-df.mid)); df['off']=lm
for t in ('atp','wta','chal','itf'): df['lm_'+t]=lm*(df.tour==t)
df['lm_early']=lm*(df.M<=-90); df['lm_spread']=lm*df.spread.clip(0,0.2)
for c in ('c30','c60','c120','c240'): df[c]=df[c].fillna(0).clip(-0.2,0.2)
FE=['lm_atp','lm_wta','lm_chal','lm_itf','lm_early','lm_spread','c30','c60','c120','c240']
days=np.sort(df.day.unique()); WARM=20
X=df[FE].to_numpy(float); y=df.value.to_numpy(float); off=df.off.to_numpy(float); dv=df.day.to_numpy()
ph=np.full(len(df),np.nan)
for i,d in enumerate(days):
    if i<WARM: continue
    if (i-WARM)%3==0: b=fit(X[dv<d],y[dv<d],off[dv<d],lam=5.0)
    ph[dv==d]=1/(1+np.exp(-(off[dv==d]+X[dv==d]@b)))
df['ph']=ph
print('beta',dict(zip(FE,b.round(3))))
o=df.dropna(subset=['ph']).copy(); o['e']=o.ph-o.ask-o.fee
alld=np.sort(o.day.unique())
def line(nm,b_):
    dd=b_.groupby('day').pnl_yes.sum().reindex(alld,fill_value=0)
    t=dd.mean()/dd.std(ddof=1)*math.sqrt(len(dd)) if dd.std(ddof=1)>0 else 0
    print(f"{nm:28s} bets={len(b_):5d} ({len(b_)/len(alld):5.1f}/day) {100*b_.pnl_yes.mean():+5.2f}c/bet total ${b_.pnl_yes.sum():+7.2f} t={t:+.2f} up {int((dd>0).sum())}/{len(dd)} px={b_.ask.mean():.2f}")
for th in (0.0,0.01,0.02,0.03):
    b_=o[(o.e>=th)&(o.ask>=0.05)&(o.ask<=0.97)].sort_values(['day','M']).drop_duplicates('k'); line(f'model thr {th}',b_)
b_=o[(o.e>=0.0)&(o.ask<=0.97)].sort_values(['day','M']).drop_duplicates('k')
for t,g in b_.groupby('tour'): line('thr 0 '+t,g)
# calibration OOS
o['shift']=o.ph-o.mid; o['sb']=pd.cut(o['shift'],[-1,-0.02,-0.01,0,0.01,0.02,0.03,1])
print(o.groupby('sb',observed=True).agg(n=('res','size'),pred=('shift','mean'),real=('res','mean')).round(4))
# simple structural: chal favourites by spread
ch=df[(df.tour=='chal')&(df.mid>=0.8)&(df.mid<=0.95)]
ch=ch.assign(sb=pd.cut(ch.spread,[0,0.02,0.03,0.05,0.1,1]))
print(ch.groupby('sb',observed=True).agg(n=('res','size'),res_c=('res',lambda x:100*x.mean()),buy_c=('pnl_yes',lambda x:100*x.mean()),ask_minus_mid=('ask',lambda x:0)).round(2))
print('chal fav value-mid by day-half:', ch[ch.day<np.median(ch.day)].res.mean().round(4), ch[ch.day>=np.median(ch.day)].res.mean().round(4))
