"""Ship the remote_worker package to the remote IRD machine and launch it detached."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from ..config import SSHTarget, RTLConfig
from ..transfer.resilient_rsync import rsync_to_remote
from ..transfer.resilient_ssh import ssh_run, ssh_run_detached

logger = logging.getLogger(__name__)


def _build_job_config(config: RTLConfig, remote_work_dir: str) -> dict:
    """Build the job_config.json that the remote worker consumes."""
    return {
        "remote_root_dir_path": config.remote_root_dir_path,
        "remote_root_dir": config.remote_root_dir,
        "git_url": config.git_url,
        "suites": config.suites,
        "yaml_files": config.yaml_files,
        "tests": config.tests,
        "project_yaml": config.project_yaml,
        "debug_dir_path": config.debug_dir_path,
        "debug_dir": config.debug_dir,
        "test_dir_suffix": config.test_dir_suffix,
        "tests_dir": config.tests_dir,
        "isa_file_name": config.isa_file_name,
        "rtl_log_file_suffix": config.rtl_log_file_suffix,
        "sim_result_yaml": config.sim_result_yaml,
        "src_firmware_dir_path": config.src_firmware_dir_path,
        "src_firmware_dir": config.src_firmware_dir,
        "src_hd_proj_dir_path": config.src_hd_proj_dir_path,
        "src_hd_proj_dir": config.src_hd_proj_dir,
        "mode": config.mode,
        "num_processes": config.num_processes,
        "max_test_attempts": config.max_test_attempts,
        "remote_python": config.remote_python,
        "num_bytes_per_register": config.num_bytes_per_register,
        "package_level": config.package_level,
    }


def deploy(
    ssh_target: SSHTarget,
    config: RTLConfig,
    remote_work_dir: str,
    *,
    ird_ssh_target: SSHTarget | None = None,
    selection_id: str | None = None,
) -> None:
    """Deploy the remote_worker to the IRD machine and launch it.

    Args:
        ssh_target: Direct SSH target for the compute node (used for rsync and direct_ssh launch).
        config: RTL configuration.
        remote_work_dir: Remote directory for worker files.
        ird_ssh_target: SSH target for the IRD server (needed for ird_connect launch mode).
        selection_id: IRD selection ID (needed for ird_connect launch mode).
    """

    # 1. Create remote work directory and clean up stale artifacts from previous runs
    logger.info("Creating remote work directory: %s", remote_work_dir)
    ssh_run(ssh_target, f"mkdir -p {remote_work_dir}")
    ssh_run(ssh_target, f"rm -rf {remote_work_dir}/progress {remote_work_dir}/DONE {remote_work_dir}/data_package {remote_work_dir}/job.log", check=False)

    # 2. Write job_config.json locally (temp)
    job_config = _build_job_config(config, remote_work_dir)
    local_config_path = Path("job_config.json")
    local_config_path.write_text(json.dumps(job_config, indent=2) + "\n")

    # 3. Rsync remote_worker/ package to remote
    package_dir = Path(__file__).resolve().parent.parent / "remote_worker"
    if not package_dir.is_dir():
        raise FileNotFoundError(f"remote_worker package not found at {package_dir}")

    logger.info("Syncing remote_worker/ to %s", remote_work_dir)
    success = rsync_to_remote(
        str(package_dir) + "/",
        f"{remote_work_dir}/remote_worker/",
        ssh_target,
    )
    if not success:
        raise ConnectionError("Failed to rsync remote_worker/ to remote")

    # 4. Rsync job_config.json to remote
    logger.info("Syncing job_config.json to %s", remote_work_dir)
    success = rsync_to_remote(
        str(local_config_path),
        f"{remote_work_dir}/",
        ssh_target,
    )
    if not success:
        raise ConnectionError("Failed to rsync job_config.json to remote")

    # 5. Launch the remote worker
    python = config.remote_python
    launch_mode = config.launch_mode
    log_path = f"{remote_work_dir}/job.log"

    if launch_mode == "ird_connect":
        _launch_via_ird_connect(
            ird_ssh_target, selection_id, python, remote_work_dir, log_path,
        )
    else:
        _launch_via_direct_ssh(ssh_target, python, remote_work_dir, log_path)


def _launch_via_ird_connect(
    ird_ssh_target: SSHTarget,
    selection_id: str,
    python: str,
    remote_work_dir: str,
    log_path: str,
) -> None:
    """Launch the remote worker via `ird connect-to`, which sets up the full
    container environment (IRD_VERSION, conda/tek, PATH) automatically."""
    if ird_ssh_target is None or selection_id is None:
        raise ValueError("ird_connect launch mode requires ird_ssh_target and selection_id")

    inner_cmd = f"cd {remote_work_dir} && nohup {python} -m remote_worker job_config.json > {log_path} 2>&1 & echo \\$!"
    # ird connect-to runs a command inside the container with the full environment
    ird_cmd = f"ird connect-to {selection_id} -- bash -c '{inner_cmd}'"
    logger.info("Launching via ird connect-to: %s", ird_cmd)
    result = ssh_run(ird_ssh_target, ird_cmd, check=False, timeout=60)
    pid = result.stdout.strip().splitlines()[-1] if result.stdout else "unknown"
    logger.info("Remote worker launched via ird connect-to with PID: %s", pid)


def _launch_via_direct_ssh(
    ssh_target: SSHTarget,
    python: str,
    remote_work_dir: str,
    log_path: str,
) -> None:
    """Launch the remote worker via direct SSH to the compute node.
    Faster but doesn't set up the container environment — requires the remote
    Python and env vars to be correct without `ird connect-to`."""
    inner_cmd = f"cd {remote_work_dir} && {python} -m remote_worker job_config.json"
    logger.info("Launching via direct SSH: %s (log: %s)", inner_cmd, log_path)
    result = ssh_run_detached(
        ssh_target,
        f"bash -c '{inner_cmd}'",
        log_file=log_path,
    )
    pid = result.stdout.strip() if result.stdout else "unknown"
    logger.info("Remote worker launched via direct SSH with PID: %s", pid)
