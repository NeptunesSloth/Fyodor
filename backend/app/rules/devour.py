"""-- keyword mechanics (wave 9D) -- devour N (702.82): "As this object enters, you may sacrifice any number of creatures.
This permanent enters with N +1/+1 counters on it for each creature sacrificed this way." (702.82a), and devour
[quality] N: the same with permanents of that quality (702.82c: land, artifact, Food).

The choice is made before it enters (614.12a) like the other "as ~ enters" answers, one object per question: each
answer names a permanent to sacrifice or ends the list (``done``), and the answers pile up as one comma-separated
entering answer (``choices[WHAT]``). The sacrifice happens as it enters (:func:`sacrifice`), all at once (701.21a); the
objects can't be one entering at the same time or one another entering permanent already chose (614.13a-b). Only a
single devour instance on an object is read; the counters follow what was actually sacrificed. "If it devoured a
creature" (702.82b) is not read: those cards stay manual.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

WHAT = "devour"
DONE = "done"
_PIECE = re.compile(r"devour (?:(?P<q>land|artifact|food) )?(?P<n>\d+)")
_QUALITY_WORD = {None: "creature", "land": "land", "artifact": "artifact", "food": "Food", "creature_pw": "creature or planeswalker",
                 "nonland": "nonland permanent", "permanent": "permanent"}


def pieces(line: str) -> list[tuple[str | None, int]]:
    """The devour instances of a keyword line: (quality or None for creatures, N)."""
    out = []
    if re.fullmatch(r"devour x, where x is the number of creatures devoured this way", re.sub(r"\s*\(.*?\)", "", line).strip().rstrip(".").lower()):
        return [(None, 0)]  # (wave 48B: Thromok, "X" is how many were sacrificed: that many counters for each of them, 702.82a; N 0 stands for it)
    for p in re.split(r"[,;]\s*", re.sub(r"\s*\(.*?\)", "", line).strip().rstrip(".")):
        m = _PIECE.fullmatch(p.strip().lower())
        if m:
            out.append((m["q"], int(m["n"])))
    return out


def supported(line: str) -> bool:
    return len(pieces(line)) == 1


# -- if you do (wave 100B) -- Devouring Hellion: "As this creature enters, you may sacrifice any number of creatures and/or planeswalkers. If you do,
# it enters with twice that many +1/+1 counters on it." Devour 2 for both kinds (702.82a; the 2019-05-03 rulings: only permanents already there)
# Rescuer Sphinx: "As this creature enters, you may return a nonland permanent you control to its owner's hand. If you do, this creature enters with a
# +1/+1 counter on it." The same choice, of at most one permanent, returned instead of sacrificed (the 2019-05-03 rulings: only one already there).
_STATICS = {"As ~ enters, you may sacrifice any number of creatures and/or planeswalkers. If you do, it enters with twice that many +1/+1 counters on it.":
            ("creature_pw", 2),
            "As ~ enters, you may return a nonland permanent you control to its owner's hand. If you do, ~ enters with a +1/+1 counter on it.": ("nonland", 1),
            # -- (wave 110J) -- Shimatsu the Bloodcloaked: any number of permanents (zero allowed), one counter each (the same choice as devour 1)
            "As ~ enters, sacrifice any number of permanents. ~ enters with that many +1/+1 counters on it.": ("permanent", 1)}
RETURNS = "nonland"  # (the one quality returned to its owner's hand, at most one)


def static100b(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    return {"kind": "static", "static": "devour100b", "effects": []} if ability.kind == "static" and scripts.self_text(ability.text, ch.name) in _STATICS else None


def spec(ch: Any) -> tuple[str | None, int] | None:
    from app.rules import scripts

    found = [p for ab in ch.abilities if ab.kind == "keywords" and "devour" in ab.keywords for p in pieces(ab.text)]
    found += [_STATICS[scripts.self_text(ab.text, ch.name)] for ab in ch.abilities if static100b(ab, ch) is not None]
    return found[0] if len(found) == 1 else None


def picked(value: str | None) -> list[str]:
    return [x for x in (value or "").split(",") if x and x != DONE]


def finished(value: str | None) -> bool:
    return bool(value) and value.endswith(DONE)  # type: ignore[union-attr]


def merge(previous: str | None, chosen: str) -> str:
    """The entering answer after one more pick: the earlier picks, then this one (``done`` ends the list)."""
    return ",".join([*picked(previous), chosen])


def _matches(plan: Plan, cid: str, quality: str | None) -> bool:
    from app.rules import characteristics as chars

    ch = chars.of(plan.state.cards[cid], plan.info)
    return {None: ch.is_creature, "land": ch.is_land, "artifact": "Artifact" in ch.types,
            "food": "Food" in ch.subtypes, "creature_pw": ch.is_creature or "Planeswalker" in ch.types, "nonland": not ch.is_land, "permanent": True}[quality]


def candidates(plan: Plan, card: CardInstance, controller: str, quality: str | None, taken: set[str]) -> list[str]:
    """Permanents its controller could sacrifice: matching, on the battlefield, not the one entering (614.13a) nor one
    already picked or chosen by another entering permanent (614.13b)."""
    return [cid for cid in plan.state.zones.get(zone_key(controller, "battlefield"), [])
            if cid != card.id and cid not in taken and plan.in_game(plan.state.cards[cid]) and _matches(plan, cid, quality)]


def plan_entry(plan: Plan, card: CardInstance, controller: str, answers: dict[str, str], out: dict[str, Any],
               reserved: set[str]) -> None:
    """replacements.entry_plan's part: the next question (``out["choice"]``), or ``out["devour"]`` (what to sacrifice)."""
    if plan.manual(card):
        return
    ch = plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller}))
    found = spec(ch)
    if found is None:
        return
    value = answers.get(WHAT)
    left = candidates(plan, card, controller, found[0], {*reserved, *picked(value)})
    if not finished(value) and left and not (found[0] == RETURNS and picked(value)):
        if "choice" not in out:
            out["choice"] = {"what": WHAT, "reserved": sorted(reserved), "picked": value}
        return
    ids = [c for c in picked(value) if c in plan.state.zones.get(zone_key(controller, "battlefield"), [])]
    if ids:
        out["devour"] = ids
        if found[0] == RETURNS:
            out["devour_return"] = True
    out.setdefault("choices", {})[WHAT] = ",".join(ids) + ("," if ids else "") + DONE


