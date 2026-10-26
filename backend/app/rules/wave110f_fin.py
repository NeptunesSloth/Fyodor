"""Wave 110F final pass: whole-ability definitions read onto existing machinery (one exact wording each)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.selectors import Selector

_MASTER = ("Whenever a nontoken artifact creature you control dies, you may exile it. If you do, choose an opponent with the most life among your "
           "opponents. That player faces a villainous choice — They lose 4 life, or you create a token that's a copy of that card.")


_ANIMATE = "As long as enchanted artifact isn't a creature, it's an artifact creature with power and toughness each equal to its mana value."


_BUSY: list[int] = []  # (reading the same ability natively once)
_VOLT_COST = "Collect evidence 6: ~ becomes an artifact creature until end of turn."
_VOLT_ATTACK = ("Whenever ~ attacks, you may cast an instant or sorcery spell from among cards exiled with it. "
                "If that spell would be put into a graveyard, put it on the bottom of its owner's library instead.")


_TASTER = ("When ~ enters, target opponent reveals X cards from their hand, where X is the number of Goblins you control. You choose one of those cards. "
           "That player exiles it. If an instant or sorcery card is exiled this way, you may cast it for as long as you control ~, and mana of any type can be spent to cast that spell.")


_DOCTOR = ("Whenever ~ attacks, choose a card in your hand. Defending player guesses whether that card's mana value is greater than the number of artifacts you control. "
           "If they guessed wrong, you may cast it without paying its mana cost. If you don't cast a spell this way, investigate.")


_SERV = ("When ~ enters, return target creature card from your graveyard to the battlefield.",
         "When the creature put onto the battlefield with ~ dies, exile it and return ~ to its owner's hand.",
         "When ~ leaves the battlefield, exile the creature put onto the battlefield with ~.")


_STAND = ("At the beginning of combat on your turn, for each defending player, separate all creatures that player controls into two piles and that player chooses one. "
          "Only creatures in the chosen piles can block this turn.")


_JARKELD = ("{T}: Choose two target blocked attacking creatures. If each of those creatures could be blocked by all creatures that the other is blocked by, each creature "
            "that's blocking exactly one of those attacking creatures stops blocking it and is blocking the other attacking creature. Activate only during the declare blockers step.")


_TAHNGARTH = ("Whenever an opponent attacks with one or more creatures, if ~ is tapped, you may have that opponent gain control of ~ until end of combat. "
              "If you do, choose a player or planeswalker that opponent is attacking. ~ is attacking that player or planeswalker.")


_IDRIS = "~ has all activated and triggered abilities of the exiled card and gets +X/+X, where X is the exiled card's mana value."


_BOOK = ("{T}, Exile ~ and artifacts you control named Eye of Vecna and Hand of Vecna: Create Vecna, a legendary 8/8 black Zombie God creature token with indestructible and all "
         "triggered abilities of the exiled cards.")


_MIMEO = "{2}: ~ becomes a copy of target creature card exiled with it, except it's 0/0 and has this ability."


_EQUILIBRIUM = ("If an opponent who controls at least as many lands as you do would put a land onto the battlefield, that player instead puts that land onto the battlefield "
                "then sacrifices a land of their choice.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts
    from app.rules.token_copy_outcomes import ORIGINAL

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == "triggered" and text == _MASTER:
        probe = scripts.define(replace(ability, text=_MASTER.split(" If you do,")[0]), ch)
        if probe is None or probe["kind"] != "triggered":
            return None
        return {**probe, "effects": [{**probe["effects"][0], "as": ORIGINAL}, {"do": "master110f"}]}
    if ability.kind == "static" and text == _ANIMATE:  # 613.1d, 613.4b: the type is added whatever the host is; its P/T only when it was no creature (2008-08-01 ruling)
        probe = scripts.define(replace(ability, text="Enchanted artifact has flying."), ch)
        if probe is None or probe.get("who") != "attached":
            return None
        return {**probe, "keywords": [], "layered": True, "base_mv": True, "animate_mv110f": True, "layer4": {"add_types": ["Artifact", "Creature"]}}
    if ability.kind == "activated" and text == _VOLT_COST:  # 607.2a: the collected cards are exiled by this activated ability's cost: they are "exiled with it"
        if _BUSY:
            return None
        _BUSY.append(1)
        try:
            probe = scripts.define(ability, ch)
        finally:
            _BUSY.pop()
        return None if probe is None else {**probe, "effects": [{"do": "link_cost110f"}, *probe["effects"]]}
    if ability.kind == "triggered" and text == _VOLT_ATTACK:  # 608.2g (2024-02-02 ruling): cast during resolution, paying costs; 614.1a: a graveyard destination becomes the library's bottom
        probe = scripts.define(replace(ability, text="Whenever this Vehicle attacks, you may draw a card."), ch)
        if probe is None or probe["kind"] != "triggered":
            return None
        sel = Selector(types=("Instant", "Sorcery"), zones=("stack",)).key()
        return {**probe, "optional": False, "effects": [{"do": "linked_cards", "as": "e0"}, {"do": "free_cast", "zone": "that", "who": "ref:e0", "filter": sel, "optional": True, "mv": None, "n": 1,
                                                                           "paid": True, "graveyard_destination": "library_bottom"}]}
    if ability.kind == "triggered" and text == _TASTER:  # 701.20a reveal, 701.13 exile, 611.2b "for as long as you control ~", 118.9/609.4b mana of any type; X once (ruling 2025-11-17)
        probe = scripts.define(replace(ability, text="When ~ enters, target opponent loses 1 life."), ch)
        if probe is None or probe["kind"] != "triggered":
            return None
        sel = Selector(types=("Instant", "Sorcery"), card=True).key()
        goblins = scripts.parse_effects("Target opponent reveals X cards from their hand, where X is the number of Goblins you control.")
        assert goblins is not None
        return {**probe, "effects": [*goblins[0],
                                     {"do": "choose_from_hand", "who": "you", "sel": 'sel:{"card":true,"zones":[]}', "n": 1, "label": "card", "optional": False, "as": "e1"},
                                     {"do": "exile", "who": "ref:e1", "as": "e2"}, {"do": "only_if", "cond": {"object": "ref:e2", "is": sel}, "skip": 1},
                                     {"do": "grant_play", "who": "ref:e2", "play": False, "cast": True, "until": "source_controlled", "optional": True, "spend": "type"}]}
    if ability.kind == "triggered" and text == _DOCTOR:
        probe = scripts.define(replace(ability, text="Whenever ~ attacks, draw a card."), ch)
        cast = scripts.parse_effects("You may cast a spell from your hand without paying its mana cost. If you don't, investigate.")
        if probe is None or probe["kind"] != "triggered" or cast is None:
            return None
        free, gate, investigate = cast[0]
        return {**probe, "effects": [{"do": "seventh110f"}, {"do": "only_if", "cond": {"succeeded": "wrong110f"}, "skip": 1},
                                     {**free, "zone": "that", "who": "ref:seventh110f"}, gate, investigate]}
    if ability.kind == "triggered" and text in _SERV:  # 607.2c: the creature this enchantment's enters ability put onto the battlefield, by object (400.7)
        if text == _SERV[0]:
            if _BUSY:
                return None
            _BUSY.append(1)
            try:
                native = scripts.define(ability, ch)
            finally:
                _BUSY.pop()
            if native is None or [x["do"] for x in native["effects"]] != ["return_card"]:
                return None
            return {**native, "effects": [{**native["effects"][0], "as": "e0"}, {"do": "link_put110f"}]}
        probe = scripts.define(replace(ability, text=("Whenever a creature you control dies, exile it and return ~ to its owner's hand." if text == _SERV[1]
                                                     else "When ~ leaves the battlefield, you gain 1 life.")), ch)
        if probe is None:
            return None
        return {**probe, "cond": {"event": "die", "subject": "put_with110f"}} if text == _SERV[1] else {**probe, "effects": [{"do": "servitude110f"}]}
    if ability.kind == "triggered" and text == _STAND:  # 802.2: every opponent is a defending player as the combat phase starts; 700.3: the piles; Fight or Flight's machinery (pile_groups)
        probe = scripts.define(replace(ability, text="At the beginning of combat on your turn, draw a card."), ch)
        if probe is None or probe["kind"] != "triggered":
            return None
        sel = Selector(types=("Creature",)).key()
        return {**probe, "effects": [{"do": "pile_deal", "who": "each_opponent", "split": "you", "sel": sel, "zone": "battlefield", "pick": "owner", "n": 2,
                                      "chosen": "limit_block", "other": None, "say": "creatures"}]}
    if ability.kind == "activated" and text == _JARKELD:
        probe = scripts.define(replace(ability, text="{T}: Choose two target blocked attacking creatures. You gain 1 life. Activate only during the declare blockers step."), ch)
        if probe is None or probe.get("kind") != "activated" or not probe.get("targets"):
            return None
        return {**probe, "effects": [{"do": "jarkeld110f"}]}
    if ability.kind == "triggered" and text == _TAHNGARTH:
        probe = scripts.define(replace(ability, text="Whenever an opponent attacks with one or more creatures, if ~ is tapped, you may draw a card."), ch)
        if probe is None or probe["kind"] != "triggered" or not probe.get("optional"):
            return None
        return {**probe, "effects": [{"do": "tahngarth110f"}]}
    if ability.kind == "static" and text == _IDRIS:  # 113.10, 613.1f the exiled card's abilities, 613.4c +X/+X, X its mana value (X in its cost is 0: 2023-10-13 ruling); none exiled: neither
        from app.rules.statics import _definition

        d = _definition("self", None, [], abilities_of={"sel": None, "linked": True, "no_mana": False, "triggered": True})
        d["each"] = {"p": 1, "t": 1, "value": {"linked_pool": {"projection": "total_mv110f"}}}
        return d
    if ability.kind == "activated" and scripts.self_text(ability.text, ch.name) == _BOOK:
        native = scripts.define(replace(ability, text=ability.text.replace(" and all triggered abilities of the exiled cards", "")), ch)
        if native is None or [x["do"] for x in native["effects"]] != ["create_token"]:
            return None
        return {**native, "effects": [{"do": "vecna110f", "token": native["effects"][0]["token"]}]}
    if ability.kind == "activated" and text == _MIMEO:  # 707.9a-b: a copy of the exiled card (a card in exile: its printed values) except 0/0 (the counters stay) and with this ability
        probe = scripts.define(replace(ability, text=_MIMEO.replace("target creature card exiled with it", "target creature card in a graveyard").replace("~", "Mimeoplasm")), ch)
        if probe is None or [x["do"] for x in probe["effects"]] != ["become_copy"]:
            return None
        eff = probe["effects"][0]
        fixed = {**eff, "excepts": [{**eff["excepts"][0], "add_text": [ability.text.replace(ch.name.split(",")[0], "This permanent")]}]}
        return {**probe, "effects": [fixed], "target": {"what": "exiled_with"}}
    if ability.kind == "static" and text == _EQUILIBRIUM:  # applied as lands are planned to enter: devour.equilibrium (614.1a)
        return {"kind": "static", "static": "equilibrium110f", "effects": []}
    return None


def vecna(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The Book of Vile Darkness (2021-07-23 rulings): the token's triggered abilities are those printed on the exiled cards (their text as exiled, not the permanents' as they were),
    part of its copiable values, so an enters trigger of the Eye triggers as Vecna arrives. The lenders' names are the token's own (113.10: "this creature")."""
    from app.rules import characteristics as chars
    from app.rules import effects

    cards = [*effects._cards(plan, ctx, "cost:exiled"), *effects._cards(plan, ctx, "cost_exiled_self")]
    lines = []
    for cid in dict.fromkeys(cards):
        card = plan.state.cards[cid]
        ch = chars.of(card, plan.info)
        lines += [a.text.replace(ch.name, e["token"]["name"]) for a in ch.abilities if a.kind == "triggered"]
    token = {**e["token"], "text": "\n".join([e["token"].get("text") or "", *lines]).strip()}
    return effects.PRIMITIVES["create_token"](plan, ctx, {"do": "create_token", "who": "you", "n": 1, "token": token})


