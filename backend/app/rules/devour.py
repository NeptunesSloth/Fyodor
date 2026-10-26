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
GY = "gy110f"  # (wave 110F) Sutured Ghoul: creature cards in the graveyard, exiled, totals as for Dracoplasm
STATS = "stats110f"  # (wave 110F) the quality of Dracoplasm: creatures, totals of their power and toughness
REV = "reveal110i"  # (wave 110I) Arsenal Thresher: other artifact cards revealed from hand, one counter each (nothing leaves the hand)
FRANK = "frank110i"  # (wave 110I) Frankenstein's Monster: exactly X creature cards from the graveyard, exiled; one +2/+0, +1/+1 or +0/+2 counter for each
FRANK_KINDS = ("+2/+0", "+1/+1", "+0/+2")
KINDS_KEY = "frank_kinds110i"  # the counter kinds chosen (they are kept apart from the picks: ``sacrifice`` rewrites those to the objects exiled)
DONE = "done"
REMOVE = "counters110c"  # (wave 110C) Sin, Unending Cataclysm: any number of artifacts, creatures and enchantments (any player's) lose all their counters
REMOVED = "removed110c"
_PIECE = re.compile(r"devour (?:(?P<q>land|artifact|food) )?(?P<n>\d+)")
_QUALITY_WORD = {None: "creature", "stats110f": "creature", "gy110f": "creature card", "land": "land", "artifact": "artifact", "food": "Food", "untapped_forest": "untapped Forest", "creature_pw": "creature or planeswalker",
                 "nonland": "nonland permanent", "reveal110i": "artifact card", "mimeo110f": "creature card", "indo110f": "creature card", "frank110i": "creature card", "permanent": "permanent", "counters110c": "permanent with counters"}


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
            "As ~ enters, sacrifice any number of untapped Forests.": ("untapped_forest", 0),  # (wave 110A: Wood Elemental, no counters: its P/T read "Forests sacrificed")
            # -- stats (wave 110F) -- Dracoplasm: sacrifice any number of creatures (no counters); its base P/T become their totals, set as it enters (:func:`apply_totals`)
            "As ~ enters, sacrifice any number of creatures. ~'s power becomes the total power of those creatures and its toughness becomes their total toughness.": (STATS, 0),
            # -- gy (wave 110F) -- Sutured Ghoul: exile creature cards from your graveyard; its P/T are their totals (the second line, _COMPANION)
            "As ~ enters, exile any number of creature cards from your graveyard.": (GY, 0),
            # -- (wave 110I) -- Frankenstein's Monster: 614.12 / 122.6, exactly X, else 614.6 it goes to the graveyard (``_frank``)
            "As ~ enters, exile X creature cards from your graveyard. If you can't, put ~ into its owner's graveyard instead of onto the battlefield. "
            "For each creature card exiled this way, ~ enters with a +2/+0, +1/+1, or +0/+2 counter on it.": (FRANK, 0),
            # -- (wave 110J) -- Shimatsu the Bloodcloaked: any number of permanents (zero allowed), one counter each (the same choice as devour 1)
            "As ~ enters, sacrifice any number of permanents. ~ enters with that many +1/+1 counters on it.": ("permanent", 1),
            # -- counters (wave 110C) -- Sin: 122.1 counters removed as it enters, twice as many +1/+1 counters (:func:`counters`)
            "As ~ enters, remove all counters from any number of artifacts, creatures, and enchantments. ~ enters with X +1/+1 counters on it, where X is twice "
            "the number of counters removed this way.": (REMOVE, 0)}
