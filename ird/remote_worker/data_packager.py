"""Assemble the data_package/ directory on the remote for local pull."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_PACKAGE_LEVELS = {"minimal", "comprehensive"}


def package(config: dict) -> None:
    """Assemble the data_package/ directory mirroring the ws-tensix repo layout.

    Supports two package levels (set via config["package_level"]):
      - "minimal"        (default) ELFs, assembly.yaml, memory_map.json, sim_result.yml
      - "comprehensive"  everything needed for debugging
    """
    package_level = config.get("package_level", "minimal")
    if package_level not in VALID_PACKAGE_LEVELS:
        raise ValueError(
            f"Invalid package_level '{package_level}', "
            f"expected one of {sorted(VALID_PACKAGE_LEVELS)}"
        )

    ws_path = config.get("ws_tensix_path") or os.path.join(
        config["remote_root_dir_path"], config.get("remote_root_dir", "ws-tensix")
    )
    data_pkg = Path("data_package")
    ws_root = data_pkg / "ws-tensix"

    _clean_old_package(data_pkg)

    logger.info("Packaging at level: %s", package_level)

    # --- always included (both levels) ---
    _package_git_commit(data_pkg, ws_root, ws_path)
    _package_meta(ws_root, ws_path, config)
    _package_memory_map(ws_root, ws_path, config)
    _package_tests_common(ws_root, ws_path, config)

    # --- comprehensive only ---
    if package_level == "comprehensive":
        _package_src(ws_root, ws_path, config)
        _package_tests_debug(ws_root, ws_path, config)

    job_config_path = Path("job_config.json")
    if job_config_path.exists():
        data_pkg.mkdir(parents=True, exist_ok=True)
        shutil.copy2(job_config_path, data_pkg / "job_config.json")

    logger.info("Data package assembled at %s (level=%s)", data_pkg, package_level)


# ---------------------------------------------------------------------------
# Helpers used by both levels
# ---------------------------------------------------------------------------

def _clean_old_package(data_pkg: Path) -> None:
    """Remove a previous data_package/ so the new build starts clean."""
    if not data_pkg.exists():
        return
    backup = data_pkg.with_name(data_pkg.name + ".bak")
    if backup.exists():
        shutil.rmtree(backup)
    data_pkg.rename(backup)
    logger.info("Moved old %s -> %s", data_pkg, backup)


def _package_git_commit(data_pkg: Path, ws_root: Path, ws_path: str) -> None:
    """Write git commit ID in both the legacy and new locations."""
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, cwd=ws_path,
    )
    commit_id = result.stdout.strip() if result.returncode == 0 else "unknown"

    data_pkg.mkdir(parents=True, exist_ok=True)
    (data_pkg / "git_commit_id.txt").write_text(commit_id + "\n")

    ws_root.mkdir(parents=True, exist_ok=True)
    (ws_root / "rtl_git_commit_id.txt").write_text(commit_id + "\n")

    logger.info("Captured git commit ID: %s", commit_id)


def _package_meta(ws_root: Path, ws_path: str, config: dict) -> None:
    """meta/: assembly.yaml in its original repo path (ws-tensix/src/meta/...)."""
    isa_name = config.get("isa_file_name", "assembly.yaml")
    isa_rel_hint = os.path.join("meta", "instructions", "yaml", isa_name)
    isa_src = _find_file(ws_path, isa_rel_hint)
    if isa_src:
        # Mirror the actual repo-relative path (e.g. src/meta/instructions/yaml/...)
        # rather than the legacy hint path.
        dest_rel = os.path.relpath(isa_src, ws_path)
        dest = ws_root / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(isa_src, dest)
        logger.info("Copied %s -> %s", isa_name, dest)


def _package_memory_map(ws_root: Path, ws_path: str, config: dict) -> None:
    """Generate memory_map.json from the ws-tensix HTML/cfg_defines sources.

    Always runs regardless of package_level so consumers can rely on a stable
    artifact path. The destination mirrors the repo layout
    (ws-tensix/src/meta/instructions/yaml/memory_map.json). Raises on failure
    — the memory map is a required artifact, so a silent skip would mask
    broken deployments.
    """
    num_bytes = config.get("num_bytes_per_register", 4)
    dest = ws_root / "src" / "meta" / "instructions" / "yaml" / "memory_map.json"
    dest.parent.mkdir(parents=True, exist_ok=True)

    vendor_dir = os.path.join(os.path.dirname(__file__), "vendor")
    if os.path.isdir(vendor_dir) and vendor_dir not in sys.path:
        sys.path.insert(0, vendor_dir)

    # Scope the walk to ws-tensix/src/ so we don't pick up unrelated cfg_defines.h
    # under deps/ (e.g. deps/tt_noc/legacy_firmware/riscv/common/cfg_defines.h).
    src_root = os.path.join(ws_path, "src")
    if not os.path.isdir(src_root):
        raise FileNotFoundError(
            f"Memory map generation needs {src_root} but it does not exist"
        )

    from . import registers_utils
    registers_utils.write_memory_map(src_root, num_bytes, str(dest))
    logger.info("Generated memory map at %s", dest)


def _package_tests_common(ws_root: Path, ws_path: str, config: dict) -> None:
    """Per-test essentials: sim_result.yml and .elf files (both levels)."""
    debug_dir_path = config.get("debug_dir_path", "rsim")
    debug_dir = config.get("debug_dir", "debug")
    test_dir_suffix = config.get("test_dir_suffix", "_0")
    sim_result_name = config.get("sim_result_yaml", "sim_result.yml")

    for test_name, src_test_dir, dest_test_dir in _iter_test_dirs(
        ws_root, ws_path, debug_dir_path, debug_dir, test_dir_suffix
    ):
        sim_result = os.path.join(src_test_dir, sim_result_name)
        if os.path.isfile(sim_result):
            shutil.copy2(sim_result, dest_test_dir / sim_result_name)

        _copy_elf_files(src_test_dir, dest_test_dir)


# ---------------------------------------------------------------------------
# Comprehensive-only packaging
# ---------------------------------------------------------------------------

def _package_src(ws_root: Path, ws_path: str, config: dict) -> None:
    """src/: firmware, hardware proj, meta, and verif dirs preserving repo-relative paths."""
    src_dirs = [
        (config.get("src_firmware_dir_path", "src"), config.get("src_firmware_dir", "firmware")),
        (config.get("src_hd_proj_dir_path", "src/hardware/tensix"), config.get("src_hd_proj_dir", "proj")),
        ("src", "meta"),
        ("src", "verif"),
    ]

    for parent_rel, dir_name in src_dirs:
        src_path = os.path.join(ws_path, parent_rel, dir_name)
        if not os.path.isdir(src_path):
            logger.warning("Source directory not found: %s", src_path)
            continue
        dest_path = ws_root / parent_rel / dir_name
        if dest_path.exists():
            shutil.rmtree(dest_path)
        shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
        logger.info("Copied %s/%s", parent_rel, dir_name)


def _package_tests_debug(ws_root: Path, ws_path: str, config: dict) -> None:
    """Per-test debug artifacts: logs and trace files (comprehensive only)."""
    debug_dir_path = config.get("debug_dir_path", "rsim")
    debug_dir = config.get("debug_dir", "debug")
    test_dir_suffix = config.get("test_dir_suffix", "_0")
    rtl_log_suffix = config.get("rtl_log_file_suffix", ".rtl_test.log")

    for test_name, src_test_dir, dest_test_dir in _iter_test_dirs(
        ws_root, ws_path, debug_dir_path, debug_dir, test_dir_suffix
    ):
        log_file = os.path.join(src_test_dir, test_name + rtl_log_suffix)
        if os.path.isfile(log_file):
            shutil.copy2(log_file, dest_test_dir / (test_name + rtl_log_suffix))

        sim_run_log = os.path.join(src_test_dir, "sim-run.log")
        if os.path.isfile(sim_run_log):
            shutil.copy2(sim_run_log, dest_test_dir / "sim-run.log")

        _copy_top_trace_files(src_test_dir, dest_test_dir)


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _iter_test_dirs(
    ws_root: Path, ws_path: str,
    debug_dir_path: str, debug_dir: str, test_dir_suffix: str,
):
    """Yield (test_name, src_test_dir, dest_test_dir) for every test in progress/."""
    progress_dir = Path("progress")
    if not progress_dir.exists():
        logger.warning("No progress directory found, skipping test packaging")
        return

    for progress_file in progress_dir.glob("*.json"):
        test_name = progress_file.stem
        test_dir_name = test_name + test_dir_suffix
        src_test_dir = os.path.join(ws_path, debug_dir_path, debug_dir, test_dir_name)

        if not os.path.isdir(src_test_dir):
            logger.warning("Test output dir not found: %s", src_test_dir)
            continue

        dest_test_dir = ws_root / debug_dir_path / debug_dir / test_dir_name
        dest_test_dir.mkdir(parents=True, exist_ok=True)
        yield test_name, src_test_dir, dest_test_dir


def _copy_top_trace_files(src_dir: str, dest_dir: Path) -> None:
    """Copy TOP*.txt trace files (e.g. trisc traces) from the test directory."""
    for fname in os.listdir(src_dir):
        if fname.startswith("TOP") and fname.endswith(".txt"):
            src_file = os.path.join(src_dir, fname)
            if os.path.isfile(src_file):
                shutil.copy2(src_file, dest_dir / fname)


def _copy_elf_files(src_dir: str, dest_dir: Path) -> None:
    """Copy ELF files from neo_*/thread_*/ subdirectories."""
    for root, dirs, files in os.walk(src_dir):
        for fname in files:
            if fname.endswith(".elf"):
                src_file = os.path.join(root, fname)
                rel = os.path.relpath(src_file, src_dir)
                dst = dest_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst)


def _find_file(root_dir: str, rel_path: str) -> str | None:
    """Find a file by relative path or by walking."""
    candidate = os.path.join(root_dir, rel_path)
    if os.path.isfile(candidate):
        return candidate

    base_name = os.path.basename(rel_path)
    for dirpath, _, filenames in os.walk(root_dir):
        if base_name in filenames:
            return os.path.join(dirpath, base_name)

    logger.warning("Could not find %s under %s", rel_path, root_dir)
    return None
