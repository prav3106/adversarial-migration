# PROJECT_CONTEXT.md — Adversarial Behavior-Preserving COBOL Migration

## Mission
Migrate legacy COBOL programs to Python with **proof that behavior is preserved**.
We don't trust AI-generated code, so two translator agents translate each program
blind, a prosecutor agent hunts for inputs where they disagree, and the real
COBOL binary (GnuCOBOL) is the ground truth that settles every dispute.

Workflow category: application maintenance (legacy modernization).

## Agent roles
- **Translator A**: idiomatic, readable Python. Writes only to translation/a/.
  Never reads translation/b/.
- **Translator B**: line-by-line structural Python that mirrors COBOL paragraphs
  and working storage. Writes only to translation/b/. Never reads translation/a/.
- **Prosecutor**: uses Hypothesis to search for inputs where A, B, and the golden
  master disagree, then shrinks each failure to a minimal input.
- **Orchestrator**: runs the resolution loop and processes programs in dependency
  waves, with programs in the same wave in parallel.

## Non-negotiable rules
1. All numeric values use `decimal.Decimal`. Never use float, anywhere.
2. Match COBOL arithmetic exactly: COMPUTE truncates unless ROUNDED is present;
   ROUNDED means ROUND_HALF_UP. Never use Python's default banker's rounding.
3. Overflow behavior must match COBOL (high-order truncation into the field size).
4. Output comparison is **byte-exact** on fixed-width records, with no normalization.
5. Handle COMP-3 packed decimal, signed fields, and implied decimals (V) per the
   data dictionary. Never guess a field's format.
6. Translators must not add validation, logging, or logic absent from the COBOL.
7. No secrets in code. Config comes from `.env`, which is gitignored. Never print
   or commit credentials.

## Repository structure
- `legacy_source/` COBOL programs, copybooks, build.sh (source of truth, never edit)
- `dictionary/` extract.py, data_dictionary.json, dependency_graph.json
- `golden_master/` run_legacy.py, strategies.py, outputs/<program>/<hash>.json
- `translation/a/`, `translation/b/`, `translation/naive/` one .py per program
- `verify/` run_candidate.py, compare.py
- `prosecutor/` hunt.py
- `orchestrator.py`
- `reports/` findings/, fix_requests/, run_log.json, naive_baseline.json, BENCHMARK.md
- `docs/` PLAN.md, bob-sessions/ (screenshots), submission docs
- `tests/` pytest tests mirroring the structure above

## Interfaces (keep these stable)
- **Translated program**: each file exposes `run(record: dict) -> bytes`.
  The input dict is keyed by COBOL field name with Decimal/str values, and the
  output is the exact fixed-width record bytes.
- **Data dictionary entry**: field_name, programs, pic, usage (DISPLAY|COMP-3),
  digits_before, digits_after, signed, offset, length, python_type, rounding
  (truncate|half_up), source_line.
- **Golden output file**: input, output_hex, output_decoded, program, input_hash.
- **Comparison result**: one of agree_correct, a_wrong, b_wrong,
  both_wrong_same, both_wrong_different, plus a field-level diff (field, golden,
  a, b).
- **Finding**: program, minimal_input, golden, a_output, b_output, diff,
  classification, timestamp.

## Resolution protocol
1. The prosecutor runs its budget (N inputs, with a minimum sample count per
   boundary class).
2. On a finding, the failing translator(s) receive the minimal input, their
   output, and the golden output, and must fix their translation.
3. Maximum 3 fix attempts per translator per program, then mark the program
   NEEDS_HUMAN_REVIEW.
4. A program passes when the prosecutor exhausts its budget with zero findings.
   Prefer A's translation if both pass.

## Boundary classes (the input generator must cover all of these)
zero · smallest unit (0.01) · max value · max minus smallest unit ·
negative max (if signed) · rounding edge (x.xx5) · overflow (above field max) ·
random mid-range

## Working rules for every session
- Read only the files named in the prompt, plus this file. Don't scan the whole repo.
- Don't refactor, rename, or reformat code outside the task's scope.
- Every component gets a CLI entry point and pytest tests.
- Finish every task by running its tests and showing they pass.
- If a rule here conflicts with the prompt, stop and ask. Don't guess.
- Keep responses brief: summarize what changed, list the files touched, show the
  test results.

## Definition of done (project)
- Every program is PASSED or NEEDS_HUMAN_REVIEW, with a full run log.
- The naive baseline has been measured against the same inputs.
- reports/BENCHMARK.md has been generated.
- The repo contains no secrets.