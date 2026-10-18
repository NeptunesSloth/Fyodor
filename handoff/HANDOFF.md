# Rules-engine waves: handoff

This branch only carries the working kit of the session that ran waves 30–51 on `claude/vibrant-hamilton-e00gs8`
(draft PR NeptunesSloth/Fyodor#16). It is not meant to be merged. Copy `handoff/` into a new session's scratchpad.

## Where things stand
- Fresh inventory at `3996acc8`: FULL 27,042 / 32,068 (84.33%), commanders 2,890 / 3,501 (82.55%), lines 89.74%.
  - Waves 51A–51I are all merged at `659de4de`. By the agents' own deltas that is about 27,175 FULL and about 2,912 commanders.
  - Run a fresh inventory to get exact numbers: `cd backend && python -m tools.inventory --db ../data/cards.sqlite --out X.json -j 2`.
- **First thing to do:** run the full backend suite at `659de4de`. The last clean full run was at `51926a0a`. After it come
  51A, review 43, 51B, 51D, 51E, 51F, 51G, 51H and 51C, each checked with ruff, mypy and its own and related tests only.
  Expect a few stale pins; check each one is really stale.
- The remaining PARTIAL cards are a long tail: about 3,990 cards blocked by one line, in about 3,900 distinct shapes.
  The productive tracks lately were commander sweeps by family (if you do, trigger, counters, statics), most-played cards
  in rank order, and the few shapes that still repeat (keyword mechanics, modal modes).
- CI: GitHub Actions assigns no runner, so every job fails in 1–2 s. All verification is local (ruff, mypy, pytest, vitest, Playwright).

Every agent branch was merged before the session ended. Nothing is left open.

## How the waves ran
- `BRIEF.md` is the shared agent brief: policies, work contract, test conventions and style. Its scratchpad paths point to
  the old session; replace them with the new scratchpad.
- Four Sonnet implementation agents run at once, each in a worktree on branch `claude/vibrant-hamilton-e00gs8-wNNx`.
  An Opus "false-FULL" review covers every group of about 4 merged waves.
- **Merging**
  - Merge with `git merge --no-ff` in a side worktree, then run `ruff check app tests`, `mypy app tools` and targeted pytest, then push.
  - Run the full backend suite (`pytest -q -n 3`) after every few merges. Each run finds stale pins: tests that pinned a wording as manual which a newer wave now reads.
  - Before calling a full-suite failure a stale pin, check the card really plays right. Ice Cream Kitty and Sting were real bugs.
- Never use bare `git stash`: the stash stack is shared with agents' worktrees.

## Tools (`handoff/tools`, run from `backend/`)
- `levels.py --out F.json -j N`: level + parsed-definition hash of every card, from the `app` in the cwd. `levels_diff.py A B` compares two dumps.
- `cardq.py REGEX [--level PARTIAL] [--defs]`: Oracle-text search with levels. `defs_of.py "Name"`: parsed definitions of a card.
- `cmdr_left_now.py IN OUT` re-measures a commander list; `shapes.py IN OUT` clusters single-line blockers by shape.
- `lastmsg.py TRANSCRIPT.jsonl`: an agent's final report from its transcript (after a container restart).
- `lists/nonfull_by_rank.json`, `lists/cmdrs.json`: non-FULL cards and commanders at `3996acc8`, by EDHREC rank, with blocking lines.
- Rulings: the Scryfall bulk "rulings" file (`/bulk-data`), joined on `oracle_id` with `data/cards.sqlite` `printings`.

## Next work (researched, not started)
- Copy-this-spell on resolution: Sevinne's Reclamation, Chain of Vapor, Chain Lightning, Chain of Smog, Chain of Plasma,
  Chain of Silence, Chain of Acid, Chain Stasis, Social Snub, Barroom Brawl, String of Disappearances.
  - `copying.copy_stack_object` has no "this spell" source.
  - The copier must be settable: whoever creates the copy controls it (Chain Lightning ruling 2022-12-08).
  - Sevinne's copy isn't cast, so it doesn't copy itself again, and it is made only if the original target is still legal.
- Saw in Half: tokens copying the creature with halved base P/T (last known information, X is 0, nothing if not destroyed).
- Other most-played cards still manual: Forgotten Ancient, Tibalt's Trickery, Banner of Kinship, Bloodchief Ascension,
  Mizzix's Mastery, Tainted Pact, Ripples of Potential, Sword of Hearth and Home, Myr Battlesphere, Promise of Loyalty,
  Cut a Deal, Approach of the Second Sun, Combustible Gearhulk, Arcane Lighthouse, Charismatic Conqueror, Breach the
  Multiverse, Agadeem's Awakening.
- Shapes skipped by several agents: power-up with a hybrid cost (118.7e, no rulings), banding, Attractions, splice, epic.
- Not yet reviewed for false FULLs (review 44 was cut short; it checked Arcane Denial, Liliana, Animate Dead, Urza's Saga, Chrome Mox, Veil, Kalitas, Elsha and Throne defs):
  - waves 51A, 51C, 51D (Mikey & Don's top-card visibility, Mister Negative, Stiltzkin), 51E (blight, Skullbriar, Kodama, Satoru), 51G and 51H (offering's hybrid reduction);
  - Elsha's "look at the top any time" (owner only);
  - Valakut Awakening's private choice;
  - Veil of Summer's player hexproof against abilities from blue sources.
  Make this review 45.
- 51G found the next shared fix: "Choose an opponent. … that player" (Sandstone Oracle, Slithermuse, the Offering cycle, Skullwinder).
- 51H left the time counters on suspended cards and Dauthi Voidwalker features unstarted.
- Open doubts:
  - Wonder Man's extra power-up is keyed by name, so it survives ability loss.
  - Season of the Burrow: the same mode twice on one target.
  - Zero modes aren't offered for Seasons and kicked Inscriptions (a missing option only).
  - Serpentine Spike's three hits are separate events.
  - A payable special action shows opponents a "can act" stop (covered by the bluff-stops setting).
