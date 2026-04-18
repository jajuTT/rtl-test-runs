"""Pull the data_package/ from the remote to a local directory."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from ..connection import apply_config_overrides, ensure_reservation
from ..ird_reservation import ird_release_by_job
from ..session import Session
from ..transfer.resilient_rsync import rsync_from_remote

logger = logging.getLogger(__name__)


def pull(
    session: Session,
    local_dir: str | Path,
    *,
    session_path: Path = Path("session.json"),
    config_path: str | None = None,
    max_retries: int = 5,
) -> None:
    """Rsync data_package/ from the remote into <local_dir>/<rtl_tag>/."""
    apply_config_overrides(session, config_path)
    session, acquired = ensure_reservation(session, session_path)
    try:
        _do_pull(session, local_dir, max_retries=max_retries)
    finally:
        if acquired:
            ird_release_by_job(session.ird_ssh_target(), session.job_id)


def _do_pull(
    session: Session,
    local_dir: str | Path,
    *,
    max_retries: int = 5,
) -> None:
    local_path = Path(local_dir)
    tag_dir = local_path / session.rtl_tag

    _clean_local_tag_dir(tag_dir)
    tag_dir.mkdir(parents=True, exist_ok=True)

    target = session.ssh_target()
    remote_data_pkg = f"{session.remote_work_dir}/data_package/"

    logger.info("Pulling data package from %s to %s", remote_data_pkg, tag_dir)
    success = rsync_from_remote(
        remote_data_pkg,
        tag_dir,
        target,
        max_retries=max_retries,
    )

    if not success:
        raise ConnectionError(
            f"Failed to pull data_package from {session.host}:{remote_data_pkg}. "
            "Check connectivity and retry with: python -m ird.cli pull"
        )

    logger.info("Data package pulled successfully to %s", tag_dir)
    _verify_package(tag_dir)


def _clean_local_tag_dir(tag_dir: Path) -> None:
    """Remove a previous local tag directory so the pull starts clean."""
    if not tag_dir.exists():
        return
    backup = tag_dir.with_name(tag_dir.name + ".bak")
    if backup.exists():
        shutil.rmtree(backup)
    tag_dir.rename(backup)
    logger.info("Moved old %s -> %s", tag_dir, backup)


def _verify_package(tag_dir: Path) -> None:
    """Basic completeness check on the pulled data package."""
    ws = tag_dir / "ws-tensix"
    checks = {
        "git_commit_id.txt": (tag_dir / "git_commit_id.txt").is_file(),
        "ws-tensix/": ws.is_dir(),
        "ws-tensix/rsim/debug/": (ws / "rsim" / "debug").is_dir(),
    }

    all_ok = True
    for name, present in checks.items():
        status_str = "OK" if present else "MISSING"
        if not present:
            all_ok = False
        logger.info("  %s: %s", name, status_str)

    if all_ok:
        print(f"Data package verified: {tag_dir}")
    else:
        print(f"WARNING: Data package may be incomplete at {tag_dir}")
