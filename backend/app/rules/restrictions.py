"""Activation restrictions (CR 602.5) and trigger limits, researched against CR 2026-09-25.

An activated ability's text may end with a restriction sentence: "Activate only as a sorcery."
(602.5d, 307.5: the player must have priority, during a main phase of their turn, with the
stack empty), "Activate only as an instant." (602.5e, 304.5: priority is all it takes),
"Activate only once each turn." / "Activate no more than twice each turn." (602.5b: the limit
belongs to the object — a permanent that left and came back is a new object, 400.7, and a
change of controller doesn't reset it), "Activate only once." (per object, for the game),
"Activate only during your turn." / "… during your upkeep." / "… during combat." / "… during the
declare blockers step." / "… during your turn, before attackers are declared." (the steps of a
turn, 500.1, 506.1, 508.1: attackers are declared as the declare attackers step begins) and
"Activate only if [condition]." (a condition the engine reads, app/rules/conditions.py, checked
as the ability would be activated — 602.5: a player can't begin to activate a prohibited
ability). Several restrictions may be joined ("Activate only as a sorcery and only once each
turn."): all of them apply.

Triggered abilities may end with "This ability triggers only once each turn.": after it has
triggered once in a turn (603.2), later events don't make it trigger again — even if that first
ability was countered or removed from the stack, it had triggered. "Do this only once each turn."
is different (603.2h: the ability triggers only if its source's controller has not yet taken the
indicated action that turn — an action they may decline): the action is recorded on the
resolution side (app/rules/effects.py ``record_action``, appended to the ability's effects, so it
counts only when the resolution got that far — not when the ability was countered, its "you may"
declined, or a payment it hinges on wasn't made) and read by triggers._add as it would trigger.

Uses are counted in ``RulesState.ability_uses`` (app/game/rules_state.py): a JSON dict keyed
``"<object id>:<ability index>:t<turn number>"`` for a turn's uses and
``"<object id>:<ability index>:game"`` for the game's, so the count survives saving, loading and
replay, resets with the turn number (extra turns have their own number) and dies with the object.
Wordings this module doesn't read leave the ability manual: nothing is guessed.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.state import COMBAT_PHASES, PHASES, STACK
from app.rules import activation_words
from app.rules.activation_words import ANY_PLAYER, ANY_PLAYER_BUT, OPPONENTS_BUT, OPPONENTS_ONLY

if TYPE_CHECKING:
    from app.game.rules_state import RulesState
    from app.game.state import CardInstance, GameState
    from app.rules.plan import Plan

Restriction = dict[str, Any]

MAIN_PHASES = ("main1", "main2")
_BEFORE_ATTACKERS = tuple(PHASES[: PHASES.index("declare_attackers")])

# The sentence(s) that carry an activation restriction, at the end of an activated ability's text.
_RESTRICTION_SENTENCE = re.compile(r"^(?:Activate (?:this ability )?only|Activate no more than|You can't activate this ability) (?P<rest>.+)\.$")
# -- activated (wave 100I) -- 602.5b: a limit counted at each attempt (Withering Wisps ruling 2008-10-01)
_COUNTED_LIMIT = re.compile(r"^Activate no more times each turn than the number of (?P<what>.+)\.$")
# Trigger limits (the last sentence of a triggered ability's text)
TRIGGER_LIMIT_ONCE = "This ability triggers only once each turn."
# 603.2h: "Do this only once each turn." — the ability triggers only if its source's controller has
# not yet taken the indicated action that turn: the action is recorded as the ability's resolution
# gets to it (effects.record_action), and triggers._add reads that count as it would trigger.
TRIGGER_LIMIT_DO_ONCE = "Do this only once each turn."
TRIGGER_LIMIT_REFUSED: tuple[str, ...] = ()
TRIGGER_LIMITS = {TRIGGER_LIMIT_ONCE: "once_each_turn", TRIGGER_LIMIT_DO_ONCE: "do_once",
                  "This ability triggers only once.": "once_game"}  # -- turn state (wave 100H) -- once for the object (a new object may again, 400.7)


def limit_kind(sentence: str) -> str:
    """The definition's ``limit`` for a trigger-limit sentence split_trigger_limit found."""
    return TRIGGER_LIMITS[sentence]

