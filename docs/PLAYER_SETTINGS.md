# Profiles, settings, views, sound — and snapshots & history

## Local player profiles

*Settings* (top navigation, or ⋯ → Settings… at the table). No accounts, passwords or cloud:
profiles live in this browser's storage and are never required — a default profile always
exists. **Export** writes `<name>.json`; **Import…** reads one back (e.g. on another computer).

A profile holds: display name and icon, preferred sleeves / playmat (worn automatically when you
sit down at a LAN table), preferred seat (taken when free), HUD mode, UI scale, card-preview
size, high contrast, colorblind-safe seat markers (a shape per seat next to the color), reduced
motion, animation speed, snap preference, sound levels, graphics preset, token-collapse
threshold, favorite counters, saved views and remapped keys. The profile also shows its pod
record (matched by name) from Pod stats, which the host keeps.

Stored data is versioned (`fyodor.profiles`, version 2); older data (the single
`fyodor.prefs` object) is migrated automatically. Unit tests cover the migration.

## Views (the 2D table's camera bookmarks)

*⋯ → Views*: whole table, one player's board (enlarged), stack open/closed. **Ctrl+Shift+1…9**
saves the current view under a name, **Ctrl+1…9** recalls it. Views are per profile.

## Keys

All shortcuts come from one table (`frontend/src/game/hotkeys.ts`); *Settings → Keys* remaps
any of them (click, press the new key; ↺ restores the default). The screen warns when two
actions share a key, and a unit test guarantees the defaults never do.

## Sound

Subtle tabletop sounds synthesised in the browser (no audio files): card slides and placement,
taps, flips, riffle shuffles, draws, dice on felt, a coin ring, token and counter clicks, a soft
bell for response checks and a quiet chime on a new turn. Master / Cards / Dice / Interface /
Ambient levels and **Mute all**. Nothing in the game depends on sound.

## Performance

**Low / Medium / High** graphics presets: Low drops shadows, animations and background texture
and collapses identical tokens above 5; Medium keeps light shadows. The token-collapse threshold
(5 / 10 / 20 / Never) is separate and applies when you create tokens.

## Snapshots & history

*⋯ → Snapshots & history…*

* **Save snapshot** — the whole table (hands, library order, positions, counters, effects,
  ownership and control, stack, life, arrows…) under a name such as “Before board wipe”. Any
  player can save one; they're kept with the game (and in its saves), up to 30.
* **Restore** — host only on LAN. The table becomes exactly the snapshot; private views end and
  hidden cards stay anonymous. A restore is an ordinary action: **Undo** takes it back.
* **History** — every recorded action with the log lines *you* may read. Pick one to see the
  table right after it, as you could see it then (for disputes and debugging). The host can
  **Restore from here**.
* Randomness (shuffles, dice, coins, mulligans) is resolved once on the server and stored in the
  action, so undo → redo and history replays give the same results; nothing is re-rolled.
