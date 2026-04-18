"""IRD reservation management: reserve, release, list.

Key design changes from the old ird_polaris.py:
- No release-all on startup. Only the current session's instance is tracked.
- Context manager for guaranteed release of the reserved instance.
- Retry logic on reserve/list/release commands.
- Selection ID logged prominently for manual recovery.
"""

from __future__ import annotations

import contextlib
import logging
import re
import time
from dataclasses import dataclass

from .config import SSHTarget
from .transfer.resilient_ssh import ssh_run

logger = logging.getLogger(__name__)


@dataclass
class IRDInstance:
    selection_id: str
    host: str
    port: int
    job_id: str = ""


def ird_list(ssh_target: SSHTarget, max_retries: int = 3) -> list[dict[str, str]]:
    """Get the list of current IRD reservations."""
    result = ssh_run(
        ssh_target,
        "ird list",
        max_retries=max_retries,
        check=False,
    )

    if result.returncode != 0:
        logger.warning("ird list returned non-zero exit code: %d", result.returncode)
        return []

    lines = result.stdout.strip().splitlines()
    if len(lines) < 2:
        return []

    cols = re.split(r"\s{2,}", lines[0].strip())
    data = [dict(zip(cols, re.split(r"\s{2,}", line.strip()))) for line in lines[1:] if line.strip()]
    return data


def _parse_port(raw: str) -> int | None:
    """Parse an SSH PORT value, returning None for empty or ``(null)``."""
    if not raw or raw == "(null)":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def ird_reserve(
    ssh_target: SSHTarget,
    cluster: str = "tt_aus",
    team: str = "tensix_interactive",
    machine: str | None = None,
    max_retries: int = 3,
) -> IRDInstance:
    """Reserve a new IRD instance. Does NOT release existing instances."""

    cmd = (
        f'ird reserve --cluster={cluster} --team={team} '
        f'--timeout="max" --docker-image=centos7 compute'
    )
    if machine:
        cmd += f" --machine={machine}"

    logger.info("Reserving IRD instance: %s", cmd)
    ssh_run(ssh_target, cmd, max_retries=max_retries, timeout=300)

    reservations = ird_list(ssh_target, max_retries=max_retries)
    if not reservations:
        raise RuntimeError("IRD reserve succeeded but no reservations found in ird list")

    latest = reservations[-1]
    port = _parse_port(latest.get("SSH PORT", ""))
    if port is None:
        host = latest.get("MACHINE", "?")
        sel = latest.get("SELECTION ID", "?")
        raise RuntimeError(
            f"IRD reservation landed on {host} but its SSH PORT is "
            f"'{latest.get('SSH PORT', '')}' (container failed to start). "
            f"Release it manually with: ssh {ssh_target.host} 'ird release {sel}'\n"
            f"Then re-run with --machine=<working-host> or set tensix_host "
            f"in your config to pin to a healthy machine."
        )

    instance = IRDInstance(
        selection_id=latest["SELECTION ID"],
        host=latest["MACHINE"],
        port=port,
        job_id=latest.get("JOB ID", ""),
    )

    logger.info(
        "========================================\n"
        "  IRD INSTANCE RESERVED\n"
        "  Job ID       : %s\n"
        "  Selection ID : %s\n"
        "  Machine      : %s\n"
        "  SSH Port     : %d\n"
        "  Manual release: ssh %s 'ird release %s'\n"
        "========================================",
        instance.job_id, instance.selection_id, instance.host, instance.port,
        ssh_target.host, instance.selection_id,
    )

    return instance


def ird_release(
    ssh_target: SSHTarget,
    selection_id: str,
    max_retries: int = 3,
) -> None:
    """Release a specific IRD instance by selection ID."""
    logger.info("Releasing IRD instance: %s", selection_id)
    try:
        ssh_run(
            ssh_target,
            f"ird release {selection_id}",
            max_retries=max_retries,
            check=False,
        )
        logger.info("IRD instance %s released successfully", selection_id)
    except ConnectionError:
        logger.error(
            "Failed to release IRD instance %s. "
            "Manual cleanup: ssh %s 'ird release %s'",
            selection_id, ssh_target.host, selection_id,
        )
        raise


def ird_lookup_job(ssh_target: SSHTarget, job_id: str) -> IRDInstance | None:
    """Find an active reservation by stable JOB ID.

    Host and SSH port are stable for a given JOB ID; only SELECTION ID is
    ephemeral and can shift as other reservations come and go.
    Returns None if the job is not listed or its container never started.
    """
    if not job_id:
        return None
    for row in ird_list(ssh_target):
        if row.get("JOB ID") == job_id:
            port = _parse_port(row.get("SSH PORT", ""))
            if port is None:
                logger.warning("JOB ID %s found but container not ready (port=%s)",
                               job_id, row.get("SSH PORT", "?"))
                return None
            return IRDInstance(
                selection_id=row["SELECTION ID"],
                host=row["MACHINE"],
                port=port,
                job_id=row["JOB ID"],
            )
    return None


def ird_lookup_reservation(
    ssh_target: SSHTarget,
    tensix_host: str | None = None,
    user: str | None = None,
) -> IRDInstance | None:
    """Find the first live reservation matching the given filters.

    Used to bootstrap a session when ``session.json`` is absent: instead of
    reserving a brand-new instance, adopt an existing one the user already has.

    Filters:
      * ``tensix_host`` — if set, only rows where ``MACHINE`` matches are
        considered.  If unset, any machine is acceptable.
      * ``user`` — if set and the ``USER`` column exists, only rows for that
        user are considered.  (Normally ``ird list`` already filters by the
        SSH user, but be defensive.)

    Rows whose SSH PORT is ``(null)`` (container never started) are skipped.
    Returns ``None`` if no matching live reservation is found.
    """
    for row in ird_list(ssh_target):
        if user and row.get("USER") and row.get("USER") != user:
            continue
        if tensix_host and row.get("MACHINE") != tensix_host:
            continue
        port = _parse_port(row.get("SSH PORT", ""))
        if port is None:
            continue
        return IRDInstance(
            selection_id=row["SELECTION ID"],
            host=row["MACHINE"],
            port=port,
            job_id=row.get("JOB ID", ""),
        )
    return None


def ird_release_by_job(
    ssh_target: SSHTarget,
    job_id: str,
    max_retries: int = 3,
) -> None:
    """Release an IRD instance by looking up its current selection_id from JOB ID.

    Safe no-op (with warning) if the job is already gone.
    """
    instance = ird_lookup_job(ssh_target, job_id)
    if instance is None:
        logger.warning("JOB ID %s not found in ird list — already released?", job_id)
        return
    ird_release(ssh_target, instance.selection_id, max_retries=max_retries)


@contextlib.contextmanager
def ird_session(
    ssh_target: SSHTarget,
    cluster: str = "tt_aus",
    team: str = "tensix_interactive",
    machine: str | None = None,
):
    """Context manager that reserves an IRD instance and guarantees release.

    Usage:
        with ird_session(ssh_target) as instance:
            # instance.selection_id, instance.host, instance.port
            ...
        # instance is released here, even on exception
    """
    instance = None
    try:
        instance = ird_reserve(ssh_target, cluster, team, machine)
        yield instance
    finally:
        if instance is not None:
            try:
                ird_release(ssh_target, instance.selection_id)
            except Exception:
                logger.error(
                    "Failed to release IRD instance %s. "
                    "Manual cleanup: ssh %s 'ird release %s'",
                    instance.selection_id, ssh_target.host, instance.selection_id,
                )
