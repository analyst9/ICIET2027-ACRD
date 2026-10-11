"""Anthropic Message Batches adapter with durable budget reservations and prompt caching.

The adapter keeps the scientific prompts/models unchanged, but submits paid inference
through /v1/messages/batches.  Clarification is handled by the batch runner in three
causal rounds (question -> simulated student -> final clarification).
"""
import os,json,hashlib,time,urllib.request,urllib.error
from pathlib import Path
from decimal import Decimal as D
from datetime import datetime,timezone
from .live import MODELS,PRICES,BudgetStop,UnresolvedRequest

BATCH_FACTOR=D('0.5')
CACHE_TTL='1h'
# Prompt-caching multipliers documented by Anthropic.
WRITE_5M=D('1.25'); WRITE_1H=D('2'); READ=D('0.1')
API='https://api.anthropic.com'


def make_payload(model,system,messages,temperature=0,max_tokens=500):
    if model not in PRICES or not 1<=max_tokens<=1000:raise ValueError('unsupported model/output budget')
    # temperature argument is retained for interface compatibility but intentionally omitted.
    # Effective API default is 1.0; no claim of deterministic generation.
    payload={'model':model,'system':system,'messages':messages,'max_tokens':max_tokens}
    if model != MODELS['expert']:
        payload['cache_control']={'type':'ephemeral','ttl':CACHE_TTL}
    return payload

