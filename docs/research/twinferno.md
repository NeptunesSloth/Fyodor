# Twinferno's next-spell watch

Twinferno's first mode uses the same native once-only, turn-limited cast watch as
"When you next cast an instant or sorcery spell this turn." Its alternative Oracle
word order, "When you cast your next ...", now reaches that parser too.

The following permission to choose new targets belongs to the future triggered
ability (CR 603.7, 707.10c). The watch sentence joiner recognizes both word orders
and captures the retarget marker together with the copy instruction. Without
this capture, a copy would be made with its old targets while the permission was
incorrectly processed during Twinferno's own resolution.

Eight canonical gameplay tests cover both modes, instant and sorcery copying,
nonqualifying artifacts, opponent spells, one-shot consumption, expiration,
countered-original last-known values, actual retargeting to a third player,
end-of-turn keyword expiration, and JSON/history replay.
