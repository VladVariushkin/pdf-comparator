import json
from dataclasses import asdict

import redis as _redis_lib
from celery import Celery

from config import JOB_TTL, REDIS_URL, TASK_TIMEOUT
from services.evaluator import evaluate_pair

celery_app = Celery("comparator", broker=REDIS_URL)
# No result backend — tasks write directly to the job store in Redis.

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=TASK_TIMEOUT - 30,  # SIGTERM with 30s grace
    task_time_limit=TASK_TIMEOUT,             # SIGKILL if still alive
)

_redis = _redis_lib.from_url(REDIS_URL, decode_responses=True)
_redis_bin = _redis_lib.from_url(REDIS_URL, decode_responses=False)


@celery_app.task(name="tasks.compare_pair")
def compare_pair(
    job_id: str, pair_idx: int,
    name_a: str, name_b: str,
    file_type_mode: str,
) -> None:
    bytes_a = _redis_bin.getdel(f"job:{job_id}:f:{pair_idx}:a")
    bytes_b = _redis_bin.getdel(f"job:{job_id}:f:{pair_idx}:b")
    if bytes_a is None or bytes_b is None:
        payload = json.dumps({"elapsed": 0, "error": "File data not found — job may have expired.", "raw": None})
        _redis.setex(f"job:{job_id}:r:{pair_idx}", JOB_TTL, payload)
        return
    result, elapsed, error = evaluate_pair(name_a, bytes_a, name_b, bytes_b, file_type_mode)
    payload = json.dumps({
        "elapsed": elapsed,
        "error": error,
        "raw": asdict(result) if result else None,
    })
    _redis.setex(f"job:{job_id}:r:{pair_idx}", JOB_TTL, payload)
