# Ordered payments, keyword counters, and activation-cost card references

Researched against Comprehensive Rules effective 2026-09-25 and the installed Oracle catalog.
These changes extend reusable rules grammar and resolution; unsupported wording stays manual.

## Ordered resolution

Energy wording is normalized before parsing, preserving the order of mandatory effects and
optional payments (CR 118.12). Lightning Runner gains energy before offering its eight-energy
payment. Blaster Hulk chooses damage targets in a separate reflexive trigger after payment
(CR 603.12). The hand-to-battlefield grammar shares the existing number vocabulary, allowing
Ugin, the Spirit Dragon to put up to seven permanents onto the battlefield after gaining life
and drawing cards. Tests include declining payments, insufficient energy, divided damage,
choosing no permanents, replay, and save/load.

## Keyword counters and decayed grants

Exalted and decayed counters grant complete triggered abilities, once per counter, with the
shared timestamp of the newest counter of that kind (CR 122.1b, 613.7c, 702.83, 702.147).
Ability removal and subsequent counter placement use the existing layer-six ordering.
Counters retained by Skullbriar grant their keywords outside the battlefield too; an exalted
ability in a graveyard does not trigger from attacks. Returning Skullbriar to hand clears its
counters as its own Oracle text requires.

An undated decayed grant persists for the affected object's lifetime (CR 611.2a).
Pronouns following linked-card returns refer to the newly returned objects (CR 400.7j),
not the preceding exile snapshot. Gisa scenarios distinguish her linked cards from unrelated
exiled cards and distinguish separate incarnations of Gisa.

## Announced X and cost-exiled copies

A cost requiring a card with mana value X announces X before targets and payment
(CR 107.3a, 602.2b). The number of cards paid remains one; the announced value filters their
mana value. Availability hints can show the ability before X is selected, but actual payment
must match the selected value, including zero. An optional resolution payment cannot use
this activation-only form without an announced X.

A copy of “the exiled card” can bind to exactly one chosen card exiled by the activation's
own supported cost (CR 400.7j). It uses that rules object, not a later incarnation of the
same physical card. Public objects exiled as costs are captured for last known information
if they leave exile before resolution (CR 608.2h). Existing optional-payment and linked-card
copy bindings remain separate.

Copy exceptions can add Artifact without also adding Creature, including a zero-power
Construct whose copied static ability applies before state-based actions (CR 707.9b).
Osgir, Tawnos, Dollhouse of Horrors, Kozilek, and Knollspine Invocation scenarios cover
normal payments, zero X, rejected payments, copies, temporary haste, and responses that
move the cost-exiled object. All scenario suites check replay and save/load behavior.

## Limits

These changes do not finish the catalog. Outside-the-game collection import and selection
remain pending, as do other unsupported rule families. The host's saved deck library does
not imply per-player collection ownership.
