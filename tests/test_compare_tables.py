import os
import re
from pathlib import Path
import pytest
from services.comparator import compare_tables, _find_natural_key
from services.report_builder import _display_title

_BEFORE_PDF = str(Path(__file__).parent / "fixtures" / "pdfs" / "UWS_279295_Flowchart_Report_2026-03-20_Before.pdf")


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
        # Note: All columns including key column are now shown as value fields.
        headers = ["Selling Name", "Rate", "Days", "Total"]
        rows = [{"Selling Name": "Bravo Early", "Rate": "$241", "Days": "MTWTFSS", "Total": "$1,205"}]
        a = [_col("1Q26", headers, rows)]
        b = [_col("1Q26", headers, rows)]
        result = compare_tables(a, b)
        col_names = [d.field.split(" › ")[-1] for d in result.diffs]
        assert col_names == ["Selling Name", "Rate", "Days", "Total"]

    def test_columnar_rows_follow_pdf_order(self):
        # "Zebra Early" before "Alpha Morning" in PDF — sorted() would reverse this.
        # Note: Now includes key column (Name) as a value field, so each row has 2 diffs.
        headers = ["Name", "Rate"]
        rows = [
            {"Name": "Zebra Early", "Rate": "$241"},
            {"Name": "Alpha Morning", "Rate": "$335"},
        ]
        a = [_col("1Q26", headers, rows)]
        b = [_col("1Q26", headers, rows)]
        result = compare_tables(a, b)
        row_labels = [d.field.split(" › ")[1] for d in result.diffs]
        # Each row has 2 fields (Name, Rate), so labels repeat
        assert row_labels == ["Zebra Early", "Zebra Early", "Alpha Morning", "Alpha Morning"]

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
        # Note: All columns including key column are now shown as value fields.
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
        # PDF order: Selling Name, Days/Times, CommType, 12/29, 1/5, 1/12, Total Dollars
        # (Selling Name is now included as a value field along with all other columns)
        assert col_names == ["Selling Name", "Days/Times", "CommType", "12/29", "1/5", "1/12", "Total Dollars"]


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

    def test_numeric_column_skipped_as_key(self):
        # AvgUnitRate values are dollar amounts → must not appear in the key
        # even when the first column ("Network") has duplicates.
        rows_a = [{"Network": "Bravo", "AvgUnitRate": "$780"},
                  {"Network": "Bravo", "AvgUnitRate": "$751"}]
        rows_b = [{"Network": "Bravo", "AvgUnitRate": "$780"},
                  {"Network": "Bravo", "AvgUnitRate": "$751"}]
        result = _find_natural_key(rows_a, rows_b,
                                   ["Network", "AvgUnitRate"],
                                   ["Network", "AvgUnitRate"])
        assert result == ["Network"]

    def test_non_numeric_column_still_discriminates(self):
        # "Days" contains text values like "M", "T" → must still extend key
        rows_a = [{"Name": "X", "Days": "M", "Rate": "$1"},
                  {"Name": "X", "Days": "T", "Rate": "$2"}]
        rows_b = [{"Name": "X", "Days": "W", "Rate": "$3"},
                  {"Name": "X", "Days": "F", "Rate": "$4"}]
        assert _find_natural_key(rows_a, rows_b,
                                 ["Name", "Days", "Rate"],
                                 ["Name", "Days", "Rate"]) == ["Name", "Days"]


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


