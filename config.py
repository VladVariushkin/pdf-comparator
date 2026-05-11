import os


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable '{name}' is not set.")
    return value


REDIS_URL: str = _require_env("REDIS_URL")
JOB_TTL: int = int(os.getenv("JOB_TTL_SECONDS", "600"))
MAX_QUEUE_DEPTH: int = int(os.getenv("MAX_QUEUE_DEPTH", "20"))
MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
TASK_TIMEOUT: int = int(os.getenv("TASK_TIMEOUT_SECONDS", "300"))
CELERY_QUEUE: str = os.getenv("CELERY_QUEUE", "celery")
