"""Predetermined coverage grid; no outcome-based scenario selection."""
import itertools,json,hashlib
from .rules import CAT,MANDATORY,FIRST,ORDINARY,Student
from .solver import SearchState,Design

def coverage_specs():
    from .scenarios import ordinary_route
    route=ordinary_route();profiles=[]
    def add(family,semester,completed,pool,history=(),sept=0,objective='degree_completion',**extra):
        assert len(pool)<=6 and set(pool)<=ORDINARY and not set(pool)&set(completed)
        assert set(history)<=set(completed)
        assert all((CAT[c]['semester']+1)//2<=(semester+1)//2 for c in completed)
        profiles.append(dict(family=family,semester=semester,completed=sorted(completed),pool=list(pool),history=list(history),september_hours=sept,objective=objective,**extra))
    buckets={(season,kind):sorted(c for c in route if CAT[c]['season']==season and CAT[c]['mandatory']==kind) for season in ('fall','spring') for kind in (True,False)}
    patterns=[]
    for season in ('fall','spring'):
     m,e=buckets[season,True],buckets[season,False]
     for n in (1,2,3):
      patterns.extend([tuple(m[:n]),tuple(e[:n])])
      if n>1:patterns.append(tuple(m[:n-1]+e[:1]))
    patterns.extend([(buckets['fall',True][0],buckets['spring',True][0]),(buckets['fall',False][0],buckets['spring',False][0]),(buckets['fall',True][0],buckets['spring',True][0],buckets['fall',False][0])])
    assert len(patterns)==19 and len(set(patterns))==19
    for missing in patterns:
     complete=route-set(missing)
     for sem in (9,10):
      for n in ((0,) if sem==9 else (0,16,17,18)):
       history=tuple(sorted(c for c in complete if CAT[c]['season']=='fall')[:n]);assert len(history)==n
       for sept in (0,150):add('degree',sem,complete,missing,history,sept)
    first=sorted(FIRST)
    for sem in (5,6,7,8,9,10):
     season='fall' if sem%2 else 'spring'
     for n in (11,12,13):
      for composition in ('prefix','spread'):
       complete=set(first[:n] if composition=='prefix' else first[::2][:12] + first[1::2][:max(0,n-12)])
       # For n=11 trim the spread list; preserve count exactly.
       if len(complete)>n:complete=set(sorted(complete)[:n])
       assert len(complete)==n
       old=next(c for c in first if c not in complete and CAT[c]['season']==season)
       second=next(c for c in sorted(MANDATORY) if CAT[c]['semester']==(5 if sem%2 else 6))
       add('gate',sem,complete,(old,second),sept=150,objective='selected_obligations',gate_count=n,record_pattern=composition)
    for sem in (3,4,5,6):
     season='fall' if sem%2 else 'spring'
     future_sem=(5 if sem%2 else 6) if sem<=4 else (7 if sem%2 else 8)
     future=next(c for c in sorted(ORDINARY) if CAT[c]['semester']==future_sem)
     for n_passed in (10,11,12):
      complete=set(first[:n_passed])
      older=[c for c in sorted(MANDATORY) if c not in complete and CAT[c]['season']==season and CAT[c]['semester']<=sem]
      for n in (1,2,3):add('higher_year',sem,complete,tuple(older[:n-1]+[future]),sept=150,objective='selected_obligations',gate_interaction=n_passed<12)
    for sem in (5,6,7,8,9,10):
     season='fall' if sem%2 else 'spring'
     for passed in (14,16,18):
      complete=set(sorted(c for c in first if CAT[c]['season']=='fall')[:passed//2]+sorted(c for c in first if CAT[c]['season']=='spring')[:passed//2]);old=next(c for c in first if c not in complete and CAT[c]['season']==season)
      req=next(c for c in sorted(MANDATORY) if CAT[c]['semester']==(5 if sem%2 else 6))
      elective=next(c for c in sorted(ORDINARY) if not CAT[c]['mandatory'] and CAT[c]['semester']==(5 if sem%2 else 6))
      add('priority',sem,complete,(old,req,elective),sept=150,objective='selected_obligations')
    for group in (5,6,7,8):
     selected=sorted(c for c in route if not CAT[c]['mandatory'] and CAT[c]['semester']==group)
     outsiders=sorted(c for c in ORDINARY-route if CAT[c]['semester']==group and not CAT[c]['mandatory'])
     debt=selected[-1]
     for n_alt in (2,3):
      alternatives=[debt]+outsiders[:n_alt-1];assert len(alternatives)==n_alt
      calendars=[list(subset) for n in range(1,n_alt+1) for subset in itertools.combinations(alternatives,n)]
      for n_debt in (1,2):
       req=buckets[CAT[debt]['season'],True][:n_debt]
       complete=route-set(req)-{debt}
       for sem in (9,10):
        for n_history in ((0,) if sem==9 else (0,17)):
         history=tuple(sorted(c for c in complete if CAT[c]['season']=='fall')[:n_history]);assert len(history)==n_history
         for sept in (0,150):add('offerings',sem,complete,tuple(req+alternatives),history=history,sept=sept,offering_alternatives=alternatives,calendar_worlds=calendars)
    keys=[json.dumps({k:p[k] for k in ('semester','completed','pool','history','september_hours','objective')},sort_keys=True) for p in profiles]
    assert len(keys)==len(set(keys))
    
    return profiles

def digest(data):return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
def coverage_cases():
    result=[]
    for p in coverage_specs():
        academic={k:p[k] for k in ('semester','completed','history')}
        decision={k:p[k] for k in ('semester','completed','history','pool','objective')}
        scenario={k:p[k] for k in ('semester','completed','history','pool','objective','september_hours')}
        aid='record-'+digest(academic);did='decision-'+digest(decision);sid=p['family']+'-'+digest(scenario)
        calendars=p.get('calendar_worlds',[[]])
        for model in ('priority','proportional'):
            for kappa in (25,30):
                for context in ('rules_visible','rules_retrieved'):
                    worlds=[]
                    for hours in (150,300):
                        for calid,calendar in enumerate(calendars):
                            offered=set(ORDINARY)
                            if p['family']=='offerings':offered-=set(p['offering_alternatives'])-set(calendar)
                            student=Student(2022,p['semester'],completed=frozenset(p['completed']),year_history=tuple(p['history']),
                                annual_limit=18,maximum_active_semester=18,declaration_open=True)
                            design=Design(tuple(p['pool']),tuple(sorted(offered)),(hours,hours,p['september_hours']),kappa,model,
                              max_events=9,target_courses=tuple(p['pool']) if p['objective']=='selected_obligations' else None)
                            worlds.append({'id':len(worlds),'capacity_ects_equivalent':5 if hours==150 else 10,'offering_variant':calid,
                              'node':SearchState(student,'fall' if p['semester']%2 else 'spring'),'design':design})
                    result.append({'id':f'{sid}-{model}-k{kappa}-{context}','base_profile':sid,'scenario_id':sid,
                      'academic_record_id':aid,'decision_state_id':did,'objective':p['objective'],'context_variant':context,
                      'family':p['family'],'model':model,'kappa':kappa,'neutral_prompt':True,'worlds':worlds,
                      'label':'predetermined coverage scenario, not an independent empirical student'})
    return result
