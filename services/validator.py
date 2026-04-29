"""
Deterministic consistency checks on LLM-extracted document data.
Flags when derived values disagree with stated values — independent of LLM judgement.
"""

import re
from typing import Optional

from models.comparison import ValidationWarning


def _parse_number(value) -> Optional[float]:
    """Extract the first numeric value from a string or pass through a number."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace(",", "").replace("$", "").replace("%", "").strip()
    m = re.search(r"\d+\.?\d*", s)
    return float(m.group()) if m else None


def _check_line_item_total(doc: str, checks: dict, warnings: list) -> None:
    """Sum individual line-item amounts and compare to any stated total."""
    items = checks.get("line_items", [])
    totals = checks.get("totals", [])
    if not items or not totals:
        return

    amounts = [_parse_number(item.get("amount")) for item in items]
    amounts = [a for a in amounts if a is not None]
    if not amounts:
        return

    computed = sum(amounts)
    for total in totals:
        stated = _parse_number(total.get("amount"))
        if stated is None or stated == 0:
            continue
        deviation = abs(computed - stated) / stated
        if deviation > 0.01:  # > 1% tolerance
            warnings.append(ValidationWarning(
                document=doc,
                rule="line_item_total",
                detail=(
                    f"Line-item sum ({computed:,.0f}) differs from stated "
                    f'"{total.get("label", "total")}" ({stated:,.0f}) '
                    f"by {deviation*100:.1f}% — possible extraction error, verify manually."
                ),
            ))


def _check_date_ordering(doc: str, checks: dict, warnings: list) -> None:
    """Assert every start-date comes before its paired end-date."""
    from dateutil import parser as dparser

    for pair in checks.get("date_pairs", []):
        try:
            start = dparser.parse(str(pair.get("start_value", "")), fuzzy=True)
            end = dparser.parse(str(pair.get("end_value", "")), fuzzy=True)
        except Exception:
            continue
        if start >= end:
            warnings.append(ValidationWarning(
                document=doc,
                rule="date_ordering",
                detail=(
                    f'"{pair.get("start_label", "start")}" ({pair.get("start_value")}) '
                    f'is not before "{pair.get("end_label", "end")}" ({pair.get("end_value")}) '
                    f"— possible OCR or extraction error."
                ),
            ))


def validate(doc_label: str, checks: dict) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    _check_line_item_total(doc_label, checks, warnings)
    _check_date_ordering(doc_label, checks, warnings)
    return warnings
