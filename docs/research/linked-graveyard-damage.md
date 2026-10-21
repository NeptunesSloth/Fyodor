# Linked exile cleanup and damage

Valakut Exploration's Oracle text and official rulings were checked against
[Scryfall's printing](https://api.scryfall.com/cards/18cb7bf6-9c7c-4e62-a678-7b75862e2f64) and
[official rulings](https://api.scryfall.com/cards/18cb7bf6-9c7c-4e62-a678-7b75862e2f64/rulings).

The ruling for Two-Headed Giant states that the opposing team loses 2 life
"for each card put into its owner's graveyard." Thus damage counts cards
actually put into graveyards, rather than their mana values or cards diverted
elsewhere by a replacement effect (CR 614.6). Rest in Peace makes this count zero.

CR 607.2a and 400.7 bind the exiled cards to the source object. A card played
before cleanup, or one that left exile and returned, is excluded. A source that
left and returned has a new linked set. The granted play permission persists
when the enchantment leaves, as the official ruling also confirms.

CR 603.4 checks the intervening condition both at the end-step event and when
the trigger resolves. Once triggered, the ability uses the original source
object's linked set even if that source leaves (CR 113.7a, 608.2h). The damage
instruction uses the controller of the triggered ability and the normal damage
replacement/prevention pipeline.
