"""Offline reassessment of complete saved responses: no client, API or ledger writes."""
import argparse,copy,hashlib,json
from pathlib import Path
from uth_ds.experiment import ACTIONS,SCHEMA,capacity_disclosed,evaluate,reference_for
from uth_ds.scenarios import cases


def case_index(rows):
    ids={r['case'] for r in rows}
    for suite in ('coverage','expanded','pilot'):
        index={c['id']:c for c in cases(suite)}
        if ids<=index.keys():return index
    raise ValueError('Saved cases do not match this executable scenario definition')


def reassess(data,out):
    data=Path(data);out=Path(out)
    if data.resolve()==out.resolve() or out.exists():
        raise ValueError('Use a new output directory; source and existing outputs are preserved')
    source=data/'results.jsonl';blob=source.read_bytes()
    rows=[json.loads(line) for line in blob.decode('utf-8-sig').splitlines()]
    if not rows or any(r['schema']!=SCHEMA for r in rows):raise ValueError('Incompatible or empty results')
    if len({r['run_identity'] for r in rows})!=1:raise ValueError('Mixed source runs')
    # Validate complete groups before any new output is created.
    groups={}
    for r in rows:
        groups.setdefault((r['case'],r['sample_id']),[]).append(r)
    for key,g in groups.items():
        n=g[0]['worlds_n']
        if len(g)!=n or {r['world'] for r in g}!=set(range(n)) or any(r['worlds_n']!=n for r in g):
            raise ValueError('Incomplete/duplicate world group '+str(key))
    index=case_index(rows);changed=0;audits={}
    old_audit=data/'clarification_audit.jsonl'
    annotations={a['id']:a for a in map(json.loads,old_audit.read_text(encoding='utf-8-sig').splitlines())} if old_audit.exists() else {}
    code_hash=hashlib.sha256(Path(__file__).read_bytes()+b''.join(p.read_bytes() for p in sorted((Path(__file__).parent/'uth_ds').glob('*.py')))).hexdigest()
    identity=hashlib.sha256((rows[0]['run_identity']+code_hash+'offline_reassessment_v1').encode()).hexdigest()
    assessed=[]
    for r in rows:
        c=index[r['case']];w=next(w for w in c['worlds'] if w['id']==r['world'])
        if list(w['design'].pool)!=r['pool'] or w['design'].budgets[0]!=r['capacity_hours'] or w['node'].phase!=r['phase'] or len(c['worlds'])!=r['worlds_n']:
            raise ValueError('Scenario mismatch '+r['case'])
        disclosed=capacity_disclosed(r['student_answer'],r['capacity_hours'])
        new=copy.deepcopy(r)
        for a in ACTIONS:
            old=r['outcomes'][a]
            if old['completion_status']=='not_scheduled':continue
            result=evaluate(c,w,a,old['raw'],disclosed)
            # Audit-only correction must not move strict primary true-world endpoints.
            for field in ('format','feasible_true','delay_semesters','regret_semesters','completion_status','domain_errors','failures','unknown','feasible_robust_nominal'):
                if result.get(field)!=old.get(field):raise ValueError('Primary endpoint changed: '+r['case']+' '+a+' '+field)
            new['outcomes'][a]=result
        new['references']['clarify_operational']=reference_for(c,w,'clarify',disclosed)
        changed+=disclosed!=r['capacity_disclosed_auto']
        new['capacity_disclosed_auto']=disclosed
        new['source_run_identity']=r['run_identity'];new['run_identity']=identity
        new['free_choice']['selected_outcome']=new['outcomes'].get(new['free_choice']['action'])
        assessed.append(new)
        ident=r['prompt_id']+'-hours'+str(r['capacity_hours'])+'-sample'+str(r['sample_id'])
        old=annotations.get(ident,{})
        same=old.get('question')==r['question'] and old.get('answer')==r['student_answer']
        audits[ident]={'id':ident,'question':r['question'],'answer':r['student_answer'],'auto_disclosed':disclosed,
                      'human_disclosed':old.get('human_disclosed') if same else None,'notes':old.get('notes','') if same else ''}
    out.mkdir(parents=True)
    for name,items in [('results',assessed),('clarification_audit',list(audits.values()))]:
        (out/(name+'.jsonl')).write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in items),encoding='utf-8')
    manifest={'schema':SCHEMA,'run_identity':identity,'source_run_identity':rows[0]['run_identity'],
              'source_sha256':hashlib.sha256(blob).hexdigest(),'assessment_code_sha256':code_hash,'instances':len(rows),
              'disclosure_flags_changed':changed,'raw_responses_unchanged':True,'strict_true_world_endpoints_unchanged':True,
              'live_api_calls':0,'ledger_modified':False,'purpose':'offline evaluation correction; not a generation checkpoint'}
    (out/'reassessment_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest,indent=2));return assessed


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();reassess(a.data,a.out)
