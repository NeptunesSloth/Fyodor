# Personal deck collections and outside-game permissions

## Player workflow

In a LAN lobby, open **Bring a deck → My decks**. Import multiple exported files or public
Archidekt deck URLs. Each successful import stores a resolved deck list on that browser/device;
a failed file does not discard the other imports. URL imports use the host's Internet connection.
Saved lists and exported files resolve against the installed card catalog without Internet.
Artwork still depends on the host's image cache; readable card rendering works without it.

**Export My decks** creates a portable list-only JSON backup. Import that backup under My decks
to transfer the library to another device or table address. It contains no seat credentials.
Older URL-only remembered decks must be opened online once to save their lists before export.
The library no longer silently drops decks after twenty imports. Storage failures are reported.

All decks in My decks contribute their listed card quantities to that player's collection.
Refreshing the same Archidekt source replaces its previous version. Different deck lists with
the same title remain distinct. Tokens and maybeboard entries do not contribute owned cards.
Changing the library synchronizes the collection to the current lobby without replacing the
playing deck, and clears the owner's readiness when the collection changes.

Select an optional companion from the imported candidates before choosing the playing deck.
The server checks ownership, its starting-deck condition, Commander legality, color identity,
and duplicate names. All starting copies count, including the commander. An invalid selection
does not replace the previously accepted deck. Existing companion payment remains the normal
once-per-game, sorcery-speed {3} special action.

The host's separate deck library remains local-only. A guest cannot browse that library.
Choosing a host-library deck on the host device saves only that chosen deck into My decks;
it does not assign the host's entire library to a player.

## Rules question and authoritative sources

Can imported collections supply cards to Wishes, Learn, and companions in Commander?
Sources: Comprehensive Rules effective **2026-09-25**, stored in `data/rules/comprehensive_rules/2026-09-25`.

- **400.11–400.11c:** outside the game is not a game zone; ordinary effects cannot affect those
  cards unless the rules allow it.
- **903.11:** ordinary permissions to obtain or cast outside-game traditional cards do not
  supply an exception to Commander's prohibition. An explicit Commander exception is required.
- **903.11a:** permitted imports must also satisfy Commander identity and duplicate-name limits.
- **103.2b, 702.139, 116.2g:** companion has an explicit pregame reveal and special-action rule.
- **701.48a:** Learn offers discard/draw first, then a Lesson import if no card was discarded.
  The ordinary Lesson import remains unavailable in Commander under 903.11.
- **723.4:** outside-card information remains private even from a player controlling its owner.
- **608.2c–d:** follow all other instructions in order; do not offer impossible optional imports.

The earlier assumption that settling collection membership would make ordinary Wishes usable
in Commander was incorrect under this CR version. Collections do not override the format rule.

## Engine implementation and edge cases

Collections are per-player metadata in `GameState.collections`, not thousands of extra card
instances in a pseudo-zone. Starting cards already represented on the table, including a selected
companion, are subtracted from the imported quantities. Old saves default collections to empty.
Collections persist in saved games, portable game packages, and replay state.

Authenticated lobby import returns a normalized list only to the submitting seat. Collection
synchronization applies only to that seat. The explicit owner-only collection endpoint does not
honor another player's viewer parameter in a LAN game, does not inherit player-control access,
and returns `Cache-Control: private, no-store`. Routine table views omit collection contents.

`rules/outside_game.py` recognizes specific ordinary outside-card permissions. In Commander
those permissions do nothing, while the remaining instructions still resolve: Wishes exile
themselves, Death Wish loses half the player's life rounded up, and creatures still enter.
Spawnsire pays its activation cost normally. Granted still follows the Adventure rules.
Unknown wording remains unsupported. Ordinary outside-card selection in other formats remains
a manual fallback; this module claims Commander automation only. Karn's combined outside/exile
choice remains partial rather than losing its legal exile option.

Real Oracle scenarios cover all twelve promotions: Burning Wish, Cunning Wish, Living Wish,
Glittering Wish, Golden Wish, Death Wish, Wish, Mastermind's Acquisition, Fae of Wishes // Granted,
Legion Angel, Spawnsire of Ulamog, and North Wind Avatar. They also cover an owned Lesson during
Learn, both Mastermind modes, Granted followed by casting and bouncing Fae, Spawn-token mana,
odd life rounding, cast and uncast Avatar entry, replay, and save/load.

## Coverage and validation

Whole-catalog comparison: **27,601 → 27,613 FULL**, **4,467 → 4,455 PARTIAL** of 32,068
Commander-legal cards. Possible commanders remain 2,941 FULL out of 3,501. No previously FULL
card lost that status. All-card automation remains unfinished.

Browser checks exercise separate host and remote guest contexts, multiple imports including an
invalid file, reload, portable export/reimport after deleting the local library, offline list
reuse, starting a game, and owner-only collection access. API tests also exercise an actual
host restart with networking disabled and loading a saved game with its private collection.
