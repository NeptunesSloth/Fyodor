"""Relative library qualifiers and ordered attachment continuations for native tutors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption, ObjectRef
from app.rules import card_names, context
from app.rules import qualified_search_packets as queries

if TYPE_CHECKING:
    from app.rules.plan import Plan

BIND = "ref:attached_tutor"


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = " ".join(body.lower().split()).rstrip(".").replace("that permanent", "that aura")
    kinds = {
        "you may search your library for an aura card with mana value less than or equal to that aura and with a different name than each aura you control, put that card onto the battlefield attached to ~, then shuffle": "light_paws",
        "search your library for an aura card that could enchant it. if this creature is still on the battlefield, put that aura card onto the battlefield attached to it. otherwise, reveal the aura card and put it into your hand. then shuffle": "auratouched",
        "search your library for an aura card that could enchant it. if ~ is still on the battlefield, put that aura card onto the battlefield attached to it. otherwise, reveal the aura card and put it into your hand. then shuffle": "auratouched",
        "you may search your library for an aura card that could enchant that creature, put it onto the battlefield attached to that creature, then shuffle": "sovereigns",
        "you may search your library for a curse card that doesn't have the same name as a curse attached to enchanted player, put it onto the battlefield attached to that player, then shuffle": "curse",
        "search your library for an equipment card, put it onto the battlefield, attach it to a creature you control, then shuffle": "equipment",
        "you may search your library for an aura card with enchant creature, reveal it, put it into your hand, then shuffle": "tallowisp",
        "you may search your library for a card with flashback or disturb, put it into your graveyard, then shuffle": "flashback_disturb",
        "search your library for a creature card with deathtouch, hexproof, reach, or trample and reveal it. shuffle and put that card on top": "beast_tracker",
        "search your library for a card named halvar, god of battle or an equipment card, reveal it, put it into your hand, then shuffle": "halvar",
        "you may search your library for a creature card with the same total power and toughness, put it onto the battlefield, then shuffle": "wild_pair",
        "count the colors of the sacrificed creature, then search your library for a creature card that's exactly that many colors plus one. exile that card, then shuffle. you may cast the exiled card": "evolving",
        "you may search your library for a basic land card that doesn't share a land type with a land you control, put that card onto the battlefield, then shuffle": "land_types",
    }
    if (kind := kinds.get(text)) is None:
        return None
    effect = {"do": "relative_tutor", "kind": kind, "binding": BIND}
    if kind in ("light_paws", "wild_pair", "sovereigns"):
        effect["event_reference"] = "ref:event"
    if kind == "evolving":
        effect["cost_reference"] = "cost:sacrificed"
    return [effect], None, False


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    """Use native trigger/cost parsing while keeping the compound tutor one instruction."""
    from dataclasses import replace

    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    replacements = [
        (
            "You may discard a nonland card. If you do, search your library for a card with the same mana value as that card, reveal it, put it into your hand, then shuffle.",
            "discard_mv",
        ),
        (
            "When you next cast a creature spell this turn, search your library for a creature card with lesser mana value, put it onto the battlefield, then shuffle.",
            "watch_lesser",
        ),
    ]
    for clause, kind in replacements:
        if clause.lower() in text.lower():
            start = text.lower().index(clause.lower())
            stub = (
                "You may discard a nonland card. If you do, scry 1."
                if kind == "discard_mv"
                else "When you next cast a creature spell this turn, scry 1."
            )
            d = scripts._define(replace(ability, text=text[:start] + stub), ch)
            if d is None:
                return None
            es = d["effects"]
            for i, e in enumerate(es):
                if e["do"] in ("scry", "deferred:scry"):
                    es[i] = {
                        "do": "deferred:relative_tutor"
                        if e["do"].startswith("deferred:")
                        else "relative_tutor",
                        "kind": "lesser_mv" if kind == "watch_lesser" else kind,
                        "binding": BIND,
                    }
                    if kind == "discard_mv":
                        es[i]["discard_binding"] = "ref:" + next(
                            x["bind"] for x in es if x["do"] == "optional_payment"
                        )
            return d
    # Commas within a relative qualification are not trigger separators.
    head, sep, body = ability.text.partition(", ")
    if (
        sep
        and (parsed := parse(body)) is not None
        and body.lower().startswith("you may search your library for a curse")
    ):
        d = scripts._define(replace(ability, text=head + ", scry 1."), ch)
        return {**d, "effects": parsed[0]} if d is not None else None
    return None


def _insert(plan: Plan, ctx: dict[str, Any], es: list[dict[str, Any]]) -> bool:
    from app.rules import effects

    ctx["effects"][ctx["next"] : ctx["next"]] = es
    effects.continue_effects(plan, ctx)
    return False


def prepare(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import attached_players, effects, values

    k = e["kind"]
    kind = {
        "light_paws": "Aura card",
        "auratouched": "Aura card",
        "sovereigns": "Aura card",
        "curse": "Curse card",
        "equipment": "Equipment card",
        "tallowisp": "Aura card",
        "beast_tracker": "creature card",
        "wild_pair": "creature card",
        "evolving": "creature card",
        "lesser_mv": "creature card",
        "land_types": "basic land card",
    }.get(k, "card")
    to = (
        "battlefield"
        if k
        in (
            "light_paws",
            "auratouched",
            "sovereigns",
            "curse",
            "equipment",
            "wild_pair",
            "lesser_mv",
            "land_types",
        )
        else "graveyard"
        if k == "flashback_disturb"
        else "top"
        if k == "beast_tracker"
        else "exile"
        if k == "evolving"
        else "hand"
    )
    request = queries.search(kind, to=to, relative_tutor={"kind": k}, outcome=e["binding"])
    request["may"] = k in (
        "light_paws",
        "sovereigns",
        "curse",
        "tallowisp",
        "flashback_disturb",
        "wild_pair",
        "land_types",
    )
    qualifier = request["relative_tutor"]
    if k in ("auratouched", "sovereigns", "light_paws"):
        who = "event" if k == "sovereigns" else "self"
        pair = values._object(plan, ctx, who)
        if pair:
            host, hch = pair
            qualifier["host"] = host.id
            if k == "sovereigns":
                event_refs = context._object_refs(ctx, context.EVENT)
                qualifier["event_object"] = event_refs[0].object_id if len(event_refs) == 1 else None
            qualifier["host_object"] = (
                plan.oid(host)
                if host.id in plan.state.cards and plan.state.cards[host.id].zone.endswith(":battlefield")
                else None
            )
        request["host"] = "event" if k == "sovereigns" else "self"
        if k == "auratouched" and not effects._cards(plan, ctx, "self"):
            request.update(to="hand", reveal=True)
    if k == "curse":
        players = attached_players.enchanted_player(plan, ctx)
        qualifier["player"] = players[0] if players else None
        if players:
            request["host"] = "player:" + players[0]
    if k in ("wild_pair", "lesser_mv", "light_paws"):
        pair = values._object(plan, ctx, "event")
        qualifier["number"] = (
            sum(pair[1].pt or (0, 0)) if k == "wild_pair" and pair else pair[1].mana_value if pair else -1
        )
    if k == "discard_mv":
        infos = context.infos(plan, ctx, e["discard_binding"].removeprefix(context.PREFIX))
        qualifier["number"] = infos[0][1].mana_value if len(infos) == 1 else -1
    if k == "evolving":
        pair = values._object(plan, ctx, "cost:sacrificed")
        qualifier["number"] = len(pair[1].colors) + 1 if pair else -1
    if k == "land_types":
        qualifier["types"] = sorted(
            {
                t
                for c in plan.state.cards.values()
                if c.controller == ctx["controller"]
                and c.zone.endswith(":battlefield")
                and plan.ch(c).is_land
                for t in plan.ch(c).subtypes
            }
        )
    if k == "equipment":
        request["shuffle"] = False
    tail = (
        [{"do": "relative_tutor_after", "kind": k, "binding": e["binding"]}]
        if k in ("equipment", "evolving")
        else []
    )
    return _insert(plan, ctx, [request, *tail])


def matches(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], cid: str) -> bool:
    from app.rules import attachments, values

    q = e["relative_tutor"]
    k = q["kind"]
    c = plan.state.cards[cid]
    ch = plan.ch(c)
    if k == "halvar":
        return card_names.has_name(ch, "Halvar, God of Battle") or "Equipment" in ch.subtypes
    if k == "tallowisp":
        return attachments.enchant_selector(ch) == "creature"
    if k == "flashback_disturb":
        return any(x.lower().startswith(("flashback", "disturb")) for x in ch.keywords)
    if k == "beast_tracker":
        return any(x.lower() in ("deathtouch", "hexproof", "reach", "trample") for x in ch.keywords)
    if k == "wild_pair":
        return sum(ch.pt or (0, 0)) == q["number"]
    if k == "lesser_mv":
        return ch.mana_value < q["number"]
    if k == "discard_mv":
        return ch.mana_value == q["number"]
    if k == "evolving":
        return len(ch.colors) == q["number"]
    if k == "land_types":
        return not set(ch.subtypes).intersection(q["types"])
    if k == "curse":
        p = q.get("player")
        return bool(p) and not any(
            set(card_names.names_of(ch)).intersection(card_names.names_of(plan.ch(a)))
            for a in plan.state.cards.values()
            if a.zone.endswith(":battlefield") and a.attached_player == p and "Curse" in plan.ch(a).subtypes
        )
    if k == "light_paws":
        if ch.mana_value > q["number"]:
            return False
        if any(
            set(card_names.names_of(ch)).intersection(card_names.names_of(plan.ch(a)))
            for a in plan.state.cards.values()
            if a.zone.endswith(":battlefield")
            and a.controller == ctx["controller"]
            and "Aura" in plan.ch(a).subtypes
        ):
            return False
    if k in ("auratouched", "sovereigns"):
        pair = values._object(plan, ctx, "self" if k == "auratouched" else "event")
        if pair is None:
            return False
        host, hch = pair
        real = plan.state.cards.get(host.id)
        if k == "sovereigns" and (
            real is None
            or not real.zone.endswith(":battlefield")
            or not q.get("host_object")
            or plan.oid(real) != q.get("event_object")
        ):
            return False
        return (
            attachments.host_problem(plan, c, host.id, ctx["controller"], host_card=host, host_face=hch)
            is None
        )
    return True


def after(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    name = e["binding"].removeprefix(context.PREFIX)
    old = [ObjectRef.model_validate(r) for r in context.refs(ctx).get(name, {}).get("objects", [])]
    context.bind_moved(plan, ctx, name, old)
    cards = context.objects(plan, ctx, name)
    if e["kind"] == "evolving":
        # Existing free-cast engine supports ordinary-cost immediate cast offers.
        return (
            _insert(
                plan,
                ctx,
                [
                    {
                        "do": "free_cast",
                        "who": e["binding"],
                        "zone": "that",
                        "n": 1,
                        "paid": True,
                        "exact_refs": True,
                    }
                ],
            )
            if cards
            else True
        )
    equipment = [c for c in cards if plan.state.cards[c].zone.endswith(":battlefield")]
    if not equipment:
        return _insert(plan, ctx, [{"do": "shuffle_library", "who": "you"}])
    from app.rules import attachments

    source = plan.state.cards[equipment[0]]
    legal = [
        c.id
        for c in plan.state.cards.values()
        if c.zone.endswith(":battlefield")
        and c.controller == ctx["controller"]
        and plan.ch(c).is_creature
        and attachments.host_problem(plan, source, c.id, ctx["controller"]) is None
    ]
    if not legal:
        return _insert(plan, ctx, [{"do": "shuffle_library", "who": "you"}])
    from app.rules.plan import decide

    decide(
        plan,
        player=ctx["controller"],
        kind="choose_cards",
        prompt="Attach the Equipment to a creature you control",
        options=[
            DecisionOption(id=c, label=plan.ch(plan.state.cards[c]).name or "Creature", card_id=c)
            for c in legal
        ],
        min_choices=1,
        max_choices=1,
        resume={
            "step": "relative_tutor_attach",
            "ctx": ctx,
            "equipment": {"card": source.id, "object_id": plan.oid(source)},
        },
    )
    return False


def resume_attach(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import attachments

    r = d.resume["equipment"]
    c = plan.state.cards.get(r["card"])
    if c is not None and plan.oid(c) == r["object_id"] and chosen:
        attachments.attach(plan, c.id, chosen[0], d.player)
    _insert(plan, d.resume["ctx"], [{"do": "shuffle_library", "who": "you"}])


PRIMITIVES = {"relative_tutor": prepare, "relative_tutor_after": after}
RESUME = {"relative_tutor_attach": resume_attach}
