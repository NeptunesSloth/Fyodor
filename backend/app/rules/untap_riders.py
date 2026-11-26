"""-- mana riders (wave 5A) -- untapping as a rider, researched against CR 2026-09-25.

1. "Untap up to three lands." (Frantic Search, Snap, Rewind, Unwind, Peregrine Drake, Cloud of Faeries, Treachery,
   Palinchron; "You untap up to six lands." Time Spiral; "untap up to three lands you control.")
   * Not a target (115.1: no "target"): as the instruction is carried out the controller chooses up to that many
     lands (608.2c; any lands, any controller's, unless "you control" says so) and untaps them (701.26b: only tapped
     ones can be untapped, so only tapped lands are offered — choosing an untapped one would do nothing).
   * 122.1d: a stunned land loses a stun counter instead (app/rules/keyword_actions.untap_stunned).
2. "Untap all permanents you control during each other player's untap step." (Seedborn Muse, Unwinding Clock,
   Drumbellower, Murkfiend Liege, Ohabi Caleria; "Untap this artifact during …" Bender's Waterskin, Endbringer).
   * 502.3: in the untap step the active player untaps their permanents; these statics untap their controller's
     matching permanents at that same time, in each untap step that isn't their controller's own (Seedborn ruling
     2007-07-15: no choice about what untaps). A skipped untap step (614.10) doesn't happen at all, so nothing untaps.
   * "doesn't untap during its controller's / your untap step" doesn't apply then: it isn't that player's untap step
     (Seedborn ruling 2004-10-04) — so the engine's keep-tapped list for the active player isn't used here.
   * 122.1d: a stunned permanent loses a stun counter instead of untapping.
   * 800.4a: a player who left the game controls nothing any more (``plan.live()``).

Nothing from a card is executed: the selectors are app/rules/selectors.py keys.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
_UNTAP_UP_TO = re.compile(r"^(?:you )?untap up to (?P<n>one|two|three|four|five|six|seven|eight) lands(?P<y> you control)?$")
# -- trigger other (wave 25B) -- "Untap a land you control." (an exact choice of one: 608.2c), "Untap a creature you control.", and the
# player doing it: "that player untaps a land they control." (Hokori, Rising Waters: that player chooses, 608.2d)
_UNTAP_ONE = re.compile(r"^(?:(?P<who>you|that player) )?untaps? (?:an?|one) (?P<k>land|creature)(?P<y> (?:you|they) control)?$")
_OTHER_STEP = re.compile(r"^Untap (?:(?P<self>this (?:artifact|creature|permanent|land|enchantment)|~)|(?:all|each) (?P<sel>.+?)) "
                         r"during each other player's untap step\.$")
STATIC = "untap_other_steps"


# -- 1. "Untap up to N lands." ---------------------------------------------------------------------------------------
def _template(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import selectors

    sel = selectors.parse("tapped lands you control" if m["y"] else "tapped lands")
    assert sel is not None
    return [{"do": "untap_choice", "n": _N[m["n"]], "sel": sel.key()}], None


# "Draw three cards, untap up to two lands, then discard a card." (Pore Over the Pages: a list of three instructions;
# the ", then" is split first, scripts._clause)
_DRAW_AND_UNTAP = re.compile(r"^draw (?P<d>one|two|three|four|five) cards?, untap up to (?P<n>one|two|three|four|five|six|seven|eight) "
                             r"lands$")


def _draw_and_untap(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    untap, _ = _template(_UNTAP_UP_TO.match(f"untap up to {m['n']} lands"))  # type: ignore[arg-type]
    return [{"do": "draw", "who": "you", "n": _N[m["d"]]}, *untap], None


def _untap_one(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import selectors

    if m["who"] == "that player" and not m["y"]:
        from app.rules.scripts import _NoMatch

        raise _NoMatch  # (whose lands? only "they control" is read)
    sel = selectors.parse(f"tapped {m['k']}s you control" if m["y"] else f"tapped {m['k']}s")  # ("you" is the one who chooses)
    assert sel is not None
    return [{"do": "untap_choice", "n": 1, "sel": sel.key(), "exact": True, "kind": m["k"],
             **({"who": "that_player"} if m["who"] == "that player" else {})}], None


# -- wave 110C -- "untap up to X lands, where X is the greatest power among those creatures" (Shriekwood Devourer): X is the attack batch's
# greatest power (values _EVENT_GROUP, 608.2h), read when the choice opens; the lands are any lands (115.1: no target)
_UNTAP_X = re.compile(r"^untap up to X lands, where X is (?P<v>the greatest power among those creatures)$")


def _untap_x(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    from app.rules import selectors, values

    sel = selectors.parse("tapped lands")
    assert sel is not None
    return [{"do": "untap_choice", "n": values.parse_count(m["v"]), "sel": sel.key()}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_UNTAP_X, _untap_x), (_UNTAP_UP_TO, _template), (_DRAW_AND_UNTAP, _draw_and_untap), (_UNTAP_ONE, _untap_one)]


def untap_choice(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The controller chooses up to ``n`` of the tapped lands that match and untaps them. False while the choice is open."""
    from app.game.rules_state import DecisionOption
    from app.rules import selectors
    from app.rules.effects import _players
    from app.rules.plan import decide

    chosen_by = _players(plan, ctx, e["who"]) if e.get("who") else [ctx["controller"]]  # (wave 25B: "that player untaps …")
    if not chosen_by:
        return True
    you = chosen_by[0]
    found = [c for c in selectors.candidates(plan, selectors.from_key(e["sel"]), you, ctx.get("source_card"))
             if plan.state.cards[c].tapped and plan.state.cards[c].zone.endswith(":battlefield")]
    if not found:
        return True
    if isinstance(e["n"], dict):  # (wave 110C: a value, fixed once so the answer needs no event)
        from app.rules import values

        e = {**e, "n": values.evaluate(plan, ctx, e["n"])}
    n = min(int(e["n"]), len(found))
    if n <= 0:
        return True
    noun = {"land": "lands", "permanent": "permanents"}.get(e.get("kind", "land"), "creatures")
    decide(plan, player=you, kind="choose_cards",
           prompt=f"{ctx.get('name', '') or 'Untap'}: untap " + (f"{n} {noun[:-1]}" if e.get("exact") else f"up to {e['n']} {noun}"),
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or noun[:-1].title(), card_id=c) for c in found],
           min_choices=n if e.get("exact") else 0, max_choices=n, resume={"step": "untap_choice", "ctx": ctx, "e": e, "chooser": you})
    return False


