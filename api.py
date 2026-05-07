import json
import os
import threading
import time
import uuid
from dataclasses import asdict

from celery.app.control import Control
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from models.api_models import (
    ComparisonOut,
    CountsOut,
    FieldDiffOut,
    FilePairOut,
    JobStatusOut,
    JobSubmitOut,
    MissingTableOut,
    PairPreviewIn,
    PairPreviewOut,
    PairResultOut,
    WarningOut,
)
from models.comparison import ComparisonResult, FieldDiff, ValidationWarning
from services.pairer import pair_by_name
from tasks import celery_app, compare_pair

app = FastAPI(title="Doc Comparator", version="1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

REDIS_URL = os.getenv("REDIS_URL")
JOB_TTL = int(os.getenv("JOB_TTL_SECONDS", "600"))
MAX_QUEUE_DEPTH = int(os.getenv("MAX_QUEUE_DEPTH", "20"))


# ---------------------------------------------------------------------------
# Job store — Redis if REDIS_URL is set, otherwise in-memory with TTL cleanup
# ---------------------------------------------------------------------------

if REDIS_URL:
    import redis as _redis_lib
    _redis = _redis_lib.from_url(REDIS_URL, decode_responses=True)

    def _store_set(job_id: str, data: dict) -> None:
        _redis.setex(f"job:{job_id}", JOB_TTL, json.dumps(data))

    def _store_get(job_id: str) -> dict | None:
        raw = _redis.get(f"job:{job_id}")
        return json.loads(raw) if raw else None

    def _store_delete(job_id: str) -> None:
        _redis.delete(f"job:{job_id}")

    def _store_get_result(job_id: str, idx: int) -> dict | None:
        raw = _redis.getdel(f"job:{job_id}:r:{idx}")
        return json.loads(raw) if raw else None

    def _store_count() -> int:
        return len(_redis.keys("job:*"))

else:
    _mem_store: dict[str, tuple[dict, float]] = {}

    def _store_set(job_id: str, data: dict) -> None:
        _mem_store[job_id] = (data, time.time() + JOB_TTL)

    def _store_get(job_id: str) -> dict | None:
        entry = _mem_store.get(job_id)
        if not entry:
            return None
        data, expires_at = entry
        if time.time() > expires_at:
            _mem_store.pop(job_id, None)
            return None
        return data

    def _store_delete(job_id: str) -> None:
        _mem_store.pop(job_id, None)

    def _store_get_result(job_id: str, idx: int) -> dict | None:
        return None  # Celery requires Redis; not supported in memory-only mode

    def _store_count() -> int:
        return len(_mem_store)

    def _cleanup_loop() -> None:
        while True:
            time.sleep(300)
            now = time.time()
            stale = [jid for jid, (_, exp) in list(_mem_store.items()) if now > exp]
            for jid in stale:
                _mem_store.pop(jid, None)

    threading.Thread(target=_cleanup_loop, daemon=True).start()


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _to_comparison_out(result: ComparisonResult) -> ComparisonOut:
    diffs = [
        FieldDiffOut(
            field=d.field, table=d.table, page=d.page,
            value_a=d.value_a, value_b=d.value_b, status=d.status,
            formula_a=d.formula_a, formula_b=d.formula_b,
        )
        for d in result.diffs
    ]
    missing = [
        MissingTableOut(title=m["title"], missing_from=m["missing_from"], page=m.get("page"))
        for m in result.missing_tables
    ]
    warnings = [
        WarningOut(document=w.document, rule=w.rule, detail=w.detail)
        for w in result.warnings
    ]
    counts = CountsOut(
        match=sum(1 for d in result.diffs if d.status == "match"),
        mismatch=sum(1 for d in result.diffs if d.status == "mismatch"),
        formula_mismatch=sum(1 for d in result.diffs if d.status == "formula_mismatch"),
        only_in_a=sum(1 for d in result.diffs if d.status == "only_in_a"),
        only_in_b=sum(1 for d in result.diffs if d.status == "only_in_b"),
        missing_tables=len(result.missing_tables),
    )
    return ComparisonOut(
        mode=result.mode, summary=result.summary,
        diffs=diffs, missing_tables=missing,
        table_order=result.table_order, table_subtitles=result.table_subtitles,
        warnings=warnings, counts=counts,
    )


def _deserialize_result(data: dict | None) -> ComparisonResult | None:
    if not data:
        return None
    return ComparisonResult(
        mode=data["mode"],
        diffs=[FieldDiff(**d) for d in data.get("diffs", [])],
        missing_tables=data.get("missing_tables", []),
        table_order=data.get("table_order", []),
        table_subtitles=data.get("table_subtitles", {}),
        summary=data.get("summary", ""),
        warnings=[ValidationWarning(**w) for w in data.get("warnings", [])],
        debug=data.get("debug", {}),
    )


# ---------------------------------------------------------------------------
# Harvest — pull completed Celery task results into the job store
# ---------------------------------------------------------------------------

def _harvest(job_id: str) -> None:
    data = _store_get(job_id)
    if not data or data["status"] == "done":
        return

    updated = False
    for idx in range(len(data["pairs"])):
        if data["results"][idx] is not None:
            continue
        payload = _store_get_result(job_id, idx)
        if payload is None:
            continue

        result = _deserialize_result(payload.get("raw"))
        pair = data["pairs"][idx]
        data["results"][idx] = PairResultOut(
            name_a=pair["name_a"],
            name_b=pair["name_b"],
            elapsed=payload["elapsed"],
            error=payload.get("error"),
            comparison=_to_comparison_out(result) if result else None,
        ).model_dump()
        data["raw_results"][idx] = payload.get("raw")
        updated = True

    if updated:
        done = sum(1 for r in data["results"] if r is not None)
        data["status"] = "done" if done == len(data["results"]) else "running"
        _store_set(job_id, data)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "store": "redis" if REDIS_URL else "memory",
        "jobs": _store_count(),
    }


