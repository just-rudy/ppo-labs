"""Assemble the public report; full logs and captures stay in Actions artifacts."""

import argparse
import shutil
from pathlib import Path


def prepare(source: Path, destination: Path):
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("index.html", "summary.json"):
        shutil.copy2(source / name, destination / name)
    for name in ("allure-report", "coverage"):
        if (source / name).is_dir():
            shutil.copytree(source / name, destination / name)
    (destination / ".nojekyll").touch()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    prepare(args.source, args.destination)
