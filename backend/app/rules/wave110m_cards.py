"""-- wave 110M -- exact Oracle wordings of single cards, built from parts of wordings the grammar already reads.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

import json
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


ATK_TAX = "block_tax_atk110m"
_PRESENCE = "Enchanted creature can't be blocked unless defending player pays {3} for each creature they control that's blocking it."


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
    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
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


_MEDDLE = "If target spell has only one target and that target is a creature, change that spell's target to another creature."


def parse(body: str) -> Any:
    """Spell bodies. Meddle: any spell may be targeted; whether it has one target and that target is a creature is judged as this resolves (115.7a, 608.2b)."""
    from app.rules import scripts

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


RESUME: dict[str, Any] = {"cover_up110m": resume_cover_up, "faces110m": resume_faces, "damnations110m": resume_damnations, "damnations110m_lose": resume_damnations_lose,
                          "damnations110m_keep": resume_damnations_keep}
PRIMITIVES: dict[str, Any] = {"top_to_bottom110m": top_to_bottom, "faces110m": faces, "lose_shield110m": lose_shield, "cover_up110m": cover_up, "damnations110m": damnations}
