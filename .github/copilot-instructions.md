# Copilot Instructions for doc-compare

## Quick Start

**Run the Streamlit UI:**
```bash
streamlit run app.py
```

**Run tests:**
```bash
pytest
# Single test file:
pytest tests/test_compare_tables.py
# Single test:
pytest tests/test_compare_tables.py::TestCompareTablesKeyValue::test_identical
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

## Project Overview

**doc-compare** is a document comparison tool that analyzes PDF pairs using three strategies:

1. **Table Parser (no AI)** - Direct field comparison from parsed tables
2. **Structured Fields (LLM)** - LLM extracts known fields, then compares
3. **Free-form Text (LLM)** - LLM finds semantic differences in prose content

### Architecture

The project has a **service-oriented design**:

- **`services/`** - Business logic modules:
  - `extractor.py` - PDF text/table extraction using `pdfplumber` and `camelot`
  - `comparator.py` - Three comparison strategies with LLM integration
  - `llm_client.py` - Azure OpenAI API wrapper (Claude Sonnet 4.6)
  - `table_parser.py` - Converts extracted tables to comparable formats
  - `validator.py` - Post-comparison consistency checks (line totals, date ordering)
  - `report_builder.py` - Excel report generation for table parser results
- **`models/`** - Data models:
  - `comparison.py` - `ComparisonResult`, `FieldDiff`, `ValidationWarning` dataclasses
- **`tests/`** - Pytest suite with fixtures for mock PDFs
- **`app.py`** - Streamlit UI (main entry point)
- **`generate_samples.py`** - Script to create sample PDFs using ReportLab

### Key Design Patterns

#### Data Flow for Comparisons

1. PDF bytes → extraction (text or tables)
2. LLM extraction (structured/freeform modes only)
3. Field-by-field comparison
4. Validation warnings (e.g., line-item totals)
5. Result rendering in Streamlit

#### LLM Integration

The `LLMClient` uses **structured outputs** (JSON schema):
- `_single_extract_system` defines extraction rules (field names must be exact, no rephrase)
- `_checks_schema` defines validation check outputs (line items, date ordering, SLA consistency)
- All LLM calls are in `services/comparator.py` and `services/validator.py`

#### Table Representation

Tables are stored as dictionaries with three types:
- **key_value**: `{"type": "key_value", "title": str, "data": {field: value}}`
- **columnar**: `{"type": "columnar", "title": str, "headers": [...], "rows": [...]}`
- **matrix**: `{"type": "matrix", "title": str, "columns": [...], "rows": [...]}`

The `table_parser.py` converts `camelot` DataFrames to these formats.

#### Field Naming in Comparisons

Fields use hierarchical naming with `›` as separator:
- Key-value tables: `"TableTitle › FieldName"`
- Columnar/matrix tables: `"TableTitle › ColumnName"`

This is parsed in `app.py` line 100 to display user-friendly names.

## Configuration

Environment variables (see `.env.example`):

```
AZURE_OPENAI_ENDPOINT=...      # Azure OpenAI endpoint
AZURE_OPENAI_API_KEY=...       # API key
AZURE_OPENAI_DEPLOYMENT=...    # Deployment name (Claude Sonnet 4.6)
TESSDATA_PREFIX=...            # Optional: Tesseract OCR path (Windows scanned PDFs)
```

Load via `.env` file or set directly. Required for LLM modes.

## Common Tasks

### Adding a New Comparison Mode

1. Add strategy function to `services/comparator.py` (follow `compare_structured` pattern)
2. Update radio button in `app.py` line 21
3. Route in `_evaluate_pair` function (app.py line 186)

### Adding a New Validation Check

1. Define check in `_checks_schema` (services/comparator.py line 44+)
2. Add extraction logic to `validate()` (services/validator.py)
3. Return `ValidationWarning` objects with `rule` name matching labels in `app.py` line 60

### Extending LLM Extraction Rules

Edit the `_single_extract_system` prompt in `services/comparator.py` (line 7+). The prompt includes examples for:
- Two-column label/value tables
- Multi-column tables with row labels
- Metrics tables

### Debugging Extractions

Enable debug output in Streamlit UI (line 142). Shows:
- **Table parser**: Parsed tables as JSON
- **LLM modes**: Extracted text and LLM extraction results

### Running Tests with Coverage

```bash
pytest --cov=services --cov=models tests/
```

## Conventions

- **Imports**: Service modules use lazy imports for heavy dependencies (e.g., `camelot`, `pdfplumber`)
- **Error Handling**: Extraction failures return empty lists/None; handled gracefully in UI
- **Field Names**: Exact as they appear in documents (no normalization)
- **Parallel Processing**: Multiple PDF pairs use `ThreadPoolExecutor` (app.py line 205)
- **Timestamps**: `ComparisonResult` includes elapsed time for performance tracking

## Related Documentation

For deeper guidance on specific areas, see:

- **[pdf-extraction-rules.md]** - PDF extraction strategies, table detection, handling scanned PDFs, common extraction issues
- **[debugging-rules.md]** - Debugging workflow, common scenarios, performance profiling, testing with sample PDFs
- **[dependency-rules.md]** - Dependency overview, performance characteristics, memory usage, maintenance guidance
