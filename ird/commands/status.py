"""Check remote job progress by rsyncing progress/ directory."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from ..connection import apply_config_overrides, ensure_reservation
from ..ird_reservation import ird_release_by_job
from ..session import Session
from ..transfer.resilient_rsync import rsync_from_remote
from ..transfer.resilient_ssh import ssh_run

logger = logging.getLogger(__name__)


def status(
    session: Session,
    *,
    watch: bool = False,
    poll_interval: int = 30,
    local_progress_dir: Path = Path("progress"),
    session_path: Path = Path("session.json"),
    config_path: str | None = None,
) -> bool:
    """Check progress of the remote job.

    Returns True if the DONE marker is found (job completed).
    In --watch mode, blocks until completion.
    """
    apply_config_overrides(session, config_path)
    session, acquired = ensure_reservation(session, session_path)
    try:
        return _do_status(session, watch=watch, poll_interval=poll_interval,
                          local_progress_dir=local_progress_dir)
    finally:
        if acquired:
            ird_release_by_job(session.ird_ssh_target(), session.job_id)


def _do_status(
    session: Session,
    *,
    watch: bool = False,
    poll_interval: int = 30,
    local_progress_dir: Path = Path("progress"),
) -> bool:
    target = session.ssh_target()

    while True:
        rsync_from_remote(
            f"{session.remote_work_dir}/progress/",
            local_progress_dir,
            target,
            delete=True,
        )

        done = _check_done_marker(session, target)
        summary = _print_summary(session, local_progress_dir, done)

        if done:
            print("\nJob completed!")
            return True

        if not watch:
            return False

        print(f"\nPolling again in {poll_interval}s... (Ctrl-C to stop)")
        try:
            time.sleep(poll_interval)
        except KeyboardInterrupt:
            print("\nStopped watching.")
            return False


def _check_done_marker(session: Session, target) -> bool:
    """Check if the remote DONE marker file exists."""
    try:
        result = ssh_run(
            target,
            f"test -f {session.remote_work_dir}/DONE && cat {session.remote_work_dir}/DONE",
            check=False,
            max_retries=2,
            timeout=30,
        )
        return result.returncode == 0
    except ConnectionError:
        logger.warning("Could not check DONE marker (connection issue)")
        return False


def _print_summary(
    session: Session,
    local_progress_dir: Path,
    done: bool,
) -> dict:
    """Parse progress files and print a summary table."""
    progress_files = list(local_progress_dir.glob("*.json"))

    total = len(progress_files)
    completed = 0
    running = 0
    passed = 0
    failed = 0
    retried = 0
    errors = 0

    for pf in progress_files:
        try:
            data = json.loads(pf.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        status_val = data.get("status", "unknown")
        if status_val == "done":
            completed += 1
            if data.get("exit_code", -1) == 0:
                passed += 1
            else:
                failed += 1
            if data.get("attempt", 1) > 1:
                retried += 1
        elif status_val == "running":
            running += 1
        elif status_val == "error":
            errors += 1
            completed += 1

    pending = max(0, total - completed - running)

    print(f"\nRTL Test Run Status (tag: {session.rtl_tag}, "
          f"host: {session.host}, port: {session.port})")
    print(f"  Total: {total} tests | Done: {completed} | Running: {running} | Pending: {pending}")
    print(f"  Pass: {passed} | Fail: {failed} | Errors: {errors} | Retried: {retried}")
    if done:
        print("  Status: COMPLETED")
    else:
        print("  Status: IN PROGRESS")

    return {
        "total": total, "completed": completed, "running": running,
        "passed": passed, "failed": failed, "errors": errors, "retried": retried,
    }
