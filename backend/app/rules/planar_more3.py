"""-- planechase more 3 (wave F2) -- the remaining lines of a few planes and phenomena, each read in its exact Oracle wording (the playbook's
cheapest hook) and, where no native rule exists, a small dedicated one. Every face-up plane is an object (901.11c: several can be face up,
Spatial Merging; each reader below goes over all of them). "You" is the planar controller (311.5, 901.6). State: ``RulesState.planar_more3_f2``.

Phenomena (an encounter ability, 312.5; then the planar controller planeswalks, 704.6f):

* Caught in a Parallel Universe: in turn order (101.4) each player chooses a creature controlled by the player to their left (``Plan.left``: the
  seat order) — a choice, not a target (608.2d) — then each player creates a token copy of the creature they chose, with menace (707.9b).
* Human—Time Lord Meta-Crisis: in turn order each player chooses one or two creatures they control, the first and then (optionally) the
  second; each creates a token copy of their first, except it isn't legendary (707.9b), then each who chose a second puts +1/+1 counters on
  the token they created equal to that creature's power (as it is then; 608.2h if it is gone).
* Morphic Tide: Warp World's procedure (wave110c_misc ``warp_*``; the rulings 2012-06-01 compare them) with planeswalker cards entering with the
  artifacts, creatures and lands (``morphic_enter_f2``); the library is shuffled by the server (701.24), the reveal is public, the rest go to the
  bottom in an order each owner chooses (401.4).

Planes:

* The Moonbase: "for each opponent, choose up to one target creature card in that player's graveyard. Put those cards onto the battlefield
  face down under your control. They're 2/2 Cyberman artifact creatures." — the native per-opponent target group (opponent_group) with Death in
  Heaven's face-down 2/2 Cyberman entry (708.2a; rulings 2023-10-13: nameless, colorless; turned face up it is the card).
* The Doctor's Childhood Barn: "for each opponent, choose up to one target nonland permanent that opponent controls. Untap those permanents.
  They phase out. They can't phase in for as long as ~ remains face up. When a player planeswalks, those permanents phase in." — the
  objects are recorded (``barn``); in their controller's untap step they don't phase in while that plane is face up (``cant_phase_in``, ruling
  2023-10-13: once it isn't, they phase in there as normal); the next planeswalk (701.31, any player's: the ``from`` event) creates the delayed
  trigger (603.7) that phases them in.
* Ood Sphere: "Noncreature spells have convoke." — the native convoke grant (spell_helper) for every player's spells (``all_f2``).
* Singing Towers of Darillium (chaos): "you may cast a foretold card you own from exile without paying its mana cost this turn." — a
  permission (zone exile, one spell, this turn, free: 118.9) for any card of yours that is foretold (``RulesState.foretold``) as you cast it.
* Two Streams Facility: each player's last choice of green anchor or red waterfall, made as it is planeswalked to and in the first upkeep of the
  game (turn 1: ``first_game_f2``), recorded for this plane object (``streams``; a new object after a planeswalk back has none until its ability
  resolves, 400.7); "may play an additional land" for green anchor players (305.2, ``extra_lands``); "+2/+0 and haste" for the creatures of red
  waterfall players (a grant whose creatures are read through the ``streams_f2`` selector extra); chaos swaps every player's choice.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

Def = dict[str, Any]

STREAMS_LAND = "streams_land_f2"
STATIC_KINDS = frozenset({STREAMS_LAND, "spell_helper"})
MATRIX_TRIGGER = "matrix_play_f2"
TRIGGER_KINDS = frozenset({MATRIX_TRIGGER})
ANCHOR, WATERFALL = "anchor", "waterfall"
_LABELS = {ANCHOR: "green anchor", WATERFALL: "red waterfall"}

CAUGHT = ("When you encounter Caught in a Parallel Universe, each player chooses a creature controlled by the player to their left. Each player "
          "creates a token that's a copy of the creature they chose, except it has menace.")
META = ("When you encounter Human—Time Lord Meta-Crisis, each player chooses one or two creatures they control. Each player creates a token that's "
        "a copy of the first creature they chose, except it isn't legendary. Then each player who chose a second creature puts a number of +1/+1 "
        "counters on the token they created equal to the power of the second creature they chose.")
MORPHIC = ("When you encounter Morphic Tide, each player shuffles all permanents they own into their library, then reveals that many cards from the top "
           "of their library. Each player puts all artifact, creature, land, and planeswalker cards revealed this way onto the battlefield, then does "
           "the same for enchantment cards, then puts all cards revealed this way that weren't put onto the battlefield on the bottom of their library "
           "in any order.")
MOONBASE = ("Whenever chaos ensues, for each opponent, choose up to one target creature card in that player's graveyard. Put those cards onto the "
            "battlefield face down under your control. They're 2/2 Cyberman artifact creatures.")
BARN = ("Whenever chaos ensues, for each opponent, choose up to one target nonland permanent that opponent controls. Untap those permanents. They "
        "phase out. They can't phase in for as long as The Doctor's Childhood Barn remains face up. When a player planeswalks, those permanents "
        "phase in.")
OOD_CONVOKE = "Song of the Ood — Noncreature spells have convoke."
TOWERS = "Whenever chaos ensues, you may cast a foretold card you own from exile without paying its mana cost this turn."
STREAMS_TO = ("Whenever you planeswalk to Two Streams Facility and at the beginning of the first upkeep of the game, each player chooses green anchor "
              "or red waterfall.")
STREAMS_LAND_TEXT = "Each player who last chose green anchor may play an additional land during each of their turns."
STREAMS_PUMP = "Creatures controlled by players who last chose red waterfall get +2/+0 and have haste."
STREAMS_CHAOS = "Whenever chaos ensues, each player who last chose green anchor chooses red waterfall, and vice versa."
SANS_TO = "wHeN YoU pLAnESWalK tO tHIs pLAnE, eACh pLAyER cHoOSeS a nOnBlACk cREaTuRE tHEy cONtrOl. dEsTRoy tHOsE cREatUReS."
SANS_CHAOS = ("wHeNEveR cHoAS EnSUEs, pERfoRm tHe foLLowiNG pROceSs X tiMEs, wHErE X iS tHe nUmBEr oF tImeS yOU'vE roLLeD tHe PlaNAr diE tHIs tuRN. "
              "eAcH oPPonENt LOseS 3 LiFE uNLeSs tHAt pLAyEr sAcRiFicEs A nOnLaND pErManENt OR diSCaRds a cArD.")
OOD_CHAOS = ("Red-Eye — Whenever chaos ensues, for each opponent, goad up to one target creature that opponent controls. Until your next turn, those "
             "creatures can't become tapped unless they're being declared as attackers.")
MATH = ("Whenever a nontoken creature attacks, exile it. Return it to the battlefield under its owner's control tapped and attacking at the "
        "beginning of that player's next declare attackers step.")
MATRIX = ("Whenever you play a land or cast a spell from among cards exiled with The Matrix of Time, that card's owner loses 3 life and exiles the top "
          "card of their library.")


def _planar(ch: Characteristics) -> bool:
    from app.rules import planar

    return planar.planar(ch)


def _native(ability: AbilityText, ch: Characteristics, text: str) -> Def | None:
    from app.rules import scripts

    d = scripts.define(replace(ability, text=text), ch)
    return copy.deepcopy(d) if d is not None else None


def _planar_native(ability: AbilityText, ch: Characteristics, text: str) -> Def | None:
    """A plane's own trigger ("When you encounter ~, …", "Whenever chaos ensues, …") read with a native body."""
    from app.rules import planar

    d = planar.definition(replace(ability, text=text), ch)
    return copy.deepcopy(d) if d is not None else None


