import os
import pytest
from services.comparator import compare_tables, _find_natural_key

_BEFORE_PDF = r"C:\Users\Vladyslav_Variushkin\Desktop\UWS_279295_Flowchart_Report_2026-03-20_Before.pdf"


def _kv(title, data):
    return {"type": "key_value", "title": title, "data": data}

def _col(title, headers, rows):
    return {"type": "columnar", "title": title, "headers": headers, "rows": rows}

def _mat(title, columns, rows):
    return {"type": "matrix", "title": title, "columns": columns, "rows": rows}


class TestCompareTablesKeyValue:
    def test_identical(self):
        a = [_kv("Plan", {"UWS #": "289805", "Property": "Bravo"})]
        b = [_kv("Plan", {"UWS #": "289805", "Property": "Bravo"})]
        result = compare_tables(a, b)
        assert all(d.status == "match" for d in result.diffs)
        assert result.summary == "No differences found."

    def test_value_mismatch(self):
        a = [_kv("Plan", {"UWS #": "289805", "Property": "Bravo"})]
        b = [_kv("Plan", {"UWS #": "289805", "Property": "USA Network"})]
        result = compare_tables(a, b)
        mismatches = [d for d in result.diffs if d.status == "mismatch"]
        assert len(mismatches) == 1
        assert mismatches[0].field == "Plan › Property"
        assert mismatches[0].value_a == "Bravo"
        assert mismatches[0].value_b == "USA Network"

    def test_field_only_in_a(self):
        a = [_kv("Plan", {"UWS #": "289805", "Extra": "only here"})]
        b = [_kv("Plan", {"UWS #": "289805"})]
        result = compare_tables(a, b)
        only_a = [d for d in result.diffs if d.status == "only_in_a"]
        assert len(only_a) == 1
        assert only_a[0].field == "Plan › Extra"

    def test_field_only_in_b(self):
        a = [_kv("Plan", {"UWS #": "289805"})]
        b = [_kv("Plan", {"UWS #": "289805", "Extra": "only here"})]
        result = compare_tables(a, b)
        only_b = [d for d in result.diffs if d.status == "only_in_b"]
        assert len(only_b) == 1
        assert only_b[0].field == "Plan › Extra"

    def test_numeric_semantic_match(self):
        # "$2,400,000 USD" vs "2400000" should match via _values_match
        a = [_kv("Plan", {"Contract Value": "$2,400,000 USD"})]
        b = [_kv("Plan", {"Contract Value": "2400000"})]
        result = compare_tables(a, b)
        assert all(d.status == "match" for d in result.diffs)


