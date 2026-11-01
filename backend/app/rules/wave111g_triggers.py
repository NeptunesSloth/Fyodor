"""Wave 111G: Star Trek trigger one-offs, read as whole abilities (``scripts.define`` hook). Researched against the CR of 2026-09-25.

* Tuvok, Chief Tactical Officer: "When ~ enters during the declare attackers step, choose up to two target attacking creatures. For each of them,
  you may reselect which player or permanent that creature is attacking." Portal Mage's machinery (attacker_reselection73) with up to two targets
  (115.1, 601.2c: zero, one or two attacking creatures, any controller's), each still attacking as the trigger resolves asked in turn (608.2b). 508.7:
  the creature isn't removed from combat and didn't attack again (508.7a); the new choice ignores attack requirements and restrictions (508.7b) and
  must be an opponent of that creature's controller or a planeswalker or battle of one (508.7c; Commander plays with attack multiple players, 802).
* U.S.S. Defiant, Mirror Migrant: "When ~ enters, it and up to one target creature you control phase out." Both phase out at once (702.26a, one
  phasing event); "it" is the Spacecraft only while it is still that object on the battlefield (400.7).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TUVOK = ("When ~ enters during the declare attackers step, choose up to two target attacking creatures. For each of them, you may reselect which "
         "player or permanent that creature is attacking.")
DEFIANT = "When ~ enters, it and up to one target creature you control phase out."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.kind != "triggered" or not ability.text.startswith("When "):
        return None
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == TUVOK:
        from app.rules import attacker_reselection73

        base = attacker_reselection73.definition(
            replace(ability, text=f"When this creature enters during the declare attackers step, {attacker_reselection73.SINGLE}"), ch)
        if base is None or base.get("effects") != [{"do": "attacker_reselect73", "mode": "single"}]:
            return None
        from app.rules import selectors

        attacking = selectors.Selector(types=("Creature",), attacking=True).key()
        return {**base, "target": None, "targets": [{"what": attacking, "min": 0, "max": 2}]}
    if text == DEFIANT:
        base = scripts.define(replace(ability, text="When this artifact enters, up to one target creature you control phases out."), ch)
        if base is None or base.get("effects") != [{"do": "phase_out", "who": "target:0"}]:
            return None
        return {**base, "effects": [{"do": "phase_out", "who": "union:self+target:0"}]}
    return None
