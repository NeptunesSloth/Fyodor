# Nalfeshnee

Canonical printing: Scryfall `b7717617-706a-4338-a207-dd8c08feb1c3`.

The exile-cast trigger copies any spell. Only a permanent-spell copy gains haste and the quoted beginning-of-end-step sacrifice ability. Those granted abilities are not copiable values: a subsequent Clone does not inherit them. Copying a permanent spell produces a token through the native spell-resolution path; this is not token creation for Parallel Lives. Twinning Staff does increase the number of spell copies, and every resulting permanent copy receives the abilities.

The generic copying parser accepts the conditional permanent-spell grant following an otherwise supported spell-copy instruction. Serializable copy jobs retain unconditional and permanent-only grants separately. Each new copy is classified using its actual copied characteristics, including a departed original's last-known chosen face, before the layer-six grants are applied. Existing spell-to-permanent effect continuity carries the grants across resolution.

Copy prohibition checks in the stack-object copying path now use the original object identifier and last-known stack characteristics. Countering an uncopyable spell before Nalfeshnee's trigger resolves does not remove its prohibition. Copying a card outside the stack still observes the distinct meaning of “this spell.”

`tests/test_rules_nalfeshnee.py` contains 14 canonical gameplay/save/replay checks: actual Reckless Impulse exile permission; permanent and instant copies; optional retargeting; hand casts and land plays; Twinning Staff and Parallel Lives; countered original spells; last-known copy prohibition; source departure and control change; opponent casts; noninheritance through Clone; and a countered modal double-faced sorcery whose physical card has reset to its permanent front face.

Validation: all 14 cases plus 53 Choreographed Sparks, Display of Power, and spell-copy-replacement regressions passed together (67 tests). Log: `/tmp/fyodor-nalfeshnee-combined.log`.
