"""-- wave 110M -- exact Oracle wordings of single cards, built from parts of wordings the grammar already reads.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]

# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    "When one or more of your opponents are dealt combat damage during your turn, draw two cards. If your library has no cards in it, you win the game. "
    "Fblthp's owner shuffles him into their library.":
        ("When one or more of your opponents are dealt combat damage during your turn, draw two cards. If your library has no cards in it, you win the game. "
         "Fblthp's owner shuffles it into their library.", lambda d: d),
}


class _Reading(threading.local):
    texts: set[str]

    def __init__(self) -> None:
        self.texts = set()


_READING = _Reading()  # the whole-ability texts being read natively right now, per thread
ATK_TAX = "block_tax_atk110m"
_PRESENCE = "Enchanted creature can't be blocked unless defending player pays {3} for each creature they control that's blocking it."


def on_draw(plan: Any, pid: str, drawn: list[str]) -> None:
    """Booby Trap: the chosen player reveals each card they draw (701.20a, as it is drawn); each card with the chosen name makes the trap's ability trigger (603.2)."""
    from app.game.rules_state import TriggerEvent
    from app.rules import card_names, chosen, context, scripts
    from app.rules.triggers import _add

    traps = [(src, i, d) for src in plan.state.cards.values() if src.choices and src.zone.endswith(":battlefield") and plan.in_game(src) and not plan.manual(src)  # (it records its choices: 614.12a)
             for i, d in scripts.definitions(plan.ch(src)).items() if d.get("static") == BOOBY_RULE and chosen.player_of(plan, src.id) == pid]
    if not traps or not drawn:
        return
    plan.do({"type": "reveal", "card_ids": list(drawn)}, actor=pid)
    for cid in drawn:
        card = plan.state.cards[cid]
        plan.note(f"{plan.name(pid)} reveals {card.name or 'a card'}, a card they drew", [cid], actor=pid)
        for src, _, _ in traps:
            if not card_names.matches(plan, src.id, plan.ch(card)):
                continue
            trigger = next(((i, d) for i, d in scripts.definitions(plan.ch(src)).items() if (d.get("cond") or {}).get("hooked110m")), None)
            if trigger is not None:
                ref = context.ref_of(plan, cid)
                _add(plan, controller=src.controller, source_card=src.id, source_object=plan.oid(src), name=src.name, index=trigger[0],
                     definition=trigger[1], event=TriggerEvent(kind="draw", players=[pid], objects=[ref] if ref else []))


def attacker_tax(ch: Any) -> str:
    """Awesome Presence: the mana the defending player pays for each creature that blocks this attacker (509.1d, 509.1f), or "" (the enchanted creature's rule)."""
    return "".join(r.split(":", 1)[1] for r in sorted(ch.imposed) if r.startswith(f"{ATK_TAX}:"))


def block_tax_for(plan: Any, blocks: Any) -> str:
    """The attacker-side block costs of a declaration: one payment for each blocker of an attacker that has one."""
    return "".join(attacker_tax(plan.ch(plan.state.cards[b.attacker_id])) for b in blocks if b.attacker_id in plan.state.cards)


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts, statics

    if ability.kind == "static" and ability.text.strip() == _PRESENCE:
        return statics._definition("attached", "creature", [], rules=[f"{ATK_TAX}:{{3}}"])
    if ability.text.strip() == _TEFERI:
        return _teferi_definition(ability, ch)
    if ability.kind == "static" and ability.text.strip() == _CENTAUR_STATIC:
        return statics._definition("self", None, [], each={"p": 1, "t": 1, "value": {"stored_same110m": 1}})
    if ability.text.strip() == _ADVERSARY:
        return _adversary_definition(ability, ch)
    if ability.text.strip() == _BOOBY_ENTER:  # both choices are made as it enters (614.12a) and stay public on the permanent
        first = scripts.define(replace(ability, text="As this artifact enters, choose an opponent."), ch)
        second = scripts.define(replace(ability, text="As this artifact enters, choose a card name other than a basic land card name."), ch)
        return None if first is None or second is None else {**first, "effects": [*first["effects"], *second["effects"]]}
    if (built := _BUILD.get(ability.text.strip())) is None or ability.text.strip() in _READING.texts:
        return None  # (an entry whose native wording is its own: the grammar reads it plainly, then the change is applied)
    _READING.texts.add(ability.text.strip())
    try:
        native = scripts.define(replace(ability, text=built[0]), ch)
    finally:
        _READING.texts.discard(ability.text.strip())
    return None if native is None else built[1](native)


_RHINO = ("Target creature you control gets +1/+0 until end of turn. It fights target creature an opponent controls. When excess damage is dealt to the creature "
          "an opponent controls this way, destroy up to one target noncreature artifact with mana value 3 or less.")


def _rhino() -> Any:
    """Rhino's Rampage: the fight binds the excess damage the opponent's creature was dealt (120.10); when there was some, the reflexive ability (603.12) picks its target."""
    from app.rules import scripts

    fight = scripts.parse_effects("Target creature you control gets +1/+0 until end of turn. It fights target creature an opponent controls.")
    reflex = scripts.parse_effects("You may sacrifice a creature. When you do, destroy up to one target noncreature artifact with mana value 3 or less.")
    if fight is None or reflex is None:
        return None
    effects = [dict(x) for x in fight[0]]
    index = next(i for i, x in enumerate(effects) if x["do"] == "fight")
    effects[index] = {**effects[index], "bind_excess": "excess110m", "excess_on": effects[index]["with"]}
    ability = next(x for x in reflex[0] if x["do"] == "reflexive")
    return [*effects, {**ability, "cond": {"value": {"ref_amount": "excess110m"}, "op": ">=", "n": 1}}], fight[1], fight[2]


_BRILLIANCE = ("Choose target artifact card in your graveyard. Return it to the battlefield if it's an artifact creature card. Otherwise, return it to the battlefield "
               "and it's a 3/3 Robot artifact creature with flying.")


def _brilliance() -> Any:
    """Brilliance Unleashed, second mode: an artifact creature card just returns; any other artifact card returns as a 3/3 Robot artifact creature with flying too (205.1b, 614.12)."""
    from app.rules import scripts

    found = scripts.parse_effects("Return target artifact card from your graveyard to the battlefield. It's a 3/3 Robot artifact creature with flying in addition to its other types.")
    if found is None or [x["do"] for x in found[0]] != ["return_card", "become"]:
        return None
    back, become = found[0]
    creature = {"object": "ref:e0", "is": 'sel:{"card":true,"types":["Creature"],"zones":[]}', "negate": True}
    return [back, {"do": "only_if", "cond": creature, "skip": 1}, become], found[1], found[2]


_COVER_UP = ("Destroy all creatures. If evidence was collected, exile a card from an opponent's graveyard. Then search its owner's graveyard, hand, and library for any "
             "number of cards with that name and exile them. That player shuffles, then draws a card for each card exiled from their hand this way.")


def _cover_up() -> Any:
    from app.rules import scripts

    found = scripts.parse_effects("Destroy all creatures. If evidence was collected, draw a card.")
    if found is None or found[0][-1]["do"] != "draw":
        return None
    return [*found[0][:-1], {"do": "cover_up110m"}], found[1], found[2]


