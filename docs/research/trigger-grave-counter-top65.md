# Moss-Pit Skeleton 65 — production reviewed

Moss-Pit Skeleton (`edf0e7c0-d9a1-4d29-9cee-5267d3a3978f`) has passed independent root registration review and the native production rerun. Its exact live hook is admitted pending the central catalog diff; no shared algorithm change was needed.

The exact printed trigger composes the native graveyard return-to-hand watcher and changes only its final effect to native `to_library`, `who=self_gy`, `place=top`. The native graveyard watcher, per-creature counter event, optional choice, controller filter, and intervening condition remain intact. `self_gy` requires the source's exact object UID and current graveyard zone; library placement moves that card to the top of its owner's library.

Verification passed 22 unique native cases: an 18-case whole run including two genuine subprocess reloads, two controller-versus-owner boundaries, and two paid copy boundaries. These cover actual paid normal and kicked casting, paid Lightning Bolt death into the graveyard, accepting and declining recursion, doubled counters producing one trigger, two creatures receiving counters producing two distinct optional triggers, opponent counters, negative counters, prevented counters, zero-count entry, positive native entry counters, battlefield/exile source exclusions, removal before resolution, and leaving then returning to the graveyard with a new UID. The true cold cases resume both a pending trigger and an existing optional decision.

The paid Double Major copy of a kicked Moss-Pit Skeleton spell enters as a token with three +1/+1 counters, as does the original. A paid Clone entering as a copy of the kicked battlefield permanent is not kicked and receives no counters. These verify the relevant official kicker rulings using existing native producers.

Related verification passed a clean admitted 38 cases: source-graveyard 50 (16) and conditional entry counters (22). Scoped mypy (one source) and Ruff passed. An earlier mixed related invocation mistakenly included the held Bold Plagiarist/Captain Marvel packet scope; it was stopped and excluded from final evidence. No held packet adapter or registration was added.

Full actual canonical and all eight official rulings: `/tmp/counter65-moss-canonical.json`, `/tmp/counter65-moss-rulings.json`. Frozen exact hashes, proposed four-line define hook, and verification logs: `/tmp/counter65-moss-staged-manifest.json`. Sources: `backend/app/rules/trigger_grave_counter_top65.py`, `backend/tests/test_rules_trigger_grave_counter_top65.py`, and its full canonical fixture.
