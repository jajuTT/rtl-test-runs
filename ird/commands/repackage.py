"""Repackage command: rebuild data_package/ on remote without re-running tests."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..config import load_config
from ..connection import apply_config_overrides, ensure_reservation
from ..ird_reservation import ird_release_by_job
from ..session import Session
from ..transfer.resilient_rsync import rsync_to_remote
from ..transfer.resilient_ssh import ssh_run

logger = logging.getLogger(__name__)


# Shared prefix that resolves $PYTHON from the remote job_config.json.
# The system python3 on IRD containers is too old (3.6); the conda python
# (e.g. /opt/miniconda3/bin/python) supports modern syntax.
_PYTHON_PREFIX = (
    "PYTHON=$(python3 -c \"import json; "
    "print(json.load(open('job_config.json')).get('remote_python','python3'))\")"
)


def repackage(
    session: Session,
    *,
    session_path: Path = Path("session.json"),
    config_path: str | None = None,
) -> None:
    """Sync updated remote_worker code and re-run data_packager on the remote.

    Useful after changing data_packager.py locally, or when you need to
    rebuild data_package/ without re-running rsim tests.
    """
    apply_config_overrides(session, config_path)
    session, acquired = ensure_reservation(session, session_path)
    try:
        _do_repackage(session, config_path=config_path)
    finally:
        if acquired:
            ird_release_by_job(session.ird_ssh_target(), session.job_id)


def _do_repackage(session: Session, *, config_path: str | None = None) -> None:
    target = session.ssh_target()
    remote_work_dir = session.remote_work_dir

    package_dir = Path(__file__).resolve().parent.parent / "remote_worker"
    if not package_dir.is_dir():
        raise FileNotFoundError(f"remote_worker package not found at {package_dir}")

    print("Syncing remote_worker/ to remote...")
    success = rsync_to_remote(
        str(package_dir) + "/",
        f"{remote_work_dir}/remote_worker/",
        target,
    )
    if not success:
        raise ConnectionError("Failed to rsync remote_worker/ to remote")

    if config_path is not None:
        _patch_remote_job_config(session, config_path)

    _ensure_remote_vendor(session)

    packager_cmd = (
        f"cd {remote_work_dir} && "
        f"{_PYTHON_PREFIX} && "
        f"$PYTHON -c '"
        f"import json, sys; "
        f"config = json.load(open(\"job_config.json\")); "
        f"sys.path.insert(0, \".\"); "
        f"from remote_worker import data_packager; "
        f"data_packager.package(config)"
        f"'"
    )

    print("Running data_packager on remote...")
    logger.info("Executing packager on %s:%s", session.host, remote_work_dir)
    result = ssh_run(target, packager_cmd, check=False, timeout=300)

    if result.returncode != 0:
        logger.error("Packager stderr: %s", result.stderr.strip())
        raise RuntimeError(
            f"Remote data_packager failed (exit {result.returncode}). "
            f"Check logs on {session.host}:{remote_work_dir}"
        )

    print(f"Data package rebuilt on {session.host}:{remote_work_dir}/data_package/")
    logger.info("Repackage complete")


def _patch_remote_job_config(session: Session, config_path: str) -> None:
    """Update packaging-behavior fields in the remote job_config.json.

    Only rewrites ``package_level`` and ``num_bytes_per_register`` so that a
    fresh run_config edit propagates to the remote packager. Leaves all other
    deployment state (paths, tests, tensix_host, etc.) untouched.
    """
    rtl_config, _ = load_config(config_path)

    new_values = {
        "package_level": rtl_config.package_level,
        "num_bytes_per_register": rtl_config.num_bytes_per_register,
    }
    encoded = json.dumps(new_values)

    patch_script = (
        "import json, sys\n"
        "updates = json.loads(sys.argv[1])\n"
        "with open(\"job_config.json\") as f:\n"
        "    cfg = json.load(f)\n"
        "cfg.update(updates)\n"
        "with open(\"job_config.json\", \"w\") as f:\n"
        "    json.dump(cfg, f, indent=2)\n"
        "    f.write(\"\\n\")\n"
    )

    cmd = (
        f"cd {session.remote_work_dir} && "
        f"{_PYTHON_PREFIX} && "
        f"$PYTHON -c {_shell_quote(patch_script)} {_shell_quote(encoded)}"
    )

    logger.info(
        "Patching remote job_config.json: package_level=%s num_bytes_per_register=%s",
        rtl_config.package_level, rtl_config.num_bytes_per_register,
    )
    result = ssh_run(session.ssh_target(), cmd, check=False, timeout=60)
    if result.returncode != 0:
        logger.error("Patch stderr: %s", result.stderr.strip())
        raise RuntimeError(
            f"Failed to patch remote job_config.json (exit {result.returncode})"
        )


def _ensure_remote_vendor(session: Session) -> None:
    """Make sure remote_worker/vendor/ exists on the remote.

    Calls ``remote_worker.setup._install_vendor_deps()`` which is idempotent
    (short-circuits on ``vendor/.installed``). This fixes pre-existing
    deployments that were created before the vendor dep was introduced.
    """
    bootstrap_script = (
        "import sys\n"
        "sys.path.insert(0, \".\")\n"
        "from remote_worker.setup import _install_vendor_deps\n"
        "_install_vendor_deps()\n"
    )

    cmd = (
        f"cd {session.remote_work_dir} && "
        f"{_PYTHON_PREFIX} && "
        f"$PYTHON -c {_shell_quote(bootstrap_script)}"
    )

    logger.info("Ensuring remote_worker/vendor/ is installed on %s", session.host)
    result = ssh_run(session.ssh_target(), cmd, check=False, timeout=180)
    if result.returncode != 0:
        logger.error("Vendor bootstrap stderr: %s", result.stderr.strip())
        raise RuntimeError(
            f"Failed to install remote vendor deps (exit {result.returncode})"
        )


def _shell_quote(s: str) -> str:
    """Wrap *s* in single quotes for safe inclusion in a bash command string."""
    return "'" + s.replace("'", "'\"'\"'") + "'"
