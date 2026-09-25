# PLAN.md — Adversarial Behavior-Preserving COBOL Migration

## Top-Level Overview

Migrate each COBOL module to Python and **prove** behavior is preserved.
Two independent translator agents (A and B) each produce a Python module.
A prosecutor agent (Hypothesis-powered) searches for inputs where A, B, and
the real GnuCOBOL binary disagree. The binary is ground truth. Any failing
translator gets the minimal counterexample and must fix its translation.
A program is *done* when the prosecutor exhausts its budget finding nothing.

**Scope for this plan:** Five programs (VALIDATE, GROSSPAY, TAXCALC, DEDUCT,
PAYSLIP) split from a payroll domain with shared copybooks, a real dependency
graph, and deliberate semantic traps in each program. This gives wave scheduling
and parallel subagents genuine independent work.

**Budget constraint:** 38 Bob coins total. Sessions are merged wherever the
work is cohesive and the test surface is small.

---

## Correction Log (applied from user review)

| # | Correction |
|---|-----------|
| 1 | Translator isolation is a **hard constraint**: A and B are built in separate Bob sessions; neither session may read the other's directory. |
| 2 | GnuCOBOL is installed locally. No Docker fallback needed. |
| 3 | `translation/naive/` is an **honest single-pass translation** (Decimal, correct rounding, full rules), with no prosecutor loop. It is a fair benchmark baseline — **not** a float-based deliberate-wrong baseline. |
| 4 | Legacy runner uses `cobc -x` to produce an executable, invoked via `subprocess` with **file-based I/O**. No ctypes, no `.so`. Golden outputs are cached, so speed is not a concern. |
| 5 | Sign-handling risk corrected: moving a negative value into an **unsigned** field stores the **absolute value** (sign dropped). It does **not** clamp to zero. |
| 6 | COMP-3 encode/decode errors are caught by round-trip tests inside `tests/test_run_legacy.py`, not by `test_extract.py`. |
| 7 | PAYROLL.cbl is **split into 5 programs** (VALIDATE, GROSSPAY, TAXCALC, DEDUCT, PAYSLIP) with shared copybooks and a real dependency graph. Each program contains at least one deliberate semantic trap (see trap table below). |
| 8 | **Every build step must include passing pytest tests.** A step is not done until its tests pass. |

---

## Component Breakdown

### 1. `legacy_source/`
| | |
|---|---|
| **Responsibility** | Source of truth. Five COBOL programs, shared copybooks, and `build.sh`. Never edited after creation. |
| **Inputs** | `.cbl` source files, copybooks `.cpy` |
| **Outputs** | Compiled executables (`bin/<PROGRAM>`) invoked by `run_legacy.py` via `subprocess` |
| **Implements** | No Python interface — it *is* the ground truth |
| **Consumes** | Nothing from the Python side |

### 2. `dictionary/extract.py` + `data_dictionary.json`
| | |
|---|---|
| **Responsibility** | Parse COBOL WORKING-STORAGE/LINKAGE sections; emit a machine-readable field registry |
| **Inputs** | `.cbl` source files |
| **Outputs** | `data_dictionary.json` — array of **Data Dictionary Entry** objects |
| **Implements** | **Data Dictionary Entry** interface (field_name, programs, pic, usage, digits_before, digits_after, signed, offset, length, python_type, rounding, source_line) |
| **Consumes** | Nothing |

### 3. `golden_master/strategies.py`
| | |
|---|---|
| **Responsibility** | Generate input records covering all eight boundary classes |
| **Inputs** | `data_dictionary.json`, program name, count, optional seed |
| **Outputs** | List of input dicts keyed by COBOL field name with `Decimal` values |
| **Implements** | Boundary class coverage (zero, smallest_unit, max_value, max_minus_unit, negative_max, rounding_edge, overflow, random_mid_range) |
| **Consumes** | Data Dictionary Entry interface |

