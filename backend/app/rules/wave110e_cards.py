"""-- wave 110E -- exact Oracle wordings of single cards, built from a wording the grammar reads plus native effects.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

import re
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
    "For each creature attacking you or a planeswalker you control, create a token that's a copy of that creature and that's blocking that creature. Exile those tokens at end of combat.":
        ("Draw a card.", [{"do": "mirror_match110e"}]),
    # 509.4, 509.1h/509.3c: the token enters blocking the attacker (an unblocked one becomes blocked by it; combat_rules.enter_blocking, block_events.become_blocked)
    "Create a 1/1 green Saproling creature token that's blocking target creature attacking you.":
        ("Tap target creature attacking you.",
         [{"do": "create_token", "who": "you", "n": 1, "as": "blk110e",
           "token": {"name": "Saproling", "power": "1", "toughness": "1", "colors": ["G"], "type_line": "Token Creature — Saproling", "text": ""}},
          {"do": "become_blocked", "who": "target"}, {"do": "enter_blocking", "who": "ref:blk110e", "blocked": "target"}]),
    # 205.1b: "becomes a Coward in addition to its other types" (the card's own name is read as ~ in the grammar, so the type is added here)
    "Target creature can't block this turn and becomes a Coward in addition to its other types until end of turn.":
        ("Target creature can't block this turn.",
         [{"do": "restrict", "who": "target", "rules": ["cant_block"]},
          {"do": "become", "who": "target", "types": [], "retain": True, "add_creature_types": ["Coward"], "duration": "end_of_turn"}]),
    "Killer deals 3 damage to target creature and each other creature that shares a creature type with it.":  # 120.3; all of them are dealt damage at once
        ("Killer deals 3 damage to target creature.", [{"do": "damage", "who": "kin110e", "n": 3}]),
    # 608.2h/707.2: the Shapeshifters copy the returned creature as it last existed on the battlefield (the ref keeps its last known information)
    "Return target creature to its owner's hand. You may have Shapeshifters you control become copies of that creature until end of turn.":
        ("Return target creature to its owner's hand.",
         [{"do": "bounce", "who": "target", "as": "abs110e"},
          {"do": "may_rest"},
          {"do": "become_copy", "who": 'sel:{"controller":"you","subtypes":["Shapeshifter"]}', "with": "ref:abs110e", "last_known": True,
           "duration": "end_of_turn"}]),
    "Permanents enter tapped this turn.": ("Draw a card.", [{"do": "enter_tapped110e"}]),
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


_CORRUPTED_FB = "Corrupted — As long as an opponent has three or more poison counters and this card is in your graveyard, it has flashback {2}{G}."
_CLOSE_LINE2 = "Close Encounter deals damage equal to the power of the chosen creature or card to target creature."
_RETURNS = ("Each player shuffles their hand and graveyard into their library. You exile the top ten cards of your library. "
            "Then each player draws up to seven cards.")
_THUNDERCLAP = ("Target creature you control deals damage equal to its power to another target creature. "
                "If this spell's additional cost was paid, destroy target noncreature artifact or noncreature enchantment.")
_SURGE = "Voltage Surge deals 2 damage to target creature or planeswalker. If this spell's additional cost was paid, Voltage Surge deals 4 damage instead."


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


def enter_tapped_turn(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """614.1d, 611.2c: "Permanents enter tapped this turn." = a replacement record for every permanent entering (read by others_enter_tapped)."""
    from app.rules import replace, selectors

    replace.add_record(plan, event="enters_tapped", match={"selector": selectors.Selector().key()}, op={"do": "tap"},
                       controller=ctx["controller"], source=ctx.get("source_object"), source_card=ctx.get("source_card"),
                       label=ctx.get("name") or "Enter tapped")
    return True


_WILD = ("Choose one. Until end of turn, target creature you control has that base power and toughness, becomes that creature type, "
         "and gains that ability.")
_WILD_MODE = re.compile(r"^• (\d+/\d+) ([A-Z][a-z]+) with ([a-z]+)\.$")


def modal_lines(lines: list[Any]) -> list[Any]:
    """Wild Shape: the shared sentence after "Choose one." is read as part of every bullet (700.2: each mode is its own instruction)."""
    if not lines or lines[0].text != _WILD or not all(_WILD_MODE.match(x.text) for x in lines[1:]):
        return lines
    return [replace(lines[0], text="Choose one —"), *(replace(x, text=f"• Until end of turn, target creature you control becomes a "
                                                           f"{m[1]} {m[2]} and gains {m[3]}.") for x in lines[1:] if (m := _WILD_MODE.match(x.text)))]


def mirror_match(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Mirror Match: for each creature attacking the caster or a planeswalker they control (as the spell resolves), a token copy of it that enters
    blocking it (509.4; an unblocked attacker becomes blocked, 509.3c) and is exiled at end of combat. Expanded into one native block per attacker."""
    import copy

    from app.rules import context, scripts

    me = ctx["controller"]
    attackers = []
    for c in plan.state.cards.values():
        t = c.attacking
        if c.is_attacking and c.zone.endswith(":battlefield") and t is not None and (
                t.id == me or (t.id in plan.state.cards and plan.state.cards[t.id].controller == me)):
            attackers.append(c.id)
    made = scripts.parse_effects("Create a token that's a copy of target creature attacking you. Exile it at end of combat.")
    assert made is not None
    block: list[dict[str, Any]] = []
    for i, cid in enumerate(attackers):
        context.bind_objects(plan, ctx, f"mm{i}", [cid])
        for eff in copy.deepcopy(made[0]):
            eff = {**eff, **({"who": f"ref:mm{i}"} if eff.get("who") == "target" else {}), **({"as": f"mmt{i}"} if eff.get("as") else {})}
            if eff.get("who") == "ref:e0":
                eff["who"] = f"ref:mmt{i}"
            block.append(eff)
            if eff.get("do") == "token_copy":
                block[-1:] = [{"do": "become_blocked", "who": f"ref:mm{i}"}, eff,
                              {"do": "enter_blocking", "who": f"ref:mmt{i}", "blocked": f"ref:mm{i}"}]
    ctx["effects"][ctx["next"]:ctx["next"]] = block
    return True


