# Card copies cast during resolution (CR 707.12)

The Tale of Tamiyo IV and Arcane Bombardment now use typed card-copy casting
sequences. These create ephemeral cards in exile and actually cast the selected
copies; ordinary cast triggers and payment records apply. Isochron Scepter uses
the same existing casting machinery and remains covered by regression tests.

Tamiyo targets any number of instant, sorcery, or Tamiyo planeswalker cards in
its controller’s graveyard. It copies only the originals actually exiled and
allows each copy to be cast with its costs paid. A Tamiyo planeswalker spell
copy resolves as a token with its normal starting loyalty. Bombardment randomly
exiles an eligible graveyard card and copies every card linked to that source
object, including previously linked cards when the graveyard is empty. Its
copies receive the printed mana-cost waiver.

Paid casting during resolution now uses the normal casting pipeline through a
narrow, server-created resolving permission. This preserves alternative costs,
mandatory additional costs, cost reductions, manual payment, and cancellation
back to the remaining copies. Force of Will can use its life/exile alternative;
a waived copy cannot choose a second alternative. Cards without a mana cost
remain uncastable unless a valid alternative cost is available. X uses the
existing supported announcement range, including values above forty.

“Any number” iterates the remaining eligible copies without a ninety-nine-copy
limit. Copy creation checkpoints after bounded work and resumes from saved
object identities. Ephemeral cleanup groups table actions within their API
capacity. Split and modal double-faced backing printings retain their face data;
Aftermath and Fuse source-zone restrictions remain enforced. Unsupported generic
meld/reversible/prepare layouts still request manual handling; none is a legal
instant, sorcery, or Tamiyo planeswalker card target in these fixture scenarios.

Canonical Oracle fixtures and gameplay tests cover zero and illegal targets,
paid and waived casts, X=41, alternative and additional costs, payment cancel,
missing costs, split/MDFC faces, Aftermath/Fuse restrictions, planeswalker token
entry, cast triggers, source blink/control changes, linked exile identity,
replay/save-load, and cleanup of more than 250 ephemeral copies. A separate
large scenario creates 101 copies and actually casts the first 100 to prove the
remaining copy remains available across processing checkpoints.
