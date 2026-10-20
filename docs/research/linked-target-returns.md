# Targeted returns from linked exile

The Darkness Crystal's last ability targets a creature card in the exile set belonging to the particular Crystal object that exiled it. Its [official rulings](https://api.scryfall.com/cards/0f93b6ac-54ce-45d0-8549-19307406e6e5/rulings) confirm that its replacement exiles nontoken opposing creatures instead of their dying. The replacement and return abilities are linked under CR 607.2b.

The ability keeps using its original source object after activation. Destroying or blinking the Crystal in response does not change that ability's exile set (CR 113.7a). The returned Crystal is a new object with a separate exile set (CR 400.7). A copied activation keeps the original activation's source and linked set when new targets are chosen (CR 707.10).

The target must remain the same card object in exile through resolution (CR 608.2b). Pull from Eternity followed by Cremate puts the same physical card back into exile as a new rules object; that new object is not the activation's target or the original linked exile object.

The returned creature enters tapped under the ability controller's control, with two additional +1/+1 counters. Those counters combine with native entry counters and pass through the normal entry-replacement pipeline (CR 122.6, 614.12). An entering Corpsejack Menace cannot apply its own general counter replacement to itself as it enters; an already-present Vorinclex or Hardened Scales can modify the entry counters.

Implementation must pass the StackEntry's saved source object ID to target legality and copy retargeting. Looking up only the source's physical card ID would silently switch to a blinked Crystal's new exile set.
