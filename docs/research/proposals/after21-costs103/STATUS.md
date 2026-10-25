# Optional waterbend costs and paid branches

Depends on costs102. Patch contains only costs103 owned functional hunks. Three canonical PR21 PARTIAL names now FULL: Spirit Water Revival, Ruinous Waterbending, Katara, Seeking Revenge. No other optional bodies claimed.

Native optional cost announcements supply waterbend amount before modifiers; exact chosen nonmana helpers are paid through existing cost machinery. Printed mana remains payable separately. Real paid receipt reads before cast-origin guard so copies retain decisions without inventing mana or kicker. Adapters only disambiguate canonical additional-cost condition and Katara discard branch, then use native spell/trigger parsing and effects.

Native-final9.log9 PASS: all3 definitions plus paid/unpaid paths (Spirit draw2 vs shuffle/draw7/no limit/self-exile; Ruinous same-spell SBA deaths watch; Katara discard vs no discard). cold-and-related4.log3 existing blight PASS, initial cold hand delta asserted1 too high because pending source remains in hand; fixed. cold-copy-final3.log1 true cold PASS,2 test response setup errors (Reverberate target no longer on stack), corrected native copy fixture. Final copy rerun tracked separately. Scoped mypy5 and configured Ruff6 PASS. All earlier failures retained; no whole-suite claim.

Final closure: copy-opponent-native2.log2 PASS actual opponent-controlled Reverberate copies. Copies inherit actual paid decision despite cast_from=None, independently of mana spent/controller. Total12 unique native checks (9 +1 true cold +2 copies),3 related blight, mypy5 and Ruff6 PASS. Earlier copy fixtures wrongly waited through original resolution / assumed caster priority; corrected to actual opponent priority. No runtime changes needed after final9 besides import sorting.