# -- Ulamog's Despoiler (wave 110H) -- "As this creature enters, you may put two cards your opponents own from exile into their owners' graveyards. If you do,
# this creature enters with four +1/+1 counters on it.": the same choice over the opponents' exiled cards; all or nothing (exactly two, 608.2c "if you do").
OPP_EXILE = "opp_exile110h"
_STATICS["As ~ enters, you may put two cards your opponents own from exile into their owners' graveyards. If you do, ~ enters with four +1/+1 counters on it."] = (OPP_EXILE, 4)
_STATICS["As ~ enters, you may reveal any number of other artifact cards from your hand. ~ enters with a +1/+1 counter on it for each card revealed this way."] = (REV, 1)
# -- same name (wave 110I) -- Sheltered Valley: the legend-rule-like replacement sacrifices every other permanent of the same name, no choice and no counters (614.1a)
SAME_NAME = "same_name110i"
_STATICS["If ~ would enter, instead sacrifice each other permanent named Sheltered Valley you control, then put ~ onto the battlefield."] = (SAME_NAME, 0)
# -- wave 110F -- Mimeoplasm, Revered One: up to X creature cards from your graveyard, exiled (the cards "exiled with it", 607.2b), three +1/+1 counters for each; Indominus Rex, Alpha:
# any number of creature cards discarded from your hand, a counter of a keyword kind for each keyword one of them has (2023-11-10 ruling: one of each kind)
MIMEO = "mimeo110f"
INDO = "indo110f"
INDO_KINDS = "indo_kinds110f"
INDO_KEYWORDS = ("flying", "first strike", "double strike", "deathtouch", "hexproof", "haste", "indestructible", "lifelink", "menace", "reach", "trample", "vigilance")
_STATICS["As ~ enters, exile up to X creature cards from your graveyard. It enters with three +1/+1 counters on it for each creature card exiled this way."] = (MIMEO, 3)
_STATICS["As ~ enters, discard any number of creature cards. It enters with a flying counter on it if a card discarded this way has flying. The same is true for first strike, "
         "double strike, deathtouch, hexproof, haste, indestructible, lifelink, menace, reach, trample, and vigilance."] = (INDO, 0)
NO_COUNTERS = {"untapped_forest", SAME_NAME}
_COMPANION = "~'s power is equal to the total power of the exiled cards and its toughness is equal to their total toughness."  # no effect of its own: apply_totals
RETURNS = "nonland"  # (the one quality returned to its owner's hand, at most one)


