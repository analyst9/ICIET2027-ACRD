"""Solve each coverage world independently of model responses. Run from code/: python oracle.py oracle.json"""
import json,sys
sys.path.insert(0,'.')
from uth_ds.coverage import coverage_cases
from uth_ds.solver import solve
out={};memo={}
for c in coverage_cases():
    for w in c['worlds']:
        k=(w['node'],w['design'])
        if k not in memo: memo[k]=solve(w['node'],w['design'])['semesters']
        out[f"{c['id']}|{w['id']}"]=memo[k]
json.dump(out,open(sys.argv[1],'w'))
