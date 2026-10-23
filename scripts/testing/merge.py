"""Collect independent CI jobs into one report, including skipped stages."""

import argparse
import json
import os
import shutil
from pathlib import Path

from scripts.testing.run import STAGES, Pipeline


def collect(pipeline, sources: Path, outcomes):
    cleanups = {}
    results = pipeline.output / "allure-results"
    results.mkdir(exist_ok=True)
    for stage in STAGES:
        source = sources / f"lab2-stage-{stage}"
        summary_file = source / "summary.json"
        outcome = outcomes.get(stage, "skipped")
        if outcome == "skipped":
            pipeline.summary["stages"][stage] = {
                "status": "skipped",
                "reason": "Previous CI job failed",
            }
            continue
        if not summary_file.exists():
            pipeline.summary["errors"].append(
                f"{stage}: CI job {outcome}, summary missing"
            )
            pipeline.summary["stages"][stage] = {"status": "failed"}
            cleanups[stage] = "unverified"
            continue
        summary = json.loads(summary_file.read_text())
        pipeline.summary["stages"][stage] = summary["stages"][stage]
        cleanups[stage] = summary["cleanup"]
        pipeline.summary["errors"].extend(
            f"{stage}: {error}" for error in summary["errors"]
        )
        if outcome != "success":
            pipeline.summary["errors"].append(f"{stage}: GitHub job {outcome}")
        if stage == "integration":
            pipeline.summary["integration_repeated_on_same_instance"] = summary.get(
                "integration_repeated_on_same_instance", False
            )
        if stage == "e2e" and "capture" in summary:
            pipeline.summary["capture"] = summary["capture"]
        # Keep complete diagnostics under each job's name.
        shutil.copytree(source, pipeline.output / "jobs" / stage)
        for name in (
            f"{stage}.xml",
            "integration-first.xml",
            "coverage.xml",
            "demo.pcap",
            "replay.jsonl",
            "http-packets.tsv",
            "capture-verification.json",
        ):
            if (source / name).exists():
                shutil.copy2(source / name, pipeline.output / name)
        if stage == "unit" and (source / "coverage").exists():
            shutil.copytree(source / "coverage", pipeline.output / "coverage")
        for item in (source / "allure-results").glob("*"):
            if item.is_file() and item.name not in (
                "infrastructure-result.json",
                "executor.json",
            ):
                target = results / item.name
                if target.exists():
                    raise ValueError(f"Duplicate Allure result: {item.name}")
                shutil.copy2(item, target)
    pipeline.summary["job_cleanup"] = cleanups
    pipeline.summary["cleanup"] = (
        "verified"
        if cleanups and all(value == "verified" for value in cleanups.values())
        else "failed"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=Path("build/stages"))
    args = parser.parse_args()
    pipeline = Pipeline(
        argparse.Namespace(
            run_id=os.environ["CMB_RUN_ID"],
            history_key=os.environ["CMB_HISTORY_KEY"],
            phase="all",
            only_stage=None,
            keep=False,
            fail_stage=None,
            repeat_integration=False,
            replay=False,
        )
    )
    try:
        collect(pipeline, args.sources, json.loads(os.environ["CMB_JOB_RESULTS"]))
        pipeline.command(["build", "tests"], name="build-report-image", timeout=1200)
        pipeline.built = True
    except Exception as exc:
        pipeline.summary["errors"].append(str(exc))
    finally:
        pipeline.finalize()
    print(json.dumps(pipeline.summary, indent=2))
    return int(
        bool(pipeline.summary["errors"]) or pipeline.summary["cleanup"] != "verified"
    )


if __name__ == "__main__":
    raise SystemExit(main())
