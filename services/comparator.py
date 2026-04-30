import re

from models.comparison import ComparisonResult, FieldDiff, ValidationWarning
from services.llm_client import LLMClient
from services.validator import validate

_SINGLE_EXTRACT_SYSTEM = (
    "You are a document parser. Extract named pieces of information from tables and form fields only.\n"
    "Rules:\n"
    "- Use the field label EXACTLY as it appears — do not rename, rephrase, abbreviate, or combine labels.\n"
    "- Two-column label/value table: label column → field name, value column → field value.\n"
    "- Multi-column table: first-column cell → field name, remaining cells joined with ' | ' → field value.\n"
    "- Skip prose paragraphs, narrative sentences, and running text entirely — even if they contain numbers or dates.\n"
    "- Only include data explicitly present. Do not infer or fabricate.\n"
    "\n"
    "Example 1 — two-column label/value table:\n"
    "Input:\n"
    "  Field              | Value\n"
    "  Contract ID        | SLA-2025-0042\n"
    "  Effective Date     | January 15, 2025\n"
    "  Contract Value     | $2,400,000 USD\n"
    "Reasoning: Two-column table. First column is the label, second is the value. Copy labels verbatim.\n"
    'Output: {"Contract ID": "SLA-2025-0042", "Effective Date": "January 15, 2025", "Contract Value": "$2,400,000 USD"}\n'
    "\n"
    "Example 2 — multi-column table with a primary row label:\n"
    "Input:\n"
    "  Severity | Breach Duration | Credit (% of Monthly Fee)\n"
    "  Minor    | < 1 hour        | 5%\n"
    "  Major    | 4 - 8 hours     | 30%\n"
    "  Critical | > 8 hours       | 50%\n"
    "Reasoning: First column is the row label. Remaining cells are concatenated as the value.\n"
    "  Do NOT invent names like 'Credit - Minor Breach Duration' — use the row label as-is.\n"
    'Output: {"Minor": "< 1 hour | 5%", "Major": "4 - 8 hours | 30%", "Critical": "> 8 hours | 50%"}\n'
    "\n"
    "Example 3 — multi-column metrics table:\n"
    "Input:\n"
    "  Metric              | Target    | Measurement Window | Penalty Threshold\n"
    "  Platform Uptime     | 99.95%    | Monthly            | < 99.9%\n"
    "  Stream Start Time   | <= 2.0 sec| Weekly avg.        | > 3.0 sec\n"
    "Reasoning: 'Metric' column contains the row labels. Use metric name verbatim as field name.\n"
    'Output: {"Platform Uptime": "99.95% | Monthly | < 99.9%", "Stream Start Time": "<= 2.0 sec | Weekly avg. | > 3.0 sec"}\n'
)

_checks_schema = {
    "type": "object",
    "properties": {
        "line_items": {
            "type": "array",
            "description": "Individual line items from a pricing table or payment schedule — each row with a label and a numeric amount. Empty array if no such table exists in the document.",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["label", "amount"],
            },
        },
        "totals": {
            "type": "array",
            "description": "Explicitly stated grand totals or contract values that should equal the sum of line items. Empty array if not present.",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["label", "amount"],
            },
        },
        "date_pairs": {
            "type": "array",
            "description": "Pairs of semantically related start and end dates — such as contract effective/expiration dates or project start/end dates. Only include pairs where both dates are explicitly present. Empty array if no such pairs exist.",
            "items": {
                "type": "object",
                "properties": {
                    "start_label": {"type": "string"},
                    "start_value": {"type": "string"},
                    "end_label": {"type": "string"},
                    "end_value": {"type": "string"},
                },
                "required": ["start_label", "start_value", "end_label", "end_value"],
            },
        },
    },
    "required": ["line_items", "totals", "date_pairs"],
}

_EXTRACTION_TOOL = {
    "name": "extract_document",
    "description": (
        "Extract named pieces of information from the document's tables and form fields — "
        "rows with an explicit label and a discrete value — into a flat fields dictionary. "
        "Do NOT extract from prose paragraphs, narrative sentences, or running text. "
        "Also populate the three consistency-check arrays (line_items, totals, date_pairs) "
        "only when that type of structured data is explicitly present; otherwise leave them empty."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fields": {
                "type": "object",
                "description": "Every named piece of information from the document as field_name → string_value pairs.",
                "additionalProperties": {"type": "string"},
            },
            "checks": {**_checks_schema, "description": "Structured data used to verify internal consistency of the document's numbers and dates."},
        },
        "required": ["fields", "checks"],
    },
}

