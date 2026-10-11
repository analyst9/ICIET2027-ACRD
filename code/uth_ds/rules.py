"""Source-grounded validator. Unknown facts are not replaced by invented approvals."""
from dataclasses import dataclass,field
from pathlib import Path
import json
CAT={r['code']:r for r in json.loads(Path(__file__).with_name('catalogue.json').read_text())['courses']}
ORDINARY={c for c,r in CAT.items() if r['kind']=='course'}
MANDATORY={c for c in ORDINARY if CAT[c]['mandatory']}
FIRST={c for c in MANDATORY if CAT[c]['semester']<=4}

@dataclass(frozen=True)
class Student:
    admission_year:int
    active_semester:int  # authoritative academic record; interruptions already adjudicated
    completed_active_semesters:int|None=None
    completed:frozenset=field(default_factory=frozenset)
    recognized_english:frozenset=field(default_factory=frozenset)
    exemption_counts_for_gate:bool|None=None
    year_history:tuple|None=None  # registered IDs incl. failed courses, current academic year
    annual_limit:int|None=None  # declared scenario interpretation, NOT an official universal 18
    maximum_active_semester:int|None=None
    within_duration:bool|None=None
    year_authoritative:bool=True
    declaration_open:bool|None=None

@dataclass
class Verdict:
    failures:list=field(default_factory=list)
    unknown:list=field(default_factory=list)
    assumptions:list=field(default_factory=list)
    @property
    def status(self):return 'infeasible' if self.failures else 'insufficient_data' if self.unknown else 'feasible'
    def add(self,rule,detail,unknown=False):
        (self.unknown if unknown else self.failures).append({'rule':rule,'detail':detail})
    def to_dict(self):return {'status':self.status,'failures':self.failures,'unknown':self.unknown,'assumptions':self.assumptions}

def common(s):
    v=Verdict()
    if s.admission_year<2022:v.add('R01','outside new-cohort scope')
    if s.active_semester<1:v.add('STATE','invalid active semester')
    if not s.year_authoritative:v.add('R12','active year/interruptions require adjudicated record',True)
    invalid=set(s.completed)|set(s.recognized_english)
    if invalid-set(CAT):v.add('STATE','unknown completed IDs')
    if set(s.recognized_english)-{'Υ100','Υ200'}:v.add('R21','unknown English recognition')
    if s.maximum_active_semester is not None:
        if s.active_semester>s.maximum_active_semester:v.add('R22','outside supplied duration limit')
        v.assumptions.append('duration bound supplied as administrative scenario fact')
    elif s.within_duration is None:v.add('R22','duration eligibility unavailable',True)
    elif not s.within_duration:v.add('R22','administratively outside permitted duration')
    return v

def credits(s,first_years=None):
    return sum(CAT[c]['ects'] for c in set(s.completed)|set(s.recognized_english)
      if c in CAT and (first_years is None or CAT[c]['semester'] is not None and CAT[c]['semester']<=2*first_years))

def gate(s,v):
    if s.active_semester>8:return True  # completed normal 4-year period, not merely fourth year
    n=len(set(s.completed)&FIRST)
    if n>=12:return True
    e=set(s.recognized_english)&FIRST-set(s.completed)
    if e and n+len(e)>=12:
        if s.exemption_counts_for_gate is None:v.add('R09','recognition counting in 12/24 unresolved',True);return None
        if s.exemption_counts_for_gate:return True
    return False

