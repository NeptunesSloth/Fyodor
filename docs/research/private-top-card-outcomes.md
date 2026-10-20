# Optional private top-card outcomes

The Biblioplex and Delver of Secrets // Insectile Aberration use a private exact look at the top library card, followed by native saved card decisions and native movement/transform effects. The card is not revealed merely because its controller looked at it.

Delver allows revealing any top card, including a land or other non-instant/non-sorcery. The native choose-only looked-card operation publicly reveals the selected card and binds its original library object without moving it. Only a selected revealed instant or sorcery queues the native transform instruction. Whether revealed or declined, the card remains on top. Transform refers to the original source object; a source that leaves and returns is a new object (CR400.7), and its earlier trigger does not transform that new permanent.

Biblioplex's last activation checks exactly zero or seven cards in hand when activated (CR602.5). Native preflight reparses original Oracle restriction text, so the shared restriction grammar now represents the general wording 'you have exactly N or M cards in hand' as an OR of native exact-count predicates. It is not sufficient to change only a scripted definition's restriction metadata. The count is not checked again during resolution, as the official ruling specifies.

After a private look, Biblioplex optionally reveals an instant or sorcery and puts it into hand. If the original card remains in the library, it may instead be put into the graveyard. Declining both leaves it on top and private. Native reveal occurs before a selected card moves into the hand; normal movement resets its current revealed marker, while the resolved public reveal remains in replay history. No unsupported inference from card type causes an automatic public reveal.

Canonical tests and fixture are `backend/tests/test_rules_private_top_card_outcomes.py` and `backend/tests/fixtures/private_top_card_outcomes_cards.json`. They cover both allowed hand sizes, rejected other hand sizes, paid cost/tap, announcement-only gating, instant and sorcery transformations, voluntary nonspell reveals, declined reveals, original-source identity, and fresh-process continuations at both cards' private decisions.

Official ruling excerpts preserved in `/tmp/fyodor-qualified-look36-rulings.json`:

- Biblioplex, 2021-04-16: If neither reveal/hand nor graveyard is chosen, the card stays on top. Hand size only matters when activating.
- Delver, 2011-09-22: A card may be revealed even if it is not an instant or sorcery. Revealing does not move the card from the top.

Public references: https://scryfall.com/search?q=%21%22The+Biblioplex%22 and https://scryfall.com/search?q=%21%22Delver+of+Secrets%22.
