"""Optional costs paid as a spell or ability resolves: "You may pay {2}. If you do, draw a card.",
"You may sacrifice another creature. If you do, …", "… unless that player pays {1}".

CR 118.12: "[A player] may [do something]. If [that player] [does, doesn't, or can't], [effect]."
— the action is a cost, paid when the spell or ability resolves; the "if" clause checks whether the
player chose to pay it (not what events actually occurred). 118.12a: "[Do something] unless [a
player does something else]" means "[A player may do something else]. If [that player doesn't],
[do something]". 118.3: a player can't pay a cost without the resources to pay it fully; 601.2h:
partial payments are not allowed, unpayable costs can't be paid; 608.2d: a player can't choose an
option that's impossible ("A player who controls no creatures can't choose the sacrifice
option"). 608.2c: the instructions are followed in order — so the payment is an effect
(``optional_payment``) that records its result in the resolution context (app/rules/context.py,
``bind_payment``), and the dependent effects follow it behind an ``only_if`` on that binding
(``{"succeeded": "pay0"}``, negated for "unless"). The binding is named by the grammar, so a
second "if you do" in the same ability refers to its own payment.

The decision (PAY / DECLINE) goes to the payer only — the controller, or "that player" / "its
controller" — and PAY is offered only while the whole cost is payable (118.3). Paying is
transactional: the complete cost is validated again when the payer answers (mana abilities can
change the table while the prompt is open); if it can't be paid in full any more, nothing is
paid and the dependent effects don't happen. Non-mana parts go through the generic cost engine
(app/rules/costs.py components, app/rules/cost_payment.py): life, energy, discard, sacrifice,
tapping other permanents, removing counters, exiling (this card or cards from your graveyard),
returning permanents to hand. Mana goes through the mana payment (app/rules/casting.py).

Reflexive triggers ("When you do", 603.12): a "you may [cost]" followed by "When you do, …" is the same
payment; the reflexive ability triggers if it was made (wave 3R1: scripts._reflexive, effects.reflexive).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef, PaymentRecord
from app.game.state import CardInstance
from app.rules import context, cost_payment, mana_units, optional_counter55, selectors
from app.rules import costs as C
from app.rules import mana as M
from app.rules.costs import AbilityCost
from app.rules.plan import Plan, decide

Context = dict[str, Any]

# The resume step shares its name with the pay-or-sacrifice prompt so that casting.paying_now lets
# the payer tap their mana while it is open (the mana-while-paying path); the resume payload tells
# the two apart (``opt`` is only ours).
STEP = "pay_or_sacrifice"
PAY, DECLINE = "pay", "decline"
SUPPORTED = frozenset({C.MANA, C.PAY_LIFE, C.PAY_ENERGY, C.SACRIFICE, C.DISCARD, C.EXILE, C.EXILE_FROM_GRAVEYARD,
                       C.REMOVE_COUNTER, C.RETURN_PERMANENT, C.TAP_OTHER, C.PUT_COUNTER, C.DISCARD_HAND,
                       C.MILL, "EXILE_FROM_HAND", C.EXILE_TO_GY,  # (MILL, EXILE_FROM_HAND: wave 8C; EXILE_TO_GY: wave 15C)  # (PUT_COUNTER: wave 6F, blight)
                       C.FORAGE, C.COLLECT_EVIDENCE, C.BEHOLD, C.WATERBEND, "SOURCE_DAMAGE"})  # (C.BEHOLD: wave 49B)  # (SOURCE_DAMAGE: wave 27A; wave 26C: "you may forage", "you may collect evidence 4": 701.61a, 701.59a)
FLEXIBLE = (C.FORAGE, C.COLLECT_EVIDENCE)  # (wave 26C) the cards that pay are chosen as a whole (cost_payment._flexible_options)
_MANA_ONLY = re.compile(r"^(\{[^}]+\})+$")


# -- if you do (wave 6F) -- "You may blight 1. If you do, …" (Scuzzback Scrounger, Sourbread Auntie): 701.68a, to blight N
# is to put N -1/-1 counters on a creature you control — paid as it resolves (118.12) through the activation-cost part
# (cost_payment._pay_new_part: one creature, all N counters on it); 701.68b: with no creature the option isn't offered.
# (wave 110F) the one either-or discard read as an optional payment, as Steamcore Scholar's scenario tests it
_STEAMCORE_DISCARD = "Discard an instant or sorcery card or a creature card with flying"


def _blight_like(comp: C.CostComponent) -> bool:
    """A "put N counters on a creature you control" part (blight): one chosen permanent of the payer's — or "discard
    your hand" (every card in it; ``paid_x`` records how many, for "draw that many cards"); -- champion (wave 12B) -- or one chosen
    permanent exiled (702.72a); -- cards (wave 110F) -- or a discard of either of two descriptions ("an instant or sorcery card or a creature card with flying"); -- keywords (wave 43C) -- or a counter put on the source itself ("Cumulative upkeep—Put a -1/-1 counter on this
    creature": not on the battlefield, it can't be paid, cost_payment._new_part_problem)."""
    return comp.kind in (C.FORAGE, C.COLLECT_EVIDENCE, C.WATERBEND) or (comp.kind == C.PUT_COUNTER and comp.alt is None and not comp.x) \
        or comp.kind == C.DISCARD_HAND or comp.kind == C.MILL \
        or (comp.kind == C.EXILE and comp.selector is not None and comp.amount == 1) \
        or (comp.kind == C.DISCARD and comp.alt is not None and comp.selector is not None and comp.text == _STEAMCORE_DISCARD) \
        or (comp.kind == C.SACRIFICE and comp.alt is not None and comp.selector is not None)  # (wave 8C: mill 701.17b; "another creature or an artifact")


# -- grammar helpers (app/rules/scripts.py) --------------------------------------------------------
def cost_text(phrase: str) -> str | None:
    """The cost an Oracle "you may …" / "unless … pays …" phrase names ("pay {2}", "sacrifice
    another creature", "pay 2 life", "pay {1} and discard a card"), as the comma-separated cost
    text the cost parser reads — or None when the engine couldn't pay every part by itself."""
    if " another " not in f" {phrase} ":  # -- if you do (wave 15C) -- the payer chooses what pays (Torment of Scarabs); "another" is
        phrase = phrase.replace(" of their choice", "")  # other than what? (an Aura's: the enchanted creature) — not read
    phrase = re.sub(r"\b(non[a-z]+), (?=non[a-z]+ )", r"\1 ", phrase)  # -- trigger other (wave 39A) -- "two nonland, nontoken permanents" (Rakdos, Patron of Chaos): one adjective list, not two costs
    parts = []
    # -- if you do (wave 6F) -- "sacrifice an artifact, creature, enchantment, land, or planeswalker" (Braids): one
    # permanent of any of those types — the cost parser's "a creature or artifact or land"
    listed = re.fullmatch(r"(?P<verb>sacrifice) (?P<a>an?) (?P<items>(?:[a-z]+, )+)or (?P<last>[a-z]+)", phrase.strip())
    if listed is not None:
        words = [w.strip() for w in listed["items"].split(",") if w.strip()] + [listed["last"]]
        phrase = f"{listed['verb']} {'an' if words[0][0] in 'aeiou' else 'a'} {' or '.join(words)}"
    for raw in re.split(r", | and ", phrase.strip()):
        part = raw.strip()
        if part.startswith("pay ") and _MANA_ONLY.match(part[4:]) and not re.fullmatch(r"(?:\{E\})+", part[4:]):  # ({E}: wave 3E)
            part = part[4:]
        elif re.fullmatch(r"\d+ life", part):  # "… unless that player pays 3 life"
            part = "pay " + part
        elif part == "put a card from your hand on the bottom of your library":  # -- if you do (wave 6F) --
            return _HAND_TO_BOTTOM_TEXT if len(re.split(r", | and ", phrase.strip())) == 1 else None
        elif part in ("discard your hand", "discard all the cards in your hand"):  # -- if you do (wave 6F) --
            part = "discard your hand"  # (701.9a; with no card in hand it may still be chosen: Wizards rulings on
            # Narset, Jeskai Waymaster 2025-04-04 and Jackdaw 2024-07-05 — "If you do" is then true, 118.12)
        if not part:
            return None
        parts.append(part[0].upper() + part[1:])
    text = ", ".join(parts)
    return text if parse(text) is not None else None


# -- if you do (wave 6F) -- "You may sacrifice an artifact or discard a card. If you do, …" (Reckless Detective, Vision of
# Love): one cost or the other, the payer's pick among those they can pay in full (118.3); "If you do" is true when
# either was paid (118.12).
_ALT_VERB = re.compile(r" or (?=(?:sacrifice|discard|pay|exile|return|tap|remove|put) )")


def alternatives(phrase: str) -> list[str] | None:
    """"sacrifice an artifact or discard a card" → ["Sacrifice an artifact", "Discard a card"], or None (not two
    costs each read alone)."""
    pieces = _ALT_VERB.split((phrase if " another " in f" {phrase} " else phrase.replace(" of their choice", "")).strip())
    if len(pieces) != 2:
        return None
    found = [cost_text(p) for p in pieces]
    return [f for f in found if f is not None] if all(found) else None


# -- if you do (wave 6F) -- "You may put a card from your hand on the bottom of your library. If you do, draw a card."
# (Fire Prophecy, Manhole Missile, Volcanic Spite): a card of the payer's choice from their hand (chosen privately,
# 400.2), moved to the bottom of their library (400.2: a hidden zone, the card is never revealed); payable with any card in
# hand (118.3).
HAND_TO_BOTTOM = "HAND_TO_BOTTOM"
_HAND_TO_BOTTOM_TEXT = "Put a card from your hand on the bottom of your library"


def _hand_to_bottom() -> AbilityCost | None:
    key = C._selector("card", zone="hand")
    return AbilityCost(components=(C.CostComponent(HAND_TO_BOTTOM, selector=key, text=_HAND_TO_BOTTOM_TEXT),)) if key else None


_EXILE_FROM_HAND = re.compile(r"^Exile (?:a|an|one) (?:[\w\-]+ )*card(?: with mana value \d+ or (?:less|greater))? from your hand$")  # (wave 18F: Isochron Scepter)
# -- if you do (wave 15C) -- "You may reveal a Dinosaur card from your hand. If you do, …" (Priest of the Wakening Sun): revealing is
# the cost (701.20a: shown to everyone, it stays in the hand); payable only with such a card in hand (118.3)
REVEAL_FROM_HAND = "REVEAL_FROM_HAND"
_REVEAL_FROM_HAND = re.compile(r"^Reveal (?:a|an) (?P<what>[A-Za-z]+ card) from your hand$")


# -- unless damage (wave 27A) -- "… unless its controller has ~ deal 4 damage to them." (Lava Blister, Molten Influence, Skullscorch): the payer
# has the source deal the damage to them as the cost (118.12a); it is damage dealt by the source (120.3: prevention, protection and lifelink
# apply, 615), and the cost counts as paid even if the damage is prevented (118.12: what is chosen, not what happens).
_SOURCE_DAMAGE = re.compile(r"^Have (?:~|this [a-z]+) deal (?P<n>\d+) damage to you$")


def parse(text: str) -> AbilityCost | None:
    """The cost text as components, or None if any part isn't one the engine pays here."""
    if (d := _SOURCE_DAMAGE.match(text)) is not None:  # (wave 27A)
        return AbilityCost(components=(C.CostComponent("SOURCE_DAMAGE", amount=int(d["n"]), text=text),))
    if text == _HAND_TO_BOTTOM_TEXT:  # -- if you do (wave 6F) --
        return _hand_to_bottom()
    if (r := _REVEAL_FROM_HAND.match(text)) is not None:  # -- if you do (wave 15C) --
        key = C._selector(r["what"], zone="hand")
        return AbilityCost(components=(C.CostComponent(REVEAL_FROM_HAND, selector=key, text=text),)) if key else None
    if text.startswith("Behold "):  # -- commander sweep (wave 49B) -- "You may behold a Dragon. If you do, …" (Sarkhan, Dragon Ascendant): 701.4a, a Dragon card revealed from your hand or a Dragon you control
        behold = C._extra_part(text)
        return AbilityCost(components=(behold,)) if behold is not None and behold.kind == C.BEHOLD else None
    if (m := _EXILE_FROM_HAND.match(text)) is not None:  # -- if you do (wave 8C) -- "Exile a creature card from your hand"
        from app.rules import alt_costs

        part = alt_costs._part(text)
        return AbilityCost(components=(part,)) if isinstance(part, C.CostComponent) and m else None
    cost = C.parse_ability_cost(text, anyn=False)
    if cost.unsupported or not cost.components or "{X}" in cost.mana.upper() or cost.energy_x:
        return None
    if any(c.activation_only and not _blight_like(c) and c.life_rule != "half" for c in cost.components) and not optional_counter55.allowed(cost):  # (wave 4H; wave 6F: blight; wave 100D: half your life, 119.4)
        return None
    if any(c.kind not in SUPPORTED for c in cost.components):
        return None
    if any(c.kind == C.WATERBEND for c in cost.components) and (
            sum(c.kind == C.WATERBEND for c in cost.components) != 1
            or any(c.kind not in (C.MANA, C.WATERBEND) for c in cost.components)):
        return None  # Resolution waterbending: one cost, paid with mana and its own helpers.
    if any(c.kind == C.DISCARD and c.selector is None for c in cost.components):  # -- ability words (wave 4F) --
        return None  # ("discard this card": a cost of an ability that works from the hand, never an optional payment)
    return cost


# -- the payer -------------------------------------------------------------------------------------
def payer_of(plan: Plan, ctx: Context, who: str) -> str | None:
    """Who is offered the payment: "you" (the controller), "target" / "target:<g>" (a target
    player, or the controller of a target object: "its controller"), or a binding / the trigger
    event's player ("that player", app/rules/effects._players)."""
    from app.rules import effects  # (effects registers this module's primitive)

    if who == "you":
        return str(ctx["controller"])
    if who == "target" or who.startswith("target:"):
        for t in effects.target_refs(ctx, who):
            if t["id"] in plan.state.players:
                return str(t["id"]) if t["id"] in plan.live() else None
            card = plan.state.cards.get(t["id"])
            if card is not None and plan.oid(card) == t.get("object_id"):
                on_stack_or_field = card.zone == "stack" or card.zone.endswith(":battlefield")
                pid = card.controller if on_stack_or_field else card.owner  # 108.4a
                return pid if pid in plan.live() else None
        return None
    found = effects._players(plan, ctx, who)
    return found[0] if found else None


# -- validation (118.3: the whole cost, before anything moves) ------------------------------------
def _source(plan: Plan, ctx: Context) -> CardInstance:
    """The source, for the parts of a cost about it (and selectors' "another"). If the card is
    gone, a stand-in that is nowhere: costs about ~ then can't be paid."""
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is not None:
        return card
    return CardInstance(id=str(ctx.get("source_card") or "?"), owner=ctx["controller"], controller=ctx["controller"], zone="none")


def _self_parts(cost: AbilityCost) -> list[C.CostComponent]:
    return [c for c in cost.components if c.selector is None
            and c.kind in (C.SACRIFICE, C.EXILE, C.EXILE_FROM_GRAVEYARD, C.RETURN_PERMANENT, C.REMOVE_COUNTER, C.PUT_COUNTER)]


def problem(plan: Plan, ctx: Context, cost: AbilityCost, payer: str, chosen: dict[int, list[str]] | None = None,
            *, cost_has_x: bool | None = None) -> str | None:
    """Why ``payer`` can't pay ``cost`` in full right now, or None. With ``chosen`` (objects
    picked for the parts that need a choice) those picks are validated too."""
    from app.rules import (
        prohibitions,  # -- review 22B -- 614.17: Tamiyo / Sigarda: an opponent's "unless you sacrifice / discard" can't be taken
    )
    parts = {c.kind for c in cost.components}
    if parts & {C.SACRIFICE, C.DISCARD, C.DISCARD_HAND} and (why := (
            prohibitions.cant_cause_sacrifice(plan, payer, ctx["controller"]) if C.SACRIFICE in parts else None)
            or (prohibitions.cant_cause_discard(plan, payer, ctx["controller"]) if parts & {C.DISCARD, C.DISCARD_HAND} else None)):
        return f"{why}: {plan.name(payer)} can't be made to sacrifice or discard by it"
    was, plan.resolution_cost = plan.resolution_cost, True  # (a cost paid as it resolves: Angel of Jubilation doesn't reach it)
    excluded_before, plan.cost_attacker = plan.excluded, selectors.attacker_of(ctx.get("event"))  # (wave 110C: "other than that creature")
    if ctx.get('resolution_cost_exclusions'):
        plan.excluded = plan.excluded | _taken(plan, ctx, payer)
    try:
        return _problem(plan, ctx, cost, payer, chosen, cost_has_x=cost_has_x)
    finally:
        plan.resolution_cost = was
        plan.excluded, plan.cost_attacker = excluded_before, None


def _problem(plan: Plan, ctx: Context, cost: AbilityCost, payer: str, chosen: dict[int, list[str]] | None,
             *, cost_has_x: bool | None = None) -> str | None:
    from app.rules import casting  # casting imports cost_payment → (not this module)

    source = _source(plan, ctx)
    same = plan.oid(source) == ctx.get("source_object") if source.zone != "none" else False
    for comp in _self_parts(cost):
        if comp.kind == C.EXILE_FROM_GRAVEYARD:
            if not same or not source.zone.endswith(":graveyard"):
                return f"{source.name or 'it'} isn't in the graveyard"
        elif not same or not source.zone.endswith(":battlefield"):
            return f"{source.name or 'it'} isn't on the battlefield"  # (118.12: Standstill exiled in response)
        elif comp.kind == C.REMOVE_COUNTER and comp.counter != C.ANY_COUNTER and source.counters.get(comp.counter or "", 0) < comp.amount:
            return f"{source.name or 'It'} doesn't have {comp.amount} {comp.counter} counters"
    if cost.life and plan.state.players[payer].life < cost.life:  # 119.4
        return f"{plan.name(payer)} can't pay {cost.life} life"
    from app.rules import life_lock  # -- can't lose life (wave 29D) -- 119.8, 614.17b

    if (lock := life_lock.pay_problem(plan.state, plan.info, payer, cost.life)) is not None:
        return lock
    found = cost_payment.problem(plan, cost, source, payer)
    if found is not None:
        return found
    if chosen is not None:
        used: set[str] = set()
        for i, comp in cost.choices:
            if optional_counter55.component(comp):
                picks = chosen.get(i, [])
                if not optional_counter55.validate(plan, source, comp, picks, used):
                    return f"Those counters can't pay “{comp.text}”"
                used |= set(picks)
                continue
            if comp.kind in FLEXIBLE:  # -- if you do (wave 26C) -- forage / collect evidence: validated as a whole (701.61a, 701.59a)
                options, _ = cost_payment._flexible_options(plan, comp, source, payer, used)
                picks = chosen.get(i, [])
                if len(set(picks)) != len(picks) or any(c not in options for c in picks) or not cost_payment._flexible_ok(plan, comp, picks):
                    return f"Those can't pay “{comp.text}”"
                used |= set(picks)
                continue
            usable = [c for c in cost_payment.candidates(plan, comp, payer, source)
                      if c not in cost_payment._reserved(cost, comp, source) and c not in used]
            picks = chosen.get(i, [])
            right_count = len(picks) <= comp.amount if comp.kind == C.WATERBEND else len(picks) == comp.objects
            if not right_count or len(set(picks)) != len(picks) or any(c not in usable for c in picks):
                return f"Those can't pay “{comp.text}”"
            if comp.kind != C.PUT_COUNTER:
                used |= set(picks)
    if any(c.kind == C.WATERBEND for c in cost.components):
        from app.rules import waterbend_payments

        return waterbend_payments.problem(plan, payer, source, cost, chosen)
    if cost.mana:
        exclude = cost_payment.excluded(cost, source, chosen or {})
        if not casting.can_pay(plan.state, payer, M.parse_cost(cost.mana), plan.info, exclude=exclude,
                               purpose=casting.Purpose(selected_cost_has_x=cost_has_x)):
            from app.rules import reveal_mana

            if not reveal_mana.available(plan, payer, exclude):
                return f"{plan.name(payer)} can't pay {cost.mana}"
    return None


# -- the primitive ---------------------------------------------------------------------------------
def optional_payment(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """``{"do": "optional_payment", "who": <payer>, "cost": <cost text>, "bind": "pay0"}``: offer
    the payer the cost (PAY / DECLINE, privately) if they can pay it now; record the result as the
    binding ``bind`` (``{"succeeded": bind}`` in a following ``only_if``)."""
    # -- unless pays (wave 4C) -- a cost sized as it resolves ("{X}", "{1} for each …": app/rules/unless_pays.py)
    from app.rules import paid_x, unless_pays

    if paid_x.sized(e):  # -- sized payments (wave 5G) -- "you may pay {X}" / "pay X life, where X is …"
        started = paid_x.start(plan, ctx, e)
        if started is not True and started is not False:
            e = {**e, "cost": started}
        else:
            return bool(started)
    if e.get("alts"):  # -- if you do (wave 6F) -- one cost or the other
        return _offer_alternatives(plan, ctx, e)
    if e.get("ask"):  # -- optional payments by another player (wave 25D) -- "That player may create a tapped Zombie token.": nothing to pay, the
        # player the trigger event names chooses (608.2d), and "If they do" / the gated instructions read the answer like a payment's
        who = payer_of(plan, ctx, e.get("who", "you"))
        if who is None:
            context.bind_payment(ctx, str(e.get("bind") or "pay0"), False)
            return True
        decide(plan, player=who, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: {e['ask']}?",
               options=[DecisionOption(id=PAY, label="Yes"), DecisionOption(id=DECLINE, label="No")],
               resume={"step": STEP, "ctx": ctx, "opt": {"cost": "", "bind": str(e.get("bind") or "pay0"), "payer": who, "chosen": {}},
                       "cost": "{0}", "ask": True}, source=plan.state.cards.get(ctx.get("source_card") or ""))
        return False
    if (alt := e.get("alt")) and alt.get("hard"):  # -- unless pays (wave 51C) -- "If you control a creature with power 4 or greater, counter that spell instead." (Stubborn Denial): checked as it resolves (608.2c), nothing is offered when it holds
        from app.rules import conditions

        if conditions.holds(plan, ctx, alt["cond"]):
            context.bind_payment(ctx, str(e.get("bind") or "pay0"), False)
            return True
    text = unless_pays.concrete_cost(plan, ctx, e)
    cost = parse(text)
    # -- end unless pays (wave 4C) --
    name = str(e.get("bind") or "pay0")
    payer = payer_of(plan, ctx, e.get("who", "you"))
    from app.rules import effects

    if e.get("needs") and not effects._cards(plan, ctx, e["needs"]):  # -- exile as a cost (wave 49D) -- 118.3, 400.7: "pay … and exile it" with it gone (Timothar's ruling)
        plan.note(f"{plan.name(payer or ctx['controller'])} can't pay for {ctx.get('name') or 'it'}: the card is no longer where it went")
        context.bind_payment(ctx, name, False)
        return True
    if cost is None or payer is None:
        context.bind_payment(ctx, name, False)
        return True
    why = problem(plan, ctx, cost, payer, cost_has_x=e.get('cost_has_x'))
    from app.rules import manual_choice_mana85

    manual_mana = bool(cost.mana and all(c.kind == C.MANA for c in cost.components) and not cost.life
                       and manual_choice_mana85.available(plan, payer))
    if manual_mana:
        why = None  # Keep the native activation window open; never select sacrifice objects automatically.
    # -- copied abilities (wave 18F) -- imprint, "you may exile an instant card from your hand": a hand is hidden (101.4a), so whether the
    # choice is offered mustn't tell the other players whether there was a card to exile: the payer is asked either way, and a pay
    # that then finds no card is a decline that says nothing about the hand
    hidden = any(c.kind == "EXILE_FROM_HAND" for c in cost.components)
    if why is not None and not hidden:  # 118.3 / 608.2d: the option isn't offered
        plan.note(f"{plan.name(payer)} can't pay {_label(cost)} for {ctx.get('name') or 'it'}: {why}")
        context.bind_payment(ctx, name, False)
        return True
    source = plan.state.cards.get(ctx.get("source_card") or "")
    opt: dict[str, Any] = {"cost": text, "bind": name, "payer": payer, "chosen": {},
                           "cost_has_x": e.get('cost_has_x')}  # Preserve before numeric cost serialization.
    if e.get('link'):
        opt['link'] = True
    if e.get("needs"):
        opt["needs"] = e["needs"]  # (wave 49D)
    if e.get("defer"):  # -- review (wave 6R) -- paid with the other players' choices (pay_deferred)
        opt["defer"] = True
    hint = " (activate your mana abilities first)" if manual_mana else " (tap your mana first)" if cost.mana and _self_pays(plan, payer) else ""
    shown = re.sub(r"^pay ", "", _label(cost).replace("~", ctx.get("name") or "it"), flags=re.IGNORECASE)  # ("Have ~ deal 7 damage to you": the source by name; "Pay 3 life" once)
    ask = shown if shown.startswith("Have ") else f"Pay {shown}"
    hint += f" for {e['for110o']}" if e.get("for110o") else ""  # -- (wave 110O) -- Cleansing: which land the payment is for
    decide(plan, player=payer, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: {ask[0].lower()}{ask[1:]}?{hint}",
           options=[DecisionOption(id=PAY, label=ask), DecisionOption(id=str(e.get("decline_id") or DECLINE), label="Don't pay")],
           resume=_resume(ctx, opt, cost), source=source,
           display={"kind": "optional_cost", "cost": _label(cost), "pool": mana_units.visible_pool(plan.state, payer)} if cost.mana else None)
    return False


def _offer_alternatives(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """-- if you do (wave 6F) -- PAY one of ``alts`` (each offered only while payable in full, 118.3) or DECLINE."""
    name = str(e.get("bind") or "pay0")
    payer = payer_of(plan, ctx, e.get("who", "you"))
    was, plan.excluded = plan.excluded, _taken(plan, ctx, payer)
    try:
        payable = [(i, text, cost) for i, text in enumerate(e["alts"])
                   if (cost := parse(text)) is not None and payer is not None and problem(plan, ctx, cost, payer) is None]
    finally:
        plan.excluded = was
    if payer is None or not payable:
        if payer is not None:
            plan.note(f"{plan.name(payer)} can't pay {' or '.join(e['alts'])} for {ctx.get('name') or 'it'}")
        context.bind_payment(ctx, name, False)
        return True
    opt: dict[str, Any] = {"alts": list(e["alts"]), "bind": name, "payer": payer, "chosen": {}, "cost": payable[0][1]}
    if e.get("defer"):  # -- review (wave 6R) --
        opt["defer"] = True
    decide(plan, player=payer, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: pay {' or '.join(e['alts'])}?",
           options=[*(DecisionOption(id=f"{PAY}:{i}", label=f"Pay {_label(cost)}") for i, _, cost in payable),
                    DecisionOption(id=DECLINE, label="Don't pay")],
           resume=_resume(ctx, opt, payable[0][2]), source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def _label(cost: AbilityCost) -> str:
    # Repeated cumulative-upkeep costs need a bounded, readable label even
    # with many age counters. The payment itself retains every component.
    bending = [c.text for c in cost.components if c.kind == C.WATERBEND]
    if bending:
        return ", ".join(bending)
    texts = [c.text for c in cost.components]
    full = ", ".join(texts)
    if len(full) <= 190:
        return full
    return ", ".join(f"{text} ({texts.count(text)} times)" if texts.count(text) > 1 else text
                     for text in dict.fromkeys(texts))


def _self_pays(plan: Plan, payer: str) -> bool:
    from app.rules import casting

    return casting.payment_mode(plan, payer) == "self"


def _resume(ctx: Context, opt: dict[str, Any], cost: AbilityCost, **more: Any) -> dict[str, Any]:
    # "cost" (the mana part) is what casting._best_option reads to pick a color while tapping
    return {"step": STEP, "ctx": ctx, "opt": opt, "cost": cost.mana or "{0}", **more}


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    """PAY / DECLINE, or the objects chosen for one part of the cost."""
    from app.rules import effects

    r = d.resume
    assert r is not None
    if "choose_x" in r:  # -- sized payments (wave 5G) -- the X chosen
        from app.rules import paid_x

        paid_x.resume_choice(plan, d, chosen)
        return
    if "opt" not in r:  # a pay-or-sacrifice / counter-unless prompt (app/rules/effects.py)
        effects.resume_pay_or_sacrifice(plan, d, chosen)
        return
    ctx, opt = r["ctx"], r["opt"]
    if r.get("ask"):  # -- optional payments by another player (wave 25D) -- the yes / no of "that player may …"
        context.bind_payment(ctx, opt["bind"], chosen[0] == PAY)
        effects.continue_effects(plan, ctx)
        return
    cost = parse(opt["cost"])
    assert cost is not None
    if "component" in r:
        if not chosen and (r.get("hand") or r.get("counter_pick55")):  # (wave 18F: a card from a hand, chosen privately; none is a decline that says nothing of the hand)
            plan.note(f"{plan.name(d.player)} didn't pay {_label(cost)} for {ctx.get('name') or 'it'}")
            context.bind_payment(ctx, opt["bind"], False)
            effects.continue_effects(plan, ctx)
            return
        if r.get("flexible"):  # -- if you do (wave 26C) -- forage / collect evidence: the picks must pay the part as a whole
            comp = cost.components[r["component"]]
            options, _ = cost_payment._flexible_options(plan, comp, _source(plan, ctx), d.player, set())
            if len(set(chosen)) != len(chosen) or any(c not in options for c in chosen) or not cost_payment._flexible_ok(plan, comp, chosen):
                raise ActionError(f"Those cards don't pay “{comp.text}”")
        elif not r.get("waterbend") and len(chosen) != r["amount"]:
            raise ActionError(f"Choose {r['amount']}")
        opt = {**opt, "chosen": {**opt["chosen"], str(r["component"]): list(chosen)}}
    elif opt.get("alts") and chosen[0].startswith(f"{PAY}:"):  # -- if you do (wave 6F) -- the cost picked
        k = chosen[0].split(":", 1)[1]
        if not k.isdigit() or int(k) >= len(opt["alts"]):
            raise ActionError("Choose one of the offered costs")
        opt = {**opt, "cost": opt["alts"][int(k)], "alts": None}
        picked = parse(opt["cost"])
        assert picked is not None
        cost = picked
    elif chosen[0] != PAY:
        plan.note(f"{plan.name(d.player)} didn't pay {_label(cost)} for {ctx.get('name') or 'it'}")
        context.bind_payment(ctx, opt["bind"], False)
        effects.continue_effects(plan, ctx)
        return
    if _choose_next(plan, ctx, opt, cost):
        if opt.get("defer"):  # -- review (wave 6R) -- chosen now, paid with the others' (101.4)
            _defer(plan, ctx, opt, cost)
            effects.continue_effects(plan, ctx)
        else:
            _pay(plan, ctx, opt, cost)


# -- review (wave 6R) -- "Each opponent may sacrifice …" (app/rules/each_may.py): 101.4 — each player in turn order
# chooses whether to pay (and what with; 101.4b: the choices made before are known), then the actions happen
# simultaneously (Wizards ruling on Fandaniel, Telophoroi Ascian, 2025-06-06: "each of the chosen creatures are
# sacrificed simultaneously"). A choice is kept in the resolution context; ``pay_deferred`` pays them all, the
# sacrifices as one move (one event batch: a permanent sacrificed alongside another sees it go, 603.10a).
def defers(text: str | None, alts: list[str] | None = None) -> bool:
    """Whether a payment of this cost can wait for the other players' choices: anything but mana (the payer taps their
    mana while their own prompt is open)."""
    costs = [parse(t) for t in ([text] if text else []) + list(alts or [])]
    return bool(costs) and all(c is not None and not c.mana for c in costs)


def _taken(plan: Plan, ctx: Context, payer: str | None) -> frozenset[str]:
    """-- cost reductions paid with objects (wave 47C) -- what the payer's earlier choices of this resolution (chosen, not yet paid) already take: Rottenmouth Viper's "previously
    chosen can't be chosen again" (ruling 2024-07-26)."""
    reserved = {c for o in (ctx.get("deferred_pay") or {}).values() if o["payer"] == payer for ids in o["chosen"].values() for c in ids}
    # A printed cost can exclude an earlier named object rather than its own
    # ability source. Exact context references expire on a real zone change.
    for exclusion in ctx.get('resolution_cost_exclusions') or []:
        if exclusion['payer'] == payer:
            reserved.update(context.objects(plan, ctx, exclusion['who'].removeprefix(context.PREFIX)))
    return frozenset(reserved)


def _defer(plan: Plan, ctx: Context, opt: dict[str, Any], cost: AbilityCost) -> None:
    payer = opt["payer"]
    picked = [c for ids in opt["chosen"].values() for c in ids]
    public = [c for c in picked if (x := plan.state.cards.get(c)) is not None and x.zone.endswith(":battlefield")]
    # (a card chosen from a hand stays hidden until it is discarded: 101.4a)
    plan.note(f"{plan.name(payer)} chooses to pay {_label(cost)} for {ctx.get('name') or 'it'}",
              public if len(public) == len(picked) else [])
    ctx.setdefault("deferred_pay", {})[opt["bind"]] = {**opt, "defer": None}


def _sacrifice_only(cost: AbilityCost) -> bool:
    return (not cost.mana and not cost.life and not cost.remove_counters and not _self_parts(cost)
            and all(c.kind == C.SACRIFICE and c.selector is not None for c in cost.components))


@dataclass
class DeferredPayments:
    remaining: list[tuple[dict[str, Any], AbilityCost]]
    together: list[tuple[dict[str, Any], AbilityCost, list[str]]]


def pay_deferred(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Finish chosen payments before resuming; the final sacrifice batch remains simultaneous."""
    pending = ctx.pop("deferred_pay", None) or {}
    queued = [(opt, cost) for name in e["binds"] if (opt := pending.get(name)) is not None
              and (cost := parse(opt["cost"])) is not None]
    if queued and all(cost.components and all(c.kind == C.DISCARD and c.selector is not None for c in cost.components)
                      for _, cost in queued):
        from app.rules import grouped_discard

        grouped_discard.begin(plan, ctx, queued)
    else:
        _pay_deferred_remaining(plan, ctx, DeferredPayments(queued, []))
    return False  # The continuation owns the resolution, even when every payment was synchronous.


def _pay_deferred_remaining(plan: Plan, ctx: Context, after: DeferredPayments) -> None:
    from app.rules import effects
    from app.rules.triggers import sacrificing

    together = after.together
    for i, (opt, cost) in enumerate(after.remaining):
        if not _sacrifice_only(cost):
            _pay(plan, ctx, opt, cost, after=DeferredPayments(after.remaining[i + 1:], together))
            return
        name = opt["bind"]
        chosen = {int(k): list(v) for k, v in opt["chosen"].items()}
        why = problem(plan, ctx, cost, opt["payer"], chosen, cost_has_x=opt.get('cost_has_x'))
        if why is not None:
            plan.note(f"{plan.name(opt['payer'])} couldn't pay {_label(cost)} for {ctx.get('name') or 'it'}: {why}")
            context.bind_payment(ctx, name, False)
            continue
        together.append((opt, cost, [c for ids in chosen.values() for c in ids]))
    if not together:
        effects.continue_effects(plan, ctx)
        return
    gone = [c for _, _, ids in together for c in ids]
    refs = {opt["bind"]: [r for r in (context.ref_of(plan, c) for c in ids) if r is not None] for opt, _, ids in together}
    sacrificing(plan, gone)  # 701.21a: to their owners' graveyards, all at once
    plan.do({"type": "move", "card_ids": gone, "to": {"zone": "graveyard"}}, actor=ctx["controller"])
    for opt, cost, ids in together:
        plan.note(f"{plan.name(opt['payer'])} paid {_label(cost)} for {ctx.get('name') or 'it'}", [c for c in ids if c in plan.state.cards])
        context.bind_payment(ctx, opt["bind"], True, refs[opt["bind"]])
    effects.continue_effects(plan, ctx)


def _choose_next(plan: Plan, ctx: Context, opt: dict[str, Any], cost: AbilityCost) -> bool:
    """Ask the payer for the objects of the next part that needs a choice (privately: a discard's
    options are their hand); True when every part has its objects."""
    payer = opt["payer"]
    source = _source(plan, ctx)
    picked = {int(k): list(v) for k, v in opt["chosen"].items()}
    # CR 702.24a: each age counter has its own choice. A permanent can
    # receive counters repeatedly; it cannot be sacrificed/discarded twice.
    used = {c for i, ids in picked.items() if cost.components[i].kind != C.PUT_COUNTER for c in ids} | _taken(plan, ctx, payer)
    for i, comp in cost.choices:
        if i in picked:
            continue
        if optional_counter55.component(comp):
            counters = optional_counter55.choose(plan, ctx, opt, cost, i, comp, source, used)
            if counters is None:
                return False
            picked[i] = counters
            used |= set(counters)
            opt["chosen"][str(i)] = counters
            continue
        if comp.kind in FLEXIBLE:  # -- if you do (wave 26C) -- the payer picks the graveyard cards (or the Food) as a whole; none is a decline
            options, payable = cost_payment._flexible_options(plan, comp, source, payer, used)
            if not payable:
                return True  # (validated again in _pay: it can't be paid any more)
            decide(plan, player=payer, kind="choose_cards",
                   prompt=f"{ctx.get('name') or 'It'}: choose the cards for “{comp.text}”, or none to decline",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in options],
                   min_choices=0, max_choices=len(options) if comp.kind == C.COLLECT_EVIDENCE else 3,
                   resume=_resume(ctx, opt, cost, component=i, amount=None, hand=True, flexible=True),
                   source=plan.state.cards.get(ctx.get("source_card") or ""))
            return False
        was, plan.resolution_cost, plan.cost_attacker = plan.resolution_cost, True, selectors.attacker_of(ctx.get("event"))  # (review 22B)
        try:
            usable = [c for c in cost_payment.candidates(plan, comp, payer, source)
                      if c not in cost_payment._reserved(cost, comp, source) and c not in used]
        finally:
            plan.resolution_cost, plan.cost_attacker = was, None
        if comp.kind == C.WATERBEND:
            if not usable:
                opt["chosen"][str(i)] = []
                continue
            decide(plan, player=payer, kind="choose_cards",
                   prompt=f"{ctx.get('name') or 'It'}: tap up to {comp.amount} artifacts and creatures, each paying for {{1}} (none: mana only)",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in usable],
                   min_choices=0, max_choices=min(comp.amount, len(usable)),
                   resume=_resume(ctx, opt, cost, component=i, amount=None, waterbend=True),
                   source=plan.state.cards.get(ctx.get("source_card") or ""))
            return False
        hand = comp.kind == "EXILE_FROM_HAND"  # -- copied abilities (wave 18F) -- always asked, even with one card or none (101.4a): none = decline
        if len(usable) < comp.objects and not hand:  # (objects: one permanent for its counters, wave 6F)
            return True  # (validated again in _pay: it can't be paid any more)
        if len(usable) == comp.objects and not hand:
            picked[i] = usable
            if comp.kind != C.PUT_COUNTER:
                used |= set(usable)
            opt["chosen"][str(i)] = usable
            continue
        verb = cost_payment._VERBS.get(comp.kind, "use")
        decide(plan, player=payer, kind="choose_cards",
               prompt=f"{ctx.get('name') or 'It'}: choose {comp.objects} to {verb} (“{comp.text}”)",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in usable],
               min_choices=0 if hand else comp.objects, max_choices=comp.objects,
               resume=_resume(ctx, opt, cost, component=i, amount=comp.objects, hand=hand),
               source=plan.state.cards.get(ctx.get("source_card") or ""))
        return False
    return True


@dataclass
class OptionalPaymentFrame:
    ctx: Context
    opt: dict[str, Any]
    cost: AbilityCost
    source: CardInstance
    paid: list[str]
    refs: list[ObjectRef]
    after: DeferredPayments | None = None


def _payment_done(plan: Plan, ctx: Context, after: DeferredPayments | None) -> None:
    from app.rules import effects

    if after is not None:
        _pay_deferred_remaining(plan, ctx, after)
    else:
        effects.continue_effects(plan, ctx)


def _pay(plan: Plan, ctx: Context, opt: dict[str, Any], cost: AbilityCost, *, after: DeferredPayments | None = None) -> None:
    """Pay the whole cost at once (601.2h), or nothing: the payer chose to pay, but the table may
    have changed while they were asked (mana abilities), so everything is checked first."""
    from app.rules import casting

    payer: str = opt["payer"]
    name: str = opt["bind"]
    label = ctx.get("name") or "it"
    chosen = {int(k): list(v) for k, v in opt["chosen"].items()}
    from app.rules import effects

    why = problem(plan, ctx, cost, payer, chosen, cost_has_x=opt.get('cost_has_x'))
    if why is not None and cost.mana and all(c.kind == C.MANA for c in cost.components) and not cost.life:
        from app.rules import manual_choice_mana85

        if manual_choice_mana85.available(plan, payer):
            raise ActionError(f'Activate your mana abilities first: {cost.mana} is not payable yet')
    if why is None and opt.get("needs") and not effects._cards(plan, ctx, opt["needs"]):  # (wave 49D: it may have moved while the payer tapped mana)
        why = "the card is no longer where it went"
    if why is not None:
        hand = any(c.kind == "EXILE_FROM_HAND" for c in cost.components)  # (wave 18F: no reason given: it would describe a hidden hand)
        plan.note(f"{plan.name(payer)} " + (f"didn't pay {_label(cost)}" if hand else f"couldn't pay {_label(cost)}: {why}") + f" for {label}")
        context.bind_payment(ctx, name, False)
        _payment_done(plan, ctx, after)
        return
    source = _source(plan, ctx)
    from app.rules import waterbend_payments

    mana_cost = waterbend_payments.mana(cost, chosen) if cost.mana else None
    purpose = casting.Purpose(selected_cost_has_x=opt.get('cost_has_x'))
    if mana_cost is not None and _self_pays(plan, payer) and not casting.pool_covers(plan.state, payer, mana_cost, purpose=purpose, info=plan.info):
        raise ActionError(f"Tap your mana first: {mana_cost.text()} isn't in your mana pool")
    paid = ([source.id] if _self_parts(cost) else []) + [c for ids in chosen.values() for c in ids]
    refs = [r for r in (context.ref_of(plan, c) for c in dict.fromkeys(paid)) if r is not None]
    frame = OptionalPaymentFrame(ctx, opt, cost, source.model_copy(deep=True), paid, refs, after)
    from app.rules import payment_continuations as pc

    then = pc.continuation(plan, "optional_payment", frame)
    if mana_cost is not None:
        casting.pay_then(plan, payer, mana_cost, f"paid {opt.get('amount_label') or mana_cost.text()} for {label}", then=then,
                         sources=[] if _self_pays(plan, payer) else None,
                         purpose=purpose,
                         exclude=cost_payment.excluded(cost, source, chosen))
        return
    pc.finish(plan, then, None)


def _paid(plan: Plan, frame: OptionalPaymentFrame, payment: M.Payment | None) -> None:
    ctx, opt, cost, source = frame.ctx, frame.opt, frame.cost, frame.source
    payer, name = opt["payer"], opt["bind"]
    label = ctx.get("name") or "it"
    chosen = {int(k): list(v) for k, v in opt["chosen"].items()}
    paid, refs = frame.paid, frame.refs
    if cost.life:
        from app.rules import replace as _replace_life  # (wave 28B: 119.4)
        _replace_life.lose_life(plan, [(payer, cost.life)], actor=payer, paid=True)
    for kind, n in cost.remove_counters:
        from app.rules import counter_removal_results

        if counter_removal_results.remove(plan, source.id, kind, n, by=payer) != n:
            raise ActionError("The source counters can no longer pay this cost")
    record = PaymentRecord(card=source.id, controller=payer, total_cost=opt.get("amount_label") or _label(cost))
    actor, plan.actor = plan.actor, payer  # -- if you do (wave 6F) -- the parts cost_payment pays as "the actor" are the payer's
    try:
        cost_payment.pay(plan, cost, source, chosen, record)
    finally:
        plan.actor = actor
    # -- unless damage (wave 27A) -- the source deals the damage to the payer (120.3) as the next instruction (review 27A: a damage
    # instruction of its own, so the payer's 616.1 choices among replacement / prevention effects can pause it)
    hurt = [{"do": "damage", "who": f"player:{payer}", "n": comp.amount} for comp in cost.components if comp.kind == "SOURCE_DAMAGE"]
    if opt.get("needs"):  # -- exile as a cost (wave 49D) -- "… and exile it": the other half of the cost, done the moment the rest is paid
        hurt.append({"do": "exile", "who": opt["needs"], "as": f"{name}x"})
    if hurt:
        at = int(ctx.get("next") or 0)
        ctx["effects"] = [*ctx["effects"][:at], *hurt, *ctx["effects"][at:]]
    for i, comp in enumerate(cost.components):  # -- if you do (wave 15C) -- shown to everyone, and it stays in the hand
        if comp.kind == REVEAL_FROM_HAND and chosen.get(i):
            plan.do({"type": "reveal", "card_ids": chosen[i]}, actor=payer)
    for i, comp in enumerate(cost.components):  # -- if you do (wave 6F) -- to the bottom of the payer's library
        if comp.kind == HAND_TO_BOTTOM and chosen.get(i):  # (-- review 30 -- at once, one move: 401.4)
            plan.do({"type": "move", "card_ids": list(chosen[i]), "to": {"player": payer, "zone": "library"}, "position": "bottom"},
                    actor=payer)
    if any(c.kind == C.DISCARD_HAND for c in cost.components):  # -- if you do (wave 6F) -- "draw that many cards"
        ctx.setdefault("paid_x", {})[name] = len(record.discarded)
    if any((c.kind in (C.EXILE, 'EXILE_FROM_HAND') or opt.get('link') and c.kind == C.EXILE_FROM_GRAVEYARD)
           and c.selector is not None for c in cost.components):  # -- champion (wave 12B) -- 607.2a (wave 18F: imprint)
        from app.rules import exiled_with

        exiled_with.record(plan, ctx, [c for c in paid if c != source.id])
    if not (cost.mana and all(c.kind == C.MANA for c in cost.components) and not cost.life and not cost.remove_counters):
        # (a cost of mana alone was logged as it was paid: "Alice paid {1}{U/R} for Mizzix, Replica Rider", once)
        plan.note(f"{plan.name(payer)} paid {opt.get('amount_label') or _label(cost)} for {label}", [c for c in paid if c in plan.state.cards])
    context.bind_payment(ctx, name, True, refs, context.moved_objects(plan, refs))  # (moved: wave 8C)

    _payment_done(plan, ctx, frame.after)


from app.rules import payment_continuations as _payment_continuations  # noqa: E402, I001

_payment_continuations.register("optional_payment", OptionalPaymentFrame, _paid)
