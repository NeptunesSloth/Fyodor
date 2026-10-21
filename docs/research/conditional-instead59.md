# Conditional instead branches 59 — staged only

The exact native leaves for these three cards await root review and registration. They are outside the trigger peer's delegated registration scope. No live hook is installed and no promotion is counted.

| Card | Oracle ID |
| --- | --- |
| Dark Temper | 3a0ea41e-b4f5-4aa1-9f7a-158485313c64 |
| Will of the All-Hunter | dec281b4-e6d6-4b78-b755-358e07eb7c06 |
| Everflame Eidolon | 2c6b2f4a-4e0e-4dc1-92a8-c07e5cbba5f4 |

`backend/app/rules/conditional_instead59.py` composes existing native effects and resolution-time conditions. A native flag freezes the verdict before executing either branch. Costs, targeting, cycling, bestow, blocking state, and departed Aura/host object references retain their existing native paths. No shared algorithm or schema changes are proposed.

Verification in `/tmp/counter59-stage` with only the proposed four-line `scripts.define` hook:

- 19 native cases passed: an 18-case run and one additional Will blocking cold case. Three genuine subprocess reload cases passed, covering all three cards.
- 299 related cases passed: conditionals 261, cycling graveyard 18, joint attached pumps 14, and wave20b instead 6.
- Scoped mypy (one source), Ruff, and owned diff checks passed.

Evidence and complete file hashes: `/tmp/counter59-staged-manifest.json`. Full actual database canonicals: `/tmp/counter59-instead-canonical.json`. All official rulings (2/1/6): `/tmp/counter59-instead-rulings.json`. Proposed registration: `/tmp/counter59-hooks-proposal.patch`. Native, cold, and related logs: `/tmp/counter59-native-expanded-final.log`, `/tmp/counter59-cold-final.log`, `/tmp/counter59-related.log`.

Reviewed leaf SHA256: `06a9e586b76d4afd8ffb8c6a7b621f9753b73f6dede4e97252ef2ac5a8f4f206`. Tests and full canonical fixture are `backend/tests/test_rules_conditional_instead59.py` and `backend/tests/fixtures/conditional_instead59_cards.json`.
