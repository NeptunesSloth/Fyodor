# Nine-Lives Familiar: delayed return with fewer counters

Oracle: “This creature enters with eight revival counters on it if you cast it. / When this creature dies, if it had a revival counter on it, return it to the battlefield with one fewer revival counter on it at the beginning of the next end step.”

The official Scryfall rulings endpoint currently returns an empty list:
https://api.scryfall.com/cards/24587cc6-0fbd-4e28-b94a-e808885fcc61/rulings

The conditional eight-counter entry replacement already parses. The missing rule is a delayed return whose entry-counter count is fixed from the dead object's counter count. Under 603.4 and 608.2h the trigger's revival-counter test and count use its battlefield last-known information; counters do not transfer to the new graveyard object (122.2). Return must capture the exact graveyard incarnation (400.7e / 603.7c), not look for whichever familiar card is later in that graveyard.

The bounded typed parser accepts the return-with-one-fewer-counter delayed wording and emits a scheduling primitive. At original trigger resolution, read the dead event object's count, clamp count minus one at zero, and create a native delayed trigger carrying an immutable integer and the exact new graveyard ObjectRef. Its deferred native return_card uses that bound reference with integer counter_n. This reuses entry restrictions, entry replacement ordering, token cessation and copied characteristics rather than setting counters after entry. No delayed chronology engine changes are needed; the existing create_plain helper records the next end step through Temur's shared phase chronology.

Required tests: actual cast enters eight, repeated deaths return seven down through zero and then stop; reanimation without casting supplies no eight-counter entry; copied spell not cast; Doubling Season doubles initial eight to sixteen and next returned fifteen to thirty; Solemnity prevents counters on initial/return entry; removal of the graveyard card or graveyard→exile→graveyard defeats return; Priest exiles attempted return; effect survives source absence; death during the end step waits for the next end step; tokens don't return; merged component semantics if relevant; replay and save/load preserve pending count and exact object identity. The count must not be reread from a new object or from later counters on a separate incarnation.

Implementation is integrated through `app/rules/delayed_fewer_counters.py`, parser registration, and effect registration only. No delayed chronology or counter engine changes are needed.

The original dies ability creates its delayed trigger even if its old graveyard object already left before the original ability resolves. Raw event.new references are captured rather than rescanning whichever card is now in the graveyard. A qualifying token that already ceased has an empty new-object binding; it still creates the observable delayed ability, which later returns nothing. This preserves the trigger's timing and potential counterability.

When the fixed entry count is zero, the return instruction has no counter contribution. This avoids the native shorthand's default-one convention, so the one-counter death correctly returns a zero-counter creature; the next death does not trigger. Native entry counter replacements remain dynamic: a source dying with sixteen under Doubling Season returns with thirty if Doubling remains, or fifteen if it leaves before entry. Doubling plus Winding Constrictor produces an actual 616.1 choice before the card leaves its graveyard, with the integer and exact references preserved through save/load.

Gameplay includes all eight revivals and final exhaustion, controller versus owner, source movement both before and after scheduling, actual mutate components returning separately with the same fixed count, Solemnity, Priest, zero-counter uncast reanimation, death during an end step, and actual Cackling Counterpart token creation and cessation.
