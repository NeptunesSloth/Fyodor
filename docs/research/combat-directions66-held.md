# Directional combat restrictions — held prototype

Candidates: Pramikon, Sky Rampart; Mystic Barrier; Teyo, Geometric Tactician. Complete canonical records and official rulings are retained in `/tmp/combat66-static-canonicals.json` and `/tmp/combat66-static-rulings.json`.

The unregistered prototype `proposals/combat66-directions-prototype.py` and uncollected test draft `proposals/combat66-direction-tests.py` composes native direction choice options, declaration-only restrictions, live seating order, planeswalker ownership, and a frozen temporary Teyo direction. Its isolated shared-hook proposal is `/tmp/combat66-directions-kernel-proposal.patch`. No production hooks or admissions are authorized by this document.

A current direction stored only in the permanent's public choices is insufficient. Mirage Mirror may copy Mystic Barrier, make an upkeep choice, then copy Pramikon without performing an entry choice. The old choice must not be reused. If one copy effect later expires, any original linked choice must be restored rather than overwritten by the newer copy's choice.

The proper follow-up requires a typed receipt per original source ObjectRef, linked ability family/borrowed scope, and copy acquisition. Multiple acquisition receipts must survive while the original object survives. Capture the acquisition when a Mystic trigger is created, not when its choice resolves. Entry choices capture the actual incoming acquisition; choices cannot migrate to successor objects. Existing `chosen_color_pairs45.acquisition` and its trigger freeze/entry hooks illustrate native integration boundaries, but its unrelated receipt state must not be reused.

The initial isolated prototype passed ten canonical/native checks and exposed an expiration metadata omission in its Teyo effect. That omission was repaired in the unregistered prototype by supplying native `until_player` and `turn` when creating the continuous effect. No final proof or completion claim is made. Native acquisition transition and cold cases must pass before the permanent-choice candidates can be admitted.

The smaller Animate Wall/Warmonger's Chariot grammar sibling is being verified independently over existing native `attack_despite_defender`, without new direction kernel behavior.
