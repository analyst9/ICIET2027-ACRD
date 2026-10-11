"""Four actions + FULL; descriptive outcomes with explicit information sets and references."""
import json,re,hashlib,unicodedata
from dataclasses import replace
from functools import lru_cache
from . import prompts as P
from .rules import validate_declaration
from .solver import information_reference,first_action_value,solve
from .scenarios import compatible
SCHEMA='uth_ds_llm_descriptive_5'
ACTIONS=('advise','clarify','retrieve','defer','full')

def parse(text):
    raw=text.strip();wrapper='plain'
    m=re.fullmatch(r'```(?:json)?\s*(.*?)\s*```',raw,re.S|re.I)
    if m:raw=m.group(1);wrapper='fenced'
    try:o=json.loads(raw)
    except (TypeError,ValueError):return {'valid':False,'error':'invalid_json','courses':None,'wrapper':wrapper}
    if not isinstance(o,dict) or not isinstance(o.get('courses'),list) or not all(isinstance(c,str) for c in o['courses']):
        return {'valid':False,'error':'invalid_schema','courses':None,'wrapper':wrapper}
    return {'valid':True,'error':None,'courses':[c.strip().upper() for c in o['courses']],'wrapper':wrapper}

def parse_choice(text):
    raw=text.strip()
    m=re.fullmatch(r'```(?:json)?\s*(.*?)\s*```',raw,re.S|re.I)
    if m:raw=m.group(1)
    try:o=json.loads(raw)
    except (TypeError,ValueError):return {'valid':False,'action':None,'reason':None}
    a=o.get('action') if isinstance(o,dict) else None
    valid=isinstance(a,str) and a.lower() in ('advise','clarify','retrieve','defer')
    return {'valid':valid,'action':a.lower() if valid else None,'reason':o.get('reason') if isinstance(o,dict) else None}

def capacity_disclosed(answer,hours):
    """Conservative bilingual numeric disclosure check; retain texts for human audit."""
    text=''.join(c for c in unicodedata.normalize('NFD',answer.casefold())
                 if not unicodedata.combining(c))
    # Explicit ignorance, negation and required (rather than available) hours
    # must not become successful disclosures merely by mentioning the true number.
    if re.search(r"\b(?:not|cannot|can't|dont|don't|unknown|unsure|need|needs|required|require|δεν|οχι|αγνωστ|χρειαζ|απαιτ)\w*\b",text):
        return False
    pattern=r'\b(\d+(?:[.,]\d+)?)\s*(?:(?:total|συνολικεσ)\s+)?(?:(?:learning|study)\s+)?(?:hours|ωρεσ)\b'
    found={float(m.group(1).replace(',','.')) for m in re.finditer(pattern,text)}
    return found=={float(hours)}

@lru_cache(None)
def reference_cached(pairs):return information_reference(list(pairs))
def ref(ws):return reference_cached(tuple((w['node'],w['design']) for w in ws))
def reference_for(case,world,action,disclosed=True):
    ws=compatible(case,world,action,disclosed);r=ref(ws)
    if r['status']!='certified_within_restricted_scope':return {'status':r['status'],'expected_delay':None,'realized_delay':None,'action':None}
    a=r['best_blind_action']
    return {'status':r['status'],'expected_delay':r['blind_mean'],'realized_delay':first_action_value(world['node'],world['design'],tuple(a)),'action':a}

def mock_declaration(case,world,action,disclosed=True):
    if case.get('neutral_prompt',False):
        # Canonical SOFTWARE mock independent of the eventual scoring mechanism/kappa.
        case=dict(case,worlds=[dict(w,design=replace(w['design'],model='priority',kappa=25)) for w in case['worlds']])
        world=next(w for w in case['worlds'] if w['id']==world['id'])
    r=reference_for(case,world,action,disclosed)
    return '```json\n'+json.dumps({'courses':r['action'] or [],'reason':'MOCK reference-derived software response'},ensure_ascii=False)+'\n```'

def evaluate(case,world,action,text,disclosed=True):
    p=parse(text);result={'raw':text,'format':p,'feasible_true':None,'feasible_robust':None,
      'feasible_robust_nominal':None,'delay_semesters':None,'regret_semesters':None,'completion_status':'unevaluable',
      'domain_errors':[],'failures':[],'unknown':[],'compatible_world_ids':[]}
    if not p['valid']:return result
    courses=p['courses'];d=world['design'];s=world['node'].student
    result['domain_errors']=['outside_candidate_pool:'+c for c in courses if c not in d.pool]
    true=validate_declaration(s,courses,world['node'].phase,set(d.offerings),d.priority_rule,d.counting)
    result['failures']=true.failures;result['unknown']=true.unknown
    def valid(verdict):return True if verdict.status=='feasible' else False if verdict.status=='infeasible' else None
    result['feasible_true']=valid(true)
    for scope,ws in [('robust',compatible(case,world,action,disclosed)),('robust_nominal',compatible(case,world,action,True))]:
        states=[valid(validate_declaration(w['node'].student,courses,w['node'].phase,set(w['design'].offerings),w['design'].priority_rule,w['design'].counting)) for w in ws]
        result['feasible_'+scope]=False if False in states else None if None in states else True
        if scope=='robust':result['compatible_world_ids']=[w['id'] for w in ws]
    if result['feasible_true'] is not True or result['domain_errors']:
        result['completion_status']='invalid_or_uncertified_declaration';return result
    value=first_action_value(world['node'],world['design'],tuple(courses))
    result['delay_semesters']=value
    result['completion_status']='completed' if value is not None else 'not_completed_within_horizon'
    oracle=solve(world['node'],d)['semesters']
    result['oracle_semesters']=oracle
    result['regret_semesters']=None if value is None or oracle is None else value-oracle
    result['empty_declaration']=not courses
    return result

