"""Three-round Anthropic Message Batches runner for the UTH coverage experiment."""
import argparse,json,hashlib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from uth_ds.scenarios import cases
from uth_ds.budget import scheduled_case,EXPERT_SCENARIOS
from uth_ds import prompts as P
from uth_ds.experiment import SCHEMA
from uth_ds.live import MODELS,BudgetStop,UnresolvedRequest
from uth_ds.batch import BatchLedger,ReplayClient,make_payload,request_key
from uth_run import run as assemble


def selected(suite,scenario_ids,expert_scope):
    cs=[scheduled_case(c,expert_scope) for c in cases(suite)]
    if scenario_ids:
        known={c.get('scenario_id',c['base_profile']) for c in cs}
        if set(scenario_ids)-known:raise ValueError('unknown requested scenario IDs')
        cs=[c for c in cs if c.get('scenario_id',c['base_profile']) in scenario_ids]
    return cs

def spec(model,system,messages,tag,max_tokens=500):return {'payload':make_payload(model,system,messages,0,max_tokens),'tag':tag}

def meta(case,world,sample_id):
    sid=case['id'];wid=world['id'];neutral=case.get('neutral_prompt',False)
    prompt_id=case['base_profile']+':'+case['context_variant'] if neutral else sid
    prefix=SCHEMA+':sample'+str(sample_id)+':'
    return sid,wid,neutral,prompt_id,prefix

def round1_specs(cs,samples,expert_scope,expert_samples):
    out=[]
    for case0 in cs:
      for sample_id in range(samples):
       case=scheduled_case(case0,expert_scope,sample_id,expert_samples)
       for w in case['worlds']:
        public=P.public_context(case);sid,wid,neutral,prompt_id,prefix=meta(case,w,sample_id)
        def tag(x):return prefix+x.replace(sid,prompt_id)
        out += [spec(MODELS['target'],P.CHOICE,[{'role':'user','content':public}],tag(sid+':choice')),
                spec(MODELS['target'],P.BASE,[{'role':'user','content':public}],tag(sid+':adv')),
                spec(MODELS['target'],P.QUESTION,[{'role':'user','content':public}],tag(sid+':question'))]
        retrieved=P.retrieved_context(w,neutral);cal=hashlib.sha256(retrieved.encode()).hexdigest()[:16]
        out.append(spec(MODELS['target'],P.RETRIEVE,[{'role':'user','content':public+'\n'+retrieved}],tag(sid+':retrieve:'+cal)))
        fullcontext=public+'\n'+retrieved+'\nVERIFIED PERSONAL FACTS: '+P.private_context(w)
        if case.get('run_expert',True):out.append(spec(MODELS['expert'],P.DEFER,[{'role':'user','content':fullcontext}],tag(sid+':defer:'+str(wid)),max_tokens=800))
        out.append(spec(MODELS['target'],P.BASE,[{'role':'user','content':fullcontext}],tag(sid+':full:'+str(wid))))
    return unique(out)

def completed_text(ledger,s):
    key=request_key(s['payload'],s['tag']);c=ledger.state['calls'].get(key)
    if not c or c.get('status')!='complete':raise UnresolvedRequest('dependency not completed: '+s['tag'])
    return c['text']

def question_spec(case,w,sample_id):
    public=P.public_context(case);sid,wid,neutral,prompt_id,prefix=meta(case,w,sample_id)
    return spec(MODELS['target'],P.QUESTION,[{'role':'user','content':public}],prefix+(sid+':question').replace(sid,prompt_id))

def student_specs(ledger,cs,samples,expert_scope,expert_samples):
    out=[]
    for case0 in cs:
      for sample_id in range(samples):
       case=scheduled_case(case0,expert_scope,sample_id,expert_samples)
       for w in case['worlds']:
        sid,wid,neutral,prompt_id,prefix=meta(case,w,sample_id);q=completed_text(ledger,question_spec(case,w,sample_id))
        tag=prefix+(sid+':student:'+str(w['design'].budgets)).replace(sid,prompt_id)
        out.append(spec(MODELS['student'],P.STUDENT,[{'role':'user','content':P.private_context(w)+'\nQUESTION: '+q}],tag))
    return unique(out)

def student_spec_for(ledger,case,w,sample_id):
    sid,wid,neutral,prompt_id,prefix=meta(case,w,sample_id);q=completed_text(ledger,question_spec(case,w,sample_id))
    tag=prefix+(sid+':student:'+str(w['design'].budgets)).replace(sid,prompt_id)
    return spec(MODELS['student'],P.STUDENT,[{'role':'user','content':P.private_context(w)+'\nQUESTION: '+q}],tag)

