# Advise, Clarify, Retrieve or Defer — reproducibility package

Code, prompts, scenarios, planner, evaluation code and model outputs for the paper
*"Advise, Clarify, Retrieve or Defer: A Decision-Theoretic Framework for LLM-Based
Academic Advising on Course Selection"* (submitted to IEEE ICIET 2027).

Everything needed to **recompute every number in the paper offline** is included.
No API key and no payment are needed for that. Re-running the language-model
experiment itself is optional and paid (see the last section).

## Contents

| Folder | What it contains |
|---|---|
| `code/uth_ds/prompts.py` | All prompts (target, simulated student, expert, free choice). |
| `code/uth_ds/coverage.py` | The predetermined coverage grid: 376 scenarios, 181 academic records, 233 decision states. |
| `code/uth_ds/rules.py`, `catalogue.json` | Encoded programme rules (first-cycle gate, higher-year ban, annual ν+6 limit, mandatory-first priority, seasons) and course catalogue. |
| `code/uth_ds/solver.py` | Exact bounded-horizon planner over course pools of at most five courses; certified value of information. |
| `code/uth_ds/experiment.py`, `secondary.py`, `performance.py` | Parsing, legality checks, delay and regret, the four workload assumptions, the secondary rejection scenario. |
| `code/uth_batch_run.py`, `uth_run.py`, `uth_ds/batch.py`, `uth_ds/live.py`, `acrd/llm.py` | Runner for the Anthropic Message Batches API with a budget ledger (used for the paid run). |
| `code/uth_analyze.py`, `uth_reassess.py` | Official analysis (Tables I–III, Fig. 1 inputs, free choice, secondary scenario). |
| `code/oracle.py`, `code/failure_aware.py` | Failure-aware sensitivity metric (Opt. % and penalized regret, Table I). |
| `data/results.jsonl.gz` | All 24,320 world-level rows with raw model outputs and evaluations (gzip). |
| `data/clarification_audit.jsonl` | Clarification questions, simulated answers and the disclosure audit. |
| `results/paper_metrics/` | The exact values reported in Tables I–III, Fig. 1 and the failure-aware metric. |
| `results/analysis/` | Summary of the official analysis, secondary scenario, cost report, rerun record. |
| `protocol/` | Pre-registered protocol, coverage plan and amendments (partly in Greek, kept unchanged for provenance). |

## Models and run

- Target and simulated student: `claude-haiku-4-5-20251001`. Expert: `claude-sonnet-4-6`.
- Two target/student draws per prompt and one expert draw per world. Temperature at the API default (1.0).
- 22,688 Message Batches requests in total, all under the frozen final protocol.
- 204 requests that had first been generated during the pilot were **resubmitted** under the frozen protocol. Their new outputs replace the pilot outputs everywhere (`results/analysis/rerun_manifest.json`, `rerun_cost_and_change_summary.json`).
- Token cost of the dataset: USD 24.49 at batch prices checked on 2 October 2026.

## Reproduce the paper's numbers (offline, free)

Requires Python 3.10+ and only the standard library.

```bash
gunzip -k data/results.jsonl.gz
cd code

# Official analysis (about 3 minutes). Its summary.json matches results/analysis/summary.json.
python uth_analyze.py --data ../data --out ../results/reproduced

# Failure-aware metric (Table I, last two columns)
python oracle.py oracle.json                       # solves every case-world independently of model outputs (~1.5 min)
python failure_aware.py ../data/results.jsonl oracle.json
```

`oracle.py` decides eligibility from the planner alone: 11,942 eligible world configurations,
so 23,884 rows per target action and 11,942 for Defer. Failures (format, illegal, noncompletion)
receive a penalty of P semesters (P = 2 main; 1 and 3 as sensitivity). Bootstrap intervals use
2,000 resamples of the 181 academic records, seed 20261003.

An offline smoke test of the whole pipeline with fake model responses:

```bash
python uth_run.py --mock --suite coverage --scenario-id degree-9c7c2cdcfe86a597 --samples 1 --out ../mock_test
```

## Re-running the language-model experiment (optional, paid)

This sends real requests to the Anthropic API and is charged to your account.
Set your own key as an environment variable; never write it into a file.

```bash
export ANTHROPIC_API_KEY=...        # PowerShell: $env:ANTHROPIC_API_KEY="..."
pip install -r ../requirements.txt
python uth_batch_run.py --phase pilot --samples 1 --suite coverage --ledger budget/ledger.json --out data_pilot
python uth_batch_run.py --phase full --samples 2 --expert-samples 1 --expert-scope all \
    --suite coverage --total-budget-usd 100 --out data_full --ledger budget/ledger.json
python uth_analyze.py --data data_full --out results_full
```

The pilot uses six default scenarios with one draw; the full phase requires its cost report in the same ledger folder, and the ledger reuses any completed request whose payload and tag are identical. Outputs are stochastic,
so a new run will not reproduce the saved responses exactly. The saved dataset above is the
one analysed in the paper.

## Notes and limitations

- Student histories, available hours and offerings are synthetic. No real student data is used.
- The regulation PDFs of the Department of Digital Systems, University of Thessaly, are not
  redistributed; their file hashes are in `protocol/regulation_sources_manifest.json`, and the
  rules used are encoded in `code/uth_ds/rules.py`.
- The expert is another LLM, not a human advisor. No routing policy is trained.

## License

Code: MIT. Data, results and protocol: CC BY 4.0. See `LICENSE`.
