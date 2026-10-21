# Counter, scry, and opponent draw-or-mill choices

Palantír of Orthanc uses ordinary typed counter, scry, optional-payment, draw,
mill, and life-loss effects. The opponent decides after the counter and scry
finish (CR 608.2c/d). The mill count reads the source's current or last known
influence counters (CR 608.2h). Milled card mana values use the existing mill
snapshots, including split cards, X costs, and replacements.

The [official ruling](https://api.scryfall.com/cards/6efb6a69-562c-4d95-858d-b067444cfd7e/rulings)
confirms that the opponent is targeted when the trigger goes on the stack.
If the target becomes illegal, none of the counter, scry, draw, or mill occurs
(CR 608.2b). A focused gameplay regression checks this complete failure to resolve.
