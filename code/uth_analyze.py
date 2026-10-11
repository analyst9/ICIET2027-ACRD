"""Descriptive four-action comparisons, common feasible subsets and exact scoped references."""
import json,argparse,itertools
from pathlib import Path
from uth_ds.experiment import ACTIONS,SCHEMA
SCOPES=('true','robust','robust_nominal')
def average(values):return sum(values)/len(values) if values else None

def reference(r,action,scope):
    key='clarify_operational' if action=='clarify' and scope=='robust' else action
    return r['references'][key]['realized_delay']

def usable(r,action,scope):
    o=r['outcomes'][action]
    return o['format']['valid'] and o['feasible_'+scope] is True and not o['domain_errors'] and o['delay_semesters'] is not None

def summary_action(rows,a,scope):
    attempted=[r for r in rows if r['outcomes'][a]['completion_status']!='not_scheduled']
    parsed=[r for r in attempted if r['outcomes'][a]['format']['valid']]
    selected=[r for r in rows if usable(r,a,scope)]
    reference_pairs=[r for r in selected if reference(r,a,scope) is not None]
    return {'action':a,'scope':scope,'total':len(rows),'scheduled_sample_ids':sorted({r['sample_id'] for r in attempted}),'scheduled_n':len(attempted),'not_scheduled':len(rows)-len(attempted),'format_failures':len(attempted)-len(parsed),'parsed':len(parsed),
       'format_failure_rate':(len(attempted)-len(parsed))/len(attempted) if attempted else None,
       'infeasible_rate_among_parsed':sum(r['outcomes'][a]['feasible_'+scope] is False for r in parsed)/len(parsed) if parsed else None,
       'distinct_response_samples':len({(r['case'],r['sample_id'],r['outcomes'][a]['raw']) for r in attempted}),
       'infeasible':sum(r['outcomes'][a]['feasible_'+scope] is False for r in parsed),
       'insufficient_data':sum(r['outcomes'][a]['feasible_'+scope] is None for r in parsed),
       'domain_errors':sum(bool(r['outcomes'][a]['domain_errors']) for r in parsed),
       'no_completion_within_horizon':sum(r['outcomes'][a]['completion_status']=='not_completed_within_horizon' for r in parsed),
       'empty_declarations':sum(r['outcomes'][a]['format']['courses']==[] for r in parsed),
       'usable_delay_n':len(selected),'conditional_semesters':average([r['outcomes'][a]['delay_semesters'] for r in selected]),
       'reference_pair_n':len(reference_pairs),
       'reference_same_worlds':average([reference(r,a,scope) for r in reference_pairs]),
       'mean_paired_gap':average([r['outcomes'][a]['delay_semesters']-reference(r,a,scope) for r in reference_pairs]),
       'expected_semesters_scheduled_worlds':average([r['outcomes'][a]['delay_semesters'] for r in selected]) if attempted and len(selected)==len(attempted) else None,
       'expected_semesters_all_worlds':average([r['outcomes'][a]['delay_semesters'] for r in selected]) if len(selected)==len(rows) else None}

def paired(rows,a,b,scope):
    selected=[r for r in rows if usable(r,a,scope) and usable(r,b,scope)]
    return {'A':a,'B':b,'scope':scope,'total':len(rows),'paired_n':len(selected),'excluded_union':len(rows)-len(selected),
       'A_counts':summary_action(rows,a,scope),'B_counts':summary_action(rows,b,scope),
       'paired_A_minus_B':average([r['outcomes'][a]['delay_semesters']-r['outcomes'][b]['delay_semesters'] for r in selected]),
       'gain_all_worlds':average([r['outcomes'][a]['delay_semesters']-r['outcomes'][b]['delay_semesters'] for r in selected]) if len(selected)==len(rows) else None}

def table(records,columns):
    def val(x):return '—' if x is None else str(x).replace('|','\\|')
    return '\n'.join(['| '+' | '.join(columns)+' |','| '+' | '.join(['---']*len(columns))+' |']+[
        '| '+' | '.join(val(r.get(c)) for c in columns)+' |' for r in records])

