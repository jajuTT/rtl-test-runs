"""Typed configuration dataclasses replacing untyped dict configs."""

from __future__ import annotations

import getpass
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class SSHTarget:
    host: str
    user: str
    port: int = 22
    key_file: Path = field(default_factory=lambda: Path("~/.ssh/id_ed25519").expanduser())

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["key_file"] = str(d["key_file"])
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SSHTarget:
        d = dict(d)
        d["key_file"] = Path(d["key_file"])
        return cls(**d)


@dataclass
class RTLConfig:
    rtl_tag: str
    remote_root_dir_path: str
    remote_root_dir: str = "ws-tensix"
    git_url: str = "git@yyz-gitlab.local.tenstorrent.com:tensix/tensix-hw/ws-tensix.git"
    suites: str = "postcommit"
    tags: list[str] | None = None
    tests: list[str] | None = None
    yaml_files: dict[str, dict[str, str]] = field(default_factory=dict)
    debug_dir_path: str = "rsim"
    debug_dir: str = "debug"
    force: bool = False
    ird_server: str = "yyz-ird"
    ird_cluster: str = "tt_aus"
    ird_team: str = "tensix_interactive"
    isa_file_name: str = "assembly.yaml"
    max_num_threads_per_neo_core: int = 4
    num_processes: int = 11
    project_yaml: str = "project.yml"
    rtl_log_file_suffix: str = ".rtl_test.log"
    sim_result_yaml: str = "sim_result.yml"
    sim_result_key: str = "res"
    sim_result_pass_value: str = "PASS"
    src_dir: str = "src"
    src_firmware_dir_path: str = "src"
    src_firmware_dir: str = "firmware"
    src_hd_proj_dir_path: str = "src/hardware/tensix"
    src_hd_proj_dir: str = "proj"
    test_dir_suffix: str = "_0"
    tests_dir: str = "infra/tensix/rsim/tests"
    num_bytes_per_register: int = 4
    username: str = field(default_factory=getpass.getuser)
    ssh_key_file: Path = field(default_factory=lambda: Path("~/.ssh/id_ed25519").expanduser())
    local_root_dir_path: str = field(default_factory=os.getcwd)
    mode: str = "batch"
    max_test_attempts: int = 1
    tensix_host: str | None = None
    # Non-interactive SSH skips .bashrc, so /usr/bin/python (2.7) is the default.
    # Use the full path to the Python 3 interpreter on the remote IRD containers.
    remote_python: str = "/opt/miniconda3/bin/python"
    # "ird_connect" launches the worker via `ird connect-to` which sets up the
    # full container environment (IRD_VERSION, conda/tek, PATH).  This is the
    # recommended mode.  "direct_ssh" uses plain SSH to the compute node —
    # faster but requires manual env setup (IRD_VERSION, correct Python, etc.).
    launch_mode: str = "ird_connect"
    package_level: str = "minimal"
    # Previous RTL tag — used by the polaris_big patcher as:
    #   (a) anchor in the TTQSTags enum to locate the insertion point,
    #   (b) source for the seeded ttqs_neo4_<rtl_tag>.json config.
    previous_rtl_tag: str = "feb20"

    @property
    def local_root_dir(self) -> str:
        return f"from-{self.remote_root_dir}-{self.rtl_tag}"

    def ird_ssh_target(self) -> SSHTarget:
        return SSHTarget(
            host=self.ird_server,
            user=self.username,
            key_file=self.ssh_key_file,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ssh_key_file"] = str(d["ssh_key_file"])
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RTLConfig:
        d = dict(d)
        d["ssh_key_file"] = Path(d.get("ssh_key_file", "~/.ssh/id_ed25519")).expanduser()
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ModelConfig:
    git_url: str = "git@github.com:tenstorrent/polaris_big.git"
    git_branch: str = "main"
    instruction_kind: str = "ttqs"
    force: bool = False
    num_processes: int = 11
    start_function: str = "main"
    debug: int = 15

    cfg_enable_shared_l1: int = 1
    cfg_enable_sync: int = 1
    cfg_global_pointer: str = "0xffb007f0"
    cfg_latency_l1: float = 10.0
    cfg_order_scheme: list[list[int]] = field(
        default_factory=lambda: [[0, 1], [0, 1], [0, 2, 3], []]
    )
    cfg_risc_cpi: float = 1.0
    cfg_stack: dict[str, list[str]] = field(default_factory=lambda: {
        "0": ["0x8023FF", "0x802000"],
        "1": ["0x801FFF", "0x801C00"],
        "2": ["0x801BFF", "0x801800"],
        "3": ["0x8017FF", "0x801400"],
    })

    cfg_file_prefix: str = "cfg"
    memory_map_file_prefix: str = "memory_map"
    inputcfg_file_prefix: str = "inputcfg_"
    log_file_suffix: str = ".model_test.log"
    simreport_prefix: str = "simreport_"
    log_file_end_marker: str = "Simreport = "
    instruction_sets_dir: str = "instructions_sets"

    engines_mnemonics: dict[str, list[str]] = field(default_factory=lambda: {
        "PACKER0": ["PUSH_TILES"],
        "UNPACKER0": [
            "POP_TILES", "UNPACR_DEST_TILE", "UNPACR_DEST_TILE_INC",
            "UNPACR_DEST_FACE", "UNPACR_DEST_FACE_INC",
            "UNPACR_DEST_ROW", "UNPACR_DEST_ROW_INC", "UNPACR_DEST_STRIDE",
        ],
    })

    @property
    def root_dir(self) -> str:
        return self.git_url.split("/")[-1].removesuffix(".git")

    def cfg_dir(self, rtl_tag: str) -> str:
        return f"__config_files_{rtl_tag}"

    def odir(self, rtl_tag: str) -> str:
        return f"__llk_{rtl_tag}"

    def logs_dir(self, rtl_tag: str) -> str:
        return f"__logs_{rtl_tag}"

    def default_cfg_file_name(self, rtl_tag: str) -> str:
        return f"ttqs_neo4_{rtl_tag}.json"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ModelConfig:
        d = dict(d)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def load_config(config_path: str | Path) -> tuple[RTLConfig, ModelConfig]:
    with open(config_path) as f:
        data = json.load(f)

    rtl = RTLConfig.from_dict(data.get("rtl", {}))
    model = ModelConfig.from_dict(data.get("model", {}))
    return rtl, model


def save_config(rtl: RTLConfig, model: ModelConfig, config_path: str | Path) -> None:
    data = {"rtl": rtl.to_dict(), "model": model.to_dict()}
    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)
