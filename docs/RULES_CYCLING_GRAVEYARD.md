# Cycling graveyard rules

Abandoned Sarcophagus grants casting permission to spells with cycling in its controller’s
graveyard. It preserves normal timing and payment, excludes land plays, and ends when its
source leaves. Its replacement exiles cycling cards bound for that player’s graveyard
unless the card is being discarded to pay cycling (CR 614.1, 702.29c/f).

The planning transaction marks only that cycling card during payment. This marker never
enters saved game state; zone changes and their results remain normal replayable events.
Normal, life, sacrifice and typecycling fees share this distinction. Granted hand cycling
qualifies while discarding; the grant does not persist into the graveyard or library.

Eighteen focused scenarios cover costs, ordinary discards, milling, ownership, casting,
source departure, granted cycling, replay and saved-state reloads. 209 selected regression
tests passed before the final two milling scenarios; mypy and Ruff passed. The complete
Commander-legal catalog promotes only Sarcophagus: 27,747 FULL / 4,321 PARTIAL.
