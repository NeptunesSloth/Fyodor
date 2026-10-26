"""Bound name references and ordered qualification slots for native library searches.

CR 201.2a/709.4a: names are sets, including both halves of a split card outside
of the stack. CR 608.2c/h: freeze the reference when this instruction reads it.
The native search/parts implementation owns searching, authority, replacements,
movement and shuffling; this module only prepares its JSON-native qualifiers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules import card_names, context, selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = "qualified_search_prepare"


def key(text: str) -> str:
    sel = selectors.parse(text)
    assert sel is not None, text
    return selectors.replace(sel, zones=("library",), zone_owner="you", card=True).key()


def search(kind: str = "card", *, to: str = "hand", **kw: Any) -> dict[str, Any]:
    return {
        "do": "search",
        "sel": key(kind),
        "label": kind,
        "to": to,
        "reveal": to == "hand",
        "qualified_packet": True,
        **kw,
    }


def _parts(kinds: list[str], **kw: Any) -> dict[str, Any]:
    return search(kinds[0], parts=[key(k) for k in kinds], **kw)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = body.strip().rstrip(".").lower()
    fixed = {
        "you may search your library for a card named alpine watchdog and/or a card named igneous cur, reveal them, put them into your hand, then shuffle": _parts(
            ["card named Alpine Watchdog", "card named Igneous Cur"], may=True
        ),
        "you may search your graveyard, hand and/or library for a card named magnifying glass and/or a card named thinking cap and put them onto the battlefield. if you search your library this way, shuffle": _parts(
            ["card named Magnifying Glass", "card named Thinking Cap"],
            to="battlefield",
            graveyard=True,
            search_zones=["graveyard", "hand", "library"],
            may=True,
        ),
        "search your library and graveyard for a card named forest, a card named brambleweft behemoth, and a card named nissa, genesis mage. reveal those cards, put them into your hand, then shuffle": _parts(
            ["card named Forest", "card named Brambleweft Behemoth", "card named Nissa, Genesis Mage"],
            zones=["library", "graveyard"],
        ),
        "search your library and graveyard for a basic land card and a card named jiang yanggu, reveal them, put them into your hand, then shuffle": _parts(
            ["basic land card", "card named Jiang Yanggu"], zones=["library", "graveyard"]
        ),
        "search your library for a land card of each basic land type, put those cards onto the battlefield, then shuffle": _parts(
            [f"{t} card" for t in ("Plains", "Island", "Swamp", "Mountain", "Forest")], to="battlefield"
        ),
    }
    if text in fixed:
        return [fixed[text]], None, False
    if (
        text
        == "search your library for a basic land card and put it onto the battlefield tapped. search your library and graveyard for a card named nissa, nature's artisan, reveal it, put it into your hand, then shuffle"
    ):
        return (
            [
                search(
                    "basic land card",
                    to="battlefield_tapped",
                    shuffle=False,
                    search_event_group="ref:crescendo_search",
                ),
                search(
                    "card named Nissa, Nature's Artisan",
                    zones=["library", "graveyard"],
                    search_event_group="ref:crescendo_search",
                ),
            ],
            None,
            False,
        )
    if (
        text
        == "search your library for an instant card with mana value 3, reveal it, and put it into your hand. then repeat this process for instant cards with mana values 2 and 1. then shuffle"
    ):
        return (
            [
                *(
                    search(
                        "instant card", mv=["==", n], shuffle=False, search_event_group="ref:foresight_search"
                    )
                    for n in (3, 2, 1)
                ),
                {"do": "shuffle_library", "who": "you"},
            ],
            None,
            False,
        )
    if (
        text
        == "exile target nonland card from your graveyard. search your library for any number of cards with the same name as that card, reveal them, put them into your hand, then shuffle"
    ):
        result = scripts.parse_effects("Exile target nonland card from your graveyard.")
        assert result is not None
        moves, target, optional = result
        moves[0]["as"] = "qs_name"
        return (
            [*moves, {"do": "qualified_search", "kind": "binding", "ref": "ref:qs_name", "max": 1000000}],
            target,
            optional,
        )
    if (
        text
        == "reveal a creature card in your hand. search your library for a card with the same name as that card, reveal it, put it into your hand, then shuffle"
    ):
        return [{"do": "qualified_search", "kind": "reveal", "choose": "creature card"}], None, False
    if (
        text
        == "reveal a card from your hand. search your library for a card with the same name as that card, reveal it, put it into your hand, then shuffle"
    ):
        return [{"do": "qualified_search", "kind": "reveal", "choose": "card"}], None, False
    if text in (
        "reveal a card from your hand. search your library for a card with the same name as that card, reveal it, put it into your hand, then shuffle. hellbent — if you have no cards in hand, instead search your library for a card, put it into your hand, then shuffle",
        "reveal a card from your hand. search your library for a card with the same name as that card, reveal it, put it into your hand, then shuffle. if you have no cards in hand, instead search your library for a card, put it into your hand, then shuffle",
    ):
        return [{"do": "qualified_search", "kind": "reveal", "choose": "card", "hellbent": True}], None, False
    if (
        text
        == "you may search your graveyard, hand, and/or library for a card with the same name as that spell and put it onto the battlefield. if you search your library this way, shuffle"
    ):
        return (
            [
                {
                    "do": "qualified_search",
                    "kind": "binding",
                    "ref": "event",
                    "to": "battlefield",
                    "graveyard": True,
                    "search_zones": ["graveyard", "hand", "library"],
                    "may": True,
                }
            ],
            None,
            False,
        )
    if (
        text
        == "for each creature you control, you may search your library for a creature card with the same name as that creature. put those cards onto the battlefield, then shuffle"
    ):
        return (
            [
                {
                    "do": "qualified_search",
                    "kind": "roster",
                    "choose": "creatures you control",
                    "to": "battlefield",
                }
            ],
            None,
            False,
        )
    if (
        text
        == "choose five permanents you control. for each of those permanents, you may search your library for a card with the same name as that permanent. put those cards onto the battlefield tapped, then shuffle"
    ):
        return (
            [
                {
                    "do": "qualified_search",
                    "kind": "choose",
                    "choose": "permanents you control",
                    "n": 5,
                    "to": "battlefield_tapped",
                }
            ],
            None,
            False,
        )
    if (
        text
        == "you may pay {3} and sacrifice it. if you do, choose a land you control. then search your library for up to two basic land cards which have the same name as the chosen land, put them onto the battlefield tapped, then shuffle"
    ):
        return (
            [
                {"do": "optional_payment", "who": "you", "cost": "{3}, Sacrifice ~", "bind": "qs_paid"},
                {"do": "only_if", "cond": {"succeeded": "qs_paid"}, "skip": 1},
                {
                    "do": "qualified_search",
                    "kind": "land",
                    "choose": "lands you control",
                    "to": "battlefield_tapped",
                    "max": 2,
                },
            ],
            None,
            False,
        )
    return None


def _insert(plan: Plan, ctx: dict[str, Any], es: list[dict[str, Any]]) -> bool:
    from app.rules import effects

    at = ctx["next"]
    ctx["effects"][at:at] = es
    effects.continue_effects(plan, ctx)
    return False


def _names(plan: Plan, ids: list[str]) -> list[list[str]]:
    return [card_names.reference_names(plan.ch(plan.state.cards[c])) for c in ids]


def _prepared(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], groups: list[list[str]]) -> bool:
    kind = e["kind"]
    kw = {k: e[k] for k in ("to", "max", "graveyard", "search_zones", "may") if k in e}
    if kind in ("roster", "choose"):
        s = search("creature card" if kind == "roster" else "card", may=True, shuffle=False, **kw)
        if groups:
            s.update(parts=[s["sel"]] * len(groups), name_groups=groups)
        else:
            s["max"] = 0
        # Clarion's ruling: just ONE search. Failure to find each stated quality
        # remains independent. The final shuffle is mandatory even if no search is chosen.
        return _insert(plan, ctx, [s, {"do": "shuffle_library", "who": "you"}])
    else:
        s = search("basic land card" if kind == "land" else "card", **kw)
        s["name_in"] = [n for g in groups for n in g]
        if kind == "land" or s.get("max", 1) != 1:
            s["upto"] = True
    return _insert(plan, ctx, [s])


def prepare(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    pid, kind = ctx["controller"], e["kind"]
    if kind == "binding":
        infos = context.infos(plan, ctx, e["ref"].removeprefix(context.PREFIX))
        return _prepared(plan, ctx, e, [card_names.reference_names(ch) for _, ch in infos])
    if kind == "reveal" and e.get("hellbent") and not plan.state.zones.get(f"{pid}:hand"):
        return _insert(plan, ctx, [search(reveal=False, upto=False)])
    sel = selectors.parse(e["choose"])
    assert sel is not None
    if kind == "reveal":
        sel = selectors.replace(sel, zones=("hand",), zone_owner="you", card=True)
    options = selectors.candidates(plan, sel, pid, ctx.get("source_card"))
    if kind == "roster":
        return _prepared(plan, ctx, e, _names(plan, options))
    from app.rules.plan import decide

    n = min(e.get("n", 1), len(options))
    decide(
        plan,
        player=pid,
        kind="choose_cards",
        prompt=f"{ctx.get('name') or 'Search'}: choose {e['choose']}",
        options=[
            DecisionOption(id=c, label=plan.ch(plan.state.cards[c]).name or "Card", card_id=c)
            for c in options
        ],
        min_choices=n,
        max_choices=n,
        resume={"step": STEP, "ctx": ctx, "e": e},
    )
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    ctx, e = d.resume["ctx"], d.resume["e"]
    if e["kind"] == "reveal" and chosen:
        plan.do({"type": "reveal", "card_ids": chosen}, actor=d.player)
        # The exact chosen hand object is hidden again at the end of resolution.
        ctx.setdefault("revealed", []).extend(chosen)
        at = ctx["next"]
        ctx["effects"][at:at] = [{"do": "hide_revealed"}]
    _prepared(plan, ctx, e, _names(plan, chosen))


def slot(e: dict[str, Any], part: int) -> dict[str, Any]:
    """Resolve the same slot for every searched zone; preserve original descriptor."""
    out = dict(e)
    if e.get("parts"):
        out["sel"] = e["parts"][part]
    if "name_groups" in e:
        out["name_in"] = e["name_groups"][part]
    return out


PRIMITIVES = {"qualified_search": prepare}
RESUME = {STEP: resume}


def group_frame(
    plan: Plan, ctx: dict[str, Any], e: dict[str, Any], pid: str, owner: str, library: list[str]
) -> dict[str, Any] | None:
    """701.23h: repeated instructions before one shuffle share ONE exact searched portion."""
    if not e.get("search_event_group"):
        return None
    from app.rules import player_control

    group = e["search_event_group"]
    frames = ctx.setdefault("search_event_groups", [])
    old = next(
        (f for f in frames if f["group"] == group and f["player"] == pid and f["owner"] == owner), None
    )
    if old is not None:
        return old
    frame = {
        "group": group,
        "player": pid,
        "owner": owner,
        "noted": False,
        "objects": [r.model_dump(mode="json") for c in library if (r := context.ref_of(plan, c)) is not None],
        "decider": player_control.search_controller(plan, pid) if owner == pid else None,
    }
    frames.append(frame)
    return frame


def group_library(plan: Plan, frame: dict[str, Any], picked: list[str]) -> list[str]:
    return [
        r["card"]
        for r in frame["objects"]
        if r["card"] not in picked
        and (card := plan.state.cards.get(r["card"])) is not None
        and plan.oid(card) == r["object_id"]
        and card.zone == r["zone"]
    ]
