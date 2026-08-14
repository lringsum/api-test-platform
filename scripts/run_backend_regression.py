import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_step(name, command):
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main():
    run_step("db-upgrade", ["flask", "--app", "run.py", "db", "upgrade"])
    run_step("pytest", [sys.executable, "-m", "pytest", "-q", "tests"])


if __name__ == "__main__":
    main()