def analyze(data,out):
    rows=[json.loads(l) for l in (Path(data)/'results.jsonl').read_text(encoding='utf-8-sig').splitlines()]
    if not rows:raise ValueError('no rows')
    if any(r['schema']!=SCHEMA or not isinstance(r['mock'],bool) for r in rows):raise ValueError('incompatible schema')
    if len({r['mock'] for r in rows})!=1:raise ValueError('mixed live/mock results')
    is_mock=rows[0]['mock']
    if len({r['run_identity'] for r in rows})!=1:raise ValueError('mixed runs')
    groups={};seen=set()
    for r in rows:
        key=(r['case'],r['world'],r['sample_id'])
        if key in seen:raise ValueError('duplicate instance')
        seen.add(key);groups.setdefault(r['case'],[]).append(r)
        for a in ACTIONS:
            o=r['outcomes'][a]
            if not o['format']['valid'] and (o['feasible_true'] is not None or o['delay_semesters'] is not None):raise ValueError('format failure wrongly evaluated')
            if o['delay_semesters'] is not None and (o['feasible_true'] is not True or o['domain_errors']):raise ValueError('invalid numeric delay')
    sample_sets=[]
    for name,g in groups.items():
        ids={r['sample_id'] for r in g};sample_sets.append(ids)
        if ids!=set(range(max(ids)+1)):raise ValueError('incomplete samples '+name)
        for sample in ids:
            subset=[r for r in g if r['sample_id']==sample]
            if len({r['worlds_n'] for r in subset})!=1 or len(subset)!=subset[0]['worlds_n'] or {r['world'] for r in subset}!=set(range(len(subset))):raise ValueError('incomplete group '+name)
    if any(x!=sample_sets[0] for x in sample_sets):raise ValueError('unequal repetition counts')
    strata={}
    for r in rows:strata.setdefault((r['objective'],r['model'],r['kappa'],r['context_variant']),[]).append(r)
    actions=[dict(objective=k[0],model=k[1],kappa=k[2],context_variant=k[3],**summary_action(g,a,scope)) for k,g in strata.items() for a in ACTIONS for scope in SCOPES]
    cases=[];comparisons=[];gains=[]
    for name,g in groups.items():
        for a in ACTIONS:
            for scope in SCOPES:
                cases.append({'case':name,'base_profile':g[0]['base_profile'],'objective':g[0]['objective'],'context_variant':g[0]['context_variant'],'model':g[0]['model'],'kappa':g[0]['kappa'],**summary_action(g,a,scope)})
        for scope in SCOPES:
            for a,b in itertools.combinations(ACTIONS,2):comparisons.append({'case':name,**paired(g,a,b,scope)})
            for b in ('clarify','retrieve'):
                refpairs=[r for r in g if reference(r,'advise',scope) is not None and reference(r,b,scope) is not None]
                theoretical=average([reference(r,'advise',scope)-reference(r,b,scope) for r in refpairs]) if len(refpairs)==len(g) else None
                p=paired(g,'advise',b,scope)
                gains.append({'case':name,'base_profile':g[0]['base_profile'],'objective':g[0]['objective'],'context_variant':g[0]['context_variant'],'model':g[0]['model'],'kappa':g[0]['kappa'],'information_action':b,'scope':scope,
                    'theoretical_gain_all_worlds':theoretical,'realized_gain_all_worlds':p['gain_all_worlds'],
                    'realized_gain_paired':p['paired_A_minus_B'],'paired_n':p['paired_n'],'excluded_union':p['excluded_union'],'worlds_n':len(g)})
    matched={}
    for r in rows:
        key=(r['base_profile'],r['model'],r['kappa'],r['world'],r['sample_id'])
        matched.setdefault(key,{})[r['context_variant']]=r
    ablation=[]
    for key,v in matched.items():
        if set(v)!={'rules_visible','rules_retrieved'}:continue
        x,y=v['rules_visible'],v['rules_retrieved']
        for a in ACTIONS:
            common=usable(x,a,'robust') and usable(y,a,'robust')
            ablation.append({'base_profile':key[0],'model':key[1],'kappa':key[2],'world':key[3],'sample_id':key[4],
              'objective':x['objective'],'action':a,'visible_feasible':x['outcomes'][a]['feasible_robust'],
              'withheld_feasible':y['outcomes'][a]['feasible_robust'],'common_evaluable':common,
              'withheld_minus_visible_delay':y['outcomes'][a]['delay_semesters']-x['outcomes'][a]['delay_semesters'] if common else None,
              'interpretation':'information disclosure ablation; fixed-rule oracle unchanged'})
    choices={};choice_scoring=[]
    shared={}
    for r in rows:
        c=r['free_choice'];key=(r['prompt_id'],r['sample_id'])
        transcript={'prompt_id':r['prompt_id'],'base_profile':r['base_profile'],'context_variant':r['context_variant'],
          'sample_id':r['sample_id'],'valid':c['valid'],'action':c['action'],'reason':c['reason'],'raw':c['raw']}
        if key in choices and choices[key]!=transcript:raise ValueError('choice differs across information-compatible worlds or scoring hypotheses')
        choices[key]=transcript
        if r.get('neutral_prompt'):
            k=(r['prompt_id'],r['world'],r['sample_id'])
            texts=tuple(r['outcomes'][a]['raw'] for a in ACTIONS)+(r['question'],r['student_answer'])
            if k in shared and shared[k]!=texts:raise ValueError('neutral responses changed across scoring hypotheses')
            shared[k]=texts
        a=c['action'];o=r['outcomes'].get(a)
        for info in ('clarify','retrieve'):
            x=reference(r,'advise','robust');y=reference(r,info,'robust')
            choice_scoring.append({'case':r['case'],'prompt_id':r['prompt_id'],'world':r['world'],'sample_id':r['sample_id'],
              'objective':r['objective'],'model':r['model'],'kappa':r['kappa'],'selected_action':a,
              'selected_evaluation_status':o['completion_status'] if o else 'invalid_choice',
              'selected_feasible_robust':o['feasible_robust'] if o else None,
              'selected_delay_semesters':o['delay_semesters'] if o and usable(r,a,'robust') else None,
              'information_action':info,'certified_realized_gain':x-y if x is not None and y is not None else None,
              'reference_expected_gain':r['references']['advise']['expected_delay']-r['references'][info]['expected_delay']
                if r['references']['advise']['expected_delay'] is not None and r['references'][info]['expected_delay'] is not None else None,
              'no_unique_correct_action_without_costs':True})
    choice_list=list(choices.values())
    choice_summary={'unique_choice_samples':len(choice_list),'format_failures':sum(not c['valid'] for c in choice_list),
       'counts':{a:sum(c['action']==a for c in choice_list) for a in ACTIONS if a!='full'},
       'interpretation':'one pre-information descriptive choice per profile/context/sample; no normative optimality or trained policy'}
    world_groups={}
    for r in rows:world_groups.setdefault((r['case'],r['world']),[]).append(r)
    expert_pairs=[]
    for (case_id,world_id),g in world_groups.items():
        experts=[r for r in g if r['expert_scheduled']]
        for action in ('advise','clarify','retrieve','full'):
            for scope in SCOPES:
                target_ok=all(usable(r,action,scope) for r in g)
                expert_ok=bool(experts) and all(usable(r,'defer',scope) for r in experts)
                common=target_ok and expert_ok
                expert_pairs.append({'case':case_id,'world':world_id,'action':action,'scope':scope,
                  'target_draws':len(g),'expert_draws':len(experts),'common_evaluable':common,
                  'target_mean':average([r['outcomes'][action]['delay_semesters'] for r in g]) if target_ok else None,
                  'expert_mean':average([r['outcomes']['defer']['delay_semesters'] for r in experts]) if expert_ok else None,
                  'target_minus_expert':average([r['outcomes'][action]['delay_semesters'] for r in g])-average([r['outcomes']['defer']['delay_semesters'] for r in experts]) if common else None,
                  'note':'one expert draw is not replicated to match target draws; absent or invalid outcomes exclude this world from numeric comparison'})
    summary={'schema':SCHEMA,'mock':is_mock,'software_test_only':is_mock,'instances':len(rows),'cases':len(groups),'base_profiles':len({r['base_profile'] for r in rows}),
        'samples_per_prompt':len(sample_sets[0]),'independence_note':'worlds may reuse the same response within a sample; rates are design-world rates, not independent trials',
        'academic_records':len({r.get('academic_record_id') for r in rows if r.get('academic_record_id')}),
        'decision_states':len({r.get('decision_state_id') for r in rows if r.get('decision_state_id')}),
        'unique_prompt_conditions':len({r['prompt_id'] for r in rows}),
        'free_choice':choice_summary,'declaration_outputs':sum(r['outcomes'][a]['completion_status']!='not_scheduled' for r in rows for a in ACTIONS),'no_policy_training':True,'no_arbitrary_invalid_penalty':True,
        'scope':'separate degree and selected-obligation objectives; bounded horizon and small action pools; uniform synthetic worlds',
        'actions':actions}
    sample_outcomes=[dict(case=name,sample_id=sample,objective=g[0]['objective'],**summary_action([r for r in g if r['sample_id']==sample],a,scope)) for name,g in groups.items() for sample in sorted(sample_sets[0]) for a in ACTIONS for scope in SCOPES]
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    for name,obj in [('summary',summary),('case_outcomes',cases),('paired_comparisons',comparisons),('information_gain',gains),('rules_ablation',ablation),('sample_outcomes',sample_outcomes),('free_choices',choice_list),('free_choice_scoring',choice_scoring),('expert_target_comparisons',expert_pairs)]:
        (out/(name+'.json')).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    report='''# UTH DS mock pilot — SOFTWARE TEST ONLY

Repetitions have independent cache sample keys. Synthetic worlds sharing an information set reuse one response within each repetition; they are not independent LLM trials. Rates are descriptive, with no population confidence claim. Degree completion and selected-obligation completion are different objectives and are stratified separately. Fixed-rule retrieval tests LLM access to rules; it does not invent uncertainty in the oracle's fixed rules.
Active neutral mock declarations are derived from a canonical priority/kappa25 software fixture and reused across all four scoring hypotheses. Legacy regression fixtures use their scoped references. These declarations are not generated by a live model. Agreement with the reference checks orchestration, not LLM quality. No human measurements or learned policy.
The two allocation mechanisms are sensitivity scenarios, not proven bounds of real behavior. No claim that reality lies between their values.
Format failures, infeasible declarations, missing facts, out-of-pool proposals and horizon non-completions are separate. Delay comparisons use common feasible/evaluable sets.

## Free choice (descriptive only)

'''+json.dumps(choice_summary,ensure_ascii=False)+'''

## Per-case outcomes against the reference

'''+table(cases,['case','action','scope','total','scheduled_n','not_scheduled','format_failures','infeasible','insufficient_data','domain_errors','no_completion_within_horizon','usable_delay_n','conditional_semesters','reference_same_worlds','mean_paired_gap','expected_semesters_all_worlds'])
    report+='\n\n## Information gain\n\n'+table(gains,['case','information_action','scope','theoretical_gain_all_worlds','realized_gain_all_worlds','realized_gain_paired','paired_n','excluded_union','worlds_n'])
    report+='\n\nNominal clarification assumes successful information acquisition; operational uses the answer recognizer. Inspect every distinct answer in clarification_audit.jsonl. Full-world averages are null if any world is excluded. Cases are stratified synthetic demonstrations, not prevalence estimates. Scope and assumptions are recorded in results.jsonl.\n'
    if not is_mock:
        report=report.replace('# UTH DS mock pilot — SOFTWARE TEST ONLY','# UTH DS live pilot — descriptive model outputs')
        report=report.replace('Active neutral mock declarations are derived from a canonical priority/kappa25 software fixture and reused across all four scoring hypotheses. Legacy regression fixtures use their scoped references. These declarations are not generated by a live model. Agreement with the reference checks orchestration, not LLM quality. No human measurements or learned policy.','Neutral live declarations are reused across four scoring hypotheses. These are outputs of the configured LLMs on synthetic student states; no empirical human measurements or learned policy. Audit the conversations and costs before interpreting results.')
    from uth_reassess import case_index
    from uth_ds.secondary import report as secondary_report
    secondary,secondary_rows=secondary_report(rows,case_index(rows))
    (out/'secondary_rejection_summary.json').write_text(json.dumps(secondary,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (out/'secondary_rejection_outcomes.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in secondary_rows),encoding='utf-8')
    report+='\n\n## Predeclared secondary administrative rejection hypothesis\n\nTrue-world illegal, syntactically valid, in-pool declarations with known legality are rejected in full and evaluated as an empty declaration. Primary outcomes above remain unchanged. Format/domain/unknown failures remain excluded; horizon noncompletion stays censored. See secondary_rejection_summary.json for counts, conditional means, paired denominators and changes in selection. This is a hypothetical filter, not an observed institutional practice.\n'
    (out/'report.md').write_text(report,encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='actions'},indent=2));return summary
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',default='data_uth_mock');p.add_argument('--out',default='results_uth_mock');a=p.parse_args();analyze(a.data,a.out)