def request_key(payload,tag):
    return hashlib.sha256(json.dumps([payload,tag],sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def payload_key(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def text_from_message(msg):
    return ''.join(b.get('text','') for b in msg.get('content',[]) if b.get('type')=='text')

def usage_cost(model,usage):
    """Actual USD list cost after the 50% Batch modifier, including cache TTL split."""
    p=PRICES[model];base=D(str(p['input']));out=D(str(p['output']))
    inp=D(int(usage.get('input_tokens',0) or 0));outn=D(int(usage.get('output_tokens',0) or 0))
    read=D(int(usage.get('cache_read_input_tokens',0) or 0))
    cc=usage.get('cache_creation') or {}
    c5=D(int(cc.get('ephemeral_5m_input_tokens',0) or 0))
    c1=D(int(cc.get('ephemeral_1h_input_tokens',0) or 0))
    legacy=D(int(usage.get('cache_creation_input_tokens',0) or 0))
    if c5+c1==0 and legacy: c1=legacy  # requested TTL is 1h; compatibility fallback.
    raw=inp*base + outn*out + c5*base*WRITE_5M + c1*base*WRITE_1H + read*base*READ
    return raw/D(1000000)*BATCH_FACTOR

def reserve_cost(model,input_tokens,max_tokens):
    """Hard pre-submit envelope: all counted input treated as 1h cache-write + max output."""
    p=PRICES[model];base=D(str(p['input']));out=D(str(p['output']))
    return (D(input_tokens)*base*WRITE_1H + D(max_tokens)*out)/D(1000000)*BATCH_FACTOR

class BatchLedger:
    def __init__(self,path,phase='pilot',phase_limit=5,total_limit=100,transport=None,poll_seconds=30):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.phase=phase;self.phase_limit=D(str(phase_limit));self.total_limit=D(str(total_limit))
        if phase not in ('pilot','full') or not 0<self.total_limit<=100 or not 0<self.phase_limit<=(5 if phase=='pilot' else 100):raise ValueError('invalid budget')
        self.poll_seconds=max(1,int(poll_seconds));self.transport=transport or self.http
        self.lock=self.path.with_suffix('.lock');self.fd=os.open(self.lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        try:
            self.state=json.loads(self.path.read_text(encoding='utf-8-sig')) if self.path.exists() else {'version':2,'prices':PRICES,'calls':{},'batches':{},'token_counts':{}}
            if self.state.get('prices')!=PRICES:raise ValueError('ledger pricing mismatch')
            self.state.setdefault('batches',{});self.state.setdefault('token_counts',{})
        except BaseException:self.close();raise
    def close(self):
        if getattr(self,'fd',None) is not None:
            os.close(self.fd);self.fd=None
            try:self.lock.unlink()
            except FileNotFoundError:pass
    def save(self):
        tmp=self.path.with_suffix('.tmp')
        with tmp.open('w',encoding='utf-8') as f:
            json.dump(self.state,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(tmp,self.path)
    def headers(self):
        key=os.environ.get('ANTHROPIC_API_KEY')
        if not key:raise ValueError('ANTHROPIC_API_KEY is missing')
        return {'x-api-key':key,'anthropic-version':'2023-06-01','content-type':'application/json'}
    def http(self,method,path,payload=None,raw=False):
        data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode('utf-8')
        req=urllib.request.Request(API+path,data=data,headers=self.headers(),method=method)
        try:
            with urllib.request.urlopen(req,timeout=180) as r:
                blob=r.read()
        except urllib.error.HTTPError as e:
            detail=e.read().decode('utf-8','replace')
            raise RuntimeError(f'Anthropic HTTP {e.code}: {detail[:1000]}') from e
        if raw:return blob.decode('utf-8')
        return json.loads(blob)
    def count_tokens(self,payload):
        pk=payload_key(payload)
        if pk in self.state['token_counts']:return int(self.state['token_counts'][pk])
        body={k:payload[k] for k in ('model','system','messages','cache_control') if k in payload}
        response=self.transport('POST','/v1/messages/count_tokens',body,False)
        n=int(response['input_tokens'])
        if n<0:raise ValueError('negative token count')
        self.state['token_counts'][pk]=n;self.save();return n
    def spent(self,phase=None):
        vals=[D(c.get('cost_usd','0')) for c in self.state['calls'].values() if c.get('status')=='complete' and (phase is None or c.get('phase')==phase)]
        return sum(vals,D('0'))
    def reserved_pending(self,phase=None):
        vals=[D(c.get('reserved_usd','0')) for c in self.state['calls'].values() if c.get('status')=='pending' and (phase is None or c.get('phase')==phase)]
        return sum(vals,D('0'))
    def remaining(self):
        total=self.total_limit-self.spent()-self.reserved_pending()
        phase=self.phase_limit-self.spent(self.phase)-self.reserved_pending(self.phase)
        return min(total,phase)
    def prepare(self,spec):
        payload=spec['payload'];tag=spec['tag'];key=request_key(payload,tag)
        old=self.state['calls'].get(key)
        if old:return key,old
        n=self.count_tokens(payload);reserve=reserve_cost(payload['model'],n,payload['max_tokens'])
        return key,{'status':'new','phase':self.phase,'model':payload['model'],'tag':tag,
                    'input_tokens_counted':n,'reserved_usd':str(reserve),'payload_hash':payload_key(payload)}
    def submit(self,specs,stage,max_requests=2000):
        """Submit one budget-safe chunk. Returns batch id, or None if nothing new."""
        requests=[];records=[];reserve_sum=D('0')
        for spec in specs:
            key,rec=self.prepare(spec)
            if rec.get('status')!='new':continue
            r=D(rec['reserved_usd'])
            if requests and (len(requests)>=max_requests or reserve_sum+r>self.remaining()):break
            if not requests and r>self.remaining():raise BudgetStop('Stopped before batch submission: insufficient reserved budget.')
            custom_id='r_'+key[:60]
            requests.append({'custom_id':custom_id,'params':spec['payload']});records.append((key,custom_id,rec));reserve_sum+=r
        if not requests:return None
        # Reserve durably before the network side effect.
        batch_local='pending_'+hashlib.sha256((''.join(r[0] for r in records)+datetime.now(timezone.utc).isoformat()).encode()).hexdigest()[:24]
        now=datetime.now(timezone.utc).isoformat()
        for key,cid,rec in records:
            self.state['calls'][key]={**rec,'status':'pending','custom_id':cid,'batch_id':batch_local,'stage':stage,'time':now}
        self.state['batches'][batch_local]={'status':'submitting','phase':self.phase,'stage':stage,'reserved_usd':str(reserve_sum),'request_count':len(requests),'created_at':now}
        self.save()
        try:response=self.transport('POST','/v1/messages/batches',{'requests':requests},False)
        except BaseException as e:
            # We cannot know whether the server accepted a timed-out POST. Halt for manual reconciliation.
            self.state['batches'][batch_local]['status']='submission_unknown';self.state['batches'][batch_local]['error']=repr(e);self.save()
            raise UnresolvedRequest('Batch submission outcome unknown; inspect Anthropic Console before continuation.') from e
        bid=response['id']
        self.state['batches'][bid]={**self.state['batches'].pop(batch_local),'status':response.get('processing_status','in_progress'),'api_response':response}
        for key,_,_ in records:self.state['calls'][key]['batch_id']=bid
        self.save();return bid
    def poll(self,bid,wait=True):
        b=self.state['batches'][bid]
        if not bid.startswith('msgbatch_'):
            raise UnresolvedRequest('Submission outcome unknown for local batch '+bid+'; reconcile against the API batch list before resuming. No automatic resubmission.')
        while True:
            status=self.transport('GET','/v1/messages/batches/'+bid,None,False)
            b['status']=status.get('processing_status');b['last_status']=status;b['checked_at']=datetime.now(timezone.utc).isoformat();self.save()
            if b['status']=='ended':break
            if not wait:return False
            time.sleep(self.poll_seconds)
        raw=self.transport('GET','/v1/messages/batches/'+bid+'/results',None,True)
        bycid={c.get('custom_id'):c for c in self.state['calls'].values() if c.get('batch_id')==bid}
        seen=set()
        for line in raw.splitlines():
            if not line.strip():continue
            item=json.loads(line);cid=item['custom_id'];seen.add(cid)
            c=bycid.get(cid)
            if c is None:raise UnresolvedRequest('Unknown custom_id in batch results')
            result=item['result']
            if result.get('type')!='succeeded':
                c['status']='error';c['result']=result;c['cost_usd']='0';continue
            msg=result['message'];usage=msg.get('usage',{})
            cost=usage_cost(c['model'],usage)
            c.update(status='complete',cost_usd=str(cost),usage=usage,text=text_from_message(msg),response_id=msg.get('id'),stop_reason=msg.get('stop_reason'),completed_at=datetime.now(timezone.utc).isoformat())
        missing=set(bycid)-seen
        if missing:raise UnresolvedRequest('Batch ended but some custom_ids are absent from results')
        b['status']='reconciled';b['reconciled_at']=datetime.now(timezone.utc).isoformat();self.save()
        errors=[c for c in bycid.values() if c.get('status')!='complete']
        if errors:raise UnresolvedRequest(f'{len(errors)} batch requests did not succeed; inspect ledger before retrying.')
        return True
    def pending_batches(self):
        return [bid for bid,b in self.state['batches'].items() if b.get('status') not in ('reconciled',)]
    def report(self,out):
        by={}
        for c in self.state['calls'].values():
            b=by.setdefault(c['model'],{'completed_calls':0,'cost_usd':0.,'tokens':{},'pending_reserved_usd':0.})
            if c.get('status')=='pending':b['pending_reserved_usd']+=float(c.get('reserved_usd',0));continue
            if c.get('status')!='complete':continue
            b['completed_calls']+=1;b['cost_usd']+=float(c['cost_usd'])
            u=c.get('usage',{})
            for k in ('input_tokens','output_tokens','cache_creation_input_tokens','cache_read_input_tokens'):
                b['tokens'][k]=b['tokens'].get(k,0)+int(u.get(k,0) or 0)
            cc=u.get('cache_creation') or {}
            for k in ('ephemeral_5m_input_tokens','ephemeral_1h_input_tokens'):
                b['tokens'][k]=b['tokens'].get(k,0)+int(cc.get(k,0) or 0)
        projected=0.;complete=True
        for model,n in ((MODELS['target'],19648),(MODELS['expert'],3040)):
            b=by.get(model,{})
            if not b.get('completed_calls'):complete=False;continue
            mean=b['cost_usd']/b['completed_calls'];b['mean_cost_per_call_usd']=mean;b['planned_full_calls']=n;projected+=mean*n
        report={'mode':'anthropic_message_batches','cache_ttl':'1h','expert_prompt_cache':'disabled','temperature_sent':False,'documented_api_default_temperature':1.0,'batch_discount':0.5,'by_model':by,
                'ledger_total_usd':float(self.spent()),'pending_reserved_usd':float(self.reserved_pending()),
                'projected_full_usd':projected if complete else None,
                'projection_with_30_percent_margin_usd':projected*1.3 if complete else None,
                'projection_is_not_a_guarantee':True,
                'limitation':'Batch cache hits are best-effort and batches may take up to 24h. Pre-submit reservations use exact Token Count API input tokens, price all input at the more expensive 1h cache-write rate, and reserve max output. Anthropic notes Workspace spend limits can be exceeded slightly by high-throughput batches; this ledger therefore also chunks submissions below the local cap.',
                'prices_usd_per_million_standard':PRICES,'price_checked':'2026-10-02'}
        Path(out).write_text(json.dumps(report,indent=2));return report

class ReplayClient:
    """Read-only client used to assemble/scorе results after all paid batch calls complete."""
    mock=False;execution_mode='batch'
    def __init__(self,state):self.state=state;self.n_calls=0;self.usage={}
    def call(self,model,system,messages,temperature=0,max_tokens=500,tag='',mock_fn=None):
        payload=make_payload(model,system,messages,temperature,max_tokens);key=request_key(payload,tag)
        c=self.state['calls'].get(key)
        if not c or c.get('status')!='complete':raise UnresolvedRequest('Missing completed batched response for '+tag)
        return c['text']
