"""Persistent session state for decoupled CLI phases."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from .config import SSHTarget

logger = logging.getLogger(__name__)

DEFAULT_SESSION_PATH = Path("session.json")


@dataclass
class Session:
    selection_id: str
    host: str
    port: int
    user: str
    key_file: str
    remote_work_dir: str
    rtl_tag: str
    created_at: str
    mode: str = "batch"
    job_id: str = ""
    ird_server: str = "yyz-ird"
    cluster: str = "tt_aus"
    team: str = "tensix_interactive"
    tensix_host: str | None = None

    def ssh_target(self) -> SSHTarget:
        """SSH target for the compute node (IRD container)."""
        return SSHTarget(
            host=self.host,
            user=self.user,
            port=self.port,
            key_file=Path(self.key_file),
        )

    def ird_ssh_target(self) -> SSHTarget:
        """SSH target for the IRD server (used for ird list/reserve/release)."""
        return SSHTarget(
            host=self.ird_server,
            user=self.user,
            key_file=Path(self.key_file),
        )

    def save(self, path: Path = DEFAULT_SESSION_PATH) -> None:
        data = asdict(self)
        path.write_text(json.dumps(data, indent=2) + "\n")
        logger.info("Session saved to %s", path)

    @classmethod
    def load(cls, path: Path = DEFAULT_SESSION_PATH) -> Session:
        if not path.exists():
            raise FileNotFoundError(
                f"Session file not found: {path}. Run 'deploy' first."
            )
        data = json.loads(path.read_text())
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def create(
        cls,
        selection_id: str,
        host: str,
        port: int,
        user: str,
        key_file: str,
        remote_work_dir: str,
        rtl_tag: str,
        mode: str = "batch",
        job_id: str = "",
        ird_server: str = "yyz-ird",
        cluster: str = "tt_aus",
        team: str = "tensix_interactive",
        tensix_host: str | None = None,
    ) -> Session:
        return cls(
            selection_id=selection_id,
            host=host,
            port=port,
            user=user,
            key_file=key_file,
            remote_work_dir=remote_work_dir,
            rtl_tag=rtl_tag,
            created_at=datetime.now(timezone.utc).isoformat(),
            mode=mode,
            job_id=job_id,
            ird_server=ird_server,
            cluster=cluster,
            team=team,
            tensix_host=tensix_host,
        )
