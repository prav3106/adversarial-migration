# Fix request: translation/a/PAYSLIP.py (attempt 2 of 3)

The prosecutor found an input where your output differs from the real COBOL program (classification: `a_wrong`).

## Minimal failing input
```json
{
  "PS-EMP-ID": "1",
  "PS-GROSS-PAY": "0.01",
  "PS-TAX-AMOUNT": "0.01",
  "PS-DEDUCTIONS": "0.01"
}
```

## Fields that differ (raw bytes, hex)

| Field | Golden (real COBOL) | Yours |
|---|---|---|
| PS-NET-PAY | `303030303030303071` (-0.01) | `30303030303030304a` (0) |

## Full output records (hex)
- Golden: `3030303030313030303030303030313030303030303030313030303030303130303030303030307130303030303030303120202020202020202020202020202020202020202020202020202020202020`
- Yours:  `3030303030313030303030303030313030303030303030313030303030303130303030303030304a30303030303030303120202020202020202020202020202020202020202020202020202020202020`

## Rules
- Edit only files in translation/a/.
- Do not read translation/b/, golden_master/, tests/, prosecutor/, or reports/ (except this file).
- Fix the underlying cause (encoding or arithmetic semantics), not this one input. Never special-case values.
- Check the whole class of inputs this bug belongs to (every sign, every digit, every field using the same encoding), not just this example.
- If the cause is in shared code, fix it there; other programs may share the mistake.
- Keep run(record: dict) -> bytes unchanged.
- Do not compare against golden outputs. The prosecutor re-verifies after your fix.