def cover_up(plan: Any, ctx: Def, e: Def) -> bool:
    """Deadly Cover-Up: its controller exiles a card from an opponent's graveyard (a public zone, chosen as it resolves), then searches that card's owner's graveyard,
    hand, and library for cards with that name (name_search; 201.2, 701.23); the owner shuffles and draws for the cards exiled from their hand."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    me = ctx["controller"]
    pool = [c.id for c in plan.state.cards.values() if c.zone.endswith(":graveyard") and c.owner != me and c.owner in plan.live()]
    if not pool:
        return True
    if len(pool) > 1:
        decide(plan, player=me, kind="choose_cards", prompt=f"{ctx.get('name', '')}: exile a card from an opponent's graveyard",
               options=[DecisionOption(id=c, label=f"{plan.state.cards[c].name} ({plan.name(plan.state.cards[c].owner)})", card_id=c) for c in pool],
               resume={"step": "cover_up110m", "ctx": ctx})
        return False
    return _cover_up_exile(plan, ctx, pool[0])


def _cover_up_exile(plan: Any, ctx: Def, card_id: str) -> bool:
    from app.rules import card_names, context

    card = plan.state.cards[card_id]
    names, owner = card_names.names_of(plan.ch(card)), card.owner
    plan.do({"type": "move", "card_ids": [card_id], "to": {"zone": "exile"}}, actor=ctx["controller"])
    context.bind_players(ctx, "cover_up_owner", [owner])
    if names:
        ctx["effects"] = [*ctx["effects"][: ctx["next"]], {"do": "name_search", "by": "bound", "player": "cover_up_owner", "names": names, "all": False, "draw": True},
                          *ctx["effects"][ctx["next"]:]]
    return True


def resume_cover_up(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if chosen and _cover_up_exile(plan, ctx, chosen[0]):
        effects.continue_effects(plan, ctx)


_HUNTED = ("Choose up to four target creatures you don't control. For each of them, that creature's controller faces a villainous choice — That creature becomes a 1/1 "
           "white Human creature and loses all abilities, or you create a token that's a copy of it.")


def _hunted() -> Any:
    from app.rules import scripts

    found = scripts.parse_effects("Choose up to four target creatures you don't control.")
    return None if found is None else ([{"do": "hunted110m"}], found[1], found[2])


def hunted(plan: Any, ctx: Def, e: Def) -> bool:
    """Hunted by The Family: for each target still a creature on the battlefield, in the order they were chosen, its controller faces a villainous choice (701.55a): it
    becomes a 1/1 white Human creature and loses all abilities for good (611.2a, 613.1), or the caster creates a token that's a copy of it (701.55b: either may be
    impossible, then as much as possible happens). Each choice is made in its turn (villainous.py), the creature one specific object (400.7)."""
    from app.rules import effects

    steps: list[Def] = []
    for cid in effects._cards(plan, ctx, "target"):
        card = plan.state.cards[cid]
        if not card.zone.endswith(":battlefield") or not plan.ch(card).is_creature:
            continue
        who = f"object:{plan.oid(card)}"
        steps.append({"do": "villain", "who": f"player:{card.controller}", "labels": [f"{card.name} becomes a 1/1 white Human creature and loses all abilities",
                                                                                      f"Create a token that's a copy of {card.name}"],
                      "a": [{"do": "become", "who": who, "types": ["Creature"], "creature_types": ["Human"], "colors": ["W"], "p": 1, "t": 1, "duration": "permanent"},
                            {"do": "become", "who": who, "types": [], "lose_abilities": True, "duration": "permanent"}],
                      "b": [{"do": "token_copy", "n": 1, "who": who}]})
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *steps, *ctx["effects"][at:]]
    return True


_MARCH = ("Choose a nonbasic land type. Each land you control of that type becomes a copy of target creature you control until end of turn and gains haste until end of turn.")


def _march() -> Any:
    from app.rules import scripts

    found = scripts.parse_effects("Target creature you control gains haste until end of turn.")
    return None if found is None else ([{"do": "march110m"}], found[1], found[2])


def march(plan: Any, ctx: Def, e: Def) -> bool:
    """March from Velis Vel: its controller names a nonbasic land type as it resolves (608.2d, public); the lands of that type they control then are fixed (611.2c) before they stop being
    lands, and each becomes a copy of the target creature (707.2) with haste, until end of turn."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.layers import LAND_TYPES
    from app.rules.plan import decide

    if not effects._cards(plan, ctx, "target"):
        return True  # (an illegal target as it resolves: 608.2b)
    basics = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Urza\u2019s"}  # (the curly spelling is the same type as Urza's)
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name', '')}: choose a nonbasic land type",
           options=[DecisionOption(id=t, label=t) for t in sorted(LAND_TYPES - basics)], resume={"step": "march110m", "ctx": ctx})
    return False


def resume_march(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import copying, effects

    ctx = d.resume["ctx"]
    kind = chosen[0]
    plan.note(f"{plan.name(d.player)} chooses {kind}", actor=d.player)
    lands = [c.id for c in plan.state.cards.values() if c.zone == f"{ctx['controller']}:battlefield" and c.controller == ctx["controller"]
             and "Land" in plan.ch(c).types and kind in plan.ch(c).subtypes]
    if lands:
        group = "union:" + "+".join(f"object:{plan.oid(c)}" for c in lands)
        copying.become_copy(plan, ctx, {"do": "become_copy", "who": group, "with": "target", "duration": "end_of_turn"})
        effects.PRIMITIVES["grant"](plan, ctx, {"do": "grant", "who": group, "keywords": ["haste"]})
    effects.continue_effects(plan, ctx)


_CENTAUR_ETB = "When this creature enters, roll five six-sided dice and store those results on it."
_CENTAUR_COMBAT = "At the beginning of combat on your turn, you may reroll any number of this creature's stored results."
_CENTAUR_STATIC = "This creature gets +X/+X, where X is the greatest number of stored results on it of the same value."
_BUILD[_CENTAUR_ETB] = ("When this creature enters, roll five six-sided dice.", lambda d: {**d, "effects": [*d["effects"], {"do": "store_dice110m"}]})
_BUILD[_CENTAUR_ETB.replace("this creature", "Centaur of Attention")] = _BUILD[_CENTAUR_ETB]
_BUILD[_CENTAUR_COMBAT] = ("At the beginning of combat on your turn, you may have this creature gain vigilance until end of combat.",
                           lambda d: {**d, "optional": False, "effects": [{"do": "reroll_pick110m"}, {"do": "reroll_roll110m"}, {"do": "store_dice110m"}]})  # (the "may" is the choice of how many: none)


def _stored(plan: Any, ctx: Def) -> list[int] | None:
    """The stored results (706.8a, all d6 on the one card that has them) of the ability's source, if it is still that object (400.7)."""
    key = ctx.get("source_object")
    if key is None or plan.oid(ctx["source_card"]) != key:
        return None
    return plan.rules.stored_dice110m.setdefault(key, [])


def store_dice(plan: Any, ctx: Def, e: Def) -> bool:
    """706.8a: the results just rolled become stored results of the source permanent (gone with it if it left: a new object, 400.7)."""
    rolled = ctx.pop("dice", [])
    card = plan.state.cards.get(ctx.get("source_card", ""))
    if rolled and card is not None and card.zone.endswith(":battlefield") and (kept := _stored(plan, ctx)) is not None:
        kept.extend(rolled)
        plan.note(f"{card.name} stores {', '.join(map(str, rolled))}")
    return True


def reroll_pick(plan: Any, ctx: Def, e: Def) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    kept = _stored(plan, ctx)
    ctx["rerolled110m"] = 0
    if not kept:
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name', '')}: reroll any number of the stored results",
           options=[DecisionOption(id=str(i), label=f"Stored {v}") for i, v in enumerate(kept)], min_choices=0, max_choices=len(kept),
           resume={"step": "reroll_pick110m", "ctx": ctx})
    return False


