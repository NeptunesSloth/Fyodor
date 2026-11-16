"""-- planechase playtest planes (wave G1) -- the lines of the playtest planes ("punk") that are defined in rules terms, each read in its exact
Oracle wording (the playbook's cheapest hook): a native rewrite whose definition is checked, then spliced; a small dedicated primitive where
no native one exists. "You" is the planar controller (311.5, 901.6); several face-up planes each work (901.11c). Reminder text has no rules
meaning (207.2a), and an ability word or a flavor word none (207.2c: "Raid —"). The refused lines (outside the game, undefined terms) are
in docs/research/planechase-refused.md.

* Shy Town: "Whenever you planeswalk here and whenever chaos ensues, …" — one ability with two trigger events (603.2: ``multi:planar_to+
  planar_chaos``); the native per-opponent target group (``opponent_group``) gets the counter, and each becomes a Coward too (205.3m).
* Jalira's Show: the same two events; "destroy up to one target creature. When you do, …" — a reflexive trigger (603.12) only when the
  creature was destroyed (701.8: moved to its owner's graveyard by the destroy, the engine's "destroyed" event — not when there was no target,
  or it was indestructible or regenerated); "its controller" is the destroyed creature's controller as it last existed (608.2h).
* Pursued by Something: "exile target creature. If it's an instant or sorcery, cast it …" — the exiled card is read as it is in exile (a
  face-down creature is turned face up there, 708.9): an instant or sorcery card is cast without paying its mana cost — a mandatory
  instruction (608.2g, "cast", not "you may cast": the choice is required while it can be cast); otherwise it returns under its owner's control.
* The Bean: "each player chooses a creature they control and creates a token that's a copy of it, except it's a Reflection …" — in turn order
  (101.4) each chooses (a choice, not a target), then each creates the copy (707.9b); chaos: you choose one of yours (not a target).
* Tarnation: "Whenever a player commits a crime, they may draw a card." — the committer (700.13) chooses and draws.
* Welcome to Valley (chaos): "except it's a 1/1" — base power and toughness 1/1 (707.9b).
* Sorin's Remastered Manor (line 1): "at the beginning your upkeep" (sic) — the only reading: your upkeep; a spooky counter is any counter
  name (122.1).
* Circus of the Sun (line 1): "Whenever you planeswalk here or at the beginning of your upkeep" — the same two trigger events as "and" (603.2).
* Black Lotus Lounge (chaos): "each player draws a card for each artifact token they control." — each number read for its player, all
  before the first draw (608.2h), the draws in turn order (121.2c).
* City Hall (chaos): "treasure" (sic, the predefined Treasure token, 111.10a) — Willie Lumpkin's native "Each player who does can't attack
  you during their next turn".
* Game Knights Live (chaos): "commanders you control can't be blocked this turn and gain "…" until end of turn".
* The Windy City (chaos): "exile target creature with flying. For as long as it remains exiled, its owner may cast it by paying {2} rather
  than paying its mana cost." — an alternative cost (118.9), the permission following that exiled object (400.7h: ``Permission.alt_mana``,
  airbend's mechanism, 701.65a — but it is no airbend: nothing "airbends").
* Mojave Desert (line 1): the native per-player search ("basic land and/or Desert", tapped); then each player under whose control a Desert
  entered by it creates a 1/1 black Snake with deathtouch (the Desert objects on the battlefield before the search are remembered in the
  resolution's context; one Snake per player, "a Desert").
* Raiders' Allegiance: point counters are player counters (122.1); "for each player dealt combat damage this turn" — the turn's log (120.3);
  planeswalking away (701.31d): each player with the most point counters or tied for the most — every player when nobody has any (all tied
  at 0) — creates three Treasures and draws three cards, then all point counters are removed; chaos: proliferate once for each Pirate you
  control (the number read as it resolves, 608.2h).
* Bicycle Rack (chaos): "Until end of turn, creatures you control have "This creature gets +1/+1 for each card you've discarded this turn."" —
  the creatures you control as it resolves (611.2c) gain the static ability; its "you" is that creature's controller.
* The Command Zone: line 1 — each player who controls a commander they own draws a card (in turn order, 121.2c), then each other player may put
  their commander (a commander card they own) from the command zone onto the battlefield; line 3 — every count of casts from the command zone
  becomes 0: the 903.8 effect is the tax ({2} per previous cast), reset through the table's ``commander_tax`` action (replayed and saved);
  ``PlayerState.commander_casts`` is a display tally no rule reads, left as it is.
* Ghirapur Grand Prix (line 3): "each player with the highest speed among players" — 702.179f: a player with no speed has speed 0 for an
  effect that refers to it, so with nobody faster every player is tied (and creates three Treasures).
"""

