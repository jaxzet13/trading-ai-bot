import sys, numpy as np, time
sys.path.insert(0,'/home/user/trading-ai-bot')
from kalshi15m import edge as E
panels=E.load_panels(log=lambda m:None)
def extra(P):
    ya=np.asarray(P['yes_ask'],float); yb=np.asarray(P['yes_bid'],float)
    with np.errstate(all='ignore'):
        lm=E._logit((ya+yb)/2)
    def lag(a,k):
        out=np.full_like(a,np.nan); out[:,k:]=a[:,:-k]; return out
    dm1=np.clip(lm-lag(lm,1),-2,2); dm3=np.clip(lm-lag(lm,3),-3,3)
    spr=np.clip(ya-yb,0,0.2)
    return {'dm1':dm1,'dm3':dm3}
def rows_plus(names):
    cols={k:[] for k in ('coin','m','j','ots','ya','yb','y','off')}; Xs=[]
    for s,d in panels.items():
        X,off,ok=E.features(d['P']); ex=extra(d['P'])
        Xe=np.stack([ex[n] for n in names],axis=-1) if names else np.zeros(X.shape[:2]+(0,))
        ok=ok&(d['open_ts']>=E.COMMON_START)[:,None]&np.isfinite(Xe).all(-1)
        mi,ji=np.nonzero(ok)
        Xs.append(np.concatenate([X[mi,ji],Xe[mi,ji]],axis=1))
        cols['coin'].append(np.full(len(mi),s)); cols['m'].append(mi); cols['j'].append(E.MIN[ji]); cols['ots'].append(d['open_ts'][mi])
        cols['ya'].append(np.asarray(d['P']['yes_ask'],float)[mi,ji]); cols['yb'].append(np.asarray(d['P']['yes_bid'],float)[mi,ji])
        cols['y'].append((d['result'][mi]==1).astype(float)); cols['off'].append(off[mi,ji])
    R={k:np.concatenate(v) for k,v in cols.items()}; R['X']=np.concatenate(Xs); R['day']=R['ots']//86400
    return R
live=['KXDOGE15M','KXNEAR15M','KXSOL15M','KXXRP15M','KXZEC15M']
for names in ([],['dm1'],['dm3'],['dm1','dm3']):
    R=rows_plus(names); p,td=E.walk_predict(R,log=lambda m:None)
    for thr in (0.05,):
        b=E.bets(R,p,thr); a=E.summary(b,td); l=E.summary(E._sub(b,np.isin(b['coin'],live)),td)
        h=len(td)//2; l1=E.summary(E._sub(b,np.isin(b['coin'],live)),td[:h]); l2=E.summary(E._sub(b,np.isin(b['coin'],live)),td[h:])
        print(f"{str(names):18s} all9: {a['per_day']:5.1f}/day {a['cents_per_bet']:+.2f}c t{a['t']:.2f} ${a['usd_per_day']:+.2f}/d | 5 coins: {l['per_day']:5.1f}/day {l['cents_per_bet']:+.2f}c t{l['t']:.2f} ${l['usd_per_day']:+.2f}/d dd{l['max_drawdown']} | halves ${l1['usd_per_day']:+.2f} / ${l2['usd_per_day']:+.2f}",flush=True)
