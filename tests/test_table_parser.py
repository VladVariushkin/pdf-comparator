import os
import pytest
import pandas as pd
from pathlib import Path
from services.table_parser import TableParser, _is_numeric, _is_header_row, _looks_like_key_value
from services.extractor import _disambiguate_titles, _merge_continuation_tables, _normalize_continuation_headers

_FIXTURES_PDFS = Path(__file__).parent / "fixtures" / "pdfs"
FLOWCHART_PDF = str(_FIXTURES_PDFS / "UWS_289805_Flowchart_Report_2026-03-20_Before.pdf")
PROPOSAL_PDF  = str(_FIXTURES_PDFS / "UWS_279295_External_Proposal_Report_Blank_2026-04-06_After.pdf")


class TestIsNumeric:
    def test_currency(self):
        assert _is_numeric("$241") is True

    def test_percentage(self):
        assert _is_numeric("100.0%") is True
        assert _is_numeric("0.0%") is True

    def test_bare_integer(self):
        assert _is_numeric("289805") is True
        assert _is_numeric("42") is True

    def test_comma_number(self):
        assert _is_numeric("2,400,000") is True

    def test_date_string_not_numeric(self):
        # "12/29" must NOT be numeric — it's a column header in matrix tables
        assert _is_numeric("12/29") is False
        assert _is_numeric("1/5") is False

    def test_alpha_label_not_numeric(self):
        assert _is_numeric("P2+") is False
        assert _is_numeric("NATL") is False
        assert _is_numeric("Selling Name") is False
        assert _is_numeric("Total Dollars") is False

    def test_empty_not_numeric(self):
        assert _is_numeric("") is False
        assert _is_numeric("   ") is False

    def test_percent_label_not_numeric(self):
        # Column headers like "Imps %" or "Total F18-49\nImps %" must not be
        # classified as numeric — only bare percentage values should match.
        assert _is_numeric("Imps %") is False
        assert _is_numeric("GRPs %") is False
        assert _is_numeric("Total F18-49\nImps %") is False


class TestIsHeaderRow:
    def test_all_string_labels(self):
        row = ["Selling Name", "Days/Times", "Comm Type", "Unit Rate", "Total Dollars"]
        assert _is_header_row(row) is True

    def test_date_column_headers(self):
        # matrix header: first cell empty, rest are date strings
        row = ["", "12/29", "1/5", "1/12", "Total"]
        assert _is_header_row(row) is True

    def test_data_row_with_currency(self):
        row = ["Bravo Early Morning", "MTWTFSS", "NATL", "$241", "$1,205"]
        assert _is_header_row(row) is False

    def test_data_row_with_percentage(self):
        row = [":15", "$0", "$0", "100.0%", "$2,545"]
        assert _is_header_row(row) is False

    def test_key_value_data_row(self):
        # second cell is numeric → not a header
        row = ["UWS #", "289805"]
        assert _is_header_row(row) is False

    def test_sparse_row_below_threshold(self):
        # only 1 cell filled in a 5-column row → fill_rate = 0.2 < 0.5
        row = ["1Q26", "", "", "", ""]
        assert _is_header_row(row) is False


class TestParseKeyValue:
    def test_basic_with_title(self):
        df = pd.DataFrame([
            ["Plan", ""],
            ["UWS #", "289805"],
            ["Plan Name", "PODS Enterprises"],
            ["Property", "Bravo"],
            ["Advertiser", "PODS Enterprises, INC"],
        ])
        result = TableParser.parse(df)
        assert result is not None
        assert result["type"] == "key_value"
        assert result["title"] == "Plan"
        assert result["data"]["UWS #"] == "289805"
        assert result["data"]["Plan Name"] == "PODS Enterprises"
        assert result["data"]["Property"] == "Bravo"
        assert result["data"]["Advertiser"] == "PODS Enterprises, INC"

    def test_no_title_row(self):
        # First row has numeric value → not a header → key_value
        df = pd.DataFrame([
            ["UWS #", "289805"],
            ["Plan Name", "PODS Enterprises"],
        ])
        result = TableParser.parse(df)
        assert result is not None
        assert result["type"] == "key_value"
        assert result["title"] == ""
        assert result["data"]["UWS #"] == "289805"

    def test_skips_empty_key_rows(self):
        df = pd.DataFrame([
            ["Plan", ""],
            ["UWS #", "289805"],
            ["", "orphan value"],   # empty key → skipped
            ["Property", "Bravo"],
        ])
        result = TableParser.parse(df)
        assert "" not in result["data"]
        assert "UWS #" in result["data"]
        assert "Property" in result["data"]


class TestParseColumnar:
    def test_basic_with_title(self):
        df = pd.DataFrame([
            ["1Q26", "", "", "", ""],
            ["Selling Name", "Days/Times", "Comm Type", "Unit Rate", "Total Dollars"],
            ["Bravo Early Morning", "MTWTFSS 06:00a-08:00a", "NATL", "$241", "$1,205"],
            ["Bravo Daytime", "M-F 08:00a-03:00p", "NATL", "$335", "$1,340"],
        ])
        result = TableParser.parse(df)
        assert result is not None
        assert result["type"] == "columnar"
        assert result["title"] == "1Q26"
        assert result["headers"] == ["Selling Name", "Days/Times", "Comm Type", "Unit Rate", "Total Dollars"]
        assert len(result["rows"]) == 2
        assert result["rows"][0]["Selling Name"] == "Bravo Early Morning"
        assert result["rows"][0]["Unit Rate"] == "$241"
        assert result["rows"][1]["Selling Name"] == "Bravo Daytime"
        assert result["rows"][1]["Total Dollars"] == "$1,340"

    def test_skips_all_empty_rows(self):
        df = pd.DataFrame([
            ["1Q26", "", ""],
            ["Col A", "Col B", "Col C"],
            ["val1", "val2", "val3"],
            ["", "", ""],           # all-empty row → skipped
            ["val4", "val5", "val6"],
        ])
        result = TableParser.parse(df)
        assert len(result["rows"]) == 2  # empty row not included


