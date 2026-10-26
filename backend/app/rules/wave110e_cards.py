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
    # 701.31a: a player may planeswalk only during a Planechase game (never in Commander), so "you may planeswalk" does nothing
    "Surveil 2, then draw a card. You may planeswalk.": ("Surveil 2, then draw a card.", []),
}

_REWRITE: dict[str, str] = {
    # 700.9: the sacrificed creature is read as it last existed (608.2h); the cost is plain "sacrifice a creature" (costs._THROWDOWN_COST)
    "Destroy target creature or planeswalker. If the modified creature was sacrificed, draw a card.":
        "Destroy target creature or planeswalker. If a modified creature was sacrificed this way, draw a card.",
    # 701.39a goad, 701.21? tap: both act on the creatures each opponent chose (608.2c)
    "Each opponent chooses a creature they control. Tap and goad the chosen creatures.":
        "Each opponent chooses a creature they control. Tap those creatures. Goad those creatures.",
}
_EMBIGGEN = ("Embiggen Fist — Whenever you cast a spell that targets a creature you control, draw a card. "
             "Until end of turn, Ms. Marvel gains \"Ms. Marvel's base power is equal to the number of cards in your hand.\"")
_RADIATE = ("Choose target instant or sorcery spell that targets only a single permanent or player. Copy that spell for each other permanent or player "
            "the spell could target. Each copy targets a different one of those permanents and players.")
_STORYWEAVE = ("Put two lore counters on target Saga you control. The next time one or more enchantment creatures you control enter this turn, "
               "each enters with two additional +1/+1 counters on it.")
_CULPRIT = "Exile any number of face-up creatures you control with disguise in a face-down pile, shuffle that pile, then cloak them."
_AMBUSH = ("Target player searches their library and/or graveyard for a card named Ezio, Blade of Vengeance, reveals it, and puts it into their hand. "
           "If they search their library this way, they shuffle.")