class TestCompareTablesColumnar:
    def test_identical_rows(self):
        headers = ["Name", "Rate", "Total"]
        a = [_col("1Q26", headers, [{"Name": "Bravo Early", "Rate": "$241", "Total": "$1,205"}])]
        b = [_col("1Q26", headers, [{"Name": "Bravo Early", "Rate": "$241", "Total": "$1,205"}])]
        result = compare_tables(a, b)
        assert all(d.status == "match" for d in result.diffs)

    def test_row_value_mismatch(self):
        headers = ["Name", "Rate"]
        a = [_col("1Q26", headers, [{"Name": "Bravo Early", "Rate": "$241"}])]
        b = [_col("1Q26", headers, [{"Name": "Bravo Early", "Rate": "$335"}])]
        result = compare_tables(a, b)
        mismatches = [d for d in result.diffs if d.status == "mismatch"]
        assert any("Rate" in d.field for d in mismatches)

    def test_extra_row_in_b(self):
        headers = ["Name", "Rate"]
        a = [_col("1Q26", headers, [{"Name": "Bravo Early", "Rate": "$241"}])]
        b = [_col("1Q26", headers, [
            {"Name": "Bravo Early", "Rate": "$241"},
            {"Name": "Bravo Daytime", "Rate": "$335"},
        ])]
        result = compare_tables(a, b)
        only_b = [d for d in result.diffs if d.status == "only_in_b"]
        assert len(only_b) > 0

    def test_auto_header_position_based_reports_row_count(self):
        # col_0/col_1 headers → position-based path; [row count] diff must fire.
        headers = ["col_0", "col_1"]
        a = [_col("1Q26", headers, [{"col_0": "Bravo Early",  "col_1": "$241"},
                                     {"col_0": "Bravo Daytime", "col_1": "$335"}])]
        b = [_col("1Q26", headers, [{"col_0": "Bravo Early",  "col_1": "$241"},
                                     {"col_0": "Bravo Early",  "col_1": "$241"},
                                     {"col_0": "Bravo Early",  "col_1": "$241"},
                                     {"col_0": "Bravo Daytime", "col_1": "$335"},
                                     {"col_0": "Bravo Daytime", "col_1": "$335"},
                                     {"col_0": "Bravo Daytime", "col_1": "$335"}])]
        result = compare_tables(a, b)
        count_diffs = [d for d in result.diffs if "[row count]" in d.field]
        assert len(count_diffs) == 1
        assert count_diffs[0].value_a == "2"
        assert count_diffs[0].value_b == "6"

    def test_duplicate_first_col_uses_compound_key(self):
        # B has duplicate "Name" values but distinct compound keys (Name+Days).
        # Compound-key path fires; no [row count] diff; A's rows are only_in_a,
        # B's split rows are only_in_b.
        headers = ["Name", "Days", "Rate"]
        a = [_col("1Q26", headers, [
            {"Name": "Bravo Early Morning", "Days": "MTWTFSS", "Rate": "$241"},
            {"Name": "Bravo Daytime",       "Days": "MTWTF",   "Rate": "$335"},
        ])]
        b = [_col("1Q26", headers, [
            {"Name": "Bravo Early Morning", "Days": "_S", "Rate": "$241"},
            {"Name": "Bravo Early Morning", "Days": "T",  "Rate": "$241"},
            {"Name": "Bravo Daytime",       "Days": "T",  "Rate": "$335"},
            {"Name": "Bravo Daytime",       "Days": "W",  "Rate": "$335"},
        ])]
        result = compare_tables(a, b)
        assert not any("[row count]" in d.field for d in result.diffs)
        only_a = [d for d in result.diffs if d.status == "only_in_a"]
        assert any("MTWTFSS" in d.field for d in only_a)
        only_b = [d for d in result.diffs if d.status == "only_in_b"]
        assert len(only_b) > 0


class TestCompareTablesMatrix:
    def test_identical(self):
        cols = ["12/29", "1/5", "Total"]
        rows = {":15": {"12/29": "$0", "1/5": "$0", "Total": "$2,545"}}
        a = [_mat("Dollars", cols, rows)]
        b = [_mat("Dollars", cols, rows)]
        result = compare_tables(a, b)
        assert all(d.status == "match" for d in result.diffs)

    def test_cell_mismatch(self):
        cols = ["12/29", "Total"]
        a = [_mat("Dollars", cols, {":15": {"12/29": "$0", "Total": "$2,545"}})]
        b = [_mat("Dollars", cols, {":15": {"12/29": "$500", "Total": "$3,045"}})]
        result = compare_tables(a, b)
        mismatches = [d for d in result.diffs if d.status == "mismatch"]
        assert len(mismatches) == 2


