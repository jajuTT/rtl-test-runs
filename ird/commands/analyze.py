"""Analyze command: stage pulled data and invoke run_rtl_neosim_correlation.py.

This is a thin subprocess wrapper. The actual model runs, correlation, and
S-curve generation are handled by polaris_big/tools/run_rtl_neosim_correlation.py.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from ..config import load_config
from ..local.polaris_big import ensure_polaris_big
from ..local.polaris_big_patch import patch_polaris_big_for_tag
from ..local.stage import stage_test_data

logger = logging.getLogger(__name__)


def analyze(
    data_dir: str | Path,
    config_path: str,
    *,
    polaris_big_dir: str | Path = "polaris_big",
    stage_method: str = "copy",
) -> None:
    """Stage pulled data into polaris_big/__ext and run the correlation tool.

    Parameters
    ----------
    data_dir:
        Parent directory that contains the pulled ``<rtl_tag>/`` directory.
        Typically ``"."`` (matches ``ird pull --local-dir .``).
    config_path:
        Path to the run_config JSON. Required — we need ``rtl_tag`` and
        ``num_processes`` from it.
    polaris_big_dir:
        Path to the polaris_big checkout. The correlation tool is invoked with
        this as the subprocess cwd so relative paths (``tools/...``,
        ``__ext/...``, ``config/...``) resolve correctly.
    stage_method:
        ``"copy"`` (default, tar-safe) or ``"symlink"`` (dev-only).
    """
    rtl_config, model_config = load_config(config_path)
    rtl_tag = rtl_config.rtl_tag

    pulled = Path(data_dir) / rtl_tag
    polaris = Path(polaris_big_dir)

    ensure_polaris_big(polaris, model_config.git_url, model_config.git_branch)
    patch_polaris_big_for_tag(polaris, rtl_tag, rtl_config.previous_rtl_tag)

    logger.info("Staging %s into %s (method=%s)", pulled, polaris, stage_method)
    stage_test_data(pulled, rtl_tag, polaris, method=stage_method)

    cmd = [
        "python", "tools/run_rtl_neosim_correlation.py",
        "--tag", rtl_tag,
        "--parallel", str(rtl_config.num_processes),
        "--memoryMap",
        f"__ext/rtl_test_data_set/{rtl_tag}/src/meta/instructions/yaml/memory_map.json",
        "--cfg", f"config/tensix_neo/ttqs_neo4_{rtl_tag}.json",
    ]
    logger.info("Invoking: %s (cwd=%s)", " ".join(cmd), polaris)
    subprocess.check_call(cmd, cwd=str(polaris))
    logger.info("Analyze complete")
