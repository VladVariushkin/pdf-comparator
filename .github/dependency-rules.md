# Dependency & Performance Rules

## Dependency Overview

### Core Dependencies

| Package | Purpose | Version | Notes |
|---------|---------|---------|-------|
| `streamlit` | UI framework | >=1.33 | Main entry point via `streamlit run app.py` |
| `openai` | LLM client | >=1.30 | Azure OpenAI integration (structured outputs) |
| `pdfplumber` | Text extraction | >=0.11 | Reads PDF text and structure |
| `camelot-py[cv]` | Table detection | >=1.0 | Requires `opencv` (cv extra) for image processing |
| `pandas` | Data manipulation | >=2.0 | DataFrame conversion and operations |
| `openpyxl` | Excel generation | >=3.1 | Creates XLSX reports in `report_builder.py` |
| `pytest` | Testing | >=7.0 | Unit test framework |
| `python-dotenv` | Config loading | >=1.0 | Loads `.env` file |
| `python-dateutil` | Date parsing | >=2.9 | Used by `validator.py` for date comparisons |

### Optional Dependencies

- **Tesseract OCR**: Required for scanned PDFs. Manual installation needed (see `.env.example`).
- **ReportLab**: Used by `generate_samples.py` to create sample PDFs (not required for main app).

### Dependency Installation

```bash
pip install -r requirements.txt
```

On Windows, if `camelot-py[cv]` fails:
1. Ensure Visual C++ build tools are installed
2. Try: `pip install camelot-py[cv] --no-cache-dir`
3. Alternative: Use conda: `conda install -c conda-forge camelot-py`

## Performance Characteristics

### Extraction Performance

| Operation | Time (approx) | Bottleneck |
|-----------|---------------|-----------|
| Text extraction (1 page) | 50-200ms | PDF parsing, font handling |
| Table extraction (1 page) | 100-500ms | Camelot lattice + stream detection |
| OCR single page (scanned) | 1-3s per page | Tesseract processing |
| Multi-page (100 pages) | 5-50s | Linear scaling with page count |

**Optimization**: For PDFs >50 pages, consider splitting or caching extractions.

### LLM Performance

| Operation | Time (approx) | Bottleneck |
|-----------|---|---|
| Structured field extraction | 2-5s | API latency + token processing |
| Free-form comparison | 3-8s | Token count (more text = slower) |
| Validation checks | 1-2s | Per-document processing |

**Optimization**: Reduce field count or text length to speed up LLM calls.

### Parallel Processing

Current implementation uses `ThreadPoolExecutor` with `max_workers=n_pairs` (app.py line 205).

**Scaling**:
- 2 PDF pairs: ~2x faster than sequential
- 10 PDF pairs: 6-8x faster (diminishing returns due to API rate limits)
- 50+ pairs: Risk of API throttling; consider batching or queuing

**Recommendation**: For > 20 pairs, implement queue-based processing with backoff.

## Memory Usage

### Per-PDF Memory Footprint

- **Small PDF** (< 5MB, 10 pages): ~50MB RAM
- **Medium PDF** (5-50MB, 50-100 pages): ~200MB RAM
- **Large PDF** (> 50MB): Potential for 500MB+ RAM

**Issue**: Streamlit loads entire file in memory. No streaming support.

**Workaround**: For very large PDFs, split into chunks before upload.

### Concurrent Uploads

Parallel extraction of N PDFs can use N × PDF_size memory. With `max_workers=N`, monitor RAM.

**Limit**: On typical machines, safe to process 3-5 large PDFs in parallel.

## Dependency Maintenance

### Regular Updates

Check for security updates:
```bash
pip install --upgrade --dry-run -r requirements.txt
pip install --upgrade -r requirements.txt
```

**Critical updates**: `openai` (API compatibility), `pdfplumber` (PDF standard changes).

### Pinning Versions

Current `requirements.txt` uses `>=` constraints (minimum versions). For production, consider pinning:
```
streamlit==1.33.0
openai==1.30.0
...
```

### Testing After Updates

After updating dependencies, always run:
```bash
pytest tests/
```

Especially important for:
- `pandas` (DataFrame API changes)
- `camelot-py` (extraction behavior)
- `openai` (SDK breaking changes)

## Dependency Conflicts

### Known Issues

- **`camelot-py` on Windows**: Requires Visual C++ build tools
- **`opencv` (camelot dependency)**: Large binary, increases install size
- **`pandas` + old NumPy**: Can cause import errors; ensure `numpy>=1.21`

### Workarounds

```bash
# If camelot installation fails:
pip install --no-binary opencv-python opencv-python

# If pandas import fails:
pip uninstall numpy && pip install numpy==1.24.0

# Clean install if stuck:
rm -r venv && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt
```

## Development Dependencies

For local development, consider adding:
```
pytest-cov        # Coverage reports
black             # Code formatting
flake8            # Linting
mypy              # Type checking
```

Add to `requirements-dev.txt` and install with:
```bash
pip install -r requirements.txt -r requirements-dev.txt
```

## CI/CD & Deployment

### Docker / Containers

For deployment, create `requirements-lock.txt` with pinned versions:
```bash
pip freeze > requirements-lock.txt
```

Use in Dockerfile:
```dockerfile
RUN pip install -r requirements-lock.txt
```

### Environment Variables

Production must set:
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT`

Never commit `.env` file. Use secrets management (e.g., GitHub Secrets, Azure Key Vault).
