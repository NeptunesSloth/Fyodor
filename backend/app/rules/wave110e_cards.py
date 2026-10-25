"""-- wave 110E -- exact Oracle wordings of single cards, built from a wording the grammar reads plus native effects.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

Def = dict[str, Any]

# 701.29a: fateseal N = look at the top N cards of an opponent's library (chosen, not targeted), any number to the bottom, the rest back on top
# in any order. Only the looking player sees them (look_top reveal false).
_FATESEAL2: list[Def] = [{"do": "choose_value", "who": "you", "what": "opponent", "as": "fs110e"},
              {"do": "look_top", "n": 2, "player": "ref:fs110e", "reveal": False},
              {"do": "pick_looked", "n": 2, "optional": True, "to": "bottom_any", "reveal": False},
              {"do": "rest_looked", "to": "top_any"}]

# whole ability text -> (the wording the grammar reads for the first part, the effects appended)
_APPEND: dict[str, tuple[str, list[Def]]] = {
    "Put target creature on top of its owner's library, then fateseal 2.":
        ("Put target creature on top of its owner's library.", _FATESEAL2),
}

# whole ability text -> (the wording the grammar reads for the targets, the effects that replace the parsed ones; "target:0" = the first target group)
_SWAP: dict[str, tuple[str, list[Def]]] = {
    # 509.1h/509.3c: each target becomes blocked (no-op for one no longer an unblocked attacker); then 120.3 damage to each of them
    "X target attacking creatures become blocked. Choking Vines deals 1 damage to each of those creatures.":
        ("X target attacking creatures gain flying until end of turn.",
         [{"do": "become_blocked", "who": "target:0"}, {"do": "damage", "who": "target:0", "n": 1}]),
    "Target creature gets -2/-2 until end of turn. It gets an additional -1/-1 until end of turn for each modified creature you controlled as you cast this spell.":
        ("Target creature gets -2/-2 until end of turn.",
         [{"do": "modified_cast110e", "as": "mod110e"}, {"do": "pump", "who": "target", "p": -2, "t": -2},
          {"do": "pump", "who": "target", "p": {"neg": {"ref_amount": "mod110e"}}, "t": {"neg": {"ref_amount": "mod110e"}}}]),
}


# Beastie Beatdown: line 1 names both targets (115.1), the other lines are read as part of it (all effects run in line order, 608.2c).
_BEATDOWN = "Choose target creature you control and target creature an opponent controls."
_BEATDOWN_REST = ("Delirium — If there are four or more card types among cards in your graveyard, put two +1/+1 counters on the creature you control.",
                  "The creature you control deals damage equal to its power to the creature an opponent controls.")


def bind_targets(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """601.2c/115.9b: the creatures the cast spell targets (still on the battlefield), as one named group for "those creatures"."""
    from app.rules import context, token_copy_sources

    refs = token_copy_sources.spell_targets(plan, ctx, e["selector"])
    context.refs(ctx)[e["as"]] = {"kind": "objects", "objects": [r.model_dump(mode="json") for r in refs]}
    return True


def bind_modified(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """601.2i: the number of modified creatures (700.9) its controller had as the spell was cast, kept as a count for later amounts."""
    record = plan.rules.payments.get(ctx.get("source_object") or "")
    ctx.setdefault("refs", {})[e["as"]] = {"kind": "amount", "n": record.cast_modified_n110e if record else 0}
    return True


PRIMITIVES = {"spell_targets110e": bind_targets, "modified_cast110e": bind_modified}

_FLYERS = "Creatures with flying can't attack you or block creatures you control."
_BLAZE = ("Target creature defending player controls can block any number of creatures this turn. "
          "It blocks each attacking creature this turn if able.")
_STORM = "Whenever you cast a spell that targets one or more creatures, those creatures gain flying until end of turn."


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    text = ability.text.strip()
    if ability.text.strip() == _STORM:
        native = scripts.define(replace(ability, text="Whenever you cast a spell that targets one or more creatures, draw a card."), ch)
        if native is None:
            return None
        return {**native, "effects": [{"do": "spell_targets110e", "selector": native["cond"]["targets"], "as": "st110e"},
                                      {"do": "grant", "who": "ref:st110e", "keywords": ["flying"]}]}
    if ability.text.strip() == _FLYERS:  # 508.1c, 509.1b: both rules on the same group, as the two sentences read apart
        a, b = (scripts.define(replace(ability, text=t), ch) for t in ("Creatures with flying can't attack you.",
                                                                       "Creatures with flying can't block creatures you control."))
        return None if a is None or b is None or a["who"] != b["who"] else {**a, "rules": [*a["rules"], *b["rules"]]}
    if ability.text.strip() == _BLAZE:  # 509.1c: the creature it names is the target of the first sentence
        native = scripts.define(replace(ability, text=_BLAZE.split(". It ")[0] + "."), ch)
        return None if native is None else {**native, "effects": [*native["effects"],
                                                                  {"do": "restrict", "who": "target", "rules": ["must_block_all110e"]}]}
    if text == _BEATDOWN:
        deal = scripts.define(replace(ability, text="Target creature you control deals damage equal to its power to target creature an opponent controls."), ch)
        grow = scripts.define(replace(ability, text=_BEATDOWN_REST[0].split(" — ")[1].replace("the creature you control", "target creature you control")), ch)
        if deal is None or grow is None:
            return None
        counters = [{**e, "who": "target:0"} if e.get("who") == "target" else e for e in grow["effects"]]
        return {**deal, "effects": [*counters, *deal["effects"]]}
    if text in _BEATDOWN_REST:
        return {"kind": "spell", "effects": []}
    swap = _SWAP.get(ability.text.strip())
    if swap is not None:
        native = scripts.define(replace(ability, text=swap[0]), ch)
        return None if native is None else {**native, "effects": swap[1]}
    got = _APPEND.get(ability.text.strip())
    if got is None:
        return None
    native = scripts.define(replace(ability, text=got[0]), ch)
    return None if native is None else {**native, "effects": [*native["effects"], *got[1]]}