def static100b(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    return {"kind": "static", "static": "devour100b", "effects": []} if ability.kind == "static" and scripts.self_text(ability.text, ch.name) in (*_STATICS, _COMPANION) else None


def spec(ch: Any) -> tuple[str | None, int] | None:
    from app.rules import scripts

    found = [p for ab in ch.abilities if ab.kind == "keywords" and "devour" in ab.keywords for p in pieces(ab.text)]
    found += [_STATICS[t] for ab in ch.abilities if static100b(ab, ch) is not None and (t := scripts.self_text(ab.text, ch.name)) in _STATICS]
    return found[0] if len(found) == 1 else None


def picked(value: str | None) -> list[str]:
    return [x for x in (value or "").split(",") if x and x != DONE and x not in FRANK_KINDS]


def kinds(value: str | None) -> list[str]:
    return [x for x in (value or "").split(",") if x in FRANK_KINDS]


def finished(value: str | None) -> bool:
    return bool(value) and value.endswith(DONE)  # type: ignore[union-attr]


def merge(previous: str | None, chosen: str) -> str:
    """The entering answer after one more pick: the earlier picks, then this one (``done`` ends the list)."""
    return ",".join([*(x for x in (previous or "").split(",") if x and x != DONE), chosen])


def _matches(plan: Plan, cid: str, quality: str | None) -> bool:
    from app.rules import characteristics as chars

    ch = chars.of(plan.state.cards[cid], plan.info)
    return {None: ch.is_creature, STATS: ch.is_creature, "land": ch.is_land, "artifact": "Artifact" in ch.types,
            "food": "Food" in ch.subtypes, GY: ch.is_creature, FRANK: ch.is_creature, MIMEO: ch.is_creature, INDO: ch.is_creature, "creature_pw": ch.is_creature or "Planeswalker" in ch.types, "nonland": not ch.is_land,
            "untapped_forest": "Forest" in ch.subtypes and not plan.state.cards[cid].tapped, "permanent": True, SAME_NAME: True, REV: "Artifact" in ch.types,
            REMOVE: bool({"Artifact", "Creature", "Enchantment"} & ch.types) and any(plan.state.cards[cid].counters.values())}[quality]


def _zone(quality: str | None) -> str:
    return "graveyard" if quality in (GY, FRANK, MIMEO) else "hand" if quality in (REV, INDO) else "battlefield"


def _zone_ids(plan: Plan, controller: str, quality: str | None) -> list[str]:
    if quality == REMOVE:  # (every player's battlefield)
        return [c for p in plan.state.players for c in plan.state.zones.get(zone_key(p, "battlefield"), [])]
    return plan.state.zones.get(zone_key(controller, _zone(quality)), [])


def candidates(plan: Plan, card: CardInstance, controller: str, quality: str | None, taken: set[str]) -> list[str]:
    """Permanents its controller could sacrifice: matching, on the battlefield, not the one entering (614.13a) nor one
    already picked or chosen by another entering permanent (614.13b)."""
    if quality == OPP_EXILE:
        return [cid for pid in plan.state.seat_order if pid != controller for cid in plan.state.zones.get(zone_key(pid, "exile"), [])
                if cid not in taken and cid in plan.state.cards and not plan.state.cards[cid].is_token]
    return [cid for cid in _zone_ids(plan, controller, quality)
            if cid != card.id and cid not in taken and plan.in_game(plan.state.cards[cid]) and _matches(plan, cid, quality)]


def _frank(plan: Plan, card: CardInstance, controller: str, answers: dict[str, str], out: dict[str, Any], reserved: set[str]) -> None:
    """Frankenstein's Monster: X is the X paid (107.3: 0 when it is not a spell being cast). With fewer than X creature cards in the graveyard it can't exile them: it doesn't enter
    (614.6, ``out["divert"]``). Otherwise its controller picks exactly X, then a counter kind for each (122.6)."""
    need = max(0, int((card.stack_info.x if card.stack_info else 0) or 0))
    value = answers.get(WHAT)
    pool = candidates(plan, card, controller, FRANK, reserved)
    if len(pool) < need:
        out["divert"] = True
        out.pop("choice", None)
        return
    ids, chosen_kinds = [c for c in picked(value) if c in pool], kinds(value) or kinds(answers.get(KINDS_KEY))
    if len(ids) < need or len(chosen_kinds) < need:
        if "choice" not in out:
            out["choice"] = {"what": WHAT, "reserved": sorted(reserved), "picked": value, "x110i": need}
        return
    out["devour"] = ids[:need]
    out["devour_exile"] = True
    out.setdefault("choices", {})[WHAT] = ",".join([*ids[:need], *chosen_kinds[:need], DONE])  # (the kinds stay in the answer: a later look at it asks nothing more)
    out["choices"][KINDS_KEY] = ",".join(chosen_kinds[:need])


def typed(ch: Any, choices: dict[str, str] | None) -> dict[str, int]:
    """The counters Frankenstein's Monster enters with: one of the chosen kind for each card exiled."""
    found = spec(ch)
    out: dict[str, int] = {}
    if found is not None and found[0] == FRANK:
        for k in kinds((choices or {}).get(KINDS_KEY)):
            out[k] = out.get(k, 0) + 1
    if found is not None and found[0] == INDO:  # -- wave 110F -- a counter of each kind (a keyword counter grants the keyword, 122.1b)
        for k in ((choices or {}).get(INDO_KINDS) or "").split(","):
            if k:
                out[k] = 1
    return out


def plan_entry(plan: Plan, card: CardInstance, controller: str, answers: dict[str, str], out: dict[str, Any],
               reserved: set[str]) -> None:
    """replacements.entry_plan's part: the next question (``out["choice"]``), or ``out["devour"]`` (what to sacrifice)."""
    if plan.manual(card):
        return
    ch = plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller}))
    found = spec(ch)
    if found is None:
        return
    if found[0] == SAME_NAME:
        ids = [c for c in candidates(plan, card, controller, SAME_NAME, reserved) if plan.ch(plan.state.cards[c]).name == ch.name]
        if ids:
            out["devour"] = ids
        out.setdefault("choices", {})[WHAT] = ",".join(ids) + ("," if ids else "") + DONE
        return
    if found[0] == FRANK:
        _frank(plan, card, controller, answers, out, reserved)
        return
    value = answers.get(WHAT)
    left = candidates(plan, card, controller, found[0], {*reserved, *picked(value)})
    two = found[0] == OPP_EXILE
    cap = max(0, int((card.stack_info.x if card.stack_info else 0) or 0)) if found[0] == MIMEO else None  # (up to X: X as cast, 107.3m)
    if found[0] == INDO and not value:
        left = left or ["asked"]  # (always asked once: whether a hand holds a creature card is nobody else's information, as for amplify)
    if not finished(value) and left and not (found[0] == RETURNS and picked(value)) and not (two and len(picked(value)) >= 2) and not (cap is not None and len(picked(value)) >= cap):
        if "choice" not in out:
            out["choice"] = {"what": WHAT, "reserved": sorted(reserved), "picked": value}
        return
    ids = [c for c in picked(value) if c in _zone_ids(plan, controller, found[0])]
    if two:  # exactly two, still in their owners' exile
        ids = [c for c in picked(value) if c in plan.state.cards and plan.state.cards[c].zone.endswith(":exile")]
        ids = ids if len(ids) == 2 else []
    if ids:
        out["devour"] = ids
        if found[0] == REMOVE:
            out["devour_remove"] = True
        if found[0] in (GY, MIMEO):
            out["devour_exile"] = True
        if found[0] == INDO:
            out["devour_discard"] = True
        if found[0] == REV:
            out["devour_reveal"] = True
        if found[0] == RETURNS:
            out["devour_return"] = True
        if two:
            out["devour_opp110h"] = True  # (its own key: Sutured Ghoul's and Frankenstein's Monster's ``devour_exile`` exile from the graveyard)
    out.setdefault("choices", {})[WHAT] = ",".join(ids) + ("," if ids else "") + DONE