_FREEFORM_SYSTEM = (
    "You are a document analyst. Compare the two documents below and identify all meaningful discrepancies. "
    'Return JSON with this exact shape: {"diffs": [{"topic": "<short label>", "text_in_a": "<what doc A says>", "text_in_b": "<what doc B says>"}], "summary": "<plain-English overview>"}. '
    "If there are no differences, return an empty diffs array and say so in the summary."
)

_SUMMARY_SYSTEM = (
    "You are a document analyst. Given the following field-level differences between two documents, "
    "write a concise 2-3 sentence plain-English summary of the discrepancies. "
    'Return JSON with this exact shape: {"summary": "<your summary here>"}.'
)


def _normalise_key(k: str) -> str:
    """Lowercase, strip surrounding whitespace and trailing punctuation."""
    return re.sub(r'[\s:]+$', '', k.strip()).lower()


def _cell_key(v: str) -> str:
    """Order-invariant fingerprint for row-key matching.

    Extracts all alphanumeric tokens, sorts them, and joins them.  This makes
    matching robust to PDF text-wrap differences where the same cell content
    is extracted with different internal line breaks across document versions
    (e.g. 'Bravo (M-Su\\nNATL\\n6a-8a)' ≡ 'Bravo (M-Su 6a-\\nNATL\\n8a)').
    """
    return " ".join(sorted(re.findall(r'[a-z0-9]+', v.lower())))


def _normalise_fields(raw: dict) -> dict:
    """Return a new dict with normalised keys; last value wins on collision."""
    return {_normalise_key(k): (v.strip() if isinstance(v, str) else str(v))
            for k, v in raw.items()}


def _to_number(s: str):
    """Return float if s encodes a number, else None."""
    cleaned = re.sub(r'[^\d.]', '', s.replace(',', ''))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _to_date(s: str):
    """Return a date object if s parses as a date, else None."""
    try:
        from dateutil import parser as dparser
        return dparser.parse(s, fuzzy=True).date()
    except Exception:
        return None


def _values_match(a: str, b: str) -> bool:
    """True when a and b are semantically equal despite surface formatting differences."""
    # 1. Exact case-insensitive
    if a.lower() == b.lower():
        return True

    # 2. Collapse whitespace ("Net 30 days" vs "Net  30 days")
    if re.sub(r'\s+', ' ', a).strip().lower() == re.sub(r'\s+', ' ', b).strip().lower():
        return True

    # 3. Numeric — handles "$2,400,000 USD" vs "$2,400,000" vs "2400000"
    na, nb = _to_number(a), _to_number(b)
    if na is not None and nb is not None:
        if na == 0 and nb == 0:
            return True
        if na != 0 and abs(na - nb) / abs(na) < 0.001:   # 0.1 % tolerance for rounding
            return True
        return False  # both parsed as numbers but differ — skip date check

    # 4. Date — handles "January 15, 2025" vs "Jan 15, 2025" vs "2025-01-15"
    da, db = _to_date(a), _to_date(b)
    if da is not None and db is not None and da == db:
        return True

    return False


def _extract_and_merge(sections: list[str], llm: LLMClient) -> dict:
    """Extract fields and checks from each section individually, then merge."""
    merged_fields: dict = {}
    merged_checks: dict = {"line_items": [], "totals": [], "date_pairs": []}

    for section in sections:
        try:
            result = llm.complete_with_tool(_SINGLE_EXTRACT_SYSTEM, section, _EXTRACTION_TOOL)
        except Exception:
            continue
        merged_fields.update(result.get("fields", {}))
        section_checks = result.get("checks", {})
        merged_checks["line_items"].extend(section_checks.get("line_items", []))
        merged_checks["totals"].extend(section_checks.get("totals", []))
        merged_checks["date_pairs"].extend(section_checks.get("date_pairs", []))

    return {"fields": merged_fields, "checks": merged_checks}


