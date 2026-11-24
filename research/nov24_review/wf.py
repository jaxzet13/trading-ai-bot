import pandas as pd, numpy as np, math, pickle, sys, time
D='/tmp/claude-0/-home-user-trading-ai-bot/c8d83796-5074-54b4-ac65-51ae66ae1912/scratchpad/diag/'
pool=pickle.load(open(D+'pool.pkl','rb'))
sys.path.insert(0,'/home/user/trading-ai-bot'); from kalshi15m.strategies import ndtr
MIN=np.arange(1,15)
def logit(p): p=np.clip(p,1e-4,1-1e-4); return np.log(p/(1-p))
rows=[]
for s,d in pool.items():
    P={k:v.astype(float) for k,v in d['P'].items()}; ots=d['open_ts']; res=d['result'].astype(int)
    keep=ots>=1788134400
    tau=(15-MIN)[None,:].astype(float)
    x=np.log(P['spot']/P['strike']); v=P['vol1m']; v240=P['vol240']
    with np.errstate(all='ignore'):
        q=ndtr(x/(v*np.sqrt(tau))); q240=ndtr(x/(v240*np.sqrt(tau)))
        ya=P['yes_ask']; yb=P['yes_bid']; mid=(ya+yb)/2
        F={'dl':np.clip(logit(q)-logit(mid),-3,3),'dl240':np.clip(logit(q240)-logit(mid),-3,3),
           'r1z':np.clip(P['r1']/v,-4,4),'r3z':np.clip(P['r3']/(v*math.sqrt(3)),-4,4),'r5z':np.clip(P['r5']/(v*math.sqrt(5)),-4,4),
           'r10z':np.clip(P['r10']/(v*math.sqrt(10)),-4,4),
           'refz':np.clip(P['ref_z'],-4,4),'refr1':np.clip(P['ref_r1']/P['ref_v60'],-4,4),'refr3':np.clip(P['ref_r3']/(P['ref_v60']*math.sqrt(3)),-4,4),
           'prevz':np.clip(P['prev_ret']/(v*math.sqrt(15)),-4,4),
           'zown':np.clip(x/(v*np.sqrt(MIN[None,:].astype(float))),-4,4)}
    ok=np.isfinite(ya)&np.isfinite(yb)&(mid>=0.04)&(mid<=0.96)&keep[:,None]
    for f in F.values(): ok&=np.isfinite(f)
    mi,ji=np.nonzero(ok)
    df=pd.DataFrame({'coin':s[2:-3],'m':mi,'j':MIN[ji],'ots':ots[mi],'ya':ya[mi,ji],'yb':yb[mi,ji],'y':(res[mi]==1).astype(float)})
    for k,f in F.items(): df[k]=f[mi,ji]
    rows.append(df)
df=pd.concat(rows,ignore_index=True)
df['mid']=(df.ya+df.yb)/2; df['off']=logit(df.mid.to_numpy()); df['day']=df.ots//86400
late=(df.j>=10).astype(float); early=(df.j<=5).astype(float)
base=['dl','dl240','r1z','r3z','r5z','r10z','refz','refr1','refr3','prevz','zown']
for f in ['dl','refz','r1z','r5z','prevz']:
    df[f+'_late']=df[f]*late; df[f+'_early']=df[f]*early
FE=base+[f+s for f in ['dl','refz','r1z','r5z','prevz'] for s in ('_late','_early')]
df.to_pickle(D+'wf_rows.pkl'); pickle.dump(FE,open(D+'FE.pkl','wb'))
print(len(df), len(FE), df.day.nunique())