def resume_untap_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import keyword_actions, selectors
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    sel = selectors.from_key(e["sel"])
    chooser = d.resume.get("chooser") or ctx["controller"]  # (wave 25B: "that player untaps a land they control")
    picked = list(dict.fromkeys(chosen))[: int(e["n"])]
    cards = [c for c in picked if (card := plan.state.cards.get(c)) is not None and card.tapped
             and card.zone.endswith(":battlefield") and selectors.matches(plan, sel, card, plan.ch(card), chooser)]
    cards = keyword_actions.untap_stunned(plan, cards, chooser)  # 122.1d
    if cards:
        plan.do({"type": "tap", "card_ids": cards, "tapped": False}, actor=chooser)
    continue_effects(plan, ctx)


# -- 2. "… during each other player's untap step." ----------------------------------------------------------------------
def static_definition(text: str) -> dict[str, Any] | None:
    from app.rules import selectors

    m = _OTHER_STEP.match(text.strip())
    if m is None:
        return None
    if m["self"]:
        return {"kind": "static", "static": STATIC, "sel": "self", "effects": []}
    phrase = m["sel"].replace(" and/or ", " or ")  # ("green and/or blue creatures": either color)
    phrase = re.sub(r"^(?P<a>[a-z]+s) and (?P<b>[a-z]+s) you control$", r"\g<a> or \g<b> you control", phrase)  # (each kind)
    if not phrase.endswith(" you control") and " you control " not in phrase:
        return None
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or sel.zones not in ((), ("battlefield",)) or '"controller":"you"' not in sel.key():
        return None
    return {"kind": "static", "static": STATIC, "sel": sel.key(), "effects": []}


def other_untap_step(plan: Plan) -> None:
    """502.3: in the active player's untap step, each other player's permanents these statics name untap too."""
    from app.rules import keyword_actions, scripts, selectors, statics

    active = plan.active
    live = plan.live()
    found: list[str] = []
    with plan.reading():  # -- big boards (step scans) -- read-only: each permanent derived once
        for key, ids in list(plan.state.zones.items()):
            if not key.endswith(":battlefield"):
                continue
            for cid in ids:
                src = plan.state.cards[cid]
                if src.controller == active or src.controller not in live or src.face_down or plan.manual(src):
                    continue
                ch = plan.ch(src)
                for d in scripts.definitions(ch).values():
                    if d.get("static") != STATIC:
                        continue
                    if not statics.conditions_hold(plan, d, source=src, controller=src.controller):
                        continue
                    if d["sel"] == "self":
                        found.append(src.id)
                        continue
                    sel = selectors.from_key(d["sel"])
                    found += [c for c in selectors.candidates(plan, sel, src.controller, src.id)
                              if plan.state.cards[c].controller == src.controller]
    cards = [c for c in dict.fromkeys(found) if plan.state.cards[c].tapped and plan.state.cards[c].zone.endswith(":battlefield")]
    if not cards:
        return
    cards = keyword_actions.untap_stunned(plan, cards, active)  # 122.1d
    if cards:
        plan.do({"type": "tap", "card_ids": cards, "tapped": False}, actor=active)
