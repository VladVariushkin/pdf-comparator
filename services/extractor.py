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


def _extract_dfs(path: str):
    """Yield (page_num, DataFrame) for each table found in the PDF.

    Uses camelot lattice flavor first; falls back to stream when a page
    yields no tables or low accuracy. Each DataFrame is yielded immediately
    so camelot's internal image buffers are not accumulated across pages.
    """
    import camelot
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        n_pages = len(pdf.pages)

    for page_num in range(1, n_pages + 1):
        tables = camelot.read_pdf(path, pages=str(page_num), flavor="lattice")
        if not tables or tables[0].parsing_report.get("accuracy", 0) < 50:
            tables = camelot.read_pdf(path, pages=str(page_num), flavor="stream")
        for table in (tables or []):
            yield page_num, table.df
        # tables goes out of scope here; camelot objects (images, DataFrames) are GC'd


def _extract(path: str) -> list[str]:
    import camelot
    import pdfplumber

    sections = []
    with pdfplumber.open(path) as plumber:
        for page_num in range(1, len(plumber.pages) + 1):
            tables = camelot.read_pdf(path, pages=str(page_num), flavor="lattice")
            if not tables or tables[0].parsing_report.get("accuracy", 0) < 50:
                tables = camelot.read_pdf(path, pages=str(page_num), flavor="stream")
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
        merged["rows"] = base.get("rows", []) + continuation.get("rows", [])
    elif t == "matrix":
        merged["rows"] = {**base.get("rows", {}), **continuation.get("rows", {})}
    elif t == "key_value":
        merged["data"] = {**base.get("data", {}), **continuation.get("data", {})}
    return merged


def _merge_continuation_tables(tables: list[dict]) -> list[dict]:
    """Merge adjacent same-title tables; disambiguate with (p. N) when interrupted."""
    from collections import defaultdict

    title_positions: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(tables):
        if t.get("title"):
            title_positions[t["title"]].append(i)

    # Group consecutive occurrences; gap > 1 means another table interrupted
    merge_groups: dict[str, list[list[int]]] = {}
    for title, positions in title_positions.items():
        groups: list[list[int]] = [[positions[0]]]
        for k in range(1, len(positions)):
            if positions[k] - positions[k - 1] == 1:
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