def tahngarth(plan: Any, ctx: dict[str, Any], e: dict[str, Any], pick: str | None = None) -> bool:
    """Tahngarth, First Mate (rulings 2019-08-23): the opponent gains control until end of combat; its controller then chooses a player or planeswalker that opponent is
    attacking (one of the objects their creatures still attack, 508.5) and it attacks that, though never declared as an attacker (508.4: no attack triggers; the new
    controller's restrictions don't apply). Nothing to choose: it is not attacking."""
    from app.rules import effects, layers

    src = plan.state.cards.get(ctx.get("source_card") or "")
    opponents = effects._players(plan, ctx, "event_player")
    if src is None or not src.zone.endswith(":battlefield") or plan.oid(src) != ctx.get("source_object") or len(opponents) != 1 or opponents[0] not in plan.live():
        return True
    opp = opponents[0]
    if pick is None:
        effects._control_effect(plan, ctx, [src.id], opp, "end_of_combat")
        layers.control_sync(plan)
        seen: dict[str, str] = {}
        for c in plan.state.cards.values():
            t = c.attacking
            if t is None or not c.zone.endswith(":battlefield") or c.controller != opp or c.id == src.id or not plan.ch(c).is_creature:
                continue
            if t.kind == "player" and t.id in plan.live():
                seen[t.id] = plan.name(t.id)
            elif t.kind == "card" and (pw := plan.state.cards.get(t.id)) is not None and pw.zone.endswith(":battlefield") and "Planeswalker" in plan.ch(pw).types:
                seen[t.id] = f"{pw.name} ({plan.name(pw.controller)})"
        if not seen:
            return True
        if len(seen) > 1:
            from app.rules.plan import decide

            decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a player or planeswalker {plan.name(opp)} is attacking",
                   options=[DecisionOption(id=k, label=v) for k, v in seen.items()], resume={"step": "tahngarth110f", "ctx": ctx, "e": e})
            return False
        pick = next(iter(seen))
    src = plan.state.cards[src.id]
    if src.zone.endswith(":battlefield") and src.controller == opp:
        plan.do({"type": "attack", "card_ids": [src.id], "target": {"kind": "player" if pick in plan.state.players else "card", "id": pick}}, actor=opp)
    return True


