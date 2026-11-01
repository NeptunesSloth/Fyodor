"""-- Star Trek (wave 111E) -- exact Oracle wordings of single Star Trek cards (trk, trc; Oracle text of 2026-10-30), built from
wordings the grammar already reads. Researched against CR 2026-09-25. Each entry matches one whole body exactly; any other
wording stays unsupported.

* Those Old Scientists III: Turn the Earth's instruction (static_spell100c) for up to two targets: each owner puts their targeted
  cards into their library and shuffles it (701.24a).
* Unification I: "The owner of up to one target creature draws two cards, then shuffles that creature into their library." (121.2,
  701.24a; no target chosen: nothing happens; a commander may go to the command zone instead, 903.9b).
* The City on the Edge of Forever I: every artifact and creature phases out at once (702.26b; what's attached to them indirectly,
  702.26g), then the Human token is created (its "Permanents can't phase in." is Disciple of Caelus Nin's, wave 110O).
* The Wrath of Khan I: the damage, then a delayed triggered ability (603.7a) "At the beginning of the next combat this turn" that gains
  control of that creature until end of turn, untaps it and gives it haste (the three sentences after the trigger condition are its
  effect, as "At the beginning of your next upkeep, return it … It gains haste." is Sundering Sentinel's); with no later combat this
  turn it never triggers (603.7b). "That creature" is the object the chapter dealt damage to (603.7c, 400.7).
* Exploratory Mission: the quest counter, then Bruntar's exile packet with a permission to play that card this turn (305.1, 601.1:
  reveal_cast_packets mode "mission111e"), then "If ~ has five or more quest counters on it, add {R}{R}." (a triggered ability that
  isn't a mana ability, 605.1b: the mana stays until the step ends, 500.4).
* U.S.S. Farragut: Sneak Attack's wording with "put it on the bottom of its owner's library" (it came from your hand: you own it),
  then the reflexive "When you do, draw a card." inside the delayed trigger (603.12): it triggers only when the card really went to the
  library (a commander its owner sent to the command zone instead, 903.9b, or an object that left the battlefield first, 400.7: no).
* Miles O'Brien: "returned to your hand" is Barrin's "put into your hand" (wave 30R Departure history).
* T'Pring: two targets (601.2c); "You may have the chosen creatures fight each other" asked as it resolves ("No": nothing more happens);
  when they fight (701.14a; 701.14b: neither fights if one of them is an illegal target, gone or no creature), a delayed triggered ability
  watches both for the rest of the turn (603.7b-c), triggering once for each of them that dies (400.7: that object, not a new one).
"""

from __future__ import annotations

import copy
from typing import Any

Def = dict[str, Any]
Parsed = tuple[list[dict[str, Any]], Any, bool]

SCIENTISTS = "Choose up to two target cards in graveyards. The owners of those cards shuffle them into their libraries."
UNIFICATION = "The owner of up to one target creature draws two cards, then shuffles that creature into their library."
CITY = "All artifacts and creatures phase out. Create a 0/1 white Human creature token with \"Permanents can't phase in.\""
KHAN = ("~ deals 4 damage to target creature an opponent controls. At the beginning of the next combat this turn, gain control of that "
        "creature until end of turn. Untap it. It gains haste until end of turn.")
MISSION = ("put a quest counter on ~. Then exile cards from the top of your library until you exile a nonland card. You may play that card "
           "this turn. If ~ has five or more quest counters on it, add {R}{R}.")
FARRAGUT = ("you may put a creature card from your hand onto the battlefield. That creature gains haste. At the beginning of the next end "
            "step, put it on the bottom of your library. When you do, draw a card.")
FARRAGUT_DID = "farragut111e"
TPRING = ("choose another target creature you control and target creature an opponent controls. You may have the chosen creatures fight each "
          "other. Whenever a creature that fought this way dies this turn, you draw a card.")
TPRING_REF = "tpring111e"

# whole ability text -> the native wording it means (exact_ability.build)
SAME = {
    "At the beginning of each end step, if a permanent was returned to your hand from the battlefield this turn, draw a card.":
        "At the beginning of each end step, if a permanent was put into your hand from the battlefield this turn, draw a card.",
}


def _native(text: str) -> Parsed:
    from app.rules import scripts

    found = scripts.parse_effects(text)
    if found is None:
        raise ValueError(f"wave 111E: the native wording no longer reads: {text!r}")
    return copy.deepcopy(found)


def _scientists() -> Parsed:
    effects, targets, _ = _native("Choose up to three target cards in graveyards. The owners of those cards shuffle them into their libraries. "
                                  "You gain 2 life.")
    assert [e["do"] for e in effects] == ["shuffle_library", "gain_life"] and len(targets) == 1
    return effects[:1], [{**targets[0], "max": 2}], False


def _unification() -> Parsed:
    _, targets, _ = _native("Return up to one target creature to its owner's hand.")
    assert len(targets) == 1 and targets[0]["max"] == 1 and targets[0]["min"] == 0
    return [{"do": "draw", "who": "owners100c:target:0", "n": 2}, {"do": "to_library", "who": "target:0", "place": "shuffle"}], targets, False