@app.get("/")
def root() -> FileResponse:
    return FileResponse("static/index.html")


@app.post("/pair-preview", response_model=PairPreviewOut)
def pair_preview(body: PairPreviewIn) -> PairPreviewOut:
    pairs, unmatched = pair_by_name(body.filenames)
    return PairPreviewOut(
        pairs=[FilePairOut(before=b, after=a) for b, a in pairs],
        unmatched=unmatched,
    )


@app.post("/jobs", status_code=202, response_model=JobSubmitOut)
async def submit_job(
    files_a: list[UploadFile] = File(...),
    files_b: list[UploadFile] = File(...),
    mode: str = Form("Table parser (no AI)"),
    file_type_mode: str = Form("Auto-detect"),
) -> JobSubmitOut:
    if REDIS_URL:
        depth = _redis.llen("celery")
        if depth >= MAX_QUEUE_DEPTH:
            raise HTTPException(
                status_code=429,
                detail=f"Server is busy — {depth} tasks already queued. Please wait a moment and try again.",
            )

    n = min(len(files_a), len(files_b))
    job_id = str(uuid.uuid4())
    pairs = []
    task_ids = []

    for i in range(n):
        ba = await files_a[i].read()
        bb = await files_b[i].read()
        na = files_a[i].filename or f"file_a_{i}"
        nb = files_b[i].filename or f"file_b_{i}"
        pairs.append({"name_a": na, "name_b": nb})
        task = compare_pair.delay(job_id, i, na, ba, nb, bb, mode, file_type_mode)
        task_ids.append(task.id)

    _store_set(job_id, {
        "job_id": job_id,
        "status": "running",
        "pairs": pairs,
        "results": [None] * n,
        "raw_results": [None] * n,
        "task_ids": task_ids,
    })

    return JobSubmitOut(job_id=job_id, n_pairs=n)


@app.get("/jobs/{job_id}", response_model=JobStatusOut)
def get_job(job_id: str) -> JobStatusOut:
    _harvest(job_id)
    data = _store_get(job_id)
    if not data:
        raise HTTPException(status_code=404, detail="Job not found")

    done = sum(1 for r in data["results"] if r is not None)
    pairs_out = [
        PairResultOut.model_validate(r) if r else PairResultOut(
            name_a=data["pairs"][i]["name_a"],
            name_b=data["pairs"][i]["name_b"],
            elapsed=0.0,
        )
        for i, r in enumerate(data["results"])
    ]

    return JobStatusOut(
        job_id=job_id,
        status=data["status"],
        done=done,
        total=len(data["results"]),
        pairs=pairs_out,
    )


@app.post("/jobs/{job_id}/cancel", status_code=204)
@app.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str) -> None:
    data = _store_get(job_id)
    if data:
        task_ids = data.get("task_ids", [])
        if task_ids:
            Control(celery_app).revoke(task_ids, terminate=True)
    _store_delete(job_id)


@app.get(
    "/jobs/{job_id}/report",
    response_class=Response,
    responses={
        200: {
            "content": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}},
            "description": "Excel comparison report",
        },
        404: {"description": "Job not found"},
        409: {"description": "Job not yet complete"},
        422: {"description": "No table_parser results available for report"},
    },
)
def get_report(job_id: str) -> Response:
    from services.report_builder import build_excel_report

    _harvest(job_id)
    data = _store_get(job_id)
    if not data:
        raise HTTPException(status_code=404, detail="Job not found")

    if data["status"] != "done":
        raise HTTPException(status_code=409, detail="Job not yet complete")

    pairs = [
        (_deserialize_result(raw), data["pairs"][i]["name_a"], data["pairs"][i]["name_b"])
        for i, raw in enumerate(data["raw_results"])
        if raw and raw.get("mode") == "table_parser"
    ]
    if not pairs:
        raise HTTPException(
            status_code=422,
            detail="No table_parser results available. Excel reports require Table parser mode.",
        )

    excel_bytes = build_excel_report(pairs)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="comparison_report.xlsx"'},
    )
