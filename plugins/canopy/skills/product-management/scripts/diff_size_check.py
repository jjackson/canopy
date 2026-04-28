"""Diff-size cap for the autonomous PM gate (spec §3a).

Reads `git diff --stat` output on stdin. Looks for the summary line
'N files changed, X insertions(+), Y deletions(-)' and fails if X+Y
exceeds the limit (default 1500).
"""
from __future__ import annotations

import argparse
import re
import sys

# Matches the insertions count in a git --stat summary line, e.g.:
#   "2 files changed, 25 insertions(+), 17 deletions(-)"
#   "1 file changed, 5 insertions(+)"
# Compiled with re.MULTILINE so ^ anchors work on each line of the block.
_INSERTIONS_RE = re.compile(r"(\d+)\s+insertions?\(\+\)", re.MULTILINE)
_DELETIONS_RE = re.compile(r"(\d+)\s+deletions?\(-\)", re.MULTILINE)


def total_changed_lines(stat_output: str) -> int:
    """Sum insertions + deletions across all summary lines in stat output."""
    total = 0
    for line in stat_output.splitlines():
        ins_m = _INSERTIONS_RE.search(line)
        del_m = _DELETIONS_RE.search(line)
        total += int(ins_m.group(1)) if ins_m else 0
        total += int(del_m.group(1)) if del_m else 0
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=1500)
    args = parser.parse_args()

    stat = sys.stdin.read()
    total = total_changed_lines(stat)
    if total > args.limit:
        print(
            f"diff-size: {total} changed lines exceeds limit {args.limit}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
