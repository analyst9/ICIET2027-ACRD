"""Small near-completion cases; design worlds and calendars, not empirical students."""
from dataclasses import replace
from .rules import Student,CAT,ORDINARY,MANDATORY
from .solver import SearchState,Design

def ordinary_route():
    route=set(MANDATORY)
    for sem,n in [(5,4),(6,4),(7,6),(8,6)]:
        route.update(sorted(c for c in ORDINARY if not CAT[c]['mandatory'] and CAT[c]['semester']==sem)[:n])
    return route

def pilot_cases():
    route=ordinary_route();result=[]
    for model in ('priority','proportional'):
        for kappa in (25,30):
            for family in ('workload','annual_budget','offerings'):
                if family=='workload':pool=('Υ101','Υ102');missing=set(pool);history=();sept=0;variants=(0,)
                elif family=='annual_budget':pool=('Υ101','Υ102','Υ201');missing=set(pool);history=tuple(sorted(route-set(pool))[:16]);sept=5*kappa;variants=(0,)
                else:pool=('Υ101','Ε706','Ε707');missing={'Υ101','Ε706'};history=();sept=0;variants=(0,1)
                worlds=[]
                for capacity in (5,10):
                    for offer_variant in variants:
                        offered=set(ORDINARY)
                        if family=='offerings':offered.remove('Ε707' if offer_variant==0 else 'Ε706')
                        s=Student(2022,9,completed=frozenset(route-missing),year_history=history,annual_limit=18,
                            maximum_active_semester=16,declaration_open=True)
                        d=Design(pool,tuple(sorted(offered)),(capacity*kappa,capacity*kappa,sept),kappa,model,max_events=9)
                        worlds.append({'id':len(worlds),'capacity_ects_equivalent':capacity,'offering_variant':offer_variant,
                          'node':SearchState(s),'design':d})
                result.append({'base_profile':family,'objective':'degree_completion','context_variant':'rules_visible','id':f'{family}-{model}-k{kappa}','family':family,'model':model,'kappa':kappa,'worlds':worlds,
                    'label':'synthetic near-completion design case on real curriculum'})
    return result

def compatible(case,world,action,capacity_disclosed=True):
    ws=case['worlds']
    if action in ('defer','full'):return [world]
    if action=='clarify' and capacity_disclosed:return [w for w in ws if w['design'].budgets==world['design'].budgets]
    if action=='retrieve':return [w for w in ws if w['design'].offerings==world['design'].offerings]
    return ws


