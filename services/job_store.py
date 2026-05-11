import json


class RedisJobStore:
    def __init__(self, redis_client, ttl: int) -> None:
        self._r = redis_client
        self._ttl = ttl

    def set(self, job_id: str, data: dict) -> None:
        self._r.setex(f"job:{job_id}", self._ttl, json.dumps(data))

    def get(self, job_id: str) -> dict | None:
        raw = self._r.get(f"job:{job_id}")
        return json.loads(raw) if raw else None

    def delete(self, job_id: str) -> None:
        self._r.delete(f"job:{job_id}")

    def get_result(self, job_id: str, idx: int) -> dict | None:
        raw = self._r.get(f"job:{job_id}:r:{idx}")
        return json.loads(raw) if raw else None

    def count(self) -> int:
        return sum(1 for k in self._r.scan_iter("job:*") if ":" not in k[4:])
