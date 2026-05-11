import os
import re
import tempfile
import threading

from services.utils import is_numeric_value

_camelot_sem = threading.Semaphore(int(os.getenv("CAMELOT_CONCURRENCY", "1")))


def extract_as_tables(pdf_bytes: bytes, filename: str = "") -> list[dict]:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    try:
        return _extract_tables(tmp_path)
    finally:
        os.unlink(tmp_path)


# Alias for the shared utility - used by _expand_single_column_df and _fix_collapsed_rows
_has_numeric = is_numeric_value


def _expand_single_column_df(df):
    """Expand a 1-column DataFrame whose rows contain \\n-separated values.

    camelot sometimes collapses an entire table (header + data rows) into a
    single column when the physical table is very narrow or sits at a page
    edge.  Each cell then holds the full row as a newline-joined string.

    Reconstruction strategy
    -----------------------
    1. Split every cell value by \\n.
    2. ``max_parts`` = largest part-count among DATA rows (rows that contain
       at least one numeric value).  Using data rows as the reference prevents
       a false expansion when the column-header row itself contained \\n (which
       would make the header appear to have far more parts than the data rows).
    3. If any non-data row has more parts than ``max_parts``, the column
       headers themselves contained \\n — this is not a truly collapsed table,
       so the DataFrame is returned unchanged.
    4. Rows whose part-count == ``max_parts - 1`` and whose parts contain no
       numeric values are treated as column-header rows and get an empty
       string prepended (restoring the blank first-column label cell).
    5. All other rows are right-padded to ``max_parts`` with empty strings.
    """
    import pandas as pd

    rows_with_newlines = sum(1 for i in range(len(df)) if '\n' in str(df.iloc[i, 0]))
    if rows_with_newlines < 2:
        return df  # not a fully-collapsed table

    split_rows = []
    for i in range(len(df)):
        val = str(df.iloc[i, 0]).strip()
        if '\n' in val:
            parts = [p.strip() for p in val.split('\n') if p.strip()]
        else:
            parts = [val] if val else ['']
        split_rows.append(parts)

    data_max = max(
        (len(r) for r in split_rows if any(_has_numeric(p) for p in r)),
        default=0,
    )
    if data_max < 2:
        return df  # no multi-column data found

    non_data_max = max(
        (len(r) for r in split_rows if not any(_has_numeric(p) for p in r)),
        default=0,
    )
    if non_data_max > data_max:
        return df  # header cells themselves contained '\n' — not a collapsed table

    max_parts = data_max

    processed = []
    for parts in split_rows:
        if len(parts) == max_parts:
            processed.append(parts)
        elif len(parts) == max_parts - 1 and not any(_has_numeric(p) for p in parts):
            processed.append([''] + parts)          # header row — prepend empty label cell
        else:
            processed.append(parts + [''] * (max_parts - len(parts)))

    return pd.DataFrame(processed)


def _fix_collapsed_rows(df):
    """Repair rows where camelot merged all cell data into col_0.

    Two cases are handled:

    * **Single-column table** — the entire table (header + data) was collapsed
      into one column with \\n separators.  Delegates to
      ``_expand_single_column_df`` to reconstruct the proper column layout.

    * **Multi-column table with some collapsed rows** — individual rows at
      page boundaries have all their values in col_0 separated by \\n while
      the rest of the table is fine.  Uses the most common non-empty column
      pattern as a template and redistributes the \\n-split parts.
    """
    from collections import Counter

    if len(df.columns) == 1:
        return _expand_single_column_df(df)

    df = df.copy()
    n_cols = len(df.columns)

    pattern_counter: Counter = Counter()
    for _, row in df.iterrows():
        cells = [str(c).strip() for c in row]
        non_empty_idx = tuple(i for i, c in enumerate(cells) if c)
        if len(non_empty_idx) >= 3:
            pattern_counter[non_empty_idx] += 1

    if not pattern_counter:
        return df

    template_indices = pattern_counter.most_common(1)[0][0]

    for idx, row in df.iterrows():
        cells = [str(c).strip() for c in row]
        non_empty = [c for c in cells if c]
        if len(non_empty) != 1:
            continue
        col0_val = cells[0]
        if '\n' not in col0_val:
            continue
        parts = [p.strip() for p in col0_val.split('\n') if p.strip()]
        if len(parts) < 2:
            continue

        # Data row: has numeric values after first part
        if any(_has_numeric(p) for p in parts[1:]):
            if len(parts) == len(template_indices):
                for col_pos, col_idx in enumerate(template_indices):
                    df.iat[idx, col_idx] = parts[col_pos]
            continue

        # Header row: no numeric values, parts count matches column count
        # Headers often have the column count or close to it
        if len(parts) == n_cols or len(parts) == len(template_indices):
            target_len = n_cols if len(parts) == n_cols else len(template_indices)
            target_indices = tuple(range(target_len)) if len(parts) == n_cols else template_indices
            for col_pos, col_idx in enumerate(target_indices):
                if col_pos < len(parts):
                    df.iat[idx, col_idx] = parts[col_pos]

    return df


