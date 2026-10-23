#!/usr/bin/env python3
"""Host-side orchestrator. Only the disposable Compose project is modified."""

import argparse
import fcntl
import html
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGES = {
    "unit": [
        "src/tests/domain",
        "src/tests/application",
        "src/tests/infrastructure",
        "tests_lab2/runner",
    ],
    "integration": ["tests_lab2/integration"],
    "e2e": ["tests_lab2/e2e"],
}


class Pipeline:
    def __init__(self, args):
        self.args = args
        self.run_id = (
            args.run_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        )
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", self.run_id):
            raise ValueError(
                "run-id must contain only lowercase ASCII letters, digits, _ and -"
            )
        self.project = "cmbtest-" + self.run_id
        self.output = ROOT / "build/testing" / self.run_id
        self.output.mkdir(parents=True, exist_ok=args.phase not in ("all", "prepare"))
        key = args.history_key
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", key):
            raise ValueError("Invalid history key")
        self.history = ROOT / "build/testing/history" / key
        self.history.mkdir(parents=True, exist_ok=True)
        self.env = dict(
            os.environ,
            CMB_TEST_OUTPUT=str(self.output),
            CMB_TEST_HISTORY=str(self.history),
            CMB_TEST_IMAGE=f"cmb-testing:{self.run_id}",
            CMB_MINIO_IMAGE=f"cmb-minio:{self.run_id}",
            CMB_TEST_UID=str(os.getuid()),
            CMB_TEST_GID=str(os.getgid()),
        )
        if (
            subprocess.run(
                ["docker", "compose", "version"], capture_output=True
            ).returncode
            == 0
        ):
            compose = ["docker", "compose"]
        elif shutil.which("docker-compose"):
            compose = ["docker-compose"]
        else:
            raise RuntimeError("Docker Compose is not installed")
        self.compose = compose + [
            "-p",
            self.project,
            "-f",
            str(ROOT / "docker-compose.testing.yml"),
        ]
        self.summary = {
            "run_id": self.run_id,
            "started_at": time.time(),
            "project": self.project,
            "stages": {},
            "cleanup": "not_started",
            "errors": [],
            "commit": self.commit(),
            "dirty_worktree": bool(
                subprocess.check_output(
                    ["git", "status", "--porcelain"],
                    cwd=ROOT,
                    text=True,
                ).strip()
            ),
        }
        self.built = False
        self.baseline = False
        if args.phase not in ("all", "prepare"):
            state = json.loads((self.output / "pipeline-state.json").read_text())
            if state["history_key"] != args.history_key:
                raise ValueError("Cannot change history key between phases")
            self.summary = state["summary"]
            self.built = state["built"]
            self.baseline = state["baseline"]

    def save_state(self):
        state = {
            "summary": self.summary,
            "built": self.built,
            "baseline": self.baseline,
            "history_key": self.args.history_key,
        }
        temporary = self.output / "pipeline-state.tmp"
        temporary.write_text(json.dumps(state, indent=2))
        temporary.replace(self.output / "pipeline-state.json")

    def commit(self):
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()

    def command(self, args, *, name, check=True, timeout=300):
        print(f"[{self.run_id}] {name}", flush=True)
        with (self.output / f"{name}.log").open("w") as log:
            try:
                result = subprocess.run(
                    self.compose + args,
                    cwd=ROOT,
                    env=self.env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                log.flush()
                self.print_log_tail(name)
                if check:
                    raise RuntimeError(f"{name} timed out; see {log.name}") from None
                return 124
        if result.returncode:
            self.print_log_tail(name)
            if check:
                raise RuntimeError(f"{name} exited {result.returncode}; see {log.name}")
        return result.returncode

    def print_log_tail(self, name):
        """Expose diagnostics in Actions as well as the downloadable artifact."""
        path = self.output / f"{name}.log"
        lines = path.read_text(errors="replace").splitlines()
        print(f"--- Last 80 lines of {name}.log ---", flush=True)
        print("\n".join(lines[-80:]), flush=True)

    def runner(self, command, *, name, env=None, check=True, timeout=300):
        options = ["run", "--rm", "--no-deps", "-T", "--name", f"{self.project}-{name}"]
        for key, value in (env or {}).items():
            options.extend(["-e", f"{key}={value}"])
        try:
            code = self.command(
                options + ["tests"] + command, name=name, check=check, timeout=timeout
            )
            if code == 124:
                self.remove_runner(name)
            return code
        except BaseException:
            # The Docker client dying does not necessarily stop its container.
            self.remove_runner(name)
            raise

    def remove_runner(self, name):
        subprocess.run(
            ["docker", "rm", "-f", f"{self.project}-{name}"],
            env=self.env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )

    def storage(self, action, name, **kwargs):
        return self.runner(
            ["python", "-m", "scripts.testing.storage", action], name=name, **kwargs
        )

    def pytest(self, stage, reason=None):
        env = {
            "CMB_STAGE": stage,
            "CMB_FAIL_STAGE": self.args.fail_stage or "",
            "COVERAGE_FILE": "/artifacts/coverage-data",
        }
        if reason:
            env["CMB_SKIP_REASON"] = reason
        command = [
            "python",
            "-m",
            "pytest",
            "-p",
            "scripts.testing.pytest_control",
            *STAGES[stage],
            "--timeout=45",
            "-o",
            "cache_dir=/artifacts/pytest-cache",
            "--randomly-seed=20261015",
            f"--junitxml=/artifacts/{stage}.xml",
            "--alluredir=/artifacts/allure-results",
        ]
        if stage == "unit" and not reason:
            command += [
                "--disable-socket",
                "--cov=src",
                "--cov-branch",
                "--cov-config=pyproject.toml",
                "--cov-report=term-missing",
                "--cov-report=xml:/artifacts/coverage.xml",
                "--cov-report=html:/artifacts/coverage",
            ]
        return self.runner(command, name=stage, env=env, check=False, timeout=600)

    def start_api(self, label):
        self.command(["up", "-d", "--no-deps", "api"], name=f"api-{label}")
        self.runner(
            ["python", "-m", "scripts.testing.wait", "api"],
            name=f"wait-api-{label}",
            timeout=120,
        )
        port = subprocess.check_output(
            self.compose + ["port", "api", "8000"], cwd=ROOT, env=self.env, text=True
        ).strip()
        (self.output / "api-url.txt").write_text("http://" + port + "\n")

    def prepare(self):
        self.command(["build", "tests", "minio"], name="build", timeout=1200)
        self.built = True
        self.command(["up", "-d", "db", "minio"], name="storage-up", timeout=180)
        self.runner(
            ["python", "-m", "scripts.testing.wait", "storage"],
            name="wait-storage",
            timeout=120,
        )
        self.storage("reset", "initial-reset")
        self.storage("snapshot", "initial-snapshot")
        self.baseline = True
        self.storage("verify", "initial-verify")

    def run_stage(self, stage):
        previous = list(STAGES)[: list(STAGES).index(stage)]
        if self.summary["errors"] or any(
            self.summary["stages"].get(name, {}).get("status") != "passed"
            for name in previous
        ):
            raise RuntimeError(
                f"Cannot run {stage}: preparation or previous stage failed"
            )
        if stage != "unit":
            self.storage("reset", f"before-{stage}-reset")
            self.storage("verify", f"before-{stage}-verify")
        if stage == "e2e":
            self.start_api("e2e")
        code = self.pytest(stage)
        if stage == "integration" and not code and self.args.repeat_integration:
            # Reuse the same PostgreSQL container and volume for both runs.
            (self.output / "integration.xml").replace(
                self.output / "integration-first.xml"
            )
            (self.output / "integration.log").replace(
                self.output / "integration-first.log"
            )
            self.storage("reset", "repeat-integration-reset")
            self.storage("verify", "repeat-integration-verify")
            code = self.pytest(stage)
            self.summary["integration_repeated_on_same_instance"] = True
        self.summary["stages"][stage] = {
            "status": "failed" if code else "passed",
            "returncode": code,
        }

    def replay(self):
        if self.summary["errors"] or any(
            self.summary["stages"].get(stage, {}).get("status") != "passed"
            for stage in STAGES
        ):
            raise RuntimeError("Cannot replay an unsuccessful pipeline")
        self.command(["stop", "api"], name="before-replay-stop")
        self.storage("reset", "before-replay-reset")
        self.start_api("replay")
        self.command(["up", "-d", "--no-deps", "capture"], name="capture-start")
        try:
            deadline = time.monotonic() + 15
            pcap = self.output / "demo.pcap"
            while not pcap.exists() or pcap.stat().st_size < 24:
                if time.monotonic() >= deadline:
                    raise RuntimeError("tcpdump did not initialize the capture")
                time.sleep(0.1)
            self.runner(
                ["python", "-m", "scripts.testing.scenario", "--curl"],
                name="curl-replay",
            )
            # Allow capture to consume the last response before SIGINT.
            time.sleep(2)
        finally:
            self.command(["stop", "capture"], name="capture-stop", check=False)
        pcap = self.output / "demo.pcap"
        if not pcap.exists() or pcap.stat().st_size <= 24:
            raise RuntimeError("Packet capture is empty")
        self.runner(["python", "-m", "scripts.testing.capture"], name="capture-verify")
        self.summary["capture"] = "verified"

    def execute(self):
        self.prepare()
        failed = None
        for stage in STAGES:
            if failed:
                code = self.pytest(stage, f"Previous stage {failed} failed")
                self.summary["stages"][stage] = {
                    "status": "skipped",
                    "returncode": code,
                }
                if code:
                    self.summary["errors"].append(f"Could not record skipped {stage}")
            else:
                self.run_stage(stage)
                if self.summary["stages"][stage]["status"] == "failed":
                    failed = stage
        if self.args.replay and not failed:
            self.replay()

    def cleanup_command(self, args, *, name, timeout):
        try:
            return self.command(args, name=name, check=False, timeout=timeout)
        except Exception as exc:
            self.summary["errors"].append(f"{name}: {exc}")
            return 1

    def finalize(self):
        # Never let signal handlers interrupt restoration halfway through.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        self.cleanup_command(["logs", "--no-color"], name="services", timeout=30)
        # A timeout/interruption may leave a docker-compose run container alive.
        self.cleanup_command(["kill"], name="stop-running-processes", timeout=30)
        if self.baseline:
            try:
                self.command(["up", "-d", "db", "minio"], name="cleanup-storage-up")
                self.runner(
                    ["python", "-m", "scripts.testing.wait", "storage"],
                    name="cleanup-wait",
                    timeout=120,
                )
                self.storage("reset", "cleanup-reset")
                self.storage("verify", "cleanup-verify")
                self.summary["cleanup"] = "verified"
            except Exception as exc:
                self.summary["cleanup"] = "failed"
                self.summary["errors"].append(str(exc))
        if self.built:
            for stage in STAGES:
                if not (self.output / f"{stage}.xml").exists():
                    try:
                        code = self.pytest(
                            stage, "Environment preparation or pipeline interrupted"
                        )
                        self.summary["stages"].setdefault(
                            stage, {"status": "skipped", "returncode": code}
                        )
                    except Exception as exc:
                        self.summary["errors"].append(str(exc))
            (self.output / "infrastructure.json").write_text(
                json.dumps(self.summary, indent=2)
            )
            try:
                with (self.history / "history.lock").open("w") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    self.runner(
                        ["python", "-m", "scripts.testing.report"],
                        name="allure-report",
                        env={
                            "CMB_RUN_ID": self.run_id,
                            "CMB_BUILD_ORDER": str(time.time_ns() // 1000000),
                            "CI": os.environ.get("CI", ""),
                        },
                    )
            except Exception as exc:
                self.summary["errors"].append(str(exc))
        if not self.args.keep:
            code = self.cleanup_command(
                ["down", "--volumes", "--remove-orphans", "--timeout", "5"],
                name="down",
                timeout=90,
            )
            if code:
                self.summary["errors"].append(f"Resource removal failed: {code}")
        self.write_report()

    def write_report(self):
        self.summary["finished_at"] = time.time()
        for stage in STAGES:
            self.summary["stages"].setdefault(
                stage,
                {
                    "status": "skipped",
                    "reason": "Environment preparation failed",
                },
            )
        rows = []
        counts = {"passed": 0, "failed": 0, "skipped": 0}
        for stage in STAGES:
            path = self.output / f"{stage}.xml"
            if path.exists():
                try:
                    cases = list(ET.parse(path).iter("testcase"))
                except ET.ParseError:
                    self.summary["errors"].append(f"Incomplete JUnit file: {stage}")
                    cases = []
                for case in cases:
                    state = (
                        "failed"
                        if case.find("failure") is not None
                        or case.find("error") is not None
                        else "skipped" if case.find("skipped") is not None else "passed"
                    )
                    counts[state] += 1
                    detail = " ".join(child.get("message", "") for child in case)
                    rows.append(
                        f"<tr><td>{stage}</td>"
                        f"<td>{html.escape(case.get('name', ''))}</td>"
                        f"<td>{state}</td><td>{html.escape(detail)}</td></tr>"
                    )
        self.summary["counts"] = counts
        (self.output / "summary.json").write_text(json.dumps(self.summary, indent=2))
        with (self.history / "trend.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            trend_file = self.history / "trends.json"
            trends = json.loads(trend_file.read_text()) if trend_file.exists() else []
            trends.append(
                {"run": self.run_id, **counts, "cleanup": self.summary["cleanup"]}
            )
            trend_file.write_text(json.dumps(trends[-30:], indent=2))
        trend_rows = "".join(
            f"<tr><td>{html.escape(x['run'])}</td><td>{x['passed']}</td>"
            f"<td>{x['failed']}</td><td>{x['skipped']}</td>"
            f"<td>{x['cleanup']}</td></tr>"
            for x in trends[-30:]
        )
        text = f"""<!doctype html><html lang="ru"><meta charset="utf-8">
<title>CMB Lab 2</title>
<style>body{{font:16px system-ui;margin:2rem;max-width:1300px}}
table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:.5rem;text-align:left}}
pre{{white-space:pre-wrap}}</style>
<h1>Cool Magic Battles: {html.escape(self.run_id)}</h1>
<p>Commit: {html.escape(self.summary["commit"])}</p>
<p>Cleanup: <b>{self.summary["cleanup"]}</b></p>
<p><a href="allure-report/index.html">Allure report</a> (serve over HTTP)</p>
<p><a href="coverage/index.html">Unit coverage</a> ·
<a href="summary.json">Summary JSON</a></p>
<h2>Pipeline</h2><pre>{html.escape(json.dumps(self.summary, indent=2))}</pre>
<h2>Trends</h2><table><tr><th>Run</th><th>Passed</th><th>Failed</th><th>Skipped</th><th>Cleanup</th></tr>{trend_rows}</table>
<h2>Tests</h2><table><tr><th>Stage</th><th>Test</th><th>Result</th><th>Details</th></tr>{"".join(rows)}</table></html>"""
        (self.output / "index.html").write_text(text)


def interrupted(signum, frame):
    raise KeyboardInterrupt(f"Signal {signum}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=os.environ.get("CMB_RUN_ID"))
    parser.add_argument(
        "--phase",
        default="all",
        choices=["all", "prepare", *STAGES, "replay", "finalize"],
        help="Execute one CI step against the same persisted Compose project",
    )
    parser.add_argument(
        "--history-key", default=os.environ.get("CMB_HISTORY_KEY", "local")
    )
    parser.add_argument(
        "--fail-stage", choices=STAGES, default=os.environ.get("CMB_FAIL_STAGE") or None
    )
    parser.add_argument(
        "--repeat-integration",
        action="store_true",
        default=os.environ.get("GITHUB_ACTIONS") == "true",
        help="Run integration twice against the same storage instance",
    )
    parser.add_argument(
        "--replay", action="store_true", help="Repeat E2E with curl and capture PCAP"
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep stopped containers with verified restored baseline",
    )
    args = parser.parse_args()
    if args.phase != "all" and not args.run_id:
        parser.error("--phase requires an explicit --run-id")
    pipeline = Pipeline(args)
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.phase == "all":
            pipeline.execute()
        elif args.phase in STAGES:
            pipeline.run_stage(args.phase)
        elif args.phase != "finalize":
            getattr(pipeline, args.phase)()
    except (Exception, KeyboardInterrupt) as exc:
        pipeline.summary["errors"].append(str(exc))
    finally:
        if args.phase in ("all", "finalize"):
            pipeline.finalize()
        else:
            pipeline.save_state()
    if args.phase not in ("all", "finalize"):
        return int(
            bool(pipeline.summary["errors"])
            or any(
                stage["status"] == "failed"
                for stage in pipeline.summary["stages"].values()
            )
        )
    print(json.dumps(pipeline.summary, indent=2))
    print(f"Report: {pipeline.output / 'index.html'}")
    return int(
        bool(pipeline.summary["errors"])
        or pipeline.summary["cleanup"] != "verified"
        or any(x["status"] != "passed" for x in pipeline.summary["stages"].values())
    )


if __name__ == "__main__":
    sys.exit(main())