_SWAP_BODY = "You may exchange this permanent with an Aura card in your hand."
_REFLECT_ETB = "When this Aura enters attached to a creature, each other nontoken creature you control becomes a copy of that creature."
_REFLECT_STATIC = "Nontoken creatures you control enter as a copy of enchanted creature."
COPY_ENTRY_HOST = "copy_entry_host110e"
_BOLAS = 'sel:{"controller":"you","subtypes":["Bolas"],"types":["Planeswalker"]}'
# whole ability text -> (the wording the grammar reads for the targets, the effects that replace the parsed ones; "target:0" = the first target group)
_SWAP: dict[str, tuple[str, list[Def]]] = {
    # 702.16j + 119.7/119.8 + 702.26: the target opponent gets the shield and life lock until their next turn, their nonland permanents phase out
    "Choose target opponent. Until that player's next turn, they gain protection from everything and their life total can't change. All nonland permanents they control phase out.":
        ("Target opponent loses 1 life. Nonland permanents that player controls phase out.",
         [{"do": "life_lock", "who": "target", "until": "next_turn"},
          {"do": "player_shield", "who": "target", "shield": "protection", "quality": "everything", "until": "next_turn"},
          {"do": "phase_out", "who": 'controlled:target|sel:{"not_types":["Land"]}'}]),
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
    # 608.2c in order: each chosen creature's controller decides whether the caster draws instead (the choice is theirs, so it is asked of them)
    "For each opponent, choose up to one target creature that player controls, then return that creature to its owner's hand unless its controller has you draw a card.":
        ("For each opponent, choose up to one target creature that player controls.",
         [{"do": "choose_targets", "who": "target:0"}, {"do": "decoy110e", "who": "target:0"}]),  # (each copied per opponent group: per_opponent.expanded)
    # 205.1a/613.1d: they become Food artifacts and lose their other card types and subtypes, for as long as they are those permanents (400.7)
    "Put onto the battlefield under your control all creature cards in your opponents' graveyards that were put there from the battlefield this turn. They are Food "
    "artifacts with \"{2}, {T}, Sacrifice this artifact: You gain 3 life.\"":
        ("Put all creature cards in your opponents' graveyards that were put there from the battlefield this turn onto the battlefield under your control.",
         [{"do": "return_card", "to": "battlefield", "tapped": False, "under": "you", "as": "sp110e",
           "who": 'sel:{"card":true,"extras":["put_there:battlefield"],"types":["Creature"],"zone_owner":"opponent","zones":["graveyard"]}'},
          {"do": "become", "who": "ref:sp110e", "types": ["Artifact"], "artifact_types": ["Food"], "duration": "permanent",
           "abilities": ["{2}, {T}, Sacrifice this artifact: You gain 3 life."]}]),
    # 608.2c: with a Bolas planeswalker all the cards return; otherwise an opponent (chosen by you) picks two to leave (bound_subset_choices "deliver")
    "Choose up to four target cards in your graveyard. If you control a Bolas planeswalker, return those cards to your hand. Otherwise, an opponent chooses two of them. "
    "Leave the chosen cards in your graveyard and put the rest into your hand.":
        ("Choose up to four target cards in your graveyard. Return those cards to your hand.",
         [{"do": "choose_targets", "who": "target:0"},
          {"do": "only_if", "cond": {"value": {"count": _BOLAS}, "op": ">=", "n": 1}, "skip": 1}, {"do": "bounce", "who": "target:0"},
          {"do": "only_if", "cond": {"value": {"count": _BOLAS}, "op": "<=", "n": 0}, "skip": 2},
          {"do": "bound_subset", "mode": "prepare", "action": "deliver", "who": "target:0"}, {"do": "bound_subset", "mode": "partition", "action": "deliver"}]),
    # 701.24/701.23: the count is bound as the cards leave the hand (608.2c); the opponent orders them (401.4, irrelevant: the library is searched whole and shuffled)
    "Target opponent puts the cards from their hand on top of their library. Search that player's library for that many cards. The player puts those cards into "
    "their hand, then shuffles.":
        ("Target opponent puts a card from their hand on top of their library.",
         [{"do": "head_games110e", "who": "target", "as": "hg110e"},
          {"do": "search", "who": "you", "label": "cards", "max": {"ref_amount": "hg110e"}, "to": "hand", "reveal": False, "upto": False,
           "sel": 'sel:{"card":true,"zone_owner":"you","zones":["library"]}', "shuffle": False, "library": "target"},
          {"do": "shuffle_library", "who": "target", "zones": []}]),
    # 608.2c in order: the fight, then the player to the left (the one whose creature was targeted) is asked and, if yes, copies the spell and may choose new targets (707.10)
    "Target creature you control fights target creature the opponent to your left controls. Then that player may copy this spell and may choose new targets for the copy.":
        ("Target creature you control fights target creature the opponent to your left controls.",
         [{"do": "fight", "who": "target:0", "with": "target:1"}, {"do": "optional_payment", "who": "left110e", "ask": "copy this spell", "cost": "", "bind": "bb110e"},
          {"do": "only_if", "cond": {"succeeded": "bb110e"}, "skip": 2},
          {"do": "copy_spell", "who": "this_spell", "by": "left110e"}, {"do": "copy_new_targets", "optional": True}]),
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


def head_games(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Head Games, step 1: the target player's whole hand goes on top of their library (they order it); how many cards that was is kept for the search."""
    from app.rules import context, effects, put_back

    pid = effects._players(plan, ctx, e["who"])[0]
    hand = list(plan.state.zones.get(f"{pid}:hand", []))
    context.bind_amount(ctx, e["as"], len(hand))
    return put_back._move(plan, ctx, pid, hand)


def decoy(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Decoy Gambit (its group's copy): for the chosen creature (still on the battlefield), its controller either has the caster draw a card or the creature is returned."""
    from app.rules import effects

    steps: list[dict[str, Any]] = []
    for i, cid in enumerate(effects._cards(plan, ctx, e["who"])):
        c = plan.state.cards[cid]
        if c.zone.endswith(":battlefield"):
            steps += [{"do": "optional_payment", "who": f"player:{c.controller}", "ask": "have the caster draw a card (otherwise the creature returns to its owner's hand)",
                       "cost": "", "bind": f"dg{i}"},
                      {"do": "only_if", "cond": {"succeeded": f"dg{i}"}, "skip": 1},
                      {"do": "draw", "who": "you", "n": 1}, {"do": "only_if", "cond": {"succeeded": f"dg{i}", "negate": True}, "skip": 1},
                      {"do": "bounce", "who": f"object:{plan.oid(c)}"}]
    at = ctx["next"]  # (a new list: the spell's own effects are copied with it, 707.10)
    ctx["effects"] = [*ctx["effects"][:at], *steps, *ctx["effects"][at:]]
    return True


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
    at = ctx["next"]  # (a new list: the spell's own effects are copied with it, 707.10)
    ctx["effects"] = [*ctx["effects"][:at], *block, *ctx["effects"][at:]]
    return True


def aura_swap_gate(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """702.65b: if either half can't be completed the ability does nothing: with the Aura gone, no Aura is put onto the battlefield."""
    from app.rules import effects

    if not effects._cards(plan, ctx, "self"):
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
    return True


def aura_swap_return(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """702.65a: the Aura from the hand came onto the battlefield (303.4g: one with nothing to enchant stays in the hand), so this one goes to its owner's hand."""
    from app.rules import effects

    if any(plan.state.cards[c].zone.endswith(":battlefield") for c in effects._cards(plan, ctx, e["of"])):
        effects.bounce(plan, ctx, {"who": "self"})
    return True


PRIMITIVES = {"aura_swap_gate110e": aura_swap_gate, "aura_swap_return110e": aura_swap_return, "mirror_match110e": mirror_match, "decoy110e": decoy, "head_games110e": head_games, "spell_targets110e": bind_targets, "modified_cast110e": bind_modified, "enter_tapped110e": enter_tapped_turn}

_FLYERS = "Creatures with flying can't attack you or block creatures you control."
_BLAZE = ("Target creature defending player controls can block any number of creatures this turn. "
          "It blocks each attacking creature this turn if able.")
_STORM = "Whenever you cast a spell that targets one or more creatures, those creatures gain flying until end of turn."


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    text = ability.text.strip()
    if text == _EMBIGGEN:  # 613.4b: until end of turn Ms. Marvel's base power is the number of cards in your hand, counted continuously (611.3a)
        native = scripts.define(replace(ability, text=_EMBIGGEN.split(", draw a card.")[0] + ", draw a card."), ch)
        return None if native is None else {**native, "effects": [*native["effects"], {"do": "dyn_base_power110e", "who": "self", "value": {"hand": "you"}}]}
    from app.rules import wave110e_imps

    if (imp := wave110e_imps.definition(ability, ch)) is not None:  # Nettling Imp, Norritt
        return imp
    from app.rules import wave110e_pets

    if (pets := wave110e_pets.definition(ability, ch)) is not None:  # Exotic Pets
        return pets
    if text == "Creatures can't attack a player unless that player cast a spell or put a nontoken permanent onto the battlefield during their last turn.":  # 508.1c, combat._defender_fact
        native = scripts.define(replace(ability, text="Creatures can't attack."), ch)
        return None if native is None or native.get("rules") != ["cant_attack"] else {**native, "rules": ["cant_attack_unless_def:acted110e"]}
    if text == "Creatures played by your opponents enter tapped.":  # 305.1/601.2: "played" creature = cast, so only a spell entering from the stack (others_enter_tapped)
        native = scripts.define(replace(ability, text="Creatures your opponents control enter tapped."), ch)
        return None if native is None else {**native, "cast110e": True}
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
    if (alt := _REWRITE.get(text)) is not None:  # an exact Oracle sentence read as the wording the grammar already knows (pattern: multi100n)
        return scripts.define(replace(ability, text=alt), ch)
    if text == _REFLECT_ETB:  # 707.9 / 707.2: the other nontoken creatures become copies of the enchanted creature, fixed as the trigger resolves (611.2c)
        native = scripts.define(replace(ability, text="When this Aura enters, draw a card."), ch)
        sel = '{"controller":"you","token":false,"types":["Creature"]}'
        return None if native is None else {**native, "effects": [{"do": "become_copy", "who": "sel:" + sel, "with": "host", "others": True}]}
    if text == _REFLECT_STATIC:  # read at entry (copy_on_entry_host)
        return {"kind": "static", "static": COPY_ENTRY_HOST, "effects": []}
    swap = _SWAP.get(ability.text.strip())
    if swap is not None:
        native = scripts.define(replace(ability, text=swap[0]), ch)
        return None if native is None else {**native, "effects": swap[1]}
    got = _APPEND.get(ability.text.strip())
    if got is None:
        return None
    native = scripts.define(replace(ability, text=got[0]), ch)
    return None if native is None else {**native, "effects": [*native["effects"], *got[1]]}


def dyn_base_power(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, layers

    for cid in effects._cards(plan, ctx, e["who"]):
        layers.add_effect(plan, affected=[plan.oid(cid)], layer="7b", source=ctx.get("source_object"), controller=ctx["controller"], dyn_power110e=e["value"])
    return True


PRIMITIVES["dyn_base_power110e"] = dyn_base_power


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """Exact wordings read as spell effects (scripts.parse_effects hook)."""
    if body.strip() == _CULPRIT:  # 701.58: the creatures are chosen as it resolves (608.2d, not targeted), then exiled face down, shuffled, cloaked (facedown.manifest_pile)
        sel = '{"controller":"you","extras":["face_up"],"types":["Creature"],"with_keywords":["disguise"]}'
        return [{"do": "player_chooses", "who": "you", "sel": "sel:" + sel, "n": 1, "label": "creature", "any": True, "upto": True, "optional": True, "as": "cul110e"},
                {"do": "manifest_pile", "kind": "cloak", "tapped": False, "who": "ref:cul110e"}], None, False
    if body.strip() == _AMBUSH:  # 701.23: the targeted player is the searcher (effects.search: who), the same search "you" would make
        from app.rules import scripts

        own = scripts.parse_effects(_AMBUSH.replace("Target player searches their", "Search your").replace("reveals it, and puts it into their hand", "reveal it, and put it into your hand")
                                    .replace("If they search their library this way, they shuffle", "If you search your library this way, shuffle"))
        return None if own is None or len(own[0]) != 1 or own[0][0].get("do") != "search" else ([{**own[0][0], "who": "target"}], "player", False)
    if body.strip() in (_SWAP_BODY, _SWAP_BODY.replace("this permanent", "~")):  # 702.65a: put the Aura card onto the battlefield (it chooses what it enchants, 303.4f), then this one returns to hand
        from app.rules import scripts

        put = scripts.parse_effects("You may put an Aura card from your hand onto the battlefield.")
        if put is None or put[0][0].get("do") != "put_from_hand":
            return None
        return [{"do": "aura_swap_gate110e", "skip": 2}, {**put[0][0], "optional": True, "as": "sw110e"}, {"do": "aura_swap_return110e", "of": "ref:sw110e"}], None, False
    if body.strip() == _RADIATE:  # 707.10d: the copies; the target spell's own restriction is read by selectors (targets_only)
        from app.rules import scripts

        first = scripts.parse_effects("Copy target instant or sorcery spell that targets only a single permanent or player.")
        return None if first is None or first[0][0].get("do") != "copy_spell" else ([{"do": "radiate110e"}], first[1], first[2])
    if body.strip() == _STORYWEAVE:  # 614.1c: the lore counters natively, then a one-shot entry rider
        from app.rules import scripts

        first = scripts.parse_effects(_STORYWEAVE.split(" The next")[0])
        sel = '{"controller":"you","extras":["all_types"],"types":["Creature","Enchantment"]}'
        return None if first is None else ([*first[0], {"do": "next_entry_counters110e", "sel": "sel:" + sel, "kind": "+1/+1", "n": 2}], first[1], first[2])
    return None


def copy_on_entry_host(plan: Any, card: Any, controller: str) -> None:
    """614.1c, 707.9: a nontoken creature entering under the controller of an Aura with the static enters as a copy of the creature it enchants (its copiable
    values, 707.2), no choice (ponytail: like Essence of the Wild, several such statics are not ordered against other copy replacements, 616.1)."""
    from app.game.rules_state import CopyEntrySource
    from app.game.state import zone_key
    from app.rules import copying, permissions

    probe = card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller})
    if card.is_token or copying.entering_as_copy(plan, card) or not plan.ch(probe).is_creature:
        return
    for aura, _, _ in permissions._table_statics(plan.state, plan.info, {COPY_ENTRY_HOST}):
        host = plan.state.cards.get(aura.attached_to or "")
        if aura.controller == controller and host is not None and host.id != card.id and host.zone.endswith(":battlefield") and plan.ch(host).is_creature:
            copying.add_copy_effect(plan, [plan.oid(card)], copying.recipe_of(plan, host), controller, source=copying.ENTERING + card.id,
                                    entry_source=CopyEntrySource(card=host.id, object_id=plan.oid(host), controller=host.controller))
            return