### 4. `golden_master/run_legacy.py`
| | |
|---|---|
| **Responsibility** | Encode input dict → fixed-width file, invoke GnuCOBOL executable via `subprocess`, decode output file, persist golden record |
| **Inputs** | Input dict, program name, data dictionary, path to compiled executable |
| **Outputs** | **Golden Output File** (input, output_hex, output_decoded, program, input_hash) written under `golden_master/outputs/<program>/` |
| **Implements** | **Golden Output File** interface |
| **Consumes** | Data Dictionary Entry interface, compiled COBOL executable |
| **I/O method** | File-based: write input to a temp file, pass path as arg to executable, read output from a second temp file. No ctypes, no shared objects. |

### 5. `translation/a/<PROGRAM>.py` and `translation/b/<PROGRAM>.py`
| | |
|---|---|
| **Responsibility** | A: idiomatic Python. B: structural Python mirroring COBOL paragraphs. Each blind to the other and built in separate Bob sessions. |
| **Inputs** | `record: dict` (field_name → Decimal/str) |
| **Outputs** | `bytes` — exact fixed-width output record |
| **Implements** | **Translated Program** interface: `run(record: dict) -> bytes` |
| **Consumes** | Data Dictionary Entry interface (for field widths and rounding rules) |
| **Hard isolation** | Session A never reads `translation/b/`. Session B never reads `translation/a/`. |

### 6. `translation/naive/<PROGRAM>.py` (Honest single-pass baseline)
| | |
|---|---|
| **Responsibility** | A fair single-pass translation following all rules (Decimal, correct rounding, correct overflow/sign handling) — but with no prosecutor loop and no fix iterations. Benchmarks translator quality before adversarial hardening. |
| **Inputs / Outputs** | Same `run(record) -> bytes` interface |
| **Implements** | **Translated Program** interface |
| **Important** | This is **not** a float-based deliberately-wrong baseline. It is honest but unverified. |

### 7. `verify/run_candidate.py`
| | |
|---|---|
| **Responsibility** | Dynamically import and call any translated module; return raw output bytes |
| **Inputs** | Program name, variant (`a`/`b`/`naive`), input dict |
| **Outputs** | Raw `bytes` output from the module |
| **Implements** | Nothing — utility bridge |
| **Consumes** | **Translated Program** interface |

### 8. `verify/compare.py`
| | |
|---|---|
| **Responsibility** | Byte-exact comparison of golden vs A vs B; classify result; produce field-level diff |
| **Inputs** | `golden: bytes`, `a_output: bytes`, `b_output: bytes` (optional), program name |
| **Outputs** | **Comparison Result** (classification, agree bool, field-level diff, hex values) |
| **Implements** | **Comparison Result** interface (agree_correct, a_wrong, b_wrong, both_wrong_same, both_wrong_different, field diff) |
| **Consumes** | Data Dictionary Entry interface (for field decoding in diffs) |

### 9. `prosecutor/hunt.py`
| | |
|---|---|
| **Responsibility** | Hypothesis-driven adversarial search; shrink failures to minimal inputs; save findings |
| **Inputs** | Program name, budget, variant list |
| **Outputs** | **Finding** objects written to `reports/findings/` |
| **Implements** | **Finding** interface (program, minimal_input, golden, a_output, b_output, diff, classification, timestamp) |
| **Consumes** | Translated Program interface, Golden Output File interface, Comparison Result interface |

### 10. `orchestrator.py`
| | |
|---|---|
| **Responsibility** | Drive the resolution loop: run prosecutor → dispatch fix requests → retry → mark PASSED or NEEDS_HUMAN_REVIEW. Process programs in dependency waves in parallel. |
| **Inputs** | `dependency_graph.json`, program list, run config |
| **Outputs** | `reports/run_log.json`, fix request files under `reports/fix_requests/` |
| **Implements** | Resolution protocol (max 3 fix attempts, prefer A if both pass) |
| **Consumes** | Finding interface, Comparison Result interface |

---

## COBOL Program Split — Five Programs with Shared Copybooks

PAYROLL.cbl is replaced by five focused programs. Each contains at least one
deliberate semantic trap. The dependency graph creates two waves.

### Shared copybooks
| File | Contents |
|------|----------|
| `EMPFIELDS.cpy` | Employee ID, name — shared by all programs |
| `PAYFIELDS.cpy` | Gross pay, net pay, tax amount, deductions — shared by TAXCALC, DEDUCT, PAYSLIP |