def _extract_dfs(path: str):
    import camelot

    # line_scale=40 helps camelot detect thin vertical lines that separate columns.
    # Without it, camelot sometimes merges adjacent columns on certain pages.
    with _camelot_sem:
        table_list = camelot.read_pdf(path, pages="all", flavor="lattice", line_scale=40, resolution=150)
    try:
        for table in table_list:
            yield table.parsing_report.get("page", 0), _fix_collapsed_rows(table.df)
    finally:
        del table_list


def _extract(path: str) -> list[str]:
    import camelot
    import pdfplumber

    sections = []
    with pdfplumber.open(path) as plumber:
        n_pages = len(plumber.pages)

        with _camelot_sem:
            lattice_tables = camelot.read_pdf(path, pages="all", flavor="lattice", resolution=150)
        lattice_by_page: dict[int, list] = {}
        for t in lattice_tables:
            p = t.parsing_report.get("page", 0)
            lattice_by_page.setdefault(p, []).append(t)

        low_accuracy_pages = sorted(
            p for p, tables in lattice_by_page.items()
            if tables[0].parsing_report.get("accuracy", 0) < 50
        )
        stream_by_page: dict[int, list] = {}
        if low_accuracy_pages:
            with _camelot_sem:
                stream_tables = camelot.read_pdf(
                    path,
                    pages=",".join(str(p) for p in low_accuracy_pages),
                    flavor="stream",
                    resolution=150,
                )
            for t in stream_tables:
                p = t.parsing_report.get("page", 0)
                stream_by_page.setdefault(p, []).append(t)
            del stream_tables
        del lattice_tables

        for page_num in range(1, n_pages + 1):
            if page_num in stream_by_page:
                tables = stream_by_page[page_num]
            elif page_num in lattice_by_page:
                tables = lattice_by_page[page_num]
            else:
                tables = []

            if tables:
                for table in tables:
                    md = _df_to_markdown(table.df)
                    if md:
                        sections.append(md)
            else:
                text = plumber.pages[page_num - 1].extract_text() or ""
                if text.strip():
                    sections.append(text)
    return sections


def _disambiguate_titles(tables: list[dict]) -> list[dict]:
    """Append '(p. N)' to any title that appears on more than one page.

    Note: This is a standalone utility for simple disambiguation. The production
    pipeline uses _merge_continuation_tables instead, which merges consecutive-page
    tables and only disambiguates non-consecutive duplicates.
    """
    counts: dict[str, int] = {}
    for t in tables:
        if t.get("title"):
            counts[t["title"]] = counts.get(t["title"], 0) + 1
    for t in tables:
        if t.get("title") and counts[t["title"]] > 1:
            t["title"] = f"{t['title']} (p. {t.get('page', '?')})"
    return tables