def resume_reroll_pick(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    kept = _stored(plan, ctx)
    if kept is not None and chosen:
        gone = {int(i) for i in chosen}
        plan.rules.stored_dice110m[ctx["source_object"]] = [v for i, v in enumerate(kept) if i not in gone]  # 706.8b: the rerolled results stop being stored
        ctx["rerolled110m"] = len(gone)
        plan.note(f"{plan.name(d.player)} rerolls {len(gone)} stored result{'s' * (len(gone) != 1)}", actor=d.player)
    effects.continue_effects(plan, ctx)


def reroll_roll(plan: Any, ctx: Def, e: Def) -> bool:
    """706.8b: roll one die of the noted kind (a d6) for each rerolled result; they are stored on the permanent by the next effect."""
    from app.rules import dice

    if not ctx.get("rerolled110m"):
        ctx["dice"] = []
        return True
    return dice.roll(plan, ctx, {"do": "roll", "sides": 6, "count": ctx["rerolled110m"]})


def same_stored(plan: Any, ctx: Def) -> int:
    """The greatest number of stored results of the source that share one value (0: none stored)."""
    kept = plan.rules.stored_dice110m.get(ctx.get("source_object") or "", [])
    return max((kept.count(v) for v in set(kept)), default=0)


_SYLEX = "{1}, {T}: Each nontoken permanent with a name originally printed in the Antiquities expansion is sacrificed by its controller."
# CR 206.3b lists the names this refers to.
_ANTIQUITIES = frozenset(n.replace("\u2019", "'") for n in ["Amulet of Kroog", "Argivian Archaeologist", "Argivian Blacksmith", "Argothian Pixies", "Argothian Treefolk", "Armageddon Clock", "Artifact Blast", "", "Artifact Possession", "Artifact Ward", "Ashnod’s Altar", "Ashnod’s Battle Gear", "Ashnod’s Transmogrant", "Atog", "Battering Ram", "Bronze Tablet", "", "Candelabra of Tawnos", "Circle of Protection: Artifacts", "Citanul Druid", "Clay Statue", "Clockwork Avian", "Colossus of Sardia", "Coral Helm", "Crumble", "", "Cursed Rack", "Damping Field", "Detonate", "Drafna’s Restoration", "Dragon Engine", "Dwarven Weaponsmith", "Energy Flux", "Feldon’s Cane", "Gaea’s Avenger", "", "Gate to Phyrexia", "Goblin Artisans", "Golgothian Sylex", "Grapeshot Catapult", "Haunting Wind", "Hurkyl’s Recall", "Ivory Tower", "Jalum Tome", "Martyrs of Korlis", "", "Mightstone", "Millstone", "Mishra’s Factory", "Mishra’s War Machine", "Mishra’s Workshop", "Obelisk of Undoing", "Onulet", "Orcish Mechanics", "Ornithopter", "", "Phyrexian Gremlins", "Power Artifact", "Powerleech", "Priest of Yawgmoth", "Primal Clay", "The Rack", "Rakalite", "Reconstruction", "Reverse Polarity", "", "Rocket Launcher", "Sage of Lat-Nam", "Shapeshifter", "Shatterstorm", "Staff of Zegon", "Strip Mine", "Su-Chi", "Tablet of Epityr", "Tawnos’s Coffin", "Tawnos’s Wand", "", "Tawnos’s Weaponry", "Tetravus", "Titania’s Song", "Transmute Artifact", "Triskelion", "Urza’s Avenger", "Urza’s Chalice", "Urza’s Mine", "Urza’s Miter", "", "Urza’s Power Plant", "Urza’s Tower", "Wall of Spears", "Weakstone", "Xenic Poltergeist", "Yawgmoth Demon", "Yotian Soldier"])
_BUILD[_SYLEX] = ("{1}, {T}: You gain 1 life.", lambda d: {**d, "effects": [{"do": "sylex110m"}]})


def sylex(plan: Any, ctx: Def, e: Def) -> bool:
    """Golgothian Sylex: every nontoken permanent whose name is on the CR 206.3b list is sacrificed by its controller, all at once (701.21a)."""
    from app.rules import effects

    hit = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and not c.is_token
           and (plan.ch(c).name or "").replace("\u2019", "'") in _ANTIQUITIES]
    effects._sacrifice_cards(plan, hit, ctx["controller"], ctx)
    return True


_BLOODCASTER = "{1}{B}, {T}: Rather than pay the mana cost of the next spell you cast this turn, you may pay life equal to that spell's mana value."
_BUILD[_BLOODCASTER] = ("{1}{B}, {T}: You gain 1 life.",
                        lambda d: {**d, "effects": [{"do": "next_spell_grant", "grants": [{"keyword": "life110m", "filter": None}]}]})


def life_offers(state: Any, player: str, card: Any, ch: Any, info: Any) -> list[Any]:
    """Marshland Bloodcaster: the next spell its caster casts this turn may be cast by paying life equal to its mana value rather than its mana cost (118.9, 118.9b: optional;
    118.9c: the mana value is the printed one). A spell with {X} in its cost is not offered: its mana value while being cast depends on the X announced later (202.3e)."""
    from app.rules import alt_costs, spell_grants

    if not spell_grants.pending(state, player, card, ch, info, "life110m") or "X" in (ch.mana_cost or ""):
        return []
    alt = alt_costs.parse_cost(f"pay {int(ch.mana_value)} life")
    return [] if alt is None else [alt_costs.Offer(f"{card.id}:life110m", f"{ch.name}: pay {int(ch.mana_value)} life (Marshland Bloodcaster)", alt)]


def life_cause(plan: Any, ctx: Def | None) -> str | None:
    """The spell (card id) whose resolution is gaining life, if the effect is a spell's own (not an ability's): Firesong and Sunspeaker asks which spell caused a gain."""
    if ctx is None:
        return None
    card = plan.state.cards.get(ctx.get("source_card", ""))
    return card.id if card is not None and card.zone == "stack" and card.ability is None and plan.oid(card) == ctx.get("source_object") else None


_NIHILOOR_ETB = ("When Nihiloor enters, for each opponent, tap up to one untapped creature you control. When you do, gain control of target creature that player controls with power "
                 "less than or equal to the tapped creature's power for as long as you control Nihiloor.")
_NIHILOOR_ATTACK = "Whenever you attack with a creature an opponent owns, you gain 2 life and that player loses 2 life."
_NIH_ETB_NATIVE = "When this creature enters, gain control of target creature an opponent controls for as long as you control this creature."
_BUILD[_NIHILOOR_ETB] = (_NIH_ETB_NATIVE, lambda d: {**d, "effects": [{"do": "nihiloor110m", "steal": d["effects"]}], "target": None})  # (the steal as the grammar reads it)
_BUILD[_NIHILOOR_ETB.replace("Nihiloor", "~")] = _BUILD[_NIHILOOR_ETB]


def _nihiloor_attack(d: Def) -> Def:
    """Each attacking creature you control that an opponent owns (508.1, 603.2): you gain 2 life and its owner (the opponent) loses 2."""
    from app.rules import selectors

    cond = {**d["cond"], "sel": selectors.Selector(types=("Creature",), controller="you", owner="opponent").key()}
    return {**d, "cond": cond}


_BUILD[_NIHILOOR_ATTACK] = ("Whenever a creature you control attacks, you gain 2 life and that creature's owner loses 2 life.", _nihiloor_attack)


def _nih_ability(natives: Any) -> Def:
    """The reflexive ability (603.12): gain control of the target creature that player controls, power capped by the tapped creature's as the ability goes on the stack."""
    from dataclasses import replace

    from app.rules import selectors

    sel = selectors.Selector(types=("Creature",), controller="that_player", compare=(("power", "<=", selectors.EVENT_STAT + "power"),))
    return {"kind": "triggered", "trigger": "reflexive", "effects": natives, "optional": False, "target": {"what": replace(sel).key()}}


def nihiloor(plan: Any, ctx: Def, e: Def) -> bool:
    """Nihiloor, for each opponent (in turn order): its controller taps up to one untapped creature they control, then a reflexive ability for that opponent triggers (603.12a)."""
    ctx["nih110m"] = [p for p in plan.apnap() if p != ctx["controller"]]
    return _nihiloor_next(plan, ctx, e)


def _nihiloor_next(plan: Any, ctx: Def, e: Def) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    pid = ctx["controller"]
    while ctx["nih110m"]:
        opp = ctx["nih110m"].pop(0)
        mine = [c.id for c in plan.state.cards.values() if c.zone == f"{pid}:battlefield" and c.controller == pid and not c.tapped and plan.ch(c).is_creature]
        if not mine:
            continue
        decide(plan, player=pid, kind="choose_cards", prompt=f"{ctx.get('name', '')}: tap up to one untapped creature you control (for {plan.name(opp)})",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in mine], min_choices=0, max_choices=1,
               resume={"step": "nihiloor110m", "ctx": ctx, "e": e, "opp": opp})
        return False
    return True