### Program descriptions and semantic traps

| Program | Wave | Depends on | Deliberate semantic trap(s) |
|---------|------|------------|------------------------------|
| **VALIDATE** | 0 | none | Signed field: stores absolute value when a negative hours value is moved to an unsigned field (sign dropped, not clamped). |
| **GROSSPAY** | 0 | none | Truncation without ROUNDED: `COMPUTE GROSS-PAY = HOURS-WORKED * HOURLY-RATE` truncates toward zero. COMP-3 field for GROSS-PAY. |
| **TAXCALC** | 1 | GROSSPAY | COMPUTE ROUNDED: `COMPUTE TAX-AMOUNT ROUNDED = GROSS-PAY * TAX-RATE` uses ROUND_HALF_UP. |
| **DEDUCT** | 1 | GROSSPAY | Overflow at field max: DEDUCTIONS field is narrow (PIC 9(5)V99); overflow silently drops high-order digits (modulo truncation). |
| **PAYSLIP** | 2 | TAXCALC, DEDUCT | Combines all: signed NET-PAY field, COMP-3 storage, implied-decimal V, final MOVE truncation into fixed-width output. |

### Dependency graph (dependency_graph.json)
```json
{
  "VALIDATE":  { "wave": 0, "depends_on": [] },
  "GROSSPAY":  { "wave": 0, "depends_on": [] },
  "TAXCALC":   { "wave": 1, "depends_on": ["GROSSPAY"] },
  "DEDUCT":    { "wave": 1, "depends_on": ["GROSSPAY"] },
  "PAYSLIP":   { "wave": 2, "depends_on": ["TAXCALC", "DEDUCT"] }
}
```

**Wave 0** (VALIDATE, GROSSPAY) can run in parallel.
**Wave 1** (TAXCALC, DEDUCT) can run in parallel after wave 0 passes.
**Wave 2** (PAYSLIP) runs last.

---

## Build Order

Each step is independently testable before the next begins. **No step is complete
without passing pytest tests.**
Steps marked **[PRIORITY]** are on the demo-critical path.

---

### Step 1 — Repository skeleton + tooling **[PRIORITY]**

**Status:** `[ ] pending`

**Intent:** Establish the package layout, test discovery, tooling config, and
environment template so every subsequent step has a clean base to build on.

**Files created:**
- `.gitignore`, `.env.example`, `requirements.txt`
- `__init__.py` stubs for every package
- `pytest.ini` or `pyproject.toml` with test discovery config

**Tests that must pass:**
- `pytest --collect-only` discovers all test files without import errors.

**Dependencies:** none

**Merge note:** Combine with Step 2 in one session.

---

### Step 2 — COBOL source split + `dictionary/extract.py` **[PRIORITY]**

**Status:** `[ ] pending`

**Intent:** Replace single `PAYROLL.cbl` with five focused programs (VALIDATE,
GROSSPAY, TAXCALC, DEDUCT, PAYSLIP) sharing two copybooks. Each program must
contain its assigned semantic trap. The extractor parses all five and emits a
combined `data_dictionary.json` and `dependency_graph.json`.

**Files created / replaced:**
- `legacy_source/VALIDATE.cbl`, `GROSSPAY.cbl`, `TAXCALC.cbl`, `DEDUCT.cbl`, `PAYSLIP.cbl`
- `legacy_source/EMPFIELDS.cpy`, `PAYFIELDS.cpy`
- `legacy_source/build.sh` (updated to compile all five with `cobc -x`)
- `legacy_source/PAYROLL.cbl` — **deleted** (replaced by the five above)
- `dictionary/extract.py`
- `dictionary/data_dictionary.json`
- `dictionary/dependency_graph.json`
- `tests/test_extract.py`

**Tests that must pass:**
- Parse all five `.cbl` files; assert every expected field appears with correct
  pic, offset, length, digits_before/after, rounding, and usage (DISPLAY or COMP-3).
- Assert no field has `python_type == "float"`.
- Assert `dependency_graph.json` has correct waves (VALIDATE/GROSSPAY wave=0,
  TAXCALC/DEDUCT wave=1, PAYSLIP wave=2).
