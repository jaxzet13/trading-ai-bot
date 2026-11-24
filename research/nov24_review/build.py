import sys, numpy as np, pandas as pd, pickle, time
sys.path.insert(0,'/home/user/trading-ai-bot')
from kalshi15m import backtest as B, lab2, lab3, data as D
from kalshi15m.fwdscore import FWD_DIR
out={}
t0=time.time()
for s in lab3.COINS:
    try:
        pm=B.Panel(B.build_panel(s)); lab3.add_features(pm,s,"main")
    except Exception as e:
        print(s,'main failed',e); pm=None
    lab3._SPOT.clear()
    lab3._SPOT[(s,"main")]=lab3.Spot(FWD_DIR/f"{s}_spot.csv")
    ref="KXETH15M" if s=="KXBTC15M" else "KXBTC15M"
    lab3._SPOT[(ref,"main")]=lab3.Spot(FWD_DIR/f"{ref}_spot.csv")
    with lab2._source(FWD_DIR):
        pf=B.Panel(B.build_panel(s))
    lab3.add_features(pf,s,"main")
    lab3._SPOT.clear()
    if pm is not None:
        keep=~np.isin(pm.ticker,pf.ticker)
        pm=pm.subset(keep & (pm.open_ts<pf.open_ts.min()))
        p=B.Panel.concat([pm,pf])
    else: p=pf
    out[s]={'ticker':p.ticker,'open_ts':np.asarray(p.open_ts,np.int64),'result':np.asarray(p.result),'P':{k:v.astype(np.float32) if v.dtype==float else v for k,v in p.P.items()}}
    print(s,len(p),'markets',time.strftime('%m-%d',time.gmtime(p.open_ts.min())),time.strftime('%m-%d',time.gmtime(p.open_ts.max())),set(p.result) if len(set(p.result))<6 else '', f'{time.time()-t0:.0f}s',flush=True)
pickle.dump(out,open('/tmp/claude-0/-home-user-trading-ai-bot/c8d83796-5074-54b4-ac65-51ae66ae1912/scratchpad/diag/pool.pkl','wb'))
