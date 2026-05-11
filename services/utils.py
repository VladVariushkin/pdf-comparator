"""Shared utilities for comparison services."""

import os
import re


def strip_filename_metadata(name: str) -> str:
    """Strip directory, extension, copy suffix, Before/After role, and date from a filename stem.

    Examples:
        "UWS_279295_Flowchart_Report_2026-03-20_Before.pdf"  → "UWS_279295_Flowchart_Report"
        "UWS_279295_Flowchart_Report__2026-03-23_After (1).pdf" → "UWS_279295_Flowchart_Report"
    """
    stem = os.path.splitext(os.path.basename(name))[0]
    stem = re.sub(r'\s*\(\d+\)\s*$', '', stem)
    stem = re.sub(r'[_ ]*(Before|After)\s*$', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'[_ ]+\d{4}-\d{2}-\d{2}', '', stem)
    return stem.strip('_ ')


def is_numeric_value(s: str) -> bool:
    """True if s represents a numeric quantity (currency, percentage, or plain number).

    Used by both extractor (to detect collapsed rows) and comparator (to classify
    columns as key vs. value columns).
    """
    s = s.strip()
    if not s:
        return False
    if s.startswith('$'):
        return True
    if s.endswith('%'):
        part = re.sub(r'[,\s]', '', s[:-1])
        try:
            float(part)
            return True
        except ValueError:
            return False
    cleaned = re.sub(r'[,\s]', '', s)
    # Reject strings with letters or slashes (date-like values such as "1/5")
    if re.search(r'[a-zA-Z/]', cleaned):
        return False
    try:
        float(cleaned)
        return True
    except ValueError:
        return False
