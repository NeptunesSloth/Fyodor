"""-- wave 110G -- exact Oracle wordings of single cards, read as a wording the grammar reads or built from parts of it (as wave110b_cards)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]


def _keep_revealed(d: Def) -> Def:
    """The first choice leaves the rest of the revealed hand revealed for the second (701.20a)."""
    first = next(e for e in d["effects"] if e["do"] == "choose_from_hand")
    first["keep110g"] = True
    return d


def _controlled_since_turn_start(d: Def) -> Def:
    """"Except for creatures the player hasn't controlled continuously since the beginning of the turn": only those controlled since then are destroyed."""
    from app.rules import controller_turn_history69, selectors

    eff = d["effects"][0]
    head, _, key = eff["who"].partition("|sel:")
    sel = selectors.from_key("sel:" + key)
    return {**d, "effects": [{**eff, "who": f"{head}|" + replace(sel, extras=(*(("didnt_attack_combat110g" if x == "didnt_attack_this_turn" else x) for x in sel.extras), controller_turn_history69.EXTRA)).key()}]}


def _battles(d: Def) -> Def:
    """"...and each battle they protect": a second damage effect to the battles an opponent protects (310.8)."""
    from app.rules import selectors

    sel = replace(selectors.from_key('sel:{"types":["Battle"]}'), extras=("protected_by_opp110g",))
    return {**d, "effects": [*d["effects"], {**d["effects"][0], "who": sel.key()}]}


def _any_shuffle(d: Def) -> Def:
    """Psychogenic Probe: any player's shuffle (701.24), not just an opponent's."""
    return {**d, "cond": {**d["cond"], "player": "any"}}


def _shuffler_puts_back(d: Def) -> Def:
    """Widespread Panic: the shuffling player (the trigger's event player) puts the card back, not each opponent."""
    return {**_any_shuffle(d), "effects": [{**d["effects"][0], "who": "event_player"}]}


def _twin(d: Def) -> Def:
    """The token is named Twin and copies the attacker's power and toughness once, as it is created (111.1)."""
    token = d["effects"][0]["token"]
    token.update(name="Twin", toughness={"toughness": "self"})
    return d


def _pay_life_reveal(d: Def) -> Def:
    """Pay any amount of life (119.4, 0 up to the life total), then reveal that many cards (701.20a): the payment's amount sizes the reveal."""
    pay = {"do": "optional_payment", "who": "you", "cost": "", "bind": "viz110g", "choose_x": {"max": {"life": "you"}, "life": True}}
    reveal, *rest = d["effects"]
    return {**d, "effects": [pay, {**reveal, "n": {"paid_x": "viz110g"}}, *rest]}


def _walls_only(d: Def) -> Def:
    return {**d, "if": {"w110g": "walls_block"}}


def walls_block(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    """509.1g / 509.3b: another Wall blocks the attacker this creature blocks, and every creature blocking it is a Wall."""
    attacker = ((ctx.get("event") or {}).get("other") or {}).get("card")
    blockers = [c for c in plan.state.cards.values() if attacker and c.blocks(attacker)]
    return any(c.id != ctx.get("source_card") for c in blockers) and all("Wall" in plan.ch(c).subtypes for c in blockers)


def opponent_protects(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    """310.8: the targeted battle's protector is an opponent of the ability's controller."""
    from app.rules import battles

    return any((p := battles.protector(plan.state, c)) is not None and p != ctx["controller"]
               for t in ctx.get("targets") or [] if t and (c := plan.state.cards.get(t["id"])) is not None)


def holds(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    return bool({"walls_block": walls_block, "opp_protects": opponent_protects}[cond["w110g"]](plan, ctx, cond))


_INFERNAL = ("Choose an opponent. You and that player each sacrifice a creature. Each player who sacrificed a creature this way draws two cards.")
_REANIMATE = ("Choose an opponent. Return a creature card from your graveyard to the battlefield, then that player returns a creature card from their graveyard "
              "to the battlefield.")
_BARGE = ("Target creature gains islandwalk until end of turn. When ~ leaves the battlefield this turn, destroy that creature. "
          "A creature destroyed this way can't be regenerated.")
_SWING = ("Choose target battle. If an opponent protects it, remove three defense counters from it. Otherwise, put three defense counters on it.")


def parse(body: str) -> Any:
    """Etched Host Doombringer's mode: one target battle; the protector decides between removing and adding (310.4, 310.8)."""
    from app.rules import scripts

    if body.strip() == _INFERNAL:  # Infernal Offering mode 1: the controller and the chosen opponent sacrifice together (101.4, 701.21a)
        got = scripts.parse_effects("Choose an opponent. Each player sacrifices a creature. "
                                    "Each player who sacrificed a creature this way draws two cards.")
        if got is None:
            return None
        (pick, sac, *rest), target, optional = got  # type: ignore[misc]
        return [{**pick, "as": "e0"}, {**sac, "do": "sacrifice_pair110g", "who": "ref:e0"}, *rest], target, optional
    if body.strip() == _REANIMATE:  # Infernal Offering mode 2: "then" is a sequence, as the grammar reads two sentences
        return scripts.parse_effects("Choose an opponent. Return a creature card from your graveyard to the battlefield. "
                                     "That player returns a creature card from their graveyard to the battlefield.")
    if body.strip() == _BARGE:  # War Barge: the 'leaves' trigger belongs to the artifact (self), its effect to the ability's target (603.7c)
        from app.rules import bound_delayed_effects as bound
        from app.rules import language

        group = language.target_group("target creature")
        if group is None:
            return None
        return [{"do": "grant", "who": "target", "keywords": ["islandwalk"]},
                *bound._event("leave", "self", [{"do": "destroy", "who": "target"}, {"do": "no_regen"}])], [group], False
    if body != _SWING:
        return None
    (remove,), target, optional = scripts.parse_effects("Remove three defense counters from target battle.")  # type: ignore[misc]
    (add,), _, _ = scripts.parse_effects("Put three defense counters on target battle.")  # type: ignore[misc]
    opp = {"w110g": "opp_protects"}
    gate = lambda cond: {"do": "only_if", "cond": cond, "skip": 1}  # noqa: E731 - a failed condition skips the next effect
    return [gate(opp), remove, gate({"not": opp}), add], target, optional


def _exchange_power(d: Def) -> Def:
    """701.12g: exchanging two powers makes a continuous effect setting each (613.4b) to the other's previous value."""
    return {**d, "effects": [{"do": "exchange_power110g", "duration": "end_of_combat"}]}


def _lowest_life_control(d: Def) -> Def:
    """Loxodon Peacekeeper: the player with the lowest life total gains control; the controller picks among ties."""
    return {**d, "effects": [{"do": "lowest_life_control110g"}]}


# whole ability text -> the wording the grammar reads for it
_AS: dict[str, str] = {
    # Portcullis: "two or more other creatures" is three or more with the entering one; the card returns when the artifact leaves (610.3)
    "Whenever a creature enters, if there are two or more other creatures on the battlefield, exile that creature. Return that card to the battlefield "
    "under its owner's control when this artifact leaves the battlefield.":
        "Whenever a creature enters, if there are three or more creatures on the battlefield, exile it until this artifact leaves the battlefield.",
    # Acquisitions Expert: the opponent reveals that many cards of their choice (701.20a); "those cards" read as "them"
    "When this creature enters, target opponent reveals a number of cards from their hand equal to the number of creatures in your party. "
    "You choose one of those cards. That player discards that card.":
        "When this creature enters, target opponent reveals a number of cards from their hand equal to the number of creatures in your party. "
        "You choose one of them. That player discards that card.",
}

def _transformed(d: Def) -> Def:
    """Invasion of Pyrulea (back face): the group is transformed permanents (701.27g), not creatures."""
    from app.rules import selectors, zones100g

    return {**d, "who": replace(selectors.from_key(d["who"]), types=(), extras=(zones100g.TRANSFORMED,)).key()}


def _land_or_dfc(d: Def) -> Def:
    """Invasion of Pyrulea: the revealed card is a land card or a double-faced card (711.1)."""
    from app.rules import selectors

    dfc = selectors.Selector(zones=(), card=True, extras=("double_faced_card",)).key()
    fx = [{**e, "cond": {"any": [e["cond"], {**e["cond"], "is": dfc}]}} if e.get("do") == "only_if" else e for e in d["effects"]]
    return {**d, "effects": fx}


# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    # Serene Master
    "Whenever this creature blocks, exchange its power and the power of target creature it's blocking until end of combat.":
        ("Whenever this creature blocks, target creature it's blocking has base power 3 until end of combat.", _exchange_power),
    # Total War: attack declaration (508.1); "didn't attack" = not among this combat's attackers
    "Whenever a player attacks with one or more creatures, destroy all untapped non-Wall creatures that player controls that didn't attack, except for creatures "
    "the player hasn't controlled continuously since the beginning of the turn.":
        ("Whenever a player attacks with one or more creatures, destroy all untapped non-Wall creatures that player controls that didn't attack this turn.",
         _controlled_since_turn_start),
    # Gemini Engine: "X/X where X is its power", toughness patched
    "Whenever this creature attacks, create a colorless Construct artifact creature token named Twin that's attacking. Its power is equal to this creature's power "
    "and its toughness is equal to this creature's toughness. Sacrifice the token at end of combat.":
        ("Whenever this creature attacks, create an X/X colorless Construct artifact creature token that's attacking, where X is this creature's power. "
         "Sacrifice it at end of combat.", _twin),
    # Psychogenic Probe: every library shuffle in the engine is made by a spell or ability (701.24)
    "Whenever a spell or ability causes a player to shuffle their library, this artifact deals 2 damage to that player.":
        ("Whenever an opponent shuffles their library, this artifact deals 2 damage to that player.", _any_shuffle),
    # Widespread Panic
    "Whenever a spell or ability causes its controller to shuffle their library, that player puts a card from their hand on top of their library.":
        ("Whenever an opponent shuffles their library, each opponent puts a card from their hand on top of their library.", _shuffler_puts_back),
    # Joyful Stormsculptor
    "Whenever you cast a spell that has convoke, this creature deals 1 damage to each opponent and each battle they protect.":
        ("Whenever you cast a spell that has convoke, this creature deals 1 damage to each opponent.", _battles),
    # Vizkopa Confessor
    "When this creature enters, pay any amount of life. Target opponent reveals that many cards from their hand. You choose one of them and exile it.":
        ("When this creature enters, target opponent reveals a number of cards from their hand equal to the number of creatures you control. "
         "You choose one of them. Exile that card.", _pay_life_reveal),
    "Other transformed permanents you control have trample and ward {2}.":
        ("Other creatures you control have trample and ward {2}.", _transformed),
    "When this Siege enters, scry 3, then reveal the top card of your library. If it's a land or double-faced card, draw a card.":
        ("When this Siege enters, scry 3, then reveal the top card of your library. If it's a land card, draw a card.", _land_or_dfc),
    # Loxodon Peacekeeper
    "At the beginning of your upkeep, the player with the lowest life total gains control of this creature. If two or more players are tied for lowest life total, "
    "you choose one of them, and that player gains control of this creature.":
        ("At the beginning of your upkeep, you gain control of this creature.", _lowest_life_control),
    # Wall of Caltrops
    "Whenever this creature blocks a creature, if at least one other Wall creature is blocking that creature and no non-Wall creatures are blocking that creature, "
    "this creature gains banding until end of turn.":
        ("Whenever this creature blocks a creature, this creature gains banding until end of turn.", _walls_only),
    # Distended Mindbender: two sequential choices from the revealed hand (701.9)
    "When you cast this spell, target opponent reveals their hand. You choose from it a nonland card with mana value 3 or less and a card with mana value 4 or greater. "
    "That player discards those cards.":
        ("When you cast this spell, target opponent reveals their hand. You choose a nonland card with mana value 3 or less from it. That player discards that card. "
         "You choose a card with mana value 4 or greater from it. That player discards that card.", _keep_revealed),
}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if (same := _AS.get(ability.text.strip())) is not None:
        return scripts.define(replace(ability, text=same), ch)
    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def lowest_life_control(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Control goes to the lowest life total (119.1); on a tie the controller chooses one of the tied players (this card's text)."""
    from app.rules import effects

    live = list(plan.live())
    low = min(plan.state.players[p].life for p in live)
    tied = [p for p in live if plan.state.players[p].life == low]
    if len(tied) > 1:
        effects.decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a tied player to gain control",
                       options=[effects.DecisionOption(id=p, label=plan.name(p)) for p in tied], resume={"step": "lowest_control110g", "ctx": ctx, "tied": tied})
        return False
    return effects.gain_control(plan, ctx, {"do": "gain_control", "who": "self", "to": f"player:{tied[0]}"})


def resume_lowest_control(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if chosen[0] not in d.resume["tied"]:
        raise ValueError("not a tied player")
    plan.note(f"{plan.name(d.player)} chooses {plan.name(chosen[0])}")
    if effects.gain_control(plan, ctx, {"do": "gain_control", "who": "self", "to": f"player:{chosen[0]}"}):
        effects.continue_effects(plan, ctx)


def sacrifice_pair(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """701.21a, 101.4: the controller and the player ``who`` names choose in APNAP order, then both sacrifice at once."""
    from app.rules import effects

    pair = {ctx["controller"], *effects._players(plan, ctx, e["who"])}
    return effects._sacrifice_next(plan, ctx, e["sel"], 1, [p for p in plan.apnap() if p in pair], [], e.get("as"))  # type: ignore[no-any-return]


def exchange_power(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Both powers are read before either is set (701.12g)."""
    from app.rules import effects, values

    mine, theirs = (values.evaluate(plan, ctx, {"power": who}) for who in ("self", "target"))
    base = {"do": "become", "types": [], "duration": e["duration"]}
    effects.become(plan, ctx, {**base, "who": "self", "p": theirs})
    return effects.become(plan, ctx, {**base, "who": "target", "p": mine})


PRIMITIVES: dict[str, Any] = {"exchange_power110g": exchange_power, "lowest_life_control110g": lowest_life_control,
                           "sacrifice_pair110g": sacrifice_pair}
RESUME: dict[str, Any] = {"lowest_control110g": resume_lowest_control}