from __future__ import annotations

import copy
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

Def = dict[str, Any]
BOTH = "multi:planar_to+planar_chaos"  # 603.2: one ability, two trigger events

SHY = ("Whenever you planeswalk here and whenever chaos ensues, for each opponent, put a shy counter on up to one target creature they control. That "
       "creature becomes a Coward in addition to its other types.")
JALIRA = ("Whenever you planeswalk here or chaos ensues, destroy up to one target creature. When you do, its controller reveals cards from the top of "
          "their library until they reveal a creature card. The player puts that card onto the battlefield, then puts the rest on the bottom of their "
          "library in a random order.")
PURSUED = ("Whenever Chaos ensues, exile target creature. If it's an instant or sorcery, cast it without paying its mana cost. Otherwise put it onto the "
           "battlefield under its owner's control.")
BEAN_TO = ("When you planeswalk here, each player chooses a creature they control and creates a token that's a copy of it, except it's a Reflection in "
           "addition to its other types.")
BEAN_CHAOS = ("Whenever chaos ensues, create a token that's a copy of a creature you control, except it's a Reflection in addition to its other "
              "types.")
TARNATION = "Whenever a player commits a crime, they may draw a card."
WELCOME = "Whenever Chaos ensues, create a token that's a copy of target creature you control, except it's a 1/1."
SORIN = "When you planeswalk here and at the beginning your upkeep, put a spooky counter on target creature you control."
CIRCUS = ("Whenever you planeswalk here or at the beginning of your upkeep, create two 1/1 red performer creature tokens with flying and haste.")
LOTUS = "Whenever Chaos ensues, each player draws a card for each artifact token they control."
CITY = ("Whenever Chaos ensues, each player may create two tapped treasure tokens. Each player who does can't attack you during their next turn.")
KNIGHTS = ('Whenever chaos ensues, commanders you control can\'t be blocked this turn and gain "Whenever this creature deals combat damage to a '
           'player, draw a card" until end of turn.')
WINDY = ("Whenever chaos ensues, exile target creature with flying. For as long as it remains exiled, its owner may cast it by paying {2} rather than "
         "paying its mana cost.")
MOJAVE = ("Whenever you planeswalk here, each player searches their library for up to two basic land or Desert cards and puts them onto the battlefield "
          "tapped, then shuffles their library. If a Desert entered the battlefield under a player's control this way, they create a 1/1 black Snake "
          "creature token with deathtouch.")
RAID = ("At the beginning of your second main phase, for each player dealt combat damage this turn, you get a point counter and create a 2/2 black "
        "Pirate creature token with menace.")
RAIDERS_FROM = ("Whenever you planeswalk away from here, each player with the most point counters or tied for the most point counters creates three "
                "Treasure tokens and draws three cards. Then remove all point counters from each player.")
RAIDERS_CHAOS = "Whenever Chaos ensues, proliferate for each Pirate you control."
BICYCLE = 'Until end of turn, creatures you control have "This creature gets +1/+1 for each card you\'ve discarded this turn."'
COMMAND_TO = ("When you planeswalk here, each player who controls their commander draws a card. Other players may put their commander from the "
              "command zone onto the battlefield.")
