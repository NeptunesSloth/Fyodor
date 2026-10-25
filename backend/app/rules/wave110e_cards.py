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


def bind_targets(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """601.2c/115.9b: the creatures the cast spell targets (still on the battlefield), as one named group for "those creatures"."""
    from app.rules import context, token_copy_sources

    refs = token_copy_sources.spell_targets(plan, ctx, e["selector"])
    context.refs(ctx)[e["as"]] = {"kind": "objects", "objects": [r.model_dump(mode="json") for r in refs]}
    return True


PRIMITIVES = {"spell_targets110e": bind_targets}

_FLYERS = "Creatures with flying can't attack you or block creatures you control."
_BLAZE = ("Target creature defending player controls can block any number of creatures this turn. "
          "It blocks each attacking creature this turn if able.")
_STORM = "Whenever you cast a spell that targets one or more creatures, those creatures gain flying until end of turn."


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

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
    got = _APPEND.get(ability.text.strip())
    if got is None:
        return None
    native = scripts.define(replace(ability, text=got[0]), ch)
    return None if native is None else {**native, "effects": [*native["effects"], *got[1]]}
