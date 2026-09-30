---
name: mtg-rules-research
description: >
  Research Magic: The Gathering rules for Fyodor's Commander-only deterministic rules engine.
  Use before implementing or changing engine behavior, card scripts or coverage levels, when a
  precise or disputed rules question comes up, or after the Comprehensive Rules update.
---

# MTG rules research

This skill is for researching Magic: The Gathering rules for Fyodor's Commander-only
deterministic rules engine.

Never answer a precise or disputed rules question from model memory. Look it up, cite it, or
say it is unknown.

## Authority (highest first)

1. The CURRENT Wizards Comprehensive Rules stored locally:
   `data/rules/comprehensive_rules/<effective-date>/comprehensive_rules.txt`
   (use the newest dated folder; `source.json` holds effective date, URL and SHA-256).
2. Current Oracle text: the local card database (`data/cards.sqlite`, via `app/cards`).
3. Official Wizards rules updates, release notes and rulings, when needed
   (`data/rules/bulletins.json` lists known ones).
4. Scryfall, as a convenient Oracle/rulings mirror where appropriate.
5. Secondary sources: only to discover questions. Never the final authority when official
   material exists.

If sources disagree, the current CR wins. See `docs/RULES_RESEARCH.md` for tooling details.

## How to research

- Search the local CR narrowly. From `backend/` (needs the backend venv; `scripts/setup.sh`):
  - `python -m tools.rules_research.search "<term>"` for a term or glossary entry;
  - `python -m tools.rules_research.search 702.19` for one rule and its subrules.
  - Fallback: `grep -n` on the TXT for a specific phrase or rule number.
- Retrieve only the relevant numbered rules and glossary entries. Do not read the whole CR.
- Cite the exact rule numbers used (for example 603.10a, 704.5j, 903.9b).
- Keep core CR rules separate from card-specific Oracle text.
- Keep current rules separate from historical behavior. If a rule changed between CR versions,
  use the current version and say what changed.
- Check current Oracle wording for representative Commander-legal cards. Do not trust
  remembered wording.
- Prefer reusable rules abstractions over card-specific hacks.
- State uncertainty explicitly. If the answer is not supported by a source, say so.
- Never invent a ruling. When unsure, keep the behavior MANUAL instead of guessing.

## Fyodor constraints

- Development scope: automation of Commander-legal cards. Core Magic rules needed to resolve
  Commander games still apply.
- No runtime LLM judge. Research may propose deterministic code and tests; the engine decides
  outcomes.
- Physical card identity and rules object identity are separate.
- Respect zone-change new-object rules (400.7). Use last known information only where the CR
  requires it.
- Preserve simultaneous-event semantics, APNAP ordering, multiplayer semantics and hidden
  information.
- Wrong automation is worse than PARTIAL/MANUAL coverage. Do not promote a card to FULL unless
  all relevant behavior is supported and tested (`app/rules/coverage.py`).

## Card examples

- Use real Commander-legal cards, with current Oracle text from the local database.
- For a generic mechanic, use several representative cards.
- Include adversarial and edge-case cards, not only happy paths.

## Rule updates

- Record the CR version / effective date used (from `source.json`).
- If behavior changed between CR versions, follow the current version.
- Note whether existing engine tests, card scripts or reports need revalidation
  (`data/reports/rules_changes.md`, `data/reports/sba_audit.md`).

## Required output for implementation research

```
RULES QUESTION
CURRENT CR REFERENCES          (rule numbers + CR effective date)
ORACLE / CARD EXAMPLES         (real Commander-legal cards, current Oracle text, incl. edge cases)
ENGINE IMPLICATION             (reusable abstraction; affected modules)
EDGE CASES
TEST SCENARIOS                 (deterministic, concrete)
COVERAGE IMPACT                (if available: FULL/PARTIAL/REVIEW/MANUAL changes)
MANUAL FALLBACK / UNSUPPORTED CASES
```

Mark every claim that is not backed by a cited source as UNCERTAIN.
