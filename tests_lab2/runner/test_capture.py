"""A truncated or unrelated PCAP must never count as successful evidence."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from scripts.testing.capture import verify


@pytest.mark.parametrize(
    "packets,error",
    [
        ("1\tPOST\t/api/v1/game/new\t\t\n2\t\t\t200\t1\n", None),
        ("1\tPOST\t/api/v1/game/new\t\t\n", "Incomplete capture"),
        ("1\tPOST\t/wrong\t\t\n2\t\t\t200\t1\n", "differs from replay"),
        ("1\tPOST\t/api/v1/game/new\t\t\n2\t\t\t500\t1\n", "differs from replay"),
        ("1\tPOST\t/api/v1/game/new\t\t\n2\t\t\t200\t9\n", "differs from replay"),
    ],
)
def test_capture_requires_complete_matching_exchange(tmp_path, packets, error):
    (tmp_path / "replay.jsonl").write_text(
        json.dumps({"method": "POST", "path": "/api/v1/game/new", "status": 200}) + "\n"
    )
    with patch(
        "scripts.testing.capture.subprocess.run",
        return_value=SimpleNamespace(stdout=packets),
    ):
        if error:
            with pytest.raises(ValueError, match=error):
                verify(tmp_path)
            assert not (tmp_path / "capture-verification.json").exists()
        else:
            verify(tmp_path)
            evidence = json.loads((tmp_path / "capture-verification.json").read_text())
            assert evidence[0]["request_frame"] == "1"
            assert evidence[0]["response_frame"] == "2"