def resume_nihiloor(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.rules_state import ObjectRef, TriggerEvent
    from app.rules import context, effects
    from app.rules.triggers import _add

    ctx, opp = d.resume["ctx"], d.resume["opp"]
    cards = [c for c in chosen if c in plan.state.cards and not plan.state.cards[c].tapped]
    if cards:
        plan.do({"type": "tap", "card_ids": cards, "tapped": True}, actor=ctx["controller"])
        ref = ObjectRef(card=cards[0], object_id=plan.oid(cards[0]))
        ref = ref.model_copy(update={"snapshot": context.snapshot(plan, ref)})
        _add(plan, controller=ctx["controller"], source_card=ctx.get("source_card") or "", source_object=ctx.get("source_object") or "", name=str(ctx.get("name") or ""),
             index=7301, definition=_nih_ability(d.resume["e"]["steal"]), event=TriggerEvent(kind="reflexive", objects=[ref], count=1, players=[opp]))
    if _nihiloor_next(plan, ctx, d.resume["e"]):
        effects.continue_effects(plan, ctx)


_SMOKE = ("For each of up to X target creatures, create a red Aura enchantment token named Smoke Blessing attached to that creature. Those tokens have enchant creature and "
          "\"When enchanted creature dies, it deals 1 damage to its controller and you create a Treasure token.\"")


def smoke(plan: Any, ctx: Def, e: Def) -> bool:
    """Smoke Spirits' Aid: one Smoke Blessing Aura token (roles.NAMED) for each target still a legal creature, each entering attached to its creature (303.4f); a token a replacement
    effect doubles is attached to the same creature (614.16). The tokens are made one after another, so each can be ordered against replacement effects."""
    from app.rules import effects

    steps = [{"do": "create_role", "role": "Smoke Blessing", "who": f"object:{plan.oid(cid)}"} for cid in effects._cards(plan, ctx, "target")]
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *steps, *ctx["effects"][at:]]
    return True


_ESTRID_MASK = "−1: Create a white Aura enchantment token named Mask attached to another target permanent. The token has enchant permanent and umbra armor."
_ESTRID_ULT = "−7: Mill seven cards. Return all non-Aura enchantment cards from your graveyard to the battlefield, then do the same for Aura cards."
_BUILD[_ESTRID_MASK] = ("−1: Create a Mask Aura token attached to another target permanent.", lambda d: d)
_BUILD[_ESTRID_ULT] = ("−7: Mill seven cards. Return all non-Aura enchantment cards from your graveyard to the battlefield. Return all Aura cards from your graveyard to the battlefield.", lambda d: d)


_MEDDLE = "If target spell has only one target and that target is a creature, change that spell's target to another creature."


def parse(body: str) -> Any:
    """Spell bodies. Meddle: any spell may be targeted; whether it has one target and that target is a creature is judged as this resolves (115.7a, 608.2b)."""
    from app.rules import scripts

    if body.strip() == _SMOKE:
        parsed = scripts.parse_effects("Choose up to X target creatures.")
        assert parsed is not None
        return [{"do": "smoke110m"}], parsed[1], False
    if body.strip() == _MARCH:
        return _march()
    if body.strip() == _HUNTED:
        return _hunted()
    if body.strip() == _COVER_UP:
        return _cover_up()
    if body.strip() == _BRILLIANCE:
        return _brilliance()
    if body.strip() == _RHINO:
        return _rhino()
    if body.strip() == _MEDDLE:
        parsed = scripts.parse_effects("Counter target spell.")
        assert parsed is not None
        _, target, optional = parsed
        return [{"do": "change_target", "who": "target", "must": "creature", "creature110m": True}], target, optional
    if body.strip() == _DAMNATIONS:
        parsed = scripts.parse_effects("Target opponent loses 1 life.")
        assert parsed is not None
        return [{"do": "damnations110m"}], parsed[1], False
    if body.strip() in (_REVERSAL, f"{_REVERSAL} Exile ~."):  # (the spell's own second sentence, "Exile Stunning Reversal.", moves it out of the graveyard's way)
        return [{"do": "lose_shield110m"}, *([{"do": "exile", "who": "self"}] if body.strip().endswith("Exile ~.") else [])], None, False
    return None


def _crown(d: Def) -> Def:
    """Crown of Convergence: only the creatures that share a color with the top card get the bonus; with no top card the condition fails (nothing)."""
    from app.rules import selectors

    sel = selectors.from_key(d["who"])
    return {**d, "who": replace(sel, extras=(*sel.extras, "top_color110m")).key()}


_BUILD["As long as the top card of your library is a creature card, creatures you control that share a color with that card get +1/+1."] = (
    "As long as the top card of your library is a creature card, creatures you control get +1/+1.", _crown)
_BUILD["{G}{W}: Put the top card of your library on the bottom of your library."] = (
    "{G}{W}: Draw a card.", lambda d: {**d, "effects": [{"do": "top_to_bottom110m", "who": "you"}]})


def top_to_bottom(plan: Any, ctx: Def, e: Def) -> bool:
    """Put the top card of the controller's library on the bottom of it (no one learns what it was; an empty library: nothing)."""
    pid = ctx["controller"]
    if library := plan.state.zones.get(f"{pid}:library", []):
        plan.do({"type": "move", "card_ids": [library[0]], "to": {"player": pid, "zone": "library"}, "position": "bottom"}, actor=pid)
        plan.note(f"{plan.name(pid)} puts the top card of their library on the bottom", actor=pid)
    return True


def _lucius(d: Def) -> Def:
    """Lucius the Eternal: 603.7a, 603.10a — the dying Lucius is exiled, and when the chosen creature leaves the battlefield that object (still in exile, 400.7) returns."""
    choose, delay = d["effects"][0], d["effects"][1]
    ret = {"do": "deferred:return_card", "who": "ref:e0", "to": "battlefield", "tapped": False, "under": "owner"}
    return {**d, "effects": [{"do": "exile", "who": "event.new", "as": "e0"}, choose, delay, ret]}


_LUCIUS = ("When this creature dies, exile it and choose target creature an opponent controls. When that creature leaves the battlefield, "
           "return this card from exile to the battlefield under its owner's control.")
_BUILD["Armour of Shrieking Souls — " + _LUCIUS.replace("this creature", "Lucius the Eternal")] = (
    "When this creature dies, choose target creature an opponent controls. When that creature leaves the battlefield, you gain 3 life.", _lucius)
_SCULPTOR = "{1}{W}, {T}: Target creature becomes an enchantment and loses all abilities until a player casts a creature spell."
_BUILD[_SCULPTOR] = ("{1}{W}, {T}: Target creature becomes an enchantment until your next turn. It loses all abilities until your next turn.",
                     lambda d: json.loads(json.dumps(d).replace('"next_turn"', '"creature_cast110m"')))


def spell_cast(plan: Any, card: Any) -> None:
    """Soul Sculptor: 611.2a — a creature spell cast by any player ends the effects that last until then (601.2i: it is a spell as soon as it is cast)."""
    from app.rules import delayed

    if plan.ch(card).is_creature and (ended := [e for e in plan.rules.effects if e.duration == "creature_cast110m"]):
        delayed._end(plan, ended)


NO_TAP = "no_tap_on_attack110m"
_JOHAN = ("At the beginning of combat on your turn, you may have Johan gain \"Johan can't attack\" until end of combat. If you do, attacking doesn't cause "
          "creatures you control to tap this combat if Johan is untapped.")


def _johan(d: Def) -> Def:
    """Johan: it can't attack until end of combat (611.2a), and its imposed rule (same duration, 514.2-style cleanup of the combat) is read where attackers tap."""
    return {**d, "effects": [{"do": "restrict", "who": "self", "rules": ["cant_attack", NO_TAP], "duration": "end_of_combat"}]}


_BUILD[_JOHAN] = ("At the beginning of combat on your turn, you may have Johan gain vigilance until end of combat.", _johan)


def attack_taps_nothing(plan: Any) -> bool:
    """508.1f: an untapped permanent of the attacking player carries Johan's rule this combat, so none of their creatures taps as it attacks."""
    return any(NO_TAP in plan.ch(c).imposed for c in plan.state.cards.values()
               if c.controller == plan.actor and c.zone == f"{plan.actor}:battlefield" and not c.tapped)


