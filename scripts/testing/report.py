"""Allure 2 HTML + persisted history. Called inside the test image."""

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path


def generate():
    root = Path("/artifacts")
    results = root / "allure-results"
    results.mkdir(exist_ok=True)
    infrastructure = json.loads((root / "infrastructure.json").read_text())
    good = not infrastructure["errors"] and infrastructure["cleanup"] == "verified"
    now = int(time.time() * 1000)
    (results / "infrastructure-result.json").write_text(
        json.dumps(
            {
                "uuid": str(uuid.uuid4()),
                "historyId": "cmb-lab2-environment-restoration",
                "testCaseId": "cmb-lab2-environment-restoration",
                "name": "Environment preparation and baseline restoration",
                "fullName": "lab2.infrastructure.baseline_restoration",
                "status": "passed" if good else "failed",
                "stage": "finished",
                "start": now,
                "stop": now,
                "statusDetails": {"message": json.dumps(infrastructure, indent=2)},
                "labels": [{"name": "suite", "value": "Infrastructure"}],
            }
        )
    )
    history = Path("/history/current")
    if history.exists():
        shutil.copytree(history, results / "history", dirs_exist_ok=True)
    (results / "executor.json").write_text(
        json.dumps(
            {
                "name": "Cool Magic Battles lab2",
                "type": "github" if os.getenv("CI") else "local",
                "buildName": os.environ["CMB_RUN_ID"],
                "buildOrder": int(os.environ["CMB_BUILD_ORDER"]),
            }
        )
    )
    subprocess.run(
        [
            "allure",
            "generate",
            str(results),
            "-o",
            str(root / "allure-report"),
            "--clean",
        ],
        check=True,
    )
    generated = root / "allure-report/history"
    if generated.exists():
        if history.exists():
            shutil.rmtree(history)
        shutil.copytree(generated, history)


if __name__ == "__main__":
    generate()