COMMAND_CHAOS = "Whenever chaos ensues, the number of times each commander has been cast from the command zone becomes 0."
GHIRAPUR = ("When you planeswalk away from Ghirapur Grand Prix, each player with the highest speed among players creates three Treasure tokens.")

_RAID_WORD = "Raid — "
_CHAOS_SHORT = re.compile(r"^(?:Chaos: |Whenever chaos ensues, )(?P<body>.+)$")
_TREASURES = "When you planeswalk away from {name}, each player creates three Treasure tokens."


def _planar(ch: Characteristics) -> bool:
    from app.rules import planar

    return planar.planar(ch)


def _native(ability: AbilityText, ch: Characteristics, text: str, kind: str = "triggered") -> Def | None:
    from app.rules import scripts

    d = scripts.define(replace(ability, text=text, kind=kind), ch)  # type: ignore[arg-type]
    return copy.deepcopy(d) if d is not None else None


def _does(d: Def | None, *names: str) -> bool:
    return d is not None and [e.get("do") for e in d.get("effects") or []] == list(names)


def _shell(ability: AbilityText, ch: Characteristics, header: str) -> Def | None:
    """The trigger of ``header`` ("Whenever chaos ensues", "When you planeswalk here", …) with a placeholder body, its effects to be replaced."""
    d = _native(ability, ch, f"{header}, you gain 1 life.")
    return d if _does(d, "gain_life") else None


def _bicycle(text: str) -> bool:
    m = _CHAOS_SHORT.match(text)
    return m is not None and m["body"][:1].upper() + m["body"][1:] == BICYCLE


def _treasure(ability: AbilityText, ch: Characteristics) -> Def | None:
    d = _native(ability, ch, _TREASURES.format(name=ch.name))
    return d["effects"][0]["token"] if d is not None and _does(d, "create_token") else None


