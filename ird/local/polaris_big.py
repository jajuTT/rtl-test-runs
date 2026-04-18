"""Ensure polaris_big/ is present locally before stage / analyze.

polaris_big is the primary development repo for the RTL-vs-model correlation
tool. Users routinely switch branches, compare, and commit in it, so we clone
the full repo (no --single-branch / --depth) but never auto-update a pre-
existing checkout — updates are explicitly the user's responsibility.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_polaris_big(
    polaris_big_dir: str | Path,
    git_url: str,
    git_branch: str,
) -> Path:
    """Ensure *polaris_big_dir* is a real polaris_big git checkout.

    - Directory exists with ``.git/`` -> no-op (user owns updates).
    - Directory missing -> ``git clone -b <branch> <url> <dir>``.
    - Directory exists without ``.git/`` -> it's a stale leftover from a
      previous ``stage``/``analyze`` run that wrote ``__ext/...`` into a
      not-yet-cloned path.  If the only content is ``__ext/`` (or it's
      empty), wipe and clone; ``stage_test_data`` will regenerate
      ``__ext/`` on the next step.  If there's anything else, raise so we
      never clobber user data.

    Raises ``subprocess.CalledProcessError`` on git failures so callers see
    the git stderr directly.
    """
    p = Path(polaris_big_dir)

    if p.exists():
        if (p / ".git").is_dir():
            logger.info("polaris_big already present at %s (skipping clone)", p.resolve())
            return p
        stray = [e.name for e in p.iterdir() if e.name != "__ext"]
        if stray:
            raise RuntimeError(
                f"{p.resolve()} is not a git checkout (no .git/) and contains "
                f"unexpected entries {stray!r}. Remove it manually and rerun."
            )
        logger.warning(
            "%s is not a git checkout; wiping stale leftover before cloning",
            p.resolve(),
        )
        shutil.rmtree(p)

    logger.info("Cloning %s (branch=%s) into %s", git_url, git_branch, p)
    subprocess.check_call([
        "git", "clone", "-b", git_branch, git_url, str(p),
    ])
    return p