_MERIEKE = ("{T}: Gain control of target creature for as long as you control Merieke Ri Berit. When Merieke Ri Berit leaves the battlefield or becomes untapped, "
            "destroy that creature. It can't be regenerated.")


def _merieke(d: Def) -> Def:
    """Merieke Ri Berit: 603.7a — the delayed trigger watches Merieke herself (leaving, or becoming untapped: delayed.on_events), destroying the creature gained."""
    watch = {"do": "delayed", "when": {"kind": "event", "event": "leave_or_untap110m"}, "n": 2, "who": "self"}
    return {**d, "effects": [*d["effects"], watch, {"do": "deferred:destroy", "who": "target"}, {"do": "deferred:no_regen"}]}


_BUILD[_MERIEKE] = ("{T}: Gain control of target creature for as long as you control Merieke Ri Berit.", _merieke)

_GURZIGOST_UPKEEP = "At the beginning of your upkeep, sacrifice this creature unless you put two cards from your graveyard on the bottom of your library."
_GURZIGOST_ABILITY = "{G}{G}, Discard a card: You may have this creature assign its combat damage this turn as though it weren't blocked."
UNBLOCKED = "assign_unblocked110m"


def _gurzigost_upkeep(d: Def) -> Def:
    """118.12a: the controller may put exactly two cards from their graveyard on the bottom of their library (none, or with fewer than two there: sacrifice)."""
    sacrifice = d["effects"]
    return {**d, "effects": [{"do": "gurzigost110m"}, {"do": "only_if", "cond": {"flag": "gurzigost110m", "negate": True}, "skip": len(sacrifice)}, *sacrifice]}


_BUILD[_GURZIGOST_UPKEEP] = ("At the beginning of your upkeep, sacrifice this creature.", _gurzigost_upkeep)
_BUILD[_GURZIGOST_ABILITY] = ("{G}{G}, Discard a card: This creature can't be blocked this turn.",
                              lambda d: {**d, "effects": [{"do": "restrict", "who": "self", "rules": [UNBLOCKED]}]})


def gurzigost(plan: Any, ctx: Def, e: Def) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    pid = ctx["controller"]
    graveyard = list(plan.state.zones.get(f"{pid}:graveyard", []))
    if len(graveyard) < 2:
        context.bind_flag(ctx, "gurzigost110m", False)
        return True
    decide(plan, player=pid, kind="choose_cards", prompt=f"{ctx.get('name', '')}: put two cards from your graveyard on the bottom of your library (none: sacrifice it)",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in graveyard], min_choices=0, max_choices=2,
           resume={"step": "gurzigost110m", "ctx": ctx})
    return False


def resume_gurzigost(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.game.rules_state import DecisionOption
    from app.rules import context, effects
    from app.rules.plan import decide

    ctx, pid = d.resume["ctx"], d.player
    if d.resume.get("order"):  # (401.4: the owner puts them in the order they like: the chosen one goes on the very bottom)
        first = [c for c in d.resume["order"] if c != chosen[0]]
        plan.do({"type": "move", "card_ids": [*first, chosen[0]], "to": {"player": pid, "zone": "library"}, "position": "bottom"}, actor=pid)
        context.bind_flag(ctx, "gurzigost110m", True)
        effects.continue_effects(plan, ctx)
        return
    if len(chosen) not in (0, 2) or len(set(chosen)) != len(chosen) or any(c not in plan.state.zones.get(f"{pid}:graveyard", []) for c in chosen):
        raise ActionError("Choose exactly two cards from your graveyard, or none")
    if not chosen:
        context.bind_flag(ctx, "gurzigost110m", False)
        effects.continue_effects(plan, ctx)
        return
    decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name', '')}: which card goes on the very bottom of your library?",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in chosen],
           resume={"step": "gurzigost110m", "ctx": ctx, "order": chosen})


def unblocked_rule(ch: Any) -> bool:
    """Gurzigost: the creature may assign its combat damage this turn as though it weren't blocked (510.1c; asked in combat.ask_split)."""
    return UNBLOCKED in ch.imposed


_BUILD["Fortified land has indestructible."] = ("Enchanted land has indestructible.", lambda d: d)
_BUILD["Whenever fortified land becomes tapped, target creature gets +1/+1 until end of turn."] = (
    "Whenever enchanted land becomes tapped, target creature gets +1/+1 until end of turn.", lambda d: d)

BOOBY_RULE = "chosen_draw_reveal110m"
_BOOBY_ENTER = "As this artifact enters, choose an opponent and a card name other than a basic land card name."
_BOOBY_REVEAL = "The chosen player reveals each card they draw."
_BOOBY_TRIGGER = ("When the chosen player draws a card with the chosen name, sacrifice this artifact. If you do, this artifact deals 10 damage to that player.")


def _booby_trigger(d: Def) -> Def:
    return {**d, "cond": {**d["cond"], "hooked110m": True}}  # (a draw event for the "that player" it reads; on_draw adds the trigger, never the generic match)


_BUILD[_BOOBY_TRIGGER] = ("Whenever a player draws a card, sacrifice this artifact. If you do, this artifact deals 10 damage to that player.", _booby_trigger)
_BUILD[_BOOBY_REVEAL] = ("Players have no maximum hand size.", lambda d: {"kind": "static", "static": BOOBY_RULE, "effects": []})

_KAYLA = ("{4}, {T}: Discard all the cards in your hand, then draw that many cards. You may choose an artifact or creature card with mana value 1 you discarded this way, "
          "then do the same for artifact or creature cards with mana values 2 and 3. Return those cards to the battlefield. Activate only as a sorcery.")


def _kayla(d: Def) -> Def:
    """Queen Kayla bin-Kroog: up to one discarded artifact or creature card for each of the mana values 1, 2 and 3 — up to three cards with different mana values from
    those 1 to 3 — returned together (so one event, 603.2c); the discarded cards are public (404.2)."""
    from app.rules import selectors

    discard, draw, _, back = d["effects"]
    refs, _, sel_key = back["who"].partition("|")
    sel = selectors.from_key(sel_key)
    wide = replace(sel, compare=(("mv", ">=", 1), ("mv", "<=", 3))).key()
    return {**d, "effects": [discard, draw, {**back, "who": f"{refs}|{wide}", "n": 3, "upto": True, "different": "mana value"}]}


_BUILD[_KAYLA] = ("{4}, {T}: Discard your hand, then draw that many cards. You may return an artifact or creature card with mana value 1 discarded this way to the battlefield. "
                  "Activate only as a sorcery.", _kayla)

_ADVERSARY = ("When this creature enters, you may pay {1}{G} any number of times. When you pay this cost one or more times, put that many +1/+1 counters on this creature, then "
              "up to that many target lands you control become 3/3 Wolf creatures with haste that are still lands.")


def _adversary_definition(ability: Any, ch: Any) -> Def | None:
    """Primal Adversary: the two reflexive results read separately (the counters, the lands) are one ability — counters first, then the lands (603.12), both sized by the payments."""
    from app.rules import scripts

    head = "When this creature enters, you may pay {1}{G} any number of times. When you pay this cost one or more times, "
    counters = scripts.define(replace(ability, text=head + "put that many +1/+1 counters on this creature."), ch)
    lands = scripts.define(replace(ability, text=head + "up to that many target lands you control become 3/3 Wolf creatures with haste that are still lands."), ch)
    if counters is None or lands is None:
        return None
    first = next((e for e in counters["effects"] if e.get("do") == "reflexive"), None)
    second = next((e for e in lands["effects"] if e.get("do") == "reflexive"), None)
    if first is None or second is None:
        return None
    merged = {**second, "ability": {**second["ability"], "effects": [*first["ability"]["effects"], *second["ability"]["effects"]]}}
    return {**lands, "effects": [merged if e is second else e for e in lands["effects"]]}


_ASHIOK_PLUS = "+2: Exile the top three cards of target opponent's library."
_ASHIOK_X = ("−X: Put a creature card with mana value X exiled with Ashiok onto the battlefield under your control. That creature is a Nightmare in addition to its other types.")
_ASHIOK_ULT = "−10: Exile all cards from all opponents' hands and graveyards."


