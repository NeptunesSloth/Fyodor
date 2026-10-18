# -- random choices (wave 47B) --
"""Random choices: "Choose an opponent at random." (Vial Smasher, Ruhan of the Fomori), "… an opponent chosen at random" (Zaffai), "Choose a creature at
random" (Last One Standing), "reveals a card at random from their hand" (Ignite Memories, Nebuchadnezzar). Researched against CR 2026-09-25 and the
rulings (Vial Smasher the Fierce 2020-11-10, Scab-Clan Giant 2013-04-15, Indoraptor 2023-11-10).

* The Comprehensive Rules have no rule for "at random": nobody chooses, the game picks without bias, while the ability resolves (Vial Smasher ruling),
  from the players still in the game (800.4a); with one opponent left that opponent is it.
* The pick comes from the table's entropy source (plan.rng, as dice and coin flips) and is recorded: the player or object lands in the resolution
  context (a decision's resume, the saved rules state) and every instruction after it is a recorded step, so a replay or a load never draws again.
* Public things (players, the battlefield, graveyards): the pick is logged. A hand is hidden: ``reveal_random`` shows only the cards picked, to
  everyone (701.20a) or to the looker alone (701.20e), and hides them again when the resolution ends (effects.hide_revealed); nothing about the
  cards left is asked, logged or shown. A pick among hidden cards that isn't revealed afterwards is not read.
* "Choose an opponent at random. ~ deals damage … to that player or a planeswalker that player controls." (Vial Smasher): after the pick,
  its controller chooses the player or one of that player's planeswalkers (ruling); no player may act between the two.
* "target … chosen at random" is a target group flagged ``random`` (language.target_group; targets.choose_groups picks it as the targets are chosen,
  601.2c, and reads nothing the caller sent); only an ability's single group is read (coverage.definition_supported).

Not read (manual): "didn't attack during your last combat" (Territorial Hellkite), a pick among modes of a Saga chapter, "choose 1, 2 or 3 at random".
"""

from __future__ import annotations

import json
import re
import secrets
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules import context
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_CLAUSE = re.compile(r"choose (?P<w>an opponent|a player) at random")
_OBJECT = re.compile(r"choose (?:a|an) (?P<w>[\w -]+?) at random(?: (?P<z>in your graveyard))?")
_DAMAGE_AT_RANDOM = re.compile(r"(?P<s>~|[Ii]t) deals (?P<n>\d+) damage to a (?P<w>creature(?: an opponent controls| you control)?) chosen at random")
_DISCARD_REVEALED = re.compile(r"(?:then )?that player discards (?:all|each) (?P<what>[\w -]+?) revealed this way")
_REVEAL = re.compile(r"(?:(?P<s>.+?) )?reveals? (?P<n>a|one|two|three|X|\d+) cards? at random (?:from|in) (?:their|your|that player's) hand")
_LOOK = re.compile(r"look at (?P<n>a) card at random in (?P<s>target (?:player|opponent))'s hand")
_OR_PW = re.compile(r"(?<=\. )(?P<d>[^.]*?) to that player or a planeswalker that player controls\.")
INLINE = "random_opponent"  # the group token of "an opponent chosen at random" (scripts: post() makes it a pick and a binding)


def clause(text: str) -> tuple[list[dict[str, Any]], None] | None:
    """"choose an opponent at random" / "choose a player at random" (one instruction, no final period)."""
    m = _CLAUSE.fullmatch(text)
    return None if m is None else ([{"do": "choose_random", "pool": "opponent" if m["w"] == "an opponent" else "player"}], None)


def object_clause(text: str) -> tuple[list[dict[str, Any]], None] | None:
    """"Choose a creature at random" / "choose a creature an opponent controls at random" / "choose a card at random in your graveyard": one object of a
    public zone (the battlefield, a graveyard), the table's pick; the instructions after it name it ("that creature", "it", "the rest")."""
    from app.rules import selectors

    m = _OBJECT.fullmatch(text)
    if m is None or m["w"].split()[0] in ("opponent", "player"):
        return None
    sel = selectors.parse(f"{m['w']} in your graveyard" if m["z"] else m["w"])
    if sel is None or sel.player is not None or sel.zones not in ((), ("battlefield",), ("graveyard",)) or sel.ability is not None:
        return None  # (a hidden zone, or not a plain object phrase: the pick would be among cards nobody has seen, or isn't one)
    return [{"do": "choose_random_object", "sel": sel.key()}], None


