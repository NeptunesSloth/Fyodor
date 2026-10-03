"""-- name search (wave 11D) -- "Exile target creature. Search its controller's graveyard, hand, and library for all cards with
the same name as that creature and exile them. Then that player shuffles." (Eradicate, Splinter, Counterbore, Quash, Sowing
Salt, Crumble to Dust, Scour) and "Choose target card in a graveyard other than a basic land card. Search its owner's
graveyard, hand, and library for [all / any number of] cards with the same name as that card and exile them. Then that
player shuffles." (Extirpate, Surgical Extraction).

Read against the Comprehensive Rules:
* 201.2 — the name is the one the object had (its last known information once it left, 608.2h: a token that was exiled
  has ceased to exist, but the name it had is what is searched for).
* 701.23a/b — the ability's controller searches the other player's graveyard, hand and library. They are hidden zones:
  nobody but the searcher learns what is there. The searcher chooses, privately, among the matches: "all cards" names a
  quality, so they may find fewer (701.23b: a review of wave 11D; "any number of" says so itself). That decision is
  asked even when there are no matches, so its timing says nothing.
* 701.24 — the searched player (the library's owner) shuffles afterwards, whether or not anything was found.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.rules.effects import Context
    from app.rules.plan import Plan

_PLAIN_EXTIRPATE = re.compile(r"Choose target card in a graveyard other than a basic land card\. Search its owner's graveyard, hand, "
                              r"and library for (all|any number of) cards with the same name as that card and exile them\. "
                              r"Then that player shuffles\.")
_SHUFFLE_TAIL = re.compile(r"(and exile them)\. Then that player shuffles\.")
ZONES = ("graveyard", "hand", "library")
PATTERN = (r"search (?:(?P<pron>its controller's|its owner's) graveyard, hand, and library|the graveyard, hand, and library of the "
           r"owner of (?P<t>target nonbasic card in a graveyard)) for (?P<q>all|any number of) cards with the same name as "
           r"that (?:card|spell|creature|land|artifact|enchantment|permanent) and exile them, then that player shuffles")


def rewrite(body: str) -> str:
    """The two sentences about one search read as one: Extirpate's "choose target card" names the target the search is
    about, and "Then that player shuffles" is part of the same instruction."""
    body = _PLAIN_EXTIRPATE.sub(lambda m: f"Search the graveyard, hand, and library of the owner of target nonbasic card in a graveyard "
                                          f"for {m[1]} cards with the same name as that card and exile them, then that player shuffles.",
                                body)
    return _SHUFFLE_TAIL.sub(r"\1, then that player shuffles.", body)


def build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language

    by = "owner" if m["t"] or m["pron"] == "its owner's" else "controller"
    group = language.target_group(m["t"]) if m["t"] else None
    return [{"do": "name_search", "by": by, "all": m["q"] == "all"}], language._one(group)


def _subject(plan: Plan, ctx: Context, e: dict[str, Any]) -> tuple[str, str] | None:
    """(the name, the player whose zones are searched) of the one target, as it was when it left (608.2h)."""
    from app.rules import effects

    refs = effects.target_refs(ctx, "target")
    if len(refs) != 1:
        return None
    t = refs[0]
    card = plan.state.cards.get(t["id"])
    if card is not None and plan.oid(card) == t.get("object_id"):
        name, owner, controller = plan.ch(card).name, card.owner, card.controller
    elif (snap := plan.rules.lki.get(t.get("object_id") or "")) is not None:
        name, owner, controller = snap.name, snap.owner, snap.controller
    else:
        return None
    pid = owner if e["by"] == "owner" else controller
    return (name, pid) if name and pid in plan.state.players else None


def _matches(plan: Plan, name: str, pid: str) -> list[str]:
    return [c for z in ZONES for c in plan.state.zones.get(zone_key(pid, z), []) if plan.ch(plan.state.cards[c]).name == name]


def search(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.effects import decide

    if (subject := _subject(plan, ctx, e)) is None:
        return True  # (the object is not known any more: nothing is searched for)
    name, pid = subject
    me = ctx["controller"]
    found = _matches(plan, name, pid)
    decide(plan, player=me, kind="choose_cards", prompt=f"{ctx.get('name') or 'Search'}: search {plan.name(pid)}'s graveyard, hand, "
           f"and library for cards named {name}", options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c)
                                                         for c in found],
           min_choices=0, max_choices=len(found), resume={"step": "name_search", "ctx": ctx, "pid": pid, "name": name})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    pid = d.resume["pid"]
    allowed = set(_matches(plan, d.resume["name"], pid))
    if finish(plan, d.resume["ctx"], pid, [c for c in chosen if c in allowed]):
        continue_effects(plan, d.resume["ctx"])


def finish(plan: Plan, ctx: Context, pid: str, cards: list[str]) -> bool:
    """Exile what was found (each to its owner's exile, all at once), then the library's owner shuffles (701.24)."""
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "exile"}}, actor=ctx["controller"])
    plan.do({"type": "shuffle", "player": pid, "zone": "library"}, actor=pid)
    return True
