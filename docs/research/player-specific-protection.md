# Protection from a player: Noble Heritage and True-Name Nemesis

Implemented against CR 702.16k. Target legality uses the actual spell or ability controller. Damage uses the physical damage source's current controller, its last-known controller when appropriate, or its owner when uncontrolled. This distinction matters when an activated ability's source changes control and when another player copies Guerrilla Tactics' discarded-card trigger.

Characteristics carry noncopiable object controller/owner metadata, reasserted after layer-one copy recipes and last-known characteristics reconstruction. Attachment legality uses the intended entering Aura controller; existing Auras and Equipment use their current controllers. Role token previews receive their prospective controller too.

True-Name Nemesis stores the chosen player's exact identity on the current object. Copies choose afresh rather than inheriting the donor's choice. Ability loss suppresses protection without erasing that choice. The internal generated protection keyword uses `player p2`, avoiding the colon reserved for activated-ability parsing.

Noble Heritage reuses the each-player counter offer engine. Protection follows an opponent's accepted legal offer, including when counter replacement reduces the result to zero; Agitator Ant continues to depend on counters actually put. The granted commander's trigger controller receives protection until their next turn, independently of Background ownership and later source departure or control changes. Solemnity prevents accepting an illegal counter placement.

Canonical gameplay tests cover actual stack-controller versus source-controller distinctions, owner fallback, Aura and Equipment control changes, Aura entry preview, choice identity/blink/copy, ability loss, replacement-modified acceptance, original trigger beneficiary and expiry, and loss of life remaining unaffected. Fresh Python process resumes cover the entering-player choice, the counter offer, and counter replacement continuation. Existing protection, attachments, and Agitator Ant suites pass unchanged.

## Resolved player qualities and opponent groups

The next family adds Eon Frolicker, Absolute Virtue, Cliffside Rescuer, and Figure of Fable. Resolved effects bind actual opponent identities once; changing the protected permanent's controller does not rewrite that set. Figure's ordinary animation effect expands its opponent-protection line at resolution. Absolute Virtue's continuous static player shield instead follows its current controller's opponents and stops with ability loss or source departure.

Eon uses the ordinary cast-condition and extra-turn machinery. Its opponent target is shared by the extra turn and protection instructions. Player protection belongs to the original ability controller; planeswalkers are the exact objects controlled as the effect resolves, not later entrants (611.2c). Both expire at that controller's next turn even if the creature leaves or a protected planeswalker changes controller. Reanimating Eon does not satisfy the cast condition; casting Clever Impersonator and having it enter as Eon does. Native pending-trigger save/resume works in a fresh Python process without importing tests.

Canonical Oracle data: tests/fixtures/player_protection_effects_cards.json. Gameplay tests: tests/test_rules_player_protection_effects.py. Guardian Archon's secret choice/reveal cost and Courageous Resolve's fateful-hour rider remain separate work.