def _city() -> Parsed:
    wipe, _, _ = _native("Destroy all artifacts and creatures.")
    token, _, _ = _native("Create a 0/1 white Human creature token with \"Permanents can't phase in.\"")
    assert len(wipe) == 1 and wipe[0]["do"] == "destroy"
    return [{"do": "phase_out", "who": wipe[0]["who"]}, *token], None, False


def _khan() -> Parsed:
    hit, target, _ = _native("~ deals 4 damage to target creature an opponent controls.")
    steal, _, _ = _native("Gain control of target creature an opponent controls until end of turn. Untap it. It gains haste until end of turn.")
    assert [e["do"] for e in steal] == ["gain_control", "untap", "grant"]
    when = {"kind": "step", "step": "begin_combat", "whose": "next"}
    return [*hit, {"do": "delayed", "when": when, "n": len(steal), "this_turn": True},
            *({**e, "do": "deferred:" + e["do"]} for e in steal)], target, False


def _mission() -> Parsed:
    quest, _, _ = _native("Put a quest counter on ~.")
    mana, _, _ = _native("If ~ has five or more quest counters on it, add {R}{R}.")
    return [*quest, {"do": "reveal_cast_packet", "mode": "mission111e", "binding": "ref:reveal_cast"}, *mana], None, False


def _farragut() -> Parsed:
    effects, target, optional = _native("You may put a creature card from your hand onto the battlefield. That creature gains haste. At the "
                                        "beginning of the next end step, put it on the bottom of its owner's library.")
    assert [e["do"] for e in effects] == ["put_from_hand", "grant", "delayed", "deferred:to_library"] and effects[2]["n"] == 1
    draw, _, _ = _native("Draw a card.")
    effects[2]["n"] = 2
    effects[3]["reflex111e"] = FARRAGUT_DID
    effects.append({"do": "deferred:reflexive", "cond": {"succeeded": FARRAGUT_DID},
                    "ability": {"kind": "triggered", "trigger": "reflexive", "effects": draw, "optional": False, "target": None}})
    return effects, target, optional


def _tpring() -> Parsed:
    fight, targets, _ = _native("Another target creature you control fights target creature an opponent controls.")
    draw, _, _ = _native("You draw a card.")
    assert [e["do"] for e in fight] == ["fight"] and len(targets) == 2 and len(draw) == 1
    return [{"do": "may_rest", "label": "have the chosen creatures fight each other"}, {**fight[0], "do": "tpring_fight111e"},
            {"do": "delayed", "when": {"kind": "event", "event": "die"}, "n": 1, "who": "ref:" + TPRING_REF, "this_turn": True, "once": False},
            *({**e, "do": "deferred:" + e["do"]} for e in draw)], targets, False


_BODIES = {SCIENTISTS: _scientists, UNIFICATION: _unification, CITY: _city, KHAN: _khan, MISSION: _mission, FARRAGUT: _farragut,
           TPRING: _tpring}


def parse(body: str) -> Parsed | None:
    build = _BODIES.get(body.strip())
    return None if build is None else build()


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import exact_ability

    return exact_ability.build(ability, ch, {}, SAME)


def tpring_fight(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """T'Pring's fight (701.14a): the two creatures, when both are still legal targets, on the battlefield and creatures, fight; only then are they
    bound as "a creature that fought this way" for the delayed ability after it (701.14b: otherwise neither fights, and nothing is watched)."""
    from app.rules import context
    from app.rules.effects import PRIMITIVES, _cards

    a, b = _cards(plan, ctx, e["who"]), _cards(plan, ctx, e["with"])
    pair = [*a, *b] if len(a) == 1 and len(b) == 1 else []
    if any(not plan.state.cards[c].zone.endswith(":battlefield") or not plan.ch(plan.state.cards[c]).is_creature for c in pair):
        pair = []
    context.bind_objects(plan, ctx, TPRING_REF, pair)
    return bool(PRIMITIVES["fight"](plan, ctx, {**e, "do": "fight"}))


PRIMITIVES = {"tpring_fight111e": tpring_fight}


def to_library_reflex(fn: Any) -> Any:
    """``to_library`` with "reflex111e": a binding, true only when a card it moved really reached its owner's library (603.12: a reflexive
    ability triggers on the event having happened; the U.S.S. Farragut's "When you do")."""
    def run(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
        name = e.get("reflex111e")
        if not name:
            return bool(fn(plan, ctx, e))
        from app.rules import context
        from app.rules.effects import _cards

        cards = {c: plan.oid(plan.state.cards[c]) for c in _cards(plan, ctx, e["who"])}
        done = bool(fn(plan, ctx, e))
        went = any((card := plan.state.cards.get(c)) is not None and card.zone == f"{card.owner}:library" for c in cards)
        context.bind_payment(ctx, name, went)
        return done
    return run
