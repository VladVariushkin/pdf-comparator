import json
import uuid
from collections import Counter
from dataclasses import asdict

import redis as _redis_lib
from celery.app.control import Control
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from config import CELERY_QUEUE, JOB_TTL, MAX_QUEUE_DEPTH, MAX_UPLOAD_BYTES, REDIS_URL
from models.modes import AUTO_DETECT
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
from services.job_store import RedisJobStore
from services.pairer import pair_by_name
from services.report_builder import build_excel_report
from tasks import celery_app, compare_pair

app = FastAPI(title="Doc Comparator", version="1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

_redis = _redis_lib.from_url(REDIS_URL, decode_responses=True)
_redis_bin = _redis_lib.from_url(REDIS_URL, decode_responses=False)
_store = RedisJobStore(_redis, JOB_TTL)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _to_comparison_out(result: ComparisonResult) -> ComparisonOut:
    count = Counter(d.status for d in result.diffs)
    return ComparisonOut(
        mode=result.mode,
        summary=result.summary,
        diffs=[FieldDiffOut.model_validate(asdict(d)) for d in result.diffs],
        missing_tables=[MissingTableOut(**m) for m in result.missing_tables],
        table_order=result.table_order,
        table_subtitles=result.table_subtitles,
        warnings=[WarningOut.model_validate(asdict(w)) for w in result.warnings],
        counts=CountsOut(
            match=count["match"],
            mismatch=count["mismatch"],
            formula_mismatch=count["formula_mismatch"],
            only_in_a=count["only_in_a"],
            only_in_b=count["only_in_b"],
            missing_tables=len(result.missing_tables),
        ),
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
# Upload helper
# ---------------------------------------------------------------------------

async def _read_limited(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(65536):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            mb = MAX_UPLOAD_BYTES // (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"{upload.filename!r} exceeds the {mb} MB upload limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# Harvest — mark job done once all result keys are present
# ---------------------------------------------------------------------------

def _pending_pair(pair_meta: dict) -> PairResultOut:
    return PairResultOut(name_a=pair_meta["name_a"], name_b=pair_meta["name_b"], elapsed=0.0)


def _harvest(job_id: str, data: dict) -> None:
    if data["status"] == "done":
        return
    n = len(data["pairs"])
    if all(_store.get_result(job_id, i) is not None for i in range(n)):
        data["status"] = "done"
        _store.set(job_id, data)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "jobs": _store.count()}


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
    file_type_mode: str = Form(AUTO_DETECT),
) -> JobSubmitOut:
    if len(files_a) != len(files_b):
        raise HTTPException(
            status_code=422,
            detail=f"files_a ({len(files_a)}) and files_b ({len(files_b)}) must have equal counts.",
        )

    depth = _redis.llen(CELERY_QUEUE)
    if depth >= MAX_QUEUE_DEPTH:
        raise HTTPException(
            status_code=429,
            detail=f"Server is busy — {depth} tasks already queued. Please wait a moment and try again.",
        )

    n = len(files_a)
    job_id = str(uuid.uuid4())
    pairs = []
    task_ids = []

    for i in range(n):
        ba = await _read_limited(files_a[i])
        bb = await _read_limited(files_b[i])
        na = files_a[i].filename or f"file_a_{i}"
        nb = files_b[i].filename or f"file_b_{i}"
        pairs.append({"name_a": na, "name_b": nb})
        _redis_bin.setex(f"job:{job_id}:f:{i}:a", JOB_TTL, ba)
        _redis_bin.setex(f"job:{job_id}:f:{i}:b", JOB_TTL, bb)
        task = compare_pair.delay(job_id, i, na, nb, file_type_mode)
        task_ids.append(task.id)

    _store.set(job_id, {
        "job_id": job_id,
        "status": "running",
        "pairs": pairs,
        "task_ids": task_ids,
    })

    return JobSubmitOut(job_id=job_id, n_pairs=n)


@app.get("/jobs/{job_id}", response_model=JobStatusOut)
def get_job(job_id: str) -> JobStatusOut:
    data = _store.get(job_id)
    if not data:
        raise HTTPException(status_code=404, detail="Job not found")
    _harvest(job_id, data)

    pairs_out = []
    done = 0
    for i, pair_meta in enumerate(data["pairs"]):
        payload = _store.get_result(job_id, i)
        if payload is None:
            pairs_out.append(_pending_pair(pair_meta))
        else:
            result = _deserialize_result(payload.get("raw"))
            pairs_out.append(PairResultOut(
                name_a=pair_meta["name_a"],
                name_b=pair_meta["name_b"],
                elapsed=payload["elapsed"],
                error=payload.get("error"),
                comparison=_to_comparison_out(result) if result else None,
            ))
            done += 1

    return JobStatusOut(
        job_id=job_id,
        status=data["status"],
        done=done,
        total=len(data["pairs"]),
        pairs=pairs_out,
    )


@app.post("/jobs/{job_id}/cancel", status_code=204)
@app.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str) -> None:
    data = _store.get(job_id)
    if data:
        task_ids = data.get("task_ids", [])
        if task_ids:
            Control(celery_app).revoke(task_ids, terminate=True)
        for i in range(len(data["pairs"])):
            _redis_bin.delete(f"job:{job_id}:f:{i}:a", f"job:{job_id}:f:{i}:b")
            _redis.delete(f"job:{job_id}:r:{i}")
    _store.delete(job_id)


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
    data = _store.get(job_id)
    if not data:
        raise HTTPException(status_code=404, detail="Job not found")
    _harvest(job_id, data)

    if data["status"] != "done":
        raise HTTPException(status_code=409, detail="Job not yet complete")

    pairs = []
    for i, pair_meta in enumerate(data["pairs"]):
        payload = _store.get_result(job_id, i)
        if payload and payload.get("raw") and payload["raw"].get("mode") == "table_parser":
            pairs.append((
                _deserialize_result(payload["raw"]),
                pair_meta["name_a"],
                pair_meta["name_b"],
            ))
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
