"""-- refused grants/replacements (wave 3R2) -- Skipping steps, phases and turns (614.10). Researched
against the Comprehensive Rules of 2026-09-25 (data/rules/comprehensive_rules/).

* 614.10: an effect that makes a player skip a step, phase or turn is a replacement effect: "skip
  [something]" is "instead of doing [something], do nothing". Once a step, phase or turn has
  started it can't be skipped: a skip effect waits for the next occurrence (a one-shot "skips their
  next untap step" recorded during an untap step skips the next one).
* 614.10a: anything scheduled for a skipped step, phase or turn doesn't happen (its turn-based
  actions, its "at the beginning of" triggers, priority in it); anything scheduled for the "next"
  occurrence waits for the first one that isn't skipped — so a static ability that skips the
  occurrence ("Players skip their untap steps.", Stasis) is applied first and a one-shot "next
  occurrence" effect waits; two one-shot effects skip the next two occurrences (one each).
* 500.4 / 611.2: a skipped turn never begins, so "until your next turn" effects don't end with it
  and it isn't "your next turn" for anything.

Wordings (anything else stays manual):

* statics: "Skip your draw step." / "Skip your upkeep step." / "Skip your untap step." (Wild
  Wasteland, Necropotence's first line), "Players skip their untap steps." (Stasis), "Players skip
  their upkeep steps." (Eon Hub), "Each player skips their untap step." (Sands of Time);
* effects: "[You | Target player | Target opponent | That player | Each opponent | Each player]
  skip[s] [your | their] next [two | three] [untap step | upkeep | upkeep step | draw step | combat
  phase | turn(s)]" (Stonehorn Dignitary, Fatigue, Eater of Days, Chronatog, Blinding Angel), and
  the imperative "Skip your next turn." (Magosi, the Waterveil).

Exact turn-scoped spell and upkeep-choice wordings are admitted by phase_skips88.
Other unsupported wordings, including conditional statics and skipping X turns, stay manual.
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
Definition = dict[str, Any]

_WHAT = {"untap step": "untap", "upkeep step": "upkeep", "upkeep": "upkeep", "draw step": "draw", "combat phase": "combat",
         "turn": "turn", "turns": "turn"}
_LABEL = {"untap": "untap step", "upkeep": "upkeep step", "draw": "draw step", "combat": "combat phase", "turn": "turn", "main": "main phase"}

# -- statics ---------------------------------------------------------------------------------------------
_STATIC_YOU = re.compile(r"Skip your (?P<what>untap step|upkeep step|draw step)\.")
_STATIC_ALL = re.compile(r"(?:Players skip their (?P<a>untap|upkeep|draw) steps|Each player skips their (?P<b>untap|upkeep|draw) step)\.")


# -- most-played cards IV (wave 51G) -- "If an opponent would begin an extra turn, that player skips that turn instead." (Stranglehold), "If a player would begin an extra turn, …"
# (Ugin's Nexus): a replacement of the extra turn as it would begin (614.10, 500.7), read by extra_turns.take
_STATIC_EXTRA = re.compile(r"If (?P<w>a player|an opponent) would begin an extra turn, that player skips that turn instead\.")


def static_definition(text: str) -> Definition | None:
    if (e := _STATIC_EXTRA.fullmatch(text.strip())) is not None:
        return {"kind": "static", "static": "skip", "what": "extra_turn", "who": "each" if e["w"] == "a player" else "opponents", "effects": []}
    m = _STATIC_YOU.fullmatch(text.strip())
    if m:
        return {"kind": "static", "static": "skip", "what": _WHAT[m["what"]], "who": "you", "effects": []}
    m = _STATIC_ALL.fullmatch(text.strip())
    if m:
        return {"kind": "static", "static": "skip", "what": m["a"] or m["b"], "who": "each", "effects": []}
    return None


# -- effects (first letter lower-cased, no final period) ------------------------------------------------
_N = {"two": 2, "three": 3}
_SKIP = re.compile(r"(?P<who>you|target player|target opponent|that player|each opponent|each player) skips? "
                   r"(?:your|their) next (?:(?P<n>two|three) )?(?P<what>untap step|upkeep step|upkeep|draw step|combat phase|turns?)")
_IMPERATIVE = re.compile(r"skip your next (?:(?P<n>two|three) )?(?P<what>untap step|upkeep step|upkeep|draw step|combat phase|turns?)")


def _build(who: str, n: str | None, what: str) -> tuple[list[dict[str, Any]], str | None]:
    if (what == "turns") != (n is not None):
        from app.rules.scripts import _NoMatch

        raise _NoMatch
    key = {"you": "you", "target player": "target", "target opponent": "target", "that player": "event_player",
           "each opponent": "each_opponent", "each player": "each_player"}[who]
    sel = {"target player": "player", "target opponent": "opponent"}.get(who)
    return [{"do": "skip_next", "who": key, "what": _WHAT[what], "n": _N.get(n or "", 1)}], sel


def _skip(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return _build(m["who"], m["n"], m["what"])


def _imperative(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return _build("you", m["n"], m["what"])


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [
    (re.compile("^" + _SKIP.pattern + "$"), _skip),
    (re.compile("^" + _IMPERATIVE.pattern + "$"), _imperative),
]


def skip_next(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Record the skips: each waits for the player's next occurrence of that step, phase or turn
    (614.10: one that already started isn't it)."""
    from app.rules.effects import _players

    name = ctx.get("name") or "An effect"
    for pid in _players(plan, ctx, e["who"]):
        for _ in range(int(e.get("n") or 1)):
            plan.rules.skips.append({"id": secrets.token_hex(4), "player": pid, "what": e["what"], "label": name, **({"turn": plan.state.turn.number} if e.get("this_turn") else {}), **({"next_turn88": plan.state.turn.number} if e.get("next_turn88") else {}), **({"repeat88": True} if e.get("repeat88") else {})})
        n = int(e.get("n") or 1)
        what = _LABEL[e["what"]] + ("s" if n > 1 else "")
        timing = f"their {what} this turn" if e.get("this_turn") else f"their next {f'{n} ' if n > 1 else ''}{what}"
        plan.note(f"{plan.name(pid)} will skip {timing} ({name}, 614.10)", actor=ctx["controller"])
    return True