class TestParseMatrix:
    def test_basic_with_title(self):
        df = pd.DataFrame([
            ["Dollars by Week - 1Q26", "", "", "", ""],
            ["", "12/29", "1/5", "1/12", "Total"],
            [":15", "$0", "$0", "$0", "$2,545"],
            ["% :15", "0.0%", "0.0%", "0.0%", "100.0%"],
            ["Total", "$0", "$0", "$0", "$2,545"],
        ])
        result = TableParser.parse(df)
        assert result is not None
        assert result["type"] == "matrix"
        assert result["title"] == "Dollars by Week - 1Q26"
        assert result["columns"] == ["12/29", "1/5", "1/12", "Total"]
        assert ":15" in result["rows"]
        assert "% :15" in result["rows"]
        assert "Total" in result["rows"]
        assert result["rows"][":15"]["Total"] == "$2,545"
        assert result["rows"]["% :15"]["1/12"] == "0.0%"
        assert result["rows"]["Total"]["12/29"] == "$0"

    def test_sparse_header_alignment(self):
        # Empty first header cell with non-empty remaining cells → matrix.
        # 3-column layout so fill_rate = 2/3 > 0.5 (the _is_header_row threshold).
        # Tests that col_map is built from non-empty header positions only.
        df = pd.DataFrame([
            ["Title", "", ""],
            ["", "Col A", "Col C"],   # first cell empty → matrix path
            ["Row 1", "val_a", "val_c"],
        ])
        result = TableParser.parse(df)
        assert result is not None
        assert result["type"] == "matrix"
        assert result["columns"] == ["Col A", "Col C"]
        # col_map = [(1, "Col A"), (2, "Col C")]
        assert result["rows"]["Row 1"]["Col A"] == "val_a"
        assert result["rows"]["Row 1"]["Col C"] == "val_c"


class TestDisambiguateTitles:
    def _t(self, title, page):
        return {"type": "key_value", "title": title, "data": {}, "page": page}

    def test_no_duplicates_unchanged(self):
        tables = [self._t("Plan", 1), self._t("Summary", 2)]
        result = _disambiguate_titles(tables)
        assert result[0]["title"] == "Plan"
        assert result[1]["title"] == "Summary"

    def test_duplicate_titles_get_page_suffix(self):
        tables = [self._t("Property Summary Total", 3), self._t("Property Summary Total", 4)]
        result = _disambiguate_titles(tables)
        assert result[0]["title"] == "Property Summary Total (p. 3)"
        assert result[1]["title"] == "Property Summary Total (p. 4)"

    def test_only_duplicates_are_renamed(self):
        tables = [
            self._t("Plan", 1),
            self._t("Property Summary Total", 3),
            self._t("Property Summary Total", 4),
        ]
        result = _disambiguate_titles(tables)
        assert result[0]["title"] == "Plan"
        assert result[1]["title"] == "Property Summary Total (p. 3)"
        assert result[2]["title"] == "Property Summary Total (p. 4)"

    def test_three_duplicates_all_renamed(self):
        tables = [self._t("SLA", 1), self._t("SLA", 2), self._t("SLA", 3)]
        result = _disambiguate_titles(tables)
        assert result[0]["title"] == "SLA (p. 1)"
        assert result[1]["title"] == "SLA (p. 2)"
        assert result[2]["title"] == "SLA (p. 3)"

    def test_empty_title_not_affected(self):
        tables = [{"type": "key_value", "title": "", "data": {}, "page": 1},
                  {"type": "key_value", "title": "", "data": {}, "page": 2}]
        result = _disambiguate_titles(tables)
        assert result[0]["title"] == ""
        assert result[1]["title"] == ""

    def test_missing_page_falls_back_to_question_mark(self):
        tables = [{"type": "key_value", "title": "Plan", "data": {}},
                  {"type": "key_value", "title": "Plan", "data": {}}]
        result = _disambiguate_titles(tables)
        assert result[0]["title"] == "Plan (p. ?)"
        assert result[1]["title"] == "Plan (p. ?)"


