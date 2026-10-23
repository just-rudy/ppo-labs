"""CI must show the actual Docker error, rather than only a remote log path."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from scripts.testing.run import Pipeline


def test_failed_command_prints_docker_diagnostic(tmp_path, capsys):
    pipeline = Pipeline.__new__(Pipeline)
    pipeline.output = tmp_path
    pipeline.run_id = "logging-check"
    pipeline.compose = ["docker", "compose"]
    pipeline.env = {}

    def failed_command(*args, **kwargs):
        kwargs["stdout"].write("minio: pull access denied\n")
        return SimpleNamespace(returncode=1)

    with patch("scripts.testing.run.subprocess.run", side_effect=failed_command):
        with pytest.raises(RuntimeError, match="storage-up exited 1"):
            pipeline.command(["up", "-d", "db", "minio"], name="storage-up")
    assert "minio: pull access denied" in capsys.readouterr().out
    assert (tmp_path / "storage-up.log").read_text() == "minio: pull access denied\n"