def compare_structured(sections_a: list[str], sections_b: list[str], llm: LLMClient) -> ComparisonResult:
    extracted_a = _extract_and_merge(sections_a, llm)
    extracted_b = _extract_and_merge(sections_b, llm)

    fields_a = _normalise_fields(extracted_a.get("fields", {}))
    fields_b = _normalise_fields(extracted_b.get("fields", {}))

    all_keys = sorted(set(fields_a) | set(fields_b))
    diffs = []
    for key in all_keys:
        val_a = fields_a.get(key)
        val_b = fields_b.get(key)
        if val_a is None:
            status = "only_in_b"
        elif val_b is None:
            status = "only_in_a"
        elif _values_match(val_a, val_b):
            status = "match"
        else:
            status = "mismatch"
        display_key = key.title()
        diffs.append(FieldDiff(field=display_key, value_a=val_a, value_b=val_b, status=status))

    diff_text = "\n".join(
        f"- {d.field}: A='{d.value_a}' B='{d.value_b}' [{d.status}]"
        for d in diffs if d.status != "match"
    ) or "No differences found."
    summary = llm.complete_json(_SUMMARY_SYSTEM, diff_text).get("summary", "")

    warnings = (
        validate("A", extracted_a.get("checks", {})) +
        validate("B", extracted_b.get("checks", {}))
    )

    return ComparisonResult(
        mode="structured",
        diffs=diffs,
        summary=summary,
        warnings=warnings,
        debug={
            "text_a": sections_a,
            "text_b": sections_b,
            "extracted_a": extracted_a,
            "extracted_b": extracted_b,
        },
    )


def compare_freeform(sections_a: list[str], sections_b: list[str], llm: LLMClient) -> ComparisonResult:
    text_a = "\n\n".join(sections_a)
    text_b = "\n\n".join(sections_b)
    user_msg = f"Document A:\n{text_a}\n\n---\n\nDocument B:\n{text_b}"
    resp = llm.complete_json(_FREEFORM_SYSTEM, user_msg)

    diffs = [
        FieldDiff(
            field=d.get("topic", ""),
            value_a=d.get("text_in_a", ""),
            value_b=d.get("text_in_b", ""),
            status="mismatch",
        )
        for d in resp.get("diffs", [])
    ]
    return ComparisonResult(mode="freeform", diffs=diffs, summary=resp.get("summary", ""))


def _diff_key_value(data_a: dict, data_b: dict, prefix: str, *, table: str = "", page: int = 0) -> list[FieldDiff]:
    diffs = []
    for key in dict.fromkeys(list(data_a) + list(data_b)):
        val_a = data_a.get(key)
        val_b = data_b.get(key)
        if val_a is None:
            status = "only_in_b"
        elif val_b is None:
            status = "only_in_a"
        elif _values_match(val_a, val_b):
            status = "match"
        else:
            status = "mismatch"
        diffs.append(FieldDiff(field=f"{prefix} › {key}", value_a=val_a, value_b=val_b, status=status, table=table, page=page))
    return diffs


def _find_natural_key(
    rows_a: list[dict],
    rows_b: list[dict],
    headers_a: list[str],
    headers_b: list[str],
) -> list[str]:
    """Return the shortest ordered prefix of columns whose values are unique
    within rows_a AND within rows_b.  If no prefix achieves uniqueness (truly
    duplicate rows), returns all columns — caller proceeds with last-wins dict."""
    ordered_cols = list(dict.fromkeys(headers_a + headers_b))
    key_cols: list[str] = []
    for col in ordered_cols:
        key_cols.append(col)
        keys_a = [tuple(_cell_key(row.get(c, "")) for c in key_cols) for row in rows_a]
        keys_b = [tuple(_cell_key(row.get(c, "")) for c in key_cols) for row in rows_b]
        if len(keys_a) == len(set(keys_a)) and len(keys_b) == len(set(keys_b)):
            return key_cols
    return key_cols


