# Behold and exile additional costs

The canonical Champions of the Perfect, Champion of the Path, Champion of the Weird,
Champions of the Shoal, and Champion of the Clachan require their caster to behold
a card of the indicated creature type and exile it. This is one mandatory
additional cost: choose either a qualifying card in hand or a qualifying permanent
under the caster's control. A hand card is revealed before exile. The spell itself
cannot pay its own cost. A noncreature card with the required creature type can pay,
and changeling is evaluated through the existing derived characteristics.

The implementation reuses the native private additional-cost choice and payment
record, with a distinct `BEHOLD_EXILE` component. Ordinary behold remains unchanged.
The existing linked-exile framework transfers the cost's exact exile objects to
the permanent as the spell resolves (CR 607.2q). Its existing leaves-the-battlefield
trigger returns those objects to their owners' hands. Copies, reanimation, and
blink do not inherit another incarnation's cost payment.

The transfer checks the recorded exile object snapshot, rather than just the
physical card identifier. A paid card that leaves exile and returns before the
spell resolves is a new object and must not become linked. Older payment records
without object snapshots retain the existing compatibility behavior.

Canonical fixtures and gameplay regressions cover all five cards, payment from
both zones, hand privacy and cancellation, invalid choices, tribal noncreatures,
changeling, stolen permanents, tokens, countering and reanimation, blink, copies,
stale exile objects, replay, and fresh-process saves during both payment and the
pending return trigger. Manual table moves are used only to construct the stale
object case; native Unsummon, Counterspell, Reanimate, Act of Treason, and Ephemerate
exercise the actual rules events elsewhere.
