"""Actual craft materials linked to the permanent the craft return creates."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules import mana as M
    from app.rules.plan import Plan


CRAFT_RETURN = "Return this card to the battlefield transformed under its owner's control."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import costs, scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == 'activated' and CRAFT_RETURN in text and any(
            c.kind == costs.CRAFT for c in costs.parse_ability_cost(ability.cost or '', card_name=ch.name).components):
        base = scripts.define(replace(ability, text=ability.text.replace(CRAFT_RETURN, 'Gain 1 life.')), ch)
        parsed = scripts.parse_effects(CRAFT_RETURN)
        if base is not None and parsed is not None and parsed[1] is None and not parsed[2]:
            return {**base, 'effects': [{'do': 'prepare_craft_materials'}, *parsed[0], {'do': 'cleanup_craft_materials'}]}
    if ability.kind == 'triggered' and text == 'When ~ enters, you gain life equal to the mana value of the exiled card used to craft it.':  # (wave 110B)
        base = scripts.define(replace(ability, text='When this creature enters, you gain 1 life.'), ch)
        return None if base is None else {**base, 'effects': [{**base['effects'][0], 'n': {'crafted_mv': True}}]}
    if ability.kind == 'static' and text == "~'s power and toughness are each equal to the number of colors among the exiled cards used to craft it.":
        return {'kind': 'static', 'static': 'cda', 'p': {'crafted_colors': True}, 't': {'crafted_colors': True}, 'effects': []}
    if ability.kind == 'static' and text == "~'s power and toughness are each equal to the total power of the exiled cards used to craft it.":  # (wave 110A: Wretched Bonemass)
        return {'kind': 'static', 'static': 'cda', 'p': {'crafted_power': True}, 't': {'crafted_power': True}, 'effects': []}
    if ability.kind == 'static' and ability.text == KEYWORDS_LINE:
        return {'kind': 'static', 'static': 'crafted_keywords110a', 'effects': []}  # read by ``overlay`` (layers)
    if ability.kind == 'static' and text == "~'s power is equal to the total power of the exiled cards used to craft it.":  # (wave 110E)
        return {'kind': 'static', 'static': 'cda', 'p': {'crafted_power': True}, 't': None, 'effects': []}
    return None


# 702.167a / 613.1f: the permanent has each of these keywords while a card exiled to craft it has it (Wretched Bonemass); "protection" is each protection quality.
KEYWORDS = ("flying", "first strike", "double strike", "deathtouch", "haste", "hexproof", "indestructible", "lifelink", "menace", "protection", "reach", "trample", "vigilance")
KEYWORDS_LINE = ("This creature has flying as long as an exiled card used to craft it has flying. The same is true for first strike, double strike, deathtouch, haste, hexproof, "
                 "indestructible, lifelink, menace, protection, reach, trample, and vigilance.")


def overlay(state: Any, card: Any, ch: Any, info: Any) -> Any:
    """The keywords the exiled craft materials have (their current characteristics, as the card is now in exile), for a permanent with the line above."""
    from app.rules import characteristics as chars
    from app.rules import oracle

    r = state.rules
    refs = r.crafted_materials.get(r.object_id(card.id)) if r is not None else None
    if not refs or KEYWORDS_LINE not in {a.text for a in ch.abilities}:
        return ch
    got: set[str] = set()
    protections: list[Any] = []
    for ref in refs:
        mat = state.cards.get(ref.card)
        if mat is None or r.object_id(mat.id) != ref.object_id or not mat.zone.endswith(':exile'):
            continue
        mch = chars.of(mat, info)
        got |= {k for k in mch.keywords if k in KEYWORDS and k != 'protection'}
        for ab in mch.abilities:
            if ab.kind == 'keywords' and 'protection' in ab.keywords:
                from app.rules.protection import _pieces

                protections += [oracle.parse_abilities(p + '.')[0] for p in _pieces(ab.text)]
    if protections:
        from dataclasses import replace as rep

        ch = replace(ch, abilities=(*ch.abilities, *(rep(a, index=1100 + i) for i, a in enumerate(protections))))
    return replace(ch, granted=ch.granted | frozenset(got)) if got else ch


def parse_mana(text: str, identity: tuple[str, ...], name: str) -> M.ManaAbility | None:
    from app.rules import mana as M
    from app.rules import scripts

    if 'craft this permanent' in text:  # -- lent abilities -- (abilities_of._lent's wording: 702.167c, the cards used to craft another object — unsettled: manual)
        return None
    if scripts.self_text(text, name) == '{T}: For each color among the exiled cards used to craft ~, add one mana of that color.':
        return M.ManaAbility(tap=True, sacrifice_self=False, options=((),), native_body=True, chooses=True,
            immediate_effects=({'do': 'crafted_color_mana'},))
    return None


def prepare(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import ObjectRef

    sid = ctx.get('stack_id')
    paid = plan.rules.payments.get(plan.oid(sid)) if sid else None
    if paid is None:
        return unknown_cost(plan, ctx)
    original = ctx.get('source_object')
    own = next((i for i, oid in enumerate(paid.exiled_was) if oid == original), None)
    if own is None or len(paid.exiled_objects) != len(paid.exiled) or len(paid.exiled_was) != len(paid.exiled):
        return unknown_cost(plan, ctx)
    source_oid = paid.exiled_objects[own]
    source = plan.state.cards.get(paid.exiled[own])
    if source is None or plan.oid(source) != source_oid or not source.zone.endswith(':exile'):
        return True
    refs = [ObjectRef(card=cid, object_id=oid, zone=card.zone)
            for cid, oid in zip(paid.exiled, paid.exiled_objects, strict=False)
            if (card := plan.state.cards.get(cid)) is not None and oid != source_oid
            and plan.oid(card) == oid and card.zone.endswith(':exile') and not card.is_token]
    plan.rules.pending_crafts[source_oid] = refs
    ctx['pending_craft_source'] = source_oid
    return True


def cleanup(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    plan.rules.pending_crafts.pop(ctx.get('pending_craft_source') or '', None)
    return True


def unknown_cost(plan: Plan, ctx: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    source = ctx.get('source_card')
    if source in plan.state.cards:
        plan.rules.card_modes[source] = 'manual'
    decide(plan, player=ctx['controller'], kind='manual_resolution',
        prompt='This older activation did not record its exact craft materials. Finish the return by hand; the card will remain under manual control.',
        options=[DecisionOption(id='done', label='Done')], resume={'step': 'unknown_craft_cost', 'ctx': ctx})
    return False


def colors(plan: Plan, ctx: dict[str, Any]) -> set[str]:
    refs = plan.rules.crafted_materials.get(ctx.get('source_object') or '', [])
    return {color for ref in refs if (card := plan.state.cards.get(ref.card)) is not None
            and plan.oid(card) == ref.object_id and card.zone.endswith(':exile')
            for color in plan.ch(card).colors}


def mana_value(plan: Plan, ctx: dict[str, Any]) -> int:
    """The mana value of the exiled card(s) the permanent was crafted with (702.167a); a card's mana value in exile is its own (202.3)."""
    refs = plan.rules.crafted_materials.get(ctx.get('source_object') or '', [])
    return sum(int(plan.ch(card).mana_value) for ref in refs if (card := plan.state.cards.get(ref.card)) is not None
               and plan.oid(card) == ref.object_id and card.zone.endswith(':exile'))


