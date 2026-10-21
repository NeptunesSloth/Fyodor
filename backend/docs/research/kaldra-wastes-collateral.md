# Kaldra and Wastes canonical collateral validation

Batch31 named-literal support correctly automated Walker of the Wastes. Its live boost uses lands currently controlled by the source controller and the actual current name Wastes, not a land subtype, mana production or original printing. Actual Vesuva entry/copy, changing land control, Urborg subtype changes and Turn to Frog ability loss are covered with replay/save verification.

Canonical Shield of Kaldra gameplay exposed a false FULL result: its coordinated three-name list had been read as one literal name. The bounded correction recognizes that exact Oracle list (including self-text-normalized spelling) and creates native OR branches, each containing the Equipment constraint and one fixed card name. Other names containing commas retain exact literal semantics.

Ten actual-card tests cover global grants across three controllers, source control changes/departure, native equip and lethal Lightning Bolt, animated source ability loss, a matching-named Sword turned into a non-Equipment by Song of the Dryads before Shield enters, Walker cases, and fresh-process resolution/view/replay/save compatibility. Canonical fixture metadata is retained. No general ambiguous name-list partitioning is introduced.
