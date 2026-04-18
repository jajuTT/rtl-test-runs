"""SSH command execution with retry, exponential backoff, and keepalive."""

from __future__ import annotations

import logging
import random
import subprocess
import time

from ..config import SSHTarget

logger = logging.getLogger(__name__)


def ssh_run(
    ssh_target: SSHTarget,
    command: str,
    *,
    max_retries: int = 3,
    base_delay: float = 5.0,
    max_delay: float = 60.0,
    timeout: int = 120,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Execute a command over SSH with retry and exponential backoff.

    Raises subprocess.CalledProcessError on persistent failure if check=True.
    """
    # IRD containers get new host keys every time they are recreated.
    # UserKnownHostsFile=/dev/null avoids "REMOTE HOST IDENTIFICATION HAS
    # CHANGED" errors from stale entries in ~/.ssh/known_hosts.
    # LogLevel=ERROR suppresses the "Warning: Permanently added ..." noise
    # that StrictHostKeyChecking=no would otherwise print on every connection.
    ssh_cmd = [
        "ssh",
        "-p", str(ssh_target.port),
        "-o", "ConnectTimeout=30",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-i", str(ssh_target.key_file),
        f"{ssh_target.user}@{ssh_target.host}",
        command,
    ]

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        logger.info(
            "ssh attempt %d/%d to %s:%d: %s",
            attempt + 1, max_retries, ssh_target.host, ssh_target.port, command,
        )
        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0 or not check:
                return result
            if result.returncode == 255:
                logger.warning("SSH connection error (exit 255): %s", result.stderr.strip())
            else:
                if check:
                    raise subprocess.CalledProcessError(
                        result.returncode, ssh_cmd, result.stdout, result.stderr
                    )
                return result
        except subprocess.TimeoutExpired as e:
            logger.warning("ssh timed out after %ds on attempt %d", timeout, attempt + 1)
            last_exc = e
        except subprocess.CalledProcessError:
            raise
        except OSError as e:
            logger.warning("ssh OS error on attempt %d: %s", attempt + 1, e)
            last_exc = e

        if attempt < max_retries - 1:
            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = random.uniform(0, delay * 0.3)
            sleep_time = delay + jitter
            logger.info("Retrying in %.1fs...", sleep_time)
            time.sleep(sleep_time)

    error_msg = f"ssh failed after {max_retries} attempts to {ssh_target.host}:{ssh_target.port}"
    logger.error(error_msg)
    if last_exc:
        raise ConnectionError(error_msg) from last_exc
    raise ConnectionError(error_msg)


def ssh_run_detached(
    ssh_target: SSHTarget,
    command: str,
    log_file: str = "job.log",
    *,
    max_retries: int = 3,
) -> subprocess.CompletedProcess:
    """Launch a command on the remote host via nohup, fully detached from SSH session."""
    detached_cmd = f"nohup {command} > {log_file} 2>&1 & echo $!"
    return ssh_run(ssh_target, detached_cmd, max_retries=max_retries, check=False)


def scp_to_remote(
    local_path: str,
    remote_path: str,
    ssh_target: SSHTarget,
    *,
    max_retries: int = 3,
    base_delay: float = 5.0,
    timeout: int = 120,
) -> bool:
    """SCP a file to a remote host with retry logic."""
    # Same SSH options as ssh_run — see comment there for rationale.
    scp_cmd = [
        "scp",
        "-P", str(ssh_target.port),
        "-o", "ConnectTimeout=30",
        "-o", "ServerAliveInterval=15",
        "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-i", str(ssh_target.key_file),
        local_path,
        f"{ssh_target.user}@{ssh_target.host}:{remote_path}",
    ]

    for attempt in range(max_retries):
        logger.info("scp attempt %d/%d: %s -> %s", attempt + 1, max_retries, local_path, remote_path)
        try:
            result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0:
                return True
            logger.warning("scp failed (exit %d): %s", result.returncode, result.stderr.strip())
        except subprocess.TimeoutExpired:
            logger.warning("scp timed out on attempt %d", attempt + 1)
        except OSError as e:
            logger.warning("scp OS error on attempt %d: %s", attempt + 1, e)

        if attempt < max_retries - 1:
            delay = min(base_delay * (2 ** attempt), 60.0)
            jitter = random.uniform(0, delay * 0.3)
            time.sleep(delay + jitter)

    logger.error("scp failed after %d attempts", max_retries)
    return False
