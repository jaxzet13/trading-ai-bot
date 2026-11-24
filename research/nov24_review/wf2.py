import pandas as pd, numpy as np, math, pickle, sys, time
D='/tmp/claude-0/-home-user-trading-ai-bot/c8d83796-5074-54b4-ac65-51ae66ae1912/scratchpad/diag/'
df=pd.read_pickle(D+'wf_rows.pkl'); FE=pickle.load(open(D+'FE.pkl','rb'))
def fit(X,y,off,lam=50.0,prior=None,iters=12):
    k=X.shape[1]; b=np.zeros(k) if prior is None else prior.copy(); pr=np.zeros(k) if prior is None else prior
    for _ in range(iters):
        p=1/(1+np.exp(-(off+X@b))); w=p*(1-p)
        g=X.T@(y-p)-lam*(b-pr); H=(X*w[:,None]).T@X+lam*np.eye(k)
        step=np.linalg.solve(H,g); b=b+step
        if np.abs(step).max()<1e-6: break
    return b
days=np.sort(df.day.unique()); WARM=28
X=df[FE].to_numpy(); y=df.y.to_numpy(); off=df.off.to_numpy(); dayv=df.day.to_numpy(); coinv=df.coin.to_numpy()
phat=np.full(len(df),np.nan); coins=sorted(df.coin.unique())
t0=time.time(); betas={}
for i,d in enumerate(days):
    if i<WARM: continue
    if (i-WARM)%3==0:    # refit every 3 days on all earlier days
        tr=dayv<d
        bp=fit(X[tr],y[tr],off[tr],lam=20.0)
        bc={c:fit(X[tr&(coinv==c)],y[tr&(coinv==c)],off[tr&(coinv==c)],lam=300.0,prior=bp) for c in coins}
        betas[int(d)]=(bp,bc)
    te=dayv==d
    for c in coins:
        mk=te&(coinv==c)
        phat[mk]=1/(1+np.exp(-(off[mk]+X[mk]@bc[c])))
df['phat']=phat
df.to_pickle(D+'wf_pred.pkl')
print('fit done',time.time()-t0)
print('pooled beta (last):'); print(' '.join(f"{f}:{b:+.3f}" for f,b in zip(FE,bp)))
for c in coins: print(c,' '.join(f"{f}:{b:+.3f}" for f,b in zip(FE[:11],bc[c][:11])))
o=df.dropna(subset=['phat'])
# OOS calibration of the predicted shift
o=o.assign(shift=o.phat-o.mid, res=o.y-o.mid)
o['sb']=pd.cut(o['shift'],[-1,-0.06,-0.04,-0.03,-0.02,-0.01,0,0.01,0.02,0.03,0.04,0.06,1])
print(o.groupby('sb',observed=True).agg(n=('res','size'),pred=('shift','mean'),real=('res','mean')).round(4))
