# Wave 110I refused / deferred

- Sheltered Valley: replacement sacrifices others before it enters; an ETB-trigger stand-in changes timing (leaves-battlefield triggers, 614.12). Needs an "instead sacrifice, then put onto battlefield" replacement.
- Torrent of Lava: "as long as it is on the stack, each creature has {T}: prevent..." (static on the stack granting activated abilities); first line alone reads.
- Spoils of War: X fixed "as you cast this spell" with a non-X cost; only as_cast_values42 (greatest power) exists, no general foundation (7 cards share it).
- Glimpse the Cosmos: conditional graveyard cast (needs a Giant) plus exile-instead rider; escape.GY_COST has neither.
- Skyblade's Boon: activate from battlefield or graveyard; graveyard activation exists only for self-exile costs (casting.py ~5448).
- Cuombajj Witches: second target chosen by an opponent.
- Hipparion: pay-to-block restriction not modelled.
- Bioessence Hydra: "one or more loyalty counters put on planeswalkers" is one trigger per batch (603.2c); counters_put events are per object, so a proliferate over two planeswalkers would trigger twice (Hardened Scales etc. differ).
- Dodecapod: entering "with two +1/+1 counters" via the discard replacement needs an enters-with carrier on the replaced move; counters after entry would differ (614.12).
- Skyblade's Boon: "Activate only if on the battlefield or in your graveyard" needs a graveyard activation flag on a non-cost ability (casting.activate_ability only reads cost.from_graveyard).
- Phylactery Lich: "As ~ enters, put a counter on an artifact" read as an ETB trigger would let the state trigger sacrifice it first.
- Merieke Ri Berit: needs a persistent delayed trigger bound to the controlled creature (leaves/untaps); no such watch exists.
- Fasting: "you may skip your draw step instead" needs an optional-skip decision at step start (skips.py has only unconditional skips).
- Torrent of Lava, Dark Intimations, Aeon Engine, Hero of Bretagard, Aegis of the Legion, Grifter's Blade: stack-granted ability / Bolas-cast trigger / turn-order reversal / exile-from-hand batch / mentor event / equipment enters-attached choice: each a separate foundation.
