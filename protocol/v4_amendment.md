# V4 amendment - 2026-10-02

This amendment follows the v3 pilot, before inspecting main v4 outcomes. V3 full
execution was stopped locally by the user; its exact server submission status
must be established from its ledger/API history. We do not claim zero v3 full
charges or that no batches were accepted. V1-v3 data remain historical pilot and
engineering records and are not pooled with v4 main outcomes.

## Fixed changes

All declaration actions share the explicit synthetic timing rule implemented by
the validator: new declarations in fall/spring must match nominal course season
and actual scenario offering. September re-examines eligible previously failed
registrations only. This explicit simulation convention is not presented as an
additional verbatim institutional regulation. Empty lists are legal submissions
when the student's other administrative conditions allow; the model may choose
one when nothing legal/useful can be submitted. Format examples use an illustrative
placeholder absent from the catalogue and pools, explicitly never an output ID.

Clarify asks about total AVAILABLE learning hours in the current semester, not
hours required to complete courses or a degree. The simulated student's prompt
and truthful private facts are unchanged. Automatic disclosure flags still need
human audit, including explicit ignorance/denial and ambiguous numeric mentions.
Use clarification_audit.jsonl to retain human judgments; do not treat an automatic
flag as proof of disclosure. No recognizer change is made in this amendment.

The expert has no cache_control in Batch payloads. The other roles keep existing
cache metadata. Usage-based cost accounting is unchanged, and budget reservations
remain conservative even for uncached expert input. Batch payloads omit temperature;
the documented API default is 1.0 (https://platform.claude.com/docs/en/api/messages/create).
The legacy function parameter value 0 is ignored by the batch adapter and is not
an experimental temperature setting. Two draws need not yield different text.

Models, scenarios, restricted pools, information sets, solver, horizon, primary
parser/evaluator and sample allocation are unchanged: full target/student=2,
expert=1 on sample 0; expert is an LLM, not an observed human advisor. Costs are
scenario assumptions, not observed human referral costs. Freeze v4 scientific
prompts before full generation. Preserve complete outputs including failures.

## Primary outcomes and denominators

Report syntax/schema failures, out-of-pool/domain errors, legal feasibility,
noncompletion within the bounded horizon, conditional delay and regret separately.
Show objective/context/mechanism strata and actual sample and world denominators.
Reused responses across worlds are not independent model draws. Paired comparisons
use common evaluable worlds and state exclusions. A successful pilot format check
is not evidence of correct decisions, human advising efficacy or a trained policy.

## Predeclared secondary analysis: rejected illegal declaration becomes empty

For a syntactically valid, in-pool declaration found ILLEGAL in the true world,
assume a simulated administrative filter rejects the ENTIRE declaration, submits
no new courses at this decision event, and otherwise preserves the state, including
existing September re-examination rights. Evaluate first_action_value(node, design, ())
using the same horizon, performance mechanism and fully informed continuation.
Do not partially accept, reorder, substitute, or repair a declaration.

For legal, known, in-pool declarations, retain original first-action value. Exclude
invalid JSON/schema, out-of-pool IDs and unresolved legality (unknown facts) from
this secondary numeric endpoint; report their counts explicitly. Empty declarations
already legal receive their own original value. Do not convert censored/unreachable
values into a fixed numeric penalty. Report completion coverage and conditional
means together; show paired common-world denominators and changed selections.
Keep primary strict outcomes visible beside the secondary values. This is a
hypothetical administrative rejection mechanism, not evidence that the institution
actually implements this filter or that an LLM's invalid advice is acceptable.

This document predeclares the secondary analysis; it is not yet implemented in the
primary uth_analyze.py. Implement/validate it on saved v4 results before reporting
secondary numerical findings, without changing this rule after seeing outcomes.

## Pilot review before full

Check 192 expected pilot worlds and their run identity, JSON failures, empty-only
world feasibility, and model answers/questions; audit disclosure flags. Compare
v3/v4 as separate pilot versions only; do not claim changes are statistically
independent or attributable solely to one prompt edit. Obtain fresh usage-based
forecast. New v4 ledger starts from zero and excludes all earlier charges; account
for those separately when applying a user's overall spending limit.