- Assert GROSSPAY has at least one field with `usage == "COMP-3"`.
- Assert VALIDATE has at least one unsigned field.

**Dependencies:** Step 1

**Note on COMP-3 encode/decode tests:** These belong in `tests/test_run_legacy.py`
(Step 4), not here. `test_extract.py` only verifies the parsed metadata.

---

### Step 3 — `golden_master/strategies.py` **[PRIORITY]**

**Status:** `[ ] pending`

**Intent:** Produce inputs covering all eight boundary classes for any given
program, driven by the data dictionary so the generator is program-agnostic.

**Files created:**
- `golden_master/strategies.py`
- `tests/test_strategies.py`

**Tests that must pass:**
- For each of the five programs, `generate_inputs("<PROGRAM>", count=8)` returns
  at least 8 records.
- Each of the 8 boundary classes is represented.
- All numeric values are `Decimal` instances — no `float` anywhere.
- The `overflow` class value exceeds the field maximum.
- The `zero` class value is `Decimal("0")`.
- For VALIDATE, the `negative_max` class produces a negative value on the signed
  field (VALIDATE is the program with the sign trap).

**Dependencies:** Step 2

---

### Step 4 — `golden_master/run_legacy.py` **[PRIORITY]**

**Status:** `[ ] pending`

**Intent:** Encode an input dict to a fixed-width binary file, invoke the
GnuCOBOL executable via `subprocess`, read the fixed-width output file, decode
it back to a dict, and persist the golden record. Caching means the subprocess
call happens only once per unique input hash.

**I/O contract:**
- Write the input record to a temp file as fixed-width bytes.
- Pass the input path and output path as positional args to the compiled executable.
- Read the output file; decode per data dictionary.
- No ctypes. No shared objects. Pure subprocess + file I/O.

**Files created:**
- `golden_master/run_legacy.py`
- `tests/test_run_legacy.py`

**Tests that must pass:**
- `encode_input` round-trip: encode a known record, assert byte positions match
  the data dictionary offsets exactly.
- `decode_output` round-trip: given a known hex string, assert Decimal values
  match expected (correct scale applied to implied-decimal V fields).
- **COMP-3 round-trip test**: encode a Decimal value into a COMP-3 field; decode
  it; assert the value is bit-for-bit identical. Catches packed-decimal encoder
  bugs.
- **Sign round-trip test**: encode a negative value into a signed DISPLAY field;
  decode it; assert the sign is preserved. Encode into an unsigned field; assert
  the decoded value equals `abs(input)` (sign dropped, not clamped).
- Integration test (requires GnuCOBOL): run GROSSPAY with a known input; assert
  golden output matches manually-computed expected bytes. Mark with
  `@pytest.mark.integration` and gate on `GNUCOBOL_AVAILABLE` env flag.

**Dependencies:** Step 2

---

### Step 5 — `verify/compare.py` + `verify/run_candidate.py` **[PRIORITY]**

**Status:** `[ ] pending`

**Intent:** Two small utility modules that form the evaluation backbone. Merged
into one step because both are pure logic with no external dependencies.

**Files created:**
- `verify/compare.py`
- `verify/run_candidate.py`
- `tests/test_compare.py`
- `tests/test_run_candidate.py`

**Tests that must pass (`compare.py`):**
- Three identical byte strings → `agree_correct`.
- A differs, B matches golden → `a_wrong`.
- B differs, A matches golden → `b_wrong`.
- Both differ with same bytes → `both_wrong_same`.
- Both differ with different bytes → `both_wrong_different`.
- Field diff lists correct field names, golden values, and candidate values.
- No float arithmetic anywhere in this module.

**Tests that must pass (`run_candidate.py`):**
- Import a minimal stub module exposing `run(record) -> bytes`; assert bytes pass
  through unchanged.
- `FileNotFoundError` for a missing module path.
- `AttributeError` if the module lacks a `run` function.
- `TypeError` if `run` returns a non-bytes value.

**Dependencies:** Step 2

---

### Step 6 — Translator A — all five programs (Session A) **[PRIORITY]**