class TestMergeContinuationTables:
    def _col(self, title, rows, page, headers=None):
        return {"type": "columnar", "title": title, "subtitle": "", "headers": headers or ["Col"], "rows": rows, "page": page}

    def _kv(self, title, data, page):
        return {"type": "key_value", "title": title, "subtitle": "", "data": data, "page": page}

    def _mat(self, title, rows, page, columns=None):
        return {"type": "matrix", "title": title, "subtitle": "", "columns": columns or ["C"], "rows": rows, "page": page}

    def test_no_duplicates_unchanged(self):
        tables = [self._col("A", [{"Col": "1"}], 1), self._col("B", [{"Col": "2"}], 2)]
        result = _merge_continuation_tables(tables)
        assert len(result) == 2
        assert result[0]["title"] == "A"
        assert result[1]["title"] == "B"

    def test_adjacent_columnar_merged(self):
        tables = [
            self._col("Report", [{"Col": "r1"}], 1),
            self._col("Report", [{"Col": "r2"}], 2),
        ]
        result = _merge_continuation_tables(tables)
        assert len(result) == 1
        assert result[0]["title"] == "Report"
        assert result[0]["rows"] == [{"Col": "r1"}, {"Col": "r2"}]
        assert result[0]["page"] == 1

    def test_adjacent_key_value_merged(self):
        tables = [
            self._kv("Plan", {"UWS #": "123"}, 1),
            self._kv("Plan", {"Property": "Bravo"}, 2),
        ]
        result = _merge_continuation_tables(tables)
        assert len(result) == 1
        assert result[0]["data"] == {"UWS #": "123", "Property": "Bravo"}

    def test_adjacent_matrix_merged(self):
        tables = [
            self._mat("Stats", {"Row1": {"C": "1"}}, 1),
            self._mat("Stats", {"Row2": {"C": "2"}}, 2),
        ]
        result = _merge_continuation_tables(tables)
        assert len(result) == 1
        assert "Row1" in result[0]["rows"]
        assert "Row2" in result[0]["rows"]

    def test_three_consecutive_all_merged(self):
        tables = [
            self._col("X", [{"Col": "a"}], 1),
            self._col("X", [{"Col": "b"}], 2),
            self._col("X", [{"Col": "c"}], 3),
        ]
        result = _merge_continuation_tables(tables)
        assert len(result) == 1
        assert result[0]["title"] == "X"
        assert len(result[0]["rows"]) == 3

    def test_interleaved_tables_interrupt_merge(self):
        # B(page=1) sits between A(page=1) and A(page=2) in the extraction list.
        # Any titled table between the two A occurrences blocks the merge,
        # even if on the same page — indicates A(p1) is complete.
        tables = [
            self._col("A", [{"Col": "r1"}], 1),
            self._col("B", [{"Col": "rx"}], 1),
            self._col("A", [{"Col": "r2"}], 2),
        ]
        result = _merge_continuation_tables(tables)
        assert len(result) == 3
        assert result[0]["title"] == "A (p. 1)"
        assert result[0]["rows"] == [{"Col": "r1"}]
        assert result[1]["title"] == "B"
        assert result[2]["title"] == "A (p. 2)"
        assert result[2]["rows"] == [{"Col": "r2"}]

    def test_non_consecutive_pages_disambiguates(self):
        # A appears on pages 1 and 3 (page 2 skipped) → two distinct tables.
        tables = [
            self._col("A", [{"Col": "r1"}], 1),
            self._col("A", [{"Col": "r2"}], 3),
        ]
        result = _merge_continuation_tables(tables)
        assert len(result) == 2
        assert result[0]["title"] == "A (p. 1)"
        assert result[1]["title"] == "A (p. 3)"

    def test_interleaving_table_breaks_later_merge(self):
        # A(p1) and A(p2) are consecutive with no table between → merged.
        # B(p2) appears after A(p2), so A(p3) cannot merge with A(p1-p2).
        tables = [
            self._col("A", [{"Col": "r1"}], 1),
            self._col("A", [{"Col": "r2"}], 2),
            self._col("B", [{"Col": "rx"}], 2),
            self._col("A", [{"Col": "r3"}], 3),
        ]
        result = _merge_continuation_tables(tables)
        assert len(result) == 3
        # A(p1-p2) merged (no table between them)
        assert result[0]["title"] == "A (p. 1)"
        assert result[0]["rows"] == [{"Col": "r1"}, {"Col": "r2"}]
        assert result[1]["title"] == "B"
        # A(p3) separate (B interrupted before it)
        assert result[2]["title"] == "A (p. 3)"
        assert result[2]["rows"] == [{"Col": "r3"}]

    def test_untitled_tables_pass_through(self):
        tables = [
            {"type": "key_value", "title": "", "data": {}, "page": 1},
            {"type": "key_value", "title": "", "data": {}, "page": 2},
        ]
        result = _merge_continuation_tables(tables)
        assert len(result) == 2
        assert result[0]["title"] == ""
        assert result[1]["title"] == ""

    def test_untitled_table_between_pages_does_not_break_merge(self):
        # An untitled table between A(p1) and A(p2) must not prevent the merge
        # because A's pages are still consecutive.
        tables = [
            self._col("A", [{"Col": "r1"}], 1),
            {"type": "key_value", "title": "", "data": {}, "page": 1},
            self._col("A", [{"Col": "r2"}], 2),
        ]
        result = _merge_continuation_tables(tables)
        assert len(result) == 2
        assert result[0]["title"] == "A"
        assert result[0]["rows"] == [{"Col": "r1"}, {"Col": "r2"}]
        assert result[1]["title"] == ""

    def test_multi_page_interrupting_table_breaks_merge(self):
        # Regression: A spans p1-p2-p3, B spans p2-p3. B's continuation on p3
        # interrupts A's continuation, so A(p3) must NOT merge with A(p1-p2).
        tables = [
            self._col("A", [{"Col": "a1"}], 1),
            self._col("A", [{"Col": "a2"}], 2),
            self._col("B", [{"Col": "b1"}], 2),
            self._col("B", [{"Col": "b2"}], 3),
            self._col("A", [{"Col": "a3"}], 3),
        ]
        result = _merge_continuation_tables(tables)
        assert len(result) == 3, f"Expected 3 tables, got {len(result)}"
        # A(p1-p2) merged
        assert result[0]["title"] == "A (p. 1)"
        assert result[0]["rows"] == [{"Col": "a1"}, {"Col": "a2"}]
        # B(p2-p3) merged
        assert result[1]["title"] == "B"
        assert result[1]["rows"] == [{"Col": "b1"}, {"Col": "b2"}]
        # A(p3) separate
        assert result[2]["title"] == "A (p. 3)"
        assert result[2]["rows"] == [{"Col": "a3"}]

    def test_same_page_table_breaks_merge(self):
        # B appears between A(p2) and A(p3) in extraction order → breaks merge.
        # Even though B is on page 2, it indicates A(p2) is complete.
        tables = [
            self._col("A", [{"Col": "a1"}], 1),
            self._col("A", [{"Col": "a2"}], 2),
            self._col("B", [{"Col": "b1"}], 2),
            self._col("A", [{"Col": "a3"}], 3),
        ]
        result = _merge_continuation_tables(tables)
        assert len(result) == 3
        # A(p1-p2) merged (no table between them)
        assert result[0]["title"] == "A (p. 1)"
        assert len(result[0]["rows"]) == 2
        assert result[1]["title"] == "B"
        # A(p3) separate
        assert result[2]["title"] == "A (p. 3)"

    # --- header/column promotion on merge ---

    _ALL_HEADERS = ["Selling Name", "Unit Length", "SN Group", "Comm Type", "Rtg",
                    "Imps (000)", "Imps %", "Gross CPM", "Net CPM", "Unit (000)", "GRPs", "VPVH"]
    _PARTIAL_HEADERS = ["Imps (000)", "Imps %", "Gross CPM", "Net CPM", "Unit (000)", "GRPs", "VPVH"]

    def test_merge_columnar_continuation_has_more_headers(self):
        # Simulates page-boundary truncation: base table extracted with 7 cols,
        # continuation on the next page has all 12 cols.
        base = self._col("Report", [{"Imps (000)": "1,270"}], 1, headers=self._PARTIAL_HEADERS)
        cont = self._col("Report", [{"Selling Name": "Bravo", "Imps (000)": "108"}], 2, headers=self._ALL_HEADERS)
        result = _merge_continuation_tables([base, cont])
        assert len(result) == 1
        assert result[0]["headers"] == self._ALL_HEADERS
        assert len(result[0]["rows"]) == 2

    def test_merge_columnar_base_has_more_headers(self):
        # Continuation is a shorter fragment — base headers must be preserved.
        base = self._col("Report", [{"Selling Name": "Bravo"}], 1, headers=self._ALL_HEADERS)
        cont = self._col("Report", [{"Imps (000)": "108"}], 2, headers=self._PARTIAL_HEADERS)
        result = _merge_continuation_tables([base, cont])
        assert len(result) == 1
        assert result[0]["headers"] == self._ALL_HEADERS

    def test_merge_columnar_equal_headers_unchanged(self):
        base = self._col("Report", [{"Col": "a"}], 1)
        cont = self._col("Report", [{"Col": "b"}], 2)
        result = _merge_continuation_tables([base, cont])
        assert result[0]["headers"] == ["Col"]

    def test_merge_matrix_continuation_has_more_columns(self):
        all_cols = ["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10", "W11", "W12", "Total"]
        partial_cols = ["W7", "W8", "W9", "W10", "W11", "W12", "Total"]
        base = self._mat("Stats", {":15": {"W7": "$0", "Total": "$2,545"}}, 1, columns=partial_cols)
        cont = self._mat("Stats", {":30": {"W1": "$100", "Total": "$1,200"}}, 2, columns=all_cols)
        result = _merge_continuation_tables([base, cont])
        assert len(result) == 1
        assert result[0]["columns"] == all_cols
        assert ":15" in result[0]["rows"]
        assert ":30" in result[0]["rows"]

    def test_merge_matrix_base_has_more_columns(self):
        all_cols = ["W1", "W2", "W3", "Total"]
        partial_cols = ["W3", "Total"]
        base = self._mat("Stats", {"Row1": {"W1": "1", "Total": "3"}}, 1, columns=all_cols)
        cont = self._mat("Stats", {"Row2": {"W3": "2", "Total": "2"}}, 2, columns=partial_cols)
        result = _merge_continuation_tables([base, cont])
        assert result[0]["columns"] == all_cols


