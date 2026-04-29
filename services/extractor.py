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


def _extract_dfs(path: str) -> list:
    import camelot
    import pdfplumber

    all_tables = []

    with pdfplumber.open(path) as pdf:
        n_pages = len(pdf.pages)

    for page_num in range(1, n_pages + 1):
        tables = camelot.read_pdf(path, pages=str(page_num), flavor="lattice")
        if not tables or tables[0].parsing_report.get("accuracy", 0) < 50:
            tables = camelot.read_pdf(path, pages=str(page_num), flavor="stream")
        all_tables.append((page_num, tables))

    return all_tables


def _extract(path: str) -> list[str]:
    import pdfplumber

    sections = []
    for page_num, tables in _extract_dfs(path):
        if tables:
            for table in tables:
                md = _df_to_markdown(table.df)
                if md:
                    sections.append(md)
        else:
            with pdfplumber.open(path) as pdf:
                text = pdf.pages[page_num - 1].extract_text() or ""
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


def _extract_tables(path: str) -> list[dict]:
    from services.table_parser import TableParser

    tables = []
    for page_num, page_tables in _extract_dfs(path):
        for table in (page_tables or []):
            parsed = TableParser.parse(table.df)
            if parsed:
                parsed["page"] = page_num
                tables.append(parsed)
    return _disambiguate_titles(tables)


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
