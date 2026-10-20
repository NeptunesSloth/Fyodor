# Kicked spell follow-ups and alternatives

Six canonical spell effects compose existing native primitives without new
payment behavior, queues, callbacks, schema or card-name checks:

- Joint Exploration always scries and draws first. Only a kicked spell offers
  the subsequent optional land entry. Declining keeps the mandatory effects.
- Blood Tribute binds actual life lost after replacements, then gains that
  amount only if its native Vampire-tap kicker was paid.
- Zuko's Conviction replaces the hand return with a tapped battlefield return
  for the same graveyard target when kicked; native entry replacements apply.
- Reclaim the Wastes performs one search and shuffle, with one or two basic
  lands allowed according to the kicker payment. Failed searches remain legal.
- Tribute to Urborg applies its additional reduction using the current number
  of instant/sorcery cards in the graveyard at resolution. The resolving spell
  is still on the stack while this quantity is determined.
- Chocobo Kick uses the targeted creature as the damage source and reads its
  current power. Its native return-land kicker doubles that amount.

The parser-only leaf composes native kicked_gate, may_rest, put_from_hand,
return_card, search, pump and damage descriptors. Spell copies retain kicker
choices (CR707.10); this differs from predicates requiring an actual cast.
Tests use actual casts and costs, source-power and graveyard changes in
response, copied kicked reanimation, entry replacements and a fresh-process
resume after Joint Exploration's mandatory draw. Every scenario checks replay
and JSON state. Existing kicker suites cover adjacent cost and target handling.