class TestNormalizeContinuationHeaders:
    """_normalize_continuation_headers must remap row dict keys even when the
    page's headers *clean* to the canonical form but are not literally equal —
    e.g. "Unit\\nRate" cleans to "Unit Rate" == canonical, but the row dict still
    has "Unit\\nRate" as the key.  Without the fix compare_tables sees
    value_cols = ["Unit Rate"] and row.get("Unit Rate") == None → value dropped."""

    def _col(self, title, headers, rows, page):
        return {"type": "columnar", "title": title, "headers": headers, "rows": rows, "page": page}

    def test_row_keys_remapped_when_headers_differ_only_in_newlines(self):
        page_a = self._col(
            "Dayparts by Quarter",
            headers=["Daypart", "Unit Rate", "Gross Dollars"],
            rows=[{"Daypart": "Prime", "Unit Rate": "$921", "Gross Dollars": "$7,364"}],
            page=9,
        )
        # Page 10 has the same headers but with \n instead of spaces.
        # After cleaning they equal canonical, so the current code skips remapping.
        page_b = self._col(
            "Dayparts by Quarter",
            headers=["Daypart", "Unit\nRate", "Gross\nDollars"],
            rows=[{"Daypart": "Total", "Unit\nRate": "$780", "Gross\nDollars": "$732,276"}],
            page=10,
        )

        result = _normalize_continuation_headers([page_a, page_b])

        total_row = result[1]["rows"][0]
        assert "Unit Rate" in total_row, (
            f"Row key not remapped from 'Unit\\nRate' to canonical 'Unit Rate': {list(total_row.keys())}"
        )
        assert total_row["Unit Rate"] == "$780"
        assert "Gross Dollars" in total_row
        assert total_row["Gross Dollars"] == "$732,276"
        assert "Unit\nRate" not in total_row
        assert "Gross\nDollars" not in total_row

    def test_canonical_page_rows_unchanged(self):
        """The page whose headers are already canonical must not be modified."""
        page_a = self._col(
            "Dayparts by Quarter",
            headers=["Daypart", "Unit Rate"],
            rows=[{"Daypart": "Prime", "Unit Rate": "$921"}],
            page=9,
        )
        page_b = self._col(
            "Dayparts by Quarter",
            headers=["Daypart", "Unit\nRate"],
            rows=[{"Daypart": "Total", "Unit\nRate": "$780"}],
            page=10,
        )

        result = _normalize_continuation_headers([page_a, page_b])

        # Page A rows are unchanged
        assert result[0]["rows"][0] == {"Daypart": "Prime", "Unit Rate": "$921"}