def not_scheduled():
    return {'raw':None,'format':{'valid':False,'error':'not_scheduled','courses':None},
      'feasible_true':None,'feasible_robust':None,'feasible_robust_nominal':None,
      'delay_semesters':None,'regret_semesters':None,'completion_status':'not_scheduled',
      'domain_errors':[],'failures':[],'unknown':[],'compatible_world_ids':[]}

def run_world(client,models,case,world,sample_id=0):
    public=P.public_context(case);sid=case['id'];wid=world['id']
    neutral=case.get('neutral_prompt',False)
    prompt_id=case['base_profile']+':'+case['context_variant'] if neutral else sid
    def call(model,system,messages,tag,mock,max_tokens=500):
        return client.call(model,system,messages,temperature=0,max_tokens=max_tokens,tag=SCHEMA+':sample'+str(sample_id)+':'+tag.replace(sid,prompt_id),mock_fn=mock)
    choice_raw=call(models['target'],P.CHOICE,[{'role':'user','content':public}],sid+':choice',lambda:'{"action":"Clarify","reason":"MOCK software fixture"}')
    choice=parse_choice(choice_raw)
    adv=call(models['target'],P.BASE,[{'role':'user','content':public}],sid+':adv',lambda:mock_declaration(case,world,'advise'))
    question=call(models['target'],P.QUESTION,[{'role':'user','content':public}],sid+':question',lambda:'How many total hours can you devote to learning this semester?')
    answer=call(models['student'],P.STUDENT,[{'role':'user','content':P.private_context(world)+'\nQUESTION: '+question}],sid+':student:'+str(world['design'].budgets),
      lambda:f"I have {world['design'].budgets[0]} total learning hours available this semester.")
    disclosed=capacity_disclosed(answer,world['design'].budgets[0])
    clr=call(models['target'],P.CLARIFY,[{'role':'user','content':public},{'role':'assistant','content':question},{'role':'user','content':answer}],sid+':clarify:'+str(world['design'].budgets),
       lambda:mock_declaration(case,world,'clarify',disclosed))
    retrieved=P.retrieved_context(world,neutral)
    calendar_tag=hashlib.sha256(retrieved.encode()).hexdigest()[:16]
    ret=call(models['target'],P.RETRIEVE,[{'role':'user','content':public+'\n'+retrieved}],sid+':retrieve:'+calendar_tag,lambda:mock_declaration(case,world,'retrieve'))
    fullcontext=public+'\n'+retrieved+'\nVERIFIED PERSONAL FACTS: '+P.private_context(world)
    expert=call(models['expert'],P.DEFER,[{'role':'user','content':fullcontext}],sid+':defer:'+str(wid),lambda:mock_declaration(case,world,'defer'),max_tokens=800) if case.get('run_expert',True) else None
    full=call(models['target'],P.BASE,[{'role':'user','content':fullcontext}],sid+':full:'+str(wid),lambda:mock_declaration(case,world,'full'))
    texts=dict(zip(ACTIONS,(adv,clr,ret,expert,full)))
    outcomes={a:evaluate(case,world,a,t,disclosed) if t is not None else not_scheduled() for a,t in texts.items()}
    references={a:reference_for(case,world,a,True) for a in ACTIONS}
    references['clarify_operational']=reference_for(case,world,'clarify',disclosed)
    return {'schema':SCHEMA,'mock':client.mock,'case':sid,'family':case['family'],'model':case['model'],'kappa':case['kappa'],
       'academic_record_id':case.get('academic_record_id'),'decision_state_id':case.get('decision_state_id'),
       'scenario_id':case.get('scenario_id',sid),'sample_id':sample_id,'base_profile':case.get('base_profile',case['family']),
       'context_variant':case.get('context_variant','rules_visible'),'objective':case.get('objective','degree_completion'),
       'active_semester':world['node'].student.active_semester,'phase':world['node'].phase,
       'world':wid,'worlds_n':len(case['worlds']),'capacity_ects_equivalent':None if neutral else world['capacity_ects_equivalent'],
       'capacity_level':'low' if world['capacity_ects_equivalent']==5 else 'high',
       'offering_variant':world['offering_variant'],'design_prior':'uniform independent synthetic worlds',
       'expert_scheduled':case.get('run_expert',True),'prompt_id':prompt_id,'neutral_prompt':neutral,'capacity_hours':world['design'].budgets[0],
       'free_choice':dict(choice,raw=choice_raw,selected_outcome=outcomes.get(choice['action'])),
       'models':models,'question':question,'student_answer':answer,'capacity_disclosed_auto':disclosed,
       'outcomes':outcomes,'references':references,'pool':list(world['design'].pool),'event_horizon':world['design'].max_events,
       'assumptions':{'annual_limit':world['node'].student.annual_limit,'counting':world['design'].counting,
          'priority':world['design'].priority_rule,'september_hours':world['design'].budgets[2],
          'first_decision_only':True,'future_continuation':'fully informed optimum in restricted action pool'}}