class TestCompareTablesMixed:
    def test_missing_table_in_b(self):
        a = [_kv("Plan", {"UWS #": "289805"}), _kv("Extra", {"Field": "Val"})]
        b = [_kv("Plan", {"UWS #": "289805"})]
        result = compare_tables(a, b)
        # missing tables now live in result.missing_tables, not result.diffs
        assert any(mt["title"] == "Extra" and mt["missing_from"] == "B" for mt in result.missing_tables)

    def test_missing_table_in_a(self):
        a = [_kv("Plan", {"UWS #": "289805"})]
        b = [_kv("Plan", {"UWS #": "289805"}), _kv("Extra", {"Field": "Val"})]
        result = compare_tables(a, b)
        assert any(mt["title"] == "Extra" and mt["missing_from"] == "A" for mt in result.missing_tables)

    def test_missing_table_appears_in_table_order(self):
        a = [_kv("Plan", {"UWS #": "289805"}), _kv("Extra", {"Field": "Val"})]
        b = [_kv("Plan", {"UWS #": "289805"})]
        result = compare_tables(a, b)
        assert "Extra" in result.table_order

    def test_type_mismatch(self):
        a = [_kv("Plan", {"Field": "Val"})]
        b = [_col("Plan", ["Field"], [{"Field": "Val"}])]
        result = compare_tables(a, b)
        type_diffs = [d for d in result.diffs if "[type]" in d.field]
        assert len(type_diffs) == 1

    def test_empty_both(self):
        result = compare_tables([], [])
        assert result.diffs == []
        assert result.summary == "No differences found."

    def test_table_order_preserves_pdf_order(self):
        # Tables should appear in the order given by tables_a, not alphabetically
        a = [_kv("Zebra", {"x": "1"}), _kv("Alpha", {"x": "1"})]
        b = [_kv("Zebra", {"x": "1"}), _kv("Alpha", {"x": "1"})]
        result = compare_tables(a, b)
        assert result.table_order == ["Zebra", "Alpha"]

    def test_subtitle_mismatch_is_a_diff(self):
        a = [{"type": "columnar", "title": "Summary", "subtitle": "Primary Demo P50+",
              "headers": ["Property"], "rows": [{"Property": "Bravo"}]}]
        b = [{"type": "columnar", "title": "Summary", "subtitle": "F18-49",
              "headers": ["Property"], "rows": [{"Property": "Bravo"}]}]
        result = compare_tables(a, b)
        mismatches = [d for d in result.diffs if d.status == "mismatch"]
        assert any("[subtitle]" in d.field for d in mismatches)

    def test_matching_subtitles_are_match(self):
        a = [{"type": "columnar", "title": "Summary", "subtitle": "Primary Demo P50+",
              "headers": ["Property"], "rows": [{"Property": "Bravo"}]}]
        b = [{"type": "columnar", "title": "Summary", "subtitle": "Primary Demo P50+",
              "headers": ["Property"], "rows": [{"Property": "Bravo"}]}]
        result = compare_tables(a, b)
        assert all(d.status == "match" for d in result.diffs)

    def test_subtitle_only_in_a(self):
        a = [{"type": "columnar", "title": "Summary", "subtitle": "P50+",
              "headers": ["Property"], "rows": []}]
        b = [{"type": "columnar", "title": "Summary", "subtitle": "",
              "headers": ["Property"], "rows": []}]
        result = compare_tables(a, b)
        only_a = [d for d in result.diffs if d.status == "only_in_a" and "[subtitle]" in d.field]
        assert len(only_a) == 1

    def test_diff_carries_table_and_page(self):
        a = [{"type": "key_value", "title": "Plan", "data": {"Field": "A"}, "page": 2}]
        b = [{"type": "key_value", "title": "Plan", "data": {"Field": "B"}, "page": 2}]
        result = compare_tables(a, b)
        assert len(result.diffs) == 1
        assert result.diffs[0].table == "Plan"
        assert result.diffs[0].page == 2


