import pytest
from services.pairer import _doc_identity, _doc_role, pair_by_name

# Real-world filenames from the project
_BEFORE = "UWS_279295_Flowchart_Report_2026-03-20_Before.pdf"
_AFTER  = "UWS_279295_Flowchart_Report__2026-03-23_After (1).pdf"
_AFTER2 = "UWS_279295_External_Proposal_Report_Blank_2026-04-06_After.pdf"


class TestDocIdentity:
    def test_strips_before_label(self):
        assert _doc_identity(_BEFORE) == "UWS_279295_Flowchart_Report"

    def test_strips_after_label_and_copy_number(self):
        assert _doc_identity(_AFTER) == "UWS_279295_Flowchart_Report"

    def test_strips_date_only(self):
        assert _doc_identity("Report_2026-01-15.pdf") == "Report"

    def test_double_underscore_is_normalised(self):
        # The After filename has __ before the date; identity should still match Before
        assert _doc_identity(_BEFORE) == _doc_identity(_AFTER)

    def test_no_date_no_label_returns_stem(self):
        assert _doc_identity("MyReport.pdf") == "MyReport"

    def test_copy_number_stripped(self):
        assert _doc_identity("Report_Before (2).pdf") == "Report"

    def test_external_proposal_identity(self):
        assert _doc_identity(_AFTER2) == "UWS_279295_External_Proposal_Report_Blank"

    def test_path_prefix_ignored(self):
        assert _doc_identity(r"C:\Users\Desktop\Doc_2026-01-01_Before.pdf") == "Doc"


class TestDocRole:
    def test_detects_before(self):
        assert _doc_role(_BEFORE) == "before"

    def test_detects_after_with_copy_number(self):
        assert _doc_role(_AFTER) == "after"

    def test_detects_after_no_copy(self):
        assert _doc_role(_AFTER2) == "after"

    def test_returns_none_when_no_label(self):
        assert _doc_role("Report_2026-01-15.pdf") is None

    def test_case_insensitive(self):
        assert _doc_role("Doc_BEFORE.pdf") == "before"
        assert _doc_role("Doc_AFTER.pdf") == "after"


class TestPairByName:
    def test_basic_before_after_pair(self):
        pairs, unmatched = pair_by_name([
            "Doc_2026-01-01_Before.pdf",
            "Doc_2026-02-01_After.pdf",
        ])
        assert len(pairs) == 1
        assert pairs[0][0] == "Doc_2026-01-01_Before.pdf"
        assert pairs[0][1] == "Doc_2026-02-01_After.pdf"
        assert unmatched == []

    def test_real_world_filenames(self):
        pairs, unmatched = pair_by_name([_BEFORE, _AFTER, _AFTER2])
        assert len(pairs) == 1
        assert pairs[0] == (_BEFORE, _AFTER)
        assert unmatched == [_AFTER2]

    def test_multiple_identities_paired_independently(self):
        names = [
            "FlowA_Before.pdf",
            "FlowA_After.pdf",
            "PropB_Before.pdf",
            "PropB_After.pdf",
        ]
        pairs, unmatched = pair_by_name(names)
        assert len(pairs) == 2
        assert unmatched == []
        pair_map = {p[0]: p[1] for p in pairs}
        assert pair_map["FlowA_Before.pdf"] == "FlowA_After.pdf"
        assert pair_map["PropB_Before.pdf"] == "PropB_After.pdf"

    def test_extra_before_goes_to_unmatched(self):
        pairs, unmatched = pair_by_name([
            "Doc_Before.pdf",
            "Doc_Before_v2.pdf",  # same identity after stripping, second before
            "Doc_After.pdf",
        ])
        assert len(pairs) == 1
        assert len(unmatched) == 1

    def test_extra_after_goes_to_unmatched(self):
        pairs, unmatched = pair_by_name([
            "Doc_Before.pdf",
            "Doc_After.pdf",
            "Doc_After (2).pdf",
        ])
        assert len(pairs) == 1
        assert len(unmatched) == 1
        assert "Doc_After (2).pdf" in unmatched

    def test_no_label_goes_to_unmatched(self):
        pairs, unmatched = pair_by_name(["NoLabel_2026-01-01.pdf"])
        assert pairs == []
        assert unmatched == ["NoLabel_2026-01-01.pdf"]

    def test_only_before_no_after(self):
        pairs, unmatched = pair_by_name(["Doc_Before.pdf"])
        assert pairs == []
        assert "Doc_Before.pdf" in unmatched

    def test_empty_input(self):
        pairs, unmatched = pair_by_name([])
        assert pairs == []
        assert unmatched == []
