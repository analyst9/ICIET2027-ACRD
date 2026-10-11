"""Exact bounded-horizon search ONLY over a supplied small ordinary-course action pool.
No claim of solving all possible electives or of unconstrained long-run optimality.
"""
from dataclasses import dataclass,replace
from functools import lru_cache
from itertools import combinations,permutations
from .rules import CAT,Student,validate_declaration,graduation
from .performance import study

@dataclass(frozen=True)
class SearchState:
    student:Student
    phase:str='fall'
    september_rights:tuple=()

@dataclass(frozen=True)
class Design:
    pool:tuple
    offerings:tuple  # explicit fixed synthetic calendar (IDs); nominal season still checked
    budgets:tuple=(250,250,125)  # DESIGN VALUES, not measured student hours
    kappa:int=25
    model:str='priority'
    priority_rule:str='mandatory_then_semester'
    counting:str='registrations'
    max_events:int=9
    target_courses:tuple|None=None  # selected-obligation subproblem; None means degree completion


@lru_cache(None)
def declarations(node,design):
    """All legal lists incl. priority-consistent permutations in the RESTRICTED action pool."""
    s=node.student
    available=[c for c in design.pool if c not in s.completed and c not in s.recognized_english and c in design.offerings and CAT[c]['season']==node.phase]
    result=[]
    for n in range(len(available)+1):
        for comb in combinations(available,n):
            for order in permutations(comb):
                v=validate_declaration(s,list(order),node.phase,set(design.offerings),design.priority_rule,design.counting)
                if v.unknown:raise ValueError('uncertified scenario: '+str(v.unknown))
                if v.status=='feasible':result.append(order)
    return tuple(result)

def goal_met(student,design):
    if design.target_courses is not None:
        return set(design.target_courses)<=set(student.completed)|set(student.recognized_english)
    return graduation(student)['status']=='complete'

def advance(node,design,action=()):
    s=node.student
    phase=node.phase;idx={'fall':0,'spring':1,'september':2}[phase]
    if phase=='september':
        if action:raise ValueError('September is re-examination, not a new declaration')
        eligible=tuple(c for c in node.september_rights if c not in s.completed)
        outcome=study(eligible,design.budgets[idx],design.kappa,design.model)
        done=s.completed|frozenset(outcome['passed'])
        after=replace(s,completed=done)
        nxt=SearchState(replace(after,active_semester=s.active_semester+1,year_history=()),'fall',())
        return nxt,after,0,outcome
    if action not in declarations(node,design):raise ValueError('illegal action')
    outcome=study(action,design.budgets[idx],design.kappa,design.model)
    done=s.completed|frozenset(outcome['passed'])
    after=replace(s,completed=done,completed_active_semesters=s.active_semester,year_history=tuple(sorted(s.year_history+tuple(action))))
    # Every declared failed ID consumes a registration slot and yields a September right.
    rights=tuple(dict.fromkeys(node.september_rights+tuple(outcome['failed'])))
    if phase=='fall':nxt=SearchState(replace(after,active_semester=s.active_semester+1),'spring',rights)
    else:nxt=SearchState(after,'september',rights)
    return nxt,after,1,outcome

@lru_cache(maxsize=16384)
def solve(initial,design,memo=True):
    if len(design.pool)>6:raise ValueError('prototype exact search supports at most 6 candidate IDs')
    if len(set(design.pool))!=len(design.pool) or not set(design.pool)<=set(CAT):raise ValueError('pool IDs')
    if any(CAT[c]['kind']!='course' for c in design.pool):raise ValueError('special activities outside numerical solver')
    if design.max_events<1:raise ValueError('horizon')
    if initial.phase not in ('fall','spring','september'):raise ValueError('phase')
    if initial.student.maximum_active_semester is None:raise ValueError('explicit duration bound required for future search')
    if initial.student.annual_limit is None or initial.student.year_history is None:raise ValueError('annual facts required')
    @lru_cache(None)
    def cached(node,remaining):return search(node,remaining)
    def search(node,remaining):
        if goal_met(node.student,design):return (0,0,())
        if remaining==0:return None
        if node.student.active_semester>node.student.maximum_active_semester:return None
        actions=[()] if node.phase=='september' else declarations(node,design)
        best=None
        for action in actions:
            nxt,after,cost,outcome=advance(node,design,action)
            step={'phase':node.phase,'active_semester':node.student.active_semester,'declaration':list(action),
              'passed':list(outcome['passed']),'failed':list(outcome['failed']),
              'annual_registration_count':len(after.year_history),'september_rights':list(nxt.september_rights)}
            if goal_met(after,design):candidate=(cost,1,(step,))
            else:
                sub=(cached if memo else search)(nxt,remaining-1)
                if sub is None:continue
                candidate=(cost+sub[0],1+sub[1],(step,)+sub[2])
            if best is None or candidate[:2]<best[:2]:best=candidate
        return best
    value=(cached if memo else search)(initial,design.max_events)
    return {'status':'completed' if value else 'not_completed_within_horizon',
      'semesters':value[0] if value else None,'completion_phase':value[2][-1]['phase'] if value and value[2] else 'already_complete' if value else None,
      'path':list(value[2]) if value else [],'model':design.model,'kappa':design.kappa,
      'exact_scope':'bounded horizon; supplied ordinary-course pool and synthetic calendar; selected rule interpretations',
      'objective':'degree_completion' if design.target_courses is None else 'selected_obligations',
      'target_courses':None if design.target_courses is None else list(design.target_courses),
      'candidate_pool':list(design.pool),'event_horizon':design.max_events,'states':cached.cache_info().currsize if memo else None}

@lru_cache(None)
def first_action_value(initial,design,action):
    """First-decision semesters followed by the same fully informed optimal continuation."""
    nxt,after,cost,_=advance(initial,design,tuple(action))
    if goal_met(after,design):return cost
    if design.max_events<=1:return None
    rest=solve(nxt,replace(design,max_events=design.max_events-1))
    return None if rest['semesters'] is None else cost+rest['semesters']

def information_reference(worlds):
    """Uniform DESIGN weights, not empirical priors. Requires complete uncensored outcomes.
    Worlds are (SearchState, Design); only information about which world is revealed.
    Invalid lists never receive a numeric penalty; intersect feasible action sets instead.
    """
    if not worlds:raise ValueError('empty worlds')
    sets=[set(declarations(n,d)) for n,d in worlds]
    actions=sorted(set.intersection(*sets))
    informed=[solve(n,d)['semesters'] for n,d in worlds]
    evaluated=[]
    for a in actions:
        values=[first_action_value(n,d,tuple(a)) for n,d in worlds]
        evaluated.append({'action':list(a),'world_values':values,'mean':sum(values)/len(values) if all(v is not None for v in values) else None})
    complete=all(v is not None for v in informed) and all(r['mean'] is not None for r in evaluated)
    if not complete:return {'status':'uncertified_due_to_horizon','rows':evaluated,'informed':informed,'gain':None}
    best=min(evaluated,key=lambda r:r['mean'])
    oracle=sum(informed)/len(informed)
    return {'status':'certified_within_restricted_scope','design_weights':'uniform','blind_mean':best['mean'],
      'informed_mean':oracle,'gain':best['mean']-oracle,'best_blind_action':best['action'],'rows':evaluated}
