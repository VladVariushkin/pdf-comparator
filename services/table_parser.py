import re

import pandas as pd


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _clean(df: pd.DataFrame) -> list[list[str]]:
    rows = []
    for _, row in df.iterrows():
        cells = [str(c).strip() for c in row]
        rows.append(cells)
    return rows


def _strip_title_rows(rows: list[list[str]]) -> tuple[str | None, str | None, list[list[str]]]:
    title = None
    subtitle = None
    while rows:
        non_empty = [c for c in rows[0] if c.strip()]
        if len(non_empty) == 1:
            if title is None:
                title = non_empty[0]
            elif subtitle is None:
                subtitle = non_empty[0]
            rows = rows[1:]
        else:
            break
    return title, subtitle, rows


def _is_numeric(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if s.startswith('$'):
        return True
    if s.endswith('%'):
        # Only a percentage value (e.g. "100.00%"), not a label ending in "%" (e.g. "Imps %")
        numeric_part = re.sub(r'[,\s]', '', s[:-1])
        try:
            float(numeric_part)
            return True
        except ValueError:
            return False
    cleaned = re.sub(r'[,\s]', '', s)
    # Must not contain letters or slashes (avoids matching "12/29" or "P2+")
    if re.search(r'[a-zA-Z/]', cleaned):
        return False
    try:
        float(cleaned)
        return True
    except ValueError:
        return False


def _is_header_row(row: list[str]) -> bool:
    non_empty = [c for c in row if c.strip()]
    if not non_empty:
        return False
    fill_rate = len(non_empty) / len(row)
    return fill_rate > 0.5 and not any(_is_numeric(c) for c in non_empty)


def _looks_like_key_value(rows: list[list[str]]) -> bool:
    """Return True if a 2-col table is label→value pairs rather than a columnar dataset.

    Row 0 sometimes passes _is_header_row even when it is just the first data row
    (e.g. ["Advertiser", "Boehringer-Ingelheim"]). Scanning the full table catches
    two unambiguous key_value signals:
      - any blank right cell  (value fields can be empty; column headers cannot)
      - any right cell longer than 35 chars  (a value string, not a header label)
    """
    if not _is_header_row(rows[0]):
        return True
    for row in rows:
        right = row[1].strip() if len(row) > 1 else ""
        if not right:
            return True
        if len(right) > 35:
            return True
    return False


def _parse_key_value(rows: list[list[str]], title: str | None, subtitle: str | None = None) -> dict:
    data = {}
    for row in rows:
        key = row[0].strip() if len(row) > 0 else ''
        val = row[1].strip() if len(row) > 1 else ''
        if key:
            data[key] = val
    return {'type': 'key_value', 'title': title or '', 'subtitle': subtitle or '', 'data': data}


def _parse_columnar(header: list[str], rows: list[list[str]], title: str | None, subtitle: str | None = None) -> dict:
    headers = [h.strip() for h in header if h.strip()]
    result_rows = []
    for row in rows:
        if not any(c.strip() for c in row):
            continue
        obj = {header[i].strip(): row[i].strip()
               for i in range(len(header))
               if header[i].strip() and i < len(row)}
        if obj:
            result_rows.append(obj)
    return {'type': 'columnar', 'title': title or '', 'subtitle': subtitle or '', 'headers': headers, 'rows': result_rows}


def _parse_matrix(header: list[str], rows: list[list[str]], title: str | None, subtitle: str | None = None) -> dict:
    col_map = [(i + 1, c.strip()) for i, c in enumerate(header[1:]) if c.strip()]
    columns = [col for _, col in col_map]
    result_rows = {}
    for row in rows:
        if not row or not row[0].strip():
            continue
        row_label = row[0].strip()
        row_data = {col: row[pos].strip() for pos, col in col_map if pos < len(row)}
        result_rows[row_label] = row_data
    return {'type': 'matrix', 'title': title or '', 'subtitle': subtitle or '', 'columns': columns, 'rows': result_rows}


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class TableParser:
    @staticmethod
    def parse(df: pd.DataFrame) -> dict | None:
        """Convert a camelot DataFrame to a typed dict. Returns None if empty."""
        rows = _clean(df)
        if not rows:
            return None

        title, subtitle, rows = _strip_title_rows(rows)

        if not rows:
            return None

        n_cols = max(len(r) for r in rows)
        rows = [r + [''] * (n_cols - len(r)) for r in rows]  # pad to uniform width

        # Trim trailing columns that are entirely empty across all rows.
        # Merged cells in Excel inflate column count (e.g. a 2-col key-value sheet
        # appears as 14 columns because merged value cells span cols 2-13).
        while n_cols > 1 and all(not r[n_cols - 1].strip() for r in rows):
            n_cols -= 1
            rows = [r[:n_cols] for r in rows]

        if n_cols == 2 and _looks_like_key_value(rows):
            return _parse_key_value(rows, title, subtitle)

        # Scan forward (bounded) to find the first valid header row, skipping blank
        # and sparse preamble rows (e.g. quarter-label rows like "1Q26" in flowchart
        # reports that appear before the real column-header row).
        _LOOKAHEAD = 10
        header_row_idx = None
        for _i in range(min(_LOOKAHEAD, len(rows))):
            if _is_header_row(rows[_i]):
                header_row_idx = _i
                break

        if header_row_idx is not None:
            rows = rows[header_row_idx:]  # discard preamble rows
            header = [c.strip() for c in rows[0]]
            rows = rows[1:]
            if not header[0]:  # first cell empty → matrix
                return _parse_matrix(header, rows, title, subtitle)
            else:
                return _parse_columnar(header, rows, title, subtitle)
        else:
            header = [f'col_{i}' for i in range(n_cols)]
            return _parse_columnar(header, rows, title, subtitle)