def definition(ability: AbilityText, ch: Characteristics) -> Def | None:  # noqa: C901 -- one exact wording per branch
    """A playtest plane's line in one of the wordings of the module docstring; else None."""
    if not _planar(ch):
        return None
    text = ability.text.strip()
    if text.startswith(_RAID_WORD):
        text = text[len(_RAID_WORD):]  # 207.2c
    if text == SHY:
        d = _native(ability, ch, "When you planeswalk here, for each opponent, put a shy counter on up to one target creature that player controls.")
        if d is None or not _does(d, "add_counters") or not (d.get("targets") or [{}])[0].get("opponent_group"):
            return None
        return {**d, "trigger": BOTH, "effects": [*d["effects"], {"do": "become", "who": "target:0", "types": [], "retain": True,
                                                                  "add_creature_types": ["Coward"], "duration": "permanent"}]}
    if text == JALIRA:
        d = _native(ability, ch, "Whenever chaos ensues, destroy up to one target creature. Its controller reveals cards from the top of their library "
                                 "until they reveal a creature card. That player puts that card onto the battlefield, then puts the rest on the bottom "
                                 "of their library in a random order.")
        if d is None or not _does(d, "destroy", "look_top", "pick_looked", "rest_looked") or d["effects"][0].get("as") != "e0":
            return None
        destroy, look, pick, rest = d["effects"]
        if look.get("player") != "ref:e0.controller":
            return None
        ability_def = {"kind": "triggered", "trigger": "reflexive", "optional": False, "target": None,
                       "effects": [{**look, "player": "ref:event.controller"}, pick, rest]}
        return {**d, "trigger": BOTH, "effects": [destroy, {"do": "jalira_g1", "ref": "e0", "ability": ability_def}]}
    if text == PURSUED:
        d = _native(ability, ch, "Whenever chaos ensues, exile target creature. If it's an instant or sorcery card, you may cast it without paying its "
                                 "mana cost. Otherwise, return it to the battlefield under its owner's control.")
        if d is None or not _does(d, "exile", "only_if", "free_cast", "only_if", "return_card"):
            return None
        effects = d["effects"]
        effects[2] = {**effects[2], "optional": False, "required": True}  # "cast it": not "you may" (608.2g)
        return d
    if text == BEAN_TO:
        d = _shell(ability, ch, "When you planeswalk here")
        return {**d, "effects": [{"do": "bean_g1"}]} if d is not None and d.get("trigger") == "planar_to" else None
    if text == BEAN_CHAOS:
        d = _native(ability, ch, "Whenever chaos ensues, choose a creature you control. Create a token that's a copy of it, except it's a Reflection "
                                 "in addition to its other types.")
        return d if d is not None and _does(d, "player_chooses", "token_copy") and d.get("trigger") == "planar_chaos" else None
    if text == TARNATION:
        d = _native(ability, ch, "Whenever a player commits a crime, that player may draw a card.")
        return d if d is not None and (d.get("cond") or {}).get("event") == "commit_crime" and (d.get("cond") or {}).get("player") == "any" else None
    if text == WELCOME:
        d = _native(ability, ch, "Whenever chaos ensues, create a token that's a copy of target creature you control, except it's 1/1.")
        return d if d is not None and _does(d, "token_copy") and d["effects"][0].get("excepts") == [{"power": "1", "toughness": "1"}] else None
    if text == SORIN:
        d = _native(ability, ch, "When you planeswalk here and at the beginning of your upkeep, put a spooky counter on target creature you control.")
        return d if d is not None and _does(d, "add_counters") and d.get("trigger") == "multi:planar_to+upkeep_you" else None
    if text == CIRCUS:
        d = _native(ability, ch, "When you planeswalk here and at the beginning of your upkeep, create two 1/1 red Performer creature tokens with "
                                 "flying and haste.")
        return d if d is not None and _does(d, "create_token") and d.get("trigger") == "multi:planar_to+upkeep_you" else None
    if text == LOTUS:
        from app.rules import values

        d = _shell(ability, ch, "Whenever chaos ensues")
        n = values.parse_count("the number of artifact tokens you control")
        if d is None or n is None:
            return None
        return {**d, "effects": [{"do": "draw", "who": "each_player", "n": {"per_player": n}}]}  # (sized_damage.PER_PLAYER: each their own)
    if text == CITY:
        d = _native(ability, ch, "Whenever chaos ensues, each player may create two tapped Treasure tokens. Each player who does can't attack you "
                                 "during their next turn.")
        return d if d is not None and _does(d, "each_may") and d["effects"][0].get("then") else None
    if text == KNIGHTS:
        a = _native(ability, ch, "Whenever chaos ensues, commanders you control can't be blocked this turn.")
        b = _native(ability, ch, 'Whenever chaos ensues, until end of turn, commanders you control gain "Whenever this creature deals combat damage '
                                 'to a player, draw a card."')
        if a is None or b is None or not _does(a, "restrict") or not _does(b, "grant"):
            return None
        return {**a, "effects": [*a["effects"], *b["effects"]]}
    if text == WINDY:
        d = _native(ability, ch, "Whenever chaos ensues, exile target creature with flying.")
        if d is None or not _does(d, "exile"):
            return None
        return {**d, "effects": [{**d["effects"][0], "as": "e0"}, {"do": "windy_g1", "ref": "e0"}]}
    if text == MOJAVE:
        d = _native(ability, ch, "When you planeswalk here, each player searches their library for up to two basic land and/or Desert cards, puts them "
                                 "onto the battlefield tapped, then shuffles.")
        snake = _native(ability, ch, "When you planeswalk here, create a 1/1 black Snake creature token with deathtouch.")
        if d is None or snake is None or not _does(d, "search") or not _does(snake, "create_token"):
            return None
        from app.rules import selectors

        # (the native "basic land and/or Desert" reads "basic (land or Desert)": each card is a basic land card or a Desert card, either branch)
        base = selectors.from_key(d["effects"][0]["sel"])
        if base.supertypes != ("Basic",) or base.types != ("Land",) or base.subtypes != ("Desert",) or not base.union:
            return None
        basic = replace(base, subtypes=(), union=False)
        desert = replace(base, supertypes=(), types=(), union=False)
        either = replace(base, supertypes=(), types=(), subtypes=(), union=False, either=(basic.key(), desert.key()))
        search = {**d["effects"][0], "sel": either.key(), "label": "basic land or Desert cards"}
        return {**d, "effects": [{"do": "mojave_g1", "step": "before"}, search, {"do": "mojave_g1", "step": "after",
                                                                                       "token": snake["effects"][0]["token"]}]}
    if text == RAID:
        d = _native(ability, ch, "At the beginning of your second main phase, create X 2/2 black Pirate creature tokens with menace, where X is the "
                                 "number of players who were dealt combat damage this turn.")
        if d is None or not _does(d, "create_token") or d.get("trigger") != "step:main2:you":
            return None
        n = d["effects"][0]["n"]
        return {**d, "effects": [{"do": "player_counter", "who": "you", "counter": "point", "n": n}, *d["effects"]]}
    if text == RAIDERS_FROM:
        d = _shell(ability, ch, "When you planeswalk away from Raiders' Allegiance")
        token = _treasure(ability, ch)
        if d is None or token is None or d.get("trigger") != "planar_from":
            return None
        return {**d, "effects": [{"do": "raiders_g1", "token": token}]}
    if text == RAIDERS_CHAOS:
        d = _native(ability, ch, "Whenever chaos ensues, proliferate X times, where X is the number of Pirates you control.")
        return d if _does(d, "repeat", "proliferate") else None
    if _bicycle(text):
        d = _native(ability, ch, 'Whenever chaos ensues, until end of turn, creatures you control gain "Whenever this creature deals combat damage to '
                                 'a player, draw a card."')
        if d is None or not _does(d, "grant"):
            return None
        return {**d, "effects": [{**d["effects"][0], "abilities": ["~ gets +1/+1 for each card you've discarded this turn."]}]}
    if text == COMMAND_TO:
        d = _shell(ability, ch, "When you planeswalk here")
        return {**d, "effects": [{"do": "command_zone_g1"}]} if d is not None and d.get("trigger") == "planar_to" else None
    if text == COMMAND_CHAOS:
        d = _shell(ability, ch, "Whenever chaos ensues")
        return {**d, "effects": [{"do": "command_tax_g1"}]} if d is not None and d.get("trigger") == "planar_chaos" else None
    if text == GHIRAPUR:
        d = _shell(ability, ch, "When you planeswalk away from Ghirapur Grand Prix")
        token = _treasure(ability, ch)
        if d is None or token is None or d.get("trigger") != "planar_from":
            return None
        return {**d, "effects": [{"do": "ghirapur_g1", "token": token}]}
    return None


