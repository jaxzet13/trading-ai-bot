import sys, numpy as np
sys.path.insert(0,'/home/user/trading-ai-bot')
from kalshi15m import edge as E
R=E.rows(E.load_panels(log=lambda m:None)); p,td=E.walk_predict(R,log=lambda m:None)
live=['KXDOGE15M','KXNEAR15M','KXSOL15M','KXXRP15M','KXZEC15M']
b=E.bets(R,p); b=E._sub(b,np.isin(b['coin'],live))
order=np.lexsort((b['j'],b['ots'])); b={k:v[order] for k,v in b.items()}
rank=np.zeros(len(b['pnl']),int); seen={}
for i,(o,s) in enumerate(zip(b['ots'],b['side'])):
    k=(int(o),int(s)); seen[k]=seen.get(k,0)+1; rank[i]=seen[k]
anyrank=np.zeros(len(b['pnl']),int); seen={}
for i,o in enumerate(b['ots']):
    seen[int(o)]=seen.get(int(o),0)+1; anyrank[i]=seen[int(o)]
for r in (1,2,3,4):
    m=rank==r if r<4 else rank>=4
    print(f"same-side bet #{r}{'+' if r==4 else ''} in its window: n={m.sum():5d} {100*b['pnl'][m].mean():+.2f}c/bet")
for cap in (1,2,3,99):
    s=E.summary(E._sub(b,rank<=cap),td)
    print(f"cap {cap:2d} same-side bets a window: {s['per_day']:5.1f}/day {s['cents_per_bet']:+.2f}c ${s['usd_per_day']:+.2f}/day t {s['t']} worst day {s['worst_day']} maxDD {s['max_drawdown']}")
# opposite-side same window (hedged) share
print('windows with bets:',len(set(b['ots'])),' bets:',len(b['pnl']),' windows with 3+ same-side:', sum(1 for v in seen.values() if v>=3))