class TestGroupPositionalMatching:
    """When the non-numeric key (e.g. network name) is non-unique, rows are
    matched positionally within each group — numeric values must not appear
    in the field path."""

    def _headers(self):
        return ["Network", "AvgUnitRate", "GrossDollars"]

    def test_numeric_value_not_in_field_path(self):
        h = self._headers()
        rows = [
            {"Network": "Bravo", "AvgUnitRate": "$780", "GrossDollars": "$100,000"},
            {"Network": "Bravo", "AvgUnitRate": "$751", "GrossDollars": "$80,000"},
        ]
        a = [_col("Summary", h, rows)]
        b = [_col("Summary", h, rows)]
        result = compare_tables(a, b)
        assert not any("$780" in d.field or "$751" in d.field for d in result.diffs)

    def test_matching_rows_are_match(self):
        h = self._headers()
        rows = [
            {"Network": "Bravo", "AvgUnitRate": "$780", "GrossDollars": "$100,000"},
            {"Network": "Bravo", "AvgUnitRate": "$751", "GrossDollars": "$80,000"},
        ]
        a = [_col("Summary", h, rows)]
        b = [_col("Summary", h, rows)]
        result = compare_tables(a, b)
        assert all(d.status == "match" for d in result.diffs)

    def test_rate_change_shows_as_mismatch_not_missing(self):
        h = self._headers()
        a = [_col("Summary", h, [
            {"Network": "Bravo", "AvgUnitRate": "$780", "GrossDollars": "$100,000"},
            {"Network": "Bravo", "AvgUnitRate": "$751", "GrossDollars": "$80,000"},
        ])]
        b = [_col("Summary", h, [
            {"Network": "Bravo", "AvgUnitRate": "$790", "GrossDollars": "$100,000"},
            {"Network": "Bravo", "AvgUnitRate": "$751", "GrossDollars": "$80,000"},
        ])]
        result = compare_tables(a, b)
        mismatches = [d for d in result.diffs if d.status == "mismatch"]
        only_in_a = [d for d in result.diffs if d.status == "only_in_a"]
        only_in_b = [d for d in result.diffs if d.status == "only_in_b"]
        # Changed AvgUnitRate in row 1 must be a mismatch, not a disappearing row
        assert any("AvgUnitRate" in d.field for d in mismatches)
        assert not only_in_a
        assert not only_in_b

    def test_positional_label_uses_numeric_suffix_for_groups(self):
        h = self._headers()
        rows = [
            {"Network": "Bravo", "AvgUnitRate": "$780", "GrossDollars": "$100,000"},
            {"Network": "Bravo", "AvgUnitRate": "$751", "GrossDollars": "$80,000"},
        ]
        a = [_col("Summary", h, rows)]
        b = [_col("Summary", h, rows)]
        result = compare_tables(a, b)
        labels = {d.field.split(" › ")[1] for d in result.diffs}
        assert "Bravo (1)" in labels
        assert "Bravo (2)" in labels

    def test_single_row_group_has_no_suffix(self):
        h = self._headers()
        a = [_col("Summary", h, [
            {"Network": "Bravo", "AvgUnitRate": "$780", "GrossDollars": "$100,000"},
            {"Network": "CNN",   "AvgUnitRate": "$567", "GrossDollars": "$50,000"},
        ])]
        b = [_col("Summary", h, [
            {"Network": "Bravo", "AvgUnitRate": "$780", "GrossDollars": "$100,000"},
            {"Network": "CNN",   "AvgUnitRate": "$567", "GrossDollars": "$50,000"},
        ])]
        result = compare_tables(a, b)
        labels = {d.field.split(" › ")[1] for d in result.diffs}
        # CNN appears once — no positional suffix
        assert "CNN" in labels
        assert not any(l.startswith("CNN (") for l in labels)


class TestDisplayTitle:
    def test_strips_page_suffix(self):
        assert _display_title("Property Summary Total (p. 3)") == "Property Summary Total"

    def test_strips_with_space_variants(self):
        assert _display_title("Property Summary Total (p.3)") == "Property Summary Total"
        assert _display_title("Selling Names (p. 12)") == "Selling Names"

    def test_strips_question_mark_page(self):
        assert _display_title("Plan (p. ?)") == "Plan"

    def test_title_without_suffix_unchanged(self):
        assert _display_title("Property Summary Total") == "Property Summary Total"
        assert _display_title("1Q26") == "1Q26"
        assert _display_title("") == ""

    def test_does_not_strip_mid_title_parens(self):
        # Only trailing "(p. N)" should be removed, not parens elsewhere in the title.
        assert _display_title("P2+ (000) by Week (p. 3)") == "P2+ (000) by Week"
        assert _display_title("P2+ (000) by Week") == "P2+ (000) by Week"


