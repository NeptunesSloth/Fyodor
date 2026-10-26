# Wave 110M refusals
- Aeon Engine: "Reverse the game's turn order" — the engine's only turn order is `seat_order`, which is also seating (left/right, draft, votes); reversing it would corrupt those. Needs a separate direction flag read by every turn-advance site.
