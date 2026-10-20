# Public played-card receipts and optional revealed-card entry

Batch36 supports Search the City, Cemetery Gatekeeper, Cemetery Protector, and Minamo's Meddling through exact public event metadata. It additionally supports Whiskervale Forerunner and Break Out through a shared two-stage optional selection/entry sequence.

## Played lands

Playing a land remains a land play when its entry is replaced or diverted. `Event.played_snapshot` is optional for old-save compatibility and preserves the selected land face before native entry-cost diversion or a move to another destination. It carries native snapshot traits rather than reconstructing the card from its new zone. The existing successful battlefield route retains its normal current-object semantics. `from_zone` now records the actual play origin on both routes, so an entry log is not required to recognize a diverted play from exile. This creates no ETB or landfall event.

Search the City's same-name qualification is checked when the play/cast event occurs. It is not an intervening-if condition. It re-reads the exact old source's linked pool for the optional card and subsequent empty-pool check. The extra turn requires an actual sacrifice of that source incarnation. Cemetery triggers do have the printed intervening-if and use the current linked card plus the played event's exact object/current characteristics or snapshot.

## Public splice names

`PaymentRecord.spliced_names` is captured at announcement and carried in the native `_PostCast` persistent payment continuation. New ordinary casts record an empty list; an absent receipt in an older save is unknown. Native stack copying already aliases the original payment metadata, preserving this public splice provenance without treating the copy as cast.

Minamo freezes the targeted spell's current controller and splice names before the counter attempt. Its following reveal and simultaneous named discard occur even when the native counter is prevented. Missing legacy information is explicitly restored by that controller through a public typed choice, recorded in the receipt, and never inferred from the current hand or rules text. The parser accepts semicolon-separated canonical names or the explicit answer `No cards`.

## Optional revealed-card placement

Native `pick_looked` now has an opt-in `to: choose`: exact-object validation, private filtered choice (including zero matches), selected-only reveal, removal from the remaining looked set, and normal named binding happen without a zone change. The new `look_optional_placement` leaf queues a native optional `return_choice` to the battlefield, so pausing entry replacements use the established continuation machinery. A still-original library card goes to the hand when entry was declined, ineligible, or prevented. A new incarnation is not pulled from an unrelated zone. Break Out grants haste only to actual battlefield arrivals. Whiskervale uses the native first-controlled-target event, including copied spells, and permits entry only during the resolving controller's turn.

Canonical tests: `test_rules_name_event_receipts.py` (13), `test_rules_look_optional_placement.py` (14). They cover actual positive effects for all six cards, diverted Lake of the Dead, native paid splice, uncounterable spells, copied-spell controller provenance, source/linked-card incarnation changes, public legacy restoration, private look choices, Cage entry prevention, Valiant spell copies, and four fresh-process resumes. Related native cast/land/entry-cost and Batch35 name regressions: 183 passing cases.

## Case File Auditor

`case_solved` is a native event emitted when the existing To solve instruction is reached during resolution. It records the resolving ability's controller and exact original source object. A manual Solved choice, countered ability, or failed intervening-if emits no event. The event is independent of whether its source is still present to receive the designation. This implements the official Auditor ruling that its trigger refers to resolving a To solve ability, including a copied ability.

The separate `case_solve_watchers` leaf composes native ETB-or-solve triggering with private exact look6, optional enchantment reveal/hand movement, and random bottom placement. Ten canonical gameplay tests include Case-only any-color spending (four blue mana actually cast the green Case; ordinary Bears cannot use that permission), native seven-land Hothouse solving, failed/countered/manual cases, source departure, Strionic Resonator copies, and two fresh-process resumes. When a copied To solve ability solves a still-present Case, the original fails its unsolved intervening-if. With the source gone both copies can resolve, and each resolution triggers Auditor without inventing a Solved designation.
