import os
import re


def _doc_identity(name: str) -> str:
    """Return the canonical document identity key for a filename.

    Strips (in order): directory, extension, Windows copy-number suffix ' (N)',
    Before/After role label, date segment YYYY-MM-DD, trailing underscores/spaces.

    Examples:
        "UWS_279295_Flowchart_Report_2026-03-20_Before.pdf"  → "UWS_279295_Flowchart_Report"
        "UWS_279295_Flowchart_Report__2026-03-23_After (1).pdf" → "UWS_279295_Flowchart_Report"
    """
    stem = os.path.splitext(os.path.basename(name))[0]
    stem = re.sub(r'\s*\(\d+\)\s*$', '', stem)
    stem = re.sub(r'[_ ]*(Before|After)\s*$', '', stem, flags=re.IGNORECASE)
    stem = re.sub(r'[_ ]+\d{4}-\d{2}-\d{2}', '', stem)
    return stem.strip('_ ')


def _doc_role(name: str) -> str | None:
    """Return 'before', 'after', or None based on the filename label."""
    stem = os.path.splitext(os.path.basename(name))[0]
    stem = re.sub(r'\s*\(\d+\)\s*$', '', stem)
    m = re.search(r'[_ ](Before|After)\s*$', stem, flags=re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return None


def pair_by_name(names: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Group filenames into Before/After pairs by document identity.

    Returns:
        pairs:     list of (before_name, after_name) tuples
        unmatched: names that could not be paired (no counterpart, wrong/missing
                   role label, or extra files beyond the first matched pair)
    """
    groups: dict[str, dict[str, list[str]]] = {}
    for name in names:
        identity = _doc_identity(name)
        role = _doc_role(name)
        groups.setdefault(identity, {"before": [], "after": [], "none": []})
        if role == "before":
            groups[identity]["before"].append(name)
        elif role == "after":
            groups[identity]["after"].append(name)
        else:
            groups[identity]["none"].append(name)

    pairs: list[tuple[str, str]] = []
    unmatched: list[str] = []

    for identity, buckets in groups.items():
        befores = buckets["before"]
        afters = buckets["after"]
        nones = buckets["none"]

        unmatched.extend(nones)

        if befores and afters:
            pairs.append((befores[0], afters[0]))
            unmatched.extend(befores[1:])
            unmatched.extend(afters[1:])
        else:
            unmatched.extend(befores)
            unmatched.extend(afters)

    return pairs, unmatched