def _diff_columnar(ta: dict, tb: dict, prefix: str, *, table: str = "", page: int = 0) -> list[FieldDiff]:
    diffs = []
    rows_a = ta.get("rows", [])
    rows_b = tb.get("rows", [])
    headers_a = ta.get("headers", [])
    headers_b = tb.get("headers", [])
    all_cols = list(dict.fromkeys(headers_a + headers_b))

    id_key = (headers_a or headers_b or [None])[0]

    # Auto-generated headers (col_0, col_1, …) → position-based only.
    if not id_key or re.match(r'^col_\d+$', id_key):
        if len(rows_a) != len(rows_b):
            diffs.append(FieldDiff(
                field=f"{prefix} › [row count]",
                value_a=str(len(rows_a)), value_b=str(len(rows_b)),
                status="mismatch", table=table, page=page,
            ))
        for i in range(max(len(rows_a), len(rows_b))):
            row_a = rows_a[i] if i < len(rows_a) else {}
            row_b = rows_b[i] if i < len(rows_b) else {}
            for col in all_cols:
                val_a, val_b = row_a.get(col), row_b.get(col)
                if val_a is None and val_b is None:
                    continue
                status = ("only_in_b" if val_a is None else
                          "only_in_a" if val_b is None else
                          "match" if _values_match(val_a, val_b) else "mismatch")
                diffs.append(FieldDiff(field=f"{prefix} › Row {i + 1} › {col}",
                                       value_a=val_a, value_b=val_b,
                                       status=status, table=table, page=page))
        return diffs

    # Real headers → compound-key matching.
    # Extend the key column-by-column until values are unique in both tables.
    key_cols = _find_natural_key(rows_a, rows_b, headers_a, headers_b)
    value_cols = [c for c in all_cols if c not in key_cols]

    def _key(row: dict) -> tuple:
        # Fingerprint-based key: order-invariant alphanumeric tokens per cell.
        # Handles PDF text-wrap differences where the same cell is extracted
        # with different internal line breaks across document versions.
        return tuple(_cell_key(row.get(c, "")) for c in key_cols)

    def _display_label(row: dict) -> str:
        return " · ".join(re.sub(r'\s+', ' ', row.get(c, "")).strip() for c in key_cols)

    idx_a = {_key(r): r for r in rows_a}
    idx_b = {_key(r): r for r in rows_b}

    all_keys = list(dict.fromkeys([_key(r) for r in rows_a] + [_key(r) for r in rows_b]))
    for k in all_keys:
        row_a = idx_a.get(k)
        row_b = idx_b.get(k)
        label = _display_label(row_a or row_b)
        for col in value_cols:
            val_a = row_a.get(col) if row_a is not None else None
            val_b = row_b.get(col) if row_b is not None else None
            if val_a is None and val_b is None:
                continue
            status = ("only_in_b" if val_a is None else
                      "only_in_a" if val_b is None else
                      "match" if _values_match(val_a, val_b) else "mismatch")
            diffs.append(FieldDiff(field=f"{prefix} › {label} › {col}",
                                   value_a=val_a, value_b=val_b,
                                   status=status, table=table, page=page))
    return diffs


def _diff_matrix(ta: dict, tb: dict, prefix: str, *, table: str = "", page: int = 0) -> list[FieldDiff]:
    diffs = []
    all_row_labels = list(dict.fromkeys(list(ta.get("rows", {})) + list(tb.get("rows", {}))))
    all_cols = list(dict.fromkeys(ta.get("columns", []) + tb.get("columns", [])))

    for row_label in all_row_labels:
        row_a = ta.get("rows", {}).get(row_label, {})
        row_b = tb.get("rows", {}).get(row_label, {})
        for col in all_cols:
            val_a = row_a.get(col)
            val_b = row_b.get(col)
            if val_a is None and val_b is None:
                continue
            if val_a is None:
                status = "only_in_b"
            elif val_b is None:
                status = "only_in_a"
            elif _values_match(val_a, val_b):
                status = "match"
            else:
                status = "mismatch"
            diffs.append(FieldDiff(field=f"{prefix} › {row_label} › {col}", value_a=val_a, value_b=val_b, status=status, table=table, page=page))
    return diffs


def _check_duplicate_rows(tables: list[dict], doc_label: str) -> list:
    warnings = []
    for t in tables:
        if t.get("type") != "columnar":
            continue
        headers = t.get("headers", [])
        id_key = headers[0] if headers else None
        if not id_key or re.match(r'^col_\d+$', id_key):
            continue
        counts: dict[str, int] = {}
        for row in t.get("rows", []):
            val = row.get(id_key, "").strip()
            if val:
                counts[val] = counts.get(val, 0) + 1
        dupes = [val for val, cnt in counts.items() if cnt > 1]
        if dupes:
            table_name = t.get("title") or "(untitled)"
            warnings.append(ValidationWarning(
                document=doc_label,
                rule="duplicate_rows",
                detail=f'Table "{table_name}" — duplicate row(s): {", ".join(repr(d) for d in dupes)}.',
            ))
    return warnings


def _check_duplicate_cols(tables: list[dict], doc_label: str) -> list:
    warnings = []
    for t in tables:
        t_type = t.get("type")
        if t_type == "columnar":
            headers = t.get("headers", [])
        elif t_type == "matrix":
            headers = t.get("columns", [])
        else:
            continue
        counts: dict[str, int] = {}
        for h in headers:
            h = h.strip()
            if h:
                counts[h] = counts.get(h, 0) + 1
        dupes = [h for h, cnt in counts.items() if cnt > 1]
        if dupes:
            table_name = t.get("title") or "(untitled)"
            warnings.append(ValidationWarning(
                document=doc_label,
                rule="duplicate_columns",
                detail=f'Table "{table_name}" — duplicate column(s): {", ".join(repr(d) for d in dupes)}.',
            ))
    return warnings