def _merge_tables(base: dict, continuation: dict) -> dict:
    merged = dict(base)
    t = base.get("type")
    if t == "columnar":
        base_h = base.get("headers", [])
        cont_h = continuation.get("headers", [])
        merged["headers"] = cont_h if len(cont_h) > len(base_h) else base_h
        merged["rows"] = base.get("rows", []) + continuation.get("rows", [])
    elif t == "matrix":
        base_c = base.get("columns", [])
        cont_c = continuation.get("columns", [])
        merged["columns"] = cont_c if len(cont_c) > len(base_c) else base_c
        merged["rows"] = {**base.get("rows", {}), **continuation.get("rows", {})}
    elif t == "key_value":
        merged["data"] = {**base.get("data", {}), **continuation.get("data", {})}
    return merged


def _merge_continuation_tables(tables: list[dict]) -> list[dict]:
    """Merge same-title tables on consecutive pages; disambiguate when pages are non-consecutive.

    Uses page numbers (not list-index positions) to detect continuations so that
    interleaved tables from the same page don't break the merge.  For example, if
    page 3 yields [TableA, TableB] and page 4 yields [TableA, TableB], the two TableA
    fragments are on consecutive pages and are merged even though their indices in
    `tables` differ by 2.

    However, if another table appears BETWEEN two occurrences of the same title in
    extraction order and that interrupting table is on a page between the two
    occurrences, the merge is blocked - those are distinct tables that happen to
    share a name.
    """
    from collections import defaultdict

    title_positions: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(tables):
        if t.get("title"):
            title_positions[t["title"]].append(i)

    def _has_interrupting_table(prev_idx: int, curr_idx: int, prev_page: int, curr_page: int) -> bool:
        """Check if any titled table appears between two indices.

        Any titled table between two occurrences (in extraction order) is an
        interruption. If another table appears between them, the first table
        is complete and should not be merged with the later occurrence.
        """
        for idx in range(prev_idx + 1, curr_idx):
            t = tables[idx]
            if not t.get("title"):
                continue
            # Any titled table between the two is an interruption
            return True
        return False

    # Group runs where each successive occurrence is on the immediately next page
    # AND no other table interrupts between them.
    merge_groups: dict[str, list[list[int]]] = {}
    for title, positions in title_positions.items():
        groups: list[list[int]] = [[positions[0]]]
        for k in range(1, len(positions)):
            prev_idx = positions[k - 1]
            curr_idx = positions[k]
            prev_page = tables[prev_idx].get("page", 0)
            curr_page = tables[curr_idx].get("page", 0)
            # Merge only if pages are consecutive AND no interrupting table exists
            if curr_page == prev_page + 1 and not _has_interrupting_table(prev_idx, curr_idx, prev_page, curr_page):
                groups[-1].append(curr_idx)
            else:
                groups.append([curr_idx])
        merge_groups[title] = groups

    needs_disambiguation = {
        title for title, groups in merge_groups.items() if len(groups) > 1
    }

    index_map: dict[int, tuple[str, int, int]] = {}
    for title, groups in merge_groups.items():
        for group_num, group in enumerate(groups):
            for pos, idx in enumerate(group):
                index_map[idx] = (title, group_num, pos)

    result: list[dict] = []
    result_idx_for_group: dict[tuple[str, int], int] = {}

    for i, table in enumerate(tables):
        if not table.get("title") or i not in index_map:
            result.append(dict(table))
            continue

        orig_title, group_num, pos_in_group = index_map[i]

        if pos_in_group == 0:
            t = dict(table)
            if orig_title in needs_disambiguation:
                t["title"] = f"{orig_title} (p. {t.get('page', '?')})"
            result.append(t)
            result_idx_for_group[(orig_title, group_num)] = len(result) - 1
        else:
            prev_idx = result_idx_for_group[(orig_title, group_num)]
            result[prev_idx] = _merge_tables(result[prev_idx], table)

    return result