class TestLooksLikeKeyValue:
    def test_numeric_right_cell_is_key_value(self):
        rows = [["UWS #", "289805"], ["Plan Name", "Bravo"]]
        assert _looks_like_key_value(rows) is True

    def test_blank_right_cell_is_key_value(self):
        # Even if row 0 passes _is_header_row, a blank value cell signals key_value
        rows = [
            ["Advertiser", "Boehringer-Ingelheim"],
            ["UWS Plan Link Id", ""],   # blank value ← definitive signal
        ]
        assert _looks_like_key_value(rows) is True

    def test_long_right_cell_is_key_value(self):
        rows = [
            ["Advertiser", "Boehringer-Ingelheim"],
            ["Campaign Name", "Boehringer-Ingelheim 1Q26 CKD Advanced : Bravo-V2"],
        ]
        assert _looks_like_key_value(rows) is True

    def test_genuine_columnar_header_is_not_key_value(self):
        # Short non-empty values in both columns → genuine columnar table
        rows = [
            ["Metric", "Value"],
            ["Uptime", "99.9%"],
            ["Latency", "50ms"],
        ]
        assert _looks_like_key_value(rows) is False


class TestParseWithSubtitle:
    def test_columnar_subtitle_is_preserved(self):
        df = pd.DataFrame([
            ["Property Summary Total", "", "", ""],
            ["Primary Demo P50+", "", "", ""],
            ["Property", "SN Group", "Imps (000)", "GRPs"],
            ["Bravo", "No SN Group", "4,126", "3.36"],
        ])
        result = TableParser.parse(df)
        assert result is not None
        assert result["type"] == "columnar"
        assert result["title"] == "Property Summary Total"
        assert result["subtitle"] == "Primary Demo P50+"
        assert result["headers"] == ["Property", "SN Group", "Imps (000)", "GRPs"]
        assert len(result["rows"]) == 1

    def test_key_value_subtitle_is_preserved(self):
        df = pd.DataFrame([
            ["Plan", ""],
            ["Q1 Details", ""],
            ["UWS #", "289805"],
            ["Property", "Bravo"],
        ])
        result = TableParser.parse(df)
        assert result is not None
        assert result["type"] == "key_value"
        assert result["title"] == "Plan"
        assert result["subtitle"] == "Q1 Details"
        assert result["data"]["UWS #"] == "289805"

    def test_no_subtitle_gives_empty_string(self):
        df = pd.DataFrame([
            ["Plan", ""],
            ["UWS #", "289805"],
        ])
        result = TableParser.parse(df)
        assert result["subtitle"] == ""

    def test_matrix_subtitle_is_preserved(self):
        df = pd.DataFrame([
            ["Dollars by Week", "", "", ""],
            ["P50+", "", "", ""],
            ["", "12/29", "1/5", "Total"],
            [":15", "$0", "$0", "$2,545"],
        ])
        result = TableParser.parse(df)
        assert result is not None
        assert result["type"] == "matrix"
        assert result["subtitle"] == "P50+"


class TestParseEdgeCases:
    def test_empty_dataframe(self):
        df = pd.DataFrame()
        assert TableParser.parse(df) is None

    def test_title_only(self):
        df = pd.DataFrame([["Only Title", ""]])
        assert TableParser.parse(df) is None

    def test_two_col_with_header(self):
        # Genuine columnar: short non-empty values in both columns across all rows
        # "Metric"/"Value" as headers, data rows with short values → stays columnar
        df = pd.DataFrame([
            ["Metric", "Value"],
            ["Uptime", "99.9%"],
            ["Latency", "50ms"],
        ])
        result = TableParser.parse(df)
        assert result is not None
        assert result["type"] == "columnar"
        assert result["headers"] == ["Metric", "Value"]
        assert len(result["rows"]) == 2

    def test_overview_style_table_is_key_value(self):
        # Regression: all-text 2-col table with a blank value and a long value
        # was incorrectly parsed as columnar before _looks_like_key_value was added.
        df = pd.DataFrame([
            ["Overview", ""],                   # title row (stripped)
            ["Advertiser", "Boehringer-Ingelheim"],
            ["Campaign Name", "Boehringer-Ingelheim 1Q26 CKD Advanced : Bravo-V2"],
            ["Agency", "OMD USA"],
            ["Deal Status", "Order"],
            ["UWS Plan Link Id", ""],           # blank value ← triggers key_value detection
            ["UWS Plan Id", "279295"],
        ])
        result = TableParser.parse(df)
        assert result is not None
        assert result["type"] == "key_value", f"Expected key_value, got {result['type']}"
        assert result["title"] == "Overview"
        assert result["data"]["Advertiser"] == "Boehringer-Ingelheim"
        assert result["data"]["Campaign Name"] == "Boehringer-Ingelheim 1Q26 CKD Advanced : Bravo-V2"
        assert result["data"]["UWS Plan Link Id"] == ""
        assert result["data"]["UWS Plan Id"] == "279295"