_TIMES = {"once": 1, "twice": 2, "three times": 3, "four times": 4}
_STEPS = {
    "your upkeep": ("upkeep", "you"),
    "an opponent's upkeep": ("upkeep", "opponent"),
    "any upkeep step": ("upkeep", None),
    "an upkeep step": ("upkeep", None),
    "combat": (tuple(sorted(COMBAT_PHASES, key=PHASES.index)), None),
    "the declare blockers step": ("declare_blockers", None),
    "the declare attackers step": ("declare_attackers", None),
    "the end of combat step": ("end_combat", None),
    "your end step": ("end", "you"),
    "their draw step": ("draw", "you"),  # (wave 17B: an any-player ability's "their": the activator's)
    "the end step": ("end", None),
}


def _sentences(body: str) -> list[str]:
    # (quote-aware: a granted `…." Activate only once.` splits right)
    from app.rules.oracle import split_sentences

    return split_sentences(body.strip())


def split(body: str) -> tuple[str, str | None]:
    """Split an activated ability's effect text into (effects, the restriction sentences or
    None). The restriction sentences are the trailing ones that start with "Activate only …"."""
    sentences = _sentences(body)
    found: list[str] = []
    while sentences and (_RESTRICTION_SENTENCE.match(sentences[-1]) or sentences[-1] in (ANY_PLAYER, OPPONENTS_ONLY)
                         or ANY_PLAYER_BUT.match(sentences[-1]) or OPPONENTS_BUT.match(sentences[-1]) or _COUNTED_LIMIT.match(sentences[-1])):  # (ANY_PLAYER: wave 7B; ANY_PLAYER_BUT: wave 17B; wave 100I)
        found.insert(0, sentences.pop())
    if not found:
        return body, None
    return " ".join(sentences), " ".join(found)


def split_trigger_limit(body: str) -> tuple[str, str | None]:
    """Split a triggered ability's text into (effects, its trailing limit sentence or None)."""
    sentences = _sentences(body)
    if sentences and (sentences[-1] in TRIGGER_LIMITS or sentences[-1] in TRIGGER_LIMIT_REFUSED):
        return " ".join(sentences[:-1]), sentences[-1]
    return body, None


EXHAUST = "Exhaust — "  # -- ability words (wave 4F) -- 702.177
# -- activation costs (wave 4H) -- 702.142a: "Boast — [Cost]: [Effect]" means "[Cost]: [Effect]. Activate only if this
# creature attacked this turn and only once each turn." (Birgi, God of Storytelling: twice during each of your turns)
BOAST = "Boast — "
_BOAST_TWICE = frozenset({"Birgi, God of Storytelling"})


def _face_name(card: CardInstance) -> str:
    """-- review (wave 4R) -- the name of the face a permanent shows: a modal double-faced card's instance carries
    both names ("Birgi, God of Storytelling // Harnfel, Horn of Bounty"); face down, it has none (708.2)."""
    if card.face_down:
        return ""
    names = card.name.split(" // ")
    return names[card.face] if 0 <= card.face < len(names) else names[0]


