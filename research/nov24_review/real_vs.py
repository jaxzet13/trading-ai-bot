import pandas as pd, numpy as np, json, pickle, math
D='/tmp/claude-0/-home-user-trading-ai-bot/c8d83796-5074-54b4-ac65-51ae66ae1912/scratchpad/diag/'
pool=pickle.load(open(D+'pool.pkl','rb'))
bets=json.load(open(D+'bets.json'))
df=pd.read_pickle(D+'wf_pred.pkl')
idx={}
for s,d in pool.items():
    idx[s]={tk:i for i,tk in enumerate(d['ticker'])}
fee=lambda a: 0.07*a*(1-a)
rows=[]
for b in bets:
    s=b['series']; i=idx[s].get(b['ticker'])
    if i is None or not b['minute']: continue
    j=b['minute'][0]   # runner's minute index
    P=pool[s]['P']
    for jj in (j-1,j,j+1):
        if 1<=jj<=14:
            ya=float(P['yes_ask'][i,jj-1]); yb=float(P['yes_bid'][i,jj-1])
            a=ya if b['side']=='yes' else 1-yb
            rows.append({'tk':b['ticker'],'coin':s[2:-3],'m':i,'jrun':j,'jj':jj,'d':jj-j,'candle_a':a,'intent':b['iprice'][0],'fill':b['fprice'][0],'side':b['side'],'pnl1':b['pnl']/b['n'],'n':b['n'],'rule':b['rules'][0]})
r=pd.DataFrame(rows)
for d,g in r.groupby('d'):
    g=g.dropna(subset=['candle_a'])
    print('candle minute = runner minute %+d:'%d, 'n',len(g),'mean(fill - candle ask) c', round(100*(g.fill-g.candle_a).mean(),2), 'median', round(100*(g.fill-g.candle_a).median(),2), 'mean abs', round(100*(g.fill-g.candle_a).abs().mean(),2), ' intent-candle', round(100*(g.intent-g.candle_a).mean(),2))
pickle.dump(r,open(D+'real_rows.pkl','wb'))
