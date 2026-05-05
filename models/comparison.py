from dataclasses import dataclass, field


@dataclass
class FieldDiff:
    field: str
    value_a: str | None
    value_b: str | None
    status: str   # "match" | "mismatch" | "formula_mismatch" | "only_in_a" | "only_in_b"
    table: str = ""   # table title this diff belongs to (table_parser mode)
    page: int = 0     # PDF page or Excel sheet the table appeared on
    formula_a: str | None = None  # Excel formula in doc A (if formula_mismatch)
    formula_b: str | None = None  # Excel formula in doc B (if formula_mismatch)


@dataclass
class ValidationWarning:
    document: str   # "A" or "B"
    rule: str       # "line_item_total" | "date_ordering" | "sla_consistency"
    detail: str


@dataclass
class ComparisonResult:
    mode: str  # "structured" | "freeform" | "table_parser"
    diffs: list[FieldDiff] = field(default_factory=list)
    missing_tables: list[dict] = field(default_factory=list)   # [{"title": str, "missing_from": "A"|"B", "page": int}]
    table_order: list[str] = field(default_factory=list)       # table titles in PDF order (table_parser mode)
    table_subtitles: dict = field(default_factory=dict)        # {table_title: subtitle_string}
    summary: str = ""
    warnings: list[ValidationWarning] = field(default_factory=list)
    debug: dict = field(default_factory=dict)