def parse(text: str) -> list[Restriction] | None:
    """The restrictions in an ability's text (an empty list: none), or None when a restriction
    sentence isn't one this module reads (the ability then stays manual)."""
    _, found = split(text.split(":", 1)[1] if ":" in text else text)
    # -- ability words (wave 4F) -- 702.177a: "Exhaust — [Cost]: [Effect]" means "[Cost]: [Effect]. Activate only once."
    exhaust: list[Restriction] = [{"kind": "per_game", "n": 1, "exhaust": True}] if text.startswith(EXHAUST) else []
    if text.startswith("Power-up — "):  # -- counters (wave 7C) -- 702.193a: "Activate this ability only once."
        exhaust = [{"kind": "per_game", "n": 1, "power_up": True}]
    if text.startswith("Forecast — "):  # -- forecast (wave 24C) -- 702.57a: "Activate only during your upkeep and only once each turn."
        exhaust = [{"kind": "step", "phases": ["upkeep"], "whose": "you"}, {"kind": "per_turn", "n": 1}]
    if text.startswith(BOAST):  # -- activation costs (wave 4H) -- 702.142a
        exhaust = [{"kind": "if", "cond": {"history": "self_attacked", "object": "self"}, "text": "this creature attacked this turn"},
                   {"kind": "per_turn", "n": 1, "boast": True}]
    if found is None:
        return exhaust
    out: list[Restriction] = list(exhaust)
    for sentence in _sentences(found):
        if sentence == OPPONENTS_ONLY:
            out.append({"kind": "any_player", "opponents_only": True})
            continue
        if sentence == ANY_PLAYER:  # -- activation wordings (wave 7B) -- 602.2
            out.append({"kind": "any_player"})
            continue
        if (counted := _COUNTED_LIMIT.match(sentence)) is not None:  # -- activated (wave 100I) --
            from app.rules import selectors

            sel = selectors.parse(counted["what"])
            if sel is None or sel.player is not None:
                return None
            out.append({"kind": "per_turn", "n": 0, "count100i": sel.key(), "text": f"the number of {counted['what']}"})
            continue
        but = ANY_PLAYER_BUT.match(sentence) or OPPONENTS_BUT.match(sentence)
        if but is not None:  # -- activated sweep (wave 17B) -- "Any player may activate this ability but only as a sorcery." (wave 100I: "Only your opponents … and only as a sorcery.")
            out.append({"kind": "any_player", **({"opponents_only": True} if sentence.startswith("Only") else {})})
        m = _RESTRICTION_SENTENCE.match(sentence) if but is None else but
        assert m is not None  # (split only keeps matching sentences)
        if sentence == "You can't activate this ability during combat.":
            out.append({'kind': 'if', 'cond': {'not': {'combat_phase': 'any'}}, 'text': "it is not combat"})
            continue
        if sentence.startswith("You can't activate"):
            return None
        rest = m["rest"]
        if sentence.startswith("Activate no more than"):
            rest = "no more than " + rest
        # (-- activated (wave 100I) -- also a list: "during the declare blockers step, only if …, and only once each turn" (Grizzled Wolverine))
        for clause in re.split(r",? and (?:only )?(?=if |as |once|during |before |no more than |twice|three times)|, only (?=if |as |once|during )", rest):
            one = _clause(clause.strip())
            if one is None:
                return None
            out.append(one)
    return out


def _clause(clause: str) -> Restriction | None:
    if clause == "as a sorcery":
        return {"kind": "sorcery"}
    if clause == "as an instant":
        return {"kind": "instant"}
    if clause == "once":
        return {"kind": "per_game", "n": 1}
    m = re.fullmatch(r"(?:no more than )?(?P<times>once|twice|three times|four times) each turn", clause)
    if m:
        return {"kind": "per_turn", "n": _TIMES[m["times"]]}
    if clause in ('during your turn before the end step', 'during their turn before the end step'):
        from app.game.state import PHASES

        return {'kind': 'step', 'phases': [p for p in PHASES if p not in ('end', 'cleanup')], 'whose': 'you'}
    if clause in ("during your turn", "during their turn"):  # (wave 17B: "their": the activator's, any player may activate it)
        return {"kind": "your_turn"}
    if clause == "during an opponent's turn":
        return {"kind": "opponents_turn"}
    m = re.fullmatch(r"(?:during your turn, )?before attackers are declared", clause)
    if m:
        return {"kind": "step", "phases": list(_BEFORE_ATTACKERS), "whose": "you" if clause.startswith("during your turn") else None,
                "first_combat": True}  # (wave 7R: 506.8d, 506.8g)
    if (stepped := activation_words.step_clause(clause)) is not None:  # -- activation wordings (wave 7B) --
        return stepped
    m = re.fullmatch(r"during (?P<step>.+)", clause)
    if m and m["step"] in _STEPS:
        phases, whose = _STEPS[m["step"]]
        return {"kind": "step", "phases": [phases] if isinstance(phases, str) else list(phases), "whose": whose}
    m = re.fullmatch(r"if (?P<cond>.+)", clause)
    if m:
        cond = _condition(m["cond"])
        return {"kind": "if", "cond": cond, "text": m["cond"]} if cond is not None else None
    return None


