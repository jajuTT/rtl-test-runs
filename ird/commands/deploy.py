"""Deploy command: reserve IRD, ship remote_worker, launch, write session.json."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

from ..config import RTLConfig, load_config
from ..ird_reservation import ird_reserve
from ..remote.deployer import deploy as _deploy
from ..session import Session

logger = logging.getLogger(__name__)


def deploy(config_path: str, session_path: Path = Path("session.json")) -> Session:
    """Reserve an IRD instance, deploy the remote worker, and save the session."""
    rtl_config, model_config = load_config(config_path)

    ssh_ird = rtl_config.ird_ssh_target()

    logger.info("Reserving IRD instance via %s", ssh_ird.host)
    instance = ird_reserve(
        ssh_ird,
        cluster=rtl_config.ird_cluster,
        team=rtl_config.ird_team,
        machine=rtl_config.tensix_host,
    )

    remote_work_dir = rtl_config.remote_root_dir_path + "/_rtl_job"

    session = Session.create(
        selection_id=instance.selection_id,
        host=instance.host,
        port=instance.port,
        user=rtl_config.username,
        key_file=str(rtl_config.ssh_key_file),
        remote_work_dir=remote_work_dir,
        rtl_tag=rtl_config.rtl_tag,
        mode=rtl_config.mode,
        job_id=instance.job_id,
        ird_server=rtl_config.ird_server,
        cluster=rtl_config.ird_cluster,
        team=rtl_config.ird_team,
        tensix_host=rtl_config.tensix_host,
    )

    remote_target = session.ssh_target()

    logger.info("Deploying remote worker to %s:%s", instance.host, remote_work_dir)
    _deploy(
        remote_target,
        rtl_config,
        remote_work_dir,
        ird_ssh_target=ssh_ird,
        selection_id=instance.selection_id,
    )

    session.save(session_path)
    print(f"IRD reserved: job={instance.job_id} sel={instance.selection_id} "
          f"at {instance.host}:{instance.port}")
    print(f"Session saved to {session_path}")

    return session
