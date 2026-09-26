# Fix request: translation/b/GROSSPAY.py (attempt 1 of 3)

The prosecutor found an input where your output differs from the real COBOL program (classification: `b_wrong`).

## Minimal failing input
```json
{
  "GP-EMP-ID": "0",
  "GP-HOURS-WORKED": "0",
  "GP-HOURLY-RATE": "0"
}
```

## Fields that differ (raw bytes, hex)

| Field | Golden (real COBOL) | Yours |
|---|---|---|
| GP-REGULAR-PAY | `000000000f` (0) | `000000000c` (0) |
| GP-OVERTIME-PAY | `000000000f` (0) | `000000000c` (0) |
| GP-GROSS-PAY | `000000000f` (0) | `000000000c` (0) |

## Full output records (hex)
- Golden: `303030303030000000000f000000000f000000000f2020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020`
- Yours:  `303030303030000000000c000000000c000000000c2020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020202020`

## Rules
- Edit only files in translation/b/.
- Do not read translation/a/, golden_master/, tests/, prosecutor/, or reports/ (except this file).
- Fix the underlying cause (encoding or arithmetic semantics), not this one input. Never special-case values.
- Check the whole class of inputs this bug belongs to (every sign, every digit, every field using the same encoding), not just this example.
- If the cause is in shared code, fix it there; other programs may share the mistake.
- Keep run(record: dict) -> bytes unchanged.
- Do not compare against golden outputs. The prosecutor re-verifies after your fix.