# -- helpers ---------------------------------------------------------------------------------------------------------------------------
def _insert(ctx: dict[str, Any], added: list[Def]) -> None:
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]


def _ask(plan: Plan, ctx: dict[str, Any], player: str, prompt: str, cards: list[str], resume: dict[str, Any], *, lo: int, hi: int) -> None:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=player, kind="choose_cards", prompt=f"{ctx.get('name') or 'Choose'}: {prompt}",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in cards],
           min_choices=lo, max_choices=hi, resume={"ctx": ctx, **resume})


def _creatures(plan: Plan, pid: str) -> list[str]:
    return [c.id for c in plan.state.cards.values() if c.zone == f"{pid}:battlefield" and c.controller == pid and plan.ch(c).is_creature]


def _tokens(token: Def, pid: str, n: int) -> Def:
    return {"do": "create_token", "who": f"player:{pid}", "n": n, "token": token}


# -- The Bean: each player chooses a creature they control, then each creates a Reflection copy of it ------------------------------------------
def bean(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    return _bean(plan, ctx, list(plan.apnap()), [])


def _bean(plan: Plan, ctx: dict[str, Any], who: list[str], picks: list[list[str]]) -> bool:
    from app.rules import context

    while who:
        pid, who = who[0], who[1:]
        cards = _creatures(plan, pid)
        if len(cards) == 1:
            picks = [*picks, [pid, cards[0]]]
            plan.note(f"{plan.name(pid)} chooses {plan.state.cards[cards[0]].name} (no choice)", cards, actor=pid)
        elif cards:
            _ask(plan, ctx, pid, "choose a creature you control", cards, {"step": "bean_g1", "who": who, "picks": picks}, lo=1, hi=1)
            return False
    added: list[Def] = []
    for i, (pid, cid) in enumerate(picks):
        context.bind_objects(plan, ctx, f"bean_g1_{i}", [cid])
        added.append({"do": "token_copy", "n": 1, "excepts": [{"add_subtypes": ["Reflection"]}], "who": f"ref:bean_g1_{i}", "creator": f"player:{pid}"})
    _insert(ctx, added)
    return True


def _resume_bean(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    picks = [*r["picks"], [d.player, chosen[0]]] if chosen else r["picks"]
    if chosen:
        plan.note(f"{plan.name(d.player)} chooses {plan.state.cards[chosen[0]].name}", chosen, actor=d.player)
    if _bean(plan, r["ctx"], r["who"], picks):
        effects.continue_effects(plan, r["ctx"])


# -- Jalira's Show: "When you do" — only for a creature the destroy destroyed --------------------------------------------------------------
def jalira(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    from app.rules import context, effects

    b = context.refs(ctx).get(e["ref"]) or {}
    was = {str(r.get("object_id")) for r in [*(b.get("was") or []), *(b.get("objects") or [])]}  # (rebound after the move: "was" is the permanent)
    r = plan.rules
    if not was or not any(ev.kind == "designation" and ev.counter == "destroyed" and ev.object_id in was for ev in r.events):
        plan.note("Nothing was destroyed: the reflexive ability doesn't trigger (603.12)")
        return True
    context.refs(ctx)["jalira_g1"] = {"kind": "payment", "ok": True}
    return effects.reflexive(plan, ctx, {"do": "reflexive", "cond": {"succeeded": "jalira_g1"}, "lki": e["ref"], "ability": e["ability"]})


# -- The Windy City: its owner may cast it from exile for {2} --------------------------------------------------------------------------------
def windy(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    import secrets

    from app.game.rules_state import Permission
    from app.rules import context

    for ref in (context.refs(ctx).get(e["ref"]) or {}).get("objects") or []:
        card = plan.state.cards.get(str(ref.get("card")))
        if card is None or card.is_token or not card.zone.endswith(":exile"):
            continue  # (a token ceases to exist, 111.7; a commander sent to the command zone, 903.9b, is not exiled)
        plan.rules.permissions.append(Permission(
            id=secrets.token_hex(4), player=card.owner, cast=True, zone="exile", object_id=plan.oid(card), card=card.id, until="permanent",
            turn=plan.state.turn.number, alt_mana="{2}", source=ctx.get("source_object"),
            label=f"{card.name}: cast it from exile for {{2}} (The Windy City)"))
        plan.note(f"{plan.name(card.owner)} may cast {card.name} from exile for {{2}}", [card.id])
    return True


# -- Mojave Desert: a Snake for each player a Desert entered for --------------------------------------------------------------------------
def _deserts(plan: Plan) -> dict[str, str]:
    return {c.id: plan.oid(c) for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and "Desert" in plan.ch(c).subtypes}


def mojave(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    if e["step"] == "before":
        ctx["mojave_g1"] = _deserts(plan)
        return True
    before = ctx.pop("mojave_g1", None) or {}
    new = [cid for cid, oid in _deserts(plan).items() if before.get(cid) != oid]
    who = {plan.state.cards[c].controller for c in new}
    _insert(ctx, [_tokens(e["token"], p, 1) for p in plan.apnap() if p in who])
    return True


# -- Raiders' Allegiance: the most point counters --------------------------------------------------------------------------------------------
def raiders(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    live = list(plan.apnap())
    counts = {p: int(plan.state.players[p].resources.get("point", 0)) for p in live}
    most = max(counts.values(), default=0)
    added: list[Def] = []
    for p in live:
        if counts[p] == most:
            added += [_tokens(e["token"], p, 3), {"do": "draw", "who": f"player:{p}", "n": 3}]
    _insert(ctx, [*added, {"do": "raiders_clear_g1"}])
    return True


def raiders_clear(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    for pid, p in plan.state.players.items():
        if have := int(p.resources.get("point", 0)):  # (a removal through the table's action: replayed and saved like any other)
            plan.do({"type": "resource", "player": pid, "key": "point", "delta": -have}, actor=ctx["controller"])
    return True


# -- Ghirapur Grand Prix: the highest speed ---------------------------------------------------------------------------------------------------
def ghirapur(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    from app.rules import speed

    live = list(plan.apnap())
    speeds = {p: speed.of(plan, p) for p in live}  # 702.179f: no speed is 0
    top = max(speeds.values(), default=0)
    _insert(ctx, [_tokens(e["token"], p, 3) for p in live if speeds[p] == top])
    return True


# -- The Command Zone ------------------------------------------------------------------------------------------------------------------------
def _commanders(plan: Plan, pid: str, zone: str) -> list[str]:
    return [c.id for c in plan.state.cards.values() if c.owner == pid and c.commander_key and c.zone == f"{pid}:{zone}"
            and (zone != "battlefield" or c.controller == pid)]


def command_zone(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    live = list(plan.apnap())
    controls = [p for p in live if _commanders(plan, p, "battlefield")]
    _insert(ctx, [*({"do": "draw", "who": f"player:{p}", "n": 1} for p in controls),
                  {"do": "command_put_g1", "who": [p for p in live if p not in controls]}])
    return True


def command_put(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    return _put(plan, ctx, list(e.get("who") or []))


def _put(plan: Plan, ctx: dict[str, Any], who: list[str]) -> bool:
    while who:
        pid, who = who[0], who[1:]
        if pid not in plan.live():
            continue
        cards = _commanders(plan, pid, "command")
        if cards:
            _ask(plan, ctx, pid, "you may put your commander from the command zone onto the battlefield", cards,
                 {"step": "command_put_g1", "who": who}, lo=0, hi=len(cards))
            return False
    return True


def _resume_put(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    if chosen:
        plan.do({"type": "move", "card_ids": chosen, "to": {"player": d.player, "zone": "battlefield"}}, actor=d.player)
    if _put(plan, r["ctx"], r["who"]):
        effects.continue_effects(plan, r["ctx"])


def command_tax(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """903.8: the commander tax is {2} for each previous cast from the command zone; each count becomes 0, so each tax does (the table's
    ``commander_tax`` action, replayed and saved like any other)."""
    for p in plan.state.players.values():
        for key, tax in list(p.commander_tax.items()):
            if tax:
                plan.do({"type": "commander_tax", "commander": key, "value": 0}, actor=p.id)
    plan.note("The number of times each commander has been cast from the command zone becomes 0")
    return True


PRIMITIVES: dict[str, Any] = {"bean_g1": bean, "jalira_g1": jalira, "windy_g1": windy, "mojave_g1": mojave, "raiders_g1": raiders,
                              "raiders_clear_g1": raiders_clear, "ghirapur_g1": ghirapur, "command_zone_g1": command_zone,
                              "command_put_g1": command_put, "command_tax_g1": command_tax}
RESUME: dict[str, Any] = {"bean_g1": _resume_bean, "command_put_g1": _resume_put}
