"""Two PREDECLARED deterministic workload hypotheses, exact rational arithmetic."""
from fractions import Fraction as F
from .rules import CAT
MODELS=('priority','proportional')
def study(courses,budget,kappa=25,model='priority'):
    if model not in MODELS:raise ValueError('model')
    if len(courses)!=len(set(courses)):raise ValueError('duplicate study courses')
    k=F(str(kappa));b=F(str(budget))
    if not 25<=k<=30 or b<0:raise ValueError('kappa/budget')
    if any(CAT[c]['kind']!='course' for c in courses):raise ValueError('ordinary courses only')
    need={c:k*CAT[c]['ects'] for c in courses};total=sum(need.values(),F(0));left=b;hours={}
    for c in courses:
        if model=='priority':hours[c]=min(left,need[c]);left-=hours[c]
        else:hours[c]=need[c]*min(F(1),b/total) if total else F(0)
    # Proportional + hard threshold: overload can cause all courses to fail.
    # This is a deliberate structural sensitivity, NOT an empirical pass model.
    passed=tuple(c for c in courses if hours[c]>=need[c])
    return {'passed':passed,'failed':tuple(c for c in courses if c not in passed),
      'hours':{c:str(h) for c,h in hours.items()},'model':model,'unused_hours':str(b-sum(hours.values(),F(0)))}
