# V4 final evaluation freeze - 2026-10-02

This amendment follows the v4 pilot and precedes the main run. Scientific prompts,
models, payloads, scenario definitions, catalogue, legal rules, solver and sample
allocation remain byte-identical to v4. No selective retry or JSON repair is added.

The bilingual recognizer now accepts explicit numeric English/Greek hour statements
(including accent/case normalization and decimal comma), and conservatively excludes
explicit ignorance/negation, required hours and contradictory alternatives. UTF-8 encoding is explicit when reopening ledgers/checkpoints and writing audits,
so Greek text is preserved on Windows. Automatic
flags still require transcript audit; this recognizer is not a general semantic judge.
In the saved v4 pilot, all 24 student answers disclose their exact available hours;
four Greek answers were missed, affecting 16 design-world rows. Reassessment changes
information-compatible world sets and operational references, never model responses
or strict true-world feasibility/delay/regret. Existing human annotations are preserved
with matching question/answer text; annotations remain audit metadata, not automatic
evaluation overrides.

The predeclared secondary rejection endpoint in v4_amendment.md is implemented in
uth_ds/secondary.py. Entire illegal in-pool submissions with known legality become
an empty first action. Invalid format/domain/unknown outcomes remain excluded;
horizon noncompletion stays null. Primary reports remain unchanged and separate.
Secondary target/expert comparisons average the two target draws per world and use
the single scheduled expert draw without replication. Counters and pair exclusions
are explicit. This hypothetical filter is not an observed institutional practice.

uth_reassess.py validates saved scenarios and unchanged primary true-world endpoints,
retains raw text, creates provenance hashes and writes to a NEW folder. It has no API
client or ledger-write path. Reassessed outputs are not generation checkpoints.
Full generation uses its own new output folder and the copied original v4 ledger.
Request keys remain unchanged, allowing completed v4 pilot sample-0 calls to be reused.
The run identity changes because executable evaluation code is hashed. V1-v3 remain
separate. Count prior spending separately; the v4 ledger only records its own work.

Freeze these prompts before main outcomes. Model legality and format errors are
research outcomes, not reasons to keep adapting prompts. Keep strict primary and
secondary outcomes together; no empirical human or trained-policy claim is supported.