def profile_specs():
    """26 DISTINCT records, not inflated by allocation/kappa/context factors.
    Early-year cases have selected-obligation objectives because all remaining degree
    requirements cannot honestly fit in a six-candidate action pool.
    """
    route=ordinary_route();profiles=[]
    choices=[('Υ101','Υ102'),('Υ103','Ε701'),('Υ105','Ε702'),('Υ301','Υ501','Ε703'),
      ('Υ303','Ε704'),('Υ305','Ε705'),('Υ201','Υ203'),('Υ202','Ε801'),
      ('Υ204','Ε802'),('Υ401','Υ601','Ε803'),('Υ403','Ε804'),('Υ405','Ε805')]
    for i,missing in enumerate(choices):
        sem=(9 if i<6 else 10)+(2 if i%3==2 else 0)
        season='fall' if sem%2 else 'spring'
        complete=route-set(missing)
        count=16 if i%3==1 and season=='spring' else 0
        history=tuple(sorted(c for c in complete if CAT[c]['season']=='fall')[:count])
        profiles.append({'id':f'degree-{i:02d}','family':'annual_budget' if count else 'workload',
          'semester':sem,'completed':complete,'pool':missing,'history':history,'objective':'degree_completion',
          'targets':None,'offerings':False,'sept_ects':5 if i%2 else 0})
    first=sorted(c for c in MANDATORY if CAT[c]['semester']<=4)
    for i,(n,sem) in enumerate([(11,5),(12,5),(13,5),(11,7),(12,7),(11,9)]):
        profiles.append({'id':f'gate-{i:02d}','family':'gate', 'semester':sem,'completed':set(first[:n]),
          'pool':('Υ302','Υ501'),'history':(),'objective':'selected_obligations','targets':('Υ302','Υ501'),
          'offerings':False,'sept_ects':5})
    for i,sem in enumerate((3,4,5)):
        pool=('Υ302','Υ501') if sem%2 else ('Υ401','Υ601')
        profiles.append({'id':f'year-{i:02d}','family':'higher_year','semester':sem,'completed':set(first[:14] if sem==5 else first[:12]),
          'pool':pool,'history':(),'objective':'selected_obligations','targets':pool,'offerings':False,'sept_ects':0})
    for i,sem in enumerate((5,7,9)):
        profiles.append({'id':f'priority-{i:02d}','family':'priority','semester':sem,'completed':set(first[:12]),
          'pool':('Υ302','Υ501','Ε501'),'history':(),'objective':'selected_obligations',
          'targets':('Υ302','Υ501','Ε501'),'offerings':False,'sept_ects':5})
    # Add distinct elective-availability cases (not merely another allocation factor).
    for i,(sem,mandatory,e1,e2) in enumerate([(9,'Υ101','Ε706','Ε707'),(10,'Υ201','Ε806','Ε807')]):
        complete=route-{mandatory,e1}
        # e1 may lie outside the initially selected six; remove the selected sixth instead.
        group=CAT[e1]['semester'];selected=sorted(c for c in complete if CAT[c]['semester']==group and not CAT[c]['mandatory'])
        while len(selected)>5:complete.remove(selected.pop())
        profiles.append({'id':f'offerings-{i:02d}','family':'offerings','semester':sem,'completed':complete,
          'pool':(mandatory,e1,e2),'history':(),'objective':'degree_completion','targets':None,'offerings':True,'sept_ects':0})
    assert len(profiles)==26
    assert len({(p['semester'],tuple(sorted(p['completed'])),tuple(p['history']),tuple(p['pool'])) for p in profiles})==26
    return profiles

def expanded_cases():
    result=[]
    for p in profile_specs():
        for model in ('priority','proportional'):
            for kappa in (25,30):
                for context_variant in ('rules_visible','rules_retrieved'):
                    worlds=[]
                    for capacity in (5,10):
                        for offer_variant in (0,1) if p['offerings'] else (0,):
                            offered=set(ORDINARY)
                            if p['offerings']:offered.remove(p['pool'][2] if offer_variant==0 else p['pool'][1])
                            s=Student(2022,p['semester'],completed=frozenset(p['completed']),year_history=tuple(p['history']),
                                annual_limit=18,maximum_active_semester=18,declaration_open=True)
                            d=Design(tuple(p['pool']),tuple(sorted(offered)),(150 if capacity==5 else 300,150 if capacity==5 else 300,p['sept_ects']*30),
                                kappa,model,max_events=9,target_courses=p['targets'])
                            worlds.append({'id':len(worlds),'capacity_ects_equivalent':capacity,'offering_variant':offer_variant,
                              'node':SearchState(s,'fall' if p['semester']%2 else 'spring'),'design':d})
                    result.append({'id':f"{p['id']}-{model}-k{kappa}-{context_variant}",
                      'neutral_prompt':True,'base_profile':p['id'],'objective':p['objective'],'context_variant':context_variant,
                      'family':p['family'],'model':model,'kappa':kappa,'worlds':worlds,
                      'label':'synthetic records with real curriculum; degree and selected-obligation outcomes separate'})
    return result

def cases(suite='pilot'):
    if suite=='coverage':
        from .coverage import coverage_cases
        return coverage_cases()
    if suite=='pilot':return pilot_cases()
    if suite=='expanded':return expanded_cases()
    raise ValueError('suite')
