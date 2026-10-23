"""Merging must preserve failures, cleanup evidence, and real Allure results."""

import json
from types import SimpleNamespace

from scripts.testing.merge import collect


def stage_result(root, stage, *, cleanup="verified", errors=None):
    source = root / f"lab2-stage-{stage}"
    (source / "allure-results").mkdir(parents=True)
    (source / "summary.json").write_text(
        json.dumps(
            {
                "stages": {stage: {"status": "passed", "returncode": 0}},
                "cleanup": cleanup,
                "errors": errors or [],
            }
        )
    )
    (source / f"{stage}.xml").write_text("<testsuites/>")
    (source / "allure-results" / f"{stage}-result.json").write_text("{}")
    (source / "allure-results" / "infrastructure-result.json").write_text("{}")


def pipeline(root):
    output = root / "output"
    output.mkdir()
    return SimpleNamespace(output=output, summary={"errors": [], "stages": {}})


def test_merge_keeps_skipped_stages_and_one_set_of_results(tmp_path):
    stage_result(tmp_path, "unit")
    target = pipeline(tmp_path)
    collect(
        target,
        tmp_path,
        {"unit": "success", "integration": "skipped", "e2e": "skipped"},
    )
    assert target.summary["stages"]["integration"]["status"] == "skipped"
    assert target.summary["cleanup"] == "verified"
    assert (target.output / "allure-results/unit-result.json").exists()
    assert not (target.output / "allure-results/infrastructure-result.json").exists()
    assert (target.output / "jobs/unit/summary.json").exists()


def test_missing_failed_job_artifact_cannot_appear_successful(tmp_path):
    target = pipeline(tmp_path)
    collect(target, tmp_path, {"unit": "failure"})
    assert target.summary["stages"]["unit"]["status"] == "failed"
    assert target.summary["cleanup"] == "failed"
    assert "summary missing" in target.summary["errors"][0]


def test_cleanup_failure_propagates_to_combined_report(tmp_path):
    stage_result(tmp_path, "unit", cleanup="failed", errors=["baseline mismatch"])
    target = pipeline(tmp_path)
    collect(target, tmp_path, {"unit": "failure"})
    assert target.summary["cleanup"] == "failed"
    assert "unit: baseline mismatch" in target.summary["errors"]


def test_successful_single_stage_ignores_other_stage_placeholders(
    tmp_path, monkeypatch
):
    from unittest.mock import Mock

    from scripts.testing.run import main

    target = SimpleNamespace(
        execute=Mock(),
        finalize=Mock(),
        output=tmp_path,
        summary={
            "errors": [],
            "cleanup": "verified",
            "stages": {
                "unit": {"status": "skipped"},
                "integration": {"status": "passed"},
                "e2e": {"status": "skipped"},
            },
        },
    )
    monkeypatch.setattr("scripts.testing.run.Pipeline", Mock(return_value=target))
    monkeypatch.setattr("scripts.testing.run.signal.signal", Mock())
    monkeypatch.setattr(
        "sys.argv", ["run.py", "--run-id", "single", "--only-stage", "integration"]
    )
    assert main() == 0
    target.finalize.assert_called_once_with()
