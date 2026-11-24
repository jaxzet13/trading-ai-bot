import pickle, numpy as np, pandas as pd, math
import sys; sys.path.insert(0,"/home/user/trading-ai-bot"); from kalshi15m.strategies import ndtr
D='/tmp/claude-0/-home-user-trading-ai-bot/c8d83796-5074-54b4-ac65-51ae66ae1912/scratchpad/diag/'
pool=pickle.load(open(D+'pool.pkl','rb'))
MIN=np.arange(1,15)
frames=[]
for s,d in pool.items():
    P=d['P']; ots=d['open_ts']; res=d['result'].astype(int)
    keep=ots>=1756598400  # Aug 31
    nm=len(ots)
    tau=(15-MIN)[None,:].astype(float)
    x=np.log(P['spot']/P['strike']).astype(float)
    v=P['vol1m'].astype(float); v240=P['vol240'].astype(float)
    z=x/(v*np.sqrt(tau))
    q=ndtr(z)
    ya=P['yes_ask'].astype(float); yb=P['yes_bid'].astype(float); na=1-yb; nb=1-ya
    for side,(a,b,qq,zz,win) in {'yes':(ya,yb,q,z,res[:,None]==1),'no':(na,nb,1-q,-z,res[:,None]==0)}.items():
        ok=np.isfinite(a)&np.isfinite(qq)&(a>=0.03)&(a<=0.97)&keep[:,None]
        mi,ji=np.nonzero(ok)
        df=pd.DataFrame({'coin':s[2:-3],'m':mi,'j':MIN[ji],'side':side,'ots':ots[mi],'a':a[mi,ji],'bid':b[mi,ji],'q':qq[mi,ji],'z':zz[mi,ji],
                         'win':np.broadcast_to(win,a.shape)[mi,ji].astype(float),'vr':(v/v240)[mi,ji],'hour':(ots[mi]%86400//3600),
                         'r1':P['r1'].astype(float)[mi,ji]*(1 if side=='yes' else -1),'r3':P['r3'].astype(float)[mi,ji]*(1 if side=='yes' else -1),
                         'r5':P['r5'].astype(float)[mi,ji]*(1 if side=='yes' else -1),
                         'refz':P['ref_z'].astype(float)[mi,ji]*(1 if side=='yes' else -1),'vol':v[mi,ji],
                         'prev':P['prev_ret'].astype(float)[mi,ji]*(1 if side=='yes' else -1),'volume':P['volume'].astype(float)[mi,ji]})
        frames.append(df)
df=pd.concat(frames,ignore_index=True)
df['fee']=0.07*df.a*(1-df.a)
df['pnl']=df.win-df.a-df.fee
df['day']=df.ots//86400
df['edge']=df.q-df.a
df['spread']=df.a-df.bid
df.to_pickle(D+"rows.pkl")
print(len(df), df.day.nunique(), df.pnl.mean())