@pytest.fixture(scope="module")
def flowchart_tables():
    """Parse all tables from the real flowchart PDF; skip if file absent."""
    if not os.path.exists(FLOWCHART_PDF):
        pytest.skip(f"fixture PDF not found: {FLOWCHART_PDF}")
    from services.extractor import _extract_dfs
    tables = []
    for page_num, df in _extract_dfs(FLOWCHART_PDF):
        parsed = TableParser.parse(df)
        if parsed:
            parsed["page"] = page_num
            tables.append(parsed)
    return tables


class TestFlowchartReportPdf:
    def test_table_count(self, flowchart_tables):
        assert len(flowchart_tables) == 9

    def test_page1_plan_header_is_key_value(self, flowchart_tables):
        t = flowchart_tables[0]
        assert t["type"] == "key_value"
        assert t["title"] == "Plan"

    def test_page1_plan_fields(self, flowchart_tables):
        data = flowchart_tables[0]["data"]
        assert data["UWS #"] == "289805"
        assert data["Property"] == "Bravo"
        assert data["Plan Status"] == "Order"
        assert data["Primary Demo"] == "P2+"
        assert data["Guaranteed"] == "No"
        assert data["Equivalized"] == "Yes"

    def test_page2_line_items_are_columnar(self, flowchart_tables):
        t = flowchart_tables[1]
        assert t["type"] == "columnar"
        assert t["title"] == "1Q26"
        assert "Unit\nRate" in t["headers"]
        assert "Total\nDollars" in t["headers"]

    def test_page2_line_item_rates(self, flowchart_tables):
        rows = flowchart_tables[1]["rows"]
        rates = {r["Selling\nName"].replace("\n", " "): r["Unit\nRate"] for r in rows if r.get("Unit\nRate")}
        assert rates.get("Bravo Early Morning (M-Su 6a-8a)") == "$241"
        assert rates.get("Bravo Daytime (M-F 8a-3p)") == "$335"

    def test_page2_units_by_week_matrix(self, flowchart_tables):
        t = flowchart_tables[2]
        assert t["type"] == "matrix"
        assert t["title"] == "Units by Week - 1Q26"
        assert "Total" in t["columns"]
        assert t["rows"][":15"]["Total"] == "9"
        assert t["rows"]["Total"]["1/19"] == "9"

    def test_page2_dollars_by_week_matrix(self, flowchart_tables):
        t = flowchart_tables[3]
        assert t["type"] == "matrix"
        assert t["title"] == "Dollars by Week - 1Q26"
        assert t["rows"][":15"]["Total"] == "$2,545"
        assert t["rows"][":15"]["1/19"] == "$2,545"
        assert t["rows"][":15"]["12/29"] == "$0"

    def test_matrix_week_columns(self, flowchart_tables):
        # All matrix tables share the same 14 weekly columns
        expected_cols = ["12/29", "1/5", "1/12", "1/19", "1/26",
                         "2/2", "2/9", "2/16", "2/23", "3/2", "3/9", "3/16", "3/23", "Total"]
        for t in flowchart_tables[2:]:   # skip key_value and columnar
            assert t["type"] == "matrix"
            assert t["columns"] == expected_cols

    def test_matrix_titles(self, flowchart_tables):
        expected_titles = [
            "Units by Week - 1Q26",
            "Dollars by Week - 1Q26",
            "P2+ (000) by Week - 1Q26",
            "P2+ (000) by Week - 1Q26",   # split across pages
            "F18-49 (000) by Week - 1Q26",
            "P2+ GRPs by Week - 1Q26",
            "F18-49 GRPs by Week - 1Q26",
        ]
        actual = [t["title"] for t in flowchart_tables[2:]]
        assert actual == expected_titles


@pytest.fixture(scope="module")
def proposal_tables():
    """Extract tables from the External Proposal Report PDF via the full pipeline
    (including _disambiguate_titles); skip if the file is absent."""
    if not os.path.exists(PROPOSAL_PDF):
        pytest.skip(f"fixture PDF not found: {PROPOSAL_PDF}")
    from services.extractor import _extract_tables
    return _extract_tables(PROPOSAL_PDF)


class TestExternalProposalPdf:
    def test_same_title_tables_disambiguated_when_interrupted(self, proposal_tables):
        # "Property Summary Total" appears on pages 3 and 4, but they're interrupted
        # by "Property Summary Total by Quarter" on page 3. So they must be disambiguated.
        titles = [t["title"] for t in proposal_tables]
        # Both should be disambiguated since they can't merge
        assert "Property Summary Total (p. 3)" in titles
        assert "Property Summary Total (p. 4)" in titles
        # The un-disambiguated version should NOT exist
        assert "Property Summary Total" not in titles

    def test_all_titles_are_unique(self, proposal_tables):
        titles = [t["title"] for t in proposal_tables if t.get("title")]
        duplicates = [t for t in set(titles) if titles.count(t) > 1]
        assert not duplicates, f"Duplicate titles after disambiguation: {duplicates}"

    def test_page_numbers_are_attached(self, proposal_tables):
        for t in proposal_tables:
            assert "page" in t, f"Table '{t.get('title')}' is missing 'page' key"
            assert isinstance(t["page"], int) and t["page"] > 0


