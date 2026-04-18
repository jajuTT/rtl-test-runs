"""Stage pulled ws-tensix/{src,rsim} as polaris_big/__ext/rtl_test_data_set/<tag>/{src,rsim}.

The staged tree is the artifact downstream consumers use (either directly via
``run_rtl_neosim_correlation.py`` or via a tarball uploaded to the shared file
cache). Default ``method="copy"`` produces a self-contained minimal snapshot;
``method="symlink"`` is a dev-only shortcut for fast local iteration.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Artifacts added by _package_tests_debug / _copy_top_trace_files in
# ird/remote_worker/data_packager.py when package_level == "comprehensive".
# Keep this set in sync with that packager so the staged tree is always a
# minimal snapshot regardless of how it was pulled.
_COMPREHENSIVE_ONLY_EXACT = {"sim-run.log"}
_COMPREHENSIVE_ONLY_SUFFIXES = (".rtl_test.log",)


def _minimal_ignore(dirname: str, names: list[str]) -> list[str]:
    ignored = []
    for n in names:
        if n in _COMPREHENSIVE_ONLY_EXACT:
            ignored.append(n)
        elif n.endswith(_COMPREHENSIVE_ONLY_SUFFIXES):
            ignored.append(n)
        elif n.startswith("TOP") and n.endswith(".txt"):
            ignored.append(n)
    return ignored


_STAGED_SUBDIRS = ("src", "rsim")


def stage_test_data(
    pulled_tag_dir: Path | str,
    rtl_tag: str,
    polaris_big_dir: Path | str,
    *,
    method: str = "copy",
) -> Path:
    """Materialize polaris_big/__ext/rtl_test_data_set/<tag>/{src,rsim}.

    Parameters
    ----------
    pulled_tag_dir:
        Directory produced by ``ird pull`` — expected to contain ``ws-tensix/``.
        Typically ``<cwd>/<rtl_tag>``.
    rtl_tag:
        e.g. ``"apr16"``; the staged directory name and run_rtl_neosim tag.
    polaris_big_dir:
        Path to the ``polaris_big`` checkout whose ``__ext/`` we populate.
    method:
        ``"copy"`` (default, tar-safe) uses ``shutil.copytree`` with a minimal
        ignore filter. ``"symlink"`` creates absolute symlinks; fast for local
        iteration but MUST NOT be tarred and cannot enforce the minimal filter.

    Returns
    -------
    Path
        The staged ``<dest_root>/<rtl_tag>`` directory.
    """
    if method not in ("copy", "symlink"):
        raise ValueError(f"Invalid method {method!r}; expected 'copy' or 'symlink'")

    pulled_tag_dir = Path(pulled_tag_dir).resolve()
    polaris_big_dir = Path(polaris_big_dir).resolve()

    ws_tensix = pulled_tag_dir / "ws-tensix"
    missing = [s for s in _STAGED_SUBDIRS if not (ws_tensix / s).is_dir()]
    if missing:
        raise FileNotFoundError(
            f"Cannot stage: {ws_tensix} is missing {missing}. "
            f"Run `ird pull` (or `ird repackage` then `ird pull`) first."
        )

    dest_root = polaris_big_dir / "__ext" / "rtl_test_data_set"
    dest_tag = dest_root / rtl_tag

    _backup_existing(dest_tag)
    dest_tag.mkdir(parents=True, exist_ok=True)

    if method == "copy":
        for sub in _STAGED_SUBDIRS:
            src = ws_tensix / sub
            dst = dest_tag / sub
            logger.info("Copying %s -> %s (minimal filter)", src, dst)
            shutil.copytree(src, dst, symlinks=False, ignore=_minimal_ignore)
    else:  # symlink
        logger.warning(
            "stage method=symlink: dev-only shortcut; do NOT tar this tree. "
            "Use method='copy' for tarball-bound staging."
        )
        for sub in _STAGED_SUBDIRS:
            src = ws_tensix / sub
            dst = dest_tag / sub
            logger.info("Symlinking %s -> %s", src, dst)
            os.symlink(src, dst, target_is_directory=True)

    logger.info("Staged tree ready at %s", dest_tag)
    return dest_tag


def _backup_existing(dest_tag: Path) -> None:
    """Move an existing staged directory aside so each stage starts clean."""
    if not dest_tag.exists() and not dest_tag.is_symlink():
        return
    backup = dest_tag.with_name(dest_tag.name + ".bak")
    if backup.exists() or backup.is_symlink():
        if backup.is_symlink() or backup.is_file():
            backup.unlink()
        else:
            shutil.rmtree(backup)
    if dest_tag.is_symlink():
        dest_tag.rename(backup)
    else:
        dest_tag.rename(backup)
    logger.info("Moved old %s -> %s", dest_tag, backup)