**Status:** `[ ] pending`

**Intent:** Translate all five COBOL programs to idiomatic Python in a single
**dedicated Bob session**. Session A reads `legacy_source/` and `dictionary/`
only — it must never open any file under `translation/b/`.

**Files created (Session A only):**
- `translation/a/VALIDATE.py`
- `translation/a/GROSSPAY.py`
- `translation/a/TAXCALC.py`
- `translation/a/DEDUCT.py`
- `translation/a/PAYSLIP.py`
- `tests/test_translation_a.py`

**Tests that must pass:**
- For each program, a known input with integer values → expected output byte
  positions are correct.
- All output values decoded as `Decimal`, not float.
- Overflow input → high-order truncation, no exception raised.
- Rounding edge input (x.xx5) on a truncating COMPUTE → result truncates, does
  NOT round up.
- COMPUTE ROUNDED (TAXCALC) → result rounds half-up.
- Unsigned field receives a negative value → decoded value equals `abs(input)`
  (VALIDATE trap).
- Output is the correct fixed-width byte length for each program.
- Filler bytes are ASCII spaces.

**Hard isolation rule:** Session A must never read `translation/b/`.

**Dependencies:** Steps 2, 4 (encode/decode helpers), 5

---

### Step 7 — Translator B — all five programs (Session B) **[PRIORITY]**

**Status:** `[ ] pending`

**Intent:** Translate all five COBOL programs to structural Python (mirroring
COBOL paragraph structure) in a **separate dedicated Bob session**, blind to
Session A's output.

**Files created (Session B only):**
- `translation/b/VALIDATE.py`
- `translation/b/GROSSPAY.py`
- `translation/b/TAXCALC.py`
- `translation/b/DEDUCT.py`
- `translation/b/PAYSLIP.py`
- `tests/test_translation_b.py`

**Tests that must pass:**
- Same structural tests as Step 6, applied to variant B.
- For all 8 boundary-class inputs per program:
  `run_candidate("<PROGRAM>", "a", record) == run_candidate("<PROGRAM>", "b", record)`
  Both translations must agree with each other on a correct implementation.

**Hard isolation rule:** Session B must never read `translation/a/`.

**Dependencies:** Steps 5, 6

---

### Step 8 — Naive baseline — all five programs

**Status:** `[ ] pending`

**Intent:** Produce honest single-pass translations (Decimal, correct rounding,
all non-negotiable rules from `PROJECT_CONTEXT.md`) without any prosecutor loop
or fix iterations. This is the "unaided AI" baseline for benchmark comparison.

**Files created:**
- `translation/naive/VALIDATE.py`
- `translation/naive/GROSSPAY.py`
- `translation/naive/TAXCALC.py`
- `translation/naive/DEDUCT.py`
- `translation/naive/PAYSLIP.py`
- `tests/test_translation_naive.py`

**Tests that must pass:**
- Each module imports and `run()` returns the correct fixed-width byte length.
- All numeric arithmetic uses `Decimal`.
- At least one boundary-class input on at least one program produces output
  that differs from Translator A (demonstrating that the prosecutor loop
  adds real value over a naive single-pass translation).

**Note:** Naive translations follow all rules but have not been adversarially
verified. They may still have subtle errors — that is the point.

**Dependencies:** Step 5

---

### Step 9 — `prosecutor/hunt.py` **[PRIORITY]**

**Status:** `[ ] pending`

**Intent:** Use Hypothesis to search for inputs where a candidate translation
disagrees with the golden master, then shrink each failure to the minimal
counterexample and persist the finding.

**Files created:**
- `prosecutor/hunt.py`
- `tests/test_hunt.py`

**Tests that must pass:**
- Hunt with a deliberately buggy stub module → at least one finding returned.
- Hunt with two identical correct stubs → zero findings returned.
- Each finding contains all required keys: program, minimal_input, golden,
  a_output, b_output, diff, classification, timestamp.
- `minimal_input` has Decimal-serializable values, no float.
- Finding is persisted to `reports/findings/<program>/`.
- No GnuCOBOL required: tests mock `run_cobol` with a precomputed golden fixture.

