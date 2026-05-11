import io
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def test_health_returns_ok():
    import api
    client = TestClient(api.app)
    with patch.object(api, "_store") as mock_store:
        mock_store.count.return_value = 0
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_submit_job_422_on_file_count_mismatch():
    import api
    client = TestClient(api.app)
    mock_redis = MagicMock(**{"llen.return_value": 0})
    with patch.object(api, "_redis", mock_redis):
        resp = client.post(
            "/jobs",
            files=[
                ("files_a", ("a1.pdf", io.BytesIO(b"%PDF"), "application/pdf")),
                ("files_a", ("a2.pdf", io.BytesIO(b"%PDF"), "application/pdf")),
                ("files_b", ("b.pdf", io.BytesIO(b"%PDF"), "application/pdf")),
            ],
        )
    assert resp.status_code == 422


def test_get_job_404_when_not_found():
    import api
    client = TestClient(api.app)
    with patch.object(api, "_store") as mock_store:
        mock_store.get.return_value = None
        resp = client.get("/jobs/nonexistent-id")
    assert resp.status_code == 404