# -- the turn structure asks ------------------------------------------------------------------------------
def _static(plan: Plan, player: str, what: str) -> str | None:
    from app.rules import scripts
    from app.rules.replace import conditional_lines

    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        if "Room" in ch.subtypes:
            continue  # (a Room door is unlocked or not: not modelled)
        skip = conditional_lines(ch)  # (a leveler's / Class's level lines: the level isn't tracked)
        for i, d in scripts.definitions(ch).items():
            if i not in skip and d.get("kind") == "static" and d.get("static") == "skip" and d.get("what") == what \
                    and (d.get("who") == "each" or (c.controller != player if d.get("who") == "opponents" else c.controller == player)):
                return plan.ch(c).name or c.name or "a permanent"
    return None


def take(plan: Plan, player: str, what: str) -> str | None:
    """Is ``player``'s ``what`` (about to begin) skipped? The name of the effect that skips it, or
    None. A static ability skips it first (614.10a); otherwise the oldest one-shot effect waiting
    for this occurrence is used up."""
    if player not in plan.live():
        return None
    plan.rules.skips[:] = [rec for rec in plan.rules.skips if rec.get("turn", plan.state.turn.number) == plan.state.turn.number]
    found = _static(plan, player, what) if what != "turn" else None
    if found is not None:
        return found
    r = plan.rules
    # An all-instance turn restriction skips the occurrence before a waiting
    # one-shot next-occurrence effect can be satisfied (614.10a).
    for i, rec in sorted(enumerate(r.skips), key=lambda pair: not pair[1].get("repeat88")):
        if rec.get("player") == player and rec.get("what") == what and "next_turn88" not in rec:
            if not rec.get("repeat88"):
                del r.skips[i]
            return str(rec.get("label") or "an effect")
    return None


def next_active(plan: Plan, after: str | None = None) -> str | None:
    """614.10: the player whose turn begins next when the next player's turn (and maybe more) is
    skipped — None when no turn is skipped."""
    nxt = plan.after(after or plan.active)  # (-- extra turns (wave 8A) -- after the player whose regular turn it was)
    skipped = False
    for _ in range(64):
        label = take(plan, nxt, "turn")
        if label is None:
            break
        plan.note(f"{plan.name(nxt)} skips their turn ({label}, 614.10)", actor=plan.active)
        skipped = True
        nxt = plan.after(nxt)
    return nxt if skipped else None


def untap_skipped(plan: Plan, player: str) -> list[str] | None:
    """614.10: the untap step of ``player``'s turn about to begin is skipped — the permanents that
    then stay tapped (none of theirs untap: 502.3) — or None."""
    label = take(plan, player, "untap")
    if label is None:
        return None
    plan.note(f"{plan.name(player)} skips their untap step ({label}, 614.10)", actor=plan.active)
    return [c.id for c in plan.state.cards.values() if c.tapped and c.controller == player and c.zone.endswith(":battlefield")]


def skip_steps(plan: Plan) -> None:
    """The step (or the combat phase) the turn just moved into is skipped: on to the next one, with
    nothing of it happening (614.10a)."""
    for _ in range(4 + len(plan.rules.extra_steps) + len(plan.rules.extra_phases)):
        # Every actual turn advances through this boundary, including turns whose
        # relevant phase is absent/skipped. Bind waiting effects to that first
        # actual next turn, so a turn with no combat never leaks to a later turn.
        for rec in plan.rules.skips:
            if rec.get('player') == plan.active and 'next_turn88' in rec and plan.state.turn.number > rec['next_turn88']:
                rec['turn'] = plan.state.turn.number
                del rec['next_turn88']
        phase = plan.state.turn.phase
        what = {"upkeep": "upkeep", "draw": "draw", "begin_combat": "combat", "main1": "main", "main2": "main"}.get(phase)
        if what is None:
            return
        label = take(plan, plan.active, what)
        if label is None:
            return
        plan.note(f"{plan.name(plan.active)} skips their {_LABEL[what]} ({label}, 614.10)", actor=plan.active)
        to = "next"
        r = plan.rules
        inserted = r.extra_steps.pop(0) if r.extra_steps else None
        if inserted is not None and inserted != "phase":
            to = inserted
        elif inserted == "phase" or what in ("combat", "main") or (what == "upkeep" and r.upkeep_only) or (what == "draw" and r.extra_beginning):
            from app.rules import combat_rules

            fallback = "begin_combat" if what == "main" and phase == "main1" else "end" if what == "main" else "main2" if what == "combat" or r.upkeep_only else "end" if r.extra_beginning else "main1"
            to = combat_rules.next_phase(plan) or fallback
            r.extra_beginning = to == "untap"
            r.upkeep_only = to == "upkeep" and r.combat_tag == "upkeep_only"
        plan.do({"type": "phase", "to": to, "force": True}, actor=plan.active)


PRIMITIVES = {"skip_next": skip_next}
