"""Run rsim tests with configurable retry and parallel/serial modes."""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import subprocess
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

PROGRESS_DIR = "progress"


def run_all(tests: list[str], config: dict) -> None:
    """Run all tests according to the configured mode."""
    os.makedirs(PROGRESS_DIR, exist_ok=True)

    mode = config.get("mode", "batch")
    num_processes = config.get("num_processes", 11)

    if mode == "serial":
        logger.info("Running %d tests serially", len(tests))
        for test in tests:
            run_test(test, config)
    else:
        num_procs = min(num_processes, len(tests))
        logger.info("Running %d tests in parallel (%d processes)", len(tests), num_procs)
        with multiprocessing.Pool(processes=num_procs) as pool:
            pool.starmap(_run_test_wrapper, [(test, config) for test in tests])


def _run_test_wrapper(test: str, config: dict) -> dict:
    """Wrapper for multiprocessing that handles exceptions."""
    try:
        return run_test(test, config)
    except Exception as e:
        logger.error("Unexpected error running test %s: %s", test, e)
        _write_progress(test, {
            "status": "error",
            "exit_code": -1,
            "attempt": 0,
            "time": time.time(),
            "error": str(e),
        })
        return {"test": test, "status": "error", "error": str(e)}


def run_test(test: str, config: dict) -> dict:
    """Run a single rsim test with configurable retry logic."""
    max_attempts = config.get("max_test_attempts", 1)
    ws_path = config.get("ws_tensix_path") or os.path.join(
        config["remote_root_dir_path"], config.get("remote_root_dir", "ws-tensix")
    )

    _write_progress(test, {"status": "running", "time": time.time()})

    result = None
    for attempt in range(max_attempts):
        logger.info("Running test %s (attempt %d/%d)", test, attempt + 1, max_attempts)
        # ENVIRONMENT WORKAROUNDS for running rsim via nohup/SSH
        #
        # When a user does `ird connect-to <id>` interactively, the container
        # entrypoint sets up the full environment: IRD_VERSION, conda in PATH,
        # tek Python, etc.  Our remote worker is launched differently — via
        # direct SSH + nohup — so that environment is absent.  Two specific
        # issues must be fixed:
        #
        # Issue 1: SETUP.cctb.local.sh checks for container env vars
        #   The script (in ws-tensix/) has this guard:
        #     if [ -z "${IRD_VERSION:-}" ] && [ -z "${RSIM_LSF_CONTAINER:-}" ] && [ -z "${CI_JOB_ID:-}" ]
        #     then
        #         echo "ERROR: Please run SETUP.cctb.local.sh in a Tensix Development Container."
        #         return 1
        #     fi
        #   At least one of IRD_VERSION, RSIM_LSF_CONTAINER, or CI_JOB_ID must
        #   be set.  To discover which one `ird connect-to` sets, run inside an
        #   interactive container session:
        #     echo "IRD_VERSION=${IRD_VERSION:-unset}"
        #     echo "RSIM_LSF_CONTAINER=${RSIM_LSF_CONTAINER:-unset}"
        #     echo "CI_JOB_ID=${CI_JOB_ID:-unset}"
        #   Currently `ird connect-to` sets IRD_VERSION (e.g. "1.12.104").
        #
        # Issue 2: .bashrc guards conda init behind a non-interactive check
        #   ~/.bashrc starts with:
        #     case $- in
        #       *i*) ;;
        #       *) return ;;
        #     esac
        #   This skips conda initialization in non-interactive shells, so
        #   `conda activate` inside SETUP.cctb.local.sh silently fails and
        #   Python resolves to /usr/bin/python (3.6) instead of the tek
        #   environment's Python (3.10).  Using `bash -i` makes the shell
        #   interactive, so .bashrc runs fully and conda initializes.
        #
        # Combined fix: bash -i + IRD_VERSION in env.
        ird_version = os.environ.get("IRD_VERSION", "1.12.104")
        result = subprocess.run(
            ["bash", "-i", "-c", f"source SETUP.cctb.local.sh && rsim run_test --test {test} --local"],
            capture_output=True,
            text=True,
            cwd=ws_path,
            env={**os.environ, "IRD_VERSION": ird_version},
        )

        if result.returncode == 0:
            logger.info("Test %s passed on attempt %d", test, attempt + 1)
            break

        stderr_snippet = (result.stderr or "").strip()[-500:]
        stdout_snippet = (result.stdout or "").strip()[-500:]
        logger.warning(
            "Test %s failed on attempt %d (exit %d)\n  stderr: %s\n  stdout: %s",
            test, attempt + 1, result.returncode, stderr_snippet, stdout_snippet,
        )
        if attempt < max_attempts - 1:
            time.sleep(10)

    progress_data = {
        "status": "done",
        "exit_code": result.returncode,
        "attempt": attempt + 1,
        "time": time.time(),
        "stderr": (result.stderr or "").strip()[-1000:],
        "stdout": (result.stdout or "").strip()[-1000:],
    }
    _write_progress(test, progress_data)
    return {"test": test, **progress_data}


def _write_progress(test: str, data: dict) -> None:
    """Write a per-test progress file atomically (tmp + rename)."""
    progress_file = Path(PROGRESS_DIR) / f"{test}.json"
    tmp_fd, tmp_path = tempfile.mkstemp(dir=PROGRESS_DIR, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp_path, progress_file)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