def _condition(text: str) -> dict[str, Any] | None:
    if text == 'three or more creature cards are above this card':
        return {'object': 'self', 'test': 'graveyard_three_creatures_above'}
    from app.rules import activated100i  # -- activated (wave 100I) --

    if (own100i := activated100i.condition(text)) is not None:
        return own100i
    from app.rules import conditions, selectors
    if text == "you're attacking two or more opponents":  # -- zones (wave 100G) -- Nemesis Phoenix: the players creatures you control attack (506.2, values.players_attacked)
        return {'value': {'players_attacked': 1, 'by': 'you'}, 'op': '>=', 'n': 2}
    if text == 'it has no time counters on it':
        text = '~ has no time counters on it'
    # -- activated other (wave 34B) -- "Activate only if this artifact or another artifact entered the battlefield under your control this turn." (Master's
    # Guide-Mural): the source is one of those artifacts too, so it is "an artifact entered …" (the turn's history reads every permanent that entered)
    text = re.sub(r"^~ or another (\w+) (entered the battlefield under your control this turn)$",
                  lambda m: f"{'an' if m[1][0] in 'aeiou' else 'a'} {m[1]} {m[2]}", text)
    if hand_sizes := re.fullmatch(r"you have exactly (?P<a>\w+) or (?P<b>\w+) cards in (?:your )?hand", text):
        first_n = 0 if hand_sizes['a'] == 'zero' else conditions._num(hand_sizes['a'])
        second_n = 0 if hand_sizes['b'] == 'zero' else conditions._num(hand_sizes['b'])
        if first_n is not None and second_n is not None:
            return {'any': [{'value': {'hand': 'you'}, 'op': '==', 'n': amount} for amount in (first_n, second_n)]}
        return None
    cond = conditions.parse(text) or activation_words.condition(text)  # (wave 7B)
    if cond is not None:
        return cond
    # "there are seven or more cards in your graveyard" (a count the selector grammar reads)
    m = re.fullmatch(r"there are (?P<n>\w+) or more (?P<what>(?:\w+ )?cards in your graveyard)", text)
    if m:
        n = conditions._num(m["n"])
        sel = selectors.parse(m["what"])
        if n is not None and sel is not None and sel.player is None:
            return {"value": {"count": sel.key()}, "op": ">=", "n": n}
    return None


# -- counting uses -----------------------------------------------------------------------------
def use_key(object_id: str, index: int, turn: int | None) -> str:
    return f"{object_id}:{index}:t{turn}" if turn is not None else f"{object_id}:{index}:game"


def uses(rules: RulesState, object_id: str, index: int, turn: int | None) -> int:
    return rules.ability_uses.get(use_key(object_id, index, turn), 0)


def record_use(rules: RulesState, object_id: str, index: int, turn: int) -> None:
    """Count one activation (or triggering) of this object's ability in this turn, for the game
    too. Earlier turns' counts are dropped: nothing reads them any more."""
    keep = (f":t{turn}", ":game")
    rules.ability_uses = {k: v for k, v in rules.ability_uses.items() if k.endswith(keep)}
    for key in (use_key(object_id, index, turn), use_key(object_id, index, None)):
        rules.ability_uses[key] = rules.ability_uses.get(key, 0) + 1


def limited(restrictions: list[Restriction]) -> bool:
    """Does activating count against a limit (so the activation must be recorded)?"""
    return any(r["kind"] in ("per_turn", "per_game") for r in restrictions)


