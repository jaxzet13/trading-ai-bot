import pandas as pd, numpy as np, math
D='/tmp/claude-0/-home-user-trading-ai-bot/c8d83796-5074-54b4-ac65-51ae66ae1912/scratchpad/diag/'
df=pd.read_pickle(D+'rows.pkl')
df=df[df.ots>=1788134400].copy()
print(len(df), df.day.nunique(),'days')
def tab(g, by):
    r=g.groupby(by,observed=True).agg(n=('pnl','size'),pnl=('pnl','mean'),win=('win','mean'),a=('a','mean'),q=('q','mean'))
    # cluster by day for t
    dd=g.groupby(list(by if isinstance(by,list) else [by])+['day'],observed=True).pnl.sum().reset_index()
    t=dd.groupby(by,observed=True).pnl.agg(lambda x: x.mean()/x.std(ddof=1)*math.sqrt(len(x)) if len(x)>2 and x.std(ddof=1)>0 else 0)
    r['t_day']=t
    r['pnl_c']=(100*r.pnl).round(2)
    return r[['n','a','q','win','pnl_c','t_day']].round(3)
df['eb']=pd.cut(df.edge,[-1,-0.2,-0.1,-0.05,0,0.03,0.06,0.09,0.12,0.16,0.2,0.3,1])
print('== by model edge (q - ask), all'); print(tab(df,'eb'))
df['ab']=pd.cut(df.a,[0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1])
print('== by ask price, all'); print(tab(df,'ab'))
print('== by minute'); print(tab(df,'j'))
print('== edge>=0.08 by price'); print(tab(df[df.edge>=0.08],'ab'))
print('== edge>=0.08 by minute'); print(tab(df[df.edge>=0.08],'j'))
print('== edge>=0.08 by coin'); print(tab(df[df.edge>=0.08],'coin'))
print('== edge>=0.08 by side'); print(tab(df[df.edge>=0.08],'side'))
df['per']=np.where(df.ots<1790726400,'Sep',np.where(df.ots<1793491200,'Oct','Nov'))
print('== edge>=0.08 by month'); print(tab(df[df.edge>=0.08],'per'))