def _ashiok_plus(d: Def) -> Def:
    """607.2a: the cards it exiles are the ones the −X ability refers to."""
    return {**d, "effects": [{**x, "link": True} if x.get("do") == "exile_top" else x for x in d["effects"]]}


def _ashiok_x(d: Def) -> Def:
    return {**d, "effects": [{"do": "ashiok110m", "as": "e0"}, d["effects"][1]], "target": None}


_BUILD[_ASHIOK_PLUS] = (_ASHIOK_PLUS, _ashiok_plus)
_BUILD[_ASHIOK_X] = ("−1: Return a creature card from your graveyard to the battlefield. That creature is a Nightmare in addition to its other types.", _ashiok_x)
_BUILD[_ASHIOK_ULT] = ("−10: You gain 1 life.", lambda d: {**d, "effects": [{"do": "ashiok_ult110m"}], "target": None})


def ashiok(plan: Any, ctx: Def, e: Def) -> bool:
    """−X: one creature card with mana value X exiled with Ashiok (607.2a; it is a card in exile, a public zone when exiled face up) onto the battlefield under your control."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects, exiled_with
    from app.rules.plan import decide

    x = int(ctx.get("x") or 0)
    pool = [c for c in exiled_with.cards(plan, ctx) if "Creature" in plan.ch(plan.state.cards[c]).types and int(plan.ch(plan.state.cards[c]).mana_value) == x]
    back = {"to": "battlefield", "tapped": False, "under": "you", "as": e.get("as")}
    if len(pool) <= 1:
        return effects._return_cards(plan, ctx, back, pool)
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name', '')}: put a creature card with mana value {x} exiled with it onto the battlefield",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool], min_choices=1, max_choices=1,
           resume={"step": "ashiok110m", "ctx": ctx, "e": back, "pool": pool})
    return False


def resume_ashiok(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if effects._return_cards(plan, ctx, d.resume["e"], [c for c in chosen if c in d.resume["pool"]][:1]):
        effects.continue_effects(plan, ctx)


def ashiok_ult(plan: Any, ctx: Def, e: Def) -> bool:
    """−10: every card in each opponent's hand and graveyard goes to exile, face up (406.3), all at once for each owner."""
    for pid in plan.live():
        if pid == ctx["controller"]:
            continue
        ids = [*plan.state.zones.get(f"{pid}:hand", []), *plan.state.zones.get(f"{pid}:graveyard", [])]
        if ids:
            plan.do({"type": "move", "card_ids": ids, "to": {"player": pid, "zone": "exile"}}, actor=ctx["controller"])
    return True


_WHISPERS = ("When this creature dies, choose target opponent. That player puts this card from its owner's graveyard onto the battlefield under their control at the "
             "beginning of the next end step.")


def _whispers(d: Def) -> Def:
    """Endless Whispers: the opponent is chosen as the trigger goes on the stack (a target, 115.1); at the next end step that player puts the card (still that object in the
    graveyard, 400.7) onto the battlefield under their control."""
    return {**d, "effects": [{"do": "bind_target_player110m", "as": "copp"}, {"do": "delayed", "when": {"kind": "step", "step": "end", "whose": "next"}, "n": 1},
                             {"do": "deferred:return_card", "who": "event.new", "to": "battlefield", "tapped": False, "under": "ref:copp"}],
            "target": {"what": "opponent"}}


_BUILD[_WHISPERS] = ("When this creature dies, target opponent loses 1 life.", _whispers)
_BUILD[_WHISPERS.replace("this creature", "~")] = ("When this creature dies, target opponent loses 1 life.", _whispers)  # (the holder as the grant machinery writes it)
_BUILD[_WHISPERS.replace("this creature", "this permanent")] = ("When this creature dies, target opponent loses 1 life.", _whispers)  # (granted: granted.quote names the holder "this permanent")


def bind_target_player(plan: Any, ctx: Def, e: Def) -> bool:
    from app.rules import context, effects

    context.bind_players(ctx, e["as"], effects._players(plan, ctx, "target"))
    return True


_GANDALF = ("Whenever you cast a spell with mana value 5 or greater, each opponent reveals the top card of their library. If any of those cards shares a card type with that spell, "
            "copy that spell, you may choose new targets for the copy, and each opponent draws a card. Otherwise, you draw a card.")


def _gandalf(d: Def) -> Def:
    """Gandalf, Westward Voyager: the reveal (701.20a), then one comparison with the cast spell's types as it last existed (608.2h); the copy and the opponents' draws, or yours."""
    reveal = d["effects"][0]
    return {**d, "effects": [reveal, {"do": "gandalf110m"},
                             {"do": "only_if", "cond": {"flag": "gandalf110m"}, "skip": 3},
                             {"do": "copy_spell", "who": "event_spell"}, {"do": "copy_new_targets", "optional": True}, {"do": "draw", "who": "each_opponent", "n": 1},
                             {"do": "only_if", "cond": {"flag": "gandalf110m", "negate": True}, "skip": 1}, {"do": "draw", "who": "you", "n": 1}]}


_BUILD[_GANDALF] = ("Whenever you cast a spell with mana value 5 or greater, each opponent reveals the top card of their library.", _gandalf)


def gandalf(plan: Any, ctx: Def, e: Def) -> bool:
    from app.rules import context

    spell = context.info(plan, ctx, context.EVENT)
    types = set(spell[1].types) if spell is not None else set()
    shares = False
    for pid in plan.live():
        if pid == ctx["controller"]:
            continue
        library = plan.state.zones.get(f"{pid}:library", [])
        if library and types & set(plan.ch(plan.state.cards[library[0]]).types):
            shares = True
    context.bind_flag(ctx, "gandalf110m", shares)
    return True


_SPHINX = ("Whenever this creature deals combat damage to a player, search that player's library for a card, then that player chooses a card name. If you searched for a creature "
           "card that doesn't have that name, you may put it onto the battlefield under your control. Then that player shuffles.")


def _sphinx(d: Def) -> Def:
    """Sphinx Ambassador: the controller searches the damaged player's library (701.23a; hidden), that player names a card (201.4), a creature card not so named may be put onto the
    battlefield under the controller's control (400.3 — the card is a card in the library still), then that player shuffles (701.24)."""
    return {**d, "effects": [{"do": "sphinx_search110m"}, {"do": "choose_value", "who": "event_player", "what": "card name", "as": "sph_name"},
                             {"do": "sphinx_put110m"}, {"do": "shuffle_library", "who": "event_player"}]}


_BUILD[_SPHINX] = ("Whenever this creature deals combat damage to a player, you gain 1 life.", _sphinx)


def sphinx_search(plan: Any, ctx: Def, e: Def) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    ctx.pop("sph_card110m", None)
    victim = next(iter(effects._players(plan, ctx, "event_player")), None)
    ctx["sph_victim110m"] = victim
    library = list(plan.state.zones.get(f"{victim}:library", [])) if victim in plan.live() else []
    if not library:
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name', '')}: search {plan.name(victim)}'s library for a card",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in library], min_choices=0, max_choices=1,
           resume={"step": "sphinx_search110m", "ctx": ctx, "pool": library})
    return False