# -- checking ----------------------------------------------------------------------------------
def problem(state: GameState, player: str, card: CardInstance, index: int, restrictions: list[Restriction],
            plan: Plan | None = None, name: str = "") -> str | None:
    """Why ``player`` can't activate the ability under these restrictions right now (None: they can).
    ``plan`` (any view of the table) is needed for "only if" conditions."""
    r = state.rules
    assert r is not None
    turn = state.turn
    for x in restrictions:
        kind = x["kind"]
        if kind == "sorcery":  # 602.5d, 307.5
            if turn.active_player != player or turn.phase not in MAIN_PHASES or state.zones.get(STACK):
                return "That can only be activated as a sorcery: in your main phase while the stack is empty"
        elif kind == "your_turn":
            if turn.active_player != player:
                return "That can only be activated during your turn"
        elif kind == "opponents_turn":
            if turn.active_player == player:
                return "That can only be activated during an opponent's turn"
        elif kind == "step":
            if x["whose"] == "you" and turn.active_player != player:
                return f"That can only be activated during your {_phase_words(x['phases'])}"
            if x["whose"] == "opponent" and turn.active_player == player:  # (wave 7A: cast timing)
                return "That can only be activated during an opponent's turn"
            if turn.phase not in x["phases"]:
                return f"That can only be activated {_when(x)}"
            # -- review (wave 7R) -- "after blockers are declared": with no attackers the declare blockers step is skipped
            # (508.8, 506.8f), so end of combat comes without blockers having been declared
            if x.get("first_combat") and turn.phase in COMBAT_PHASES and r.combats > 1:  # 506.8d / 506.8g
                return "That can only be done before that point of the turn's first combat phase (506.8d)"
            if x.get("needs_blockers") and turn.phase == "end_combat" and r.no_attackers:
                return "That can only be activated after blockers are declared (this combat has no declare blockers step)"
        elif kind == "per_turn":
            n = x["n"]
            if x.get("boast") and turn.active_player == player and any(  # (wave 4H) Birgi: "can boast twice during each of your turns"
                    (c := state.cards.get(cid)) is not None and _face_name(c) in _BOAST_TWICE for cid in state.zones.get(f"{player}:battlefield", [])):
                n = 2
            if x.get("count100i"):  # -- activated (wave 100I) -- "Activate no more times each turn than the number of …": counted at each attempt (602.5b)
                from app.rules import values

                n = values.evaluate(plan, {"controller": player, "source_card": card.id}, {"count": x["count100i"]}) if plan is not None else 0
                if uses(r, r.object_id(card.id), index, turn.number) >= n:
                    return f"That can be activated only as many times each turn as {x['text']}"
            if uses(r, r.object_id(card.id), index, turn.number) >= n:
                return "That can only be activated once each turn" if x["n"] == 1 else \
                    f"That can be activated only {_times(x['n'])} each turn"
        elif kind == "per_game":
            if x.get("exhaust") and _exhaust_again(state, player):
                continue  # (wave 4F) 702.177b: an effect lets exhaust abilities be activated again: the player decides
            if x.get("power_up") and state.turn.number in r.no_power_up_turns:  # -- power-up (wave 50J) -- Kang the Conqueror's extra turn
                return "Power-up abilities can't be activated this turn"
            # -- power-up (wave 50J) -- "Each power-up ability of permanents you control can be activated an additional time." (Wonder Man; name-keyed like Birgi's, ponytail: it
            # stays while he has lost his abilities)
            n = x["n"] + (1 if x.get("power_up") and any((c := state.cards.get(cid)) is not None and _face_name(c) == "Wonder Man, Hollywood Hero"
                                                         for cid in state.zones.get(f"{player}:battlefield", [])) else 0)
            if uses(r, r.object_id(card.id), index, None) >= n:
                return "That can only be activated once" if n == 1 else f"That can be activated only {_times(n)}"
        elif kind == "if":
            if x.get('cond', {}).get('fought_creature90') and plan is not None:
                from app.rules import fight_receipts90

                if (unknown90 := fight_receipts90.restriction_problem(plan, player)) is not None:
                    return unknown90
            if plan is None:
                return f"That can only be activated if {x['text']}"
            from app.rules import conditions

            if not conditions.holds(plan, {"controller": player, "source_card": card.id, "source_object": r.object_id(card.id)},
                                    x["cond"]):  # (source_object: wave 7B, the source as it is now)
                return f"That can only be activated if {x['text']}"
    return None


def _exhaust_again(state: GameState, player: str) -> bool:
    """-- ability words (wave 4F) -- does a permanent let exhaust abilities be activated "as though they haven't been
    activated" (Elvish Refueler, 702.177b: the only such card)? That permission isn't modelled, so the engine doesn't
    refuse the activation."""
    return any((c := state.cards.get(cid)) is not None and _face_name(c) in _EXHAUST_AGAIN
               for cid in state.zones.get(f"{player}:battlefield", []))


_EXHAUST_AGAIN = frozenset({"Elvish Refueler"})


def _times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def _phase_words(phases: list[str]) -> str:
    if phases == list(_BEFORE_ATTACKERS):
        return "turn, before attackers are declared"
    names = {"upkeep": "upkeep", "end": "end step", "declare_blockers": "declare blockers step",
             "declare_attackers": "declare attackers step", "end_combat": "end of combat step"}
    if set(phases) == COMBAT_PHASES:
        return "combat"
    return " or ".join(names.get(p, p) for p in phases)


def _when(x: Restriction) -> str:
    if x.get("text"):  # (wave 7B)
        return str(x["text"])
    if x["phases"] == list(_BEFORE_ATTACKERS):
        return "before attackers are declared"
    if set(x["phases"]) == COMBAT_PHASES:
        return "during combat"
    return f"during {'your ' if x['whose'] == 'you' else 'the '}{_phase_words(x['phases'])}"
