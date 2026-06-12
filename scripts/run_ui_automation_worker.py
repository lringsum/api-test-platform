import argparse
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.services.ui_automation_worker import UiAutomationWorker


def parse_args():
    parser = argparse.ArgumentParser(description="Run queued UI automation jobs.")
    parser.add_argument("--once", action="store_true", help="Process one queued job and exit.")
    parser.add_argument("--run-id", type=int, help="Execute a specific run and exit.")
    parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds.")
    return parser.parse_args()


def main():
    args = parse_args()
    app = create_app()
    with app.app_context():
        if args.run_id:
            run = UiAutomationWorker.execute_run(args.run_id)
            print(f"run={run.id} status={run.status} duration_ms={run.duration_ms}")
            return 0 if run.status == "passed" else 1

        while True:
            run = UiAutomationWorker.get_next_queued_run()
            if run:
                run = UiAutomationWorker.execute_run(run.id)
                print(f"run={run.id} status={run.status} duration_ms={run.duration_ms}")
                if args.once:
                    return 0 if run.status == "passed" else 1
                continue
            if args.once:
                print("no queued UI automation run")
                return 0
            time.sleep(max(0.2, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
