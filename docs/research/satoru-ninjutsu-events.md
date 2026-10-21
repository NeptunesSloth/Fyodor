# Satoru Umezawa: ninjutsu activation triggers

Satoru's trigger observes activating a ninjutsu ability, including commander ninjutsu and ninjutsu granted to a creature card in hand. The native activation event now records that keyword-ability category from its actual generated activation text; the trigger parser and matcher require that category. Ordinary activations do not match. Mana abilities remain excluded (CR 702.49, 602.2, 605.1).

The canonical static “Each creature card in your hand has ninjutsu {2}{U}{B}” also needed admission to the existing zone-keyword grant whitelist. The native dynamic hand grant, generated keyword ability, return-an-unblocked-attacker cost, entry tapped and attacking, and exact object identity are reused unchanged. Other zones do not gain this ability, and the grant ends when Satoru's static stops applying.

The trigger's existing once-each-turn limit is consumed when it triggers, even if Stifle counters it. The existing look-three, choose-one, and order-the-rest pipeline resolves above the ninjutsu ability. A trigger already created survives Satoru leaving. Returning Satoru to hand to pay the ninjutsu cost instead removes its trigger before that activation is complete, so that activation does not trigger it (CR 602.2, 603.2).

Canonical gameplay tests cover native ninjutsu, granted ninjutsu, commander ninjutsu from hand and from the command zone, exact top-three selection and bottom ordering, serialized pending choices, repeat activation limits and reset, unrelated Azure Mage activation, source departure, countering the trigger, returning Satoru as the cost, replay, and save/load. Existing hand-grant, commander-ninjutsu, and Silver-Fur Master suites guard the shared pipelines.
