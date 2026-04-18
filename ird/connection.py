"""Ensure an active IRD reservation before running a CLI stage."""

from __future__ import annotations

import logging
from pathlib import Path

from .ird_reservation import ird_lookup_job, ird_lookup_reservation, ird_reserve
from .session import Session

logger = logging.getLogger(__name__)


def apply_config_overrides(session: Session, config_path: str | None) -> Session:
    """If a config file is provided, override reservation fields in session."""
    if config_path is None:
        return session
    from .config import load_config
    rtl_config, _ = load_config(config_path)
    session.tensix_host = rtl_config.tensix_host
    session.ird_server = rtl_config.ird_server
    session.cluster = rtl_config.ird_cluster
    session.team = rtl_config.ird_team
    logger.info("Applied config overrides from %s (tensix_host=%s)",
                config_path, rtl_config.tensix_host)
    return session


def ensure_reservation(
    session: Session,
    session_path: Path,
) -> tuple[Session, bool]:
    """Guarantee an active IRD reservation, returning (session, acquired_new).

    1. Look up ``session.job_id`` in ``ird list``.
       - If found, refresh ``session.selection_id`` (the only value that may
         have shifted) and return ``acquired_new=False``.
    2. If not found (reservation expired / released), reserve a fresh instance,
       update session with the new job_id / selection_id / host / port, and
       return ``acquired_new=True``.  The caller is responsible for releasing
       the new reservation when done.
    3. Persist the updated session to *session_path* in both cases.
    """
    ird_tgt = session.ird_ssh_target()

    instance = ird_lookup_job(ird_tgt, session.job_id)

    if instance is not None:
        if session.selection_id != instance.selection_id:
            logger.info(
                "Refreshed selection_id: %s -> %s (job %s still alive)",
                session.selection_id, instance.selection_id, session.job_id,
            )
            session.selection_id = instance.selection_id
            session.save(session_path)
        else:
            logger.info("IRD reservation %s still active", session.job_id)
        return session, False

    logger.warning(
        "IRD reservation %s no longer active — reserving a new instance",
        session.job_id or "(none)",
    )
    instance = ird_reserve(
        ird_tgt,
        cluster=session.cluster,
        team=session.team,
        machine=session.tensix_host,
    )

    session.job_id = instance.job_id
    session.selection_id = instance.selection_id
    session.host = instance.host
    session.port = instance.port
    session.save(session_path)

    return session, True


def bootstrap_session_from_config(config_path: str, session_path: Path) -> Session:
    """Build a fresh ``session.json`` from ``run_config.json`` alone.

    Used by ``status`` / ``pull`` / ``release`` / ``repackage`` when the user
    runs them without having first run ``deploy`` in this shell (e.g. they
    already ran the tests earlier and just want to repackage / pull).

    Behaviour:
      1. Construct a partial ``Session`` from the config (user, key_file,
         remote_work_dir, rtl_tag, ird_server, cluster, team, tensix_host…).
         Reservation-specific fields (job_id, selection_id, host, port) are
         initially blank.
      2. Look up an existing live reservation via ``ird list`` on the IRD
         server, pinned to the config's ``tensix_host`` (if set) and filtered
         to this user.  If found — adopt it.
      3. Otherwise reserve a new one on ``tensix_host``.
      4. Persist the completed session to *session_path* and return it.

    The caller never has to know whether a new reservation was acquired —
    downstream commands just use the session as usual.  (Unlike
    ``ensure_reservation``, we do NOT signal ``acquired_new`` here; a session
    bootstrapped this way is treated as owned by the user from here on, and
    will only be released if the user explicitly runs ``ird release``.)
    """
    from .config import load_config

    rtl_config, _ = load_config(config_path)
    remote_work_dir = rtl_config.remote_root_dir_path.rstrip("/") + "/_rtl_job"

    session = Session.create(
        selection_id="",
        host="",
        port=0,
        user=rtl_config.username,
        key_file=str(rtl_config.ssh_key_file),
        remote_work_dir=remote_work_dir,
        rtl_tag=rtl_config.rtl_tag,
        mode=rtl_config.mode,
        job_id="",
        ird_server=rtl_config.ird_server,
        cluster=rtl_config.ird_cluster,
        team=rtl_config.ird_team,
        tensix_host=rtl_config.tensix_host,
    )

    logger.info(
        "No session.json found — bootstrapping from %s (tensix_host=%s)",
        config_path, rtl_config.tensix_host,
    )
    ird_tgt = session.ird_ssh_target()

    instance = ird_lookup_reservation(
        ird_tgt,
        tensix_host=rtl_config.tensix_host,
        user=rtl_config.username,
    )

    if instance is not None:
        logger.info(
            "Adopting existing IRD reservation: job=%s selection=%s machine=%s:%d",
            instance.job_id, instance.selection_id, instance.host, instance.port,
        )
    else:
        logger.info(
            "No live IRD reservation found for user=%s tensix_host=%s — reserving a new one",
            rtl_config.username, rtl_config.tensix_host,
        )
        instance = ird_reserve(
            ird_tgt,
            cluster=rtl_config.ird_cluster,
            team=rtl_config.ird_team,
            machine=rtl_config.tensix_host,
        )

    session.selection_id = instance.selection_id
    session.host = instance.host
    session.port = instance.port
    session.job_id = instance.job_id
    session.save(session_path)
    return session


def load_or_bootstrap_session(
    session_path: Path,
    config_path: str | None,
) -> Session:
    """Load ``session.json`` if present; else bootstrap from ``--config``.

    Raises a clear ``FileNotFoundError`` if neither path is usable so the user
    knows to either run ``deploy`` first or pass ``--config``.
    """
    if session_path.exists():
        return Session.load(session_path)
    if config_path is None:
        raise FileNotFoundError(
            f"Session file not found: {session_path}. "
            f"Run 'deploy' first, or pass --config to bootstrap from config."
        )
    return bootstrap_session_from_config(config_path, session_path)
