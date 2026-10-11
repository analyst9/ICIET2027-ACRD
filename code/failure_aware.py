"""Failure-aware sensitivity metric (Opt. % and penalized regret) for Table I.
Usage: python failure_aware.py data_uth_batch_v4_full_final/results.jsonl oracle.json
Worlds whose informed optimum does not complete within the horizon are excluded.
Format failures, illegal declarations and noncompletion count as failures (penalty P semesters).
Bootstrap: 2,000 resamples of academic records, seed 20261003.
"""
import json,collections,random,sys
A=['advise','clarify','retrieve','full','defer']
ORC=json.load(open(sys.argv[2]))  # world oracle from oracle.py, independent of responses
rows=[]
for l in open(sys.argv[1],encoding='utf-8'):
    r=json.loads(l)
    if ORC[f"{r['case']}|{r['world']}"] is None: continue
    sched=r['outcomes']['defer']['completion_status']!='not_scheduled'
    for a in A:
        o=r['outcomes'][a]
        if o['completion_status']=='not_scheduled': continue
        ok=o['completion_status']=='completed' and o['regret_semesters'] is not None
        rows.append((r['academic_record_id'],a,ok,o['regret_semesters'] if ok else None,sched,r['objective']))
def stats(rs,P):
    n=len(rs); opt=sum(1 for x in rs if x[2] and x[3]==0)
    pen=sum((x[3] if x[2] else P) for x in rs)
    return n,100*opt/n,pen/n
recs=sorted({x[0] for x in rows})
out={}
for subset in ['all','expert_sched']:
  for a in A:
    rs=[x for x in rows if x[1]==a and (subset=='all' or x[4])]
    n,opt,p2=stats(rs,2); _,_,p1=stats(rs,1); _,_,p3=stats(rs,3)
    out[(subset,a)]=dict(n=n,opt=opt,pen1=p1,pen2=p2,pen3=p3)
agg=collections.defaultdict(lambda:collections.defaultdict(lambda:[0,0,0]))
for x in rows:
    for subset in (['all','expert_sched'] if x[4] else ['all']):
        c=agg[x[0]][(subset,x[1])]; c[0]+=1; c[1]+=(x[2] and x[3]==0); c[2]+=(x[3] if x[2] else 2)
random.seed(20261003); B=2000; boot=collections.defaultdict(list)
for b in range(B):
    tot=collections.defaultdict(lambda:[0,0,0])
    for _ in recs:
        for k,c in agg[random.choice(recs)].items():
            t=tot[k]; t[0]+=c[0]; t[1]+=c[1]; t[2]+=c[2]
    for k,t in tot.items(): boot[k].append((100*t[1]/t[0], t[2]/t[0]))
def ci(v): v=sorted(v); return round(v[int(.025*len(v))],3),round(v[int(.975*len(v))-1],3)
for k,v in out.items():
    b=boot[k]; print(k,{kk:round(vv,3) for kk,vv in v.items()},'optCI',ci([x[0] for x in b]),'pen2CI',ci([x[1] for x in b]))
