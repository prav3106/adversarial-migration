# Fix request: translation/b/GROSSPAY.py (attempt 2 of 3)

The prosecutor found an input where your output differs from the real COBOL program (classification: `b_wrong`).

## Minimal failing input
```json
{
  "GP-EMP-ID": "999999",
  "GP-HOURS-WORKED": "999.99",
  "GP-HOURLY-RATE": "9999.99"
}
```

## Fields that differ (raw bytes, hex)

| Field | Golden (real COBOL) | Yours |
|---|---|---|
| GP-OVERTIME-PAY | `479993080f` (4799930.8) | `439983080f` (4399830.8) |
| GP-GROSS-PAY | `519993040f` (5199930.4) | `479983040f` (4799830.4) |

## Full output records (hex)
- Golden: `393939393939039999960f479993080f519993040f2020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020`
- Yours:  `393939393939039999960f439983080f479983040f2020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020`

## Rules
- Edit only files in translation/b/.
- Do not read translation/a/, golden_master/, tests/, prosecutor/, or reports/ (except this file).
- Fix the underlying cause (encoding or arithmetic semantics), not this one input. Never special-case values.
- Check the whole class of inputs this bug belongs to (every sign, every digit, every field using the same encoding), not just this example.
- If the cause is in shared code, fix it there; other programs may share the mistake.
- Keep run(record: dict) -> bytes unchanged.
- Do not compare against golden outputs. The prosecutor re-verifies after your fix.
