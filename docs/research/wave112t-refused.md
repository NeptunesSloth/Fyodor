# Wave 112T: Star Trek mechanics from the release notes (beam me up, assimilate, face a dilemma)

Read from the Star Trek release notes (https://magic.wizards.com/en/news/feature/star-trek-release-notes); the CR (2026-09-25) doesn't define these mechanics yet, so each implementation is marked "Star Trek release notes (2026-11): re-check against the CR when it defines <mechanic>".

- **Jett Reno, Problem Solver** — "Whenever you face a dilemma, put a +1/1 counter on Jett Reno.": Scryfall's Oracle text of 2026-10-30 has the typo "+1/1"; the release notes print "+1/+1 counter". The line parses once the card data is refreshed (tests/test_rules_wave112t_dilemma.py tests the release notes' text).
- **Library of Lat-Nam** ("An opponent chooses one —", read by wave110k_cards as a choice made as the spell resolves) doesn't note a dilemma for that opponent: the one-off models the choice at resolution, and a copy would choose again; left as it was.