def compare_tables(tables_a: list[dict], tables_b: list[dict]) -> ComparisonResult:
    diffs = []

    titled_a = {t["title"]: t for t in tables_a if t.get("title")}
    titled_b = {t["title"]: t for t in tables_b if t.get("title")}
    untitled_a = [t for t in tables_a if not t.get("title")]
    untitled_b = [t for t in tables_b if not t.get("title")]

    # Build pairs in PDF order: titles from A first, then any titles only in B.
    pairs: list[tuple[str, dict | None, dict | None]] = []
    seen: set[str] = set()
    for t in tables_a:
        if t.get("title") and t["title"] not in seen:
            seen.add(t["title"])
            pairs.append((t["title"], titled_a.get(t["title"]), titled_b.get(t["title"])))
    for t in tables_b:
        if t.get("title") and t["title"] not in seen:
            seen.add(t["title"])
            pairs.append((t["title"], titled_a.get(t["title"]), titled_b.get(t["title"])))
    for i in range(max(len(untitled_a), len(untitled_b))):
        ta_u = untitled_a[i] if i < len(untitled_a) else None
        tb_u = untitled_b[i] if i < len(untitled_b) else None
        pairs.append((f"Table {i + 1}", ta_u, tb_u))

    missing_tables = []
    table_order = []
    table_subtitles = {}

    for prefix, ta, tb in pairs:
        table_order.append(prefix)
        # Capture subtitle from whichever side exists — always, even for missing tables
        sub = (ta or {}).get("subtitle") or (tb or {}).get("subtitle") or ""
        if sub:
            table_subtitles[prefix] = sub
        if ta is None:
            missing_tables.append({"title": prefix, "missing_from": "A", "page": tb.get("page", 0)})
            continue
        if tb is None:
            missing_tables.append({"title": prefix, "missing_from": "B", "page": ta.get("page", 0)})
            continue
        if ta.get("type") != tb.get("type"):
            page = ta.get("page") or tb.get("page") or 0
            diffs.append(FieldDiff(field=f"{prefix} [type]", value_a=ta.get("type"), value_b=tb.get("type"), status="mismatch", table=prefix, page=page))
            continue

        page = ta.get("page") or tb.get("page") or 0
        sub_a = ta.get("subtitle") or ""
        sub_b = tb.get("subtitle") or ""
        if sub_a or sub_b:
            if _values_match(sub_a, sub_b):
                status = "match"
            elif not sub_a:
                status = "only_in_b"
            elif not sub_b:
                status = "only_in_a"
            else:
                status = "mismatch"
            diffs.append(FieldDiff(field=f"{prefix} › [subtitle]", value_a=sub_a or None, value_b=sub_b or None, status=status, table=prefix, page=page))

        t = ta["type"]
        if t == "key_value":
            diffs.extend(_diff_key_value(ta["data"], tb["data"], prefix, table=prefix, page=page))
        elif t == "columnar":
            diffs.extend(_diff_columnar(ta, tb, prefix, table=prefix, page=page))
        elif t == "matrix":
            diffs.extend(_diff_matrix(ta, tb, prefix, table=prefix, page=page))

    n_mismatch = sum(1 for d in diffs if d.status == "mismatch")
    n_only_a = sum(1 for d in diffs if d.status == "only_in_a")
    n_only_b = sum(1 for d in diffs if d.status == "only_in_b")

    if (not diffs or all(d.status == "match" for d in diffs)) and not missing_tables:
        summary = "No differences found."
    else:
        parts = []
        if missing_tables:
            parts.append(f"{len(missing_tables)} missing table(s)")
        if n_mismatch:
            parts.append(f"{n_mismatch} mismatched value(s)")
        if n_only_a:
            parts.append(f"{n_only_a} field(s) only in A")
        if n_only_b:
            parts.append(f"{n_only_b} field(s) only in B")
        summary = "Found " + ", ".join(parts) + "."

    warnings = (
        _check_duplicate_rows(tables_a, "A") + _check_duplicate_rows(tables_b, "B") +
        _check_duplicate_cols(tables_a, "A") + _check_duplicate_cols(tables_b, "B")
    )

    return ComparisonResult(
        mode="table_parser",
        diffs=diffs,
        missing_tables=missing_tables,
        table_order=table_order,
        table_subtitles=table_subtitles,
        summary=summary,
        warnings=warnings,
        debug={"tables_a": tables_a, "tables_b": tables_b},
    )
