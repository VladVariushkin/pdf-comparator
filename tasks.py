import json
import os
from dataclasses import asdict

import redis as _redis_lib
from celery import Celery

from services.evaluator import evaluate_pair

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JOB_TTL = int(os.getenv("JOB_TTL_SECONDS", "600"))

celery_app = Celery("comparator", broker=REDIS_URL)
# No result backend — tasks write directly to the job store in Redis.
TASK_TIMEOUT = int(os.getenv("TASK_TIMEOUT_SECONDS", "300"))

celery_app.conf.update(
    task_serializer="pickle",
    accept_content=["pickle"],
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=TASK_TIMEOUT - 30,  # SIGTERM with 30s grace
    task_time_limit=TASK_TIMEOUT,             # SIGKILL if still alive
)

_redis = _redis_lib.from_url(REDIS_URL, decode_responses=True)


@celery_app.task(name="tasks.compare_pair")
def compare_pair(
    job_id: str, pair_idx: int,
    name_a: str, bytes_a: bytes,
    name_b: str, bytes_b: bytes,
    mode: str, file_type_mode: str,
) -> None:
    result, elapsed, error = evaluate_pair(name_a, bytes_a, name_b, bytes_b, mode, file_type_mode)
    payload = json.dumps({
        "elapsed": elapsed,
        "error": error,
        "raw": asdict(result) if result else None,
    })
    _redis.setex(f"job:{job_id}:r:{pair_idx}", JOB_TTL, payload)
