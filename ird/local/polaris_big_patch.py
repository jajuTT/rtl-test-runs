"""Teach a fresh polaris_big checkout about a new RTL tag.

Upstream polaris_big now validates RTL tags by looping over the TTQSTags enum
in isaFunctions.py, eliminating the need to patch multiple files. When adding
a new tag (e.g. ``apr16``), only two operations are needed:

1. Add the tag to the TTQSTags enum in ttsim/back/tensix_neo/isaFunctions.py
2. Create the config file config/tensix_neo/ttqs_neo4_<tag>.json

The validation points in run_rtl_neosim_correlation.py and tensixFunc.py now
automatically loop over TTQSTags.is_supported and require no patching.

Because ``ird analyze`` auto-clones polaris_big/ from upstream, these operations
must be reapplied on every fresh checkout. This helper is idempotent: re-running
is a no-op once both operations are complete.
"""

from __future__ import annotations

import datetime
import logging
import re
import sys
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
    """Teach polaris_big about a new RTL tag. Idempotent.

    Performs two operations:
    1. Adds rtl_tag to TTQSTags enum in isaFunctions.py
    2. Creates config file ttqs_neo4_<rtl_tag>.json from previous tag

    The other validation points (run_rtl_neosim_correlation.py, tensixFunc.py)
    now loop over the TTQSTags enum automatically and require no patching.

    Parameters
    ----------
    polaris_big_dir: root of the polaris_big checkout.
    rtl_tag: tag to add (e.g. ``"apr16"``).
    previous_rtl_tag: existing tag (e.g. ``"feb20"``) used as:
      * anchor to locate insertion point in TTQSTags enum
      * source template for ttqs_neo4_<rtl_tag>.json config
    """
    root = Path(polaris_big_dir)
    touched = []

    # Operation 1: Patch TTQSTags enum
    if _patch_ttqs_enum(root, rtl_tag, previous_rtl_tag):
        touched.append("ttsim/back/tensix_neo/isaFunctions.py")

    # Operation 2: Create config file via isaFunctions helper
    if _create_config_file(root, rtl_tag):
        touched.append(f"config/tensix_neo/ttqs_neo4_{rtl_tag}.json")

    if touched:
        logger.info("Patched polaris_big for rtl_tag=%s: %s", rtl_tag, touched)
    else:
        logger.info("polaris_big already knows rtl_tag=%s (no operations needed)", rtl_tag)


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


def _create_config_file(root: Path, rtl_tag: str) -> bool:
    """Create config file via isaFunctions.create_default_cfg_file_from_previous_tag().
    Returns True if file was created, False if it already exists."""
    cfg_dir = root / "config" / "tensix_neo"
    dst = cfg_dir / f"ttqs_neo4_{rtl_tag}.json"
    
    # Check if config already exists
    if dst.exists():
        return False
    
    # Import isaFunctions from polaris_big
    # Add polaris_big to path temporarily to import the module
    sys.path.insert(0, str(root))
    try:
        import ttsim.back.tensix_neo.isaFunctions as isaFunctions
        
        # Call the helper function to create config file
        # This handles validation, error checking, and proper JSON formatting
        try:
            isaFunctions.create_default_cfg_file_from_previous_tag(
                rtl_tag,
                config_dir=cfg_dir
            )
            # Verify file was created
            return dst.exists()
        except (FileNotFoundError, ValueError) as e:
            # Re-raise with context
            raise RuntimeError(
                f"Failed to create config for {rtl_tag}: {e}"
            ) from e
    finally:
        # Clean up sys.path
        sys.path.pop(0)


def _pretty_comment(rtl_tag: str) -> str:
    """``apr16`` -> ``"Apr 16, <current-year>"``; falls back to tag verbatim."""
    m = re.fullmatch(r"([a-z]{3})(\d{1,2})", rtl_tag)
    if m and m.group(1) in _MONTH_NAMES:
        return f"{_MONTH_NAMES[m.group(1)]} {int(m.group(2))}, {datetime.date.today().year}"
    return rtl_tag