def is_choice(what: str) -> bool:
    return what == WHAT


def prompt(plan: Plan, card: CardInstance, controller: str, choice: dict[str, Any]) -> tuple[str, list[DecisionOption]]:
    ch = plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller}))
    found = spec(ch)
    assert found is not None
    quality, n = found
    already = picked(choice.get("picked"))
    if quality == OPP_EXILE:  # (a face-down exiled card stays hidden: no name, no card id, 406.3)
        opts = [DecisionOption(id=c, label=f"Put {plan.state.cards[c].name or 'a card'} into a graveyard" if not plan.state.cards[c].face_down else "Put a face-down card into a graveyard",
                               **({} if plan.state.cards[c].face_down else {"card_id": c}))
                for c in candidates(plan, card, controller, quality, {*(choice.get("reserved") or ()), *already})]
        opts.append(DecisionOption(id=DONE, label="Don't"))
        return f"{card.name}: as it enters, put two cards your opponents own from exile into their graveyards? ({len(already)} of 2 chosen)", opts
    if quality == FRANK:
        need = int(choice.get("x110i") or 0)
        if len(already) < need:
            return (f"{card.name}: as it enters, exile a creature card from your graveyard ({len(already)} of {need})",
                    [DecisionOption(id=c, label=f"Exile {plan.state.cards[c].name or 'creature card'}", card_id=c)
                     for c in candidates(plan, card, controller, FRANK, {*(choice.get("reserved") or ()), *already})])
        return (f"{card.name}: choose the counter for exiled card {len(kinds(choice.get('picked'))) + 1} of {need}",
                [DecisionOption(id=k, label=f"{k} counter") for k in FRANK_KINDS])
    word = _QUALITY_WORD.get(quality, "card")
    verb = "return" if quality == RETURNS else "exile" if quality in (GY, MIMEO) else "discard" if quality == INDO else "reveal" if quality == REV else "remove counters from" if quality == REMOVE else "sacrifice"
    options = [DecisionOption(id=c, label=f"{verb.capitalize()} {plan.state.cards[c].name or word}", card_id=c)
               for c in candidates(plan, card, controller, quality, {*(choice.get("reserved") or ()), *already})]
    options.append(DecisionOption(id=DONE, label=f"Done: {verb} {len(already)}" if already else f"Don't {verb} any"))
    if quality == RETURNS:
        return f"{card.name}: as it enters, return a {word} you control to its owner's hand?", options
    if quality == REV:
        return f"{card.name}: as it enters, reveal artifact cards from your hand? ({len(already)} chosen)", options
    if quality == REMOVE:
        return f"{card.name}: as it enters, remove all counters from permanents? ({len(already)} chosen)", options
    if quality in NO_COUNTERS:
        return f"{card.name}: as it enters, sacrifice any number of {word}s? ({len(already)} chosen)", options
    if quality in (GY, MIMEO):
        return f"{card.name}: as it enters, exile creature cards from your graveyard? ({len(already)} chosen)", options
    if quality == INDO:
        return f"{card.name}: as it enters, discard creature cards? ({len(already)} chosen)", options
    if quality == STATS:
        return f"{card.name}: as it enters, sacrifice creatures? ({len(already)} chosen)", options
    return (f"{card.name}: devour {n or 'X'} — as it enters, sacrifice {word}s? ({len(already)} chosen)", options)


