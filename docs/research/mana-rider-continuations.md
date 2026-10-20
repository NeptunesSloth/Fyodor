# Suspendable mana-ability draw riders (research checkpoint)

Abundance's replacement body must finish before a mana ability's later riders, later filter activations, or the spell/ability being paid for continue. Supplying `then={"do":"noop"}` to the draw choke point while letting those callers run on would be incorrect. Replaying the original cast intent after a pause is also incorrect: the spell may already be on the stack, convoke/delve helpers paid, activation costs changed, and source objects gone.

## Existing boundaries

`casting.after_mana_ability` performs use/counter bookkeeping and synchronous rider iteration. Its callers are automatic payment (`pay`), ordinary mana production (`produce`), and chosen-cost paid mana (`_add_paid_mana`). `replace.draw_cards` already supports body/choice suspension with persistent `then` data, and dispatches through `replace.THEN`. `RulesState.payment_outer` saves one manually nested payment decision; it does not represent an automatic payment's Python call stack. `Plan.locked_cost` is transient, not a persistent post-payment frame.

## Proposed staged frames

A typed, serializable `ManaRiderFrame` contains the exact source card/object ID, activating player, remaining frozen riders/index, and terminal continuation. Use/counter bookkeeping happens once before starting the frame. The runner advances one rider at a time; a draw passes a `mana_riders` continuation to the existing draw choke point and immediately stops on suspension. Finishing the frame dispatches the terminal continuation. Old source identity and source LKI remain available even when the source was sacrificed.

An automatic payment frame retains its selected payment, source metadata, pending source/filter sequence, and a typed post-payment continuation. Input payments for filter abilities are their own frames. Their provenance does not become spell-payment provenance. The outer source/filter sequence resumes only after a replacement body has completed. The post-payment continuation receives the actual payment exactly once.

Post-payment terminal stages must be explicit; no replay of announcements or whole intents:

- normal cast: frozen announcement/targets/alternative/additional costs and cast origin, helper/assist payment state, then remaining costs and cast finalization;
- free cast: its distinct payment/finalization stage and free-cast effect continuation;
- ordinary activated ability: retained created ability ID, cost choice objects, frozen source/definition/modal data, then remaining costs and activation finalization;
- manual mana ability: completion with priority, or restoration of the saved nested payment;
- filter mana ability: finish producing the selected output and riders, then resume its parent filter/payment sequence;
- hand/special actions: turn face up, transmute, cycle, suspend, plot, foretell, companion;
- external payments: assist, attack taxes, Licid ending, Room unlocking, and optional effect payments (which then resume the effect context).

These boundaries require extracting post-payment helpers from existing synchronous functions. A callback name with typed saved payload can share the existing `replace.THEN` dispatcher; pending decisions already serialize that continuation graph. New saved state must default compatibly and must not retain Python callables.

## Required verification

CR 605.1a (2026-09-25) excludes activated abilities whose cost or effect moves any card to or from a library, ignoring replacement effects except self-replacements. Chromatic Sphere and the Odyssey Eggs therefore have ordinary activated abilities that use the stack; “Activate only as an instant” is reminder text, not a timing restriction imposed on a mana ability. Their actual manual activations must be respondable, resolve on the stack, and then use Abundance correctly. They cannot activate inside a pending mana payment because they are not mana abilities. Millikin already used this classification rule for its milling cost.

Foundational automatic/filter/nested tests inject internal draw-rider metadata into otherwise legal printed test mana sources through a scoped fixture below the Oracle classifier. They exercise persistent payment plumbing without falsely treating printed draw abilities as mana abilities. Real future callers can still require these continuations when a genuine mana ability's life gain or damage is replaced by a draw; CR 605.1a explicitly ignores such replacements.

Cover manual activation, generic activation nested in an outer self-payment prompt, automatic payment, a filter input funded by another source, optional/paid effect payment, multiple automatic sources, and multiple riders. At each replacement choice, verify no later rider/cost/cast event has occurred; replay and reload there, then finish once. Cancel before costs remains allowed; a paid ability's replacement choice cannot undo its paid sacrifice. Source departure, spending restrictions and provenance must survive. Ordinary draw-body tests alone cannot justify an unverified live payment path.