def is_choice(what: str) -> bool:
    return what == WHAT


def prompt(plan: Plan, card: CardInstance, controller: str, choice: dict[str, Any]) -> tuple[str, list[DecisionOption]]:
    ch = plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller}))
    found = spec(ch)
    assert found is not None
    quality, n = found
    already = picked(choice.get("picked"))
    word = _QUALITY_WORD[quality]
    verb = "return" if quality == RETURNS else "sacrifice"
    options = [DecisionOption(id=c, label=f"{verb.capitalize()} {plan.state.cards[c].name or word}", card_id=c)
               for c in candidates(plan, card, controller, quality, {*(choice.get("reserved") or ()), *already})]
    options.append(DecisionOption(id=DONE, label=f"Done: {verb} {len(already)}" if already else f"Don't {verb} any"))
    if quality == RETURNS:
        return f"{card.name}: as it enters, return a {word} you control to its owner's hand?", options
    return (f"{card.name}: devour {n or 'X'} — as it enters, sacrifice {word}s? ({len(already)} chosen)", options)


def sacrifice(plan: Plan, ep: dict[str, Any], controller: str) -> None:
    """702.82a: the chosen permanents are sacrificed as it enters, all at once; the counters follow the ones that were."""
    ids = ep.get("devour")
    if not ids:
        return
    from app.rules.effects import _sacrifice_cards

    live = [c for c in ids if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")
            and plan.state.cards[c].controller == controller]
    was = {c: plan.oid(c) for c in live}  # (wave 48B: the answer then names the objects they were, 702.82b: "the Goblins it devoured" reads them as they last existed)
    if ep.get("devour_return"):  # (Rescuer Sphinx: to its owner's hand, 400.3)
        plan.do({"type": "move", "card_ids": live, "to": {"zone": "hand"}}, actor=controller)
    else:
        _sacrifice_cards(plan, live, controller)
    gone = [was[c] for c in live if c not in plan.state.cards or not plan.state.cards[c].zone.endswith(":battlefield")]
    ep.setdefault("choices", {})[WHAT] = ",".join(gone) + ("," if gone else "") + DONE
    if gone:
        plan.note(f"{plan.name(controller)} {'returns' if ep.get('devour_return') else 'devours'} {len(gone)} as it enters", [o.rsplit(".", 1)[0] for o in gone])


def counters(ch: Any, choices: dict[str, str] | None) -> int:
    found = spec(ch)
    n = len(picked((choices or {}).get(WHAT)))
    return (found[1] or n) * n if found is not None else 0  # (Thromok: N 0, X is how many were sacrificed)
