# Blocking without an attacker

CR506.4b keeps a blocking creature blocking when all creatures it blocked have been removed from combat. A creature's blocking status and its current attacker relationships are separate facts.

`CardInstance.blocking_without_attacker` defaults to false for older saves. `is_blocking` includes either real blocking relationships or this marker. Removing a specific attacker preserves blocking status; explicitly removing the blocker from combat clears all three fields. Zone changes, control changes, phasing, loss of creature status and combat cleanup use that explicit clearing path.

Selectors, conditions, activation restrictions, prevention scopes and LKI read status through `is_blocking`. Combat damage assignment and arrows continue to use actual relationships, so the marker cannot assign damage to an absent creature or a player. LKI stores blocking status independently of the list of blocked attackers and reconstructs it without inventing a placeholder attacker ID.

The regression uses actual Electryte combat: a Bear dies to its Dreadmaw blocker while Electryte deals combat damage to the defending player. Dreadmaw remains blocking and receives Electryte's triggered damage. The native pending trigger survives a save and a fresh-process resume. Public card views show blocking status without an attacker arrow; end of combat clears it.
