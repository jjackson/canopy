"""Tests for the diff-size cap used by the autonomous PM gate."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).parent.parent.parent
    / "plugins"
    / "canopy"
    / "skills"
    / "product-management"
    / "scripts"
    / "diff_size_check.py"
)


def _run(stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


SMALL_STAT = (
    " src/a.py | 12 ++++++------\n"
    " src/b.py | 30 +++++++++++++++++++++---------\n"
    " 2 files changed, 25 insertions(+), 17 deletions(-)\n"
)

LARGE_STAT = (
    " src/big.py | 1600 ++++++++++++++++++++++++++++++++++\n"
    " 1 file changed, 1500 insertions(+), 100 deletions(-)\n"
)


def test_small_diff_passes() -> None:
    result = _run(SMALL_STAT, "--limit", "1500")
    assert result.returncode == 0, result.stderr


def test_large_diff_blocks() -> None:
    result = _run(LARGE_STAT, "--limit", "1500")
    assert result.returncode == 1
    assert "1600" in result.stderr or "exceeds" in result.stderr.lower()


def test_default_limit_is_1500() -> None:
    just_over = (
        " src/x.py | 1501 +\n"
        " 1 file changed, 1501 insertions(+), 0 deletions(-)\n"
    )
    result = _run(just_over)
    assert result.returncode == 1


def test_at_limit_passes() -> None:
    at = (
        " src/x.py | 1500 +\n"
        " 1 file changed, 1500 insertions(+), 0 deletions(-)\n"
    )
    result = _run(at)
    assert result.returncode == 0


def test_empty_input_passes() -> None:
    result = _run("")
    assert result.returncode == 0