def discard_revealed_clause(text: str) -> tuple[list[dict[str, Any]], None] | None:
    """"Then that player discards all cards with that name revealed this way." (Nebuchadnezzar): those of the cards just revealed at random that match
    ("with that name": the name chosen earlier in the same resolution, chosen.bind_effects), from the hand they are in (701.9a)."""
    from app.rules import selectors

    m = _DISCARD_REVEALED.fullmatch(text)
    sel = selectors.parse(m["what"].replace("cards", "card")) if m is not None else None
    return None if sel is None or sel.zones not in ((), ("hand",)) else ([{"do": "discard_revealed", "sel": sel.key()}], None)


def reveal_clause(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    """"Target player reveals a card at random from their hand" (Ignite Memories, Friendly Fire, Singe-Mind Ogre, Merfolk Spy), "Reveal two cards at
    random from your hand" (Rise // Fall), "Look at a card at random in target player's hand" (Urza's Bauble): the cards are revealed to everyone
    (701.20a), or to the looker alone (701.20e); the later instructions read them as "that card"."""
    from app.rules import language
    from app.rules.values import NUMBERS

    m = _REVEAL.fullmatch(text) or _LOOK.fullmatch(text)
    if m is None:
        return None
    n: Any = {"x": 1} if m["n"] == "X" else int(m["n"]) if m["n"].isdigit() else 1 if m["n"] in ("a", "one") else NUMBERS.get(m["n"])
    try:
        kind, key, group = language.ref(m["s"] or "you")
    except language._Fail:
        return None
    if kind not in ("target", "players") or (kind == "players" and key not in ("you", "that_player")):
        return None
    return [{"do": "reveal_random", "who": language._who(kind, key), "n": n, **({"private": True} if text.startswith("look") else {})}], \
        language._one(group)


def strip_pw(body: str) -> tuple[str, str]:
    """"Choose an opponent at random. ~ deals N damage to that player or a planeswalker that player controls." (Vial Smasher): the
    sentence read as "… to that player." and the pick marked (``post(pw=True)``) to be followed by the controller's choice."""
    body = _DAMAGE_AT_RANDOM.sub(lambda m: f"Choose a {m['w']} at random. ~ deals {m['n']} damage to that creature", body)  # (Cinderheart Giant: not a target, 115.1; "it" is the creature that died)
    body = re.sub(r"(?i)\b(choose a creature at random), then destroy the rest\b", r"\1. Destroy all other creatures", body)  # (Last One Standing)
    body = re.sub(r"\bIf you discard (an? [\w ]+? card) this way\b", r"If you discarded \1 this way", body)  # (the same condition as the past tense: Cragganwick Cremator, Aether Rift)
    if "at random" in body:  # (the sentence as the grammar has it: Skull Rend's "Those players" are the opponents it dealt damage to; Reckless Handling's "shuffle, then discard")
        body = re.sub(r"(deals \d+ damage to each opponent)\. Those players each (discard )", r"\1. Each opponent \2", body)
        body = re.sub(r"(Search your library [^.]*?into your hand), shuffle, then (discard [^.]*\.)", r"\1, then shuffle. \2", body)
    if "opponent chosen at random gains control of" in body:  # (Witch Hunt: the subject of the sentence is the target, picked at random: ``post`` flags the group)
        return re.sub(r"\b([Tt]arget opponent) chosen at random (gains control of )", r"\1 \2", body), "target_random"
    if "at random" in body and "repeat this process" in body:  # (Sin: "exile a permanent card from your graveyard at random, then create a tapped token that's a copy of
        # that card. If the exiled card is a land card, repeat this process.": it is the exiled card that is asked about, not the token ``post`` sets that right)
        new = re.sub(r"\bIf the exiled card is (an? [\w ]+? card), repeat this process\.", r"If that card is \1, repeat this process.", body)
        return new, "exiled" if new != body else ""
    if not re.search(r"(?i)\bchoose (?:an opponent|a player) at random\. ", body):
        return body, ""
    new = _OR_PW.sub(lambda m: f"{m['d']} to that player.", body)
    return new, "pw" if new != body else ""


def post(got: Any, mode: str = "") -> Any:
    """"… to an opponent chosen at random" (the group token ``INLINE`` as an instruction's ``who``): the pick is made right before the
    instruction (inside its "if" gate, if it has one), bound as ``ref:rp<k>``. The token anywhere else keeps the card manual."""
    if got is None:
        return got
    effects = got[0]
    if mode == "pw":  # (the one pick of the ability: ``strip_pw`` found a single sentence)
        picks = [e for e in effects if e.get("do") == "choose_random"]
        if len(picks) != 1:
            return None
        picks[0]["pw"] = True
    if mode == "target_random":
        if not isinstance(got[1], str):
            return None
        got = (effects, [{"what": got[1], "min": 1, "max": 1, "random": True}], got[2])
    if mode == "exiled":  # the condition names the card exiled at random (the first instruction), whatever the pronoun bound to since
        first = effects[0] if effects else {}
        gates = [e for e in effects if e.get("do") == "only_if" and str((e.get("cond") or {}).get("object", "")).startswith("ref:")]
        if first.get("do") != "return_choice" or not first.get("as") or len(gates) != 1:
            return None
        gates[0]["cond"]["object"] = f"ref:{first['as']}"
    from app.rules import selectors

    for i, e in enumerate(effects):  # "Reveal … at random. … discards those": the discard reads the cards the reveal bound
        if e.get("do") == "discard_revealed":
            before = [j for j in range(i) if effects[j].get("do") == "reveal_random"]
            if not before:
                return None
            effects[before[-1]].setdefault("as", f"rv{before[-1]}")
            e["of"] = effects[before[-1]]["as"]
    for i, e in enumerate(effects):  # "Choose a creature at random. … Destroy all other creatures.": the others are the creatures but the one picked
        if e.get("do") == "choose_random_object":
            e.setdefault("as", f"rc{i}")
            for j in range(i + 1, len(effects)):
                who = effects[j].get("who")
                if effects[j].get("do") == "destroy" and isinstance(who, str) and who.startswith("sel:") and selectors.from_key(who).other:
                    effects[j] = {**effects[j], "who": f"except:{e['as']}|{selectors.replace(selectors.from_key(who), other=False).key()}"}
    k = 0
    while k < len(effects):
        if effects[k].get("who") == INLINE:
            effects[k] = {**effects[k], "who": f"ref:rp{k}"}
            effects.insert(k, {"do": "choose_random", "pool": "opponent", "as": f"rp{k}"})
            for j, g in enumerate(effects[:k]):  # (the gate of an "If …, …" now covers one more instruction)
                if g.get("do") == "only_if" and j < k <= j + int(g.get("skip", 0)):
                    g["skip"] = int(g["skip"]) + 1
            k += 1
        k += 1
    return None if INLINE in json.dumps(effects) else got


def discard_revealed(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import characteristics as chars
    from app.rules import selectors
    from app.rules.effects import _discard_next

    sel = selectors.from_key(e["sel"])
    cards = [c for c in context.objects(plan, ctx, e["of"]) if plan.state.cards[c].zone.endswith(":hand")
             and selectors.matches(plan, sel, plan.state.cards[c], chars.of(plan.state.cards[c], plan.info), ctx["controller"])]
    return _discard_next(plan, ctx, 0, [], cards)


def choose_random_object(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The table picks one of the objects the selector matches (a public zone) at random and binds it as ``as``; none matching: nothing is picked."""
    from app.rules import selectors

    found = sorted(selectors.candidates(plan, selectors.from_key(e["sel"]), ctx["controller"], ctx.get("source_card")))
    pick = (plan.rng or secrets.SystemRandom()).choice(found) if found else None
    if pick is not None:
        plan.note(f"{ctx.get('name') or 'It'}: chosen at random →", [pick], actor=ctx["controller"])  # (the card is shown as the log shows any card: a face-down one isn't named)
    if e.get("as"):
        context.bind_objects(plan, ctx, e["as"], [pick] if pick is not None else [])
    return True


def choose_random(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The table picks one player of the pool (an opponent of the controller, or any player) at random and binds it as ``as``."""
    me = ctx["controller"]
    pool = [p for p in plan.live() if e["pool"] == "player" or p != me]
    pick = (plan.rng or secrets.SystemRandom()).choice(pool) if pool else None
    if pick is not None:
        plan.note(f"{ctx.get('name') or 'It'}: {plan.name(pick)} is chosen at random", actor=me)
    if e.get("as"):
        context.bind_players(ctx, e["as"], [pick] if pick is not None else [])
    if e.get("did"):  # ("When you do, …": the pick was made)
        context.bind_payment(ctx, e["did"], pick is not None)
    if pick is not None and e.get("pw") and (walkers := _planeswalkers(plan, pick)):
        decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose {plan.name(pick)} or a planeswalker they control",
               options=[DecisionOption(id=pick, label=plan.name(pick)),
                        *(DecisionOption(id=c, label=plan.state.cards[c].name or "Planeswalker", card_id=c) for c in walkers)],
               resume={"step": "choose_random", "ctx": ctx, "e": e, "pick": pick})
        return False
    return True


def _planeswalkers(plan: Plan, pid: str) -> list[str]:
    return [c.id for c in plan.state.cards.values() if c.zone == f"{pid}:battlefield" and "Planeswalker" in plan.ch(c).types]


def resume_choose_random(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The controller's choice of the player or one of that player's planeswalkers (Vial Smasher ruling 2020-11-10)."""
    from app.rules.effects import continue_effects

    ctx, e, pick = d.resume["ctx"], d.resume["e"], d.resume["pick"]
    if chosen[0] != pick:
        if chosen[0] not in _planeswalkers(plan, pick):
            raise ValueError("not that player's planeswalker")
        context.bind_objects(plan, ctx, e["as"], [chosen[0]])
    plan.note(f"{plan.name(d.player)} chooses {plan.state.cards[chosen[0]].name if chosen[0] != pick else plan.name(pick)}")
    continue_effects(plan, ctx)


def reveal_random(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Each player named reveals N cards of their hand picked at random (fewer if the hand is smaller): the table picks among cards nobody has
    seen, and the only thing anyone learns is the cards picked, shown as they are revealed (to everyone, or the looker alone: ``private``). They
    stay revealed while this resolution needs them and are hidden again after it (effects.hide_revealed)."""
    from app.rules.effects import _amount, _players

    me = ctx["controller"]
    rng = plan.rng or secrets.SystemRandom()
    picked: list[str] = []
    for pid in _players(plan, ctx, e["who"]):
        hand = sorted(plan.state.zones.get(f"{pid}:hand", []))
        mine = rng.sample(hand, min(_amount(plan, ctx, e["n"]), len(hand)))
        if mine:
            plan.do({"type": "reveal", "card_ids": mine, **({"to": [me]} if e.get("private") else {})}, actor=pid if not e.get("private") else me)
        picked += mine
    ctx["revealed"] = [*(ctx.get("revealed") or []), *picked]
    if not ctx.get("hide_queued"):  # (appended in place: the resolver walks the same list)
        ctx["hide_queued"] = True
        ctx["effects"].append({"do": "hide_revealed"})
    if e.get("as"):
        context.bind_objects(plan, ctx, e["as"], picked)
    return True


def pick_most(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- extremes (wave 49C) -- "the player with the most life" (Wild Dogs), "the player who controls the most Wizards" (Thoughtbound Primoc): the one player whose quantity
    (read as "you" of it) is greater than every other player's, bound as ``as`` as this resolves; a tie names no one (the ruling: the player may differ from the one the
    intervening "if" saw as it triggered, 603.4)."""
    from app.rules import values

    got = {p: values.evaluate(plan, {**ctx, "controller": p}, e["value"]) for p in plan.live()}
    top = [p for p, v in got.items() if v == max(got.values())]
    context.bind_players(ctx, e["as"], top if len(top) == 1 else [])
    return True


PRIMITIVES = {"choose_random": choose_random, "choose_random_object": choose_random_object, "reveal_random": reveal_random, "discard_revealed": discard_revealed,
              "pick_most": pick_most}
RESUME: dict[str, Any] = {"choose_random": resume_choose_random}