PRIMITIVES = {"mirror_match110e": mirror_match, "spell_targets110e": bind_targets, "modified_cast110e": bind_modified, "enter_tapped110e": enter_tapped_turn}

_FLYERS = "Creatures with flying can't attack you or block creatures you control."
_BLAZE = ("Target creature defending player controls can block any number of creatures this turn. "
          "It blocks each attacking creature this turn if able.")
_STORM = "Whenever you cast a spell that targets one or more creatures, those creatures gain flying until end of turn."


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    text = ability.text.strip()
    from app.rules import wave110e_imps

    if (imp := wave110e_imps.definition(ability, ch)) is not None:  # Nettling Imp, Norritt
        return imp
    if text == _CORRUPTED_FB:  # 702.34a: the card's own conditional flashback, read by graveyard_grants.flashback_costs while it is in a graveyard
        from app.rules import conditions

        cond = conditions.parse("an opponent has three or more poison counters")
        return None if cond is None else {"kind": "static", "static": "gy_flashback110e", "cond": cond, "cost": "{2}{G}", "effects": []}
    if text == _CLOSE_LINE2:  # 120.3, 608.2h: the power of what was chosen as it was cast, as it is now or last was
        native = scripts.define(replace(ability, text="Close Encounter deals 1 damage to target creature."), ch)
        if native is None or len(native["effects"]) != 1 or native["effects"][0].get("do") != "damage":
            return None
        return {**native, "effects": [{"do": "pick110e", "as": "pk110e"}, {**native["effects"][0], "n": {"sum": "power", "of": "ref:pk110e"}}]}
    if text in ("As an additional cost to cast this spell, choose a creature type.",
                "As an additional cost to cast this spell, choose a creature you control or a warped creature card you own in exile."):  # 601.2b: asked as the spell is cast (wave110e_opp.announce), kept on the permanent
        return {"kind": "spell", "effects": []}
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
    if text == _THUNDERCLAP:  # 601.2b: the optional behold is the "additional cost"; read "if it was kicked" with that cost as the gate
        native = scripts.define(replace(ability, text=text.replace("this spell's additional cost was paid", "it was kicked")), ch)
        if native is None:
            return None
        return {**native, "effects": [{**e, "optional": "behold"} if e["do"] == "kicked_gate" else e for e in native["effects"]],
                "targets": [{**g, "optional": "behold"} if "kicked" in g else g for g in native["targets"]]}  # 601.2c: only a spell that paid it chooses this target
    if text == _SURGE:  # 601.2b: the optional sacrifice is the "additional cost"; read "if it was kicked" with that cost as the gate
        native = scripts.define(replace(ability, text="Voltage Surge deals 2 damage to target creature or planeswalker. If it was kicked, Voltage Surge deals 4 damage instead."), ch)
        if native is None:
            return None
        return {**native, "effects": [{**e, "optional": "sacrifice110e"} if e["do"] == "kicked_gate" else e for e in native["effects"]]}
    if text == _RETURNS:  # 121.2c, 101.4: each player picks 0..7 first (APNAP), then draws; reuses the Indentured Djinn chooser
        native = scripts.define(replace(ability, text=_RETURNS.replace("draws up to", "draws")), ch)
        if native is None or native["effects"][-1]["do"] != "draw":
            return None
        return {**native, "effects": [*native["effects"][:-1], {"do": "trigger_leaf51_djinn_draws", "all": True, "n": 7}]}
    swap = _SWAP.get(ability.text.strip())
    if swap is not None:
        native = scripts.define(replace(ability, text=swap[0]), ch)
        return None if native is None else {**native, "effects": swap[1]}
    got = _APPEND.get(ability.text.strip())
    if got is None:
        return None
    native = scripts.define(replace(ability, text=got[0]), ch)
    return None if native is None else {**native, "effects": [*native["effects"], *got[1]]}
