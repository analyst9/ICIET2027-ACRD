"""Prespecified diagnostic expert subset, independent of measured information gain."""
EXPERT_SCENARIOS=('degree-9c7c2cdcfe86a597', 'degree-ac2376897154166f', 'gate-b4da5b8762a9c4dc', 'higher_year-6a2d26c091246465', 'priority-79ff56270d30459a', 'offerings-874ad282bea58246')

def scheduled_case(case,scope='sentinels',sample_id=0,expert_samples=None):
    if expert_samples is not None and (not isinstance(expert_samples,int) or expert_samples<1):raise ValueError('expert samples must be positive')
    if scope not in ('sentinels','all'):raise ValueError('expert scope')
    return dict(case,run_expert=(scope=='all' or case.get('scenario_id') in EXPERT_SCENARIOS) and (expert_samples is None or sample_id<expert_samples))
