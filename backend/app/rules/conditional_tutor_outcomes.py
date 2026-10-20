"""Conditional native tutor requests and exact result-bound continuations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption, ObjectRef
from app.rules import context
from app.rules import qualified_search_packets as queries

if TYPE_CHECKING:
    from app.rules.plan import Plan

BIND = "ref:tutor_outcome"


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = " ".join(body.lower().split()).rstrip(".")
    kinds = {
        "search your library for a basic land card. if this spell was kicked, instead search your library for a basic land card and a shrine card. reveal those cards, put them into your hand, then shuffle": "kicker_slots",
        "search your library for a basic land card. if evidence was collected, instead search your library for a creature or land card. reveal that card, put it into your hand, then shuffle": "evidence_query",
        "search your library for up to two basic forest cards. if you control a nissa planeswalker, instead search your library for up to three land cards. reveal those cards, put them into your hand, then shuffle": "nissa_query",
        "search your library and/or graveyard for up to five doctor cards, reveal them, and put them into your hand. if you search your library this way, shuffle. if this spell was kicked, put those cards onto the battlefield instead of putting them into your hand": "doctor_query",
        "search your library for a creature card, reveal it, put it into your hand or graveyard, then shuffle": "hand_or_graveyard",
        "search your library for a basic land card and reveal it. you may put that card onto the battlefield tapped if you control a land named wastes. otherwise, put that card into your hand. then shuffle": "wastes_destination",
        "search your library for a basic land card, reveal it, put it into your hand, then shuffle. morbid — you may put that card onto the battlefield instead of putting it into your hand if a creature died this turn": "morbid_destination",
        "search your library for a basic land card, reveal it, put it into your hand, then shuffle. you may put that card onto the battlefield instead of putting it into your hand if a creature died this turn": "morbid_destination",
        "search your library for a basic land card, put that card onto the battlefield tapped, then shuffle. then if there are three or more basic land types among lands you control, scry 1": "domain_scry",
        "search your library and/or graveyard for an artifact creature card with mana value x or less and put it onto the battlefield with x additional +1/+1 counters on it. if x is 4 or greater, it gains haste until end of turn. if you search your library this way, shuffle": "x_entry",
        "search your library for up to two forest cards, put them onto the battlefield tapped, then shuffle. if this spell was kicked, untap all forests put onto the battlefield this way. they become 3/3 green creatures with haste that are still lands": "kicked_forests",
        "search your library for any number of basic land cards, put them onto the battlefield, then shuffle. those lands become 4/4 elemental creatures with trample. they're still lands": "elemental_lands",
        "search your library for up to two land cards that each have a basic land type, put them onto the battlefield tapped, then shuffle. look at the top x cards of your library, where x is the number of basic land types among lands you control. put up to one of them on top of your library and the rest on the bottom of your library in a random order": "domain_look",
        "you may search your library for a food card, reveal it, put it into your hand, then shuffle. if you don't put a card into your hand this way, create a food token": "food_fallback",
        "you may search your library for a basic land card and put it onto the battlefield tapped. if you search your library this way, put ~ on the bottom of its owner's library, then shuffle": "search_bottom_source",
        "you may search your library for any number of land cards, exile them, then shuffle. if you do, ~ has base power and base toughness each equal to the number of cards exiled this way": "exile_base_pt",
        "search your library for a dragon permanent card, put that card onto the battlefield, then shuffle. that dragon gains haste until end of turn. exile it at the beginning of the next end step": "dragon_delay",
        "search your library for a card. if it's an artifact card, you may put it onto the battlefield. otherwise, put that card into your hand. then shuffle": "artifact_destination",
    }
    if (
        text
        == "roll a d20. 1 | trapped! — you lose 3 life. 2—9 | create five treasure tokens. 10—19 | you gain 3 life and draw three cards. 20 | search your library for a card. if it's an artifact card, you may put it onto the battlefield. otherwise, put that card into your hand. then shuffle"
    ):
        from app.rules import scripts

        es: list[dict[str, Any]] = [{"do": "roll", "sides": 20, "count": 1}]
        for lo, hi, line in [
            (1, 1, "You lose 3 life."),
            (2, 9, "Create five Treasure tokens."),
            (10, 19, "You gain 3 life and draw three cards."),
        ]:
            native = scripts.parse_effects(line)
            assert native is not None
            es.extend(
                [
                    {
                        "do": "only_if",
                        "cond": {
                            "all": [
                                {"value": {"die": "result"}, "op": ">=", "n": lo},
                                {"value": {"die": "result"}, "op": "<=", "n": hi},
                            ]
                        },
                        "skip": len(native[0]),
                    },
                    *native[0],
                ]
            )
        es.extend(
            [
                {"do": "only_if", "cond": {"value": {"die": "result"}, "op": "==", "n": 20}, "skip": 1},
                {"do": "conditional_tutor", "kind": "artifact_destination", "binding": BIND},
            ]
        )
        return es, None, False
    kind = kinds.get(text)
    target = None
    if (
        text
        == "search your library for a plains card. if target opponent controls more lands than you, you may search your library for an additional plains card. reveal those cards, put them into your hand, then shuffle"
    ):
        kind = "target_more_lands"
        target = "opponent"
    if kind is None:
        return None
    return [{"do": "conditional_tutor", "kind": kind, "binding": BIND}], target, False


def _insert(plan: Plan, ctx: dict[str, Any], es: list[dict[str, Any]]) -> bool:
    from app.rules import effects

    ctx["effects"][ctx["next"] : ctx["next"]] = es
    effects.continue_effects(plan, ctx)
    return False


def _condition(text: str) -> dict[str, Any]:
    from app.rules import conditions

    found = conditions.parse(text, objects=True)
    assert found is not None, text
    return found


def _domain(plan: Plan, ctx: dict[str, Any]) -> int:
    from app.rules import selectors, values

    sel = selectors.parse("lands you control")
    assert sel is not None
    return values.evaluate(plan, ctx, {"distinct": "basic_land_types", "among": sel.key()})


def prepare(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import conditions, effects, values

    kind, bind = e["kind"], e["binding"].removeprefix(context.PREFIX)
    s = queries.search("basic land card")
    after = kind in (
        "domain_scry",
        "domain_look",
        "food_fallback",
        "search_bottom_source",
        "exile_base_pt",
        "dragon_delay",
        "kicked_forests",
        "elemental_lands",
        "x_entry",
    )
    kicked = values.kicked_holds(plan, ctx, True)
    if kind == "kicker_slots":
        if kicked:
            s = queries._parts(["basic land card", "Shrine card"])
    elif kind == "evidence_query":
        paid = plan.rules.payments.get(ctx.get("source_object") or "")
        if paid and any(tag.endswith(":evidence") for tag in paid.additional):
            s = queries.search("creature or land card")
    elif kind == "nissa_query":
        yes = conditions.holds(plan, ctx, _condition("you control a Nissa planeswalker"))
        s = queries.search("land card" if yes else "basic Forest card", max=3 if yes else 2, upto=True)
    elif kind == "target_more_lands":
        targets = effects._players(plan, ctx, "target")
        own = sum(
            c.zone.endswith(":battlefield") and c.controller == ctx["controller"] and plan.ch(c).is_land
            for c in plan.state.cards.values()
        )
        other = sum(
            c.zone.endswith(":battlefield") and c.controller in targets and plan.ch(c).is_land
            for c in plan.state.cards.values()
        )
        s = queries.search("Plains card", max=2 if other > own else 1, upto=True)
    elif kind == "doctor_query":
        s = queries.search(
            "Doctor card", graveyard=True, max=5, upto=True, to="battlefield" if kicked else "hand"
        )
    elif kind == "hand_or_graveyard":
        s = queries.search("creature card", destination_choice=["hand", "graveyard"])
    elif kind in ("wastes_destination", "morbid_destination"):
        s["optional_to_if"] = {
            "cond": _condition(
                "you control a land named Wastes"
                if kind == "wastes_destination"
                else "a creature died this turn"
            ),
            "to": "battlefield_tapped" if kind == "wastes_destination" else "battlefield",
        }
    elif kind == "artifact_destination":
        s = queries.search(
            "card", destination_choice=["hand", "battlefield"], destination_if=queries.key("artifact card")
        )
    elif kind == "x_entry":
        x = max(0, values.evaluate(plan, ctx, {"x": 1}))
        s = queries.search("artifact creature card", graveyard=True, to="battlefield", mv=["<=", x])
        if x:
            s.update(counter="+1/+1", counter_n=x)
    elif kind in ("kicked_forests", "elemental_lands"):
        s = queries.search(
            "Forest card" if kind == "kicked_forests" else "basic land card",
            to="battlefield_tapped" if kind == "kicked_forests" else "battlefield",
            max=2 if kind == "kicked_forests" else 1000000,
            upto=True,
        )
    elif kind in ("domain_scry", "domain_look", "search_bottom_source"):
        s = queries.search("basic land card", to="battlefield_tapped")
        if kind == "domain_look":
            s = queries.search(
                "land card",
                alts=[queries.key(t + " card") for t in ("Plains", "Island", "Swamp", "Mountain", "Forest")],
                to="battlefield_tapped",
                max=2,
                upto=True,
            )
        if kind == "search_bottom_source":
            s.update(may=True, shuffle=False)
    elif kind == "food_fallback":
        s = queries.search("Food card", may=True)
    elif kind == "exile_base_pt":
        s = queries.search("land card", to="exile", max=1000000, upto=True, may=True)
    elif kind == "dragon_delay":
        s = queries.search("Dragon permanent card", to="battlefield")
    else:
        raise AssertionError(kind)
    s["outcome"] = "ref:" + bind
    ctx.pop("search_performed", None)
    es = [s]
    if after:
        es.append({"do": "conditional_tutor_after", "kind": kind, "binding": "ref:" + bind, "kicked": kicked})
    return _insert(plan, ctx, es)


def note_result(
    plan: Plan, ctx: dict[str, Any], e: dict[str, Any], chosen: list[str], diverted: list[str]
) -> None:
    if e.get("outcome"):
        context.bind_objects(
            plan, ctx, e["outcome"].removeprefix(context.PREFIX), [c for c in chosen if c not in diverted]
        )


def after(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import delayed, effects, scripts, this_way, values

    kind, bind = e["kind"], e["binding"].removeprefix(context.PREFIX)
    b = context.refs(ctx).get(bind)
    if b and b.get("kind") == "objects" and "was" not in b:
        context.bind_moved(plan, ctx, bind, [ObjectRef.model_validate(r) for r in b.get("objects") or []])
    who = "ref:" + bind
    cards = [c for c in context.objects(plan, ctx, bind) if plan.state.cards[c].zone.endswith(":battlefield")]
    context.bind_objects(plan, ctx, bind + "_battlefield", cards)
    who = "ref:" + bind + "_battlefield"
    if kind == "domain_scry":
        return effects.scry(plan, ctx, {"n": 1, "who": "you"}) if _domain(plan, ctx) >= 3 else True
    if kind == "domain_look":
        return _insert(
            plan,
            ctx,
            [
                {"do": "look_top", "n": _domain(plan, ctx), "player": "you", "exact_look": True},
                {"do": "pick_looked", "n": 1, "optional": True, "to": "top_any"},
                {"do": "rest_looked", "to": "bottom_random"},
            ],
        )
    if kind == "food_fallback":
        n = this_way.count(plan, ctx, {"ref_count": bind, "this_way": "your_hand"})
        if n:
            return True
        native = scripts.parse_effects("Create a Food token.")
        assert native is not None
        return _insert(plan, ctx, native[0])
    if kind == "search_bottom_source":
        if not ctx.get("search_performed"):
            return True
        return _insert(
            plan,
            ctx,
            [{"do": "to_library", "who": "self", "place": "bottom"}, {"do": "shuffle_library", "who": "you"}],
        )
    if kind == "exile_base_pt":
        if not ctx.get("search_performed"):
            return True
        n = values.evaluate(plan, ctx, {"live_ref_count": bind, "zone": "exile"})
        return effects.become(plan, ctx, {"who": "self", "p": n, "t": n, "duration": "permanent"})
    if kind in ("kicked_forests", "elemental_lands"):
        if kind == "kicked_forests" and not e["kicked"]:
            return True
        es = []
        if kind == "kicked_forests":
            es.append({"do": "untap", "who": who})
        es.append(
            {
                "do": "become",
                "who": who,
                "types": ["Creature"],
                "retain": True,
                "creature_types": [] if kind == "kicked_forests" else ["Elemental"],
                "p": 3 if kind == "kicked_forests" else 4,
                "t": 3 if kind == "kicked_forests" else 4,
                "keywords": ["haste"] if kind == "kicked_forests" else ["trample"],
                "duration": "permanent",
                **({"colors": ["G"]} if kind == "kicked_forests" else {}),
            }
        )
        return _insert(plan, ctx, es)
    if kind == "x_entry":
        if values.evaluate(plan, ctx, {"x": 1}) >= 4:
            return effects.grant(plan, ctx, {"who": who, "keywords": ["haste"], "duration": "end_of_turn"})
        return True
    if kind == "dragon_delay":
        for cid in cards:
            delayed.create_move(
                plan, ctx["controller"], cid, plan.oid(cid), "exile", ctx.get("name") or "A Dragon"
            )
        return effects.grant(plan, ctx, {"who": who, "keywords": ["haste"], "duration": "end_of_turn"})
    raise AssertionError(kind)


def offer_destination(
    plan: Plan, ctx: dict[str, Any], e: dict[str, Any], pid: str, chosen: list[str], dest: dict[str, str]
) -> bool:
    from app.rules import prohibitions, selectors
    from app.rules.plan import decide

    if not e.get("destination_choice") or len(chosen) != 1 or dest.get(chosen[0]) != "hand":
        return False
    card = plan.state.cards[chosen[0]]
    if e.get("destination_if") and not selectors.matches(
        plan, selectors.from_key(e["destination_if"]), card, plan.ch(card), pid
    ):
        return False
    opts = [
        v
        for v in e["destination_choice"]
        if v != "battlefield" or prohibitions.cant_enter(plan, card, pid) is None
    ]
    if len(opts) < 2:
        return False
    decide(
        plan,
        player=pid,
        kind="choose_one",
        prompt="Choose the revealed card’s destination",
        options=[DecisionOption(id=v, label=v.title()) for v in opts],
        resume={"step": "conditional_tutor_destination", "ctx": ctx, "e": e, "cards": chosen, "dest": dest},
    )
    return True


def resume_destination(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    e = {**r["e"], "reveal": False}
    e.pop("destination_choice")
    dest = {**r["dest"], r["cards"][0]: chosen[0]}
    effects._finish_search(plan, r["ctx"], e, d.player, r["cards"], dest)


PRIMITIVES = {"conditional_tutor": prepare, "conditional_tutor_after": after}
RESUME = {"conditional_tutor_destination": resume_destination}


def merge_lines(ch: Any, out: dict[int, Any]) -> None:
    """Only the two printed cross-line found-card riders share their producer's namespace."""
    if not ch.is_instant_or_sorcery:
        return
    lines = [ab for ab in ch.abilities if ab.kind == "spell"]
    for first, second in zip(lines, lines[1:], strict=False):
        result = parse(first.text + " " + second.text)
        if result is None or result[0][0].get("kind") not in ("kicked_forests", "morbid_destination"):
            continue
        out[first.index] = {"kind": "spell", "effects": result[0], "target": None}
        out[second.index] = {"kind": "spell", "effects": [], "target": None, "merged_into": first.index}
