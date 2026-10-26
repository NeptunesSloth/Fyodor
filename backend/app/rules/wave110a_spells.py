"""-- spells (wave 110A) -- instant and sorcery wordings read onto the existing primitives."""
from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

Parsed = tuple[list[dict[str, Any]], Any, bool]


def _p(text: str) -> Parsed:
    from app.rules import scripts

    got = scripts.parse_effects(text)
    if got is None:
        raise AssertionError(f"wave110a: the grammar no longer reads {text!r}")
    return copy.deepcopy(got)


def _berserk() -> Parsed:
    """Berserk: "that creature attacked this turn" is read as the end step begins (508.1; the attack record of that object, 400.7)."""
    effects, target, optional = _p("Target creature gains trample and gets +X/+0 until end of turn, where X is its power. "
                                   "At the beginning of the next end step, destroy that creature.")
    destroy, delayed = effects.pop(), effects[-1]
    cond = {"history": "object", "object": "ref:berserk110a", "what": "attacked"}
    return [*effects[:-1], {"do": "bind110a", "who": "target", "as": "berserk110a"}, {**delayed, "n": 2},
            {"do": "deferred:only_if", "cond": cond, "skip": 1}, destroy], target, optional


def _take_the_bait() -> Parsed:
    """Take the Bait: the prevention covers you and the planeswalkers you control (615.1; damage to a planeswalker, 120.3c), then the attackers untap and
    are goaded (701.15), then the added combat phase (500.8)."""
    from app.rules import selectors

    prevent = _p("Prevent all combat damage that would be dealt to you and creatures you control this turn.")[0][0]
    walkers = selectors.Selector(controller="you", types=("Planeswalker",)).key()
    rest = _p("Untap all attacking creatures and goad them. After this phase, there is an additional combat phase.")[0]
    return [{**prevent, "scope": {**prevent["scope"], "to_objects": walkers}}, *rest], None, False


def _ronin() -> Parsed:
    """The Last Ronin's Technique: tokens that enter tapped and attacking (508.4) when the sneak cost was paid, else plain tokens (702.190a)."""
    cond = {"object": "self", "cast": {"alt": "sneak"}}
    attacking = _p("Create three 1/1 white Ninja Turtle Spirit creature tokens that are tapped and attacking.")[0]
    plain = _p("Create three 1/1 white Ninja Turtle Spirit creature tokens.")[0]
    return [{"do": "only_if", "cond": cond, "skip": 1}, *attacking, {"do": "only_if", "cond": {"not": cond}, "skip": 1}, *plain], None, False


def _snow(add: bool) -> Callable[[], Parsed]:
    from app.rules import selectors

    def build() -> Parsed:
        return ([{"do": "snow110a", "who": "target", "add": add}],
                (selectors.Selector(not_supertypes=("Snow",)) if add else selectors.Selector(supertypes=("Snow",))).key(), False)
    return build


