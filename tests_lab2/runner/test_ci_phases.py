"""Separate Actions steps must keep the same environment and failure ordering."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from scripts.testing.run import Pipeline


def test_phase_restores_same_compose_project_and_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.testing.run.ROOT", tmp_path)
    monkeypatch.setattr(
        "scripts.testing.run.subprocess.run",
        Mock(return_value=SimpleNamespace(returncode=0)),
    )
    monkeypatch.setattr(
        "scripts.testing.run.subprocess.check_output", Mock(return_value="commit\n")
    )
    args = SimpleNamespace(run_id="phase-test", history_key="branch", phase="prepare")
    initial = Pipeline(args)
    initial.built = True
    initial.baseline = True
    initial.summary["stages"]["unit"] = {"status": "passed", "returncode": 0}
    initial.save_state()
    args.phase = "integration"
    resumed = Pipeline(args)
    assert resumed.project == initial.project
    assert resumed.env["CMB_TEST_IMAGE"] == initial.env["CMB_TEST_IMAGE"]
    assert resumed.env["CMB_MINIO_IMAGE"] == initial.env["CMB_MINIO_IMAGE"]
    assert resumed.output == initial.output
    assert resumed.built and resumed.baseline
    assert resumed.summary["stages"]["unit"]["status"] == "passed"


def test_integration_does_not_execute_after_failed_unit():
    pipeline = Pipeline.__new__(Pipeline)
    pipeline.summary = {"errors": [], "stages": {"unit": {"status": "failed"}}}
    pipeline.pytest = Mock()
    with pytest.raises(RuntimeError, match="previous stage failed"):
        pipeline.run_stage("integration")
    pipeline.pytest.assert_not_called()


def test_replay_does_not_execute_before_successful_e2e():
    pipeline = Pipeline.__new__(Pipeline)
    pipeline.summary = {"errors": [], "stages": {}}
    pipeline.command = Mock()
    with pytest.raises(RuntimeError, match="unsuccessful pipeline"):
        pipeline.replay()
    pipeline.command.assert_not_called()