def resume_sphinx_search(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    ctx["sph_card110m"] = next((c for c in chosen if c in d.resume["pool"]), None)
    effects.continue_effects(plan, ctx)


def sphinx_put(plan: Any, ctx: Def, e: Def) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import card_names, context
    from app.rules.plan import decide

    cid, victim = ctx.get("sph_card110m"), ctx.get("sph_victim110m")
    named = (context.refs(ctx).get("sph_name") or {}).get("value")
    card = plan.state.cards.get(cid or "")
    if card is None or card.zone != f"{victim}:library" or not plan.ch(card).is_creature or card_names.has_name(plan.ch(card), named):
        return True
    decide(plan, player=ctx["controller"], kind="confirm", prompt=f"{ctx.get('name', '')}: put the creature card you searched for onto the battlefield under your control?",
           options=[DecisionOption(id="yes", label=f"Put {card.name} onto the battlefield"), DecisionOption(id="no", label="Leave it in the library")],
           resume={"step": "sphinx_put110m", "ctx": ctx, "card": cid})
    return False


def resume_sphinx_put(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if chosen == ["yes"] and (card := plan.state.cards.get(d.resume["card"])) is not None and card.zone.endswith(":library"):
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": ctx["controller"], "zone": "battlefield"}}, actor=ctx["controller"])
    effects.continue_effects(plan, ctx)


_CROC = "When a player has no cards in hand, if this permanent is an enchantment, it becomes a 4/4 Crocodile creature."


def _croc(d: Def) -> Def:
    """Veiled Crocodile (603.8, 603.4): the state is "a player has no cards in hand" while the permanent is an enchantment; once it becomes a creature (not "in addition", so no
    longer an enchantment, 205.1a) the state no longer matches and the trigger does not come back."""
    state = {"all": [{"as": "any", "cond": {"value": {"hand": "you"}, "op": "==", "n": 0}}, {"object": "self", "is": 'sel:{"types":["Enchantment"]}'}]}
    return {**d, "state": state}


_BUILD[_CROC] = ("When you control no Islands, this permanent becomes a 4/4 Crocodile creature.", _croc)

_TEFERI = ("−3: Tap any number of untapped creatures you control. When you do, shuffle target nonland permanent an opponent controls with mana value X or less into its owner's "
           "library, where X is the number of creatures tapped this way.")


def _teferi_definition(ability: Any, ch: Any) -> Def | None:
    """Teferi Akosa of Zhalfir −3: the creatures tapped are counted (X), and when at least one was, the reflexive ability (603.12) picks its target with mana value X or less as it goes
    on the stack (603.3d) — the same reflexive shape as "you may pay {X}. When you do, …"."""
    from app.rules import scripts

    tap = scripts.define(replace(ability, text="−3: Tap any number of untapped creatures you control."), ch)
    pay = scripts.parse_effects("You may pay {X}. When you do, shuffle target nonland permanent an opponent controls with mana value X or less into its owner's library.")
    if tap is None or pay is None or len(pay[0]) != 2 or pay[0][1].get("do") != "reflexive":
        return None
    count = {"do": "tap_count110m", "as": "tapped110m", "bind": "pay0"}
    return {**tap, "effects": [{**tap["effects"][0], "as": "tapped110m"}, count, pay[0][1]]}


def tap_count(plan: Any, ctx: Def, e: Def) -> bool:
    from app.rules import context, paid_x

    n = len(context.objects(plan, ctx, e["as"]))
    paid_x._record(ctx, e["bind"], n > 0, n)
    return True


_KYLOX = ("Whenever Kylox attacks, sacrifice any number of other creatures, then exile the top X cards of your library, where X is their total power. You may cast any number of instant "
          "and/or sorcery spells from among the exiled cards without paying their mana costs.")


def _kylox(d: Def) -> Def:
    """Kylox, Visionary Inventor: the sacrifice, the exile sized by their total power (608.2h), then the free casts from among exactly those cards (601.2, 118.9)."""
    from app.rules import selectors

    sacrifice, exile = d["effects"]
    cast = {"do": "free_cast", "zone": "that", "who": "ref:kylox110m", "filter": selectors.Selector(types=("Instant", "Sorcery"), zones=("stack",)).key(),
            "optional": True, "mv": None, "n": 99}
    return {**d, "effects": [sacrifice, {**exile, "as": "kylox110m"}, cast]}


_BUILD[_KYLOX] = ("Whenever this creature attacks, sacrifice any number of other creatures. Exile the top X cards of your library, where X is the total power of the creatures sacrificed this way.", _kylox)
_BUILD[_KYLOX.replace("Kylox attacks", "~ attacks")] = _BUILD[_KYLOX]

_DESDEMONA = ("Whenever Desdemona attacks, target creature card in your graveyard that's an artifact or that has mana value 3 or less gains escape until end of turn. The escape cost is "
              "equal to its mana cost plus exile two other cards from your graveyard.")


def _desdemona(d: Def) -> Def:
    from app.rules import selectors

    small = selectors.Selector(card=True, types=("Creature",), zones=("graveyard",), zone_owner="you", compare=(("mv", "<=", 3),)).key()
    artifact = selectors.Selector(card=True, types=("Creature", "Artifact"), zones=("graveyard",), zone_owner="you", extras=("all_types",)).key()
    what = selectors.Selector(card=True, zones=("graveyard",), zone_owner="you", either=(small, artifact)).key()
    return {**d, "effects": [{"do": "escape_grant110m", "who": "target"}], "target": {"what": what}}


_BUILD[_DESDEMONA] = ("Whenever this creature attacks, draw a card.", _desdemona)
_BUILD[_DESDEMONA.replace("Whenever Desdemona attacks", "Whenever ~ attacks")] = _BUILD[_DESDEMONA]


def escape_grant(plan: Any, ctx: Def, e: Def) -> bool:
    """The target card has escape until end of turn (611.2a): its escape cost is its mana cost plus exiling two other cards from the graveyard (see escape_offers)."""
    from app.rules import effects

    for cid in effects._cards(plan, ctx, e["who"]):
        card = plan.state.cards[cid]
        if card.zone == f"{card.owner}:graveyard":
            plan.rules.escape_grants110m.append({"oid": plan.oid(card), "owner": card.owner, "turn": plan.state.turn.number})
            plan.note(f"{card.name} gains escape until end of turn", [cid], actor=ctx["controller"])
    return True


def escape_offers(state: Any, player: str, card: Any, ch: Any, info: Any) -> list[Any]:
    """The escape cast a Desdemona grant gives this card now (702.138a): only the card that was targeted, still that object, in its owner's graveyard, on the turn it was granted."""
    from app.rules import alt_costs, escape
    from app.rules import mana as M
    from app.rules.graveyard_grants import _two_ways

    r = state.rules
    if r is None or not r.escape_grants110m or card.owner != player or not ch.mana_cost or "//" in ch.mana_cost or _two_ways(card):
        return []
    oid = r.object_id(card.id)
    if not any(g["oid"] == oid and g["owner"] == player and g["turn"] == state.turn.number for g in r.escape_grants110m):
        return []
    cost = M.parse_cost(ch.mana_cost)
    alt = None if cost.x or cost.unsupported else alt_costs.parse_cost(escape._cost_text(ch.mana_cost, 2))
    return [] if alt is None else [alt_costs.Offer(f"{card.id}:desdemona110m", f"{ch.name}: escape ({ch.mana_cost}, exile 2 other cards from your graveyard)", alt, escape=True)]


_RIP_TEXT = ("At the beginning of your second main phase, if Rip is tapped, reveal the top X cards of your library, where X is its power. Put any number of creature and/or Vehicle "
             "cards with different powers from among them into your hand. Put the rest on the bottom of your library in a random order.")


def _rip(d: Def) -> Def:
    return {**d, "effects": [{**x, "different110m": "power"} if x.get("do") == "pick_looked" else x for x in d["effects"]]}


_RIP_NATIVE = "Survival — " + _RIP_TEXT.replace("with different powers ", "").replace("if Rip is tapped", "if this creature is tapped")
for _holder in ("Rip", "~", "this creature"):
    _BUILD["Survival — " + _RIP_TEXT.replace("if Rip is tapped", f"if {_holder} is tapped")] = (_RIP_NATIVE, _rip)

_HURKYL = ("At the beginning of your end step, if you've cast a noncreature spell this turn, reveal the top five cards of your library. For each card type among noncreature spells "
           "you've cast this turn, you may put a card of that type from among the revealed cards into your hand. Put the rest on the bottom of your library in a random order.")


def noncreature_types_cast(plan: Any, pid: str) -> set[str]:
    """The card types among the noncreature spells ``pid`` cast this turn, as they were cast (601.2i, 608.2i)."""
    from app.rules.history import log_for

    return {t for note in log_for(plan).casts if note.player == pid and "Creature" not in note.types for t in note.types}


def one_per_type(plan: Any, pid: str, cards: list[str]) -> bool:
    """Can each chosen card be a card of a different type from those (a card of two types fills one of them)? A small matching, tried card by card."""
    kinds = sorted(noncreature_types_cast(plan, pid))
    have = [set(plan.ch(plan.state.cards[c]).types) & set(kinds) for c in cards]

    def fill(i: int, used: frozenset[str]) -> bool:
        return i == len(have) or any(fill(i + 1, used | {t}) for t in sorted(have[i] - used))

    return fill(0, frozenset())


_BUILD[_HURKYL] = ("At the beginning of your end step, if you've cast a noncreature spell this turn, reveal the top five cards of your library. Put any number of cards from among them "
                   "into your hand. Put the rest on the bottom of your library in a random order.",
                   lambda d: {**d, "effects": [{**x, "types_cast110m": True} if x.get("do") == "pick_looked" else x for x in d["effects"]]})

_FACES = ("Whenever a creature dies, tap all untapped creatures that share a creature type with it or untap all tapped creatures that share a creature type with it.")
_BUILD[_FACES] = ("Whenever a creature dies, draw a card.", lambda d: {**d, "effects": [{"do": "faces110m"}]})


def faces(plan: Any, ctx: Def, e: Def) -> bool:
    """Faces of the Past: its controller chooses as the trigger resolves; "it" is the creature as it last existed (608.2h), a changeling sharing with all (702.73a)."""
    from app.game.rules_state import DecisionOption
    from app.rules import context, selectors
    from app.rules.plan import decide

    died = context.info(plan, ctx, context.EVENT)
    kinds = tuple(sorted(died[1].subtypes & selectors.CREATURE_TYPES)) if died is not None else ()
    if not kinds:
        return True  # (no creature type, so nothing shares one with it)
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name', '')}: tap or untap the creatures that share a creature type with {died[0].name if died else 'it'}",
           options=[DecisionOption(id="tap", label="Tap all untapped creatures that share a creature type with it"),
                    DecisionOption(id="untap", label="Untap all tapped creatures that share a creature type with it")],
           resume={"step": "faces110m", "ctx": ctx, "kinds": list(kinds)})
    return False


def resume_faces(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects, selectors

    ctx = d.resume["ctx"]
    who = selectors.Selector(types=("Creature",), subtypes=tuple(d.resume["kinds"])).key()
    plan.note(f"{plan.name(d.player)} chooses to {chosen[0]} the creatures that share a creature type", actor=d.player)
    (effects.tap if chosen[0] == "tap" else effects.untap)(plan, ctx, {"who": who})
    effects.continue_effects(plan, ctx)


_REVERSAL = ("The next time you would lose the game this turn, instead draw seven cards and your life total becomes 1.")


def lose_shield(plan: Any, ctx: Def, e: Def) -> bool:
    """Stunning Reversal: a one-shot replacement of the controller's next loss of the game this turn (614.1a, 614.5); applied in wave110c_lose."""
    plan.rules.lose_shields110m.append({"player": ctx["controller"], "turn": plan.state.turn.number, "card": ctx.get("source_card")})
    return True


def lose_shields(plan: Any, pid: str) -> list[tuple[Any, Def]]:
    """The live shields of ``pid`` as replacement sources (the card that made them, exiled by then): only this turn's (610.3)."""
    return [(card, {"life": "reversal110m"}) for x in plan.rules.lose_shields110m
            if x["player"] == pid and x["turn"] == plan.state.turn.number and (card := plan.state.cards.get(x["card"] or "")) is not None]


_DAMNATIONS = ("Target opponent chooses a number. You may have that player lose that much life. If you don't, that player sacrifices all but that many "
               "permanents of their choice.")


def damnations(plan: Any, ctx: Def, e: Def) -> bool:
    """Choice of Damnations, step 1: the target opponent chooses a number (any number 0 or greater, announced to everyone, 107.1b)."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.group_choice import NUMBER
    from app.rules.plan import decide

    opp = next(iter(effects._players(plan, ctx, "target")), None)
    if opp is None or opp not in plan.live():
        return True  # (an illegal target as it resolves: 608.2b)
    decide(plan, player=opp, kind="choose_one", prompt=f"{ctx.get('name', '')}: choose a number",
           options=[DecisionOption(id=NUMBER, label="Type a number ≥ 0", group="number")], resume={"step": "damnations110m", "ctx": ctx, "opp": opp})
    return False


def resume_damnations(plan: Any, d: Any, chosen: list[str]) -> None:
    """Step 2: its controller may have that player lose that much life."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    ctx, opp = d.resume["ctx"], d.resume["opp"]
    n = max(0, int(chosen[0])) if chosen and chosen[0].isdigit() else 0
    plan.note(f"{plan.name(opp)} chooses {n}", actor=opp)
    decide(plan, player=ctx["controller"], kind="confirm", prompt=f"{ctx.get('name', '')}: have {plan.name(opp)} lose {n} life? (If not, they sacrifice all but {n} permanents)",
           options=[DecisionOption(id="yes", label=f"{plan.name(opp)} loses {n} life"), DecisionOption(id="no", label=f"{plan.name(opp)} sacrifices all but {n} permanents")],
           resume={"step": "damnations110m_lose", "ctx": ctx, "opp": opp, "n": n})


def resume_damnations_lose(plan: Any, d: Any, chosen: list[str]) -> None:
    """Step 3: life lost, or the player keeps the number of permanents they chose (the rest are sacrificed together, 701.21a)."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    ctx, opp, n = d.resume["ctx"], d.resume["opp"], d.resume["n"]
    if chosen and chosen[0] == "yes":
        if effects.lose_life(plan, ctx, {"do": "lose_life", "who": f"player:{opp}", "n": n}):
            effects.continue_effects(plan, ctx)
        return
    perms = [c.id for c in plan.state.cards.values() if c.zone == f"{opp}:battlefield" and c.controller == opp and plan.in_game(c)]
    if len(perms) > n > 0:
        decide(plan, player=opp, kind="choose_cards", prompt=f"{ctx.get('name', '')}: choose {n} permanents to keep; sacrifice the rest",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Permanent", card_id=c) for c in perms],
               min_choices=n, max_choices=n, resume={"step": "damnations110m_keep", "ctx": ctx, "opp": opp, "perms": perms})
        return
    effects._sacrifice_cards(plan, perms if n == 0 else [], opp, ctx, None)
    effects.continue_effects(plan, ctx)


def resume_damnations_keep(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, opp = d.resume["ctx"], d.resume["opp"]
    keep = set(chosen)
    effects._sacrifice_cards(plan, [c for c in d.resume["perms"] if c not in keep], opp, ctx, None)
    effects.continue_effects(plan, ctx)


RESUME: dict[str, Any] = {"nihiloor110m": resume_nihiloor, "reroll_pick110m": resume_reroll_pick, "march110m": resume_march, "sphinx_search110m": resume_sphinx_search, "sphinx_put110m": resume_sphinx_put, "ashiok110m": resume_ashiok, "gurzigost110m": resume_gurzigost, "cover_up110m": resume_cover_up, "faces110m": resume_faces, "damnations110m": resume_damnations, "damnations110m_lose": resume_damnations_lose,
                          "damnations110m_keep": resume_damnations_keep}
PRIMITIVES: dict[str, Any] = {"smoke110m": smoke, "nihiloor110m": nihiloor, "sylex110m": sylex, "store_dice110m": store_dice, "reroll_pick110m": reroll_pick, "reroll_roll110m": reroll_roll, "top_to_bottom110m": top_to_bottom, "faces110m": faces, "lose_shield110m": lose_shield, "escape_grant110m": escape_grant, "march110m": march, "tap_count110m": tap_count, "sphinx_search110m": sphinx_search, "sphinx_put110m": sphinx_put, "gandalf110m": gandalf, "bind_target_player110m": bind_target_player, "ashiok110m": ashiok, "ashiok_ult110m": ashiok_ult, "hunted110m": hunted, "gurzigost110m": gurzigost, "cover_up110m": cover_up, "damnations110m": damnations}
