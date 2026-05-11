import time

from models.comparison import ComparisonResult
from models.modes import AUTO_DETECT, EXCEL_TYPE
from services import excel_extractor as _excel_extractor
from services import extractor as _pdf_extractor
from services.comparator import compare_tables


def detect_file_type(filename: str) -> str:
    """Returns 'pdf' | 'excel' | 'unknown'."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith((".xlsx", ".xls")):
        return "excel"
    return "unknown"


def evaluate_pair(
    name_a: str,
    bytes_a: bytes,
    name_b: str,
    bytes_b: bytes,
    file_type_mode: str,
) -> tuple[ComparisonResult | None, float, str | None]:
    """Orchestrate extraction + comparison for one document pair.

    Returns (result, elapsed_seconds, error_message).
    result is None when error_message is set.
    Never raises — all exceptions are caught and returned as error strings.
    """
    try:
        t0 = time.perf_counter()

        if file_type_mode == AUTO_DETECT:
            type_a = detect_file_type(name_a)
            type_b = detect_file_type(name_b)
            if type_a != type_b:
                return None, 0, (
                    f"Mixed file types: {name_a} is {type_a}, {name_b} is {type_b}. "
                    "Both files must be the same type."
                )
            file_type = type_a
        elif file_type_mode == EXCEL_TYPE:
            file_type = "excel"
        else:
            file_type = "pdf"

        extractor = _excel_extractor if file_type == "excel" else _pdf_extractor
        tables_a = extractor.extract_as_tables(bytes_a, name_a)
        del bytes_a
        tables_b = extractor.extract_as_tables(bytes_b, name_b)
        del bytes_b
        if not tables_a or not tables_b:
            return None, 0, "Could not extract tables from one or both documents."
        result = compare_tables(tables_a, tables_b)

        return result, time.perf_counter() - t0, None

    except MemoryError:
        return None, 0, (
            "Out of memory — files are too large to process. "
            "Try uploading smaller files or processing one pair at a time."
        )
    except ValueError as exc:
        return None, 0, str(exc)
    except Exception as exc:
        return None, 0, f"Error processing pair: {exc}"
