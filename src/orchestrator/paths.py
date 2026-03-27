"""Shared path constants for canopy data directory.

Centralizes the data directory path and handles migration from the
legacy ~/.claude/orchestrator/ location.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CANOPY_DIR = Path.home() / ".claude" / "canopy"
_LEGACY_DIR = Path.home() / ".claude" / "orchestrator"


def ensure_canopy_dir() -> Path:
    """Return CANOPY_DIR, migrating from legacy path if needed."""
    if _LEGACY_DIR.exists() and not CANOPY_DIR.exists():
        logger.info("Migrating %s -> %s", _LEGACY_DIR, CANOPY_DIR)
        CANOPY_DIR.parent.mkdir(parents=True, exist_ok=True)
        _LEGACY_DIR.rename(CANOPY_DIR)
    elif _LEGACY_DIR.exists() and CANOPY_DIR.exists():
        logger.warning(
            "Both %s and %s exist. Using %s.",
            _LEGACY_DIR, CANOPY_DIR, CANOPY_DIR,
        )
    CANOPY_DIR.mkdir(parents=True, exist_ok=True)
    return CANOPY_DIR