def validate_declaration(s,courses,season,offered=None,priority_rule=None,counting='registrations'):
    v=common(s)
    if season not in ('fall','spring'):v.add('STATE','not a teaching declaration period');return v
    if not isinstance(courses,list) or not all(isinstance(c,str) for c in courses):
        v.add('FORMAT','courses must be a list of IDs',True);return v
    if len(courses)!=len(set(courses)):v.add('R37','duplicate ID')
    if s.declaration_open is None:v.add('R16','declaration window unknown',True)
    elif not s.declaration_open:v.add('R16','declaration window closed')
    if s.active_semester<=2 and courses:v.assumptions.append('R17 first-year declaration normally submitted by secretariat')
    known=[c for c in courses if c in CAT]
    for c in courses:
        if c not in CAT:v.add('R37','unknown ID '+c);continue
        r=CAT[c]
        if r['kind']!='course':v.add('R24/R31','special activity requires its own workflow, not an ordinary course declaration');continue
        if c in set(s.completed)|set(s.recognized_english):v.add('R37','already satisfied '+c)
        if r['season']!=season:v.add('R07','wrong nominal season '+c)
        if (r['semester']+1)//2>(s.active_semester+1)//2:v.add('R11','higher academic year '+c)
        if offered is None:v.add('R07','annual availability unknown '+c,True)
        elif c not in offered:v.add('R07','not offered in supplied calendar '+c)
    if any(CAT[c]['kind']=='course' and CAT[c]['semester']>4 for c in known):
        if gate(s,v) is False:v.add('R09','12/24 gate not met')
    if courses:
        if s.annual_limit is None or s.year_history is None:v.add('R13','annual limit or complete current-year registrations missing',True)
        else:
            if counting=='registrations':n=len(s.year_history)+len(courses)
            elif counting=='distinct_ids':n=len(set(s.year_history)|set(courses))
            else:raise ValueError('unknown annual counting interpretation')
            v.assumptions.append('R13 supplied annual_limit; counting='+counting)
            if n>s.annual_limit:v.add('R13','annual declaration budget exceeded')
    ordinary=[c for c in known if CAT[c]['kind']=='course']
    if len(ordinary)>1:
        keys={'mandatory_then_semester':lambda c:(not CAT[c]['mandatory'],CAT[c]['semester']),
              'semester_then_mandatory':lambda c:(CAT[c]['semester'],not CAT[c]['mandatory'])}
        if priority_rule is None:v.add('R14/R15','combined precedence interpretation not selected',True)
        elif priority_rule not in keys:raise ValueError('unknown priority interpretation')
        else:
            v.assumptions.append('R14/R15 order-only interpretation='+priority_rule)
            values=[keys[priority_rule](c) for c in ordinary]
            if values!=sorted(values):v.add('R14/R15','declaration out of supplied priority order')
    return v

def thesis_eligibility(s,stage='eligible',facts=None):
    v=common(s);facts=facts or {}
    if s.active_semester<7:v.add('R23','not fourth year or later')
    if credits(s,3)<90:v.add('R23','less than 90 ECTS from first three curriculum years')
    if stage not in ('eligible','assign'):raise ValueError('stage')
    if stage=='assign':
        for key,rule in [('assignment_window_open','R25'),('supervisor_agrees','R24'),('assignment_signed','R24'),('department_validated','R24')]:
            require_fact(v,facts,key,rule)
        load=facts.get('supervisor_active_load');exception=facts.get('load_exception_approved')
        if load is None:v.add('R26','supervisor load unavailable',True)
        elif load>=10 and exception is not True:
            v.add('R26','capacity exception approval unknown' if exception is None else 'supervisor full',exception is None)
    return v

def require_fact(v,facts,key,rule):
    value=facts.get(key)
    if value is None:v.add(rule,key+' unknown',True)
    elif value is not True:v.add(rule,key+' not satisfied')

def internship_eligibility(s,stage='eligible',facts=None):
    v=common(s);facts=facts or {}
    if s.active_semester<7:v.add('R30','sixth semester not completed')
    if credits(s,2)<90:v.add('R30','less than 90 ECTS from first two years')
    if stage not in ('eligible','start'):raise ValueError('stage')
    if stage=='start':
        for key,rule in [('selected','R31'),('approved_host','R34'),('atlas_recorded','R34'),('kinship_clearance','R34'),('documents_complete','R35'),('start_window_open','R31')]:require_fact(v,facts,key,rule)
    return v

def internship_score(ects_by_end_sixth,mean_at_application,social_bonus):
    """Supplied adjudicated bonus; no assumption about stacking overlapping categories."""
    from fractions import Fraction
    if not 0<=ects_by_end_sixth<=180 or not 0<=mean_at_application<=10 or social_bonus<0:raise ValueError('score input')
    return Fraction(str(ects_by_end_sixth))/180*Fraction(str(mean_at_application))*10+Fraction(str(social_bonus))

def graduation(s):
    """Certified only for the ordinary-course route; special-route accounting stays unresolved."""
    sat=set(s.completed)|set(s.recognized_english)
    if {'Ε900','Ε1000'}&sat:return {'status':'insufficient_data','reason':'special-route allocation must be specified'}
    minimum_met=s.active_semester>8 or s.completed_active_semesters is not None and s.completed_active_semesters>=8
    ok=minimum_met and MANDATORY<=sat and credits(s)>=240
    ok=ok and all(sum(c in sat for c in ORDINARY if not CAT[c]['mandatory'] and CAT[c]['semester']==sem)>=need for sem,need in [(5,4),(6,4),(7,6),(8,6)])
    return {'status':'complete' if ok else 'incomplete','ects':credits(s)}
