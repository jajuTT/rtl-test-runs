"""Clone and build the ws-tensix repository on the remote machine."""

from __future__ import annotations

import datetime
import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def _run(cmd: str, cwd: str | None = None, timeout: int = 7200) -> subprocess.CompletedProcess:
    logger.info("Running: %s (cwd=%s)", cmd, cwd or os.getcwd())
    result = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
    )
    if result.returncode != 0:
        logger.error("Command failed (exit %d): %s\nstderr: %s", result.returncode, cmd, result.stderr)
    return result


def clone_and_build_if_needed(config: dict) -> None:
    """Clone ws-tensix and build if not already present."""
    root_path = config["remote_root_dir_path"]
    repo_dir = config.get("remote_root_dir", "ws-tensix")
    git_url = config.get("git_url", "git@yyz-gitlab.local.tenstorrent.com:tensix/tensix-hw/ws-tensix.git")
    ws_path = os.path.join(root_path, repo_dir)

    os.makedirs(root_path, exist_ok=True)

    if not os.path.isdir(ws_path):
        logger.info("Cloning %s into %s", git_url, root_path)
        # Shallow single-branch clone — we only need the repo for test execution,
        # not modification. Saves significant time on this large repository.
        result = _run(f"git clone --single-branch --depth 1 {git_url}", cwd=root_path)
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {result.stderr}")
    else:
        logger.info("Repository already exists at %s", ws_path)

    _build_if_needed(ws_path)
    _install_vendor_deps()

    config["ws_tensix_path"] = ws_path


def _install_vendor_deps() -> None:
    """Install beautifulsoup4 into remote_worker/vendor/ if not already importable.

    Uses --target so the shared conda/tek env is untouched. The guard probes
    ``import bs4`` with the current Python (adding vendor/ to sys.path) rather
    than relying on a sentinel file — that way a partial / broken install is
    automatically repaired on the next invocation.
    """
    import sys as _sys

    vendor_dir = os.path.join(os.path.dirname(__file__), "vendor")

    probe = f"import sys; sys.path.insert(0, {vendor_dir!r}); import bs4"
    probe_res = subprocess.run(
        [_sys.executable, "-c", probe],
        capture_output=True,
        text=True,
    )
    if probe_res.returncode == 0:
        logger.info("Vendor deps OK (bs4 importable from %s)", vendor_dir)
        return

    logger.info("Installing beautifulsoup4 into %s", vendor_dir)
    result = _run(
        f"{_sys.executable} -m pip install --target {vendor_dir} beautifulsoup4",
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to install vendor deps: {result.stderr}")

    verify = subprocess.run(
        [_sys.executable, "-c", probe],
        capture_output=True,
        text=True,
    )
    if verify.returncode != 0:
        raise RuntimeError(
            f"Vendor deps installed but bs4 still not importable from {vendor_dir}: "
            f"{verify.stderr.strip()}"
        )
    logger.info("Vendor deps installed successfully at %s", vendor_dir)


def _build_if_needed(ws_path: str) -> None:
    """Build the RTL testbench if build logs are not present."""
    result = subprocess.run(
        ["bash", "-O", "nullglob", "-c", 'files=(build*.log); (( ${#files[@]} )) && echo FOUND || echo NONE'],
        capture_output=True,
        text=True,
        cwd=ws_path,
    )

    if result.stdout.strip() == "FOUND":
        logger.info("Build artifacts found, skipping build")
        return

    logger.info("Building RTL testbench at %s", ws_path)
    build_cmd = "source SETUP.cctb.local.sh && make allclean && make all"
    result = _run(build_cmd, cwd=ws_path)
    if result.returncode != 0:
        raise RuntimeError(f"Build failed: {result.stderr}")

    logger.info("Smoke test: running a single test to verify build")
    smoke_cmd = "source SETUP.cctb.local.sh && rsim run_test --test t6-quas-n1-ttx-elwadd-fp32-dest-llk"
    result = _run(smoke_cmd, cwd=ws_path, timeout=1800)
    if result.returncode != 0:
        logger.warning("Smoke test failed (exit %d), build may be incomplete", result.returncode)
