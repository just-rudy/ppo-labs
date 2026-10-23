"""Record skipped stages without executing fixtures; inject demonstrable failures."""

import os

import pytest


def pytest_collection_modifyitems(items):
    reason = os.environ.get("CMB_SKIP_REASON")
    if reason:
        for item in items:
            item.add_marker(pytest.mark.skip(reason=reason))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    stage = os.environ.get("CMB_STAGE")
    if (
        report.when == "call"
        and report.passed
        and stage
        and stage == os.environ.get("CMB_FAIL_STAGE")
    ):
        # Real actions already ran; the host orchestrator must restore their commits.
        report.outcome = "failed"
        report.longrepr = (
            f"Intentional {stage} failure after test actions (lab recovery demo)"
        )
