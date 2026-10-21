# Fixed owner-library placements51 — isolated review artifacts

No production source edits or coverage admissions. Disjoint ownership confirmed with exile40. Exact five-card core: Terminus, Hallowed Burial, Harmonic Convergence, Plow Under, Rebuking Ceremony. Complete canonical rows and official ruling responses saved in `/tmp/fyodor-libraryplacements51-canonical.json` and `/tmp/fyodor-libraryplacements51-rulings.json`. These are candidates with isolated whole-card proofs, not production inventory gains.

Concrete shared patch awaiting root review: `/tmp/fyodor-libraryplacements51-kernel.patch`.

* `language.py`: recognize plural owners' libraries, and an already-native untargeted selector for fixed top/bottom put instructions. Shuffle parsing retains its existing scope; unspecified hand selections still refuse.
* `effects.py`: multiple fixed top/bottom objects use existing `library_placements.start` unless the effect explicitly assigns its ordering chooser. The previous path moved single-owner subsets before other owners finished ordering.
* `library_placements.py`: prefill existing per-object places with the fixed top/bottom destination, skipping the public choice stage. Existing commander replacement, APNAP private order, exact-object snapshots and one simultaneous native move remain authoritative. No new state schema or effect primitive.

Isolated registration only: `/tmp/fyodor_libraryplacements51_plugin.py` compiles the exact staged functions and grammar variable into the existing modules for a fresh test process, then registers the existing to_library handler. Run with `FYODOR_LIBRARYPLACEMENTS_STAGE=1 PYTHONPATH=/tmp:$PWD .venv/bin/python -m pytest -p fyodor_libraryplacements51_plugin tests/test_rules_library_placements51.py` from backend. The cold test uses the same optional environment only for isolated pre-admission proofs; remove that loader before final production verification.

Whole-card gameplay covers all five canonical spells, target loss/fizzle, changed control versus ownership, top/bottom private ordering, no subset moving before all owners order, one shared zone-change batch, commander replacement before movement, actual Terminus miracle casting for W, and a genuine cold owner-order continuation. Existing Aetherspouts/owner-library regressions are separate validation of the reused native continuation.

Root review must precede shared source edits. After review, apply only exact approved hunks while preserving concurrent changes; run production proofs without staged registration; root owns final inventory/diff.

Validation complete:66 tests pass across `test_rules_library_placements51.py`, existing `test_rules_library_placements.py`, and `test_rules_owner_library_choices.py`, with cold cases, in `/tmp/fyodor-libraryplacements51-isolated.log`. Ruff passes. Scoped mypy of the real isolated app package passes all five staged source files (both batches) in `/tmp/fyodor-static50-types-package.log`. No full catalog inventory was run.
