# Wedding Ring

The cast-only entry trigger reuses the native cast-history intervening condition and target-opponent legality. Its copy instruction now supplies a creator player reference to native token_copy. The original trigger controller remains unchanged: the specified opponent creates the token, with their token doublers and creator replacements. The copy uses current copiable values or battlefield last known information if the source leaves. A token copy was not cast, so it does not recursively create another Ring.

The reusable player-event qualifier parses “an opponent who controls [permanent selector] draws a card/gains life during their turn”. It checks the event player's current controlled permanents when matching the event. This qualification is part of the trigger event, not an intervening-if condition; removing that player's Ring in response does not remove an existing trigger. Native during-their-turn matching prevents reciprocal draw/life loops. Several qualifying Rings controlled by the event player still satisfy one qualifier, rather than multiplying the number of events.

Names use the existing named_self/name: selector extras. Literal names remain literal when a copied ability is on a differently named object, while normalized self-name text refers to the source name. The qualifier also requires the Artifact type: a named Ring enchanted by Song of the Dryads is a land and does not qualify.

Fixtures copy complete Oracle metadata from the canonical local database. Tests use actual paid Ring casts, Revitalize, Divination, Ghostly Flicker, Song of the Dryads, Disenchant, Doubling Season, and Crafty Cutpurse, with replay and JSON save/load. Shared edits are confined to event parsing/matching, the generic token-copy creator field, and one targeted copy-effect parser template.

Verification: all eleven focused canonical cases pass, together with 66 related event/token/replacement cases (77 combined) and 64 additional native current/LKI token-copy cases. All processes exit 0. Scoped Ruff and diff checks pass.