class TestDuplicateRowDetection:
    def test_duplicate_row_in_a_raises_warning(self):
        headers = ["Name", "Rate"]
        dup_rows = [
            {"Name": "Bravo Early Morning", "Rate": "$826"},
            {"Name": "Bravo Daytime",       "Rate": "$1,172"},
            {"Name": "Bravo Early Morning", "Rate": "$826"},  # duplicate
        ]
        a = [_col("1Q26", headers, dup_rows)]
        b = [_col("1Q26", headers, [{"Name": "Bravo Early Morning", "Rate": "$826"}])]
        result = compare_tables(a, b)
        w = [w for w in result.warnings if w.rule == "duplicate_rows"]
        assert len(w) == 1
        assert w[0].document == "A"
        assert "Bravo Early Morning" in w[0].detail

    def test_duplicate_row_in_b_raises_warning(self):
        headers = ["Name", "Rate"]
        normal  = [{"Name": "Bravo Early Morning", "Rate": "$826"}]
        dup_rows = normal + normal  # two identical rows
        a = [_col("1Q26", headers, normal)]
        b = [_col("1Q26", headers, dup_rows)]
        result = compare_tables(a, b)
        w = [w for w in result.warnings if w.rule == "duplicate_rows"]
        assert len(w) == 1
        assert w[0].document == "B"

    def test_no_duplicate_rows_no_warning(self):
        headers = ["Name", "Rate"]
        rows = [{"Name": "Bravo Early", "Rate": "$826"}, {"Name": "Bravo Daytime", "Rate": "$1,172"}]
        a = [_col("1Q26", headers, rows)]
        b = [_col("1Q26", headers, rows)]
        result = compare_tables(a, b)
        assert not any(w.rule == "duplicate_rows" for w in result.warnings)

    def test_auto_header_tables_skipped(self):
        # col_0/col_1 headers → position-based, not checked for duplicates
        headers = ["col_0", "col_1"]
        dup_rows = [{"col_0": "Bravo", "col_1": "$826"}, {"col_0": "Bravo", "col_1": "$826"}]
        a = [_col("1Q26", headers, dup_rows)]
        b = [_col("1Q26", headers, dup_rows)]
        result = compare_tables(a, b)
        assert not any(w.rule == "duplicate_rows" for w in result.warnings)

    def test_multiple_duplicate_rows_all_reported(self):
        headers = ["Name", "Rate"]
        dup_rows = [
            {"Name": "Bravo Early Morning", "Rate": "$826"},
            {"Name": "Bravo Early Morning", "Rate": "$826"},
            {"Name": "Bravo Daytime",       "Rate": "$1,172"},
            {"Name": "Bravo Daytime",       "Rate": "$1,172"},
        ]
        a = [_col("1Q26", headers, dup_rows)]
        b = [_col("1Q26", headers, dup_rows)]
        result = compare_tables(a, b)
        details = " ".join(w.detail for w in result.warnings if w.rule == "duplicate_rows")
        assert "Bravo Early Morning" in details
        assert "Bravo Daytime" in details


class TestDuplicateColumnDetection:
    def test_duplicate_column_in_columnar_table(self):
        headers = ["Name", "1/26", "1/26", "Total"]  # 1/26 repeated
        rows = [{"Name": "Bravo", "1/26": "4.0", "Total": "48.0"}]
        a = [_col("1Q26", headers, rows)]
        b = [_col("1Q26", [h for i, h in enumerate(headers) if i != 2], rows)]  # B has no duplicate
        result = compare_tables(a, b)
        w = [w for w in result.warnings if w.rule == "duplicate_columns"]
        assert len(w) == 1
        assert w[0].document == "A"
        assert "1/26" in w[0].detail

    def test_duplicate_column_in_matrix_table(self):
        cols = ["1/26", "1/26", "Total"]  # 1/26 repeated
        rows = {":30": {"1/26": "$100", "Total": "$200"}}
        a = [_mat("Dollars", cols, rows)]
        b = [_mat("Dollars", ["1/26", "Total"], rows)]  # B is clean
        result = compare_tables(a, b)
        w = [w for w in result.warnings if w.rule == "duplicate_columns"]
        assert len(w) == 1
        assert w[0].document == "A"
        assert "1/26" in w[0].detail

    def test_no_duplicate_columns_no_warning(self):
        headers = ["Name", "Rate", "Total"]
        rows = [{"Name": "Bravo", "Rate": "$826", "Total": "$4,130"}]
        a = [_col("1Q26", headers, rows)]
        b = [_col("1Q26", headers, rows)]
        result = compare_tables(a, b)
        assert not any(w.rule == "duplicate_columns" for w in result.warnings)

    def test_key_value_tables_not_checked(self):
        a = [_kv("Plan", {"Field": "Value"})]
        b = [_kv("Plan", {"Field": "Value"})]
        result = compare_tables(a, b)
        assert not any(w.rule == "duplicate_columns" for w in result.warnings)


