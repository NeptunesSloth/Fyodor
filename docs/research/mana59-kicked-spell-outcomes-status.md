# Kicked spell outcomes (mana59)

Vines of Vastwood, Urza’s Rage, Scorching Lava and Molten Disaster now execute their kicked and unkicked effects through native operators and actual stack kicker state. Vines freezes targeting protection relative to the spell’s controller, so protecting an opponent’s creature stops that opponent targeting it while its caster may still do so. Its kicked pump is separate from the protection. Urza’s Rage deals three preventable damage or ten unpreventable damage. Scorching Lava’s kicked regeneration and death replacement apply even when all its initial damage is prevented.

A kicked Molten Disaster receives the actual split second keyword while on the stack. It uses the ordinary restrictions on casting and nonmana activation, permits mana abilities, and keeps its announced X, kicker status and split second when copied by native Doublecast. Its existing native damage operation simultaneously affects ground creatures and all players while leaving flying creatures unharmed. Its stack static is explicitly excluded from resolution instructions.

Production17 cases pass, including four genuine fresh-process scenarios, both kicker states, opponent-creature targeting protection, prevention distinctions, source-relative death replacements, native stack restrictions, mana activation and copied kicked X spells. Fifteen directly affected kicker/copy/stack-keyword regressions pass. Scoped three-file types and production Ruff pass. Exact evidence: `/tmp/fyodor-mana59-production-admission-manifest.json`.

Seven reserved kicker gaps remain queued: Thieving Skydiver, The Eagles Are Coming!, Inscription of Insight, Waste Management, Wicker Picker, Agonizing Demise and Monstrous War-Leech.
