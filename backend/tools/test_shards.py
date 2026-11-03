"""Pick backend test files for CI.

The per-card rules tests (``tests/test_rules_*.py``, about 16 hours of single-core test time) are too many for every push on
GitHub's runners. ``--quick`` lists the other test files plus a fixed sample of the rules files (every ``--every``-th, so the
sample spreads over all waves and stays the same from push to push). ``--shard I/N`` lists the I-th of N slices of all test
files, for running the full suite in parallel jobs.

Usage (from backend/): ``pytest $(python -m tools.test_shards --quick)`` or ``pytest $(python -m tools.test_shards --shard 3/8)``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1] / "tests"


def all_files() -> list[str]:
    return sorted(f"tests/{p.name}" for p in TESTS.glob("test_*.py"))


def quick(every: int) -> list[str]:
    files = all_files()
    rules = [f for f in files if f.startswith("tests/test_rules_")]
    return [f for f in files if not f.startswith("tests/test_rules_")] + rules[::every]


def shard(index: int, count: int) -> list[str]:
    """Files i, i+N, i+2N, … (1-based index): neighbouring waves, which tend to be equally heavy, land in different slices."""
    if not 1 <= index <= count:
        raise SystemExit(f"--shard {index}/{count}: the index must be between 1 and {count}")
    return all_files()[index - 1::count]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--quick", action="store_true", help="non-card tests plus a fixed sample of the card tests")
    group.add_argument("--shard", metavar="I/N", help="the I-th of N slices of all test files")
    parser.add_argument("--every", type=int, default=40, help="with --quick: take every N-th card test file (default 40)")
    args = parser.parse_args(argv)
    if args.quick:
        files = quick(max(1, args.every))
    else:
        index, _, count = args.shard.partition("/")
        files = shard(int(index), int(count))
    print(" ".join(files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