def controller_of(plan: Any, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    """"its controller has …": the condition judged for the controller the object has, or had as it last existed (608.2h); gone: false (608.2b)."""
    from app.rules import conditions, values

    found = values._object(plan, ctx, cond["object"])
    return found is not None and conditions.holds(plan, {**ctx, "controller": found[0].controller}, cond["cond"])


CONDITIONS = {"controller_of": controller_of}


def _anoint() -> Parsed:
    """Anoint with Affliction: judged once as it resolves (608.2c): corrupted (its controller has three or more poison counters) exiles it
    whatever its mana value, else only with mana value 3 or less."""
    from app.rules import multi100n

    base, target, optional = _p("Exile target creature if it has mana value 3 or less.")
    alt = _p("Exile target creature.")[0]
    corrupted = {"w110a": "controller_of", "object": "target", "cond": {"value": {"player_counters": "poison"}, "op": ">=", "n": 3}}
    return multi100n._instead(corrupted, base, alt), target, optional


def _slime() -> Parsed:
    """Convert to Slime: delirium counts the graveyard after the destruction ("Then", 608.2c); X is the total mana value of the permanents that were
    destroyed this way, each as it last existed (608.2h) — one that wasn't destroyed (indestructible, regenerated) counts for nothing."""
    effects, groups, optional = _p("Destroy up to one target artifact, up to one target creature, and up to one target enchantment. Then if there are four "
                                   "or more card types among cards in your graveyard, create a 1/1 green Ooze creature token.")
    total = {"plus": [{"sum": "mana_value", "of": f"ref:slime{i}"} for i in range(3)]}
    out = []
    for e in effects:
        if e["do"] == "destroy":
            e = {**e, "as": f"slime{e['who'].rpartition(':')[2]}"}
        elif e["do"] == "create_token":
            e = {**e, "token": {**e["token"], "power": total, "toughness": total}}
        out.append(e)
    return out, groups, optional


def _repeat_put(what: str) -> Callable[[], Parsed]:
    """Eureka, Hypergenesis: each player in turn, starting with you, may put one such card from their hand onto the battlefield (101.4: in turn order,
    each choice after the cards before it entered); the round is repeated while someone put a card onto the battlefield."""
    def build() -> Parsed:
        put = _p(f"Each player may put {what} card from their hand onto the battlefield.")[0][0]
        return [{"do": "repeat_put110a", "put": put, "first": True}], None, False
    return build


def repeat_put(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    if not e["first"] and not ctx.get("_any_put110a"):
        return True
    ctx["_any_put110a"] = False
    seats = plan.apnap()
    order = [p for p in seats[seats.index(ctx["controller"]):] + seats[:seats.index(ctx["controller"])] if p in plan.live()]
    steps: list[dict[str, Any]] = []
    for p in order:
        steps += [{**e["put"], "who": f"player:{p}"}, {"do": "note_put110a", "p": p}]
    ctx["effects"][ctx["next"]:ctx["next"]] = [*steps, {**e, "first": False}]
    return True


def note_put(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """each_put left the players who put nothing in ``_put_none``: this round goes on if one put a card."""
    if e["p"] not in ctx.get("_put_none", ()):
        ctx["_any_put110a"] = True
    return True


def _meditation() -> Parsed:
    """Cleansing Meditation: threshold judged as it resolves (608.2c); instead the enchantment cards in your graveyard that were destroyed this way
    (so yours: they go to their owner's graveyard, 400.3) return to the battlefield under your control."""
    from app.rules import multi100n

    base, target, optional = _p("Destroy all enchantments.")
    alt = _p("Destroy all enchantments, then return all enchantment cards put into your graveyard this way to the battlefield.")[0]
    return multi100n._instead(multi100n._cond("there are seven or more cards in your graveyard"), base, alt), target, optional

def _searing_light_exile() -> Parsed:
    """Olórin's Searing Light: each opponent exiles a creature with the greatest power among creatures they control (101.4: simultaneous choices,
    the edict's group exile)."""
    exile = copy.deepcopy(_p("Each opponent exiles a creature they control with the greatest power among creatures they control.")[0][0])
    return [{**exile, "as": "exiled110a"}], None, False


def _searing_light_mastery() -> Parsed:
    """Spell mastery (an ability word, no rule meaning, 207.2c): each opponent is dealt damage equal to the power of the creature that player exiled,
    as it last existed (608.2h)."""
    cond = _cond("there are two or more instant and/or sorcery cards in your graveyard")
    return [{"do": "only_if", "cond": cond, "skip": 1}, {"do": "exiled_power_damage110a", "ref": "exiled110a"}], None, False


def _cond(text: str) -> dict[str, Any]:
    from app.rules import multi100n

    return multi100n._cond(text)


def exiled_power_damage(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Damage from the source to each player who exiled a creature this way, equal to that creature's power as it last existed (120.3, 608.2h)."""
    from app.rules import context, effects, sba

    hits = []
    # (a spell's lines keep their own binding names, scripts.rename_bindings: the first line's "l0_exiled110a" is found by its suffix)
    name = next((k for k in context.refs(ctx) if k.endswith(e["ref"])), e["ref"])
    for card, ch in context.infos(plan, ctx, name):
        n = sba.power(card, ch)
        if n and n > 0:
            hits.append((effects._ability_source(plan, ctx), card.controller, n))
    return effects._deal(plan, ctx, hits) if hits else True


def exile_hands(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Every card in every hand, at once (a selector never reads hidden zones of other players; the move is public, 400.1)."""
    from app.game.state import zone_key
    from app.rules import effects

    return effects.exile_cards(plan, ctx, e, [c for p in plan.live() for c in plan.state.zones.get(zone_key(p, "hand"), [])])


def counter_opponents(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """701.6a: counter every spell and ability an opponent controls on the stack (not this spell); then ``make``'s n tokens, one for each
    that was really countered (a spell that can't be countered stays, 101.2): "for each spell and ability countered this way" (608.2c)."""
    from app.rules import effects

    sids = [c for c in plan.state.zones.get("stack", []) if c != ctx.get("stack_id") and plan.state.cards[c].controller != ctx["controller"]]
    for sid in sids:
        effects.counter_object(plan, sid, ctx["controller"], by=ctx["controller"])
    return effects.PRIMITIVES["create_token"](plan, ctx, {**e["make"], "n": sum(c not in plan.rules.stack for c in sids)})


def _answer() -> Parsed:
    """Glen Elendra's Answer: one Faerie token for each spell and ability that was countered."""
    return [{"do": "counter_opponents110a", "make": _p("Create a 1/1 blue and black Faerie creature token with flying.")[0][0]}], None, False


SPLENDOR = ("At the beginning of your upkeep, draw a card if your life total is greater than or equal to the last noted life total for ~. "
            "Then note your life total.")


def noted_draw(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Draw if the controller's life total is at least the one last noted for the source, then note it again (the source's own choice)."""
    from app.rules import effects, wave110a_enter

    card = plan.state.cards[ctx["source_card"]]
    noted = card.choices.get(wave110a_enter.NOTE, "")
    if noted and plan.state.players[ctx["controller"]].life >= int(noted):
        effects.PRIMITIVES["draw"](plan, ctx, e["draw"])
    if card.zone.endswith(":battlefield") and plan.oid(card) == ctx.get("source_object"):
        wave110a_enter.note(plan, card)
    return True


def _memories() -> Parsed:
    """Memories Returning: the five revealed cards are split by turns, you taking one, then a chosen opponent putting one on the bottom (608.2c)."""
    first = _p("Reveal the top five cards of your library. Put one of them into your hand.")[0]
    pick = first[1]
    bottom = {**pick, "to": "bottom", "chooser": "ref:opp110a"}
    last = {**pick, "which": "all"}
    return [*first, {"do": "choose_value", "who": "you", "what": "opponent", "as": "opp110a"}, bottom, copy.deepcopy(pick), copy.deepcopy(bottom), last], None, False


def _decree() -> Parsed:
    """Decree of Annihilation: the three exiles in order (608.2c); "all cards from all hands" is every card in every hand (the hand zones, 400.1)."""
    first = _p("Exile all artifacts, creatures, and lands. Exile all cards from all graveyards.")[0]
    return [*first, {"do": "exile_hands110a"}], None, False


# Sentences the grammar reads in other words with the same meaning (the rewrite must mean the same: 608.2c).
REWRITES = {
    # (Hellish Rebuke: the granted trigger names its caster; effects.grant binds "the player who cast this spell" to the caster's id)
    'Until end of turn, permanents your opponents control gain "When ~ deals damage to the player who cast ‹granter›, sacrifice ~. You lose 2 life."':
        'Until end of turn, permanents your opponents control gain "When this permanent deals damage to the player who cast this spell, sacrifice this permanent. You lose 2 life."',
    # (Threaten: control and haste both last until end of turn, 611.2a)
    "Until end of turn, you gain control of target creature and it gains haste.":
        "Gain control of target creature until end of turn. It gains haste until end of turn.",
    # (122.6: "enters with … additional counters" is the grammar's "if a creature enters this way, it enters with …" for the returned permanent card)
    "Return target historic permanent card from your graveyard to the battlefield. It enters with two additional +1/+1 counters on it if it's a "
    "creature.": "Return target historic permanent card from your graveyard to the battlefield. If a creature enters this way, it enters with two "
                 "additional +1/+1 counters on it.",
    # (Bioshift: "with the same controller" = the controller of the first target, the "that player" of Mutiny's wording; player_relative._names_player)
    "Move any number of +1/+1 counters from target creature onto another target creature with the same controller.":
        "Move any number of +1/+1 counters from target creature onto another target creature that player controls.",
    # (Dispersal: lands have mana value 0, so a nonland permanent has the greatest mana value among all permanents its controller controls exactly
    # when it has it among their nonland ones; each opponent chooses, 701.21a-style, one after the other, then the discards)
    "Each opponent returns a nonland permanent they control with the greatest mana value among permanents they control to its owner's hand, then "
    "discards a card.":
        "Each opponent chooses a nonland permanent with the greatest mana value among nonland permanents they control. Return it to its owner's hand. "
        "Each opponent discards a card.",
}


def _choose_transform(kind: str) -> Parsed:
    from app.rules import nontarget_creature_choices as pick

    return [pick.choose(kind, **{"as": "choice_group"}), {"do": "transform", "who": "ref:choice_group"}], None, False


def _owner_too() -> Parsed:
    """Pendant of Prosperity: the artifact's owner (108.3, wherever it is now) does the same as you (608.2c: each player's own hand)."""
    mine = _p("Draw a card, then you may put a land card from your hand onto the battlefield.")[0]
    draw, put = _p("Target player draws a card, then that player may put a land card from their hand onto the battlefield.")[0]
    return [*mine, {**draw, "who": "source_owner"}, {**put, "who": "source_owner"}], None, False


_ROUND = " Repeat this process until no one puts a card onto the battlefield."
def _melee() -> Parsed:
    """Melee: 509.3g, 506.4 — the watch is the grammar's "untap it and tap it" with the second step read as "remove it from combat"."""
    effects, target, optional = _p("Whenever a creature attacks and isn't blocked this combat, untap it and tap it.")
    assert effects[-1]["do"] == "deferred:tap"
    return [*effects[:-1], {**effects[-1], "do": "deferred:remove_from_combat"}], target, optional


def _chooser(kind: str, combat: bool = False) -> Callable[[], Parsed]:
    return lambda: ([{"do": "declare_chooser110a", "kind": kind, "combat": combat}], None, False)


def _dovin() -> Parsed:
    """Dovin Baan +1: the -3/-0 and "can't be activated" (602.5, mana abilities too) both last until your next turn (611.2b)."""
    pump, target, optional = _p("Until your next turn, up to one target creature gets -3/-0.")
    return [*pump, {"do": "restrict", "who": "target:0", "rules": ["cant_activate"], "duration": "next_turn"}], target, optional


def _rescue() -> Parsed:
    """Rescue from the Underworld: the target and the sacrificed card (as the cost left it in the graveyard, 400.7) are bound now (603.7c) and both
    return at your next upkeep, only if still there (400.7)."""
    effects, target, optional = _p("Return target creature card from your graveyard to the battlefield under your control at the beginning of your "
                                   "next upkeep. Exile ~.")
    delayed, back, rest = effects[0], effects[1], effects[2:]
    return [{"do": "bind_sacrificed110a"}, delayed, {**back, "who": "union:target+ref:sacrificed110a"}, *rest], target, optional


def bind_sacrificed(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Name the card the spell's cost sacrificed, as the object it is now in the graveyard (not as it last existed: a card that leaves isn't returned)."""
    from app.rules import context, values

    got = values._object(plan, ctx, "cost:sacrificed")
    if got is not None and plan.state.cards[got[0].id].zone.endswith(":graveyard"):
        context.bind_objects(plan, ctx, "sacrificed110a", [got[0].id])
    return True


def _cursed_each() -> Parsed:
    from app.rules import selectors

    return [{"do": "each100c", "who": selectors.Selector(types=("Creature",), controller="opponent").key(),
             "then": {"do": "create_role", "role": "Cursed"}}], None, False


def _plunge() -> Parsed:
    """Plunge into Darkness: the amount of life is chosen as it resolves (119.4: at most your life total, 0 allowed), paid, and the same number of
    cards are looked at (608.2c)."""
    look = _p("Look at the top X cards of your library. Put one of those cards into your hand and exile the rest.")[0]
    pay = {"do": "optional_payment", "who": "you", "cost": "", "bind": "plunge110a", "choose_x": {"max": None, "life": True}}
    return [pay, {**look[0], "n": {"paid_x": "plunge110a"}}, *look[1:]], None, False


def _continue_pilgrimage() -> Parsed:
    """Yuna's Decision: "a creature card and/or a land card" is at most one of each (two optional puts); all of it depends on the sacrifice (608.2c)."""
    effects, target, optional = _p("Sacrifice a creature. If you do, draw a card. You may put a creature card from your hand onto the battlefield. "
                                   "You may put a land card from your hand onto the battlefield.")
    effects[1]["skip"] = len(effects) - 2
    return effects, target, optional


def _beheld_power(text: str) -> Callable[[], Parsed]:
    """Monstrous Emergence / Dragon's Fire: the beheld creature (701.4a: a creature card revealed from hand or a creature you control) stands for
    "the sacrificed creature" of the parsed wording (values: cost:beheld110a)."""
    def build() -> Parsed:
        effects, target, optional = _p(text)
        for e in effects:
            if e.get("n") == {"power": "cost:sacrificed"}:
                e["n"] = {"power": "cost:beheld110a"}
        if effects[0].get("bind") == "cond0":  # Dragon's Fire: "If you control a Dragon" was parsed, the real condition is "a Dragon was beheld"
            effects[0]["cond"] = {"not": {"object": "self", "cast": {"optional": "behold"}}}
        return effects, target, optional
    return build


def _vats() -> Parsed:
    """V.A.T.S.: any number of target creatures whose toughnesses are all equal (601.2c; targets.relation_ok ``same_toughness110a``), destroyed."""
    effects, targets, optional = _p("Destroy any number of target creatures.")
    targets[0]["same_toughness110a"] = True
    return effects, targets, optional


def gambit(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Illusionist's Gambit: the attackers leave combat (506.4) and untap (701.26b); in the additional combat (500.8) each of them attacks if able
    and can't attack the caster or their planeswalkers: continuous attack effects that begin with the next combat (attack_destinations.begin_window)."""
    from app.rules import effects, layers

    who = 'sel:{"attacking":true,"types":["Creature"]}'
    cards = effects._cards(plan, ctx, who)
    effects.PRIMITIVES["remove_from_combat"](plan, ctx, {"do": "remove_from_combat", "who": who})
    if cards:
        effects.PRIMITIVES["untap"](plan, ctx, {"do": "untap", "who": "union:" + "+".join("object:" + plan.oid(c) for c in cards)})
    for cid in cards:
        card = plan.state.cards[cid]
        if card.zone.endswith(":battlefield"):
            layers.add_effect(plan, affected=[plan.oid(cid)], layer="6", source=ctx.get("source_object"), controller=ctx["controller"], duration="permanent",
                              imposes=("must_attack", f"cant_attack_player_pw:{ctx['controller']}"), declaration_window="next_combat",
                              declaration_player=card.controller)
    return effects.PRIMITIVES["extra_phases"](plan, ctx, {"do": "extra_phases", "after": "phase", "main": False})


def wheel(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Wheel of Potential: each player in turn order may exile their hand and draw as many cards as the {E} paid (101.4: all answer first,
    then it happens); if seven or more were paid, the controller may play the cards they own exiled this way until the end of their next turn."""
    from app.rules import context

    n = context.amount(ctx, next((k for k in context.refs(ctx) if k.endswith("energy_paid")), "energy_paid"))
    me, at = ctx["controller"], ctx["next"]
    players = list(plan.apnap())
    added: list[dict[str, Any]] = [{"do": "tempt_ask", "player": p, "bind": f"w110a_{i}", "text": "exile your hand and draw cards"}
                                   for i, p in enumerate(players)]
    hand = 'sel:{"card":true,"zone_owner":"you","zones":["hand"]}'
    for i, p in enumerate(players):
        added += [{"do": "only_if", "cond": {"flag": f"w110a_{i}"}, "skip": 4}, {"do": "as_player", "player": p},
                  {"do": "exile", "who": hand, "as": f"w110a_x{i}"}, {"do": "draw", "who": "you", "n": n}, {"do": "as_player_end"}]
    if n >= 7:
        added.append({"do": "grant_owned110a", "from": f"w110a_x{players.index(me)}"})
    ctx["effects"][at:at] = added
    return True


def grant_owned(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The controller may play the exiled cards they own (the others stay exiled) until the end of their next turn."""
    from app.rules import context, effects

    if e["from"] not in context.refs(ctx):  # (the controller declined: nothing was exiled)
        return True
    context.bind_objects(plan, ctx, "w110a_own", [c for c in context.objects(plan, ctx, e["from"]) if plan.state.cards[c].owner == ctx["controller"]])
    return effects.PRIMITIVES["grant_play"](plan, ctx, {"do": "grant_play", "who": "ref:w110a_own", "play": True, "cast": True,
                                                         "until": "end_of_next_turn", "optional": True})


def _wheel() -> Parsed:
    return [{"do": "wheel110a"}], None, False


def _interrogation() -> Parsed:
    """Officious Interrogation: X is summed over the chosen players that are still legal targets (608.2b, target_player_counts)."""
    chosen = _p("Choose any number of target players.")
    inv = _p("Investigate X times, where X is the number of creatures you control.")
    return [{**inv[0][0], "n": {"sum_for_players": "target:0", "of": inv[0][0]["n"]}}, *inv[0][1:]], chosen[1], False


def _new_blood() -> Parsed:
    """New Blood: gain control, then change the creature's text (612.1, 612.2: one creature type word becomes Vampire; text_change_instructions71 does the layer-3 effect)."""
    gain = _p("Gain control of target creature.")
    return [*gain[0], {"do": "new_blood110a"}], gain[1], False


def new_blood(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.creature_types import CREATURE_TYPES

    ctx["effects"][ctx["next"]:ctx["next"]] = [
        {"do": "choose_value", "what": "word to replace", "who": "you", "as": "text71_old", "options": sorted(CREATURE_TYPES)},
        {"do": "new_blood_apply110a"}]
    return True


def new_blood_apply(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, text_change_instructions71

    old = context.refs(ctx).get("text71_old", {}).get("value")
    if old == "Vampire":
        return True  # replacing a word with itself changes nothing
    context.refs(ctx)["text71_new"] = {"value": "Vampire"}
    return text_change_instructions71.apply_word(plan, ctx, {"category": "creature", "old": old, "not_wall": False, "duration": "permanent"})


def _gambit() -> Parsed:
    return [{"do": "gambit110a"}], None, False


def _calix() -> Parsed:
    """Calix -3: the exile lasts until the second target (an enchantment you control) leaves (610.3a, 610.3c)."""
    _, targets, optional = _p("Exile target creature or enchantment you don't control. Untap target enchantment you control.")
    return [{"do": "exile_until_target110a", "who": "target:0", "anchor": "target:1"}], targets, optional


def exile_until_target(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """610.3c: nothing is exiled if the enchantment already left (Calix ruling: either target gone, no exile); the cards return when it leaves."""
    from app.rules import effects

    anchor = [c for c in effects._cards(plan, ctx, e["anchor"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    if not anchor:
        return True
    keep, ctx["source_object"] = ctx["source_object"], plan.oid(anchor[0])
    try:
        return effects._exile_until_cards(plan, ctx, e, [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")])
    finally:
        ctx["source_object"] = keep


BUILDERS: dict[str, Callable[[], Parsed]] = {
    "Exile target creature or enchantment you don't control until target enchantment you control leaves the battlefield.": _calix,
    "Gain control of target creature. Change the text of that creature by replacing all instances of one creature type with Vampire.": _new_blood,
    "Choose any number of target players. Investigate X times, where X is the total number of creatures those players control.": _interrogation,
    "Each player may exile their hand and draw a number of cards equal to the amount of {E} paid this way. If seven or more {E} was paid this way, "
    "you may play cards you own exiled this way until the end of your next turn.": _wheel,
    "Remove all attacking creatures from combat and untap them. After this phase, there is an additional combat phase. Each of those creatures attacks that "
    "combat if able. They can't attack you or planeswalkers you control that combat.": _gambit,
    "Choose any number of target creatures with equal toughness. Destroy the chosen creatures.": _vats,
    "Reveal the top five cards of your library. Put one of them into your hand. Then choose an opponent. They put one on the bottom of your library. "
    "Then you put one into your hand. Then they put one on the bottom of your library. Put the other into your hand.": _memories,
    "Counter all spells your opponents control and all abilities your opponents control. Create a 1/1 blue and black Faerie creature token with "
    "flying for each spell and ability countered this way.": _answer,
    "Create three 1/1 white Ninja Turtle Spirit creature tokens. If this spell's sneak cost was paid, they enter tapped and attacking.": _ronin,
    "~ deals damage equal to the power of the creature you chose or the card you revealed to target creature.":
        _beheld_power("~ deals damage equal to the power of the sacrificed creature to target creature."),
    "~ deals 3 damage to target creature or planeswalker. If you revealed a Dragon card or chose a Dragon as you cast this spell, ~ deals damage "
    "equal to the power of that card or creature instead.":
        _beheld_power("~ deals 3 damage to target creature or planeswalker. If you control a Dragon, ~ deals damage equal to the power of the "
                      "sacrificed creature to that permanent instead."),
    "Sacrifice a creature. If you do, draw a card, then you may put a creature card and/or a land card from your hand onto the battlefield.":
        _continue_pilgrimage,
    # Asinine Antics: 303.7 / 111.1 one Cursed Role token per creature, each attached to its own creature (static_spell100c.each)
    "For each creature your opponents control, create a Cursed Role token attached to that creature.": _cursed_each,
    "Pay any amount of life, then look at that many cards from the top of your library. Put one of those cards into your hand and exile the rest.":
        _plunge,
    "Choose target creature card in your graveyard. Return that card and the sacrificed card to the battlefield under your control at the beginning "
    "of your next upkeep. Exile ~.": _rescue,
    "Until your next turn, up to one target creature gets -3/-0 and its activated abilities can't be activated.": _dovin,
    # Gideon of the Trials +1: 615.1 a prevention shield that lasts until the controller's next turn (the shield record's own duration)
    "Until your next turn, prevent all damage target permanent would deal.": lambda: (
        [{**(got := _p("Prevent all damage target permanent would deal this turn."))[0][0], "duration": "next_turn"}], got[1], got[2]),
    "Target player draws 2ˣ cards.": lambda: ([{"do": "draw", "who": "target", "n": {"two_pow": {"x": 1}}}], "player", False),  # Mathemagics: 107.3 X
    "Each opponent exiles a creature with the greatest power among creatures that player controls.": _searing_light_exile,
    "If there are two or more instant and/or sorcery cards in your graveyard, ~ deals damage to each opponent equal to the power of the "
    "creature they exiled.": _searing_light_mastery,
    "Exile all artifacts, creatures, and lands from the battlefield, all cards from all graveyards, and all cards from all hands.": _decree,
    "Whenever a creature attacks and isn't blocked this combat, untap it and remove it from combat.": _melee,
    # Predatory Focus: 510.1c, each blocked creature of the controller asks its own "as though it weren't blocked" (group_unblocked.allows)
    "You may have creatures you control assign their combat damage this turn as though they weren't blocked.":
        lambda: ([{"do": "unblocked_turn110a"}], None, False),
    # Full Bore: 702.185a, the creature's spell was cast for its warp cost (the record stays with the permanent)
    "Target creature you control gets +3/+2 until end of turn. If that creature was cast for its warp cost, it also gains trample and haste until "
    "end of turn.": lambda: (lambda got: ([got[0][0], {"do": "only_if", "cond": {"object": "target", "cast_alt110a": "warp"}, "skip": 1}, got[0][2]],
                                          got[1], got[2]))(_p("Target creature you control gets +3/+2 until end of turn. If that creature is tapped, it also "
                                                                "gains trample and haste until end of turn.")),
    "You choose which creatures attack this turn.": _chooser("attack"),  # Master Warcraft: 508.1a
    "You choose which creatures block this turn and how those creatures block.": _chooser("block"),  # 509.1a
    "You choose which creatures block this combat and how those creatures block.": _chooser("block", True),
    "you choose which creatures block this combat and how those creatures block.": _chooser("block", True),  # Odric's trigger body (509.1a)
    "Draw a card, then you may put a land card from your hand onto the battlefield. ~'s owner draws a card, then that player may put a land "
    "card from their hand onto the battlefield.": _owner_too,
    "Destroy all enchantments. If there are seven or more cards in your graveyard, instead destroy all enchantments, then return all cards in your "
    "graveyard destroyed this way to the battlefield.": _meditation,
    "Starting with you, each player may put a permanent card from their hand onto the battlefield." + _ROUND: _repeat_put("a permanent"),
    "Starting with you, each player may put an artifact, creature, enchantment, or land card from their hand onto the battlefield." + _ROUND:
        _repeat_put("an artifact, creature, enchantment, or land"),
    "Destroy up to one target artifact, up to one target creature, and up to one target enchantment. Then if there are four or more card types among "
    "cards in your graveyard, create an X/X green Ooze creature token, where X is the total mana value of permanents destroyed this way.": _slime,
    "Exile target creature if it has mana value 3 or less. Exile that creature instead if its controller has three or more poison counters.": _anoint,
    "Tap up to three target creatures. Put a stun counter on one of them.": lambda: (  # Aerith Rescue Mission: 122.1g, one of the targets (608.2d)
        [*(tap := _p("Tap up to three target creatures."))[0], {"do": "bind110a", "who": "target:0", "as": "targets110a"},
         {"do": "choose_one_of", "who": "ref:targets110a", "n": 1, "as": "one110a"},
         {"do": "add_counters", "who": "ref:one110a", "kind": "stun", "n": 1}], tap[1], False),
    "Incubate 2, then transform an Incubator token you control.": lambda: (  # Sunder the Gateway: 701.53a, then 701.28 the Incubator you choose
        [*_p("Incubate 2.")[0], *_choose_transform("Incubator token you control")[0]], None, False),
    # Thermal Flux: 205.4 snow is a supertype, so layer 4 (613.1d), until end of turn (the duration of supertype100i is the effect's default)
    # Needle Drop: 115.4 any target (a player, creature, planeswalker or battle) that was dealt damage this turn (targets.legal_targets "any_hurt110a")
    "~ deals 1 damage to any target that was dealt damage this turn.": lambda: (_p("~ deals 1 damage to any target.")[0], "any_hurt110a", False),
    "Target nonsnow permanent becomes snow until end of turn.": _snow(True),
    "Target snow permanent isn't snow until end of turn.": _snow(False),
    "Prevent all combat damage that would be dealt to you and planeswalkers you control this turn. Untap all attacking creatures and goad them. "
    "After this phase, there is an additional combat phase.": _take_the_bait,
    "End the combat phase.": lambda: ([{"do": "end_combat_phase110a"}], None, False),  # (Mandate of Peace: 724.2)
    "Target creature gains trample and gets +X/+0 until end of turn, where X is its power. At the beginning of the next end step, destroy that "
    "creature if it attacked this turn.": _berserk,
}


def bind(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Name the objects ``who`` is now (400.7), so a condition of a delayed trigger can ask about them."""
    from app.rules import context, effects

    context.bind_objects(plan, ctx, e["as"], effects._cards(plan, ctx, e["who"]))
    return True


def end_combat_phase(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """724.2: the expedited process, as end_turn.end_turn (724.1) but to the next phase (the postcombat main, or an added phase): earlier triggers
    that weren't on the stack cease to exist (724.2a), the stack is exiled with the resolving spell (724.2b), state-based actions (724.2c), combat is
    left and "until end of combat" effects expire (724.2d), no end of combat step so its abilities don't trigger (724.2e); outside a combat phase
    nothing happens (724.2g)."""
    from app.game.state import COMBAT_PHASES, STACK
    from app.rules import combat, combat_rules, engine, sba, triggers

    if plan.state.turn.phase not in COMBAT_PHASES:
        return True
    r = plan.rules
    triggers.collect(plan)
    r.pending_triggers = []
    for sid in list(plan.state.zones.get(STACK, [])):
        oid = plan.oid(sid)
        r.stack.pop(sid, None)
        r.buyback = [o for o in r.buyback if o != oid]
        r.flashback = [o for o in r.flashback if o != oid]
        r.exile_resolves.pop(oid, None)
        plan.do({"type": "move", "card_ids": [sid], "to": {"player": plan.state.cards[sid].owner, "zone": "exile"}}, actor=ctx["controller"])
    plan.note(f"{ctx.get('name') or 'An effect'} ends the combat phase (724.2)", actor=ctx["controller"])
    sba.check(plan)
    combat.end_combat(plan)
    engine.empty_pools(plan)
    plan.do({"type": "phase", "to": combat_rules.next_phase(plan) or "main2", "force": True}, actor=plan.active)
    engine._mark_step(plan)
    engine.on_step_start(plan)
    return r.decision is None


def snow(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Layer 4 (613.1d), until end of turn: the target permanent becomes snow or isn't snow (205.4, 611.2c: locked to the objects it began on)."""
    from app.rules import effects, layers

    cards = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    if cards:
        change: dict[str, Any] = {"add_supertypes": ["Snow"]} if e["add"] else {"remove_supertypes": ["Snow"]}
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer="4", source=ctx.get("source_object"), controller=ctx["controller"],
                          label=f"{'snow' if e['add'] else 'not snow'} ({ctx.get('name', '')})", **change)
    return True


# Whole abilities the grammar reads in other words (same meaning).
ABILITY_REWRITES = {
    # Karn, Living Legacy -1: "pay any amount of mana" (0 allowed) is the sized optional payment {X}; looking at 0 cards when none is paid changes nothing
    "\u22121: Pay any amount of mana. Look at that many cards from the top of your library, then put one of those cards into your hand and the rest on the bottom of "
    "your library in a random order.":
        "\u22121: You may pay {X}. If you do, look at the top X cards of your library, then put one of those cards into your hand and the rest on the bottom of your "
        "library in a random order.",
    # Estrid, the Masked: the Mask Aura token (roles.NAMED), enchant permanent + umbra armor
    "\u22121: Create a white Aura enchantment token named Mask attached to another target permanent. The token has enchant permanent and umbra armor.":
        "\u22121: Create a Mask Aura token attached to another target permanent.",
    "\u22127: Mill seven cards. Return all non-Aura enchantment cards from your graveyard to the battlefield, then do the same for Aura cards.":
        "\u22127: Mill seven cards. Return all non-Aura enchantment cards from your graveyard to the battlefield. Return all Aura cards from your graveyard to the battlefield.",
    # Storm Cauldron: a land tapped for mana is tapped by a player (106.12a); a stack trigger, it adds no mana (so not a mana ability, 605.1b)
    "Whenever a land is tapped for mana, return it to its owner's hand.":
        "Whenever a player taps a land for mana, return that land to its owner's hand.",
    # Xenagos, the Reveler: the same choice, "any number" (the exiled cards are public; 608.2d the controller chooses on resolution)
    "\u22126: Exile the top seven cards of your library. You may put any number of creature and/or land cards from among them onto the battlefield.":
        "\u22126: Exile the top seven cards of your library. Put a creature or land card exiled this way onto the battlefield.",
    # Nacatl War-Pride: "exactly one" = at least one (509.1c requirement) and no more than one (509.1b restriction)
    "~ must be blocked by exactly one creature if able.":
        "~ must be blocked if able and can't be blocked by more than one creature.",
    # Zariel's emblem: the end of the first combat phase (500.8, 511.2) is "at end of combat" while it is the first combat phase of the turn
    "At the end of the first combat phase on your turn, untap target creature you control. After this phase, there is an additional combat phase.":
        "At end of combat on your turn, if it's the first combat phase of the turn, untap target creature you control. "
        "After this phase, there is an additional combat phase.",
}
_ANY_NUMBER = {"\u22126: Exile the top seven cards of your library. You may put any number of creature and/or land cards from among them onto the battlefield."}


ZARA = ("Whenever ~ attacks, look at defending player's hand. You may put a creature card from it onto the battlefield under your control tapped and attacking "
        "that player or a planeswalker they control. Return that creature to its owner's hand at the beginning of the next end step.")
BOUNCE_CHAMBER = ("Whenever you roll to visit your Attractions, return a creature you don't control with the lowest toughness among creatures you don't control to its owner's hand.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    old = scripts.self_text(ability.text, ch.name)
    if old == "The attacking player chooses how each creature blocks each combat.":  # Invasion Plans: 509.1a, read by wave110a_choosers.chooser
        return {"kind": "static", "static": "block_chooser110a", "effects": []}
    if old == ZARA:  # Zara, Renegade Recruiter: look (701.20e), put under your control tapped and attacking (508.4), return it at the next end step
        d = scripts.define(replace(ability, text="Whenever ~ attacks, defending player reveals their hand. You choose a creature card from it."), ch)
        if d is None or [e["do"] for e in d["effects"]] != ["reveal_hand", "choose_from_hand"]:
            return None
        look, pick = d["effects"]
        pick.update(optional=True, **{"as": "zara110a"})
        return {**d, "effects": [{**look, "private": True}, pick, {"do": "enter_chosen110a", "who": "ref:zara110a"},
                                 {"do": "delayed", "when": {"kind": "step", "step": "end", "whose": "next"}, "n": 1}, {"do": "deferred:bounce", "who": "ref:zara110a"}]}
    if old == BOUNCE_CHAMBER:  # Bounce Chamber: the visitor (not each opponent) chooses among the tied lowest-toughness creatures it doesn't control
        from app.rules import selectors

        d = scripts.define(replace(ability, text="Whenever you roll to visit your Attractions, each opponent chooses a creature with the least toughness "
                                                 "among creatures they control. Return it to its owner's hand."), ch)
        sel = selectors.parse("creature you don't control with the lowest toughness among creatures you don't control")
        if d is None or sel is None or d["effects"][0]["do"] != "player_chooses":
            return None
        d["effects"][0].update(who="you", any=True, sel=sel.key(), label="creature with the lowest toughness among creatures you don't control")
        return d
    if old == "Each opponent who cast a spell this turn can't attack with creatures.":  # Angelic Arbiter: 508.1c, the creatures of an opponent who has cast a spell
        from app.rules import selectors

        d = scripts.define(replace(ability, text="Creatures your opponents control can't attack."), ch)
        return None if d is None else {**d, "who": selectors.Selector(types=("Creature",), controller="opponent", extras=("ctrl_cast110a",)).key()}
    if old == "Each opponent who controls more creatures than you can't cast creature spells. The same is true for artifacts and enchantments.":
        return {"kind": "static", "static": "cast_limit", "who": "opponents", "when": None, "filter": None, "from": None, "act": None, "max": None,
                "more110a": ["Creature", "Artifact", "Enchantment"], "effects": []}  # Ward of Bones: 601.3, per type the opponent has more of
    if old == SPLENDOR:  # Sigarda's Splendor: the upkeep trigger reads the life total noted as it entered (wave110a_enter), then notes again
        d = scripts.define(replace(ability, text="At the beginning of your upkeep, draw a card."), ch)
        return None if d is None else {**d, "effects": [{"do": "noted_draw110a", "draw": d["effects"][0]}]}
    if old == "Each opponent who controls more lands than you can't play lands.":  # Ward of Bones: 305.1, read by engine.play_land_problem
        return {"kind": "static", "static": "cant_play_lands", "effects": [], "more110a": ["Land"]}
    if old == "Each opponent who attacked with a creature this turn can't cast spells.":  # Angelic Arbiter: 601.3, an opponent who declared attackers this turn
        d = scripts.define(replace(ability, text="Your opponents can't cast spells."), ch)
        return None if d is None else {**d, "when": "attacked110a"}
    if old == ("Whenever ~ deals combat damage to a player, you may pay {W}{U}{B}{R}{G} if that player has 10 or less life. When you do, that player loses the game."):
        # Ezio: the life test is made on resolution only (it is no intervening "if", 603.4): the leading-"if" reading without its trigger-time test
        d = scripts.define(replace(ability, text="Whenever ~ deals combat damage to a player, if that player has 10 or less life, you may pay {W}{U}{B}{R}{G}. "
                                                 "When you do, that player loses the game."), ch)
        if d is None or "if" not in d:
            return None
        d.pop("if")
        return d
    new = ABILITY_REWRITES.get(old)
    d = None if new is None else scripts.define(replace(ability, text=new), ch)
    if d is not None and old in _ANY_NUMBER:
        for e in d["effects"]:
            if e["do"] == "return_choice":
                e.update(n=99, upto=True)
    return d


def more_of(state: Any, info: Any, src: Any, d: dict[str, Any], player: str, types: Any = None) -> bool:
    """Ward of Bones: ``player`` (an opponent of the source's controller) controls more permanents of one of the d["more110a"] types (limited to
    ``types``, the types of the spell cast) than the source's controller does, counted now (601.3: when the spell is proposed)."""
    from app.rules import characteristics as chars
    from app.rules.layers import derive

    if info is None or player == src.controller:
        return False
    count: dict[str, dict[str, int]] = {player: {}, src.controller: {}}
    for c in state.cards.values():
        if c.zone.endswith(":battlefield") and c.controller in count:
            for t in derive(state, c, chars.of(c, info), info).types:
                count[c.controller][t] = count[c.controller].get(t, 0) + 1
    return any(count[player].get(t, 0) > count[src.controller].get(t, 0) for t in d["more110a"] if types is None or t in types)


def unblocked_turn(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    plan.rules.assign_unblocked_turn[ctx["controller"]] = plan.state.turn.number
    return True


def enter_chosen(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The chosen cards of another player's hand enter under the ability's controller's control, tapped and attacking the defending player or a planeswalker
    they control (110.2, 508.4; ``at`` reads the event's defended player). Not cast (601.1)."""
    from app.rules import attachments, defending, effects, token_grammar

    me = ctx["controller"]
    if (dp := defending.players(plan, ctx)) and isinstance(ctx.get("event"), dict):  # 508.5: before they enter, while the attacker is still attacking
        ctx["event"]["defended"] = dp[0]
    cards = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":hand")]
    if not cards:
        return True
    if not attachments.enter(plan, [{"card": c, "player": me, "actor": me, "tapped": True, "via": ctx.get("source_object")} for c in cards], ctx):
        return False
    effects._remember(plan, ctx, {"as": "zara110a"}, cards)  # (the entered permanents are new objects, 400.7: "that creature" is them)
    return token_grammar.enter_attacking(plan, ctx, cards, {"planeswalkers": True})


PRIMITIVES = {"enter_chosen110a": enter_chosen, "new_blood110a": new_blood, "new_blood_apply110a": new_blood_apply, "wheel110a": wheel, "grant_owned110a": grant_owned, "gambit110a": gambit, "bind_sacrificed110a": bind_sacrificed, "unblocked_turn110a": unblocked_turn, "repeat_put110a": repeat_put, "note_put110a": note_put, "bind110a": bind, "end_combat_phase110a": end_combat_phase, "snow110a": snow,
              "exiled_power_damage110a": exiled_power_damage, "exile_hands110a": exile_hands, "counter_opponents110a": counter_opponents, "noted_draw110a": noted_draw, "exile_until_target110a": exile_until_target}
