import pandas as pd, numpy as np, math
D='/tmp/claude-0/-home-user-trading-ai-bot/c8d83796-5074-54b4-ac65-51ae66ae1912/scratchpad/diag/'
df=pd.read_pickle(D+'rows.pkl'); df=df[df.ots>=1788134400]
df=df[(df.side=='yes')&(df.a>=0.05)&(df.a<=0.95)].copy()     # one row per market-minute (YES view); signals are symmetric
df['mid']=(df.a+df.bid)/2
df['res']=df.win-df.mid
df['per']=np.where(df.ots<1790726400,'Sep',np.where(df.ots<1793491200,'Oct','Nov'))
tau=15-df.j
df['r1z']=df.r1/df.vol; df['r3z']=df.r3/(df.vol*math.sqrt(3)); df['r5z']=df.r5/(df.vol*math.sqrt(5))
df['edge_mid']=df.q-df.mid
df['prevz']=df.prev/(df.vol*math.sqrt(15))
feats=['edge_mid','r1z','r3z','r5z','refz','prevz']
df=df.replace([np.inf,-np.inf],np.nan).dropna(subset=feats+['res'])
for f in feats: df[f]=df[f].clip(-4,4) if f!='edge_mid' else df[f].clip(-0.4,0.4)
print(len(df))
def ols(g):
    X=np.c_[np.ones(len(g)),g[feats].to_numpy()]; y=g.res.to_numpy()
    b,_,_,_=np.linalg.lstsq(X,y,rcond=None)
    # day-clustered SE via per-day score sums
    e=y-X@b; XtXi=np.linalg.inv(X.T@X)
    S=np.zeros((X.shape[1],X.shape[1]))
    for d,idx in g.groupby('day').indices.items():
        s=X[idx].T@e[idx]; S+=np.outer(s,s)
    se=np.sqrt(np.diag(XtXi@S@XtXi))
    return b,b/se
for per in ['Sep','Oct','Nov']:
    b,t=ols(df[df.per==per])
    print(per,' '.join(f"{f}:{bb*100:+.2f}c(t{tt:+.1f})" for f,bb,tt in zip(['const']+feats,b,t)))
print('--- by coin (all months)')
for c,g in df.groupby('coin'):
    b,t=ols(g); print(c,' '.join(f"{f}:{bb*100:+.2f}c(t{tt:+.1f})" for f,bb,tt in zip(['const']+feats,b,t)))
print('--- by minute group')
for name,g in df.groupby(pd.cut(df.j,[0,3,6,9,12,14])):
    b,t=ols(g); print(name,' '.join(f"{f}:{bb*100:+.2f}c(t{tt:+.1f})" for f,bb,tt in zip(['const']+feats,b,t)))