def clarify_specs(ledger,cs,samples,expert_scope,expert_samples):
    out=[]
    for case0 in cs:
      for sample_id in range(samples):
       case=scheduled_case(case0,expert_scope,sample_id,expert_samples)
       for w in case['worlds']:
        public=P.public_context(case);sid,wid,neutral,prompt_id,prefix=meta(case,w,sample_id)
        q=completed_text(ledger,question_spec(case,w,sample_id));ans=completed_text(ledger,student_spec_for(ledger,case,w,sample_id))
        tag=prefix+(sid+':clarify:'+str(w['design'].budgets)).replace(sid,prompt_id)
        out.append(spec(MODELS['target'],P.CLARIFY,[{'role':'user','content':public},{'role':'assistant','content':q},{'role':'user','content':ans}],tag))
    return unique(out)

def unique(specs):
    d={}
    for s in specs:d.setdefault(request_key(s['payload'],s['tag']),s)
    return list(d.values())

def finish_stage(ledger,specs,stage,batch_size,wait):
    while True:
        # Resume any already-submitted batch first.
        pending=[]
        for bid,b in ledger.state['batches'].items():
            if b.get('stage')==stage and b.get('phase')==ledger.phase and b.get('status')!='reconciled':pending.append(bid)
        if pending:
            for bid in pending:
                if not ledger.poll(bid,wait=wait):return False
            continue
        missing=[s for s in specs if ledger.state['calls'].get(request_key(s['payload'],s['tag']),{}).get('status')!='complete']
        if not missing:return True
        bid=ledger.submit(missing,stage,batch_size)
        if bid is None:
            # Existing non-complete records without a recoverable batch are intentionally fatal.
            raise UnresolvedRequest('Stage has unresolved calls but no submit-able requests; inspect ledger.')
        if not ledger.poll(bid,wait=wait):return False

def run_batch(out,ledger_path,phase='pilot',samples=2,suite='coverage',scenario_ids=None,expert_scope='all',expert_samples=1,
              phase_budget=5,total_budget=100,batch_size=2000,poll_seconds=30,wait=True,transport=None):
    if suite!='coverage':raise ValueError('batch live supports coverage suite only')
    if not isinstance(samples,int) or samples<1:raise ValueError('samples must be positive')
    if not 1<=expert_samples<=samples:raise ValueError('expert samples must be between one and target samples')
    ids=scenario_ids
    if phase=='pilot':
        ids=ids or list(EXPERT_SCENARIOS)
        if len(ids)>6 or samples!=1:raise ValueError('pilot: at most6 scenarios and --samples1 required')
    cs=selected(suite,ids,expert_scope)
    ledger=BatchLedger(ledger_path,phase,phase_budget,total_budget,transport=transport,poll_seconds=poll_seconds)
    try:
        stages=[('round1',lambda:round1_specs(cs,samples,expert_scope,expert_samples)),
                ('round2_student',lambda:student_specs(ledger,cs,samples,expert_scope,expert_samples)),
                ('round3_clarify',lambda:clarify_specs(ledger,cs,samples,expert_scope,expert_samples))]
        for name,fn in stages:
            specs=fn()
            if not finish_stage(ledger,specs,name,batch_size,wait):
                return {'submitted':True,'waiting':True,'stage':name,'ledger':str(ledger.path)}
        replay=ReplayClient(ledger.state)
        rows=assemble(out,samples,suite,ids,expert_scope,expert_samples,replay)
        return {'submitted':True,'waiting':False,'assembled_instances':len(rows),'ledger':str(ledger.path)}
    finally:
        ledger.report(Path(ledger_path).parent/(phase+'_cost_report.json'));ledger.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description='UTH experiment via Anthropic Message Batches API')
    p.add_argument('--out',default='data_uth_batch_v4');p.add_argument('--samples',type=int,default=2)
    p.add_argument('--suite',choices=['coverage'],default='coverage');p.add_argument('--scenario-id',action='append')
    p.add_argument('--expert-scope',choices=['sentinels','all'],default='all');p.add_argument('--expert-samples',type=int,default=1)
    p.add_argument('--phase',choices=['pilot','full'],default='pilot');p.add_argument('--ledger',default='data_uth_budget_batch_v4/ledger_v4.json')
    p.add_argument('--phase-budget-usd',type=float);p.add_argument('--total-budget-usd',type=float,default=100)
    p.add_argument('--batch-size',type=int,default=2000);p.add_argument('--poll-seconds',type=int,default=30);p.add_argument('--submit-only',action='store_true')
    a=p.parse_args()
    if a.phase=='full':
        report_path=Path(a.ledger).parent/'pilot_cost_report.json'
        if not report_path.exists():p.error('full phase requires pilot report with same shared ledger')
        report=json.loads(report_path.read_text());forecast=report.get('projection_with_30_percent_margin_usd')
        if forecast is None or forecast+report.get('ledger_total_usd',0)>a.total_budget_usd:p.error('pilot forecast plus safety margin exceeds total budget; review design before full run')
    try:
        r=run_batch(a.out,a.ledger,a.phase,a.samples,a.suite,a.scenario_id,a.expert_scope,a.expert_samples,
                    a.phase_budget_usd or (5 if a.phase=='pilot' else 100),a.total_budget_usd,a.batch_size,a.poll_seconds,not a.submit_only)
        print(json.dumps(r,indent=2))
    except BudgetStop as e:print(str(e))
