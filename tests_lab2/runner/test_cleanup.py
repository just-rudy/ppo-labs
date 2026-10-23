"""Logging failures must not prevent baseline restoration or summary generation."""

from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from scripts.testing.run import Pipeline


def test_cleanup_survives_log_collection_error():
    pipeline = Pipeline.__new__(Pipeline)
    pipeline.args = SimpleNamespace(keep=False)
    pipeline.summary = {"errors": [], "cleanup": "not_started"}
    pipeline.baseline = True
    pipeline.built = False

    def command(args, **kwargs):
        if args[0] == "logs":
            raise OSError("Docker log client failed")
        return 0

    pipeline.command = Mock(side_effect=command)
    pipeline.runner = Mock(return_value=0)
    pipeline.storage = Mock(return_value=0)
    pipeline.write_report = Mock()
    with patch("scripts.testing.run.signal.signal"):
        pipeline.finalize()
    assert pipeline.summary["cleanup"] == "verified"
    assert pipeline.summary["errors"] == ["services: Docker log client failed"]
    assert pipeline.storage.call_args_list == [
        call("reset", "cleanup-reset"),
        call("verify", "cleanup-verify"),
    ]
    assert pipeline.command.call_args_list[-1].args[0][0] == "down"
    pipeline.write_report.assert_called_once_with()
