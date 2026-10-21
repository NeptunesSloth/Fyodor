# Conditions on a sacrificed activation payment

Authority: Comprehensive Rules effective 2026-09-25, CR 601.2h / 602.2b (cost
payment), 701.21a (sacrifice), 608.2h (last known information), 118.11 (replacement
effects do not undo a payment), 113.7a (abilities independent of their source),
700.12 (outlaws), and 702.73a (changeling).

Thallid Omnivore and Boneyard Desecrator inspect the creature sacrificed to pay
for their activation. Its battlefield characteristics matter, including type
changes and changeling, even after it becomes a new graveyard/exile object or a
token ceases to exist. A replaced destination does not undo the sacrifice cost.

The condition grammar reads “a/an [selector] was sacrificed this way” as a test of
this stack object's sacrifice payment. Existing payment records and LKI snapshots
supply the objects. The definition guard requires a genuine sacrifice cost;
resolution sacrifices need separate bindings. “The modified creature” after two
distinct alternative costs remains manual. No new state fields.

15 focused scenarios and 453 selected regression tests pass (overlap), with
replay/save-load gameplay checks. Coverage includes matching/nonmatching creature
types, changeling, token cessation, independently pending activations, source
departure, Lignify removing a qualifying type, Arcane Adaptation granting one,
Rest in Peace replacing the destination, and unsupported-condition guards.
Ruff, mypy (349 files), and whitespace checks pass.

The catalog promotes exactly Boneyard Desecrator and Thallid Omnivore, with no
lost FULL support: 27,667 FULL / 4,401 PARTIAL of 32,068 Commander-legal cards.
