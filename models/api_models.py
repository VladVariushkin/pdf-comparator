from __future__ import annotations

from pydantic import BaseModel


class FieldDiffOut(BaseModel):
    field: str        # e.g. "Revenue Table › Q1 › Net Revenue"
    table: str        # table title; empty string for non-table modes
    page: int         # PDF page or Excel sheet index; 0 = unknown
    value_a: str | None
    value_b: str | None
    status: str       # "match"|"mismatch"|"formula_mismatch"|"only_in_a"|"only_in_b"
    formula_a: str | None = None
    formula_b: str | None = None


class MissingTableOut(BaseModel):
    title: str
    missing_from: str     # "A" or "B"
    page: int | None = None


class WarningOut(BaseModel):
    document: str     # "A" or "B"
    rule: str         # "line_item_total"|"date_ordering"|"duplicate_rows"|"duplicate_columns"
    detail: str


class CountsOut(BaseModel):
    match: int
    mismatch: int
    formula_mismatch: int
    only_in_a: int
    only_in_b: int
    missing_tables: int


class ComparisonOut(BaseModel):
    mode: str                          # "table_parser"|"structured"|"freeform"
    summary: str
    diffs: list[FieldDiffOut]
    missing_tables: list[MissingTableOut]
    table_order: list[str]
    table_subtitles: dict[str, str]
    warnings: list[WarningOut]
    counts: CountsOut


class PairResultOut(BaseModel):
    name_a: str
    name_b: str
    elapsed: float
    error: str | None = None
    comparison: ComparisonOut | None = None


class JobSubmitOut(BaseModel):
    job_id: str
    n_pairs: int


class JobStatusOut(BaseModel):
    job_id: str
    status: str       # "running" | "done"
    done: int
    total: int
    pairs: list[PairResultOut]


class PairPreviewIn(BaseModel):
    filenames: list[str]


class FilePairOut(BaseModel):
    before: str
    after: str


class PairPreviewOut(BaseModel):
    pairs: list[FilePairOut]
    unmatched: list[str]