INTERNAL_PROPOSAL_PDF = str(_FIXTURES_PDFS / "Plan_279295_Internal_Proposal_Report__2026-04-06_After.pdf")

_F18_TITLE = "Selling Names by Quarter / Daypart - Secondary Demo F18-49"
# With line_scale=40, columns are extracted properly instead of being merged
_NAME_COL  = "Name"
_RATE_COL  = "Unit Rate"


@pytest.fixture(scope="module")
def internal_proposal_tables():
    """Extract tables from the Internal Proposal PDF; skip if file absent."""
    if not os.path.exists(INTERNAL_PROPOSAL_PDF):
        pytest.skip(f"fixture PDF not found: {INTERNAL_PROPOSAL_PDF}")
    from services.extractor import _extract_tables
    return _extract_tables(INTERNAL_PROPOSAL_PDF)


class TestInternalProposalMerge:
    """The F18-49 selling names table spans pages 5–6 with no interrupting
    table between them, so _merge_continuation_tables must produce a single
    merged entry rather than two separate (disambiguated) entries."""

    def test_split_table_appears_exactly_once(self, internal_proposal_tables):
        titles = [t["title"] for t in internal_proposal_tables]
        assert titles.count(_F18_TITLE) == 1, (
            f"Expected 1 occurrence of merged table, got {titles.count(_F18_TITLE)}"
        )

    def test_merged_table_starts_on_page_5(self, internal_proposal_tables):
        t = next(t for t in internal_proposal_tables if t["title"] == _F18_TITLE)
        assert t["page"] == 5

    def test_merged_table_combines_rows_from_both_pages(self, internal_proposal_tables):
        # Page 5 contributes 9 rows, page 6 contributes 2 rows → 11 total
        t = next(t for t in internal_proposal_tables if t["title"] == _F18_TITLE)
        assert len(t["rows"]) == 11

    def test_first_row_originates_from_page_5(self, internal_proposal_tables):
        t = next(t for t in internal_proposal_tables if t["title"] == _F18_TITLE)
        assert t["rows"][0][_RATE_COL] == "$1,385"

    def test_last_rows_originate_from_page_6(self, internal_proposal_tables):
        t = next(t for t in internal_proposal_tables if t["title"] == _F18_TITLE)
        assert t["rows"][9][_NAME_COL] == "Weekend Day"
        assert t["rows"][9][_RATE_COL] == "$1,163"
        assert t["rows"][10][_RATE_COL] == "$2,326"

    def test_no_page_suffixed_variant_exists(self, internal_proposal_tables):
        # If the merge had NOT happened, the titles would be disambiguated
        # to "(p. 5)" and "(p. 6)". Neither should exist.
        titles = [t["title"] for t in internal_proposal_tables]
        assert f"{_F18_TITLE} (p. 5)" not in titles
        assert f"{_F18_TITLE} (p. 6)" not in titles


# ---------------------------------------------------------------------------
# External Proposal PDF — Secondary Demos table on pages 11-12
# ---------------------------------------------------------------------------

_SNQ_SD_TITLE    = "Selling Names by Quarter - Secondary Demos"
# With line_scale=40, camelot now correctly extracts all 12 columns instead of
# merging the first 5 key columns into one. Updated column names reflect this.
_SNQ_SD_NAME_COL = "Selling Name"
_SNQ_SD_IMPS_COL = "Total F18-49 Imps (000)"
_SNQ_SD_IMPP_COL = "Total F18-49 Imps %"
_SNQ_SD_GCPM_COL = "Total F18-49 Gross CPM"
_SNQ_SD_NCPM_COL = "Total F18-49 Net CPM"
_SNQ_SD_GRPS_COL = "Total F18-49 GRPs"
_SNQ_SD_VPVH_COL = "Total F18-49 VPVH"


@pytest.fixture(scope="module")
def selling_names_qtr_sd_table(proposal_tables):
    """Return the 'Selling Names by Quarter - Secondary Demos' table."""
    t = next((t for t in proposal_tables if t["title"] == _SNQ_SD_TITLE), None)
    if t is None:
        pytest.skip(f"Table '{_SNQ_SD_TITLE}' not found in proposal PDF")
    return t


