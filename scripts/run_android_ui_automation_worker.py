import argparse
import json
import os
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.services.base_service import ServiceError
from app.services.android_ui_automation_worker import AndroidUiAutomationWorker


class SingleInstanceLock:
    def __init__(self, lock_path):
        self.lock_path = Path(lock_path)
        self.owner = False

    def _read_lock_info(self):
        if not self.lock_path.is_file():
            return {}
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def acquire(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": os.getpid(),
            "started_at": datetime.now(UTC).isoformat(),
            "python_executable": sys.executable,
            "script": str(Path(__file__).resolve()),
        }
        while True:
            try:
                fd = os.open(
                    str(self.lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                existing = self._read_lock_info()
                if AndroidUiAutomationWorker.is_pid_running(existing.get("pid")):
                    return False, existing
                try:
                    self.lock_path.unlink()
                except FileNotFoundError:
                    continue
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            self.owner = True
            return True, payload

    def release(self):
        if not self.owner:
            return
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass
        self.owner = False


class WorkerMonitor:
    def __init__(self, app, heartbeat_interval):
        self.app = app
        self.heartbeat_interval = max(1.0, float(heartbeat_interval))
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._state = "idle"
        self._current_run_id = None
        self._last_error = ""
        self._current_stage = ""
        self._progress_text = ""
        self._progress_percent = None
        self._current_task_name = ""

    def set_state(
        self,
        state,
        current_run_id=None,
        last_error=None,
        current_stage=None,
        progress_text=None,
        progress_percent=None,
        current_task_name=None,
        **extra_payload,
    ):
        if current_stage is None and "stage" in extra_payload:
            current_stage = extra_payload.get("stage")
        if current_task_name is None and "task_name" in extra_payload:
            current_task_name = extra_payload.get("task_name")
        if progress_text is None and "progress_message" in extra_payload:
            progress_text = extra_payload.get("progress_message")
        with self._lock:
            self._state = str(state or "idle")
            self._current_run_id = current_run_id
            if last_error is not None:
                self._last_error = str(last_error or "")
            if current_stage is not None:
                self._current_stage = str(current_stage or "")
            if progress_text is not None:
                self._progress_text = str(progress_text or "")
            if progress_percent is not None or progress_percent is None:
                self._progress_percent = progress_percent
            if current_task_name is not None:
                self._current_task_name = str(current_task_name or "")

    def _payload(self):
        with self._lock:
            state = self._state
            current_run_id = self._current_run_id
            last_error = self._last_error
            current_stage = self._current_stage
            progress_text = self._progress_text
            progress_percent = self._progress_percent
            current_task_name = self._current_task_name
        return {
            "pid": os.getpid(),
            "state": state,
            "current_run_id": current_run_id,
            "last_error": last_error,
            "current_stage": current_stage,
            "progress_text": progress_text,
            "progress_percent": progress_percent,
            "current_task_name": current_task_name,
            "last_heartbeat_at": datetime.now(UTC).isoformat(),
            "python_executable": sys.executable,
            "script": str(Path(__file__).resolve()),
        }

    def _loop(self):
        while not self._stop_event.wait(self.heartbeat_interval):
            with self.app.app_context():
                AndroidUiAutomationWorker.write_worker_status(self._payload())

    def start(self):
        with self.app.app_context():
            AndroidUiAutomationWorker.write_worker_status(self._payload())
        self._thread = threading.Thread(
            target=self._loop,
            name="android-ui-automation-worker-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def stop(self, final_state="stopped"):
        self.set_state(
            final_state,
            current_run_id=None,
            current_stage="",
            progress_text="",
            progress_percent=None,
            current_task_name="",
        )
        with self.app.app_context():
            AndroidUiAutomationWorker.write_worker_status(self._payload())
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.heartbeat_interval + 1)


def parse_args():
    parser = argparse.ArgumentParser(description="Run queued Android UI automation jobs.")
    parser.add_argument("--once", action="store_true", help="Process one queued job and exit.")
    parser.add_argument("--run-id", type=int, help="Execute a specific run and exit.")
    parser.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds.")
    return parser.parse_args()


def main():
    args = parse_args()
    app = create_app()
    with app.app_context():
        heartbeat_interval = app.config.get("ANDROID_UI_WORKER_HEARTBEAT_INTERVAL", 5)
        lock = SingleInstanceLock(AndroidUiAutomationWorker.worker_lock_path())
        acquired, existing = lock.acquire()
        if not acquired:
            print(
                "worker already running",
                existing.get("pid"),
                existing.get("python_executable", ""),
            )
            return 0

    monitor = WorkerMonitor(app, heartbeat_interval)
    final_state = "stopped"
    try:
        monitor.start()
        with app.app_context():
            AndroidUiAutomationWorker.recover_stale_runs()
            if args.run_id:
                monitor.set_state("running", current_run_id=args.run_id)
                run = AndroidUiAutomationWorker.execute_run(
                    args.run_id,
                    progress_callback=lambda **payload: monitor.set_state(
                        "running",
                        current_run_id=args.run_id,
                        **payload,
                    ),
                )
                monitor.set_state(
                    "idle",
                    current_run_id=None,
                    current_stage="",
                    progress_text="",
                    progress_percent=None,
                    current_task_name="",
                )
                print(f"run={run.id} status={run.status} duration_ms={run.duration_ms}")
                return 0 if run.status == "passed" else 1

        while True:
            with app.app_context():
                AndroidUiAutomationWorker.recover_stale_runs()
                run = AndroidUiAutomationWorker.get_next_queued_run()
                if run:
                    monitor.set_state("running", current_run_id=run.id)
                    run = AndroidUiAutomationWorker.execute_run(
                        run.id,
                        progress_callback=lambda **payload: monitor.set_state(
                            "running",
                            current_run_id=run.id,
                            **payload,
                        ),
                    )
                    monitor.set_state(
                        "idle",
                        current_run_id=None,
                        current_stage="",
                        progress_text="",
                        progress_percent=None,
                        current_task_name="",
                    )
                    print(f"run={run.id} status={run.status} duration_ms={run.duration_ms}")
                    if args.once:
                        return 0 if run.status == "passed" else 1
                    continue
                if args.once:
                    print("no queued Android UI automation run")
                    return 0
            monitor.set_state(
                "idle",
                current_run_id=None,
                current_stage="",
                progress_text="",
                progress_percent=None,
                current_task_name="",
            )
            time.sleep(max(0.2, args.interval))
    except ServiceError as exc:
        final_state = "error"
        monitor.set_state("error", current_run_id=None, last_error=str(exc))
        print(str(exc))
        return 1
    except Exception as exc:
        final_state = "error"
        monitor.set_state("error", current_run_id=None, last_error=str(exc))
        raise
    finally:
        # Preserve an unexpected failure in status.json.  The previous
        # unconditional "stopped" payload erased the only diagnostic shown
        # by the execution page after the worker process had exited.
        monitor.stop(final_state=final_state)
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
