import json
from unittest.mock import MagicMock

import pytest

from services.job_store import RedisJobStore


@pytest.fixture
def redis_mock():
    return MagicMock()


@pytest.fixture
def store(redis_mock):
    return RedisJobStore(redis_mock, ttl=600)


def test_set_serialises_to_json(store, redis_mock):
    store.set("j1", {"status": "running"})
    redis_mock.setex.assert_called_once_with("job:j1", 600, json.dumps({"status": "running"}))


def test_get_deserialises_json(store, redis_mock):
    redis_mock.get.return_value = json.dumps({"status": "running"})
    assert store.get("j1") == {"status": "running"}
    redis_mock.get.assert_called_once_with("job:j1")


def test_get_missing_returns_none(store, redis_mock):
    redis_mock.get.return_value = None
    assert store.get("nonexistent") is None


def test_delete_calls_redis(store, redis_mock):
    store.delete("j1")
    redis_mock.delete.assert_called_once_with("job:j1")


def test_get_result_reads_without_deleting(store, redis_mock):
    redis_mock.get.return_value = json.dumps({"elapsed": 1.2, "raw": None})
    result = store.get_result("j1", 0)
    assert result == {"elapsed": 1.2, "raw": None}
    redis_mock.get.assert_called_with("job:j1:r:0")
    redis_mock.delete.assert_not_called()


def test_get_result_missing_returns_none(store, redis_mock):
    redis_mock.get.return_value = None
    assert store.get_result("j1", 0) is None


def test_count_excludes_result_keys(store, redis_mock):
    # metadata key has no colon after "job:", result keys do
    redis_mock.scan_iter.return_value = [
        "job:abc123",
        "job:abc123:r:0",
        "job:abc123:r:1",
        "job:def456",
    ]
    assert store.count() == 2