class TestSellingNamesQtrSecondaryDemos:
    """Regression tests for the page-12 secondary-demos table.

    Root cause 1: _is_numeric("Total F18-49\\nImps %") returned True because the
    string ends with '%', causing _is_header_row to return False and falling back to
    generic col_N headers.

    Root cause 2: _merge_tables did not update headers when the continuation table
    has more columns than the base — relevant for the "Selling Names - Secondary Demos"
    table that spans pages 9-10 with 8 and 12 headers respectively.
    """

    def test_table_exists_in_extracted_output(self, selling_names_qtr_sd_table):
        assert selling_names_qtr_sd_table is not None

    def test_table_is_on_page_11_or_12(self, selling_names_qtr_sd_table):
        # With line_scale=40, camelot may detect the table starting on page 11 or 12
        assert selling_names_qtr_sd_table["page"] in (11, 12)

    def test_no_fallback_col_headers(self, selling_names_qtr_sd_table):
        # Before the _is_numeric fix, headers were ['col_0', 'col_1', ...].
        headers = selling_names_qtr_sd_table["headers"]
        fallback = [h for h in headers if h.startswith("col_")]
        assert not fallback, f"Fallback headers found: {fallback}"

    def test_header_count(self, selling_names_qtr_sd_table):
        # With line_scale=40, camelot correctly extracts all 12 columns
        # (5 key columns + 7 F18-49 metrics).
        assert len(selling_names_qtr_sd_table["headers"]) == 12

    def test_expected_column_names_present(self, selling_names_qtr_sd_table):
        headers = selling_names_qtr_sd_table["headers"]
        for col in (_SNQ_SD_IMPS_COL, _SNQ_SD_IMPP_COL, _SNQ_SD_GCPM_COL,
                    _SNQ_SD_NCPM_COL, _SNQ_SD_GRPS_COL, _SNQ_SD_VPVH_COL):
            assert col in headers, f"Expected column missing: {repr(col)}"

    def test_row_count(self, selling_names_qtr_sd_table):
        # With line_scale=40, we get 14 rows (including quarter headers like "1Q26")
        assert len(selling_names_qtr_sd_table["rows"]) == 14

    def test_first_row_is_quarter_header(self, selling_names_qtr_sd_table):
        # First row is a quarter header "1Q26", not a data row
        row = selling_names_qtr_sd_table["rows"][0]
        assert row[_SNQ_SD_NAME_COL] == "1Q26"

    def test_total_row_values(self, selling_names_qtr_sd_table):
        total = selling_names_qtr_sd_table["rows"][-1]
        assert total[_SNQ_SD_NAME_COL] == "Total"
        assert total[_SNQ_SD_IMPS_COL] == "1,270"
        assert total[_SNQ_SD_IMPP_COL] == "100.00%"
        assert total[_SNQ_SD_GCPM_COL] == "$52.32"
        assert total[_SNQ_SD_NCPM_COL] == "$44.47"
        assert total[_SNQ_SD_GRPS_COL] == "1.88"
        assert total[_SNQ_SD_VPVH_COL] == "0.261"


# ---------------------------------------------------------------------------
# UWS 260860 External Proposal — "Dayparts by Quarter" normalization regression
# ---------------------------------------------------------------------------

_260860_PROPOSAL_PDF = str(_FIXTURES_PDFS / "UWS_260860_External_Proposal_Report_Blank_2026-03-20_Before.pdf")
_DQ_TITLE = "Dayparts by Quarter"


@pytest.fixture(scope="module")
def dayparts_by_quarter_table():
    """Extract tables from the 260860 Before PDF and return the 'Dayparts by Quarter' table.

    Skips if the file is absent.  This table spans multiple pages; the
    _normalize_continuation_headers fix ensures all row keys use the canonical
    (space-separated) header strings so that Total-row values are not silently
    dropped during comparison.
    """
    if not os.path.exists(_260860_PROPOSAL_PDF):
        pytest.skip(f"fixture PDF not found: {_260860_PROPOSAL_PDF}")
    from services.extractor import _extract_tables
    tables = _extract_tables(_260860_PROPOSAL_PDF)
    t = next((t for t in tables if t["title"] == _DQ_TITLE), None)
    if t is None:
        pytest.skip(f"Table '{_DQ_TITLE}' not found in 260860 PDF")
    return t


class TestDaypartsByQuarterNormalization:
    """Regression suite for the _normalize_continuation_headers fix.

    Before the fix, page-10 rows kept 'Unit\\nRate' / 'Gross\\nDollars' keys
    because the short-circuit ``if cleaned_headers == canonical`` fired on the
    canonical page (page 9) and never remapped page-10 rows.  The Total row,
    which lives on page 10, therefore had None for all 18 metric columns in the
    comparison output.
    """

    def test_table_exists(self, dayparts_by_quarter_table):
        assert dayparts_by_quarter_table is not None

    def test_no_newline_in_any_row_key(self, dayparts_by_quarter_table):
        """No row dict may contain a key with a literal \\n character."""
        bad = []
        for row in dayparts_by_quarter_table["rows"]:
            bad.extend(k for k in row if "\n" in k)
        assert not bad, f"Row keys with \\n found (first 5): {bad[:5]}"

    def test_total_row_has_unit_rate(self, dayparts_by_quarter_table):
        total = next(
            (r for r in dayparts_by_quarter_table["rows"] if r.get("Daypart") == "Total"),
            None,
        )
        assert total is not None, "Total row not found"
        assert total.get("Unit Rate") == "$780", (
            f"Expected '$780', got {total.get('Unit Rate')!r}"
        )

    def test_total_row_has_avg_unit_rate(self, dayparts_by_quarter_table):
        total = next(r for r in dayparts_by_quarter_table["rows"] if r.get("Daypart") == "Total")
        assert total.get("Avg Unit Rate") == "$1,280"

    def test_total_row_has_gross_dollars(self, dayparts_by_quarter_table):
        total = next(r for r in dayparts_by_quarter_table["rows"] if r.get("Daypart") == "Total")
        assert total.get("Gross Dollars") == "$732,276"

    def test_total_row_has_primary_imps(self, dayparts_by_quarter_table):
        total = next(r for r in dayparts_by_quarter_table["rows"] if r.get("Daypart") == "Total")
        assert total.get("Primary Imps (000)") == "71,020"

    def test_total_row_has_vpvh(self, dayparts_by_quarter_table):
        total = next(r for r in dayparts_by_quarter_table["rows"] if r.get("Daypart") == "Total")
        assert total.get("VPVH") == "1.103"