def total_power(plan: Plan, ctx: dict[str, Any]) -> int:
    """The total power of the exiled craft materials (a card in exile has its own power: a * counts as 0, 208.2a)."""
    refs = plan.rules.crafted_materials.get(ctx.get('source_object') or '', [])
    total = 0
    for ref in refs:
        card = plan.state.cards.get(ref.card)
        if card is not None and plan.oid(card) == ref.object_id and card.zone.endswith(':exile'):
            pt = plan.ch(card).pt
            total += max(0, pt[0]) if pt is not None else 0
    return total


def production(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import immediate_mana_resolutions
    from app.rules import mana as M

    if (ctx.get('source_object') or '') not in plan.rules.crafted_materials:
        from app.game.rules_state import DecisionOption
        from app.rules.plan import decide

        decide(plan, player=ctx['controller'], kind='manual_resolution',
            prompt='This older permanent has no recorded craft materials. Add the appropriate mana by hand, then press Done.',
            options=[DecisionOption(id='done', label='Done')], resume={'step': 'unknown_crafted_mana', 'ctx': ctx})
        return False
    actual = colors(plan, ctx)
    immediate_mana_resolutions.produce_chosen(plan, ctx, ctx['controller'], [c for c in M.COLORS if c in actual])
    return False


PRIMITIVES = {'prepare_craft_materials': prepare, 'cleanup_craft_materials': cleanup, 'crafted_color_mana': production}


def resume_unknown_mana(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, d.resume['ctx'])


RESUME = {'unknown_crafted_mana': resume_unknown_mana}


def resume_unknown_cost(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume['ctx']
    source = plan.state.cards.get(ctx.get('source_card') or '')
    if source is not None:
        plan.rules.crafted_materials.pop(plan.oid(source), None)
    ctx['next'] = len(ctx['effects'])
    effects.continue_effects(plan, ctx)


RESUME['unknown_craft_cost'] = resume_unknown_cost