def definition(ability: AbilityText, ch: Characteristics) -> Def | None:
    """A plane's or phenomenon's line in one of the wordings of the module docstring; else None."""
    if not _planar(ch):
        return None
    text = ability.text.strip()
    if ability.kind == "static" and text not in (SANS_TO, SANS_CHAOS):  # (sAnS mERcY's odd case: its triggers are read as statics)
        if text == OOD_CONVOKE:  # 207.2c: a flavor word; every player's noncreature spells (not only "you cast")
            d = _native(ability, ch, "Noncreature spells you cast have convoke.")
            return {**d, "all_f2": True} if d is not None and d.get("static") == "spell_helper" and d.get("keyword") == "convoke" else None
        if text == STREAMS_LAND_TEXT:
            return {"kind": "static", "static": STREAMS_LAND, "effects": []}
        if text == STREAMS_PUMP:
            from app.rules import selectors

            d = _native(ability, ch, "Creatures you control get +2/+0 and have haste.")
            if d is None or d.get("static") != "grant" or d.get("p") != 2 or d.get("keywords") != ["haste"]:
                return None
            sel = selectors.from_key(d["who"])
            return {**d, "who": replace(sel, controller=None, extras=(*sel.extras, "streams_f2")).key()}
        return None
    if ability.kind != "triggered" and text not in (SANS_TO, SANS_CHAOS):
        return None
    if text == CAUGHT:
        d = _planar_native(ability, ch, "When you encounter Caught in a Parallel Universe, you gain 1 life.")
        return {**d, "effects": [{"do": "parallel_f2"}]} if d is not None and d.get("trigger") == "planar_encounter" else None
    if text == META:
        d = _planar_native(ability, ch, "When you encounter Human—Time Lord Meta-Crisis, you gain 1 life.")
        return {**d, "effects": [{"do": "meta_f2"}]} if d is not None and d.get("trigger") == "planar_encounter" else None
    if text == MORPHIC:
        d = _planar_native(ability, ch, "When you encounter Morphic Tide, you gain 1 life.")
        if d is None or d.get("trigger") != "planar_encounter":
            return None
        return {**d, "effects": [{"do": "warp_shuffle110c"}, {"do": "morphic_enter_f2", "kinds": "main"}, {"do": "morphic_enter_f2", "kinds": "ench"},
                                 {"do": "warp_bottom110c"}]}
    if text == MOONBASE:
        d = _planar_native(ability, ch, "Whenever chaos ensues, for each opponent, put up to one target creature card from that player's graveyard onto "
                                        "the battlefield under your control.")
        if d is None or [e.get("do") for e in d["effects"]] != ["return_card"] or d["effects"][0].get("under") != "you":
            return None
        return {**d, "effects": [{**d["effects"][0], "face_down": True, "spec": "2/2 Cyberman artifact creature"}]}
    if text == BARN:
        d = _planar_native(ability, ch, "Whenever chaos ensues, for each opponent, untap up to one target nonland permanent that player controls.")
        if d is None or [e.get("do") for e in d["effects"]] != ["untap"]:
            return None
        return {**d, "effects": [*d["effects"], {"do": "barn_f2", "who": d["effects"][0]["who"]}]}
    if text == TOWERS:
        d = _planar_native(ability, ch, "Whenever chaos ensues, you gain 1 life.")
        return {**d, "effects": [{"do": "towers_f2"}]} if d is not None and d.get("trigger") == "planar_chaos" else None
    if text == STREAMS_TO:  # one ability, both trigger events (603.2): the planeswalk to it, and the game's first upkeep (turn 1's)
        d = _native(ability, ch, "At the beginning of each player's upkeep, you gain 1 life.")
        if d is None or d.get("trigger") != "step:upkeep:each":
            return None
        return {**d, "trigger": "multi:planar_to+step:upkeep:each", "first_game_f2": True, "effects": [{"do": "streams_f2", "how": "choose"}]}
    if text == SANS_TO:  # sAnS mERcY (its case is flavor: the words are the native ones; "this plane" is ~)
        d = _planar_native(replace(ability, kind="triggered"), ch, "When you planeswalk to this plane, each player chooses a nonblack creature they "
                                                                  "control. Destroy those creatures.")
        return d if d is not None and d.get("trigger") == "planar_to" else None
    if text == SANS_CHAOS:  # "cHoAS EnSUEs" (sic: chaos ensues, 311.7); Torment of Hailfire's process, X = the planar die rolls this turn
        d = _planar_native(replace(ability, kind="triggered"), ch, "Whenever chaos ensues, each opponent loses 3 life unless that player sacrifices a "
                                                                   "nonland permanent of their choice or discards a card.")
        if d is None or d.get("trigger") != "planar_chaos" or [e.get("do") for e in d["effects"]] != ["each_may"]:
            return None
        return {**d, "effects": [{"do": "mercy_f2", "process": d["effects"][0]}]}
    if text == OOD_CHAOS:  # 207.2c: an ability word; goad (701.15) and a restriction on becoming tapped until the planar controller's next turn
        d = _planar_native(ability, ch, "Whenever chaos ensues, for each opponent, goad up to one target creature that player controls.")
        if d is None or [e.get("do") for e in d["effects"]] != ["goad"]:
            return None
        return {**d, "effects": [*d["effects"], {"do": "ood_f2", "who": d["effects"][0]["who"]}]}
    if text == MATH:  # Math is for Blockers: the native exile and delayed return (603.7), at the owner's next declare attackers step (508.4:
        # put onto the battlefield attacking, after attackers are declared; never "declared" as one)
        d = _native(ability, ch, "Whenever a nontoken creature attacks, exile it. Return it to the battlefield under its owner's control at the "
                                 "beginning of that player's next end step.")
        if d is None or [e.get("do") for e in d["effects"]] != ["exile", "delayed", "deferred:return_card"] or d["effects"][1]["when"].get("whose") != "owner":
            return None
        exile, later, back = d["effects"]
        return {**d, "effects": [exile, {**later, "when": {**later["when"], "step": "declare_attackers"}}, {**back, "tapped": True, "attacking": True}]}
    if text == MATRIX:  # (``on_events`` puts it on the waiting list; the card exiled is linked to this plane's "cards exiled with ~", 607.2a)
        return {"kind": "triggered", "trigger": MATRIX_TRIGGER, "optional": False, "target": None,
                "effects": [{"do": "lose_life", "who": "ref:event.owner", "n": 3}, {"do": "exile_top", "player": "ref:event.owner", "n": 1, "link": True}]}
    if text == STREAMS_CHAOS:
        d = _planar_native(ability, ch, "Whenever chaos ensues, you gain 1 life.")
        return {**d, "effects": [{"do": "streams_f2", "how": "swap"}]} if d is not None and d.get("trigger") == "planar_chaos" else None
    return None


