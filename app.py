import io
import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from services.extractor import extract_as_text, extract_as_tables
from services.comparator import compare_structured, compare_freeform, compare_tables
from services.llm_client import LLMClient
from services.pairer import pair_by_name


st.set_page_config(page_title="Doc Compare", layout="wide")
st.title("Document Comparison")

mode = "Table parser (no AI)"

tab_manual, tab_bulk = st.tabs(["Manual", "Bulk"])

with tab_manual:
    col_a, col_b = st.columns(2)
    with col_a:
        files_a = st.file_uploader("Document A", type=["pdf"], accept_multiple_files=True, key="files_a")
    with col_b:
        files_b = st.file_uploader("Document B", type=["pdf"], accept_multiple_files=True, key="files_b")

    if files_a and files_b and len(files_a) != len(files_b):
        st.warning(f"Unequal number of files: {len(files_a)} in A, {len(files_b)} in B. Pairs are matched by position.")

    manual_ready = len(files_a) > 0 and len(files_b) > 0
    manual_n_pairs = min(len(files_a), len(files_b))

with tab_bulk:
    bulk_files = st.file_uploader(
        "Upload all PDFs (Before + After)",
        type=["pdf"],
        accept_multiple_files=True,
        key="bulk_files",
    )
    bulk_pairs_detected: list[tuple] = []
    bulk_unmatched: list[str] = []

    if bulk_files:
        names = [f.name for f in bulk_files]
        bulk_pairs_detected, bulk_unmatched = pair_by_name(names)

        if bulk_pairs_detected:
            st.markdown(f"**{len(bulk_pairs_detected)} pair(s) detected:**")
            st.dataframe(
                pd.DataFrame(
                    [{"#": i + 1, "Document A (Before)": a, "Document B (After)": b}
                     for i, (a, b) in enumerate(bulk_pairs_detected)]
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No pairs detected yet. Upload matching Before/After PDFs.")

        if bulk_unmatched:
            st.warning(
                "Could not pair the following files (no matching Before/After counterpart): "
                + ", ".join(bulk_unmatched)
            )

    bulk_ready = len(bulk_pairs_detected) > 0


def _render_result(result: object, elapsed: float, pair_key: str,
                   name_a: str = "Document A", name_b: str = "Document B") -> None:
    n_match          = sum(1 for d in result.diffs if d.status == "match")
    n_mismatch       = sum(1 for d in result.diffs if d.status == "mismatch")
    n_unique         = sum(1 for d in result.diffs if d.status in ("only_in_a", "only_in_b"))
    n_missing_tables = len(result.missing_tables)
    n_issues         = n_mismatch + n_unique + n_missing_tables

    caption_parts = [f"{n_match} matching", f"{n_mismatch} differing", f"{n_unique} unique to one document"]
    if n_missing_tables:
        caption_parts.append(f"{n_missing_tables} missing table(s)")
    caption_parts.append(f"completed in {elapsed:.1f}s")
    st.caption(f"{'✓' if n_issues == 0 else '!'} " + " · ".join(caption_parts))

    if result.summary:
        st.info(result.summary)

    if result.warnings:
        rule_labels = {
            "line_item_total": "Line-item total mismatch",
            "date_ordering":   "Date ordering issue",
            "duplicate_rows":    "Duplicate rows detected",
            "duplicate_columns": "Duplicate columns detected",
        }
        with st.expander(f"⚠ {len(result.warnings)} consistency warning(s)", expanded=True):
            for w in result.warnings:
                label = rule_labels.get(w.rule, w.rule)
                st.warning(f"**Document {w.document} · {label}:** {w.detail}")

    _MISSING = "— (missing)"

    if result.mode == "table_parser" and result.table_order:
        missing_by_title = {mt["title"]: mt for mt in result.missing_tables}
        diffs_by_table: dict[str, list] = {}
        for d in result.diffs:
            diffs_by_table.setdefault(d.table, []).append(d)

        for table_name in result.table_order:
            if table_name in missing_by_title:
                mt = missing_by_title[table_name]
                doc_missing = name_a if mt["missing_from"] == "A" else name_b
                doc_present = name_b if mt["missing_from"] == "A" else name_a
                page_info = f"  ·  p. {mt['page']}" if mt.get("page") else ""
                subtitle = result.table_subtitles.get(table_name, "")
                subtitle_info = f"  —  {subtitle}" if subtitle else ""
                with st.expander(f"✗  {table_name}{subtitle_info}{page_info}", expanded=True):
                    st.error(f"Present in {doc_present} — not found in {doc_missing}")
            else:
                table_diffs = diffs_by_table.get(table_name, [])
                failures = [d for d in table_diffs if d.status in ("mismatch", "only_in_a", "only_in_b")]
                matches  = [d for d in table_diffs if d.status == "match"]
                page = table_diffs[0].page if table_diffs else 0
                page_info = f"  ·  p. {page}" if page else ""
                subtitle = result.table_subtitles.get(table_name, "")
                subtitle_info = f"  —  {subtitle}" if subtitle else ""
                icon = "✓" if not failures else "✗"
                label = f"{icon}  {table_name}{subtitle_info}{page_info}  —  {len(failures)} failure(s), {len(matches)} matching"
                with st.expander(label, expanded=bool(failures)):
                    if failures:
                        st.dataframe(
                            pd.DataFrame([{
                                "Field":      d.field.split(" › ", 1)[1] if " › " in d.field else d.field,
                                "Document A": d.value_a if d.value_a is not None else _MISSING,
                                "Document B": d.value_b if d.value_b is not None else _MISSING,
                                "Issue":      f"missing in {name_b}" if d.status == "only_in_a"
                                              else f"missing in {name_a}" if d.status == "only_in_b"
                                              else "value mismatch",
                            } for d in failures]),
                            use_container_width=True, hide_index=True,
                        )
                    if not failures:
                        st.success(f"All {len(matches)} field(s) match.")
    else:
        failures = [d for d in result.diffs if d.status in ("mismatch", "only_in_a", "only_in_b")]
        matches  = [d for d in result.diffs if d.status == "match"]

        with st.expander(f"Field failures ({len(failures)})", expanded=True):
            if failures:
                st.dataframe(
                    pd.DataFrame([{
                        "Field":      d.field,
                        "Document A": d.value_a if d.value_a is not None else _MISSING,
                        "Document B": d.value_b if d.value_b is not None else _MISSING,
                        "Issue":      f"missing in {name_b}" if d.status == "only_in_a"
                                      else f"missing in {name_a}" if d.status == "only_in_b"
                                      else "value mismatch",
                    } for d in failures]),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.success("No field failures.")

        with st.expander(f"Matching fields ({len(matches)})", expanded=False):
            if matches:
                st.dataframe(pd.DataFrame([{"Field": d.field, "Value": d.value_a} for d in matches]), use_container_width=True, hide_index=True)

    if result.mode != "table_parser":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["Field", "Document A", "Document B", "Status"])
        writer.writeheader()
        writer.writerows([{"Field": d.field, "Document A": d.value_a or "", "Document B": d.value_b or "", "Status": d.status} for d in result.diffs])
        st.download_button("Download CSV", data=buf.getvalue().encode(), file_name=f"comparison_{pair_key}.csv", mime="text/csv", key=f"csv_{pair_key}")

    if result.debug:
        with st.expander("Debug info", expanded=False):
            if result.mode == "table_parser":
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Document A — parsed tables**")
                    for i, t in enumerate(result.debug.get("tables_a", [])):
                        st.markdown(f"Table {i + 1}: `{t.get('type')}` · *{t.get('title') or '(no title)'}*")
                        st.json(t)
                with c2:
                    st.markdown("**Document B — parsed tables**")
                    for i, t in enumerate(result.debug.get("tables_b", [])):
                        st.markdown(f"Table {i + 1}: `{t.get('type')}` · *{t.get('title') or '(no title)'}*")
                        st.json(t)
            else:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Document A — extracted text**")
                    st.text_area("", "\n\n".join(result.debug.get("text_a", [])), height=200, disabled=True, key=f"dbg_text_a_{pair_key}")
                    st.markdown("**Document A — LLM extraction**")
                    st.json(result.debug.get("extracted_a", {}))
                with c2:
                    st.markdown("**Document B — extracted text**")
                    st.text_area("", "\n\n".join(result.debug.get("text_b", [])), height=200, disabled=True, key=f"dbg_text_b_{pair_key}")
                    st.markdown("**Document B — LLM extraction**")
                    st.json(result.debug.get("extracted_b", {}))


def _evaluate_pair(args):
    i, name_a, bytes_a, name_b, bytes_b, mode = args
    t0 = time.perf_counter()

    if mode == "Table parser (no AI)":
        tables_a = extract_as_tables(bytes_a)
        tables_b = extract_as_tables(bytes_b)
        if not tables_a or not tables_b:
            return i, name_a, name_b, None, 0, "Could not extract tables from one or both documents."
        result = compare_tables(tables_a, tables_b)
    else:
        text_a = extract_as_text(bytes_a)
        text_b = extract_as_text(bytes_b)
        if not text_a or not text_b:
            return i, name_a, name_b, None, 0, "Could not extract text from one or both documents."
        llm = LLMClient()
        if mode == "Structured fields (LLM)":
            result = compare_structured(text_a, text_b, llm)
        else:
            result = compare_freeform(text_a, text_b, llm)

    return i, name_a, name_b, result, time.perf_counter() - t0, None


col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    run_manual = st.button("Compare", disabled=not manual_ready, type="primary", key="btn_manual")
with col_btn2:
    run_bulk = st.button("Compare Pairs", disabled=not bulk_ready, type="primary", key="btn_bulk")

if run_manual or run_bulk:
    if run_manual:
        pair_args = [
            (i, files_a[i].name, files_a[i].read(), files_b[i].name, files_b[i].read(), mode)
            for i in range(manual_n_pairs)
        ]
        n_pairs = manual_n_pairs
    else:
        file_map = {f.name: f for f in bulk_files}
        pair_args = [
            (i, a, file_map[a].read(), b, file_map[b].read(), mode)
            for i, (a, b) in enumerate(bulk_pairs_detected)
        ]
        n_pairs = len(bulk_pairs_detected)
    total_start = time.perf_counter()
    outcomes = [None] * n_pairs

    with st.spinner(f"Evaluating {n_pairs} pair(s) in parallel…"):
        with ThreadPoolExecutor(max_workers=min(n_pairs, 3)) as executor:
            futures = {executor.submit(_evaluate_pair, args): args[0] for args in pair_args}
            for future in as_completed(futures):
                i, name_a, name_b, result, elapsed, error = future.result()
                outcomes[i] = (name_a, name_b, result, elapsed, error)

    total_elapsed = time.perf_counter() - total_start

    excel_placeholder = st.empty()

    for i, (name_a, name_b, result, elapsed, error) in enumerate(outcomes):
        if n_pairs > 1:
            st.subheader(f"Pair {i + 1}: {name_a}  ↔  {name_b}")
        else:
            st.subheader(f"{name_a}  ↔  {name_b}")

        if error:
            st.error(error)
        else:
            _render_result(result, elapsed, pair_key=str(i), name_a=name_a, name_b=name_b)

        if n_pairs > 1:
            st.divider()

    if n_pairs > 1:
        st.caption(f"All {n_pairs} pairs completed in {total_elapsed:.1f}s total")

    table_pairs = [
        (result, name_a, name_b)
        for name_a, name_b, result, elapsed, error in outcomes
        if result is not None and result.mode == "table_parser"
    ]
    if table_pairs:
        from services.report_builder import build_excel_report
        excel_bytes = build_excel_report(table_pairs)
        excel_placeholder.download_button(
            "⬇ Download Excel Report",
            data=excel_bytes,
            file_name=f"comparison_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="xlsx_all",
        )
