# Cyclone Summoner — staged native hand-cast sweep

Staged only; no live registration or admission. Full actual canonical and empty official rulings were read from `/tmp/counter66-summoner-canonical.json` and `/tmp/counter66-summoner-rulings.json`.

The exact printed enter trigger retains the native hand-cast payment receipt, original controller, and intervening condition both when triggering and resolving. Its body delegates a native single-batch bounce of all battlefield permanents except lands and objects with Giant or Wizard subtypes. It never hardcodes the source's identity or creature-only scope, so a noncreature Wizard Equipment is protected while the source loses protection if its subtypes change. All cards return to their owners, regardless of current controller.

Twelve unique native cases passed, including one true cold reload. They use real paid five-generic/two-blue source casting, three players and several permanent types; Giant, changeling, legal noncreature Diviner's Wand Wizard, and Dryad Arbor exclusions; a stolen artifact returning to its owner; actual Zombify and Cloudshift negative entries; a paid source spell changing controller before entry (new controller did not cast it); pending original hand-cast trigger surviving source bounce/control/blink; real Unnatural Selection adding Wizard to another creature or removing Giant/Wizard from the source; and fresh-process pending sweep resolution. Thirty-six related production-native cases passed: Stormfront Riders 13, and Slab Hammer/Azorius Aethermage 23. Scoped mypy and Ruff pass. No custom primitive or shared kernel edits.

Exact hashes and evidence: `/tmp/counter66-staged-manifest.json`; proposed four-line hook: `/tmp/counter66-hooks-proposal.patch`.
