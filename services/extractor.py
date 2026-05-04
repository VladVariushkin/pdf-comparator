import tempfile
import os


def extract_as_text(pdf_bytes: bytes) -> list[str]:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    try:
        return _extract(tmp_path)
    finally:
        os.unlink(tmp_path)


def extract_as_tables(pdf_bytes: bytes) -> list[dict]:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    try:
        return _extract_tables(tmp_path)
    finally:
        os.unlink(tmp_path)


def _fix_collapsed_rows(df):
    """Repair rows where camelot merged all cell data into col_0.

    At page boundaries camelot sometimes collapses an entire row's values into
    the first cell, separated by newlines.  This detects those rows
    (non_empty==1, col_0 contains newlines AND at least one numeric/dollar
    value) and redistributes the split parts back into the correct column
    positions, using the most common non-empty column pattern from adjacent
    well-parsed rows as a template.
    """
    import re
    from collections import Counter

    df = df.copy()

    def _has_numeric(s: str) -> bool:
        s = s.strip()
        if s.startswith('$'):
            return True
        cleaned = re.sub(r'[,\s%]', '', s)
        if not cleaned:
            return False
        try:
            float(cleaned)
            return True
        except ValueError:
            return False

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
        if not any(_has_numeric(p) for p in parts[1:]):
            continue
        if len(parts) != len(template_indices):
            continue
        for col_pos, col_idx in enumerate(template_indices):
            df.iat[idx, col_idx] = parts[col_pos]

    return df


def _extract_dfs(path: str):
    import camelot

    table_list = camelot.read_pdf(path, pages="all", flavor="lattice")
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

        lattice_tables = camelot.read_pdf(path, pages="all", flavor="lattice")
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
            stream_tables = camelot.read_pdf(
                path,
                pages=",".join(str(p) for p in low_accuracy_pages),
                flavor="stream",
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
    """Append '(p. N)' to any title that appears on more than one page."""
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
    """
    from collections import defaultdict

    title_positions: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(tables):
        if t.get("title"):
            title_positions[t["title"]].append(i)

    # Group runs where each successive occurrence is on the immediately next page.
    merge_groups: dict[str, list[list[int]]] = {}
    for title, positions in title_positions.items():
        groups: list[list[int]] = [[positions[0]]]
        for k in range(1, len(positions)):
            prev_page = tables[positions[k - 1]].get("page", 0)
            curr_page = tables[positions[k]].get("page", 0)
            if curr_page == prev_page + 1:   # strictly consecutive pages → continuation
                groups[-1].append(positions[k])
            else:
                groups.append([positions[k]])
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


def _extract_tables(path: str) -> list[dict]:
    from services.table_parser import TableParser

    tables = []
    for page_num, df in _extract_dfs(path):
        parsed = TableParser.parse(df)
        if parsed:
            parsed["page"] = page_num
            tables.append(parsed)
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
