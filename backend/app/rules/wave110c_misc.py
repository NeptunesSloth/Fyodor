"""-- exact wordings (wave 110C) -- one-off cards: Volcano Hellion."""

from __future__ import annotations

import secrets
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

ECHO_LIFE = "This creature has echo {X}, where X is your life total."  # 702.30a, the cost is {N}, N = the controller's life total when it is paid
HELLION = "When this creature enters, it deals an amount of damage of your choice to you and target creature. The damage can't be prevented."


RELENTLESS = ("When this creature dies, you may pay {X}. If you do, return another target Zombie creature card with mana value X from your graveyard to the "
              "battlefield.")


SHUTTLE = ("Midnight Entity — Whenever this Vehicle attacks, defending player faces a villainous choice — That player sacrifices a creature of their choice, or you gain "
           "control of a creature of your choice that player controls until end of turn. If you gain control of a creature this way, tap it, and it's attacking that player.")


GLYPH = ("When this artifact enters, if you cast it, for each player, choose a creature with power 2 or less that player controls. "
         "Then destroy all creatures except creatures chosen this way.")


SIEGE = ("When this Siege enters, reveal any number of Dragon cards from your hand. When you do, this Siege deals X plus 2 damage to any other target, where X is the "
         "number of cards revealed this way.")


INCINERATOR = ("Whenever this creature deals combat damage to a player, you may collect evidence X. When you do, this creature deals X damage to each creature and "
               "planeswalker that player controls.")

OMNATH = ("At the beginning of your first main phase, look at the top card of your library. You may reveal that card if it has three or more colored mana symbols in its mana cost. "
          "If you do, add three mana in any combination of its colors and put it into your hand. If you don't reveal it, put it into your hand.")

PRODDER = ("At the beginning of your upkeep, reveal the top card of your library. Any opponent may have you put that card into your graveyard. If a player does, "
           "this creature deals damage to that player equal to that card's mana value. Otherwise, put that card into your hand.")

BREATH = ("When enchanted creature deals combat damage to a player, sacrifice it and attach this Aura to a creature you control. If you do, untap all creatures you "
          "control and after this phase, there is an additional combat phase.")

# Elesh Norn // The Argent Etchings' chapters (714.2b: the exile-return gives the front face back, a new object, 400.7; "(front face up)" is reminder text; "except for" = none of those)
CHAPTERS = {
    "Incubate 2 five times, then transform all Incubator tokens you control.": "Incubate 2. " * 5 + "Transform all Incubator tokens you control.",
    "Destroy all other permanents except for artifacts, lands, and Phyrexians. Exile ~, then return it to the battlefield.":
        "Destroy all other nonland, nonartifact, non-Phyrexian permanents. Exile ~, then return it to the battlefield under its owner's control.",
}


NEERA = ("Whenever you cast a spell, you may put it on the bottom of its owner's library. If you do, reveal cards from the top of your library until you reveal a nonland card. "
         "You may cast that card without paying its mana cost. Then put all revealed cards not cast this way on the bottom of your library in a random order. "
         "This ability triggers only once each turn.")

VAEVICTIS = ("Whenever ~ attacks, for each player, choose target permanent that player controls. Those players sacrifice those permanents. Each player who sacrificed a permanent "
             "this way reveals the top card of their library, then puts it onto the battlefield if it's a permanent card.")

WILD_HUNT = ("{T}: Tap all untapped Wolf creatures you control. Each Wolf tapped this way deals damage equal to its power to target creature. That creature deals damage equal to its power "
             "divided as its controller chooses among any number of those Wolves.")

SYMBIOTE = ("{2}{U/B}, Exile this card from your graveyard: Put a +1/+1 counter on target creature you control. It gains this card's other abilities. Activate only as a sorcery.")
SYMBIOTE_OTHER = ("Whenever this creature deals combat damage to a player, look at that many cards from the top of your library. Put one of them into your hand and the rest into "
                  "your graveyard.")

ULALEK = ("Whenever you cast an Eldrazi spell, you may pay {C}{C}. If you do, copy all spells you control, then copy all other activated and triggered abilities you control. "
          "You may choose new targets for the copies.")

KEFKA = ("At the beginning of your end step, exile a card at random from each opponent's graveyard. You may cast any number of spells from among cards exiled this way without paying "
         "their mana costs. Then each player who owns a spell you cast this way loses life equal to its mana value.")

PROCTOR = "Whenever a permanent entering causes a triggered ability to trigger, counter that ability unless its controller pays {2}."


SIN_DIES = "When ~ dies, put its counters on target creature you control, then shuffle this card into its owner's library."
TORALF = "Whenever a creature or planeswalker an opponent controls is dealt excess noncombat damage, ~ deals damage equal to the excess to any target other than that permanent."
ABADDON = ("Mark of Chaos Ascendant — During your turn, spells you cast from your hand with mana value X or less have cascade, where X is the total amount of life your opponents have lost "
           "this turn.")
AMPED = ("When this creature enters, you get {E}{E}. Then if you cast it from your hand, exile cards from the top of your library until you exile a "
         "nonland card. You may cast that card by paying an amount of {E} equal to its mana value rather than paying its mana cost.")