def sacrifice(plan: Plan, ep: dict[str, Any], controller: str) -> None:
    """702.82a: the chosen permanents are sacrificed as it enters, all at once; the counters follow the ones that were."""
    ids = ep.get("devour")
    if not ids:
        return
    if ep.get("devour_opp110h"):
        was = {c: plan.oid(c) for c in ids if c in plan.state.cards}
        plan.do({"type": "move", "card_ids": list(was), "to": {"zone": "graveyard"}}, actor=controller)  # (their owners' graveyards, 400.3)
        ep.setdefault("choices", {})[WHAT] = ",".join(was.values()) + ("," if was else "") + DONE
        ep["choices"][TOTALS] = "0,0"
        return
    from app.rules.effects import _sacrifice_cards

    if ep.get("devour_reveal"):  # 701.20a: revealing moves nothing; the cards stay in hand and the reveal is public (the counters follow the count)
        ep.setdefault("choices", {})[WHAT] = ",".join(ids) + ",done"
        plan.note(f"{plan.name(controller)} reveals {len(ids)} artifact card(s) from hand", ids)
        return
    if ep.get("devour_remove"):  # 122.1: only the counters really removed are counted ("this way")
        removed = 0
        for c in ids:
            card = plan.state.cards.get(c)
            if card is not None and card.zone.endswith(":battlefield"):
                before = sum(card.counters.values())
                for kind, n in list(card.counters.items()):
                    if n > 0:
                        plan.do({"type": "counter", "card_ids": [c], "kind": kind, "delta": -n}, actor=controller)
                removed += before - sum(plan.state.cards[c].counters.values())
        ep.setdefault("choices", {})[WHAT] = ",".join(ids) + "," + DONE
        ep["choices"][REMOVED] = str(removed)
        return
    if ep.get("devour_discard"):  # -- wave 110F -- Indominus Rex, Alpha: discarded (701.9), the keywords the cards had in hand are the counters' kinds (one of each, 2023-11-10 ruling)
        from app.rules import characteristics as chars
        from app.rules.effects import _discard_next

        hand = [c for c in ids if c in plan.state.cards and plan.state.cards[c].zone == zone_key(controller, "hand")]
        kws = [k for k in INDO_KEYWORDS if any(k in chars.of(plan.state.cards[c], plan.info).keywords for c in hand)]
        was_hand = {c: plan.oid(c) for c in hand}
        if hand:
            plan.note(f"As it enters, {plan.name(controller)} discards {len(hand)} creature card(s)", hand)
            _discard_next(plan, {"controller": controller, "effects": [], "next": 0}, 0, [], hand)
        gone = [was_hand[c] for c in hand if c in plan.state.cards and plan.state.cards[c].zone.endswith(":graveyard")]
        ep.setdefault("choices", {})[WHAT] = ",".join(gone) + ("," if gone else "") + DONE
        ep["choices"][INDO_KINDS] = ",".join(kws)
        return
    exile = bool(ep.get("devour_exile"))  # (wave 110F: Sutured Ghoul, from the graveyard)
    live = [c for c in ids if c in plan.state.cards and (plan.state.cards[c].zone == zone_key(controller, "graveyard") if exile else
            plan.state.cards[c].zone.endswith(":battlefield") and plan.state.cards[c].controller == controller)]
    totals = [sum(int((plan.ch(plan.state.cards[c]).pt or (0, 0))[i] or 0) for c in live) for i in (0, 1)]  # (wave 110F: Dracoplasm's totals, as they were)
    was = {c: plan.oid(c) for c in live}  # (wave 48B: the answer then names the objects they were, 702.82b: "the Goblins it devoured" reads them as they last existed)
    if exile:
        plan.do({"type": "move", "card_ids": live, "to": {"zone": "exile"}}, actor=controller)
    elif ep.get("devour_return"):  # (Rescuer Sphinx: to its owner's hand, 400.3)
        plan.do({"type": "move", "card_ids": live, "to": {"zone": "hand"}}, actor=controller)
    else:
        _sacrifice_cards(plan, live, controller)
    gone = [was[c] for c in live if c not in plan.state.cards
            or (plan.state.cards[c].zone.endswith(":exile") if exile else not plan.state.cards[c].zone.endswith(":battlefield"))]
    ep.setdefault("choices", {})[WHAT] = ",".join(gone) + ("," if gone else "") + DONE
    ep["choices"][TOTALS] = f"{totals[0]},{totals[1]}"
    if gone:
        plan.note(f"{plan.name(controller)} {'returns' if ep.get('devour_return') else 'devours'} {len(gone)} as it enters", [o.rsplit(".", 1)[0] for o in gone])