# -- each player chooses (Caught in a Parallel Universe, Meta-Crisis) ------------------------------------------------------------------
def _creatures(plan: Plan, pid: str) -> list[str]:
    return [c.id for c in plan.state.cards.values() if c.zone == f"{pid}:battlefield" and c.controller == pid and plan.ch(c).is_creature]


def _ask(plan: Plan, ctx: dict[str, Any], player: str, prompt: str, cards: list[str], resume: dict[str, Any], *, optional: bool = False) -> None:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=player, kind="choose_cards", prompt=f"{ctx.get('name') or 'Choose'}: {prompt}",
           options=[DecisionOption(id=c, label=f"{plan.state.cards[c].name or 'Creature'} — {plan.name(plan.state.cards[c].controller)}", card_id=c)
                    for c in cards], min_choices=0 if optional else 1, max_choices=1, resume={"ctx": ctx, **resume})


def _insert(ctx: dict[str, Any], added: list[Def]) -> None:
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]


def parallel(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Caught in a Parallel Universe: each player in turn order (101.4, knowing the earlier choices) chooses a creature the player to their left
    controls; then each creates a token copy of the creature they chose, with menace."""
    return _parallel(plan, ctx, list(plan.apnap()), [])


def _parallel(plan: Plan, ctx: dict[str, Any], who: list[str], picks: list[list[str]]) -> bool:
    from app.rules import context

    while who:
        pid, who = who[0], who[1:]
        left = plan.left(pid)
        cards = _creatures(plan, left) if left != pid else []
        if len(cards) == 1:
            picks = [*picks, [pid, cards[0]]]
            plan.note(f"{plan.name(pid)} chooses {plan.state.cards[cards[0]].name} (no choice)", cards, actor=pid)
        elif cards:
            _ask(plan, ctx, pid, f"choose a creature {plan.name(left)} controls", cards, {"step": "parallel_f2", "who": who, "picks": picks})
            return False
    added: list[Def] = []
    for i, (pid, cid) in enumerate(picks):
        context.bind_objects(plan, ctx, f"parallel_f2_{i}", [cid])
        added.append({"do": "token_copy", "n": 1, "excepts": [{"add_text": ["Menace"]}], "who": f"ref:parallel_f2_{i}", "creator": f"player:{pid}"})
    _insert(ctx, added)
    return True


def _resume_parallel(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    picks = [*r["picks"], [d.player, chosen[0]]] if chosen else r["picks"]
    if chosen:
        plan.note(f"{plan.name(d.player)} chooses {plan.state.cards[chosen[0]].name}", chosen, actor=d.player)
    if _parallel(plan, r["ctx"], r["who"], picks):
        effects.continue_effects(plan, r["ctx"])


def meta(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Human—Time Lord Meta-Crisis: each player in turn order chooses a first creature they control and may choose a second; then each creates a
    token copy of their first (not legendary), then each who chose a second puts +1/+1 counters equal to its power on that token."""
    return _meta(plan, ctx, list(plan.apnap()), [], None)


def _meta(plan: Plan, ctx: dict[str, Any], who: list[str], picks: list[list[Any]], first: str | None) -> bool:
    from app.rules import context

    while who:
        pid = who[0]
        mine = _creatures(plan, pid)
        if first is None:
            if not mine:
                who = who[1:]
                continue
            if len(mine) > 1:
                _ask(plan, ctx, pid, "choose the first creature (a token copy of it)", mine, {"step": "meta_f2", "who": who, "picks": picks, "first": None})
                return False
            first = mine[0]
            plan.note(f"{plan.name(pid)} chooses {plan.state.cards[first].name} first (no choice)", [first], actor=pid)
        rest = [c for c in mine if c != first]
        if rest:
            _ask(plan, ctx, pid, "you may choose a second creature (+1/+1 counters equal to its power)", rest,
                 {"step": "meta_f2", "who": who, "picks": picks, "first": first}, optional=True)
            return False
        picks, who, first = [*picks, [pid, first, None]], who[1:], None
    copies: list[Def] = []
    counters: list[Def] = []
    for i, (pid, one, two) in enumerate(picks):
        context.bind_objects(plan, ctx, f"meta_f2_{i}", [one])
        copies.append({"do": "token_copy", "n": 1, "excepts": [{"remove_supertypes": ["Legendary"]}], "who": f"ref:meta_f2_{i}",
                       "creator": f"player:{pid}", "as": f"meta_tok_f2_{i}"})
        if two is not None:
            context.bind_objects(plan, ctx, f"meta_two_f2_{i}", [two])
            counters.append({"do": "meta_counters_f2", "player": pid, "token": f"meta_tok_f2_{i}", "second": f"meta_two_f2_{i}"})
    _insert(ctx, [*copies, *counters])
    return True


def _resume_meta(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    who, picks, first = r["who"], r["picks"], r["first"]
    if first is None:
        first = chosen[0] if chosen else _creatures(plan, d.player)[0]
        plan.note(f"{plan.name(d.player)} chooses {plan.state.cards[first].name} first", [first], actor=d.player)
        done = _meta(plan, r["ctx"], who, picks, first)
    else:
        if chosen:
            plan.note(f"{plan.name(d.player)} chooses {plan.state.cards[chosen[0]].name} second", chosen, actor=d.player)
        done = _meta(plan, r["ctx"], who[1:], [*picks, [d.player, first, chosen[0] if chosen else None]], None)
    if done:
        effects.continue_effects(plan, r["ctx"])


def meta_counters(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """"puts a number of +1/+1 counters on the token they created equal to the power of the second creature they chose" — its power now (or as it
    last existed, 608.2h); the player who chose it puts them (the native "put counters", its replacements included)."""
    from app.rules import context, sba

    found = context.info(plan, ctx, e["second"])
    if found is None:
        return True
    n = max(0, sba.power(found[0], found[1]) or 0)
    if n == 0 or not context.objects(plan, ctx, e["token"]):
        return True
    _insert(ctx, [{"do": "as_player", "player": e["player"]}, {"do": "add_counters", "who": f"ref:{e['token']}", "kind": "+1/+1", "n": n},
                  {"do": "as_player_end"}])
    return True


# -- Morphic Tide ------------------------------------------------------------------------------------------------------------------------
def morphic_enter(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Morphic Tide: Warp World's entry (wave110c_misc.warp_enter) with planeswalker cards among the first group (ruling 2012-06-01)."""
    from app.rules import attachments

    want = {"Artifact", "Creature", "Land", "Planeswalker"} if e["kinds"] == "main" else {"Enchantment"}
    entries = [{"card": c, "player": pid, "actor": pid, "tapped": False} for pid in plan.apnap() for c in ctx.get("warp110c", {}).get(pid, [])
               if plan.state.cards[c].zone == f"{pid}:library" and want & set(plan.ch(plan.state.cards[c]).types)]
    return attachments.enter(plan, entries, ctx) if entries else True


# -- The Doctor's Childhood Barn ------------------------------------------------------------------------------------------------------------
def barn(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """They phase out (702.26); recorded with the plane (its object) and the ability's controller (the delayed trigger's, 603.7d)."""
    from app.rules import effects

    ids = [cid for cid in effects._cards(plan, ctx, e["who"])
           if (c := plan.state.cards.get(cid)) is not None and plan.in_game(c) and c.zone.endswith(":battlefield")]
    if not ids:
        return True
    plan.do({"type": "phase_shift", "card_ids": ids, "out": True}, actor=ctx["controller"])
    out = [plan.oid(plan.state.cards[c]) for c in ids if plan.state.cards[c].zone.endswith(":phased")]
    if out:
        r = plan.rules
        r.planar_more3_f2 = {**r.planar_more3_f2, "barn": [*(r.planar_more3_f2.get("barn") or []),
                                                             {"plane": ctx.get("source_object") or "", "card": ctx.get("source_card") or "",
                                                              "controller": ctx["controller"], "objects": out}]}
    return True


def _face_objects(state: GameState) -> set[str]:
    from app.game.handlers import planechase

    pc, r = state.planechase, state.rules
    if pc is None or r is None:
        return set()
    return {r.object_id(fid) for fid in planechase.all_face_ids(pc) if fid in state.cards}


def cant_phase_in(plan: Plan, card_id: str) -> bool:
    """The Doctor's Childhood Barn: "They can't phase in for as long as ~ remains face up." (in the untap step, 702.26a)."""
    held = plan.rules.planar_more3_f2.get("barn") or []
    if not held or card_id not in plan.state.cards:
        return False
    oid = plan.oid(plan.state.cards[card_id])
    faces = _face_objects(plan.state)
    return any(oid in h["objects"] and h["plane"] in faces for h in held)


def _barn_walk(plan: Plan) -> None:
    """A player planeswalked (701.31): "When a player planeswalks, those permanents phase in." — the delayed triggers (603.7)."""
    from app.rules import designations

    r = plan.rules
    held = r.planar_more3_f2.get("barn") or []
    if not held:
        return
    r.planar_more3_f2 = {k: v for k, v in r.planar_more3_f2.items() if k != "barn"}
    for h in held:
        designations._add_trigger(plan, h["controller"], "The Doctor's Childhood Barn", [{"do": "barn_in_f2", "objects": h["objects"]}])


def barn_in(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """"those permanents phase in" — the ones still phased out directly (702.26: not one that came with a host)."""
    back = [c.id for c in plan.state.cards.values() if c.zone.endswith(":phased") and not c.phased_indirect and plan.oid(c) in e["objects"]
            and c.owner in plan.live()]
    if back:
        from app.game.rules_state import emit

        for cid in back:
            emit(plan.state, "designation", counter="phase_in", card=cid, object_id=plan.oid(cid), player=plan.state.cards[cid].controller)
        plan.do({"type": "phase_shift", "card_ids": back, "out": False}, actor=ctx["controller"])
    return True


# -- Singing Towers of Darillium ---------------------------------------------------------------------------------------------------------
def towers(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """"you may cast a foretold card you own from exile without paying its mana cost this turn." (118.9; one spell)."""
    from app.rules import permissions

    permissions.grant_play(plan, ctx, {"do": "grant_play", "play": False, "cast": True, "zone": "foretell", "zone_owner": "you", "free": True,
                                       "once": True, "until": "end_of_turn"})  # (the foretell zone holds only foretold cards: permissions._card_zone)
    return True


# -- Two Streams Facility ------------------------------------------------------------------------------------------------------------------
def streams(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Each player chooses green anchor or red waterfall (101.4: in turn order), recorded for this plane object; or (chaos) each choice flips."""
    plane = ctx.get("source_object") or ""
    rec = plan.rules.planar_more3_f2.get("streams") or {}
    if e["how"] == "swap":
        if rec.get("plane") != plane:
            return True
        flipped = {p: WATERFALL if c == ANCHOR else ANCHOR for p, c in (rec.get("choices") or {}).items()}
        _record(plan, plane, flipped)
        for p, c in flipped.items():
            plan.note(f"{plan.name(p)} chooses {_LABELS[c]}", actor=p)
        return True
    _record(plan, plane, {})
    return _ask_stream(plan, ctx, list(plan.apnap()))


def _record(plan: Plan, plane: str, choices: dict[str, str]) -> None:
    r = plan.rules
    r.planar_more3_f2 = {**r.planar_more3_f2, "streams": {"plane": plane, "choices": dict(choices)}}


def _ask_stream(plan: Plan, ctx: dict[str, Any], who: list[str]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    if not who:
        return True
    decide(plan, player=who[0], kind="choose_one", prompt=f"{ctx.get('name') or 'Two Streams Facility'}: choose green anchor or red waterfall",
           options=[DecisionOption(id=k, label=v) for k, v in _LABELS.items()], resume={"step": "streams_f2", "ctx": ctx, "who": who[1:]})
    return False


def _resume_stream(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    pick = chosen[0] if chosen and chosen[0] in _LABELS else ANCHOR
    rec = plan.rules.planar_more3_f2.get("streams") or {}
    if rec.get("plane") == (r["ctx"].get("source_object") or ""):
        _record(plan, rec["plane"], {**(rec.get("choices") or {}), d.player: pick})
    plan.note(f"{plan.name(d.player)} chooses {_LABELS[pick]}", actor=d.player)
    if _ask_stream(plan, r["ctx"], r["who"]):
        effects.continue_effects(plan, r["ctx"])


def _stream_choice(state: GameState, player: str) -> str | None:
    """The player's last choice for the face-up Two Streams Facility whose statics work (its object), else None."""
    r = state.rules
    rec = (r.planar_more3_f2.get("streams") if r is not None else None) or {}
    if not rec or rec.get("plane") not in _working_faces(state):
        return None
    choice = (rec.get("choices") or {}).get(player)
    return choice if isinstance(choice, str) else None


def _working_faces(state: GameState) -> set[str]:
    from app.game.handlers import planechase
    from app.rules import planar_statics

    pc, r = state.planechase, state.rules
    if pc is None or r is None:
        return set()
    return {r.object_id(fid) for fid in planechase.all_face_ids(pc) if (c := state.cards.get(fid)) is not None and planar_statics.functions(state, c)}


def extra_lands(state: GameState, player: str, info: CardInfo | None) -> int:
    """Two Streams Facility: a green anchor player may play an additional land on each of their turns (305.2)."""
    from app.rules import planar_more

    if _stream_choice(state, player) != ANCHOR or not planar_more._face_defs(state, info, STREAMS_LAND):
        return 0
    return 1


def selector_extra(plan: Any, extra: str, card: CardInstance, you: str) -> bool:
    """The selector extra ``streams_f2``: controlled by a player who last chose red waterfall."""
    return extra == "streams_f2" and _stream_choice(plan.state, card.controller) == WATERFALL


# -- events: planeswalks ---------------------------------------------------------------------------------------------------------------
def on_events(plan: Plan, events: list[Any]) -> None:
    """The table's "planar" events (planar.on_events): a planeswalk (the ``from`` event, also one made by hand) creates the Barn's delayed
    triggers."""
    if any(e.kind == "planar" and e.counter == "from" for e in events):
        _barn_walk(plan)
    if any(e.kind in ("spell_cast", "land_played") for e in events):
        _matrix(plan, events)


def _matrix(plan: Plan, events: list[Any]) -> None:
    """The Matrix of Time: "Whenever you play a land or cast a spell from among cards exiled with ~" — the planar controller cast a spell or
    played a land whose card was, as it left exile, one of the objects this plane's abilities exiled (``RulesState.exiled_with``, 607.2a)."""
    from app.game.handlers import planechase
    from app.game.rules_state import ObjectRef, TriggerEvent
    from app.rules import planar_statics, scripts, triggers

    pc = plan.state.planechase
    if pc is None:
        return
    faces = [c for fid in planechase.all_face_ids(pc) if (c := plan.state.cards.get(fid)) is not None and planar_statics.functions(plan.state, c)]
    for face in faces:
        ch = plan.ch(face)
        found = [(i, d) for i, d in scripts.definitions(ch).items() if d.get("kind") == "triggered" and d.get("trigger") == MATRIX_TRIGGER]
        linked = set(plan.rules.exiled_with.get(plan.oid(face)) or [])
        if not found or not linked:
            continue
        for e in events:
            if e.kind not in ("spell_cast", "land_played") or e.player != face.controller or not e.card:
                continue
            left = next((z for z in events if z.kind == "zone_change" and z.card == e.card and (z.from_zone or "").endswith(":exile")
                         and z.object_id in linked), None)
            card = plan.state.cards.get(e.card)
            if left is None or card is None:
                continue
            for i, d in found:
                triggers._add(plan, controller=face.controller, source_card=face.id, source_object=plan.oid(face), name=ch.name, index=i,
                              definition=d, event=TriggerEvent(kind="matrix_f2", players=[card.owner], actor=e.player,
                                                               objects=[ObjectRef(card=card.id, object_id=plan.oid(card), zone=card.zone)]))


# -- Ood Sphere: "can't become tapped unless they're being declared as attackers" (until your next turn) --------------------------------------------
def ood(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Records the goaded creatures (their objects) until the ability's controller's next turn (500.4: ``turn_began``)."""
    from app.rules import effects

    ids = [cid for cid in effects._cards(plan, ctx, e["who"]) if plan.state.cards[cid].zone.endswith(":battlefield")]
    if ids:
        r = plan.rules
        r.planar_more3_f2 = {**r.planar_more3_f2, "ood": [*(r.planar_more3_f2.get("ood") or []), {
            "objects": [plan.oid(plan.state.cards[c]) for c in ids], "player": ctx["controller"], "turn": plan.state.turn.number}]}
        plan.note(f"Until {plan.name(ctx['controller'])}'s next turn, they can't become tapped unless they're being declared as attackers", ids)
    return True


def turn_began(plan: Plan, skipped: list[tuple[str, int]] | None = None) -> None:
    """500.4: "until your next turn" ends as that player's next turn begins (800.4m: for a player who left, as it would have)."""
    r = plan.rules
    if not r.planar_more3_f2.get("ood"):
        return
    turn, active = plan.state.turn.number, plan.active

    def ended(x: Def) -> bool:
        return (x["player"] == active and turn > x["turn"]) or any(x["player"] == p and n > x["turn"] for p, n in skipped or ())

    left = [x for x in r.planar_more3_f2["ood"] if not ended(x)]
    r.planar_more3_f2 = {**{k: v for k, v in r.planar_more3_f2.items() if k != "ood"}, **({"ood": left} if left else {})}


def tap_guard(plan: Plan, payload: Def, actor: str | None) -> Def:
    """Ood Sphere's goaded creatures can't become tapped (ruling 2023-10-13: not by effects, not to pay costs) unless declared as attackers
    (combat's ``declared`` tap, 508.1f). A tap an effect makes (its controller is the actor) leaves them untapped; a cost (an untargeted tap
    action with no actor: {T}, crew, convoke, "tap an untapped creature you control") or a mana ability's {T} can't be paid with them."""
    from app.game.errors import ActionError

    held = {o for x in plan.rules.planar_more3_f2.get("ood") or [] for o in x["objects"]}
    cards = plan.state.cards
    if payload.get("type") == "rules_mana":
        bad = [c for c in payload.get("tap") or () if c in cards and plan.oid(cards[c]) in held]
    elif payload.get("declared") or payload.get("tapped") is False:
        return payload
    else:
        bad = [c for c in payload.get("card_ids") or () if c in cards and not cards[c].tapped and plan.oid(cards[c]) in held]
    if not bad:
        return payload
    names = ", ".join(cards[c].name or "It" for c in bad)
    if payload.get("type") == "rules_mana" or actor is None:
        raise ActionError(f"{names} can't become tapped unless it's being declared as an attacker (Ood Sphere)")
    keep = [c for c in payload.get("card_ids") or () if c not in bad]
    if keep:
        return {**payload, "card_ids": keep}
    return {"type": "rules_log", "text": f"{names} can't become tapped (Ood Sphere)", "card_ids": bad}


def mercy(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """sAnS mERcY: the process X times, X being the number of times "you" (the planar controller) rolled the planar die this turn (901.9: only
    the active player rolls; ``Planechase.rolls``, as Li'l Giri Saves the Day reads it)."""
    pc = plan.state.planechase
    n = pc.rolls if pc is not None and pc.roll_turn == plan.state.turn.number and plan.active == ctx["controller"] else 0
    _insert(ctx, [copy.deepcopy(e["process"]) for _ in range(n)])
    return True


PRIMITIVES: dict[str, Any] = {"mercy_f2": mercy, "ood_f2": ood, "parallel_f2": parallel, "meta_f2": meta, "meta_counters_f2": meta_counters, "morphic_enter_f2": morphic_enter,
                              "barn_f2": barn, "barn_in_f2": barn_in, "towers_f2": towers, "streams_f2": streams}
RESUME: dict[str, Any] = {"parallel_f2": _resume_parallel, "meta_f2": _resume_meta, "streams_f2": _resume_stream}
