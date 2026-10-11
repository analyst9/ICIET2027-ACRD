"""Mock and explicitly invoked budget-controlled live runner."""
import argparse,json,sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from acrd.llm import LLM
from uth_ds.scenarios import cases
from uth_ds.experiment import SCHEMA,run_world
from uth_ds.budget import scheduled_case

def run(out,samples=1,suite="pilot",scenario_ids=None,expert_scope=None,expert_samples=None,live_client=None):
    if not isinstance(samples,int) or samples<1:raise ValueError("samples must be positive")
    expert_scope=expert_scope or 'all'
    expert_samples=expert_samples if expert_samples is not None else (1 if suite=='coverage' else None)
    if expert_samples is not None and (not isinstance(expert_samples,int) or not 1<=expert_samples<=samples):raise ValueError('expert samples must be between one and target samples')
    selected_cases=[scheduled_case(c,expert_scope) for c in cases(suite)]
    if scenario_ids:
        known={c.get("scenario_id",c["base_profile"]) for c in selected_cases}
        if set(scenario_ids)-known:raise ValueError("unknown requested scenario IDs")
        selected_cases=[c for c in selected_cases if c.get("scenario_id",c["base_profile"]) in scenario_ids]
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    from uth_ds.live import MODELS
    models=MODELS if live_client else {'target':'MOCK_TARGET','student':'MOCK_STUDENT','expert':'MOCK_LLM_EXPERT'}
    definition={'schema':SCHEMA,'models':models,'cases':[c['id'] for c in selected_cases],'suite':suite,'expert_scope':expert_scope,'expert_samples':expert_samples}
    # Hash executable specification, not just case labels, to prevent mixing stale outputs.
    base=Path(__file__).parent
    files=[base/'uth_run.py',base/'uth_ds/catalogue.json']+sorted((base/'uth_ds').glob('*.py'))
    identity=hashlib.sha256(json.dumps(definition,sort_keys=True).encode()+b''.join(p.read_bytes() for p in files)).hexdigest()
    resultfile=out/'results.jsonl';rows={}
    if resultfile.exists():
        for line in resultfile.read_text(encoding='utf-8-sig').splitlines():
            r=json.loads(line)
            if r.get('run_identity')!=identity or r['schema']!=SCHEMA or r['mock'] is not (live_client is None):raise ValueError('incompatible checkpoint; use new folder')
            key=(r['case'],r['world'],r['sample_id'])
            if r['sample_id']>=samples:raise ValueError('cannot reduce repetitions in existing checkpoint')
            if key in rows:raise ValueError('duplicate checkpoint instance')
            rows[key]=r
    client=live_client or LLM(str(out/('cache_'+identity[:16]+'.jsonl')),mock=True)
    for case in selected_cases:
        for sample_id in range(samples):
            for w in case['worlds']:
                key=(case['id'],w['id'],sample_id)
                if key in rows:continue
                r=run_world(client,models,scheduled_case(case,expert_scope,sample_id,expert_samples),w,sample_id);r['run_identity']=identity;rows[key]=r
                with resultfile.open('a',encoding='utf-8') as f:f.write(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n')
    # Audit transcripts, preserving annotations if resumed with unchanged text.
    auditfile=out/'clarification_audit.jsonl';old={}
    if auditfile.exists():
        old={a['id']:a for a in [json.loads(l) for l in auditfile.read_text(encoding='utf-8-sig').splitlines()]}
    audits={}
    for r in rows.values():
        ident=r['prompt_id']+'-hours'+str(r['capacity_hours'])+'-sample'+str(r['sample_id'])
        a={'id':ident,'question':r['question'],'answer':r['student_answer'],'auto_disclosed':r['capacity_disclosed_auto'],
           'human_disclosed':None,'notes':''}
        if ident in old and old[ident]['answer']==a['answer'] and old[ident]['question']==a['question']:
            a.update(human_disclosed=old[ident].get('human_disclosed'),notes=old[ident].get('notes',''))
        audits[ident]=a
    auditfile.write_text(''.join(json.dumps(a,ensure_ascii=False)+'\n' for a in audits.values()),encoding='utf-8')
    manifest={'schema':SCHEMA,'mock':live_client is None,'run_identity':identity,'instances':len(rows),'cases':len(selected_cases),'samples_per_prompt':samples,'suite':suite,
       'expert_scope':expert_scope,'expert_samples_per_prompt':expert_samples,'expert_scenarios':len({c['scenario_id'] for c in selected_cases if c.get('scenario_id') and c['run_expert']}),
       'base_profiles':len({c.get('base_profile',c['family']) for c in selected_cases}),
       'academic_records':len({r['academic_record_id'] for r in rows.values() if r['academic_record_id']}),
       'decision_states':len({r['decision_state_id'] for r in rows.values() if r['decision_state_id']}),
       'unique_prompt_conditions':len({r['prompt_id'] for r in rows.values()}),
       'unique_choice_samples':len({(r['prompt_id'],r['sample_id']) for r in rows.values()}),
       'clarification_transcripts':len(audits),'new_mock_calls':0 if live_client else client.n_calls,'live_api_calls':client.n_calls if live_client else 0,
       'usage_this_run':client.usage,'models':models,'scope':'degree completion and selected-obligation subproblems reported separately; no empirical students or trained policy'}
    (out/'run_manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))
    return list(rows.values())
if __name__=='__main__':
    from uth_ds.live import LiveClient,BudgetStop
    from uth_ds.budget import EXPERT_SCENARIOS
    p=argparse.ArgumentParser();mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--mock',action='store_true');mode.add_argument('--live',action='store_true')
    p.add_argument('--out',default='data_uth_mock');p.add_argument('--samples',type=int,default=2)
    p.add_argument('--suite',choices=['pilot','expanded','coverage'],default='coverage');p.add_argument('--scenario-id',action='append')
    p.add_argument('--expert-scope',choices=['sentinels','all'],default='all');p.add_argument('--expert-samples',type=int,default=1)
    p.add_argument('--phase',choices=['pilot','full'],default='pilot');p.add_argument('--ledger',default='data_uth_budget/ledger.json')
    p.add_argument('--phase-budget-usd',type=float);p.add_argument('--total-budget-usd',type=float,default=100)
    a=p.parse_args()
    if a.mock:run(a.out,a.samples,a.suite,a.scenario_id,a.expert_scope,a.expert_samples)
    else:
        if a.suite!='coverage':p.error('live supports coverage suite only')
        ids=a.scenario_id
        if a.phase=='pilot':
            ids=ids or list(EXPERT_SCENARIOS)
            if len(ids)>6 or a.samples!=1:p.error('pilot: at most6 scenarios and --samples1 required')
        else:
            report_path=Path(a.ledger).parent/'pilot_cost_report.json'
            if not report_path.exists():p.error('full phase requires pilot report with same shared ledger')
            report=json.loads(report_path.read_text())
            forecast=report.get('projection_with_30_percent_margin_usd')
            if forecast is None or forecast+report['ledger_total_usd']>a.total_budget_usd:p.error('pilot forecast plus safety margin exceeds total budget; review design before full run')
        client=LiveClient(a.ledger,a.phase,a.phase_budget_usd or (5 if a.phase=='pilot' else 100),a.total_budget_usd)
        try:
            try:run(a.out,a.samples,a.suite,ids,a.expert_scope,a.expert_samples,client)
            except BudgetStop as e:print(str(e))
        finally:
            client.report(Path(a.ledger).parent/(a.phase+'_cost_report.json'));client.close()
