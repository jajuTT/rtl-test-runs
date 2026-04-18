"""Teach a fresh polaris_big checkout about a new RTL tag.

Upstream ``polaris_big/main`` hard-codes the list of accepted RTL tags in
three separate Python files and ships a per-tag ``ttqs_neo4_<tag>.json``
config. When we add a new tag (e.g. ``apr16``), all four need to grow or the
correlation tool refuses to start with::

    ValueError: One or more invalid RTL tag(s): ['apr16'], accepted RTL tags: [...]

Because ``ird analyze`` auto-clones polaris_big/ from upstream, these patches
have to be reapplied on every fresh checkout. This helper is idempotent:
re-running it is a no-op once all four patches are in place.
"""

from __future__ import annotations

import datetime
import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_MONTH_NAMES = {
    "jan": "Jan", "feb": "Feb", "mar": "Mar", "apr": "Apr",
    "may": "May", "jun": "Jun", "jul": "Jul", "aug": "Aug",
    "sep": "Sep", "oct": "Oct", "nov": "Nov", "dec": "Dec",
}


def patch_polaris_big_for_tag(
    polaris_big_dir: Path | str,
    rtl_tag: str,
    previous_rtl_tag: str,
) -> None:
    """Apply all four rtl-tag patches to *polaris_big_dir*. Idempotent.

    Parameters
    ----------
    polaris_big_dir: root of the polaris_big checkout.
    rtl_tag: tag to add (e.g. ``"apr16"``).
    previous_rtl_tag: an existing tag (e.g. ``"feb20"``) used as:
      * anchor to locate the insertion point in ``TTQSTags`` enum, and
      * source for the seeded ``ttqs_neo4_<rtl_tag>.json`` config.
    """
    root = Path(polaris_big_dir)
    touched = []

    if _patch_rtl_tags_list(root, rtl_tag):
        touched.append("tools/run_rtl_neosim_correlation.py")
    if _patch_llk_assert(root, rtl_tag):
        touched.append("ttsim/back/tensix_neo/tensixFunc.py")
    if _patch_ttqs_enum(root, rtl_tag, previous_rtl_tag):
        touched.append("ttsim/back/tensix_neo/isaFunctions.py")
    if _seed_ttqs_config(root, rtl_tag, previous_rtl_tag):
        touched.append(f"config/tensix_neo/ttqs_neo4_{rtl_tag}.json")

    if touched:
        logger.info("Patched polaris_big for rtl_tag=%s: %s", rtl_tag, touched)
    else:
        logger.info("polaris_big already knows rtl_tag=%s (no patches needed)", rtl_tag)


def _patch_rtl_tags_list(root: Path, rtl_tag: str) -> bool:
    """Append ``rtl_tag`` to ``self.rtl_tags: list[str] = [...]`` in
    tools/run_rtl_neosim_correlation.py."""
    path = root / "tools" / "run_rtl_neosim_correlation.py"
    text = path.read_text()
    pattern = re.compile(
        r"(self\.rtl_tags\s*:\s*list\[str\]\s*=\s*\[)([^\]]*?)(\])",
        re.DOTALL,
    )
    m = pattern.search(text)
    if m is None:
        raise RuntimeError(f"Could not locate `self.rtl_tags: list[str] = [...]` in {path}")
    body = m.group(2)
    if f'"{rtl_tag}"' in body or f"'{rtl_tag}'" in body:
        return False
    stripped = body.rstrip()
    sep = ", " if stripped and not stripped.endswith(",") else ("" if not stripped else " ")
    new_list = f'{m.group(1)}{stripped}{sep}"{rtl_tag}"{m.group(3)}'
    path.write_text(text[:m.start()] + new_list + text[m.end():])
    return True


def _patch_llk_assert(root: Path, rtl_tag: str) -> bool:
    """Append ``rtl_tag`` to the ``assert args['llkVersionTag'] in [...]`` list
    in ttsim/back/tensix_neo/tensixFunc.py."""
    path = root / "ttsim" / "back" / "tensix_neo" / "tensixFunc.py"
    text = path.read_text()
    pattern = re.compile(
        r"(assert\s+args\[['\"]llkVersionTag['\"]\]\s+in\s+\[)([^\]]*?)(\])"
    )
    m = pattern.search(text)
    if m is None:
        raise RuntimeError(f"Could not locate `llkVersionTag` assert list in {path}")
    body = m.group(2)
    if f'"{rtl_tag}"' in body or f"'{rtl_tag}'" in body:
        return False
    stripped = body.rstrip()
    sep = ", " if stripped and not stripped.endswith(",") else ("" if not stripped else " ")
    new_list = f'{m.group(1)}{stripped}{sep}"{rtl_tag}"{m.group(3)}'
    path.write_text(text[:m.start()] + new_list + text[m.end():])
    return True


def _patch_ttqs_enum(root: Path, rtl_tag: str, previous_rtl_tag: str) -> bool:
    """Insert ``rtl_tag = "<rtl_tag>" # <pretty-date>`` into ``class TTQSTags``
    in ttsim/back/tensix_neo/isaFunctions.py, right after *previous_rtl_tag*."""
    path = root / "ttsim" / "back" / "tensix_neo" / "isaFunctions.py"
    text = path.read_text()
    if re.search(rf"^\s*{re.escape(rtl_tag)}\s*=\s*['\"]{re.escape(rtl_tag)}['\"]",
                 text, re.MULTILINE):
        return False
    anchor = re.compile(
        rf"^(?P<indent>[ \t]*){re.escape(previous_rtl_tag)}\s*=\s*"
        rf"['\"]{re.escape(previous_rtl_tag)}['\"][^\n]*\n",
        re.MULTILINE,
    )
    m = anchor.search(text)
    if m is None:
        raise RuntimeError(
            f"Could not find TTQSTags member {previous_rtl_tag!r} in {path}. "
            f"Set rtl.previous_rtl_tag to an existing tag."
        )
    indent = m.group("indent")
    new_line = f'{indent}{rtl_tag} = "{rtl_tag}" # {_pretty_comment(rtl_tag)}\n'
    path.write_text(text[:m.end()] + new_line + text[m.end():])
    return True


def _seed_ttqs_config(root: Path, rtl_tag: str, previous_rtl_tag: str) -> bool:
    """Copy ``ttqs_neo4_<previous>.json`` -> ``ttqs_neo4_<rtl_tag>.json`` if the
    destination doesn't already exist."""
    cfg_dir = root / "config" / "tensix_neo"
    src = cfg_dir / f"ttqs_neo4_{previous_rtl_tag}.json"
    dst = cfg_dir / f"ttqs_neo4_{rtl_tag}.json"
    if dst.exists():
        return False
    if not src.exists():
        raise RuntimeError(
            f"Previous ttqs config {src} not found. "
            f"Set rtl.previous_rtl_tag to an existing tag in {cfg_dir}."
        )
    shutil.copy2(src, dst)
    return True


def _pretty_comment(rtl_tag: str) -> str:
    """``apr16`` -> ``"Apr 16, <current-year>"``; falls back to tag verbatim."""
    m = re.fullmatch(r"([a-z]{3})(\d{1,2})", rtl_tag)
    if m and m.group(1) in _MONTH_NAMES:
        return f"{_MONTH_NAMES[m.group(1)]} {int(m.group(2))}, {datetime.date.today().year}"
    return rtl_tag