def counters(ch: Any, choices: dict[str, str] | None) -> int:
    found = spec(ch)
    if found is not None and found[0] == REMOVE:
        return 2 * int((choices or {}).get(REMOVED) or 0)
    n = len(picked((choices or {}).get(WHAT)))
    if found is not None and found[0] == OPP_EXILE:
        return found[1] if n == 2 else 0
    return 0 if found is None or found[0] in NO_COUNTERS or found[0] in (STATS, GY, FRANK, INDO) else (found[1] or n) * n  # (Thromok: N 0, X is how many were sacrificed)


TOTALS = "devour_pt110f"


def linked(plan: Plan, card_id: str, controller: str, choices: dict[str, str] | None) -> None:
    """-- wave 110F -- Mimeoplasm, Revered One: the cards exiled as it entered are "exiled with it" (607.2b: a replacement effect that exiles), recorded under the permanent it became."""
    card = plan.state.cards.get(card_id)
    if card is None or not choices or WHAT not in choices:
        return
    found = spec(plan.ch(card))
    if found is None or found[0] != MIMEO:
        return
    from app.rules import exiled_with

    ids = [o.rsplit(".", 1)[0] for o in picked(choices[WHAT])]
    exiled_with.record(plan, {"controller": controller, "source_card": card_id, "source_object": plan.oid(card)}, [c for c in ids if c in plan.state.cards])


def apply_totals(plan: Plan, card: CardInstance, ch: Any, choices: dict[str, str] | None) -> None:
    """Dracoplasm: "~'s power becomes the total power of those creatures and its toughness becomes their total toughness" -- a base P/T effect
    (613.4b, layer 7b) with the amounts fixed as it entered (the creatures as they were when sacrificed, 608.2h); no sacrifice: 0/0."""
    found = spec(ch)
    if found is None or found[0] not in (STATS, GY):
        return
    from app.rules import layers

    power, toughness = (int(x) for x in ((choices or {}).get(TOTALS) or "0,0").split(","))
    layers.add_effect(plan, affected=[plan.oid(card)], layer="7b", source=None, controller=card.controller, power=power, toughness=toughness,
                      duration="permanent", label=f"Base power and toughness {power}/{toughness} ({card.name})")
