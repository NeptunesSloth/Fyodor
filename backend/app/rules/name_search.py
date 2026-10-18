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
from app.rules import player_control

if TYPE_CHECKING:
    from app.rules.effects import Context
    from app.rules.plan import Plan

_PLAIN_EXTIRPATE = re.compile(r"Choose target card in a graveyard other than a basic land card\. Search its owner's graveyard, hand, "
                              r"and library for (all|any number of) cards with the same name as that card and exile them\. "
                              r"Then that player shuffles\.")
_SHUFFLE_TAIL = re.compile(r"(and exile them)\. Then that player shuffles\.")
_SHUFFLE_DRAW = re.compile(r"(and exile them)\. That player shuffles, then draws a card for each card exiled from their hand this way\.")
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
    body = _SHUFFLE_DRAW.sub(r"\1, then that player shuffles, then draws a card for each card exiled from their hand this way.", body)
    return _SHUFFLE_TAIL.sub(r"\1, then that player shuffles.", body)


# -- card names (wave 22B) -- "Choose a nonland card name. Search target player's graveyard, hand, and library for any number of cards with that
# name and exile them. Then that player shuffles." (Slaughter Games, Memoricide, Cranial Extraction, Stain the Mind, Ancient Vendetta, Dispossess,
# Infinite Obliteration), "... That player shuffles, then draws a card for each card exiled from their hand this way." (Lost Legacy, Unmoored Ego,
# The Stone Brain): the same search as above, for the name chosen earlier in the resolution (201.4, 709.4a: one of the card's names), in the
# targeted player's zones; "up to four" limits what the searcher may take (701.23b: they may find fewer).
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
NAMED_PATTERN = (r"search (?:target (?P<w>player|opponent)|(?P<again>the targeted player))'s graveyard, hand, and library for (?P<q>all|any number of|up to (?P<n>one|two|three|four|five)) "
                 r"cards with (?:that|the chosen) name and exile them, then that player shuffles(?P<draw>, then draws a card for each card exiled "
                 r"from their hand this way)?")


def build_named(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import language, selectors

    sel = selectors.parse("card with that name")
    if sel is None:
        raise language._Fail
    return [{"do": "name_search", "by": "named", "sel": sel.key(), "all": m["q"] == "all", "max": _NUMBERS[m["n"]] if m["n"] else None,
             "draw": bool(m["draw"])}], None if m["again"] else language._one(language.target_group(f"target {m['w']}"))  # (wave 53B: "the targeted player", the one target an earlier sentence made: chosen.rewrite)


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
    if e["by"] == "named":  # -- card names (wave 22B) -- the name chosen earlier in this resolution, the player targeted
        from app.rules import selectors

        named = next((x[5:] for x in selectors.from_key(e["sel"]).extras if x.startswith("name:")), None)
        return (named, t["id"]) if named and t["id"] in plan.live() else None
    card = plan.state.cards.get(t["id"])
    if card is not None and plan.oid(card) == t.get("object_id"):
        name, owner, controller = plan.ch(card).name, card.owner, card.controller
    elif (snap := plan.rules.lki.get(t.get("object_id") or "")) is not None:
        name, owner, controller = snap.name, snap.owner, snap.controller
    else:
        return None
    pid = owner if e["by"] == "owner" else controller
    return (name, pid) if name and pid in plan.state.players else None


def _matches(plan: Plan, name: str, pid: str, library: bool = True, depth: int | None = None) -> list[str]:
    from app.rules import card_names

    return [c for z in ZONES if library or z != "library" for c in plan.state.zones.get(zone_key(pid, z), [])[:depth if z == "library" else None]
            if plan.ch(plan.state.cards[c]).name == name or card_names.has_name(plan.ch(plan.state.cards[c]), name)]  # (709.4a; wave 43B: Aven Mindcensor, the top four)


def _library_banned(plan: Plan, searcher: str, ctx: Context) -> bool:
    """-- prohibitions (wave 22B) -- 614.17 / 701.23: "Players can't search libraries": the library is left out (the graveyard and hand aren't)."""
    from app.rules import prohibitions

    return prohibitions.cant_search(plan, searcher, ctx["controller"]) is not None


def search(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.effects import decide

    if (subject := _subject(plan, ctx, e)) is None:
        return True  # (the object is not known any more: nothing is searched for)
    name, pid = subject
    me = ctx["controller"]
    from app.rules import prohibitions

    banned = _library_banned(plan, me, ctx)
    if not banned:
        prohibitions.note_search(plan, me, pid)  # -- most-played cards (wave 43B) -- "Whenever an opponent searches their library"
    found = _matches(plan, name, pid, not banned, prohibitions.search_depth(plan, me))
    decide(plan, player=me, kind="choose_cards", prompt=f"{ctx.get('name') or 'Search'}: search {plan.name(pid)}'s graveyard, hand, "
           f"and library for cards named {name}", options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c)
                                                         for c in found],
           min_choices=0, max_choices=min(len(found), e.get("max") or len(found)),
           resume={"step": "name_search", "ctx": ctx, "pid": pid, "name": name, "e": e},
           decider=player_control.search_controller(plan, me) if pid == me else None)  # (wave 18H) 723.2: Opposition Agent
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    pid = d.resume["pid"]
    from app.rules import prohibitions

    allowed = set(_matches(plan, d.resume["name"], pid, not _library_banned(plan, d.player, d.resume["ctx"]), prohibitions.search_depth(plan, d.player)))
    if finish(plan, d.resume["ctx"], pid, [c for c in chosen if c in allowed], bool((d.resume.get("e") or {}).get("draw"))):
        continue_effects(plan, d.resume["ctx"])


def finish(plan: Plan, ctx: Context, pid: str, cards: list[str], draws: bool = False) -> bool:
    """Exile what was found (each to its owner's exile, all at once), then the library's owner shuffles (701.24) [and draws a card for each
    one exiled from their hand: Lost Legacy]."""
    library = [c for c in cards if plan.state.cards[c].zone == zone_key(pid, "library")]
    from_hand = sum(1 for c in cards if plan.state.cards[c].zone == zone_key(pid, "hand"))
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "exile"}}, actor=ctx["controller"])
    if pid == ctx["controller"]:  # (wave 18H) Opposition Agent: what they find in their own library its controller may play
        player_control.permit_exiled(plan, player_control.search_exile(plan, pid), library)
    plan.do({"type": "shuffle", "player": pid, "zone": "library"}, actor=pid)
    if draws and from_hand:  # (-- card names (wave 22B) -- through the draw choke point, 121.2)
        from app.rules import replace

        return replace.draw_cards(plan, [pid], from_hand, then={"do": "continue", "ctx": ctx}, ctx=ctx)
    return True
