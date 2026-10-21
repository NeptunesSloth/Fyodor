# Uncast creature entry: Containment Priest and Hallowed Moonlight

Canonical Oracle text (local printings database):

- Containment Priest: “Flash / If a nontoken creature would enter and it wasn't cast, exile it instead.”
- Hallowed Moonlight: “Until end of turn, if a creature would enter and it wasn't cast, exile it instead. / Draw a card.”

Official Oracle rulings:

- https://api.scryfall.com/cards/384e5164-9012-41e0-998a-dbdad486b4a1/rulings (2021-03-19): creatures cast from unusual zones are unaffected; a noncreature entering as a creature (March of the Machines) is exiled; a creature entering as a noncreature (Heliod with insufficient devotion) is unaffected; Priest does not exile itself or other simultaneous entrants.
- https://api.scryfall.com/cards/94fd0c0f-4a6a-47cf-9f50-df0bbf19aae4/rulings (2015-06-22): a creature token is put into exile instead and then ceases to exist; tokens are never cast, even when the creating spell was. Creatures cast from any zone are unaffected regardless of mana paid.

## Shared behavior

Use one typed entry-redirection definition, differing by a nontoken filter and whether supplied by a battlefield static or a turn-scoped effect record. Determine whether the entering object was cast from its current stack object's PaymentRecord.cast_from, never an old permanent's record retained before a blink. A free cast counts; a copied spell does not. Derived characteristics as it would exist on the battlefield determine whether it is a creature, including entry copying, animation and devotion.

The event is replacement of entry, not a prohibition on creation. A Moonlight-diverted token must be created directly in exile, have no battlefield entry event, remain in the creation result binding, and subsequently cease to exist through normal state-based actions (704.5d). This means Springheart Nantuko did create a token and does not make its fallback Insect merely because that token is exiled. This differs from an actual token-entry prohibition under 111.5.

Entry uses three coordinated hooks: replacements.move_together/entry_plan, permanent spell resolution through engine.leave_stack's resolve_top action, and replace._make_tokens' direct create_token action. Applying after_entry would falsely emit battlefield events and is incorrect. CreateToken has an optional exile destination (default battlefield) to represent replaced creation truthfully. Source static eligibility must be captured before simultaneous entry; a newly entering Priest cannot affect its coentrants.

Copy-as-entry replacements precede these ordinary redirects under 616.1c. Other entry replacements must remain ordered through the existing choice/continuation machinery. Duplicate redirects with identical exile outcomes require no additional distinction in the resulting destination.

## Required gameplay verification

Normal and free casts from hand/exile/graveyard; copied permanent spells; Priest flashed in before an opposing spell resolves; uncast Priest self and simultaneous reanimation; blink and reanimation with a stale prior cast record; source removal/ability loss; Moonlight draw and turn expiry; noncreature entering animated and creature entering noncreature; replaced token creation with Divine Visitation and token-copy characteristics; no false enters triggers, normal token cessation, preserved creation bindings; replay and JSON save/load through every private or replacement decision.


## Implementation and verification

The typed module is `app/rules/creature_entry_redirect.py`; static and turn-record definitions share the candidate reader. `replacements.replace_move` prepares individual routes for simultaneous moves against the original table, permanent spell resolution checks before leaving the stack, and token creation writes the replaced destination directly. The existing entry-copy choice occurs before move routing (616.1c); a reanimated Metamorph copying a noncreature Sol Ring enters normally under Priest.

Incoming own layer-4 statics previously depended on an already-present battlefield-table row. The layer reader now parses the incoming object's same safe own-type statics and evaluates their conditions in a scratch view including its own mana cost. This implements the official Heliod ruling and its devotion boundary: Sun-Crowned costs {2}{W}, so existing devotion four plus its own W reaches five. Controller, not owner, supplies the devotion. Its other global abilities never affect simultaneous entrants through this scratch view.

The canonical fixtures include real Oracle metadata. Actual Reanimate, Refurbish, Living Death, Ephemerate, Omniscience, Double Major, Metamorph, Springheart Nantuko, and token replacement scenarios exercise the hooks with replay and save/load checks. A Double Major copy is not cast but becomes a token as it resolves (111.12): Priest allows it, Moonlight exiles it. A genuinely cast copy of a card instead has a nonempty cast_from payment fact and is allowed regardless of token representation.
