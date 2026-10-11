"""Predeclared hypothetical administrative rejection; primary data stay intact."""
from collections import Counter
from .solver import first_action_value, solve
from .experiment import ACTIONS


def rejection_outcome(outcome, world):
    if outcome['completion_status'] == 'not_scheduled':
        return {'status': 'not_scheduled', 'delay_semesters': None}
    if not outcome['format']['valid']:
        return {'status': 'excluded_format', 'delay_semesters': None}
    if outcome['domain_errors']:
        return {'status': 'excluded_domain', 'delay_semesters': None}
    if outcome['unknown'] or outcome['feasible_true'] is None:
        return {'status': 'excluded_unknown', 'delay_semesters': None}
    rejected = outcome['feasible_true'] is False
    value = first_action_value(world['node'], world['design'], ()) if rejected else outcome['delay_semesters']
    oracle = solve(world['node'], world['design'])['semesters']
    return {'status': 'rejected_to_empty' if rejected else 'original_legal',
            'delay_semesters': value,
            'completion_status': 'completed' if value is not None else 'not_completed_within_horizon',
            'regret_semesters': None if value is None or oracle is None else value-oracle}


def report(rows, case_map):
    records=[]
    for r in rows:
        case=case_map[r['case']]
        world=next(w for w in case['worlds'] if w['id']==r['world'])
        records.append({k:r[k] for k in ('case','world','sample_id','objective','model','kappa','context_variant')})
        records[-1]['outcomes']={a:rejection_outcome(r['outcomes'][a],world) for a in ACTIONS}
    strata={}
    for r in records:
        strata.setdefault(tuple(r[k] for k in ('objective','model','kappa','context_variant')),[]).append(r)
    summaries=[];pairs=[]
    for key,group in strata.items():
        meta=dict(zip(('objective','model','kappa','context_variant'),key))
        for action in ACTIONS:
            outcomes=[r['outcomes'][action] for r in group]
            values=[o['delay_semesters'] for o in outcomes if o['delay_semesters'] is not None]
            scheduled=sum(o['status']!='not_scheduled' for o in outcomes)
            summaries.append(dict(meta,action=action,total=len(group),scheduled_n=scheduled,
                statuses=dict(Counter(o['status'] for o in outcomes)),usable_delay_n=len(values),
                no_completion_within_horizon=sum(o.get('completion_status')=='not_completed_within_horizon' for o in outcomes),
                conditional_semesters=sum(values)/len(values) if values else None,
                expected_semesters_scheduled_worlds=sum(values)/len(values) if values and len(values)==scheduled else None))
        for action in ('clarify','retrieve','full'):
            primary=[r for r in rows if tuple(r[k] for k in ('objective','model','kappa','context_variant'))==key]
            original={(r['case'],r['world'],r['sample_id']) for r in primary
                      if all(r['outcomes'][a]['delay_semesters'] is not None for a in ('advise',action))}
            common=[r for r in group if all(r['outcomes'][a]['delay_semesters'] is not None for a in ('advise',action))]
            pairs.append(dict(meta,A='advise',B=action,total=len(group),paired_n=len(common),excluded_union=len(group)-len(common),
                primary_true_paired_n=len(original),added_paired_worlds=sum((r['case'],r['world'],r['sample_id']) not in original for r in common),
                paired_A_minus_B=sum(r['outcomes']['advise']['delay_semesters']-r['outcomes'][action]['delay_semesters'] for r in common)/len(common) if common else None))
    world_groups={}
    for r in records:world_groups.setdefault((r['case'],r['world']),[]).append(r)
    expert_pairs=[]
    for (case_id,world_id),group in world_groups.items():
        experts=[r for r in group if r['outcomes']['defer']['status']!='not_scheduled']
        for action in ('advise','clarify','retrieve','full'):
            target_ok=all(r['outcomes'][action]['delay_semesters'] is not None for r in group)
            expert_ok=bool(experts) and all(r['outcomes']['defer']['delay_semesters'] is not None for r in experts)
            target_mean=sum(r['outcomes'][action]['delay_semesters'] for r in group)/len(group) if target_ok else None
            expert_mean=sum(r['outcomes']['defer']['delay_semesters'] for r in experts)/len(experts) if expert_ok else None
            expert_pairs.append({'case':case_id,'world':world_id,'action':action,'scope':'secondary_true',
                'target_draws':len(group),'expert_draws':len(experts),'common_evaluable':target_ok and expert_ok,
                'target_mean':target_mean,'expert_mean':expert_mean,
                'target_minus_expert':target_mean-expert_mean if target_ok and expert_ok else None,
                'note':'Target draws averaged per world; expert draws are never replicated.'})
    return {'rule':'hypothetical entire illegal in-pool declaration rejection to empty; true-world scope only',
            'primary_unchanged':True,'no_arbitrary_numeric_penalty':True,'instances':len(records),
            'actions':summaries,'paired_comparisons':pairs,'expert_target_comparisons':expert_pairs},records
