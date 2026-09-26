# Benchmark

Generated 2026-09-26T18:35:38+00:00

## Per program

| Program | Wave | Single-pass result (baseline) | Final status | Accepted | Fix attempts A / B | Rounds |
|---|---|---|---|---|---|---|
| GROSSPAY | 0 | b_wrong | PASSED | A | 0 / 2 | 4 |
| VALIDATE | 0 | clean | PASSED | A | 0 / 0 | 4 |
| DEDUCT | 1 | clean | PASSED | A | 0 / 0 | 4 |
| TAXCALC | 1 | clean | PASSED | A | 0 / 0 | 4 |
| PAYSLIP | 2 | a_wrong | PASSED | A | 2 / 0 | 4 |

## Summary

- Translator A (careful single pass) shipped silent behavior changes in: PAYSLIP
- Translator B (careful single pass) shipped silent behavior changes in: GROSSPAY
- Baseline hunts stop at the first finding per program, so these are lower bounds.

## Rounds

### Round 1 (2026-09-26T09:13:24+00:00, budget 200)
- GROSSPAY: b_wrong on GP-REGULAR-PAY, GP-OVERTIME-PAY, GP-GROSS-PAY -> fix requested from B
- VALIDATE: PASSED (accepted A, 208 inputs tested)
- DEDUCT: PASSED (accepted A, 210 inputs tested)
- TAXCALC: PASSED (accepted A, 210 inputs tested)
- PAYSLIP: a_wrong on PS-NET-PAY -> fix requested from A

### Round 2 (2026-09-26T13:56:14+00:00, budget 200)
- GROSSPAY: b_wrong on GP-OVERTIME-PAY, GP-GROSS-PAY -> fix requested from B
- VALIDATE: PASSED (accepted A, 208 inputs tested)
- DEDUCT: PASSED (accepted A, 210 inputs tested)
- TAXCALC: PASSED (accepted A, 210 inputs tested)
- PAYSLIP: a_wrong on PS-NET-PAY -> fix requested from A

### Round 3 (2026-09-26T18:31:51+00:00, budget 200)
- GROSSPAY: PASSED (accepted A, 208 inputs tested)
- VALIDATE: PASSED (accepted A, 208 inputs tested)
- DEDUCT: PASSED (accepted A, 210 inputs tested)
- TAXCALC: PASSED (accepted A, 210 inputs tested)
- PAYSLIP: PASSED (accepted A, 208 inputs tested)

### Round 4 (2026-09-26T18:34:34+00:00, budget 1000)
- GROSSPAY: PASSED (accepted A, 1008 inputs tested)
- VALIDATE: PASSED (accepted A, 1008 inputs tested)
- DEDUCT: PASSED (accepted A, 1010 inputs tested)
- TAXCALC: PASSED (accepted A, 1010 inputs tested)
- PAYSLIP: PASSED (accepted A, 1008 inputs tested)
