# Debugging & Troubleshooting Rules

## Debugging Workflow

### 1. Enable Streamlit Debug Panel

In the UI, after running a comparison, expand the "Debug info" section (bottom of results). This shows:
- **Table parser mode**: Parsed tables as JSON for both documents
- **LLM modes**: Raw extracted text and LLM extraction results

Use this to identify where differences occur (extraction vs. comparison vs. validation).

### 2. Inspect Raw Extractions

**For table issues**:
- Look at `tables_a` and `tables_b` JSON to see table structure, titles, and content
- Check if expected tables appear in parsed output
- Verify field names match exactly

**For text issues**:
- Look at `text_a` and `text_b` to see what text was passed to LLM
- Check if critical content is present in extracted text
- Note: LLM extraction can infer/hallucinate, so check `extracted_a` vs `extracted_b`

### 3. Add Print Debugging

Insert print statements in `services/` modules:
```python
print(f"DEBUG: Extracted {len(tables)} tables from page {page_num}")
print(f"DEBUG: Field '{field_name}' = {value}")
```
These appear in terminal where `streamlit run app.py` is running.

### 4. Unit Test Specific Cases

Write a pytest test in `tests/` to isolate the issue:
```python
def test_my_pdf_case():
    # Load test PDF or mock data
    result = compare_tables([table_a], [table_b])
    assert result.diffs[0].field == "expected_field"
```

Run with: `pytest tests/test_file.py::test_my_pdf_case -v`

## Common Debugging Scenarios

### "No field failures" but visually different PDFs

**Possible causes**:
1. Fields matched but values are semantically similar (LLM modes only)
2. Comparison ignores prose text outside tables (table parser mode)
3. Fields are renamed in one document

**Debug**: Enable debug panel, compare `extracted_a` vs `extracted_b` (LLM modes)

### Some tables missing from results

**Check**:
1. Did extraction miss the table? (Look at `tables_a`/`tables_b` in debug)
2. Is the table present but has different title? (Field naming uses titles)
3. Is the table a matrix vs columnar mismatch? (Affects comparison logic)

**Fix**: If table structure is valid but unrecognized, adjust `_extract_dfs()` flavor thresholds in `extractor.py`

### LLM extraction returning wrong fields

**Possible causes**:
1. Field names in document don't match extraction prompt rules
2. LLM hallucinating fields not in document
3. Prompt ambiguity (two tables with same title)

**Debug**:
- Check extracted text (`text_a`, `text_b`) to verify content passed to LLM
- Check LLM response (`extracted_a`, `extracted_b`) to see what LLM returned
- Review extraction rules in `_single_extract_system` (services/comparator.py line 7)

**Fix**: Update prompt examples or add table title prefixes to distinguish tables

### Parallel processing hangs or crashes

**Cause**: Likely PDF extraction issue or LLM timeout

**Debug**:
1. Run same PDFs with `n_pairs=1` (upload same file twice)
2. If single pair works, issue is parallelization
3. If single pair fails, issue is extraction or LLM

**Fix**:
- Increase LLM timeout in `LLMClient` (llm_client.py)
- Reduce `max_workers` in ThreadPoolExecutor (app.py line 205)
- Check `.env` for correct LLM credentials

## Performance Debugging

### Slow PDF extraction

**Profile** by adding timing:
```python
import time
t0 = time.perf_counter()
tables = extract_as_tables(pdf_bytes)
print(f"Extraction took {time.perf_counter() - t0:.2f}s")
```

**Common causes**:
- Large PDF (100+ pages) - Camelot checks every page
- Complex tables - Camelot tries both lattice and stream
- Scanned PDF with OCR enabled - Tesseract is slow

**Optimization**:
- Increase Camelot thresholds to skip stream flavor more often
- Disable OCR for known text PDFs
- Process pages in parallel (requires refactoring)

### Slow LLM comparison

**Cause**: API latency or token processing time

**Debug**:
- Check Azure OpenAI usage dashboard
- Compare with baseline (same PDFs on different day)
- Check network latency to `AZURE_OPENAI_ENDPOINT`

**Optimization**:
- Reduce field extraction scope (fewer fields = fewer tokens)
- Batch extractions in single LLM call vs separate calls

## Logging and Error Messages

### Enable More Verbose Logging

Edit `services/llm_client.py` to add:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

This enables Azure SDK debug logs (helpful for API issues).

### Understand Error Messages

| Error | Likely Cause | Action |
|-------|--------------|--------|
| "Could not extract tables" | No tables found or extraction failed | Check debug panel, verify PDF has tables |
| "Could not extract text" | Empty PDF or unsupported format | Verify PDF, enable OCR if scanned |
| "API timeout" | LLM request took >30s | Check network, increase timeout |
| "Invalid API key" | `.env` not loaded or wrong key | Verify `.env.example`, set env vars |

## Testing with Sample PDFs

### Generate Test Samples

```bash
python generate_samples.py
```

This creates PDFs in `samples/` directory with known content. Use for:
- Testing extraction consistency
- Benchmarking performance
- Creating regression tests

### Add Test Fixtures

Store PDF bytes in `tests/fixtures/` and reference in tests:
```python
with open("tests/fixtures/sample.pdf", "rb") as f:
    pdf_bytes = f.read()
result = compare_tables(extract_as_tables(pdf_bytes), ...)
```