**Dependencies:** Steps 3, 5

---

### Step 10 — `orchestrator.py`

**Status:** `[ ] pending`

**Intent:** Drive the full resolution loop across all five programs using the
dependency-wave schedule. Dispatch fix requests, enforce the 3-attempt limit,
and write the run log.

**Files created:**
- `orchestrator.py`
- `tests/test_orchestrator.py`

**Tests that must pass:**
- A program with zero findings from a mock prosecutor → status `PASSED` in run log.
- A program exceeding `MAX_FIX_ATTEMPTS` → status `NEEDS_HUMAN_REVIEW`.
- Prefer A's translation when both pass.
- `run_log.json` is written with correct schema.
- Wave scheduling: VALIDATE and GROSSPAY (wave 0) are launched before TAXCALC
  and DEDUCT (wave 1), which are launched before PAYSLIP (wave 2).
- Wave 1 does not start if a wave 0 program has status `NEEDS_HUMAN_REVIEW`.

**Dependencies:** Steps 8, 9

---

### Step 11 — `reports/generate_benchmark.py` + `reports/BENCHMARK.md`

**Status:** `[ ] pending`

**Intent:** Generate a human-readable benchmark report comparing A, B, and naive
across all five programs, using the run log and naive baseline results.

**Files created:**
- `reports/generate_benchmark.py`
- `reports/BENCHMARK.md` (generated artifact)
- `tests/test_benchmark.py`

**Tests that must pass:**
- Given a synthetic `run_log.json` and `naive_baseline.json`, `BENCHMARK.md` is
  generated with correct program statuses for all five programs.
- Report includes per-program findings count, fix iteration count, and final
  status for A, B, and naive.

**Dependencies:** Step 10

---

## COBOL Semantic Risks

Each risk is paired with the responsible component, the trap location, and the
boundary class that exposes it.

| # | Risk | Where divergence happens | Responsible component | Trap program | Boundary class |
|---|------|--------------------------|-----------------------|-------------|---------------|
| 1 | **Truncation without ROUNDED** — Python's `Decimal.quantize` defaults to `ROUND_HALF_EVEN`; COBOL COMPUTE truncates toward zero unless `ROUNDED` is coded | GROSSPAY COMPUTE | `verify/compare.py` (catches); translator must use `ROUND_DOWN` explicitly | GROSSPAY | `rounding_edge` |
| 2 | **COMPUTE ROUNDED** — COBOL ROUNDED means ROUND_HALF_UP, not banker's rounding | TAXCALC COMPUTE ROUNDED | `verify/compare.py` | TAXCALC | `rounding_edge` |
| 3 | **High-order overflow / field-width truncation** — COBOL silently drops high-order digits when a value overflows a field; modulo into field width | DEDUCT COMPUTE into narrow field | `verify/compare.py` | DEDUCT | `overflow` |
| 4 | **Implied decimal V** — The `V` in PIC does not write a decimal point; misreading V shifts every value by 10^n | encode_input / decode_output / run() | `verify/compare.py`; `test_run_legacy.py` | All | `smallest_unit`, `max_value` |
| 5 | **COMP-3 packed decimal** — Each digit occupies half a byte with a sign nibble; a DISPLAY encoder applied to a COMP-3 field silently corrupts every byte | GROSSPAY COMP-3 field | `test_run_legacy.py` COMP-3 round-trip | GROSSPAY | `max_value`, `overflow` |
| 6 | **Sign handling — unsigned field** — Moving a negative value into an **unsigned** field stores the **absolute value** (sign dropped, not clamped to zero) | VALIDATE unsigned field | `prosecutor/hunt.py` via `negative_max` class | VALIDATE | `negative_max` |
| 7 | **Sign handling — signed DISPLAY** — Signed fields must carry the sign nibble or leading sign correctly; Python arithmetic can go negative where COBOL cannot | PAYSLIP NET-PAY | `prosecutor/hunt.py` | PAYSLIP | `negative_max` |
| 8 | **MOVE truncation at assignment** — COBOL truncates when a wider working-storage field is MOVEd into a narrower output field | PAYSLIP final MOVE | `verify/compare.py` | PAYSLIP | `max_value`, `overflow` |
| 9 | **Fixed-width padding** — Output fields must be zero-padded (numeric) or space-padded (alphanumeric) to exact declared length; short/long fields shift all subsequent offsets | All translated run() | `test_translation_a/b.py` (byte-exact) | All | `zero`, `smallest_unit` |
| 10 | **Float contamination** — Any accidental use of `float` introduces IEEE-754 drift invisible to casual inspection | Anywhere | `test_strategies.py`, `test_translation_a/b.py` assert `isinstance(v, Decimal)` | All | `rounding_edge`, `max_minus_unit` |
| 11 | **Numeric string scale** — Reading `"04000"` as `4000` instead of `040.00` (scale=2) silently corrupts every output | decode_output, translator input parsing | `test_run_legacy.py` round-trip | All | `smallest_unit` |

