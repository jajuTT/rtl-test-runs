"""Release command: release the IRD instance from session.json."""

from __future__ import annotations

import logging
from pathlib import Path

from ..connection import apply_config_overrides, load_or_bootstrap_session
from ..ird_reservation import ird_release_by_job

logger = logging.getLogger(__name__)


def release(
    session_path: Path = Path("session.json"),
    config_path: str | None = None,
) -> None:
    """Release the IRD instance recorded in session.json."""
    session = load_or_bootstrap_session(session_path, config_path)
    apply_config_overrides(session, config_path)

    logger.info("Releasing IRD job %s (selection %s)", session.job_id, session.selection_id)
    ird_release_by_job(session.ird_ssh_target(), session.job_id)
    print(f"IRD job {session.job_id} released")