class TestCollapsedRowKeys:
    """When camelot collapses an entire data row into the first column (all
    values joined with \\n), the row label in the field key must only use the
    text before the first embedded numeric — not the full joined string.

    Real-world trigger: 'Selling Names by Quarter' tables in multi-page PDFs
    where page-boundary rows are not repaired by _fix_collapsed_rows because
    their part-count differs from the dominant column pattern.
    """

    _HEADERS = ["Selling Name", "Unit Rate", "Avg Unit Rate", "Gross Dollars"]

    def _collapsed_row(self):
        # Simulates a row where camelot put all values in Selling Name with \n
        return {
            "Selling Name": "2Q26 - Bravo\n$634\n$1,268\n$104,550",
            "Unit Rate": "",
            "Avg Unit Rate": "",
            "Gross Dollars": "",
        }

    def test_no_dollar_amount_in_field_key(self):
        """Dollar amounts must never appear in the row-label segment of a field path."""
        a = [_col("SNQ", self._HEADERS, [self._collapsed_row()])]
        b = [_col("SNQ", self._HEADERS, [self._collapsed_row()])]
        result = compare_tables(a, b)

        for d in result.diffs:
            parts = d.field.split(" › ")
            row_label = parts[1] if len(parts) >= 2 else ""
            assert not re.search(r'\$\d', row_label), (
                f"Dollar amount leaked into row label: {d.field!r}"
            )

    def test_no_percentage_in_field_key(self):
        """Percentage values (100.00%) must never appear in the row-label segment."""
        collapsed = {
            "Selling Name": "2Q26 - Bravo\n$634\n100.00%\n$104,550",
            "Unit Rate": "",
            "Avg Unit Rate": "",
            "Gross Dollars": "",
        }
        a = [_col("SNQ", self._HEADERS, [collapsed])]
        b = [_col("SNQ", self._HEADERS, [collapsed])]
        result = compare_tables(a, b)

        for d in result.diffs:
            parts = d.field.split(" › ")
            row_label = parts[1] if len(parts) >= 2 else ""
            assert not re.search(r'\d+\.\d+%', row_label), (
                f"Percentage leaked into row label: {d.field!r}"
            )

    def test_label_uses_only_first_line_of_collapsed_cell(self):
        """The row label should be just the first line of the Selling Name cell."""
        a = [_col("SNQ", self._HEADERS, [self._collapsed_row()])]
        b = [_col("SNQ", self._HEADERS, [self._collapsed_row()])]
        result = compare_tables(a, b)

        row_labels = {
            d.field.split(" › ")[1]
            for d in result.diffs
            if len(d.field.split(" › ")) >= 2
        }
        assert row_labels == {"2Q26 - Bravo"}, (
            f"Expected label '2Q26 - Bravo', got: {row_labels}"
        )

    def test_legitimate_multiline_name_preserved(self):
        """A Selling Name with non-numeric \\n-parts must NOT be truncated at the first line."""
        # e.g. "Bravo Early\nNo\nBDN-\nFringe (M-" is the actual name of the selling unit,
        # not a collapsed row — the \n parts are text, not numeric values.
        headers = ["Selling Name", "Unit Rate"]
        row = {
            "Selling Name": "Bravo Early\nNo\nBDN-\nFringe (M-",
            "Unit Rate": "$634",
        }
        a = [_col("SNQ", headers, [row])]
        b = [_col("SNQ", headers, [row])]
        result = compare_tables(a, b)

        row_labels = {
            d.field.split(" › ")[1]
            for d in result.diffs
            if len(d.field.split(" › ")) >= 2
        }
        assert any("BDN" in lbl for lbl in row_labels), (
            f"Multi-line name was incorrectly truncated. Labels: {row_labels}"
        )

    def test_trailing_empty_key_columns_not_in_label(self):
        """When a row only fills the first key column, trailing ' · ' dots must be stripped."""
        # key_cols will be ["Selling Name", "Comm Type"] because "Selling Name" alone
        # is not unique (two Bravo rows).  The summary row has Comm Type = "" → without
        # stripping the label would be "Total Bravo · " instead of "Total Bravo".
        headers = ["Selling Name", "Comm Type", "Rate"]
        rows = [
            {"Selling Name": "Bravo", "Comm Type": "NATL",  "Rate": "$634"},
            {"Selling Name": "Bravo", "Comm Type": "Local", "Rate": "$500"},
            {"Selling Name": "Total Bravo", "Comm Type": "", "Rate": "$1,134"},
        ]
        a = [_col("SNQ", headers, rows)]
        b = [_col("SNQ", headers, rows)]
        result = compare_tables(a, b)

        for d in result.diffs:
            parts = d.field.split(" › ")
            row_label = parts[1] if len(parts) >= 2 else ""
            assert not row_label.endswith(" · "), (
                f"Trailing dot in label: {d.field!r}"
            )
            assert " ·  · " not in row_label, (
                f"Multiple empty dots in label: {d.field!r}"
            )

    def test_numeric_values_filtered_from_misaligned_summary_rows(self):
        """Summary rows with merged cells can shift metrics into key column slots.

        When camelot extracts a summary row (e.g., "No Price Period - Bravo") whose
        label spans multiple columns, the metric values may land in key column slots
        due to column misalignment. These purely numeric parts must be filtered out
        from the display label.

        Real-world example: PDF shows "No Price Period - Bravo" with metrics 3,276,
        100.00%, $40.99, $34.84. After extraction the row dict might have:
          - "Selling Name": "No Price Period - Bravo"
          - "Unit Length": "3,276"       (shifted metric!)
          - "SN Group": "100.00%"        (shifted metric!)
          - "Comm Type": "$40.99"        (shifted metric!)
          - "Rtg. Strm.": "$34.84"       (shifted metric!)

        Without filtering, the label would be:
          "No Price Period - Bravo · 3,276 · 100.00% · $40.99 · $34.84"

        With filtering, the label should be just:
          "No Price Period - Bravo"
        """
        headers = ["Selling Name", "Unit Length", "SN Group", "Comm Type", "Rtg. Strm.", "Total Imps"]
        # Summary row with misaligned metrics in key column slots
        summary_row = {
            "Selling Name": "No Price Period - Bravo",
            "Unit Length": "3,276",       # shifted metric
            "SN Group": "100.00%",        # shifted metric
            "Comm Type": "$40.99",        # shifted metric
            "Rtg. Strm.": "$34.84",       # shifted metric
            "Total Imps": "3,276",
        }
        # Detail row with proper column alignment
        detail_row = {
            "Selling Name": "Bravo Late Night",
            "Unit Length": ":15",
            "SN Group": "No SN Group",
            "Comm Type": "NATL/Guar",
            "Rtg. Strm.": "BDN-C3",
            "Total Imps": "360",
        }
        a = [_col("Summary", headers, [summary_row, detail_row])]
        b = [_col("Summary", headers, [summary_row, detail_row])]
        result = compare_tables(a, b)

        for d in result.diffs:
            parts = d.field.split(" › ")
            row_label = parts[1] if len(parts) >= 2 else ""
            # No numeric values should appear in the row label
            assert "3,276" not in row_label, f"Numeric value leaked into label: {d.field!r}"
            assert "100.00%" not in row_label, f"Percentage leaked into label: {d.field!r}"
            assert "$40.99" not in row_label, f"Currency leaked into label: {d.field!r}"
            assert "$34.84" not in row_label, f"Currency leaked into label: {d.field!r}"

        # Verify summary row label is clean
        summary_labels = {
            d.field.split(" › ")[1]
            for d in result.diffs
            if "No Price Period" in d.field
        }
        assert "No Price Period - Bravo" in summary_labels, (
            f"Expected clean summary label, got: {summary_labels}"
        )

    def test_misaligned_rows_shown_as_is_without_realignment(self):
        """Values are shown as extracted without automatic realignment.

        The _realign_row function was disabled because its heuristic incorrectly
        triggered on legitimate rows with empty columns in the middle. Values
        are now shown exactly as extracted from the PDF, even if misaligned.

        This test verifies that all columns are shown as value fields, including
        the key columns, preserving the exact extracted values.
        """
        headers = ["Selling Name", "Unit Length", "SN Group", "Total Imps", "Total GRPs", "VPVH"]
        # Row with values in various columns - no realignment attempted
        total_row = {
            "Selling Name": "Total",
            "Unit Length": "16,519",
            "SN Group": "24.39",
            "Total Imps": "",
            "Total GRPs": "",
            "VPVH": "0.256",
        }
        a = [_col("Summary", headers, [total_row])]
        b = [_col("Summary", headers, [total_row])]
        result = compare_tables(a, b)

        # Find diffs for the Total row - all columns should be present
        total_diffs = [d for d in result.diffs if d.field.startswith("Summary › Total ›")]

        # Values should appear in their original columns, no realignment
        selling_name_diff = next((d for d in total_diffs if "Selling Name" in d.field), None)
        unit_length_diff = next((d for d in total_diffs if "Unit Length" in d.field), None)
        sn_group_diff = next((d for d in total_diffs if "SN Group" in d.field), None)
        vpvh_diff = next((d for d in total_diffs if "VPVH" in d.field), None)

        assert selling_name_diff is not None, "Selling Name should appear as a value field"
        assert selling_name_diff.value_a == "Total"

        assert unit_length_diff is not None, "Unit Length should appear as a value field"
        assert unit_length_diff.value_a == "16,519"

        assert sn_group_diff is not None, "SN Group should appear as a value field"
        assert sn_group_diff.value_a == "24.39"

        assert vpvh_diff is not None, "VPVH should have a diff"
        assert vpvh_diff.value_a == "0.256"
