# PDF Extraction Rules

## Overview

The extraction pipeline uses `pdfplumber` for text and `camelot` for table detection. Understanding these tools' behavior is critical for maintaining extraction quality.

## Table Extraction Strategy

### Two-Pass Lattice/Stream Detection

`services/extractor.py` uses adaptive extraction:

1. **Lattice flavor** (line-based) first - detects tables with visible grid lines
   - Good for: Structured tables with borders
   - Accuracy threshold: 50% (see line 36)
2. **Stream flavor** (heuristic) fallback - detects tables by cell proximity
   - Good for: Borderless or sparse tables
   - Used when lattice accuracy < 50%

**Implication**: If a table is missed, it's likely neither flavor detected it. Verify it's actually a table (cell-based layout) and not prose columns.

### Page-by-Page Processing

Tables are extracted per-page (line 34). This enables:
- Accurate page numbering in UI results
- Parallel processing of large PDFs
- But: Tables spanning multiple pages are split

**Workaround**: For multi-page tables, post-merge in `table_parser.py` if needed.

### DataFrame Conversion

`camelot` returns pandas DataFrames. `_df_to_markdown()` converts to text sections for LLM processing.

**Key point**: Cell content is stringified with newlines preserved. If a cell contains formatted text (bold, italics), they're lost in the conversion.

## Text Extraction Strategy

### Section-Based Output

Text is extracted per-page with table content included (line 47-50 of extractor.py). Returns list of text sections:
- Each section is a page or logical block
- Tables are markdown-formatted
- Prose text is plain
- Newlines and spacing are preserved

### Fallback to OCR (Optional)

For scanned PDFs, `pdfplumber` returns minimal text. Tesseract OCR can be enabled via `TESSDATA_PREFIX` environment variable.

**Note**: Tesseract is NOT automatically installed. Windows users must download and set `TESSDATA_PREFIX` path (see `.env.example` line 10-12).

## Common Extraction Issues

### Missing Tables
- **Cause**: Camelot couldn't detect structure (borderless, very sparse, or image-based table)
- **Debug**: Check debug panel in Streamlit UI - shows parsed tables JSON
- **Fix**: Enable Tesseract for scanned PDFs, or adjust `_extract_dfs()` flavor thresholds

### Incorrect Field Names
- **Cause**: Camelot merged cells incorrectly or `_df_to_markdown()` lost formatting
- **Debug**: View "parsed tables" JSON in debug panel
- **Fix**: Pre-process PDF (normalize formatting) or adjust extraction logic in `table_parser.py`

### Duplicate Fields in Multi-Column Tables
- **Cause**: Camelot detected column headers multiple times or merged rows incorrectly
- **Debug**: Look at columnar/matrix table structure in debug output
- **Fix**: Add deduplication logic in `table_parser.py` if pattern is consistent

### Text Extraction Empty/Minimal
- **Cause**: PDF is scanned image or uses embedded fonts poorly
- **Debug**: Check extracted text in LLM modes' debug panel
- **Fix**: Enable Tesseract or ask user for better-quality PDFs

## PDF Quirks to Handle

### Invisible Text (Embedded Fonts)
Some PDFs embed custom fonts that `pdfplumber` can't read. Text appears in viewer but not to extraction.
- **Workaround**: Tesseract OCR fallback

### Form Fields vs Text
Fillable PDF forms store data separately from displayed text.
- **Current behavior**: We extract displayed text only, not form field values
- **Enhancement**: Could parse form field annotations if needed

### Large PDFs (100+ pages)
- Camelot is per-page, so processing time scales linearly
- Current UI shows spinner during extraction
- **Performance**: Consider pagination for very large PDFs (>500 pages)

## Maintenance Notes

- Update extraction logic in `services/extractor.py` to tune Camelot parameters
- Modify `_df_to_markdown()` to preserve formatting (e.g., bold/italic) if needed
- If OCR becomes mandatory, add Tesseract initialization check at startup
