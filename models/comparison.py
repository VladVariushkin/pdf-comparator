from dataclasses import dataclass, field
from typing import Literal


@dataclass
class FieldDiff:
    field: str
    value_a: str | None
    value_b: str | None
    status: Literal["match", "mismatch", "formula_mismatch", "only_in_a", "only_in_b"]
    table: str = ""
    page: int = 0
    formula_a: str | None = None
    formula_b: str | None = None


@dataclass
class ValidationWarning:
    document: Literal["A", "B"]
    rule: Literal["line_item_total", "date_ordering", "sla_consistency"]
    detail: str


@dataclass
class ComparisonResult:
    mode: Literal["table_parser"]
    diffs: list[FieldDiff] = field(default_factory=list)
    missing_tables: list[dict] = field(default_factory=list)   # [{"title": str, "missing_from": "A"|"B", "page": int}]
    table_order: list[str] = field(default_factory=list)       # table titles in PDF order (table_parser mode)
    table_subtitles: dict = field(default_factory=dict)        # {table_title: subtitle_string}
    summary: str = ""
    warnings: list[ValidationWarning] = field(default_factory=list)
    debug: dict = field(default_factory=dict)