class TestFieldOrdering:
    """Fields must appear in the original PDF order, not alphabetically."""

    def test_key_value_preserves_pdf_order(self):
        # Keys in reverse-alpha order — sorted() would put "Alpha" first.
        data = {"Zebra": "1", "Alpha": "2", "Mango": "3"}
        a = [_kv("Plan", data)]
        b = [_kv("Plan", data)]
        result = compare_tables(a, b)
        keys = [d.field.split(" › ", 1)[1] for d in result.diffs]
        assert keys == ["Zebra", "Alpha", "Mango"]

    def test_key_value_b_only_keys_appended_after_a_order(self):
        a = [_kv("Plan", {"Zebra": "1", "Alpha": "2"})]
        b = [_kv("Plan", {"Zebra": "1", "Alpha": "2", "Mango": "3"})]
        result = compare_tables(a, b)
        keys = [d.field.split(" › ", 1)[1] for d in result.diffs]
        assert keys == ["Zebra", "Alpha", "Mango"]

    def test_columnar_value_columns_follow_pdf_order(self):
        # "Rate" before "Days" in PDF — sorted() would put "Days" first.
        headers = ["Selling Name", "Rate", "Days", "Total"]
        rows = [{"Selling Name": "Bravo Early", "Rate": "$241", "Days": "MTWTFSS", "Total": "$1,205"}]
        a = [_col("1Q26", headers, rows)]
        b = [_col("1Q26", headers, rows)]
        result = compare_tables(a, b)
        col_names = [d.field.split(" › ")[-1] for d in result.diffs]
        assert col_names == ["Rate", "Days", "Total"]

    def test_columnar_rows_follow_pdf_order(self):
        # "Zebra Early" before "Alpha Morning" in PDF — sorted() would reverse this.
        headers = ["Name", "Rate"]
        rows = [
            {"Name": "Zebra Early", "Rate": "$241"},
            {"Name": "Alpha Morning", "Rate": "$335"},
        ]
        a = [_col("1Q26", headers, rows)]
        b = [_col("1Q26", headers, rows)]
        result = compare_tables(a, b)
        row_labels = [d.field.split(" › ")[1] for d in result.diffs]
        assert row_labels == ["Zebra Early", "Alpha Morning"]

    def test_matrix_row_labels_follow_pdf_order(self):
        # ":30" before ":15" in PDF — sorted() would put ":15" first.
        cols = ["Total"]
        rows = {":30": {"Total": "$100"}, ":15": {"Total": "$200"}, "Grand": {"Total": "$300"}}
        a = [_mat("Dollars", cols, rows)]
        b = [_mat("Dollars", cols, rows)]
        result = compare_tables(a, b)
        row_labels = [d.field.split(" › ")[1] for d in result.diffs]
        assert row_labels == [":30", ":15", "Grand"]

    def test_matrix_columns_follow_pdf_order(self):
        # "Total" before "1/5" before "12/29" in PDF — sorted() would put "1/5" first.
        cols = ["Total", "1/5", "12/29"]
        rows = {":15": {"Total": "$2,545", "1/5": "$0", "12/29": "$0"}}
        a = [_mat("Dollars", cols, rows)]
        b = [_mat("Dollars", cols, rows)]
        result = compare_tables(a, b)
        col_names = [d.field.split(" › ")[-1] for d in result.diffs]
        assert col_names == ["Total", "1/5", "12/29"]

    def test_columnar_text_columns_precede_date_columns_per_pdf(self):
        # Real-world case: PDF has text cols (Days/Times, CommType, …) to the left
        # of weekly date cols (12/29, 1/5, 1/12 …).  Alphabetically digits sort
        # before letters, so without the fix 1/12 would appear before CommType.
        headers = [
            "Selling Name", "Days/Times", "CommType",
            "12/29", "1/5", "1/12", "Total Dollars",
        ]
        rows = [{
            "Selling Name": "Bravo Daytime",
            "Days/Times": "MTWTF 8a-3p",
            "CommType": "NATL",
            "12/29": "",
            "1/5": "",
            "1/12": "",
            "Total Dollars": "$5,860",
        }]
        a = [_col("1Q26", headers, rows)]
        b = [_col("1Q26", headers, rows)]
        result = compare_tables(a, b)
        col_names = [d.field.split(" › ")[-1] for d in result.diffs]
        # PDF order: Days/Times, CommType, 12/29, 1/5, 1/12, Total Dollars
        # (Selling Name is the key col and does not appear as a value field)
        assert col_names == ["Days/Times", "CommType", "12/29", "1/5", "1/12", "Total Dollars"]


