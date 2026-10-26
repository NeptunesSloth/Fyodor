"""-- wave 110I -- exact Oracle wordings of single cards, read as a wording the grammar already reads (``_AS``) or built from parts of it.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
Researched against the Comprehensive Rules of 2026-09-25.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
Def = dict[str, Any]


def _won_last(d: Def) -> Def:
    """701.30d: the last instruction (the token's haste) happens only if you won the clash the trigger is about."""
    *head, last = d["effects"]
    return {**d, "effects": [*head, {"do": "only_if", "cond": {"clash_won100a": True}, "skip": 1}, last]}


# whole ability text -> the wording the grammar reads for it
_AS: dict[str, str] = {
    # Corrosion: "Artifacts destroyed this way" are the ones the destroy-each instruction destroyed ("They", 701.8c: can't be regenerated)
    "At the beginning of your upkeep, put a rust counter on each artifact target opponent controls. Then destroy each artifact with mana value less than "
    "or equal to the number of rust counters on it. Artifacts destroyed this way can't be regenerated.":
        "At the beginning of your upkeep, put a rust counter on each artifact target opponent controls. Then destroy each artifact with mana value less "
    "than or equal to the number of rust counters on it. They can't be regenerated.",
    # Dermoplasm: a card put onto the battlefield from the hand is face up anyway (708.2: only a face-down instruction makes it face down)
    "When this creature is turned face up, you may put a creature card with a morph ability from your hand onto the battlefield face up. If you do, return this creature to its owner's hand.":
        "When this creature is turned face up, you may put a creature card with a morph ability from your hand onto the battlefield. If you do, return this creature to its owner's hand.",
}


def _until_leaves(d: Def) -> Def:
    """The Moment: "It phases out until ~ leaves the battlefield" (610.3, 702.26a): the Oubliette lifetime packet, without its tap."""
    return {**d, "effects": [{"do": "phase_until_target110c", "untapped110i": True} if x.get("do") == "phase_out" else x for x in d["effects"]]}


def _pandorica(d: Def) -> Def:
    """The Pandorica: it can't phase in for as long as the source remains tapped, and phases in when it untaps or leaves (610.3, 702.26d)."""
    return {**d, "effects": [{"do": "phase_until_target110c", "untapped110i": True, "tapped110i": True} if x.get("do") == "phase_out" else x for x in d["effects"]]}


def _copy_cast(d: Def) -> Def:
    """Bloodthirsty Adversary: the exiled cards are copied and any number of the copies may be cast without paying (707.12, 608.2g), one at a time."""
    inner = next(e for e in d["effects"] if e.get("do") == "reflexive")["ability"]["effects"]
    at = next(i for i, e in enumerate(inner) if e.get("do") == "exile")
    inner[at] = {**inner[at], "as": "ex110i"}
    inner += [{"do": "copy_cards", "who": "ref:ex110i", "as": "cp110i"},
              {"do": "free_cast", "zone": "that", "who": "ref:cp110i", "filter": None, "optional": True, "mv": None, "all": True}]
    return d


def _lose_types(d: Def) -> Def:
    """Curse of Conformity: "lose all creature types" sets the creature types to none (205.1a, 613.1d layer 4), beside the layer 7b base P/T."""
    return {**d, "layered": True, "layer4": {"set_creature_types": []}}


def _bounce_gate(d: Def) -> Def:
    """Puppet Master: the payment is offered only if that card was returned to its owner's hand this way (a token or a card exiled instead isn't)."""
    first, *rest = d["effects"]
    return {**d, "effects": [{**first, "do": "bounce_gate110i", "skip": len(rest)}, *rest]}


def _attach_all(d: Def) -> Def:
    return {**d, "effects": [{"do": "attach_all110i"}]}


def _prevent_paid(d: Def) -> Def:
    """Errant Minion / Power Leak: the host's controller pays any amount of mana (118.3), then a prevention shield for that much (615.7) is made on
    them just before the Aura deals its 2, so damage-changing replacements (616.1) and the shield combine as the rules say."""
    (hit,) = d["effects"]
    pay = {"do": "optional_payment", "who": "event_player", "cost": "", "bind": "leak110i", "choose_x": {"max": None}}
    return {**d, "effects": [pay, {"do": "prevent", "who": "event_player", "n": {"paid_x": "leak110i"}}, hit]}


_INFINITE = ("Whenever enchanted creature blocks or becomes blocked by a creature with toughness 3 or less, destroy the other creature at end of combat. "
             "At the beginning of the next end step, if that creature was destroyed this way, put a +1/+1 counter on the first creature.")


def _destroy_mark(d: Def) -> Def:
    """Infinite Authority: remember the enchanted creature as the trigger resolves, and make the end-of-combat destroy schedule the counter."""
    effects = d["effects"]
    at = next(i for i, e in enumerate(effects) if e.get("do") == "deferred:destroy")
    effects[at] = {**effects[at], "do": "deferred:destroy_mark110i"}
    return {**d, "effects": [{"do": "bind_first110i"}, *effects]}


def _batch(d: Def) -> Def:
    """Bioessence Hydra: "one or more ... planeswalkers" is one trigger per batch of counter placements (603.2c) with their summed amount, not one per
    planeswalker (a replacement like Hardened Scales would add to each separate trigger's counters)."""
    return {**d, "cond": {**d["cond"], "aggregate": True}}


def _mirror(d: Def) -> Def:
    """Mirror of Fate: the up to seven face-up exiled cards are chosen as it resolves, not targeted (608.2d, 115.1), then the library is exiled
    (face up, 406.3) and the chosen cards go on top (401.4: their owner orders them)."""
    from app.rules import selectors

    key = selectors.parse("face-up card you own in exile").key()  # type: ignore[union-attr]
    pick = {"do": "player_chooses", "who": "you", "sel": key, "n": 7, "label": "exiled card", "zone": "exile", "upto": True, "optional": True, "as": "mof"}
    return {**d, "targets": [], "effects": [pick, {"do": "exile_library110i"}, {"do": "to_library", "who": "ref:mof", "place": "top"}]}


def _target_hand(d: Def) -> Def:
    """Nezumi Shortfang: "that player" of the later "if" is the one target opponent (608.2c), not any opponent."""
    return {**d, "effects": [{**e, "cond": {**e["cond"], "as": "target"}} if e.get("do") == "only_if" else e for e in d["effects"]]}


def _goad_while_saga(d: Def) -> Def:
    """The War Games: the tokens each player created are goaded (by the Saga's controller, 701.15a) for as long as the Saga remains on the battlefield
    (611.2b: a layer-6 effect that ends when it leaves)."""
    first, *rest = d["effects"]
    return {**d, "effects": [{**first, "as": "games110i"}, *rest, {"do": "goad_while110i", "who": "ref:games110i"}]}


_POWER_LEAK = "At the beginning of the upkeep of enchanted {0}'s controller, that player may pay any amount of mana. This Aura deals 2 damage to that player. Prevent X of that damage, where X is the amount of mana that player paid this way."

# whole ability text -> (the wording the grammar reads, what to change in its definition)
def _fasting(d: Def) -> Def:
    """Fasting: 614.10a an optional skip of the draw step; the player is asked as the step would begin (``ask_skip``)."""
    return {**d, "static": "skip_may110i", "life": 2}


def _total_sacrificed(d: Def) -> Def:
    """Smelting Vat: "total mana value less than or equal to the sacrificed artifact's mana value" caps the picked cards (608.2d), read from the cost."""
    return {**d, "effects": [{**x, "total_mv": {"mana_value": "cost:sacrificed"}} if x.get("do") == "pick_looked" else x for x in d["effects"]]}


def _bauble(d: Def) -> Def:
    """Lodestone Bauble: the targets are basic lands in any one graveyard (115.1d-style "a player's graveyard": one player), and "that player" is their owner."""
    import json

    t = d["targets"][0]
    sel = json.loads(t["what"][4:])
    sel.pop("zone_owner", None)
    t = {**t, "what": "sel:" + json.dumps(sel, separators=(",", ":"), sort_keys=True), "same_controller": True}
    return {**d, "targets": [t], "effects": [{"do": "bauble110i", "who": "target:0"}, d["effects"][0]]}


def _stardew(d: Def) -> Def:
    """Stardew Valley: the player chosen on resolution (not a target) is asked whether to gain control of the permanent (608.2d: "may" is theirs)."""
    return {**d, "effects": [{"do": "each_may", "who": e["to"], "act": [{"do": "gain_control", "who": "target", "to": "you"}], "text": "gain control of that permanent"}
                             if e.get("do") == "gain_control" else e for e in d["effects"]]}


def _fountain(d: Def) -> Def:
    """Quicksilver Fountain: the player whose upkeep it is chooses the land they control (603.3d, ``event_player``), like upkeep_target_choice65."""
    from app.rules import selectors

    sel = selectors.parse("non-Island land that player controls")
    assert sel is not None
    return {**d, "target": {"what": sel.key()}, "target_choice": "event_player"}


def _arcee(d: Def) -> Def:
    """Arcee: "that many" = the spell's targets that are creatures or Vehicles you control (115.9b: as they are when the trigger checks), counted by ``cast_targets``."""
    return {**d, "effects": [{**x, "n": {"cast_targets110i": d["cond"]["targets"]}} if x.get("do") == "add_counters" else x for x in d["effects"]]}


def bind_self(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"This card" after its own exile cost (400.7: a new object): bind the source as it is now, so a later "return this card" finds it in exile."""
    from app.rules import context

    if ctx.get("source_card") in plan.state.cards:
        context.bind_objects(plan, ctx, e["as"], [ctx["source_card"]])
    return True


def cast_targets(plan: Plan, ctx: Context, key: str) -> int:
    """The number of the cast event's targets that match the selector now (115.9b), for "put that many counters"."""
    from app.rules import selectors

    sel = selectors.from_key(key)
    you = ctx.get("controller") or ""
    n = 0
    for ref in (ctx.get("event") or {}).get("cast_targets") or []:
        card = plan.state.cards.get(ref.get("card", ""))
        if card is not None and plan.oid(card) == ref.get("object_id") and selectors.matches(plan, sel, card, plan.ch(card), you, ctx.get("source_card") or ""):
            n += 1
    return n


def _evershrike(d: Def) -> Def:
    """Evershrike: the Aura enters attached to the returned card (303.4f); "If you don't" (no Aura chosen, or none could legally enchant it, 303.4i) exiles it (118.12)."""
    back, put = d["effects"]
    return {**d, "effects": [{**back, "as": "ever110i"}, {**put, "host": "ref:ever110i", "did": "aura110i"},
                             {"do": "only_if", "cond": {"succeeded": "aura110i", "negate": True}, "skip": 1}, {"do": "exile", "who": "ref:ever110i"}]}


def _specter(d: Def) -> Def:
    """Tainted Specter: "discards a card unless they put a card from their hand on top of their library" is the target player's choice (``specter``); the damage
    is only for a discard (118.12 style "unless": what they chose, here the discard itself)."""
    discard, *damage = d["effects"]
    return {**d, "effects": [{"do": "specter110i", "who": discard["who"]}, {"do": "only_if", "cond": {"succeeded": "disc110i"}, "skip": len(damage)}, *damage]}


def specter(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    who = [p for p in effects._players(plan, ctx, e["who"]) if p in plan.live()]
    if not who or not plan.state.zones.get(f"{who[0]}:hand"):
        return True  # no player or nothing to put or discard: neither happens
    decide(plan, player=who[0], kind="choose_one", prompt="Put a card from your hand on top of your library, or discard a card?",
           options=[DecisionOption(id="top", label="Put a card from my hand on top of my library"), DecisionOption(id="discard", label="Discard a card")],
           resume={"step": "specter110i", "ctx": ctx, "pid": who[0]})
    return False


def resume_specter(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    ctx, pid = d.resume["ctx"], d.resume["pid"]
    if chosen == ["top"]:
        hand = list(plan.state.zones.get(f"{pid}:hand", []))
        decide(plan, player=pid, kind="choose_cards", prompt="Put a card from your hand on top of your library", min_choices=1, max_choices=1,
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand], resume={"step": "specter_top110i", "ctx": ctx})
    elif effects.PRIMITIVES["discard"](plan, ctx, {"do": "discard", "who": f"player:{pid}", "n": 1, "did": "disc110i"}):
        effects.continue_effects(plan, ctx)


def resume_specter_top(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    plan.do({"type": "move", "card_ids": chosen, "to": {"player": d.player, "zone": "library"}, "position": "top"}, actor=d.player)
    effects.continue_effects(plan, d.resume["ctx"])


def _raiding(d: Def) -> Def:
    """Raiding Party: the whole effect is one primitive (``raiding``): each player's tap choice, then their Plains choice, then the destruction."""
    return {**d, "effects": [{"do": "raiding110i"}]}


def raiding(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Raiding Party: in turn order (101.4) each player may tap any number of their untapped white creatures and, for each, chooses up to two Plains; then every
    Plains no player chose is destroyed (701.8) at once. The players choose knowing the earlier choices (all public)."""
    return _raiding_next(plan, ctx, [p for p in plan.apnap() if p in plan.live()], [])


def _raiding_next(plan: Plan, ctx: Context, players: list[str], chosen: list[str]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    for i, pid in enumerate(players):
        whites = [c for c in plan.state.zones.get(f"{pid}:battlefield", []) if not plan.state.cards[c].tapped and "W" in plan.ch(plan.state.cards[c]).colors
                  and plan.ch(plan.state.cards[c]).is_creature]
        if whites:
            decide(plan, player=pid, kind="choose_cards", prompt="Tap any number of untapped white creatures you control", min_choices=0, max_choices=len(whites),
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in whites],
                   resume={"step": "raiding_tap110i", "ctx": ctx, "rest": players[i + 1:], "chosen": chosen, "pid": pid})
            return False
    from app.rules import context, effects

    plains = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and "Plains" in plan.ch(c).subtypes and c.id not in chosen]
    context.bind_objects(plan, ctx, "plains110i", plains)
    effects.PRIMITIVES["destroy"](plan, ctx, {"do": "destroy", "who": "ref:plains110i"})
    return True


def resume_raiding_tap(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    r = d.resume
    ctx = r["ctx"]
    if chosen:
        plan.do({"type": "tap", "card_ids": chosen, "tapped": True}, actor=r["pid"])
        plains = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and "Plains" in plan.ch(c).subtypes]
        if plains:
            decide(plan, player=r["pid"], kind="choose_cards", prompt=f"Choose up to {2 * len(chosen)} Plains", min_choices=0, max_choices=min(2 * len(chosen), len(plains)),
                   options=[DecisionOption(id=c, label=f"{plan.state.cards[c].name} ({plan.name(plan.state.cards[c].controller)})", card_id=c) for c in plains],
                   resume={"step": "raiding_plains110i", "ctx": ctx, "rest": r["rest"], "chosen": r["chosen"], "pid": r["pid"]})
            return
    if _raiding_next(plan, ctx, r["rest"], r["chosen"]):
        effects.continue_effects(plan, ctx)


def resume_raiding_plains(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    if _raiding_next(plan, r["ctx"], r["rest"], [*r["chosen"], *chosen]):
        effects.continue_effects(plan, r["ctx"])


def _shifty(d: Def) -> Def:
    """Shifty Doppelganger: the sacrifice is bound ("did", 118.12); only if that creature left does this card return from exile (a new object, 400.7)."""
    es = [{**x, "did": "sac110i"} if x.get("do") == "deferred:sacrifice" else {**x, "n": 3} if x.get("do") == "delayed" else {**x, "skip": x["skip"] + 2} if x.get("do") == "only_if" else x for x in d["effects"]]
    return {**d, "effects": [{"do": "bind_self110i", "as": "self110i"}, *es, {"do": "deferred:only_if", "cond": {"succeeded": "sac110i"}, "skip": 1},
                             {"do": "deferred:return_card", "to": "battlefield", "tapped": False, "under": "you", "who": "ref:self110i"}]}


def _warp_strike(d: Def) -> Def:
    """Noctis: returns at the beginning of the owner's next declare attackers step (507.1, 603.7), tapped and attacking (508.4), unblockable that combat."""
    out: list[Def] = []
    for x in d["effects"]:
        if x.get("do") == "delayed":
            x = {**x, "when": {**x["when"], "step": "declare_attackers"}, "n": 2}
        elif x.get("do") == "deferred:return_card":
            x = {**x, "tapped": True, "attacking": True, "as": "warp110i", "owner110i": True}
        out.append(x)
    return {**d, "effects": [*out, {"do": "deferred:restrict", "who": "ref:warp110i", "rules": ["cant_be_blocked"], "duration": "end_of_combat"}]}


CU_UNPAID = "unpaid_cu110i"
_CU_SPENT = {"cu_spent110i": "BR"}


def _fallen(d: Def) -> Def:
    """Balduvian Fallen: starts when its cumulative upkeep was paid (702.24a); the {B} and {R} spent on that payment size the pump (filled in by ``cu_fill``)."""
    return {**d, "trigger": "paid_cu110j", "effects": [{**x, "p": _CU_SPENT} if x.get("do") == "pump" else x for x in d["effects"]]}


def _heart(d: Def) -> Def:
    """Heart of Bogardan: starts when a player doesn't pay the cumulative upkeep (702.24a), with the age counters it had just then (``cu_fill``)."""
    return {**d, "trigger": CU_UNPAID}


def cu_fill(plan: Plan, ctx: Context, d: Def) -> Def:
    """Replace the age counters / spent mana markers of a cumulative upkeep follow-up trigger by the numbers the payment (or its refusal) fixed."""
    src = plan.state.cards.get(ctx.get("source_card", ""))
    age = src.counters.get("age", 0) if src is not None else 0
    spent = ctx.get("cu_spent110i") or {}

    def walk(x: Any) -> Any:
        if isinstance(x, dict):
            if "cu_spent110i" in x and len(x) == 1:
                return sum(spent.get(c, 0) for c in x["cu_spent110i"])
            if x == {"counters": "age", "on": "self"}:
                return age
            return {k: walk(v) for k, v in x.items()}
        return [walk(v) for v in x] if isinstance(x, list) else x

    return walk(d)


def cu_unpaid(plan: Plan, ctx: Context, card_id: str) -> None:
    """The cumulative upkeep wasn't paid: "When a player doesn't pay" abilities trigger (603.2), before the permanent is sacrificed (702.24a)."""
    from app.rules import triggers

    for card, ch, i, d in triggers._watchers(plan, CU_UNPAID):
        if card.id == card_id:
            triggers._add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=i, definition=cu_fill(plan, ctx, d))


def cu_paid_then(plan: Plan, then: dict[str, Any]) -> None:
    """Pay branch of a cumulative upkeep: keep the mana spent for the "is paid" triggers, then go on."""
    from app.rules import effects

    ctx = then["ctx"]
    ctx["cu_spent110i"] = (then.get("payment") or {}).get("spent") or {}
    effects.continue_effects(plan, ctx)


_WARP = ("Warp-Strike \u2014 {3}: Exile Noctis. Return it to the battlefield under its owner's control tapped and attacking at the beginning of that player's next declare "
         "attackers step. It can't be blocked that combat.")
_BAUBLE = ("{1}, {T}, Sacrifice this artifact: Put up to four target basic land cards from a player's graveyard on top of their library in any order. "
           "That player draws a card at the beginning of the next turn's upkeep.")
_VAT = ("{1}, {T}, Sacrifice another artifact: Reveal the top eight cards of your library. Put up to two noncreature artifact cards with total mana value "
        "less than or equal to the sacrificed artifact's mana value from among them onto the battlefield and the rest on the bottom of your library in a random order.")
def _reflect(d: Def) -> Def:
    """Reflecting Mirror: any spell with a single target may be targeted; only as the ability resolves is it checked that the target is you (ruling 2004-10-04)."""
    return {**d, "effects": [{**e, "you110i": True} for e in d["effects"]]}


_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    "{X}, {T}: Change the target of target spell with a single target if that target is you. The new target must be a player. X is twice the mana value of that spell.":
        ("{X}, {T}: Change the target of target spell with a single target. The new target must be a player.", _reflect),
    "{1}{B}{B}, {T}: Target player discards a card unless they put a card from their hand on top of their library. If that player discards a card this way, "
    "this creature deals 1 damage to each creature and each player. Activate only as a sorcery.":
        ("{1}{B}{B}, {T}: Target player discards a card. This creature deals 1 damage to each creature and each player. Activate only as a sorcery.", _specter),
    "Sacrifice an Orc: Each player may tap any number of untapped white creatures they control. For each creature tapped this way, that player chooses up to two Plains. "
    "Then destroy all Plains that weren't chosen this way by any player.": ("Sacrifice an Orc: Destroy all Plains.", _raiding),
    "{X}{W/B}{W/B}: Return this card from your graveyard to the battlefield. You may put an Aura card with mana value X or less from your hand onto the battlefield "
    "attached to it. If you don't, exile this creature.":
        ("{X}{W/B}{W/B}: Return this card from your graveyard to the battlefield. You may put an Aura card with mana value X or less from your hand onto the battlefield.", _evershrike),
    "{3}{U}, Exile this creature: You may put a creature card from your hand onto the battlefield. If you do, that creature gains haste until end of turn. "
    "At the beginning of the next end step, sacrifice that creature. If you do, return this card to the battlefield.":
        ("{3}{U}, Exile this creature: You may put a creature card from your hand onto the battlefield. If you do, that creature gains haste until end of turn. "
         "At the beginning of the next end step, sacrifice that creature.", _shifty),
    "Whenever you cast a spell that targets one or more creatures or Vehicles you control, put that many +1/+1 counters on Arcee. Convert Arcee.":
        ("Whenever you cast a spell that targets one or more creatures or Vehicles you control, put a +1/+1 counter on Arcee. Convert Arcee.", _arcee),
    "Whenever this creature's cumulative upkeep is paid, it gets +1/+0 until end of turn for each {B} or {R} spent this way.":
        ("At the beginning of your upkeep, this creature gets +1/+0 until end of turn.", _fallen),
    "When a player doesn't pay this enchantment's cumulative upkeep, this enchantment deals X damage to target player or planeswalker and each creature that player or "
    "that planeswalker's controller controls, where X is twice the number of age counters on this enchantment minus 2.":
        ("At the beginning of your upkeep, this enchantment deals X damage to target player or planeswalker and each creature that player or "
         "that planeswalker's controller controls, where X is twice the number of age counters on this enchantment minus 2.", _heart),
    _WARP: ("Warp-Strike \u2014 {3}: Exile Noctis. Return it to the battlefield under its owner's control at the beginning of that player's next end step.", _warp_strike),
    "{3}, {T}: Choose target permanent you control. Draw a card, then another player of your choice may gain control of that permanent. Activate only as a sorcery.":
        ("{3}, {T}: Choose target permanent you control. Draw a card. Choose an opponent. That player gains control of that permanent. Activate only as a sorcery.", _stardew),
    "At the beginning of each player's upkeep, that player puts a flood counter on target non-Island land they control of their choice. "
    "That land is an Island for as long as it has a flood counter on it.":
        ("At the beginning of each player's upkeep, put a flood counter on target non-Island land. "
         "That land becomes an Island for as long as it has a flood counter on it.", _fountain),
    "At the beginning of each end step, if all lands on the battlefield are Islands, remove all flood counters from them.":
        ("At the beginning of each end step, if there are no non-Island lands on the battlefield, remove all flood counters from all lands.", lambda d: d),
    _BAUBLE: ("{1}, {T}, Sacrifice this artifact: Put up to four target basic land cards from your graveyard on top of your library in any order.", _bauble),
    _VAT: (_VAT.replace(" with total mana value less than or equal to the sacrificed artifact's mana value", ""), _total_sacrificed),
    "If you would begin your draw step, you may skip that step instead. If you do, you gain 2 life.": ("Skip your draw step.", _fasting),
    "When this creature enters, you may pay {2}{R} any number of times. When you pay this cost one or more times, put that many +1/+1 counters on this creature, "
    "then exile up to that many target instant and/or sorcery cards with mana value 3 or less from your graveyard and copy them. "
    "You may cast any number of the copies without paying their mana costs.":
        ("When this creature enters, you may pay {2}{R} any number of times. When you pay this cost one or more times, put that many +1/+1 counters on this creature, "
         "then exile up to that many target instant and/or sorcery cards with mana value 3 or less from your graveyard.", _copy_cast),
    "{1}{W}, {T}: Untap another target nonland permanent, then it phases out. It can't phase in for as long as The Pandorica remains tapped. "
    "When The Pandorica becomes untapped or leaves the battlefield, that permanent phases in. Activate only as a sorcery.":
        ("{1}{W}, {T}: Untap another target nonland permanent, then it phases out. Activate only as a sorcery.", _pandorica),
    _INFINITE: ("Whenever enchanted creature blocks or becomes blocked by a creature with toughness 3 or less, destroy the other creature at end of combat.", _destroy_mark),
    "{T}, Sacrifice this artifact: Choose up to seven face-up exiled cards you own. Exile all the cards from your library, then put the chosen cards on top of your library.":
        ("{T}, Sacrifice this artifact: Put up to seven target cards you own from exile on top of your library.", _mirror),
    "Whenever one or more loyalty counters are put on planeswalkers you control, put that many +1/+1 counters on this creature.":
        ("Whenever one or more loyalty counters are put on a planeswalker you control, put that many +1/+1 counters on this creature.", _batch),
    **{_POWER_LEAK.format(k): (f"At the beginning of the upkeep of enchanted {k}'s controller, this Aura deals 2 damage to that player.", _prevent_paid)
       for k in ("creature", "enchantment")},
    "{1}{B}, {T}: Target opponent discards a card. Then if that player has no cards in hand, flip this creature.":
        ("{1}{B}, {T}: Target opponent discards a card. Then if an opponent has no cards in hand, flip this creature.", _target_hand),
    "At the beginning of each opponent's upkeep, that player loses 1 life for each card fewer than three in their hand.":
        ("At the beginning of each opponent's upkeep, that player loses X life, where X is 3 minus the number of cards in their hand.", lambda d: d),
    "I \u2014 Each player creates three tapped 1/1 white Warrior creature tokens. The tokens are goaded for as long as this Saga remains on the battlefield.":
        ("I \u2014 Each player creates three tapped 1/1 white Warrior creature tokens.", _goad_while_saga),
    "Whenever an equipped creature you control other than Rhuk attacks or dies, you may attach all Equipment attached to that creature to Rhuk.":
        ("Whenever an equipped creature you control other than ~ attacks or dies, you may draw a card.", _attach_all),
    "When enchanted creature dies, return that card to its owner's hand. If that card is returned to its owner's hand this way, you may pay {U}{U}{U}. If you do, return this card to its owner's hand.":
        ("When enchanted creature dies, return that card to its owner's hand. You may pay {U}{U}{U}. If you do, return this card to its owner's hand.", _bounce_gate),
    "Nonlegendary creatures enchanted player controls have base power and toughness 3/3 and lose all creature types.":
        ("Nonlegendary creatures enchanted player controls have base power and toughness 3/3.", _lose_types),
    "{2}, {T}: Untap target creature you control. It phases out until The Moment leaves the battlefield.":
        ("{2}, {T}: Untap target creature you control. It phases out.", _until_leaves),
    "Whenever you clash, you may pay {1}. If you do, create a 3/1 red Elemental Shaman creature token. If you won, that token gains haste until end of turn.":
        ("Whenever you clash, you may pay {1}. If you do, create a 3/1 red Elemental Shaman creature token. That token gains haste until end of turn.", _won_last),
}


# a spell / mode body -> the wording the grammar reads for it
REWRITES: dict[str, str] = {}

# Survivor's Med Kit (RadAway): "loses all rad counters" is removing every rad counter the player has (122.1i, 728). The grammar's
# "Remove all rad counters from target player" only reads permanents' counters, so its first instruction is swapped for ``lose_rad110i``.
_RADAWAY = "Target player loses all rad counters. Sacrifice ~."


_DREDGING = "Return up to three target creature cards of the creature type of your choice from your graveyard to your hand."


def parse(body: str) -> Any:
    from app.rules import scripts

    if body.strip() == _RADAWAY:
        parsed = scripts.parse_effects("Target player gets 1 rad counters. Sacrifice ~.")
        assert parsed is not None
        effects, target, optional = parsed
        return [{"do": "lose_rad110i", "who": "target"}, *effects[1:]], target, optional
    if body.strip() == _DREDGING:
        # 601.2c: the creature type is chosen as the spell is cast; up to three targets that all have it = targets that share a creature type
        # (targets.relation_ok ``shares``, each with at least one type: ``typed110i``)
        parsed = scripts.parse_effects("Return up to three target creature cards from your graveyard to your hand.")
        assert parsed is not None
        effects, targets, optional = parsed
        return effects, [{**targets[0], "shares": "creature_type", "typed110i": True}], optional
    if body.strip() == _DAWN:
        return [{"do": "false_dawn110i"}], None, False
    return scripts.parse_effects(same) if (same := REWRITES.get(body.strip())) is not None else None


def lose_rad(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    for pid in effects._players(plan, ctx, e["who"]):
        if (have := plan.state.players[pid].resources.get("rad", 0)) > 0:
            plan.do({"type": "resource", "player": pid, "key": "rad", "delta": -have}, actor=ctx["controller"])
    return True


def bounce_gate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    cards = effects._cards(plan, ctx, e["who"])
    effects.bounce(plan, ctx, e)
    if not any(plan.state.cards[c].zone.endswith(":hand") for c in cards):
        del ctx["effects"][ctx["next"]:ctx["next"] + e["skip"]]  # the later instructions don't happen
    return True


def attach_all(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Rhuk: every Equipment attached to the event creature (603.10a: as it was just before it died) moves to the source (701.3a)."""
    from app.rules import attachments, context

    me = plan.state.cards.get(ctx.get("source_card") or "")
    if me is None or not me.zone.endswith(":battlefield") or plan.oid(me) != ctx.get("source_object"):
        return True
    for ref in context._object_refs(ctx, context.EVENT, was=True):
        here = context._same(plan, ref)
        snap = context.snapshot(plan, ref)
        ids = [c.id for c in plan.state.cards.values() if c.attached_to == here.id] if here is not None else list(snap.attached) if snap else []
        for cid in ids:
            gear = plan.state.cards.get(cid)
            if gear is not None and gear.zone.endswith(":battlefield") and "Equipment" in plan.ch(gear).subtypes:
                attachments.attach(plan, cid, me.id, ctx["controller"])
    return True


# friend or foe sides (app/rules/friend_foe.py): the acting player is "you" while the block runs (tempting.as_player)
SIDES: dict[str, list[Def]] = {
    # Regna's Sanction: a choice of their own (608.2d), then every other creature they control becomes tapped
    "chooses one untapped creature they control, then taps the rest": [
        {"do": "player_chooses", "who": "you", "sel": 'sel:{"tapped":false,"types":["Creature"]}', "n": 1, "label": "untapped creature", "as": "keep110i"},
        {"do": "bind_rest110i", "as": "rest110i"}, {"do": "tap", "who": "ref:rest110i"}],
    # Zndrsplt's Judgment: the friend chooses which creature they control to copy; the token is created under their control (111.2)
    "creates a token that's a copy of a creature they control": [
        {"do": "player_chooses", "who": "you", "sel": 'sel:{"types":["Creature"]}', "n": 1, "label": "creature", "as": "copy110i"},
        {"do": "token_copy", "n": 1, "who": "ref:copy110i"}],
}


def goad_while(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects, keyword_actions, layers

    cards = effects._cards(plan, ctx, e["who"])
    if cards:
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer="6", source=ctx.get("source_object"), controller=ctx["controller"],
                          duration="permanent", imposes=(keyword_actions.GOADED + ctx["controller"],), label="Goaded while the Saga remains")
        fx = plan.rules.effects[-1]
        fx.duration, fx.source_card, fx.until_player = "source_on_battlefield", ctx.get("source_card"), ctx["controller"]
    return True


def bind_rest(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Taps the rest": the creatures the acting player controls other than the one they chose."""
    from app.rules import context

    chosen = next((n for n in context.refs(ctx) if n.endswith("keep110i")), None)  # (spell lines rename their bindings: scripts.rename_bindings)
    keep = set(context.objects(plan, ctx, chosen)) if chosen else set()
    mine = [c.id for c in plan.state.cards.values() if c.zone == f"{ctx['controller']}:battlefield" and "Creature" in plan.ch(c).types and c.id not in keep]
    context.bind_objects(plan, ctx, e["as"], mine)
    return True


def exile_library(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.13 exile: every card of the controller's library moves to exile, face up."""
    pid = ctx["controller"]
    if cards := list(plan.state.zones.get(f"{pid}:library", [])):
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "exile"}}, actor=pid)
    return True


def bind_first(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    context.bind_objects(plan, ctx, "first110i", effects._cards(plan, ctx, "host"))
    return True


def bauble(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """That player (the owner of the targeted cards) draws at the next upkeep. Zero targets are legal (115.6) but leave "that player" undefined
    (no CR rule or ruling): that one resolution is handed to manual play."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    ids = effects._cards(plan, ctx, e["who"])
    if not ids:
        decide(plan, player=ctx["controller"], kind="manual_resolution",
               prompt="Lodestone Bauble had no target, so \"that player\" is undefined. Resolve any draw at the next upkeep by hand, then press Done.",
               options=[DecisionOption(id="done", label="Done")], resume={"step": "bauble110i", "ctx": ctx})
        return False
    owner = plan.state.cards[ids[0]].owner if ids else None
    if owner in plan.live():
        ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "delayed", "when": {"kind": "step", "step": "upkeep", "whose": "next_turn"}, "n": 1},
                                                   {"do": "deferred:draw", "who": f"player:{owner}", "n": 1}]
    return True


def destroy_mark(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.8a: the creature is "destroyed this way" only if this destroy put it into a graveyard (regeneration / indestructible: no); then the
    counter goes on the first creature at the next end step (603.7)."""
    from app.rules import context, delayed, effects

    doomed = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    effects.PRIMITIVES["destroy"](plan, ctx, {**e, "do": "destroy"})
    now = plan.state.cards.get(doomed[0]) if doomed else None  # (a token ceases to exist in the graveyard, 111.7)
    if doomed and (now is None or now.zone.endswith(":graveyard")) and (first := context._object_refs(ctx, "first110i")):
        refs = {"first110i": {"kind": "objects", "objects": [r.model_dump(mode="json") for r in first]}}
        delayed.create_plain(plan, ctx["controller"], ctx["source_card"], ctx["source_object"], ctx.get("name") or "Infinite Authority",
                             {"kind": "step", "step": "end", "whose": "next"},
                             [{"do": "bind_refs", "refs": refs}, {"do": "add_counters", "who": "ref:first110i", "kind": "+1/+1", "n": 1}])
    return True


PRIMITIVES = {"specter110i": specter, "raiding110i": raiding, "bind_self110i": bind_self, "bauble110i": bauble, "bind_first110i": bind_first, "destroy_mark110i": destroy_mark, "goad_while110i": goad_while, "bind_rest110i": bind_rest, "exile_library110i": exile_library, "attach_all110i": attach_all, "lose_rad110i": lose_rad, "bounce_gate110i": bounce_gate}


def ask_skip(plan: Plan, done: list[str]) -> bool:
    """Fasting: ask the active player whether the draw step they would begin is skipped (614.10a, 614.1); True while the question waits."""
    from app.game.rules_state import DecisionOption
    from app.rules import scripts, skips
    from app.rules.plan import decide

    if skips._static(plan, plan.active, "draw") is not None:
        return False  # a mandatory skip replaces the step first
    for c in plan.state.cards.values():
        if c.id in done or c.controller != plan.active or not c.zone.endswith(":battlefield") or c.face_down:
            continue
        if any(d.get("static") == "skip_may110i" for d in scripts.definitions(plan.ch(c)).values()):
            decide(plan, player=plan.active, kind="choose_one", prompt=f"{c.name}: skip your draw step instead (you gain 2 life)?",
                   options=[DecisionOption(id="yes", label="Skip the draw step"), DecisionOption(id="no", label="Draw as usual")],
                   resume={"step": "skip_may110i", "src": c.id, "done": done})
            return True
    return False


def resume_skip(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects, engine, replace

    r = d.resume
    done = [*r["done"], r["src"]]
    if chosen == ["yes"]:
        plan.rules.skips.append({"player": plan.active, "what": "draw", "label": plan.state.cards[r["src"]].name or "an effect", "turn": plan.state.turn.number})
        replace.gain_life(plan, [(plan.active, 2)], actor=plan.active)
    elif ask_skip(plan, done):
        return
    if effects.skips.skip_steps(plan, ask=False):
        return
    engine._mark_step(plan)
    engine.on_step_start(plan)


def resume_bauble(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, decision.resume["ctx"])


_PHOENIX = ("If this creature would die, return it to its owner's hand instead. Until that player's next turn, that player plays with that card revealed in "
            "their hand and can't play it.")


_DAWN = ("Until end of turn, spells and abilities you control that would add colored mana instead add that much white mana. Until end of turn, you may spend "
        "white mana as though it were mana of any color.")


def false_dawn(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """False Dawn (106.12b, 609.4b): this turn the controller's colored mana becomes white (``mana_replace`` for permanents tapped or sacrificed for mana,
    ``dawn_mana`` for what spells and other abilities add) and white mana may be spent as any color (``spending_active``)."""
    from app.rules import selectors, tap_mana

    sel = selectors.parse("permanent")
    assert sel is not None
    tap_mana.until_eot(plan, ctx, {"def": {"kind": "static", "static": "mana_replace", "who": "you", "sel": sel.key(), "all110i": True,
                                           "op": {"do": "colored_recolor86", "to": "W"}, "effects": []}})
    return tap_mana.until_eot(plan, ctx, {"def": {"kind": "static", "static": "spend_white110i", "effects": []}})


PRIMITIVES["false_dawn110i"] = false_dawn


def _dawn(state: Any, controller: str, kind: str) -> bool:
    r = state.rules
    return r is not None and any(x["def"].get("static") == kind and x["controller"] == controller and x.get("turn") == state.turn.number for x in r.tap_mana)


def dawn_mana(plan: Plan, controller: str, mana: list[str]) -> list[str]:
    """Mana an effect of ``controller`` adds: colored becomes white under False Dawn."""
    if not _dawn(plan.state, controller, "mana_replace"):
        return mana
    return ["W" if c in "WUBRG" else c for c in mana]


def spending_active(state: Any, player: str) -> bool:
    return _dawn(state, player, "spend_white110i")


def reveal_ban(plan: Plan, card: Any) -> None:
    """Firestorm Phoenix (614.1a): after it returned to its owner's hand, until that player's next turn it is revealed (701.20a) and they can't cast it (601.3).
    ponytail: a creature, so only casting is barred (a land would also need cast_limits.land_problem)."""
    import secrets

    if not card.zone.endswith(":hand"):
        return
    r = plan.rules
    plan.do({"type": "reveal", "card_ids": [card.id]}, actor=card.owner)
    r.cast_limits.append({"id": secrets.token_hex(4), "player": card.owner, "controller": card.owner, "until": "next_turn", "turn": plan.state.turn.number,
                          "obj110i": plan.oid(card), "reveal110i": card.id, "label": card.name})


def note_exiled(plan: Plan, ctx: Context, cards: list[str]) -> None:
    """Hero of Bretagard: a spell or ability ``ctx['controller']`` controls exiled these permanents from the battlefield; one event for the batch (603.2c)."""
    from app.game.rules_state import Event

    n = sum(1 for c in cards if (k := plan.state.cards.get(c)) is None or k.zone.endswith(":exile"))
    if n:
        r = plan.rules
        r.events.append(Event(batch=r.batch, kind="designation", turn=plan.state.turn.number, counter="exiled110i", player=ctx["controller"], amount=n))


def transform_attach(plan: Plan, card: Any) -> None:
    """Curse of Leeches: as it turns over into the Aura face, its controller attaches it to a player (303.4f; a replacement-like step, not a trigger).
    The decision stands before state-based actions (704.5m would put an unattached Aura into the graveyard)."""
    from app.game.rules_state import DecisionOption
    from app.rules import attachments, scripts
    from app.rules.plan import decide

    if plan.manual(card) or not any(d.get("static") == "as_transform_attach110i" for d in scripts.definitions(plan.ch(card)).values()):
        return
    hosts = [p for p in plan.live() if attachments.host_problem(plan, card, p) is None]
    if hosts:
        decide(plan, player=card.controller, kind="choose_one", prompt=f"{card.name}: attach it to a player", source=card,
               options=[DecisionOption(id=p, label=plan.state.players[p].name) for p in hosts], resume={"step": "transform_attach110i", "card": card.id})


def resume_transform_attach(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import attachments

    attachments.attach(plan, d.resume["card"], chosen[0], d.player)


RESUME = {"transform_attach110i": resume_transform_attach, "bauble110i": resume_bauble, "skip_may110i": resume_skip, "specter110i": resume_specter, "specter_top110i": resume_specter_top, "raiding_tap110i": resume_raiding_tap, "raiding_plains110i": resume_raiding_plains}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    text = ability.text.strip()
    if text == _PHOENIX:
        return {"kind": "replacement", "replacement": "hand_instead110i", "from": "battlefield", "effects": []}
    if text == "As this permanent transforms into Curse of Leeches, attach it to a player.":
        return {"kind": "static", "static": "as_transform_attach110i", "effects": []}
    if (same := _AS.get(text)) is not None:
        return scripts.define(replace(ability, text=same), ch)
    built = _BUILD.get(text)
    if built is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)
