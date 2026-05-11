import json
from unittest.mock import MagicMock, patch


def test_task_args_contain_no_binary():
    """compare_pair task args must be JSON-serializable scalars — no file bytes."""
    args = ["test-job-123", 0, "file_a.pdf", "file_b.pdf", "Auto-detect"]
    assert json.loads(json.dumps(args)) == args


def test_compare_pair_reads_bytes_from_redis():
    """compare_pair fetches file bytes from Redis using the standard key pattern."""
    from tasks import compare_pair

    bytes_a = b"%PDF-1.4 file_a"
    bytes_b = b"%PDF-1.4 file_b"

    mock_bin = MagicMock()
    mock_bin.getdel.side_effect = [bytes_a, bytes_b]
    mock_str = MagicMock()

    with patch("tasks._redis_bin", mock_bin), \
         patch("tasks._redis", mock_str), \
         patch("tasks.evaluate_pair", return_value=(None, 1.5, "test error")) as mock_eval:
        compare_pair("job-1", 2, "a.pdf", "b.pdf", "Auto-detect")

    mock_bin.getdel.assert_any_call("job:job-1:f:2:a")
    mock_bin.getdel.assert_any_call("job:job-1:f:2:b")
    mock_eval.assert_called_once_with("a.pdf", bytes_a, "b.pdf", bytes_b, "Auto-detect")


def test_compare_pair_handles_missing_bytes():
    """compare_pair writes an error result when file keys have expired."""
    from tasks import compare_pair

    mock_bin = MagicMock()
    mock_bin.getdel.return_value = None
    mock_str = MagicMock()

    with patch("tasks._redis_bin", mock_bin), \
         patch("tasks._redis", mock_str), \
         patch("tasks.evaluate_pair") as mock_eval:
        compare_pair("job-1", 0, "a.pdf", "b.pdf", "Auto-detect")

    mock_eval.assert_not_called()
    payload = json.loads(mock_str.setex.call_args[0][2])
    assert payload["error"] is not None
    assert payload["raw"] is None