---

## Bob Feature Mapping

| Step | Bob feature used | Reason |
|------|-----------------|--------|
| 1+2 — Skeleton + COBOL split | Agent mode | File creation and COBOL authoring; no parallelism benefit |
| 3+4 — Strategies + golden master | Agent mode | Sequential; strategies feeds golden master |
| 5 — compare + run_candidate | Agent mode | Pure logic; single session |
| 6 — Translator A | Agent mode, **separate session** | Reads COBOL + dictionary only; must not see translation/b/ |
| 7 — Translator B | Agent mode, **separate session, blind to A** | Reads COBOL + dictionary only; must not see translation/a/ |
| 8 — Naive baseline | Agent mode | Honest single-pass; merge with Step 9 session |
| 9 — Prosecutor | Agent mode, Hypothesis | Hypothesis handles shrinking; hunt is one focused module |
| 10 — Orchestrator | Agent mode, asyncio/concurrent.futures | Wave scheduling uses concurrency primitives |
| 11 — Benchmark | Agent mode | Simple report generator; merge with Step 10 session |

**Merges that save sessions:**
- Steps 1 + 2 → one session (skeleton + COBOL programs + dictionary)
- Steps 3 + 4 → one session (strategies + golden master)
- Steps 8 + 11 → one session (naive baseline + benchmark generator)

Estimated sessions after merging: **7**, well within the 38-coin budget.

---

## Demo-Critical Path

The minimum set of steps to show one program going through translation, a
prosecutor finding, and a fix, end-to-end:

```
Step 1  Repository skeleton
  └─▶ Step 2  COBOL split + data dictionary (5 programs, shared copybooks)
        └─▶ Step 3  Input strategies (boundary classes, all 5 programs)
              └─▶ Step 4  Golden master encode/decode + subprocess runner
                    └─▶ Step 5  compare.py + run_candidate.py
                          ├─▶ Step 6  Translator A (Session A, blind)
                          ├─▶ Step 7  Translator B (Session B, blind)
                          └─▶ Step 9  Prosecutor
                                └─▶ fix loop: failing translator receives
                                    minimal input + golden + their output
```

**Priority steps:** 1, 2, 3, 4, 5, 6, 7, 9

Steps 8 (naive), 10 (orchestrator), and 11 (benchmark) are required for project
completion but not needed to demonstrate the core loop.

The demo is complete when:
1. `run_legacy.py --generate` produces golden outputs for all five programs.
2. `hunt.py --program GROSSPAY` finds at least one disagreement (or proves agreement).
3. The failing translator receives the minimal input and fixes its `run()`.
4. Re-running `hunt.py` exhausts the budget with zero findings.
5. `compare.py` returns `agree_correct` for all golden inputs.

---

## Definition of Done (per PROJECT_CONTEXT.md)

- [ ] Every program is `PASSED` or `NEEDS_HUMAN_REVIEW` with a full run log.
- [ ] Naive baseline measured against the same inputs.
- [ ] `reports/BENCHMARK.md` generated.
- [ ] Repo contains no secrets (`.env` gitignored, no credentials in code).
- [ ] Every component has a CLI entry point and pytest tests.
- [ ] All five programs (VALIDATE, GROSSPAY, TAXCALC, DEDUCT, PAYSLIP) are covered.
