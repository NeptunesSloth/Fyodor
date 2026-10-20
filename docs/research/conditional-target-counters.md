# Forge of Heroes

Current Oracle text retrieved from Scryfall on 2026-10-19. CR 115.1c,
608.2b/c and 400.7 apply. The announced target is a commander that entered
this turn; being a creature or planeswalker is checked separately while each
instruction resolves, rather than being a targeting restriction. A commander
that is both receives both counters. A commander turned into a land remains
a legal target and receives neither.

The parser expands the two conditional instructions into existing conditions
and counter primitives, preserving a single announced target. Existing entry
history uses the current object identity. Seven focused scenarios cover real
creature and planeswalker commander casts, stale entry history, noncommanders,
target removal, an opponent's commander, and Song of the Dryads. Replay and
save/load are checked in gameplay scenarios. Focused plus counter/history
regressions: 124 passing tests.
