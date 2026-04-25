"""UAT helper: DART golden-set parity check (Phase 5 Success Criterion #3).

For each (name, corp_code) in the curated 10-filing golden set:
  1. Call src.collectors.dart.financials.get_structured_financials(corp_code, bgn_de)
     -> list[NumericFact] that the Routine would inject into _derived.numeric_facts
  2. Call dart_fss.fs.extract(corp_code, bgn_de) directly
     -> raw dict[sheet_key, DataFrame] from the dart-fss accessor
  3. For each NumericFact, locate the row in (2) whose label_ko is a
     LINE_ITEM_SYNONYMS member and compare the picked value byte-equal.

Pass criterion: every NumericFact emitted by financials.py has a byte-equal
counterpart in the raw dart-fss output for the same canonical key.

This is a one-off operator script. Run with: uv run python scripts/uat_dart_parity.py
Requires: DART_API_KEY in env. Network access to opendart.fss.or.kr.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Make src/ importable without installing package
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import dart_fss as dart  # noqa: E402

from collectors.dart.financials import (  # noqa: E402
    LINE_ITEM_SYNONYMS,
    _pick_value,
    get_structured_financials,
)

GOLDEN_SET: list[tuple[str, str]] = [
    ("삼성전자", "00126380"),
    ("SK하이닉스", "00164779"),
    ("NAVER", "00266961"),
    ("기아", "00106641"),
    ("현대자동차", "00164742"),
    ("LG에너지솔루션", "01515323"),
    ("KB금융", "00688996"),
    ("삼성SDI", "00126362"),
    ("삼성바이오로직스", "00877059"),
    ("POSCO홀딩스", "00155319"),
]

BGN_DE = "20240101"


def _raw_value_for_key(
    raw_fs: dict, canonical_key: str
) -> tuple[float | None, str | None, str | None]:
    """Walk raw dart-fss extract output the same way financials.py does and
    return (value, label_ko, sheet_key) for the first matching row. Returns
    (None, None, None) if not found."""
    synonyms = LINE_ITEM_SYNONYMS[canonical_key]
    for sheet_key in ("bs", "is", "cis", "cf"):
        df = raw_fs.get(sheet_key)
        if df is None or df.empty or "label_ko" not in df.columns:
            continue
        for _, row in df.iterrows():
            label = row["label_ko"]
            if label in synonyms:
                v = _pick_value(row)
                if v is not None:
                    return v, label, sheet_key
    return None, None, None


def main() -> int:
    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        print("ERROR: DART_API_KEY not set", file=sys.stderr)
        return 2
    dart.set_api_key(api_key=api_key)

    overall_total = 0
    overall_match = 0
    overall_mismatch = 0
    per_filing: list[dict] = []

    for name, corp_code in GOLDEN_SET:
        entry = {"name": name, "corp_code": corp_code, "status": None, "facts": []}
        try:
            our_facts = get_structured_financials(corp_code, BGN_DE)
        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = f"financials.py: {exc!r}"
            per_filing.append(entry)
            print(f"[ERROR] {name} ({corp_code}): {exc!r}", file=sys.stderr)
            continue

        try:
            from collectors.dart.financials import _fs_extract

            raw_fs = _fs_extract(corp_code, BGN_DE)
        except Exception as exc:
            entry["status"] = "error"
            entry["error"] = f"_fs_extract: {exc!r}"
            per_filing.append(entry)
            print(f"[ERROR] {name} ({corp_code}): raw extract failed: {exc!r}", file=sys.stderr)
            continue

        match = 0
        mismatch = 0
        for f in our_facts:
            raw_val, raw_label, sheet = _raw_value_for_key(raw_fs, f.key)
            ok = raw_val == f.value_krw
            entry["facts"].append(
                {
                    "key": f.key,
                    "our_value": f.value_krw,
                    "raw_value": raw_val,
                    "raw_label": raw_label,
                    "sheet": sheet,
                    "match": ok,
                }
            )
            if ok:
                match += 1
            else:
                mismatch += 1

        entry["status"] = (
            "ok" if mismatch == 0 and match > 0 else "mismatch" if mismatch else "empty"
        )
        entry["match_count"] = match
        entry["mismatch_count"] = mismatch
        per_filing.append(entry)
        overall_total += len(our_facts)
        overall_match += match
        overall_mismatch += mismatch

        print(
            f"[{entry['status'].upper():9s}] {name:18s} corp={corp_code} "
            f"facts={len(our_facts)} match={match} mismatch={mismatch}",
            file=sys.stderr,
        )

    summary = {
        "filings_total": len(GOLDEN_SET),
        "filings_ok": sum(1 for e in per_filing if e["status"] == "ok"),
        "filings_error": sum(1 for e in per_filing if e["status"] == "error"),
        "filings_mismatch": sum(1 for e in per_filing if e["status"] == "mismatch"),
        "filings_empty": sum(1 for e in per_filing if e["status"] == "empty"),
        "facts_total": overall_total,
        "facts_match": overall_match,
        "facts_mismatch": overall_mismatch,
    }
    print(json.dumps({"summary": summary, "per_filing": per_filing}, ensure_ascii=False, indent=2))

    # exit 0 only if all 10 filings ok and no mismatches
    return 0 if (summary["filings_ok"] == len(GOLDEN_SET) and summary["facts_mismatch"] == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
