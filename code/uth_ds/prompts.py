"""Common declaration contract across actions; no output repair or invented invalid-delay penalty."""
import json
from .rules import CAT
BASE='''You support academic course declarations under the UTH Digital Systems NEW curriculum.
Return ONLY one JSON object: {"courses":["<CANDIDATE_ID>"],"reason":"brief justification"}.
Your list is the final submitted declaration. No institutional filtering, substitution or truncation repairs it.
Personal workload affects performance, not institutional legality. Use only the supplied candidate IDs.
Declaration timing in this simulation: a course can be newly declared only when its nominal season matches the current phase (fall or spring), and when it is offered in the supplied scenario calendar. September is re-examination of previously registered failed courses only, not a new declaration period.
An empty declaration {"courses":[],"reason":"brief justification"} is permitted, including when no candidate can be legally declared or when declaring none is the useful choice for the stated objective. It is not a format failure. Do not force a nonempty declaration.
This is a bounded course-planning simulation, not a real student recommendation or administrative approval.
Do not invent absent personal facts, course availability, or official approvals.
No personal performance mechanism or probability of passing is known. Do not assume that declared courses are guaranteed to pass.
Minimize semesters to the objective explicitly specified in the scenario; common fully informed optimal continuation follows this first decision.
STRICT OUTPUT CONTRACT:
- Your entire response must be exactly one JSON object and nothing else.
- Start with { and end with }. Do not use Markdown fences.
- Do not write analysis, headings, notes, caveats, or prose before/after the JSON.
- Use exactly the keys "courses" and "reason".
- Keep reason to at most 35 words.
- Resolve any reconsideration internally; submit only one final object, never alternatives or corrections.
Example shape: {"courses":["<CANDIDATE_ID>"],"reason":"brief justification"}
<CANDIDATE_ID> is an illustrative placeholder, not a real course ID. Replace it only with an ID actually supplied in the candidate pool, or use an empty courses list.
'''
QUESTION='''Ask ONE short question: how many total learning hours does the student have AVAILABLE this current semester?
Total available time includes classes, projects and independent study. Ask about the student's available time budget, not hours required by courses, remaining degree workload, or missing ECTS.
Return only the question, no recommendation.'''
CLARIFY=BASE+'\nUse the student answer to update only information actually disclosed.'
RETRIEVE=BASE+'\nUse the supplied controlled retrieval of regulation excerpts and scenario calendar.'
DEFER=BASE+'\nAct as a fully informed LLM expert. You are not an observed human advisor.'
STUDENT='''Role-play a simulated student. Answer the question truthfully from the private facts supplied.
Only disclose facts relevant to the question. If the question asks something not in your facts, say you do not know.
Never fabricate institutional rules or approvals. Return one brief sentence.'''
# Source-grounded concise summaries; not verbatim quotation or a real retrieval engine.
DOCUMENTS='''CONTROLLED SOURCE SUMMARIES (source editions fixed in this experiment):
ΠΣ 2024 §2: annual declaration cap ν+6; mandatory-before-elective and smaller-semester priority;
courses from a higher study year cannot be declared; second-cycle access requires 12/24 first-cycle courses, except students after the normal four-year period.
SCENARIO DECLARATION TIMING (explicit simulation constraint): a new course declaration requires its nominal season to match the current fall/spring phase and the course to be offered in the scenario calendar. September is re-examination only, not a new declaration period.
ΠΣ 2024 §3: failed registered courses can be re-examined in September; after September failure they are re-registered next academic year.
ΠΕ edition2 2024 A2/A5: cohorts 2022–2023 onward; optional thesis 15 ECTS replacing three electives;
fourth year or later and at least 50% of first-three-year ECTS for assignment.
ΠΑ 2025 §2: after semester6 and at least75% of first-two-year ECTS for eligibility; eligibility does not guarantee a placement.
Special activities are outside this numerical ordinary-course action pool.
'''

