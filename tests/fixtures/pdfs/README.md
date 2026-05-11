# PDF Fixtures

Place the following real-world PDFs here before running the integration tests.
These files are gitignored (`*.pdf`) and must be provided manually.

| Filename | Used by |
|----------|---------|
| `UWS_279295_Flowchart_Report_2026-03-20_Before.pdf` | `test_compare_tables.py` — `TestRealPdf1Q26FieldOrdering` |
| `UWS_289805_Flowchart_Report_2026-03-20_Before.pdf` | `test_table_parser.py` — `TestFlowchartReportPdf` |
| `UWS_279295_External_Proposal_Report_Blank_2026-04-06_After.pdf` | `test_table_parser.py` — `TestExternalProposalPdf` |
| `Plan_279295_Internal_Proposal_Report__2026-04-06_After.pdf` | `test_table_parser.py` — `TestInternalProposalMerge` |
| `UWS_260860_External_Proposal_Report_Blank_2026-03-20_Before.pdf` | `test_table_parser.py` — `TestSellingNamesQtrSecondaryDemos`, `TestDaypartsByQuarterNormalization` |

Tests that depend on these files will be skipped automatically when the files are absent.