class TestFindNaturalKey:
    def test_single_column_when_already_unique(self):
        rows_a = [{"Name": "A", "Rate": "$1"}, {"Name": "B", "Rate": "$2"}]
        rows_b = [{"Name": "A", "Rate": "$1"}, {"Name": "C", "Rate": "$3"}]
        assert _find_natural_key(rows_a, rows_b, ["Name", "Rate"], ["Name", "Rate"]) == ["Name"]

    def test_extends_to_second_column_for_duplicates(self):
        rows_a = [{"Name": "X", "Days": "M"}, {"Name": "X", "Days": "T"}]
        rows_b = [{"Name": "X", "Days": "W"}, {"Name": "X", "Days": "F"}]
        assert _find_natural_key(rows_a, rows_b, ["Name", "Days"], ["Name", "Days"]) == ["Name", "Days"]

    def test_empty_tables_return_first_column(self):
        assert _find_natural_key([], [], ["Name", "Rate"], ["Name", "Rate"]) == ["Name"]

    def test_one_sided_duplicate_extends_key(self):
        # A is unique on first col, B is not — key must extend to cover B.
        rows_a = [{"Name": "A"}, {"Name": "B"}]
        rows_b = [{"Name": "A"}, {"Name": "A"}]  # duplicate in B
        assert _find_natural_key(rows_a, rows_b, ["Name"], ["Name"]) == ["Name"]
        # With a second discriminating column available, it should extend.
        rows_b2 = [{"Name": "A", "Days": "M"}, {"Name": "A", "Days": "T"}]
        rows_a2 = [{"Name": "A", "Days": "M"}, {"Name": "B", "Days": "W"}]
        assert _find_natural_key(rows_a2, rows_b2, ["Name", "Days"], ["Name", "Days"]) == ["Name", "Days"]


# ---------------------------------------------------------------------------
# Real-PDF regression: 1Q26 table field ordering (page 2)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def before_pdf_tables():
    """Extract tables from the real Before flowchart PDF; skip if absent."""
    if not os.path.exists(_BEFORE_PDF):
        pytest.skip(f"fixture PDF not found: {_BEFORE_PDF}")
    from services.extractor import _extract_tables
    return _extract_tables(_BEFORE_PDF)


class TestRealPdf1Q26FieldOrdering:
    """Columns must come out in left-to-right PDF order, not alphabetically.

    The 1Q26 table on page 2 has text columns (Days/Times, CommType, …)
    to the LEFT of the weekly date columns (12/29, 1/5, 1/12, …).
    Before the fix, sorted() caused date columns to appear first because
    digits sort before letters in ASCII.
    """

    def _1q26_cols(self, before_pdf_tables):
        result = compare_tables(before_pdf_tables, before_pdf_tables)
        seen = []
        for d in result.diffs:
            if d.table == "1Q26" and d.page == 2:
                parts = d.field.split("›")
                if len(parts) >= 3:
                    col = parts[-1].strip()
                    if col not in seen:
                        seen.append(col)
        return seen

    def test_text_columns_precede_date_columns(self, before_pdf_tables):
        cols = self._1q26_cols(before_pdf_tables)
        assert cols, "No columns found for 1Q26 p.2"
        # Text columns that must appear BEFORE any date column
        text_before_dates = ["Days/Times", "Comm\nType", "Line\nClass"]
        first_date_idx = next(
            (i for i, c in enumerate(cols) if "/" in c and c[0].isdigit()),
            None,
        )
        assert first_date_idx is not None, "No date column found"
        for col in text_before_dates:
            idx = next((i for i, c in enumerate(cols) if c == col), None)
            assert idx is not None, f"Column {col!r} not found"
            assert idx < first_date_idx, (
                f"{col!r} at position {idx} should come before first date col at {first_date_idx}"
            )

    def test_date_columns_in_chronological_order(self, before_pdf_tables):
        cols = self._1q26_cols(before_pdf_tables)
        date_cols = [c for c in cols if "/" in c and c[0].isdigit() and c != "Total\nDollars"]
        # Chronological order as they appear in the PDF: 12/29, 1/5, 1/12, …
        expected_order = ["12/29", "1/5", "1/12", "1/19", "1/26",
                          "2/2", "2/9", "2/16", "2/23",
                          "3/2", "3/9", "3/16", "3/23"]
        assert date_cols == expected_order, (
            f"Date cols not in PDF order.\nGot:      {date_cols}\nExpected: {expected_order}"
        )
