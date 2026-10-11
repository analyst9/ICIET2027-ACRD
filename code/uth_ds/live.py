"""Serial Anthropic adapter. Durable reservations precede every paid request."""
import os,json,hashlib,urllib.request
from pathlib import Path
from decimal import Decimal as D
from datetime import datetime,timezone
MODELS={'target':'claude-haiku-4-5-20251001','student':'claude-haiku-4-5-20251001','expert':'claude-sonnet-4-6'}
PRICES={MODELS['target']:{'input':1,'output':5,'write':1.25,'read':.1},MODELS['expert']:{'input':3,'output':15,'write':3.75,'read':.3}}
class BudgetStop(RuntimeError):pass
class UnresolvedRequest(RuntimeError):pass
class LiveClient:
    mock=False
    def __init__(self,ledger,phase='pilot',phase_limit=5,total_limit=100,transport=None):
        self.path=Path(ledger);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.phase=phase;self.phase_limit=D(str(phase_limit));self.total_limit=D(str(total_limit));self.transport=transport or self.http
        if phase not in ('pilot','full') or not 0<self.total_limit<=100 or not 0<self.phase_limit<= (5 if phase=='pilot' else 100):raise ValueError('invalid budget')
        self.lock=self.path.with_suffix('.lock');self.fd=os.open(self.lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        try:
            self.state=json.loads(self.path.read_text()) if self.path.exists() else {'version':1,'prices':PRICES,'calls':{}}
            if self.state['prices']!=PRICES:raise ValueError('ledger pricing mismatch')
            if any(c['status']=='pending' for c in self.state['calls'].values()):raise UnresolvedRequest('Unresolved paid request: inspect Console before any continuation; no automatic retry.')
        except BaseException:self.close();raise
        self.n_calls=0;self.usage={}
    def close(self):
        if getattr(self,'fd',None) is not None:os.close(self.fd);self.fd=None;self.lock.unlink()
    def save(self):
        tmp=self.path.with_suffix('.tmp')
        with tmp.open('w') as f:json.dump(self.state,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(tmp,self.path)
    def http(self,payload):
        key=os.environ.get('ANTHROPIC_API_KEY')
        if not key:raise ValueError('ANTHROPIC_API_KEY is missing')
        req=urllib.request.Request('https://api.anthropic.com/v1/messages',json.dumps(payload).encode(),{'x-api-key':key,'anthropic-version':'2023-06-01','content-type':'application/json'})
        with urllib.request.urlopen(req,timeout=120) as r:return json.load(r)
    def call(self,model,system,messages,temperature=0,max_tokens=500,tag='',mock_fn=None):
        if model not in PRICES or not 1<=max_tokens<=1000:raise ValueError('unsupported model/output budget')
        # Same scientific prompt, with cache annotation; never append information to one role only.
        payload={'model':model,'system':system,'messages':messages,'max_tokens':max_tokens,'cache_control':{'type':'ephemeral'}}
        if len(json.dumps(payload,ensure_ascii=False).encode('utf-8'))>100000:raise ValueError('request too large for conservative200K reservation envelope')
        key=hashlib.sha256(json.dumps([payload,tag],sort_keys=True).encode()).hexdigest()
        old=self.state['calls'].get(key)
        if old:return old['text']
        if self.transport==self.http and not os.environ.get('ANTHROPIC_API_KEY'):raise ValueError('ANTHROPIC_API_KEY is missing')
        p=PRICES[model]
        # Reserve the entire 200K context at the most expensive 5-minute input rate,
        # plus maximum output. No estimated token count is treated as a hard upper bound.
        reserve=(D('200000')*D(str(max(p['input'],p['write'],p['read'])))+D(max_tokens)*D(p['output']))/D(1000000)
        total=sum(D(c['cost_usd']) for c in self.state['calls'].values())
        phase=sum(D(c['cost_usd']) for c in self.state['calls'].values() if c['phase']==self.phase)
        if total+reserve>self.total_limit or phase+reserve>self.phase_limit:raise BudgetStop('Stopped before paid request: insufficient reserved budget.')
        self.state['calls'][key]={'status':'pending','phase':self.phase,'model':model,'tag':tag,'cost_usd':str(reserve),'reserved_usd':str(reserve),'time':datetime.now(timezone.utc).isoformat()};self.save()
        response=self.transport(payload) # no automatic retries: timeout may have incurred cost
        u=response['usage'];names=('input_tokens','output_tokens','cache_creation_input_tokens','cache_read_input_tokens')
        usage={n:int(u.get(n,0) or 0) for n in names}
        if any(v<0 for v in usage.values()) or sum(usage[n] for n in names if n!='output_tokens')>200000 or usage['output_tokens']>max_tokens:raise UnresolvedRequest('Usage exceeds reserved envelope; halt and reconcile billing.')
        cost=sum(D(usage[n])*D(str(p[r])) for n,r in zip(names,('input','output','write','read')))/D(1000000)
        text=''.join(b['text'] for b in response['content'] if b['type']=='text')
        self.state['calls'][key].update(status='complete',cost_usd=str(cost),usage=usage,text=text,response_id=response.get('id'),stop_reason=response.get('stop_reason'))
        self.save();self.n_calls+=1;self.usage[key]=usage
        return text
    def report(self,out):
        by={}
        for c in self.state['calls'].values():
            b=by.setdefault(c['model'],{'completed_calls':0,'cost_usd':0.,'tokens':{},'pending_reserved_usd':0.})
            if c['status']=='pending':b['pending_reserved_usd']+=float(c['cost_usd']);continue
            b['completed_calls']+=1;b['cost_usd']+=float(c['cost_usd'])
            for k,v in c['usage'].items():b['tokens'][k]=b['tokens'].get(k,0)+v
        projected=0.;complete=True
        for model,n in ((MODELS['target'],19648),(MODELS['expert'],3040)):
            b=by.get(model,{})
            if not b.get('completed_calls'):complete=False;continue
            mean=b['cost_usd']/b['completed_calls'];b['mean_cost_per_call_usd']=mean;b['planned_full_calls']=n;projected+=mean*n
        report={'by_model':by,'ledger_total_usd':sum(float(c['cost_usd']) for c in self.state['calls'].values()),'projected_full_usd':projected if complete else None,'projection_with_30_percent_margin_usd':projected*1.3 if complete else None,'projection_is_not_a_guarantee':True,'limitation':'Six diagnostic scenarios are not a representative token-cost sample; cache hit rates can differ in full run. Input/output reservations use a conservative200K context envelope. USD token charges exclude taxes and other Console use.','prices_usd_per_million':PRICES,'price_source':'https://platform.claude.com/docs/en/about-claude/pricing','price_checked':'2026-10-02'}
        Path(out).write_text(json.dumps(report,indent=2));return report