IRENCRAG = ("Whenever a legendary creature you control enters, you may have ~ become a legendary Equipment artifact named Everflame, Heroes' Legacy. If you do, it gains equip {3} "
            "and \"Equipped creature gets +3/+3\" and loses all other abilities.")
HAMMER = 'Equipped creature has "{1}{R}, {T}, Unattach Toralf\'s Hammer: It deals 3 damage to any target. Return Toralf\'s Hammer to its owner\'s hand."'
TORALF_NATIVE = TORALF.replace("deals damage equal to the excess to any target other than that permanent", "deals X damage to any target, where X is that excess damage")
YIDARO = ("When you cycle this card, shuffle it into your library from your graveyard. If you've cycled a card named Yidaro, Wandering Monster four or more times "
          "this game, put it onto the battlefield from your graveyard instead.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if scripts.self_text(ability.text, ch.name) == SIN_DIES:  # "this card" is Sin itself (400.7: the card in the graveyard), not the creature it chose; shuffled in even if gone (701.24c)
        d = scripts.define(replace(ability, text="When ~ dies, put ~'s counters on target creature you control, then shuffle ~ into its owner's library."), ch)
        return None if d is None else {**d, "effects": [{"do": "shuffle_dead110c"} if e["do"] == "to_library" else e for e in d["effects"]]}
    if ability.text == YIDARO:  # 702.29a-c: the card is in the graveyard when the trigger resolves; the count includes this cycling
        d = scripts.define(replace(ability, text="When you cycle this card, draw a card."), ch)
        return None if d is None else {**d, "effects": [{"do": "yidaro110c"}]}

    if ability.text == HAMMER:  # like Razor Boomerang (wave 110J): "It" is the Equipment, which deals the damage (120.3); the grant binds the name to its granter
        return scripts.define(replace(ability, text=HAMMER.replace("It deals 3", "Toralf's Hammer deals 3")), ch)
    if ability.kind == "static" and ability.text == ABADDON:  # 702.85a: the spell has cascade as it is cast (cast_limits.granted_instances: "during110c", "mv_le110c")
        d = scripts.define(replace(ability, text="Spells you cast from your hand have cascade."), ch)
        return None if d is None or d.get("static") != "spell_keyword" else {**d, "during110c": "your_turn", "mv_le110c": {"turn_history": "opp_lost"}}
    if ability.kind == "triggered" and ability.text == AMPED:  # energy first (107.14), then the exile-until-nonland offer (exile_authority_continuations 'amped110c')
        from app.rules import exile_authority_continuations as eac

        d = scripts.define(replace(ability, text="When this creature enters, you get {E}{E}."), ch)
        return None if d is None else {**d, "effects": [*d["effects"], eac.descriptor("amped110c")]}
    if ability.kind == "triggered" and scripts.self_text(ability.text, ch.name) == IRENCRAG:  # 205.1a/b, 613.1d-f: a permanent change of types, name and abilities (it loses the mana ability)
        d = scripts.define(replace(ability, text="Whenever a legendary creature you control enters, you may draw a card."), ch)
        if d is None or not d.get("optional"):
            return None
        become = {"do": "become", "who": "self", "types": ["Artifact"], "artifact_types": ["Equipment"], "legendary": True, "duration": "permanent", "lose_abilities": True}
        gain = {"do": "become", "who": "self", "types": [], "duration": "permanent", "abilities": ["Equip {3}", "Equipped creature gets +3/+3."]}  # (a later timestamp: kept, 613.7a)
        return {**d, "effects": [become, gain, {"do": "named100g", "who": "self", "name": "Everflame, Heroes' Legacy"}]}
    if scripts.self_text(ability.text, ch.name) == TORALF:  # 120.10: the event's amount is the excess; "that permanent" is the one dealt it (selector not_event)
        d = scripts.define(replace(ability, text=TORALF_NATIVE), ch)
        return None if d is None or d.get("target") != {"what": "any"} else {**d, "target": {"what": "any_but_hurt110c"}}
    if ability.kind == "triggered" and scripts.self_text(ability.text, ch.name) == PROCTOR:  # read by :func:`proctor_triggers`, not by an event pass
        return {"kind": "static", "static": "proctor110c", "effects": []}
    text = ability.text.replace(ch.name or "~", "this creature")
    if text == "If you would lose unspent mana, that mana becomes black instead.":  # 614.1a, 500.4: like Ozai's red (wave110b_cards)
        d = scripts.define(replace(ability, text="If you would lose unspent mana, that mana becomes colorless instead."), ch)
        return None if d is None else {**d, "to": "B"}
    if scripts.self_text(ability.text, ch.name) == VAEVICTIS:  # 115.1 a group per player (per_opponent), the rest once after all of them (opponent_aggregate)
        native = scripts.define(replace(ability, text="Whenever ~ attacks, for each player, choose target permanent that player controls. Destroy those permanents."), ch)
        if native is None or [e.get("do") for e in native["effects"]] != ["choose_targets", "destroy"]:
            return None
        return {**native, "effects": [native["effects"][0], {"do": "vaevictis110c", "opponent_aggregate": True}]}
    if text == WILD_HUNT:  # "each Wolf you control" is read natively; the tapped Wolves are bound ("tapped this way") and are the sources
        native = scripts.define(replace(ability, text=WILD_HUNT.split(" That creature deals")[0].replace("Wolf tapped this way", "Wolf you control")), ch)
        fx = (native or {}).get("effects") or []
        if native is None or [e.get("do") for e in fx] != ["tap", "damage"] or not str(fx[1].get("src", "")).startswith("each:"):
            return None
        tap = {**fx[0], "as": "wild110c"}
        hit = {**fx[1], "src": "ref:wild110c", "src_many": True}
        return {**native, "effects": [tap, hit, {"do": "wildhunt110c", "wolves": "ref:wild110c"}]}
    if text.removeprefix("Find New Host — ") == SYMBIOTE:  # the card's other abilities are its one combat damage trigger; an effect that adds abilities without a duration lasts (611.2a)
        granted = SYMBIOTE.replace("this card's other abilities", '"' + SYMBIOTE_OTHER + '"')
        return scripts.define(replace(ability, text=granted), ch)
    if text.split(" (Mana abilities")[0] == ULALEK:  # 707.10: every spell, then every other ability, of the controller's on the stack; new targets for each copy (707.10c)
        native = scripts.define(replace(ability, text="Whenever you cast an Eldrazi spell, you may pay {C}{C}. If you do, copy that spell. You may choose new targets for the copy."), ch)
        fx = (native or {}).get("effects") or []
        if native is None or [e.get("do") for e in fx] != ["optional_payment", "only_if", "copy_spell", "copy_new_targets"]:
            return None
        return {**native, "effects": [fx[0], fx[1], {"do": "ulalek110c"}]}
    if text == KEFKA:  # the cast is the library form's "any number of spells from among cards exiled this way"; the exile and the loss are own primitives
        native = scripts.define(replace(ability, text="At the beginning of your end step, exile the top card of each opponent's library. You may cast any number of spells from among cards exiled this way without paying their mana costs."), ch)
        fx = (native or {}).get("effects") or []
        if native is None or [e.get("do") for e in fx] != ["exile_top", "free_cast"] or fx[0].get("as") != "e0":
            return None
        return {**native, "effects": [{"do": "kefka_exile110c", "as": "e0"}, fx[1], {"do": "kefka_loss110c", "of": "e0"}]}
    if text == NEERA:  # the "you may ... if you do" gate is read as a {0} payment; the spell moves first (it is not countered, 701.6a), else nothing follows (608.2c)
        native = scripts.define(replace(ability, text=NEERA.replace("put it on the bottom of its owner's library", "pay {0}")), ch)
        event = scripts.define(replace(ability, text="Whenever you cast a spell, you may pay {0}. If you do, copy that spell. This ability triggers only once each turn."), ch)  # (the form that keeps the spell: "that spell")
        fx = (native or {}).get("effects") or []
        if event is None or [e.get("do") for e in fx] != ["optional_payment", "only_if", "look_top", "free_cast", "rest_looked"]:
            return None
        return {**event, "effects": [fx[0], {**fx[1], "skip": 4}, {"do": "spell_bottom110c", "skip": 3}, *fx[2:]]}
    if text == OMNATH:  # the look/reveal/mana/hand sequence is one primitive (omnath110c)
        d = scripts.define(replace(ability, text="At the beginning of your first main phase, draw a card."), ch)
        return None if d is None else {**d, "effects": [{"do": "omnath110c"}]}
    if text == PRODDER:
        d = scripts.define(replace(ability, text="At the beginning of your upkeep, draw a card."), ch)
        return None if d is None else {**d, "effects": [{"do": "prodder110c"}]}
    if text == BREATH.replace("this Aura", "~") or ability.text == BREATH:  # 701.21a, 701.3a: the Aura goes to the chosen creature; "if you do" = it got attached
        from app.rules.nontarget_creature_choices import key

        native = scripts.define(replace(ability, text="When enchanted creature deals combat damage to a player, untap all creatures you control and after this phase, there is an additional combat phase."), ch)
        if native is None or [e.get("do") for e in native["effects"]] != ["untap", "extra_phases"]:
            return None
        pick = {"do": "player_chooses", "who": "you", "sel": key("creature you control"), "n": 1, "label": "creature you control", "as": "bof110c"}
        return {**native, "effects": [{"do": "sacrifice", "who": "host", "by": "controller"}, pick, {"do": "attach_to", "src": "self", "who": "ref:bof110c"},
                                      {"do": "attached_if110c", "skip": 2}, *native["effects"]]}
    if text == ECHO_LIFE:
        return {"kind": "static", "static": "echo_life110c", "effects": []}
    if text == RELENTLESS:
        # 107.3f, 115.1: the target is chosen as the ability goes on the stack, X as it resolves; the card returns only if its mana value is that X
        native = scripts.define(replace(ability, text=RELENTLESS.replace("this creature", "~")), ch)  # (reads, with the selector's X unknown at targeting)
        if native is None:
            return None
        fx = native.get("effects") or []
        gone = '"compare":[["mv","==",-1]],'
        if len(fx) != 3 or fx[2].get("do") != "return_card" or not isinstance(native.get("target"), dict) or gone not in native["target"]["what"]:
            return None
        native["target"] = {**native["target"], "what": native["target"]["what"].replace(gone, "")}
        same = {"object": "target", "stat": "mana_value", "op": "==", "n": {"paid_x": fx[0]["bind"]}}
        fx[1] = {**fx[1], "cond": {"all": [fx[1]["cond"], same]}}
        return native
    if text == "Each opponent who attacked you or a planeswalker you control this turn can't cast spells.":  # 601.3, like Angelic Arbiter (wave110a_spells)
        d = scripts.define(replace(ability, text="Your opponents can't cast spells."), ch)
        return None if d is None else {**d, "when": "attacked_me110c"}
    if text == "Whenever an opponent casts a spell during their turn, they can't attack you or planeswalkers you control this turn.":  # 508.1c: their creatures
        return scripts.define(replace(ability, text=text.replace("they can't attack", "creatures that player controls can't attack")), ch)
    if text == SHUTTLE:
        native = scripts.define(replace(ability, text=SHUTTLE.split(" or you gain control")[0] + ", or you draw a card."), ch)
        if native is None or native["effects"][0].get("do") != "villain":
            return None
        v = native["effects"][0]
        v["b"] = [{"do": "shuttle110c", "player": "event_player"}]
        v["labels"] = [v["labels"][0], "You gain control of a creature of your choice that player controls until end of turn. If you gain control of a creature this way, tap it, and it's attacking that player."]
        return native
    if text == GLYPH:  # 608.2d: not targets; the intervening "if you cast it" (603.4) is read natively from the same trigger
        native = scripts.define(replace(ability, text="When this artifact enters, if you cast it, destroy all creatures."), ch)
        if native is None or [e.get("do") for e in native["effects"]] != ["only_if", "destroy_all"]:
            return None
        return {**native, "effects": [native["effects"][0], {"do": "glyph110c"}]}
    if text == SIEGE:
        # 701.20a, 603.12: reveal first; the reflexive ability then chooses its target (X can be 0, so it always triggers): the payment-X reflexive, fed by the count
        native = scripts.define(replace(ability, text="When this Siege enters, you may pay {X}. When you do, this Siege deals X plus 2 damage to any other target."), ch)
        reveal = scripts.parse_effects("Reveal any number of Dragon cards in your hand. Draw X cards, where X is the number of cards revealed this way.")
        fx = (native or {}).get("effects") or []
        if native is None or reveal is None or [e.get("do") for e in fx] != ["optional_payment", "reflexive"] or len(reveal[0]) != 2:
            return None
        count = {"do": "revealed_x110c", "bind": fx[0]["bind"], "n": reveal[0][1]["n"]}
        return {**native, "effects": [reveal[0][0], count, {**fx[1], "cond": {"succeeded": fx[0]["bind"]}}]}
    if text == INCINERATOR:  # 107.3f: X chosen as it resolves; 701.59a: cards with total mana value X or greater (the payment-X reflexive, paid by exiling)
        native = scripts.define(replace(ability, text=INCINERATOR.replace("collect evidence X", "pay {X}")), ch)
        fx = (native or {}).get("effects") or []
        if native is None or [e.get("do") for e in fx] != ["optional_payment", "reflexive"]:
            return None
        return {**native, "effects": [{"do": "evidence_x110c", "bind": fx[0]["bind"]}, *fx[1:]]}
    if text != HELLION:
        return None
    native = scripts.define(replace(ability, text="When this creature enters, ~ deals 3 damage to you and target creature. The damage can't be prevented."), ch)
    if native is None or [e.get("do") for e in native["effects"]] != ["damage", "damage"]:
        return None
    amount = {"ref_amount": "gc_hi"}  # 107.1: a number of the controller's choice, chosen as the ability resolves (one chooser: the highest is it)
    pick = {"do": "gc_choose", "who": "you", "what": "number", "min": 0, "secret": False, "as": "gc", "say": "an amount of damage"}
    native["effects"] = [pick, {"do": "gc_extremes", "as": "gc"}, *({**e, "n": amount} for e in native["effects"])]
    return native


def echo_cost(ch: Any) -> tuple[str, Any] | None:
    """triggers.echo_cost's part: a mana cost the payment prices at its time (effects.pay_or_sacrifice reads "life110c")."""
    ours = any(ab.text.replace(ch.name or "~", "this creature") == ECHO_LIFE for ab in ch.abilities)
    return ("mana", "life110c") if ours else None


def shuttle(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Midnight Crusader Shuttle, option B: the controller chooses (608.2d, not a target) a creature the facing player controls, gains control of it until end of turn,
    taps it and it attacks that player (508.4: put onto the battlefield attacking only; it never "attacked", so no attack triggers)."""
    from app.rules import selectors

    pid = e["player"].removeprefix("player:")
    sel = selectors.parse("creature")
    assert sel is not None
    key = selectors.replace(sel, controller=f"player:{pid}").key()
    added = [{"do": "player_chooses", "who": "you", "sel": key, "n": 1, "label": "creature", "any": True, "as": "shuttle110c"},
             {"do": "gain_control", "who": "ref:shuttle110c", "duration": "end_of_turn"}, {"do": "tap", "who": "ref:shuttle110c"},
             {"do": "shuttle_attack110c", "at": pid}]
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]
    return True


def shuttle_attack(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, token_grammar

    for cid in effects._cards(plan, ctx, "ref:shuttle110c"):
        card = plan.state.cards[cid]
        if card.controller == ctx["controller"] and card.zone.endswith(":battlefield"):
            token_grammar._attack_with(plan, [cid], e["at"], ctx["controller"])
    return True


def glyph(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Unstable Glyphbridge: you choose one creature with power 2 or less for each player, in turn order (101.4), then every other creature is destroyed (701.8)."""
    from app.rules import selectors

    small, every = selectors.parse("creature with power 2 or less"), selectors.parse("creature")
    assert small is not None and every is not None
    added: list[dict[str, Any]] = [
        {"do": "player_chooses", "who": "you", "sel": selectors.replace(small, controller=f"player:{p}").key(), "n": 1, "label": "creature", "any": True,
         "add": True, "as": "gco"} for p in plan.apnap() if p in plan.live()]
    added.append({"do": "destroy", "who": f"except:gco|{every.key()}"})
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *added, *ctx["effects"][at:]]
    return True


def revealed_x(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The number of cards the reveal before it showed, as the X of the reflexive ability that follows (608.2h: counted once, now)."""
    from app.rules import paid_x, this_way

    paid_x._record(ctx, e["bind"], True, this_way.count(plan, ctx, e["n"]))
    return True


def evidence_x(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"You may collect evidence X": X is chosen as this resolves (107.3f), then cards with total mana value X or greater are exiled from the graveyard (701.59a)."""
    from app.game.rules_state import DecisionOption
    from app.rules import optional_payment, paid_x
    from app.rules.plan import decide

    pid = ctx["controller"]
    total = sum(plan.ch(plan.state.cards[c]).mana_value for c in plan.state.zones.get(f"{pid}:graveyard", []))
    options = [DecisionOption(id=f"{paid_x.CHOOSE}{n}", label=f"Collect evidence {n}") for n in range(int(total) + 1)]
    options.append(DecisionOption(id=optional_payment.DECLINE, label="Don't collect evidence"))
    decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: collect evidence X? Choose X", options=options,
           resume={"step": "evidence_x110c", "ctx": ctx, "e": e}, source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def resume_evidence_x(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.game.rules_state import DecisionOption, emit
    from app.rules import effects, optional_payment, paid_x
    from app.rules.plan import decide

    ctx, e = d.resume["ctx"], d.resume["e"]
    pid = ctx["controller"]
    if "cards" in d.resume:  # the second question: which cards
        x, picked = d.resume["x"], list(dict.fromkeys(chosen))
        if sum(plan.ch(plan.state.cards[c]).mana_value for c in picked) < x or not set(picked) <= set(d.resume["cards"]):
            raise ActionError(f"Choose cards with total mana value {x} or more")
        if picked:
            plan.do({"type": "move", "card_ids": picked, "to": {"zone": "exile"}}, actor=pid)
        emit(plan.state, "designation", counter="collect_evidence", player=pid)
        paid_x._record(ctx, e["bind"], True, x)
        effects.continue_effects(plan, ctx)
        return
    if chosen[0] == optional_payment.DECLINE:
        paid_x._record(ctx, e["bind"], False, 0)
        effects.continue_effects(plan, ctx)
        return
    x = int(chosen[0][len(paid_x.CHOOSE):])
    if x == 0:
        emit(plan.state, "designation", counter="collect_evidence", player=pid)
        paid_x._record(ctx, e["bind"], True, 0)
        effects.continue_effects(plan, ctx)
        return
    gy = list(plan.state.zones.get(f"{pid}:graveyard", []))
    decide(plan, player=pid, kind="choose_cards", prompt=f"Exile cards with total mana value {x} or more from your graveyard",
           options=[DecisionOption(id=c, label=f"{plan.state.cards[c].name or 'Card'} (mana value {plan.ch(plan.state.cards[c]).mana_value:g})", card_id=c) for c in gy],
           min_choices=1, max_choices=len(gy), resume={"step": "evidence_x110c", "ctx": ctx, "e": e, "x": x, "cards": gy},
           source=plan.state.cards.get(ctx.get("source_card") or ""))


def _omnath_hand(plan: Plan, pid: str, cid: str) -> None:
    plan.do({"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": "hand"}}, actor=pid)


def omnath(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Omnath, Locus of All: 701.20a (reveal), 106.1 (mana in the card's colors); the card goes to its owner's hand either way."""
    import re

    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    pid = ctx["controller"]
    lib = plan.state.zones.get(f"{pid}:library", [])
    if not lib:
        return True
    cid = lib[0]
    if len(re.findall(r"\{[^}]*[WUBRG][^}]*\}", plan.ch(plan.state.cards[cid]).mana_cost)) < 3:  # 202.1: a hybrid or Phyrexian symbol of a color counts
        _omnath_hand(plan, pid, cid)
        return True
    decide(plan, player=pid, kind="choose_one", prompt=f"Reveal {plan.state.cards[cid].name} (add three mana in its colors) or put it into your hand?",
           options=[DecisionOption(id="reveal", label="Reveal it"), DecisionOption(id="hand", label="Don't reveal it")],
           resume={"step": "omnath110c", "ctx": ctx, "card": cid}, source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def resume_omnath(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, cid, pid = d.resume["ctx"], d.resume["card"], d.player
    if chosen[0] == "reveal":
        plan.do({"type": "reveal", "card_ids": [cid]}, actor=pid)
        _omnath_hand(plan, pid, cid)
        colors = [c for c in "WUBRG" if c in plan.ch(plan.state.cards[cid]).colors]
        if not effects.add_mana(plan, ctx, {"of": colors, "n": 3}):
            return
    else:
        _omnath_hand(plan, pid, cid)
    effects.continue_effects(plan, ctx)


def _prodder_ask(plan: Plan, ctx: dict[str, Any], cid: str, rest: list[str], yes: list[str]) -> bool:
    """608.2d: every opponent chooses, in turn order, knowing the revealed card; then the effect happens once: the card to the graveyard and its mana value dealt to
    each who chose so, or to the hand when nobody did."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    if rest:
        card = plan.state.cards[cid]
        decide(plan, player=rest[0], kind="choose_one", prompt=f"Have {plan.name(ctx['controller'])} put {card.name} into their graveyard? You take {plan.ch(card).mana_value:g} damage if so",
               options=[DecisionOption(id="yes", label="Yes, take the damage"), DecisionOption(id="no", label="No")],
               resume={"step": "prodder110c", "ctx": ctx, "card": cid, "rest": rest, "yes": yes}, source=plan.state.cards.get(ctx.get("source_card") or ""))
        return False
    pid = ctx["controller"]
    if not yes:
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": "hand"}}, actor=pid)
        return True
    mv = int(plan.ch(plan.state.cards[cid]).mana_value)
    plan.do({"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": "graveyard"}}, actor=pid)
    if mv > 0 and len(yes) > 1:
        # No CR rule or official ruling settles "that player" when several opponents say yes (608.2e only orders the choices): refuse, hand the damage to manual play.
        decide(plan, player=pid, kind="manual_resolution", options=[DecisionOption(id="done", label="Done")],
               prompt=f"Sin Prodder: {', '.join(plan.name(p) for p in yes)} each chose yes. Deal {mv} damage by hand as you rule, then press Done.",
               resume={"step": "prodder_manual110c", "ctx": ctx})
        return False
    if mv > 0:
        ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "damage", "who": f"player:{p}", "n": mv} for p in yes]
    return True


def prodder(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Sin Prodder: 701.20a (reveal), 608.2e (the opponents choose in turn order), 120.3 (the damage is Sin Prodder's)."""
    pid = ctx["controller"]
    lib = plan.state.zones.get(f"{pid}:library", [])
    if not lib:
        return True
    plan.do({"type": "reveal", "card_ids": [lib[0]]}, actor=pid)
    return _prodder_ask(plan, ctx, lib[0], [p for p in plan.apnap() if p != pid and p in plan.live()], [])


def resume_prodder(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    yes = [*r["yes"], d.player] if chosen[0] == "yes" else r["yes"]
    if _prodder_ask(plan, r["ctx"], r["card"], r["rest"][1:], yes):
        effects.continue_effects(plan, r["ctx"])


def proctor_triggers(plan: Plan, pending: Any, cause: Any, only: list[Any] | None = None) -> None:
    """Strict Proctor: an entering permanent caused ``pending`` (and its 603.2d copies) to trigger; each Proctor on the battlefield triggers at the same time for
    each (``only``: just these instances, the extras a later join of the batch added; 603.2, 603.3b: all go on the stack together, their controllers order them; a Proctor's ability put below the one it counters finds nothing to counter)."""
    from app.game.rules_state import PendingTrigger
    from app.rules import scripts, trigger_multipliers

    if cause is None or cause.kind != "enter":
        return
    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or not plan.in_game(c) or plan.manual(c) or c.face_down:
            continue
        if not any(d.get("static") == "proctor110c" for d in scripts.definitions(plan.ch(c)).values()):
            continue
        for p in only if only is not None else [pending, *trigger_multipliers._extras(plan).get(pending.id, ([], 0))[0]]:
            plan.rules.proctor_links110c.setdefault(p.id, "")
            plan.rules.pending_triggers.append(PendingTrigger(
                id=secrets.token_hex(4), controller=c.controller, source_card=c.id, source_object=plan.oid(c), name=c.name,
                ability={"kind": "triggered", "effects": [{"do": "proctor110c", "link": p.id}]}, key=f"proctor110c:{p.id}", event=cause))


def spell_bottom(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Neera: the spell that triggered the ability goes from the stack to the bottom of its owner's library (not countered); if it already left, skip the rest (608.2c)."""
    from app.rules import effects

    sids = effects._stack_targets(plan, ctx, {"who": "event_spell"})
    if not sids:
        ctx["next"] += e["skip"]
        return True
    r = plan.rules
    for sid in sids:
        oid = plan.oid(sid)
        r.stack.pop(sid, None)
        r.buyback = [o for o in r.buyback if o != oid]
        r.rebound_cast = [o for o in r.rebound_cast if o != oid]
        r.exile_resolves.pop(oid, None)
        owner = plan.state.cards[sid].owner
        to = {"player": owner, "zone": "exile" if oid in r.flashback else "library"}  # 702.34a: a flashback spell is exiled wherever it would go
        r.flashback = [o for o in r.flashback if o != oid]
        plan.do({"type": "move", "card_ids": [sid], "to": to, "position": "bottom"}, actor=ctx["controller"])
    return True


def vaevictis(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Vaevictis Asmadi: the chosen permanents are sacrificed together (701.21a, by their controllers); each player who sacrificed one reveals their top card (701.20a), and those
    that are permanent cards enter together (614.12a). A permanent that left or is no longer a legal target is not sacrificed (608.2b)."""
    from app.rules import attachments, effects

    cards = [c for c in effects._cards(plan, ctx, "all_targets") if plan.state.cards[c].zone.endswith(":battlefield")]
    who = {c: plan.state.cards[c].controller for c in cards}
    effects._sacrifice_cards(plan, cards, ctx["controller"], ctx)
    gone = {who[c] for c in cards if not plan.state.cards[c].zone.endswith(":battlefield")}
    entries = []
    me = ctx["controller"]
    for pid in (p for p in plan.apnap() if p in gone):
        ctx["controller"] = pid
        try:
            effects.look_top(plan, ctx, {"n": 1, "player": "you", "reveal": True, "exact_look": True})
        finally:
            ctx["controller"] = me
        top = ctx.get("looked") or []
        if top and plan.ch(plan.state.cards[top[0]]).types & {"Artifact", "Battle", "Creature", "Enchantment", "Land", "Planeswalker"}:
            entries.append({"card": top[0], "player": pid, "actor": pid})
    return attachments.enter(plan, entries, ctx) if entries else True


def wildhunt(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Master of the Wild Hunt: the target creature deals damage equal to its power, divided as ITS controller chooses (any number, so 0 is fine), among the Wolves tapped this way
    that are still on the battlefield (120.3, 608.2h; the engine's "divide" answer, with 0 allowed)."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    target = next(iter(effects._cards(plan, ctx, "target")), None)
    wolves = [c for c in effects._cards(plan, ctx, e["wolves"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    if target is None or not plan.state.cards[target].zone.endswith(":battlefield") or not wolves:
        return True
    pt = plan.ch(plan.state.cards[target]).pt
    power = max(0, pt[0]) if pt else 0
    if not power:
        return True
    if len(wolves) == 1:
        return effects._deal(plan, ctx, [(effects._card_source(plan, target), wolves[0], power)])
    decide(plan, player=plan.state.cards[target].controller, kind="divide", prompt=f"Divide {power} damage from {plan.state.cards[target].name} among the Wolves",
           options=[DecisionOption(id=w, label=plan.state.cards[w].name or "Wolf", card_id=w) for w in wolves], min_choices=len(wolves), max_choices=len(wolves),
           display={"kind": "divide", "total": power, "what": "damage", "least": 0},
           resume={"step": "wildhunt110c", "ctx": ctx, "total": power, "least": 0, "target": target, "wolves": wolves})
    return False


def resume_wildhunt(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    src = plan.state.cards.get(r["target"])
    hits = [(effects._card_source(plan, r["target"]), w, int(n)) for w, n in zip(r["wolves"], chosen, strict=True)
            if src is not None and src.zone.endswith(":battlefield") and plan.state.cards[w].zone.endswith(":battlefield") and int(n) > 0]
    if effects._deal(plan, r["ctx"], hits) if hits else True:
        effects.continue_effects(plan, r["ctx"])


def ulalek(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Ulalek: copy every spell the controller controls on the stack (copies of spells are spells too), then every other ability they control there (not this one, 707.10);
    each copy may get new targets. A spell or ability that can't be copied is skipped (113.6g); one the engine can't copy is handed to manual play."""
    from app.rules import copying

    me = ctx["controller"]
    mine = [sid for sid in plan.state.zones.get("stack", []) if plan.state.cards[sid].controller == me and sid != ctx.get("stack_id")]  # (a permanent spell has no stack entry)
    objects = []
    for sid in sorted(mine, key=lambda sid: plan.state.cards[sid].ability is not None):  # (spells first, each group in stack order)
        reason = copying.uncopyable(plan, plan.state.cards[sid])
        if reason:
            return copying._manual_each(plan, ctx, me, plan.state.cards[sid])
        if reason is None:
            objects.append((sid, plan.oid(sid), 1))
    if not objects:
        return True
    return copying.run(plan, copying.new_job(ctx, controller=me, objects=objects, retarget=True, label=ctx.get("name") or "Copy"))


def kefka_exile(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Kefka: from each opponent's graveyard (turn order from the controller), the table picks one card at random (no bias: not chosen by a player) and exiles it,
    face up in its owner's exile; they are "the cards exiled this way"."""
    import secrets

    from app.rules import context, effects

    me = ctx["controller"]
    order = plan.apnap()
    order = [p for p in [*order[order.index(me):], *order[:order.index(me)]] if p != me] if me in order else [p for p in order if p != me]
    picked = []
    for pid in order:
        gy = sorted(plan.state.zones.get(f"{pid}:graveyard", []))
        if gy:
            picked.append((pid, (plan.rng or secrets.SystemRandom()).choice(gy)))
    before = [r for _, c in picked if (r := context.ref_of(plan, c)) is not None]
    for pid, cid in picked:
        plan.note(f"{ctx.get('name') or 'It'}: {plan.name(pid)}'s graveyard, chosen at random →", [cid], actor=me)
        plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "exile"}}, actor=me)
    effects._moved(plan, ctx, e, before)
    return True


def kefka_loss(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Kefka: each player who owns a spell cast this way (one of the exiled cards now on the stack) loses life equal to its mana value (a graveyard is one player's, so each owns at most one)."""
    from app.rules import context

    lose = []
    for ref in context._object_refs(ctx, e["of"], was=True):
        card = plan.state.cards.get(ref.card)
        if card is not None and card.zone == "stack" and card.ability is None:
            lose.append({"do": "lose_life", "who": f"player:{card.owner}", "n": int(plan.ch(card).mana_value)})
    ctx["effects"][ctx["next"]:ctx["next"]] = lose
    return True


def proctor(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Counter that ability unless its controller pays {2} (701.6a; 118.12): nothing if it already left the stack."""
    from app.rules import effects

    sid = plan.rules.proctor_links110c.get(e["link"])
    return True if not sid else effects.counter_unless(plan, ctx, {"object": sid, "cost": "{2}"})


def yidaro(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Yidaro: back to the battlefield from the graveyard after its fourth cycling this game (the count is of the player's cycled cards by that name), else shuffled in."""
    from app.cards.names import normalize_name

    n = plan.rules.named_cycles110c.get(ctx["controller"], {}).get(normalize_name("Yidaro, Wandering Monster"), 0)
    back = {"do": "return_card", "to": "battlefield", "tapped": False, "under": "you", "who": "self_gy"}
    ctx["effects"][ctx["next"]:ctx["next"]] = [back] if n >= 4 else [{"do": "return_card", "to": "library_top", "who": "self_gy"}, {"do": "shuffle_library", "who": "you"}]
    return True


def shuffle_dead(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"... shuffle this card into its owner's library" of a dies trigger (Sin): the card the source became in the graveyard (400.7), if it is still there; the library is
    shuffled even when the card is gone (701.24c)."""
    src = plan.state.cards.get(ctx.get("source_card") or "")
    owner = src.owner if src is not None else ctx["controller"]
    became = {o.get("object_id") for o in (ctx.get("event") or {}).get("new_objects") or []}  # (the event's new objects, 400.7e)
    if src is not None and src.zone.endswith(":graveyard") and plan.oid(src) in became:
        plan.do({"type": "move", "card_ids": [src.id], "to": {"player": owner, "zone": "library"}}, actor=ctx["controller"])
    plan.do({"type": "shuffle", "player": owner, "zone": "library"}, actor=owner)
    return True


def prodder_done(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, d.resume["ctx"])


def attached_if(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Skip the next ``skip`` instructions unless the source Aura is attached to a permanent (it moved there, 303.4)."""
    src = plan.state.cards.get(ctx.get("source_card") or "")
    if src is None or not src.zone.endswith(":battlefield") or plan.oid(src) != ctx.get("source_object") or not src.attached_to:
        ctx["next"] += e["skip"]
    return True


RESUME = {"prodder110c": resume_prodder, "prodder_manual110c": prodder_done, "omnath110c": resume_omnath, "evidence_x110c": resume_evidence_x, "wildhunt110c": resume_wildhunt}
PRIMITIVES = {"shuffle_dead110c": shuffle_dead, "yidaro110c": yidaro, "proctor110c": proctor, "vaevictis110c": vaevictis, "kefka_exile110c": kefka_exile, "kefka_loss110c": kefka_loss, "ulalek110c": ulalek, "wildhunt110c": wildhunt, "spell_bottom110c": spell_bottom, "attached_if110c": attached_if, "prodder110c": prodder, "omnath110c": omnath, "evidence_x110c": evidence_x, "revealed_x110c": revealed_x, "glyph110c": glyph, "shuttle110c": shuttle, "shuttle_attack110c": shuttle_attack}