def _normalize_continuation_headers(tables: list[dict]) -> list[dict]:
    """Ensure all tables in a same-title consecutive group use identical column keys.

    When a multi-page table is extracted by camelot, some pages produce real
    column headers (e.g. 'Unit Rate') while others produce auto-generated
    col_N headers because the header row was collapsed.  After this function
    every table in such a group uses the canonical headers drawn from the
    real-header page with the most columns.

    Key-remapping strategy per table:
      - Auto-generated (col_N only): positional remap col_N → canonical[N].
      - Real headers matching canonical exactly: no change.
      - Real headers partially matching (e.g. first cell is a combined multi-
        column header): exact-string match first; then positional fallback.

    Also normalises header names to single-line (replaces \\n with space).
    """
    from collections import defaultdict

    def _is_auto(headers: list[str]) -> bool:
        return bool(headers) and all(re.match(r"^col_\d+$", h) for h in headers)

    def _clean_header(h: str) -> str:
        return re.sub(r"\s+", " ", h.replace("\n", " ")).strip()

    title_indices: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(tables):
        if t.get("title") and t.get("type") == "columnar":
            title_indices[t["title"]].append(i)

    result = list(tables)

    for title, indices in title_indices.items():
        if len(indices) < 2:
            continue

        # Find canonical: real headers with most columns.
        # But if auto-headers have MORE columns than any real headers,
        # camelot likely merged columns incorrectly on real-header pages.
        # In that case, skip normalization to avoid data loss.
        max_auto_cols = max(
            (len(result[idx].get("headers", [])) for idx in indices
             if _is_auto(result[idx].get("headers", []))),
            default=0
        )
        canonical_raw: list[str] = []
        for idx in indices:
            headers = result[idx].get("headers", [])
            if not _is_auto(headers) and len(headers) > len(canonical_raw):
                canonical_raw = headers
        if not canonical_raw:
            continue
        # Skip normalization if auto pages have more columns - structure is inconsistent
        if max_auto_cols > len(canonical_raw):
            continue

        canonical = [_clean_header(h) for h in canonical_raw]
        canonical_set = set(canonical)

        for idx in indices:
            t = result[idx]
            headers = t.get("headers", [])
            cleaned_headers = [_clean_header(h) for h in headers]

            if headers == canonical:
                continue  # already exactly canonical — row keys already match

            # Skip normalization if column counts differ significantly (>20% difference).
            # This indicates different table structures with the same title, not a
            # continuation with collapsed headers.
            if not _is_auto(headers):
                col_diff_ratio = abs(len(headers) - len(canonical)) / max(len(headers), len(canonical))
                if col_diff_ratio > 0.2:
                    continue  # Different table structure, keep original headers

            if _is_auto(headers):
                # col_N → canonical[N]
                key_map = {
                    f"col_{n}": canonical[n]
                    for n in range(len(canonical))
                }
            else:
                # Real headers, partially matching canonical.
                # Prefer exact string match; fall back to position.
                key_map: dict[str, str] = {}
                for pos, h in enumerate(cleaned_headers):
                    if h in canonical_set:
                        key_map[h] = h
                    elif pos < len(canonical):
                        key_map[h] = canonical[pos]
                    # else: leave unmapped (data kept as-is)

            new_rows = []
            for row in t.get("rows", []):
                new_row: dict[str, str] = {}
                for k, v in row.items():
                    clean_k = _clean_header(k)
                    new_row[key_map.get(clean_k, key_map.get(k, clean_k))] = v
                new_rows.append(new_row)

            updated = dict(t)
            updated["headers"] = canonical
            updated["rows"] = new_rows
            result[idx] = updated

    return result


def _extract_tables(path: str) -> list[dict]:
    from services.table_parser import TableParser

    tables = []
    for page_num, df in _extract_dfs(path):
        parsed = TableParser.parse(df)
        if parsed:
            parsed["page"] = page_num
            tables.append(parsed)
    tables = _normalize_continuation_headers(tables)
    return _merge_continuation_tables(tables)


def _df_to_markdown(df) -> str:
    rows = df.values.tolist()
    rows = [[str(c).strip() for c in row] for row in rows]
    rows = [row for row in rows if any(c for c in row)]
    if not rows:
        return ""

    header, *body = rows
    sep = ["---"] * len(header)
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)