def resume_tahngarth(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if tahngarth(plan, d.resume["ctx"], d.resume["e"], chosen[0]):
        effects.continue_effects(plan, d.resume["ctx"])


def _could_be_blocked_by(plan: Any, attacker: Any, blockers: list[Any]) -> bool | None:
    """"Could be blocked by all of them": 509.1a-b as a declaration of exactly these blockers would be judged (each pair, the attacker's minimum and maximum); None: a rule of
    declarations this check doesn't model (block_by_all, "can't block alone", a cap, a companion group): the table decides by hand."""
    from app.rules import combat, combat_rules, declaration_groups, scripts

    ach = plan.ch(attacker)
    if "block_by_all" in scripts.statics(ach) or declaration_groups.relevant(plan, {b.id for b in blockers}, "block") \
            or any("cant_block_alone" in scripts.statics(plan.ch(b)) for b in blockers) or any(plan.rules.block_caps.get(b.controller) is not None for b in blockers) \
            or combat_rules.limits(plan, combat_rules.BLOCK_LIMIT_ALL).get("*") is not None:
        return None
    if blockers and (len(blockers) < combat.min_blockers(ach) or ("max_one_blocker" in scripts.statics(ach) and len(blockers) > 1)):
        return False
    return all(combat.block_problem(plan.state, b, plan.ch(b), attacker, ach, plan.info) is None for b in blockers)


def jarkeld(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """General Jarkeld: two targets that are both still blocked attacking creatures; if each could be blocked by every creature blocking the other, each creature
    blocking exactly one of them blocks the other instead (509.1h: they stay blocked; the new blocks are no new declaration: no "blocks" triggers, 2004-10-04 ruling)."""
    from app.rules import effects
    from app.rules.combat import note_block

    cards = [plan.state.cards[c] for c in dict.fromkeys(effects._cards(plan, ctx, "target"))]
    if len(cards) != 2 or not all(c.is_attacking and c.zone.endswith(":battlefield") and c.id in plan.rules.blocked for c in cards):
        return True
    a, b = cards
    by = {c.id: [x for x in plan.state.cards.values() if x.zone.endswith(":battlefield") and x.blocks(c.id)] for c in cards}
    ok = [_could_be_blocked_by(plan, a, by[b.id]), _could_be_blocked_by(plan, b, by[a.id])]
    if None in ok:
        plan.note(f"{ctx.get('name') or 'General Jarkeld'}: the blocks can't be checked for these creatures: move the blockers by hand")
        return True
    if not all(ok):
        plan.note(f"{ctx.get('name') or 'General Jarkeld'}: the creatures can't be blocked by each other's blockers: nothing changes")
        return True
    moved = [(x, b) for x in by[a.id] if not x.blocks(b.id)] + [(x, a) for x in by[b.id] if not x.blocks(a.id)]
    for x, to in moved:
        plan.do({"type": "block", "card_id": x.id, "attacker_id": to.id}, actor=ctx["controller"])  # (a creature blocking exactly one: the block is replaced)
    if moved:
        note_block(plan.state, [plan.oid(x) for x, _ in moved], [(plan.oid(x), plan.oid(to)) for x, to in moved])
        plan.note(f"{ctx.get('name') or 'General Jarkeld'}: " + ", ".join(f"{x.name} now blocks {to.name}" for x, to in moved))
    return True


def link_put(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """607.2c: the objects this ability put onto the battlefield (the new objects, 400.7)."""
    from app.rules import effects

    new = [c for c in effects._cards(plan, ctx, "ref:e0") if plan.state.cards[c].zone.endswith(":battlefield")]
    if new and ctx.get("source_object"):
        plan.rules.put_with110f.setdefault(ctx["source_object"], []).extend(plan.oid(c) for c in new)
    return True


def servitude(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Exile the creature put onto the battlefield with this enchantment": only while it still is that object on the battlefield (400.7, 2004-10-04 ruling)."""
    ids = [c for oid in plan.rules.put_with110f.get(ctx.get("source_object") or "", ()) if (c := oid.rsplit(".", 1)[0]) in plan.state.cards
           and plan.state.cards[c].zone.endswith(":battlefield") and plan.oid(c) == oid]
    if ids:
        plan.do({"type": "move", "card_ids": ids, "to": {"zone": "exile"}}, actor=ctx["controller"])
    return True


def seventh(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """608.2d: the controller picks a card in hand in secret (it is not named in the log), the defending player guesses (X is 0 in a hand, 202.3e)."""
    from app.rules import context, effects

    me = ctx["controller"]
    hand = list(plan.state.zones.get(f"{me}:hand", []))
    context.bind_payment(ctx, "wrong110f", False)
    context.bind_objects(plan, ctx, "seventh110f", [])
    if not hand or not effects._players(plan, ctx, "defending_player"):
        return True
    effects.decide(plan, player=me, kind="choose_cards", prompt=f"{ctx.get('name') or 'Choose'}: choose a card in your hand",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand], min_choices=1, max_choices=1,
                   resume={"step": "seventh110f", "ctx": ctx})
    return False


def resume_seventh(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in plan.state.zones.get(f"{d.player}:hand", []):
        raise ActionError("Choose a card in your hand")
    context.bind_objects(plan, ctx, "seventh110f", chosen)
    guesser = effects._players(plan, ctx, "defending_player")[0]
    effects.decide(plan, player=guesser, kind="choose_one", prompt=f"{ctx.get('name') or 'Guess'}: is the mana value of the chosen card greater than the number of artifacts they control?",
                   options=[DecisionOption(id="yes", label="Yes, greater"), DecisionOption(id="no", label="No, not greater")],
                   resume={"step": "seventh110f_guess", "ctx": ctx, "card": chosen[0]})


def resume_seventh_guess(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import characteristics as chars
    from app.rules import context, effects

    if len(chosen) != 1 or chosen[0] not in ("yes", "no"):
        raise ActionError("Choose yes or no")
    ctx = d.resume["ctx"]
    card = plan.state.cards[d.resume["card"]]
    artifacts = sum("Artifact" in plan.ch(plan.state.cards[c]).types for c in plan.state.zones.get(f"{ctx['controller']}:battlefield", []))
    wrong = (chars.of(card, plan.info).mana_value > artifacts) != (chosen[0] == "yes")
    plan.note(f"{plan.name(d.player)} guessed {'wrong' if wrong else 'right'}", actor=d.player)
    context.bind_payment(ctx, "wrong110f", wrong)
    effects.continue_effects(plan, ctx)


def link_cost(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, exiled_with

    exiled_with.record(plan, ctx, effects._cards(plan, ctx, "cost:exiled"))
    return True


def master(plan: Any, ctx: dict[str, Any], e: dict[str, Any], pick: str | None = None) -> bool:
    """608.2c "If you do": only if the card really was exiled (608.2h its object is in exile now). 701.55a-b: the chosen opponent chooses an option."""
    from app.rules import context
    from app.rules.plan import decide
    from app.rules.token_copy_outcomes import ORIGINAL
    from app.rules.token_copy_sources import copy

    if pick is None:
        if not any(plan.state.cards[c].zone.endswith(":exile") for c in context.objects(plan, ctx, ORIGINAL) if c in plan.state.cards):
            return True
        opps = [p for p in plan.live() if p != ctx["controller"]]
        if not opps:
            return True
        top = max(plan.state.players[p].life for p in opps)
        best = [p for p in opps if plan.state.players[p].life == top]
        if len(best) > 1:  # "choose an opponent with the most life": a tie is the controller's choice (101.4)
            decide(plan, player=ctx["controller"], kind="choose_one", prompt="Choose an opponent with the most life",
                   options=[DecisionOption(id=p, label=plan.name(p)) for p in best], resume={"step": "master110f", "ctx": ctx, "e": e})
            return False
        pick = best[0]
    lose = [{"do": "lose_life", "who": "player:" + pick, "n": 4}]
    added = [{"do": "villain", "who": "player:" + pick, "a": lose, "b": [copy("ref:" + ORIGINAL)],
              "labels": ["They lose 4 life", "You create a token that's a copy of that card"]}]
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]
    return True


def resume_master(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if master(plan, d.resume["ctx"], d.resume["e"], chosen[0]):
        effects.continue_effects(plan, d.resume["ctx"])




# -- Riku of Many Paths: "Whenever you cast a modal spell, choose up to X, where X is the number of times you chose a mode for that spell —" (700.2, 2024-04-12 rulings) --
_RIKU = "Whenever you cast a modal spell, choose up to X, where X is the number of times you chose a mode for that spell \u2014"


def modal_header(ab: Any, ch: Any, definitions: Any) -> dict[int, Any] | None:
    """The modal triggered ability read as "Whenever you cast a spell, choose up to X —" (X as it goes on the stack, 700.2b: ``triggers.event_x`` reads the modes
    chosen for the cast spell), the spell restricted to modal spells (``modal_spell``); its modes can't repeat (2024-04-12 ruling)."""
    from app.rules import scripts, selectors

    if ab.kind != "triggered" or scripts.self_text(ab.text, ch.name) != _RIKU:
        return None
    found = definitions(replace(ab, text="Whenever you cast a noncreature spell with mana value 3 or less, choose up to X \u2014"), ch)  # (the wording that reads as a cast event)
    head = found.get(ab.index)
    if head is None or (head.get("cond") or {}).get("event") != "cast":
        return {}
    head["cond"] = {**head["cond"], "spell": selectors.Selector(zones=("stack",), extras=("modal110f",)).key()}
    head["x_modes110f"] = True
    return found


def modal_spell(plan: Any, ch: Any) -> bool:
    """700.2: a spell with two or more modes to choose among (modes chosen as it is cast)."""
    from app.rules import scripts

    d = scripts.spell_definition(ch)
    return d is not None and bool(d.get("modal")) and len(d.get("modes") or []) >= 2


def modes_chosen(plan: Any, event: Any) -> int | None:
    """The number of times a mode was chosen for the cast spell (a mode chosen twice counts twice, 2024-04-12 ruling); modes an opponent chose are none of yours (700.2e).
    As the trigger goes on the stack the spell is still there (700.2b)."""
    if event is None or event.kind != "cast" or not event.objects:
        return None
    ref = event.objects[0]
    card = plan.state.cards.get(ref.card)
    entry = plan.rules.stack.get(ref.card)
    if card is None or card.zone != "stack" or plan.oid(card) != ref.object_id or entry is None or ref.card in plan.rules.modes110f:
        return 0
    return len(entry.modes)


# -- Gather Specimens (614.1a, 614.12; 2008-10-01 rulings): "If a creature would enter the battlefield under an opponent's control this turn, it enters under your control instead." --
SPECIMENS = "If a creature would enter the battlefield under an opponent's control this turn, it enters under your control instead."


def specimens(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    plan.rules.specimens110f.append([ctx["controller"], plan.state.turn.number])
    return True


def entering_player(plan: Any, player: str) -> str:
    """The player a creature would enter under, after each Gather Specimens of this turn that applies (each once: 614.5; a creature that would enter under an opponent of its
    controller enters under that controller instead, and the new would-be controller is judged again by the others: 2008-10-01 ruling, two opposing ones end where it began).
    ponytail: with several applicable at once the one that resolved first applies first (616.1: its would-be controller chooses)."""
    r = plan.rules
    if not r.specimens110f:
        return player
    now = [owner for owner, turn in r.specimens110f if turn == plan.state.turn.number and owner in plan.live()]
    used: set[int] = set()
    again = True
    while again:
        again = False
        for i, owner in enumerate(now):
            if i not in used and player != owner:
                player, again = owner, True
                used.add(i)
                break
    return player


def creature_entering(plan: Any, card: Any, player: str, **update: Any) -> bool:
    """Would this card be a creature on the battlefield (as it would enter under ``player``)?"""
    from app.game.state import zone_key

    return "Creature" in plan.ch(card.model_copy(update={"zone": zone_key(player, "battlefield"), "controller": player, **update})).types


PRIMITIVES = {"master110f": master, "link_cost110f": link_cost, "seventh110f": seventh, "link_put110f": link_put, "servitude110f": servitude, "jarkeld110f": jarkeld, "tahngarth110f": tahngarth, "vecna110f": vecna, "specimens110f": specimens}
RESUME = {"master110f": resume_master, "seventh110f": resume_seventh, "seventh110f_guess": resume_seventh_guess, "tahngarth110f": resume_tahngarth}
