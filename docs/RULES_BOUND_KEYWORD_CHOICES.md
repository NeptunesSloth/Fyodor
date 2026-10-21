# Keyword choices with a bound subject

Hungering Puppetbeast and Hunter's Axe use the same choice-grant grammar as explicit
source and target grants. “It” is accepted only when the ordinary pronoun binder finds
an antecedent. Every alternative inherits the outer choice's bound object reference,
rather than independently interpreting “it” during resolution (CR 608.2d).

Puppetbeast pays its sacrifice cost, puts a counter if possible, then grants one chosen
keyword until end of turn. A counter prohibition does not prevent the later instruction.
An object that leaves and returns is not the same recipient. Hunter's Axe grants its
attack trigger to the equipped creature; that creature receives the chosen keyword even
if the Equipment has left before the trigger resolves (CR 113.7a).

Fourteen focused coverage/gameplay/near-miss tests and 111 selected regressions pass
(overlap), with replay/save-load. All alternatives, counter prohibition, Equipment departure,
source reincarnation, and an unbound pronoun are checked. Ruff and mypy passed.
