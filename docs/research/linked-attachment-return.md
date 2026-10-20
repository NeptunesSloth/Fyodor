# Gift of Immortality: linked creature and Aura returns

Oracle: “When enchanted creature dies, return that card to the battlefield under its owner's control. Return this card to the battlefield attached to that creature at the beginning of the next end step.”

Official rulings (2013-09-15): a token host returns neither itself nor Gift; if the returned creature is no longer on the battlefield at the next end step, Gift remains in its owner's graveyard.
https://api.scryfall.com/cards/2336faaa-fc6d-4fbb-bdd4-969eae565c72/rulings

The typed grammar delegates the immediate return to the ordinary return_card primitive, using the dies event's new graveyard ObjectRefs. This supports ordinary entry restrictions/replacements and all merged components. The source Aura's precise first graveyard ObjectRef is captured while collecting the original trigger, before the engine discards processed zone-change events. It is not reconstructed from whatever Aura incarnation happens to exist when the trigger resolves. Graveyard→exile→graveyard therefore cannot substitute a new Aura object.

The delayed primitive uses the existing serialized delayed-trigger framework, capturing the precise battlefield ObjectRefs of the creatures actually returned. A creature that blinks, dies again, phases out, or becomes an illegal enchanted object is unavailable at delayed resolution. Gift returns under its owner's control, independently of both the original Aura controller and the returned creature's owner/controller. Native attachment-entry legality applies without targeting (303.4i), including protection.

Merged hosts require an additional choice: CR 730.3c says an effect that finds the new object of a merged permanent finds and acts on all of its component cards. The native immediate return therefore returns all the creatures. CR 303.4d says an Aura that would become attached to multiple objects instead attaches to one chosen by its controller. The delayed ability stores a bounded list of exact returned creature references; the Aura owner chooses among surviving legal objects when it enters under that owner's control. The choice is private and persists through replay/save/load. This does not enumerate attachment permutations or grant a target.

Production hooks are restricted to the typed module, parser/effect registration, and trigger-creation source-reference capture. Existing attachments and delayed engine semantics are reused.
