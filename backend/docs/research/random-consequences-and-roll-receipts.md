# Random consequences and roll receipts

The shared random consequence programs preserve the printed result ranges. Sources and recipients remain separate identities: an exact damage source is frozen by object ID, while a redirected recipient is the original ability controller. Native `once` plus `batch` records cover all recipients of one simultaneous damage occurrence and expire at commit; a later combat damage step is another occurrence. One-shot prevention records opt into consumption even when that occurrence cannot be prevented (CR615.8,615.12).

Source choice uses CR609.7 current/controller LKI filtering solely during the choice. Its subsequent damage record contains the source identities, including the native future-permanent projection for a chosen permanent spell, without a continuing control restriction.

Plasma Caster's activation binds its current host into the ordinary announced target selector. The saved selector and copied ability retain that host even when Equipment changes attachment or leaves. Goblin Artisans likewise saves the activating source incarnation to distinguish another creature from this creature's other activations. Native stack targeting still checks the actual spell/ability controller.

Dice accumulation pauses after eight batches of at most100 physical dice. The native saved Continue cursor retains all completed raw results; it does not finish, cap or emit partial logical roll facts. Replacement extra dice are ignored before any retained roll events. An instruction to ignore all but the highest also runs before those events. The kept result vector preserves the unused member of a choose-one pair for Valiant Endeavor.

Revivify uses the existing exact current graveyard Arrival.object_id/from_zone receipt. Danse Macabre uses native APNAP choices and one simultaneous sacrifice, freezes only the caster's sacrificed creature's toughness from LKI, and offers only actual current graveyard cards. All returns use queued native battlefield entry, including replacements and commander state-based actions after the entire resolution.

Lae'zel's Acrobatics exiles before rolling. Its high branch follows actual first-return battlefield incarnations for the second exile, retaining original exiled incarnations whose entry was blocked. The delayed owner return excludes cards diverted to hidden zones or unrelated later incarnations.

Canonical complete records and WotC rulings were checked for all twenty cards. Gameplay, branch, identity, save/replay and cold-process verification is recorded alongside the focused test module. Cards outside this bounded family remain unclaimed.

Kept-die facts have a second bounded saved emission cursor after the full raw group is complete. It preserves the full result vector and emits the one-or-more fact only after all kept facts, without exposing priority or an intermediate state-based-action boundary. An801-kept-die fresh-process test proves the cursor and exact final event counts.

Activated abilities capture their validated announcement before mana payment in a server-only typed continuation. Paying with a mana ability may sacrifice the source or an announced target without causing a new announcement. Native payment still validates reserved nonmana cost objects, pays those costs once, and stacks the original source and target identities; resolution independently checks target legality. Fresh-process tests cover sacrificing the equipped host and Equipment during payment.
