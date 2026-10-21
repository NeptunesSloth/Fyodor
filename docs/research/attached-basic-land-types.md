# Nylea's Presence: add every basic land type

Oracle's missing line: “Enchanted land is every basic land type in addition to its other types.”

CR 205.3i lists Plains, Island, Swamp, Mountain and Forest. Adding these subtypes differs from setting a land's types under 305.7: it preserves its existing land subtypes and printed abilities. CR 305.6 supplies the corresponding intrinsic mana abilities. The existing layer-4 add_subtypes representation and intrinsic-mana reader implement those rules; no new layer behavior is needed.

The attached-types parser emits add_subtypes for these five types. Its consistency check accepts a land-only, subtype-addition-only result only when every added subtype is one of these five basic land types. Existing guards against adding creature subtypes to a noncreature land remain intact. It does not set_land_types, erase other subtypes, erase abilities, or make the land Basic.

Canonical gameplay verifies the Aura's native enters draw, an Artifact Land retaining Artifact and indestructible and its original colorless mana ability, all five gained mana abilities actually activating, Urza's Tower retaining both nonbasic land subtypes and its original conditional colorless ability, Aura removal, controller changes, and becoming a Plains without entering again (no landfall). Blood Moon tests preserve timestamps and 305.7: a later Moon replaces the subtypes with Mountain; a later Nylea adds all five after Moon, while the original abilities already removed by Moon remain removed. Every case replays and round-trips through save/load.
