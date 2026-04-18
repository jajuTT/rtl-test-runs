"""Run command: convenience chain of deploy -> status --watch -> pull -> analyze -> release."""

from __future__ import annotations

import logging
from pathlib import Path

from ..ird_reservation import ird_release_by_job
from .deploy import deploy as deploy_cmd
from .status import status as status_cmd
from .pull import pull as pull_cmd
from .analyze import analyze as analyze_cmd

logger = logging.getLogger(__name__)


def run(
    config_path: str,
    local_dir: str = ".",
    session_path: Path = Path("session.json"),
) -> None:
    """Full pipeline: deploy, wait, pull, analyze, release."""
    session = deploy_cmd(config_path, session_path)

    try:
        print("\nWaiting for remote job to complete...")
        status_cmd(session, watch=True, session_path=session_path,
                   config_path=config_path)

        print("\nPulling data package...")
        pull_cmd(session, local_dir, session_path=session_path,
                 config_path=config_path)

        print("\nRunning analysis...")
        analyze_cmd(local_dir, config_path)  # uses defaults: polaris_big/, copy

    finally:
        print("\nReleasing IRD instance...")
        try:
            ird_release_by_job(session.ird_ssh_target(), session.job_id)
            print(f"IRD job {session.job_id} released")
        except Exception:
            logger.error(
                "Failed to release IRD job %s. Run: python -m ird.cli release",
                session.job_id,
            )
