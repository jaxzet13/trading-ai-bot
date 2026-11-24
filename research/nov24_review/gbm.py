import pandas as pd, numpy as np, math, pickle, time, lightgbm as lgb
D='/tmp/claude-0/-home-user-trading-ai-bot/c8d83796-5074-54b4-ac65-51ae66ae1912/scratchpad/diag/'
df=pd.read_pickle(D+'wf_pred.pkl')
base=['dl','dl240','r1z','r3z','r5z','r10z','refz','refr1','refr3','prevz','zown']
df['coinid']=df.coin.astype('category').cat.codes
df['hour']=df.ots%86400//3600
df['spread']=df.ya-df.yb
FE=base+['j','mid','coinid','spread','hour']
days=np.sort(df.day.unique()); WARM=28
dayv=df.day.to_numpy(); ph=np.full(len(df),np.nan)
t0=time.time(); mdl=None
for i,d in enumerate(days):
    if i<WARM: continue
    if (i-WARM)%7==0:
        tr=dayv<d
        ds=lgb.Dataset(df.loc[tr,FE],label=df.loc[tr,'y'],init_score=df.loc[tr,'off'],categorical_feature=['coinid'])
        mdl=lgb.train({'objective':'binary','learning_rate':0.03,'num_leaves':15,'min_data_in_leaf':2000,'feature_fraction':0.7,'bagging_fraction':0.7,'bagging_freq':1,'lambda_l2':50,'verbose':-1,'num_threads':3},ds,num_boost_round=150)
    te=dayv==d
    ph[te]=1/(1+np.exp(-(df.loc[te,'off'].to_numpy()+mdl.predict(df.loc[te,FE],raw_score=True))))
print('gbm done',time.time()-t0)
df['pg']=ph
df.to_pickle(D+'wf_pred.pkl')
o=df.dropna(subset=['pg'])
fee=lambda a: 0.07*a*(1-a)
def sim(o,col,th):
    na=1-o.yb
    ey=o[col]-o.ya-fee(o.ya); en=(1-o[col])-na-fee(na)
    y=o[(ey>=th)&(o.ya>=0.05)&(o.ya<=0.95)&(o.j<=13)].assign(a=lambda x:x.ya,w=lambda x:x.y)
    n=o[(en>=th)&(na>=0.05)&(na<=0.95)&(o.j<=13)].assign(a=lambda x:1-x.yb,w=lambda x:1-x.y)
    b=pd.concat([y,n]).sort_values(['ots','j']); b['key']=b.coin+b.m.astype(str); b=b.drop_duplicates('key')
    b['pnl']=b.w-b.a-fee(b.a)
    dd=b.groupby('day').pnl.sum().reindex(np.sort(o.day.unique()),fill_value=0)
    return len(b)/o.day.nunique(), 100*b.pnl.mean(), dd.mean(), dd.mean()/dd.std(ddof=1)*math.sqrt(len(dd)), b
for col in ['phat','pg']:
    for th in [0.02,0.03,0.04,0.05,0.06]:
        n,c,dpd,t,_=sim(o,col,th); print(f"{col} thr {th:.2f}: {n:6.1f} bets/day {c:+.2f}c/bet ${dpd:+.2f}/day t={t:+.2f}")
o=o.assign(pavg=(o.phat+o.pg)/2)
for th in [0.02,0.03,0.04,0.05]:
    n,c,dpd,t,_=sim(o,'pavg',th); print(f"avg thr {th:.2f}: {n:6.1f} bets/day {c:+.2f}c/bet ${dpd:+.2f}/day t={t:+.2f}")
imp=dict(zip(FE,mdl.feature_importance('gain').round(0))); print(sorted(imp.items(),key=lambda x:-x[1]))
