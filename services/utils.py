"""Shared utilities for PDF comparison services."""

import re


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
