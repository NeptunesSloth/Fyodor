# Conditional additional entry counters

Thunderous Velocipede's current canonical Oracle text describes one replacement
effect adding one counter to each other Vehicle or creature with mana value at
most four, or three counters otherwise. The amount uses the entering permanent's
characteristics as it would exist on the battlefield, including entry copy
effects (CR 614.12). X is zero there (202.3e).

The existing entry-counter replacement grammar now recognizes the bounded
mana-value threshold wording and saves both amounts on its normal replacement
descriptor. The counter planner evaluates the threshold using its existing
battlefield probe, preserving controller filters, simultaneous-entry exclusion,
and normal replacement ordering. No separate entry or callback engine exists.

Canonical gameplay tests cover both threshold sides, a zero-cost creature,
uncrewed Vehicles, opponent control, the source's own entry, X spells, copy-entry
choice after JSON reload, Doubling Season and Solemnity, plus history replay.

The Solemnity case exposed an existing issue: synthetic zero-count entry events
used to discover additional counters skipped counter prohibitions. They now
check the same prohibition before applying replacements (CR 614.17), so a
replacement cannot create counters on a permanent prohibited from receiving them.

Storm Entity now uses the existing exact-incarnation cast-history descriptor for
"each other spell cast this turn." Its own cast is excluded after being logged;
reanimation counts the reanimation spell normally. The descriptor already counts
all players and follows stack-to-battlefield identity without subtracting an
arbitrary cast or using a stale prior incarnation.
