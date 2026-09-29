# Rules research

Fyodor's rules engine is built from the **current official Magic rules**, not from anyone's
memory of them. Research is a development-time activity with Internet access; the finished app
never goes online during a game.

## Authority

When deciding engine behaviour, in this order:

1. The **current Comprehensive Rules** (Wizards of the Coast), stored in this repository.
2. The current **Oracle text** of the card (the local card database).
3. Official **update bulletins**, then official **release notes**.
4. Official card rulings (and Scryfall's mirror of them).
5. Community resources — only to *find* a question, never to answer it when an official answer
   exists.

If sources disagree, the current Comprehensive Rules win. The live engine is deterministic
code; research tools (and any AI assistance while developing) propose, they never decide a
game.

## The rules on disk

```
data/rules/
  comprehensive_rules/
    2026-09-25/                 # the effective date printed in the rules
      comprehensive_rules.txt   # the official TXT, unmodified
      source.json               # source URL, fetch time, effective date, SHA-256, rule count, previous version
      sha256.txt
  bulletins.json                # discovered update bulletins and release notes (URL, kind, title, date found)
data/reports/
  rules_changes.md              # the last diff between two stored versions, with engine impact
  sba_audit.md                  # every state-based action in the current rules and Fyodor's status
```

Current version: **Comprehensive Rules effective 2026-09-25** (3,312 numbered rules, 741
glossary terms). The app reports it in diagnostics and exported rules scenarios
(`app/rules/research.py`, `app/buildinfo.py`).

## Tools (`backend/tools/rules_research`)

Run from `backend/`:

| Command | What it does |
|---|---|
| `python -m tools.rules_research.update` | Finds the TXT link on magic.wizards.com/en/rules, downloads it, stores a new version if its SHA-256 differs, diffs it against the previous one into `rules_changes.md`, and records new update bulletins / release notes from the news pages. |
| `python -m tools.rules_research.update --file CR.txt` | The same from a file you downloaded (no network). |
| `python -m tools.rules_research.search "mana ability"` | Searches the local rules and glossary (lexical, deterministic). A rule number (`903.9`) lists that rule and its subrules. |
| `python -m tools.rules_research.audit` | Regenerates `sba_audit.md` from the stored rules. |

The parser (`cr.py`) reads numbered rules, subrules, examples and the glossary. It skips the
table of contents.

## When the rules change

`update` writes `rules_changes.md`:

- every NEW / REMOVED / MODIFIED rule, and NEW KEYWORD / NEW KEYWORD ACTION;
- a category per change: COMMANDER, COMBAT, COST, ZONE CHANGE, STATE-BASED ACTION, COPY/LAYER or
  OTHER;
- a word diff for modified rules;
- **RULES UPDATE IMPACT**: the engine modules that implement the changed chapters (the map lives
  in `diff.IMPACT`). Review their tests before trusting them again.

The state-based-action audit is also a test: when the rules add or renumber a state-based
action, `tests/test_rules_research.py` fails until someone marks it SUPPORTED, PARTIAL, MISSING or
NOT APPLICABLE in `tools/rules_research/audit.py`.

Card scripts record the Oracle text hash they were validated against. When Oracle text changes,
the card drops to PARTIAL with REVIEW NEEDED (`app/rules/cards`).

## Rule references in code

Code comments cite rules for traceability ("704.5m"). Numbers can move between revisions, so
behaviour never depends on a number; the audit and the diff report catch moved rules.

## Findings from the 2026-09-25 rules so far

- **State-based actions** (`sba_audit.md`): 16 supported, 1 partial (704.5p: only creatures
  and battles are unattached, because other "attached" cards on the table are tucks), 7
  missing (they need static abilities, Sagas, dungeons, Siege/battle protectors, Role
  timestamps: M16), 6 not applicable to Commander. This research added Aura, Equipment,
  Fortification, creature-attachment and non-Siege battle state-based actions.
- **Leaving the game** follows 800.4a (`app/rules/leave.py`).
- **The commander move** follows 704.6d / 903.9a (owner's choice, once per arrival).
