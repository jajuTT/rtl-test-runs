"""Rsync wrapper with retry, exponential backoff, and SSH keepalive."""

from __future__ import annotations

import logging
import random
import subprocess
import time
from pathlib import Path

from ..config import SSHTarget

logger = logging.getLogger(__name__)


def _ssh_options(target: SSHTarget, connect_timeout: int = 30) -> str:
    # IRD containers get new host keys every time they are recreated.
    # UserKnownHostsFile=/dev/null avoids "REMOTE HOST IDENTIFICATION HAS
    # CHANGED" errors from stale entries in ~/.ssh/known_hosts.
    # LogLevel=ERROR suppresses the "Warning: Permanently added ..." noise
    # that StrictHostKeyChecking=no would otherwise print on every connection.
    opts = (
        f"-p {target.port} "
        f"-o ConnectTimeout={connect_timeout} "
        f"-o ServerAliveInterval=15 "
        f"-o ServerAliveCountMax=3 "
        f"-o StrictHostKeyChecking=no "
        f"-o UserKnownHostsFile=/dev/null "
        f"-o LogLevel=ERROR "
        f"-i {target.key_file}"
    )
    return opts


def rsync_with_retry(
    src: str,
    dest: str,
    ssh_target: SSHTarget,
    *,
    max_retries: int = 5,
    base_delay: float = 5.0,
    max_delay: float = 120.0,
    timeout: int = 600,
    extra_args: list[str] | None = None,
    delete: bool = False,
) -> bool:
    """Rsync with exponential backoff and jitter. Returns True on success."""
    ssh_opts = _ssh_options(ssh_target)
    cmd = [
        "rsync", "-az",
        "--timeout=300",
        "-e", f"ssh {ssh_opts}",
    ]
    if delete:
        cmd.append("--delete")
    if extra_args:
        cmd.extend(extra_args)
    cmd.extend([src, dest])

    for attempt in range(max_retries):
        logger.info("rsync attempt %d/%d: %s -> %s", attempt + 1, max_retries, src, dest)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                logger.info("rsync succeeded on attempt %d", attempt + 1)
                return True
            logger.warning(
                "rsync failed (exit %d): %s", result.returncode, result.stderr.strip()
            )
        except subprocess.TimeoutExpired:
            logger.warning("rsync timed out after %ds on attempt %d", timeout, attempt + 1)
        except OSError as e:
            logger.warning("rsync OS error on attempt %d: %s", attempt + 1, e)

        if attempt < max_retries - 1:
            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = random.uniform(0, delay * 0.3)
            sleep_time = delay + jitter
            logger.info("Retrying in %.1fs...", sleep_time)
            time.sleep(sleep_time)

    logger.error("rsync failed after %d attempts: %s -> %s", max_retries, src, dest)
    return False


def rsync_to_remote(
    local_path: str | Path,
    remote_path: str,
    ssh_target: SSHTarget,
    **kwargs,
) -> bool:
    """Rsync a local path to a remote destination."""
    remote_dest = f"{ssh_target.user}@{ssh_target.host}:{remote_path}"
    return rsync_with_retry(str(local_path), remote_dest, ssh_target, **kwargs)


def rsync_from_remote(
    remote_path: str,
    local_path: str | Path,
    ssh_target: SSHTarget,
    **kwargs,
) -> bool:
    """Rsync a remote path to a local destination."""
    remote_src = f"{ssh_target.user}@{ssh_target.host}:{remote_path}"
    local = Path(local_path)
    local.mkdir(parents=True, exist_ok=True)
    return rsync_with_retry(remote_src, str(local) + "/", ssh_target, **kwargs)
