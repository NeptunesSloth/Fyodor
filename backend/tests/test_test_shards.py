"""tools.test_shards: the CI slices cover every test file exactly once, and the quick run keeps every non-card test."""

from __future__ import annotations

from tools import test_shards


def test_shards_cover_every_file_once():
    files = test_shards.all_files()
    slices = [test_shards.shard(i, 8) for i in range(1, 9)]
    assert sorted(f for s in slices for f in s) == files
    assert all(slices)


def test_quick_keeps_every_non_card_test_and_samples_the_card_tests():
    files = test_shards.all_files()
    quick = test_shards.quick(40)
    assert {f for f in files if not f.startswith("tests/test_rules_")} <= set(quick)
    rules = [f for f in quick if f.startswith("tests/test_rules_")]
    assert 0 < len(rules) < len([f for f in files if f.startswith("tests/test_rules_")])
