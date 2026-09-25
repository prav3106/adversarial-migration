"""Hand-verified oracle checks: values computed by hand, confirmed against the real COBOL binary."""
from decimal import Decimal
from golden_master.run_legacy import load_dict, input_fields, output_fields, encode_input, run_cobol, decode_output


def _run_taxcalc(gross, rate):
    fields = load_dict("TAXCALC")
    rec = {f["field_name"]: Decimal("0") for f in input_fields(fields)}
    rec.update({"TC-GROSS-PAY": Decimal(gross), "TC-TAX-RATE": Decimal(rate)})
    raw = run_cobol("TAXCALC", encode_input(rec, input_fields(fields)))
    return decode_output(raw, output_fields(fields))


def test_rounded_exact_tie_is_half_up_not_bankers():
    # 100.10 * 0.0500 = 5.005 exactly. HALF_UP -> 5.01, banker's rounding would give 5.00.
    assert _run_taxcalc("100.10", "0.0500")["TC-TAX-AMOUNT"] == Decimal("5.01")


def test_same_product_rounded_vs_truncated():
    # 190.00 * 0.0275 = 5.225. ROUNDED field -> 5.23, truncated field -> 5.22.
    out = _run_taxcalc("190.00", "0.0275")
    assert out["TC-TAX-AMOUNT"] == Decimal("5.23")
    assert out["TC-BRACKET-TAX"] == Decimal("5.22")
    
def test_signed_input_uses_ascii_overpunch_and_sign_is_dropped():
    # Harness encodes -999.99 with ASCII overpunch ('y' = negative 9);
    # VALIDATE's MOVE into an unsigned field drops the sign -> 999.99.
    fields = load_dict("VALIDATE")
    rec = {f["field_name"]: Decimal("0") for f in input_fields(fields)}
    rec["VL-HOURS-WORKED"] = Decimal("-999.99")
    enc = encode_input(rec, input_fields(fields))
    assert b"9999y" in enc
    raw = run_cobol("VALIDATE", enc)
    assert decode_output(raw, output_fields(fields))["VL-HOURS-CLEAN"] == Decimal("999.99")