def public_context(case):
    w=case['worlds'][0];s=w['node'].student;d=w['design']
    candidate=[{k:CAT[c][k] for k in ('code','name','ects','semester','mandatory','season')} for c in d.pool]
    record={'admission_year':s.admission_year,'active_semester':s.active_semester,'completed':sorted(s.completed),
       'registered_this_academic_year':list(s.year_history),'administrative_duration_bound':s.maximum_active_semester,
       'declaration_window_open':True,
       'phase':w['node'].phase,'degree_route':'all mandatory + 4 electives semester5 +4 semester6 +6 semester7 +6 semester8; at least240ECTS and 8 completed semesters'}
    if case.get('context_variant','rules_visible')=='rules_visible':
        record.update(annual_limit=s.annual_limit,annual_counting=d.counting,priority=d.priority_rule,
          cycle_gate='12/24 first-cycle courses, except after semester8',higher_year='not permitted')
    neutral=case.get('neutral_prompt',False)
    context={'case':case['base_profile'] if neutral else case['id'],'student_record':record,'candidates':candidate,
        'objective':case.get('objective','degree_completion'),'target_courses':d.target_courses,
        'context_variant':case.get('context_variant','rules_visible'),
        'design_prior':{'capacity_equivalent_ects':[5,10],'capacity_hours':[5*d.kappa,10*d.kappa],
          'offering_variants':len({x['design'].offerings for x in case['worlds']}),'independent_uniform_design_worlds':True},
        'performance':{'model':d.model,'hours_per_ects':d.kappa,'pass_rule':'full assigned workload coverage required',
          'allocation':'sequential declaration order, partial preparation not retained' if d.model=='priority' else 'proportional to ECTS workload; overload may make all courses fail',
          'september_hours':d.budgets[2],'future_regular_hours':'same as hidden current capacity','future_calendar':'same fixed scenario availability; synthetic assumption'},
        'availability':'unknown until retrieval' if case['family']=='offerings' else 'all listed candidates offered in their nominal season'}
    if neutral:
        context['design_prior'].pop('capacity_equivalent_ects',None)
        context['design_prior']['capacity_hours']=[150,300]
        context.pop('performance')
        context['planning_context']={'september_hours':d.budgets[2],'future_regular_hours':'same as missing current available hours','future_calendar':'fixed synthetic offering calendar'}
    return json.dumps(context,ensure_ascii=False)

def retrieved_context(world,neutral=False):
    d=world['design']
    return DOCUMENTS+'\nSCENARIO CALENDAR (synthetic, not a current official offering announcement):\n'+json.dumps({
       'offered_candidate_ids':[c for c in d.pool if c in d.offerings],
       'capacity_prior_hours':[150,300] if neutral else [5*d.kappa,10*d.kappa],
       'scenario_rule_interpretations':{'annual_limit':world['node'].student.annual_limit,
          'counting':d.counting,'priority':d.priority_rule},
       'calendar_stays_fixed_for_continuation':True},ensure_ascii=False)

def private_context(world):
    d=world['design']
    return json.dumps({'total_learning_hours_this_semester':d.budgets[0],
        'future_spring_hours':d.budgets[1],'september_hours':d.budgets[2],
        'does_not_know_missing_institutional_offerings':True},ensure_ascii=False)

CHOICE="""Select your next action BEFORE acquiring additional facts. Return ONLY
{"action":"Advise|Clarify|Retrieve|Defer","reason":"brief justification"} using one action name.
Advise: submit a declaration now. Clarify: ask the student for missing available learning hours.
Retrieve: consult the institutional source summaries and the scenario offering calendar.
Defer: refer to a fully informed LLM expert (not an observed human advisor).
Action costs are unspecified. This is a descriptive choice, not a request to minimize a defined total cost.
Use only the current public information; do not invent missing facts.
Your entire response must be exactly one JSON object, with exactly the keys "action" and "reason".
Start with { and end with }. No Markdown fences, analysis, headings, notes, or text outside the JSON.
Keep reason to at most 35 words. Submit only one final action, never alternatives or corrections.
"""
