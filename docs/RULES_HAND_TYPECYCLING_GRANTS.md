# Hand typecycling grants

Homing Sliver grants Slivercycling {3} to Sliver cards in every player’s hand (CR 113.6, 702.29).
The existing zone grant grammar now supports this scope and typed cycling costs. Changelings
qualify; departure removes the grant, while an already activated ability remains on the stack.

Private rules stats publish granted hand abilities only to viewers allowed to see that card.
The hand menu uses each server-provided ability index. Existing own-hand grants remain scoped
to their controller. Stabilizer also prohibits these cycling activations.

Nine focused scenarios exercise multiplayer, hidden information, source departure, typecycling
searches, replay and saved-state reloads. 119 selected backend tests, 87 frontend tests, build
and mypy passed. Catalog scan promotes only Homing Sliver: 27,746 FULL / 4,322 PARTIAL.
