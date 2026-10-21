# Battle of Wits: native library-count intervening condition

Status: independently reviewed, production-tested, and admitted by the trigger agent. Exact count ownership: `/tmp/trigger50-admitted-manifest.json`. No custom primitive or shared algorithm change.

The complete actual card and both official rulings were reviewed in `/tmp/counter54-scout-canonical.json` and `/tmp/counter54-scout-rulings.json`. The exact ability delegates to the native upkeep win-game trigger and adds the same native library-count condition at trigger time and resolution: at least 200 cards in the ability controller's library. The winner/condition use the original trigger controller even if the source changes controller, leaves, or returns as a new incarnation.

Native tests use actual physical libraries exceeding 200 cards and the real paid 3UU enchantment. Owned card movement prepares exact 199/200/201 library conditions. Cases cover no trigger at 199, win at 200/201, a paid Inspiration dropping 201 to 199 before resolution, source bounce/blink/control change, native Abyssal Persecutor preventing victory, two genuine fresh-process pending-trigger continuations, and reaching 200 after upkeep without creating a retroactive trigger. All draw and source-response spells are native paid actions. Related native win-game/game-result tests run separately.

Hook proposal `/tmp/counter53-library-hooks-proposal.patch`; final review manifest `/tmp/counter53-library-review-manifest.json` is written only after whole/native/cold gates pass.
