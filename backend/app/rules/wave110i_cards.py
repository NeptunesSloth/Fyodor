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
    # Pin Collection: the stickers' abilities reach the equipped creature through stickers101.continuous (613.1f); the static itself is the +1/+1
    "Equipped creature gets +1/+1 and has all abilities of ability stickers on this Equipment.": "Equipped creature gets +1/+1.",
    # Nick Fury: the DFC transform is independent of the rest going to the bottom (701.27c, 608.2c); said last, the grammar reads "you may transform it" as the final choice
    "Power-up \u2014 {W}{U}{B}{R}{G}: Put two +1/+1 counters on Nick Fury, then look at the top seven cards of your library. You may put a Hero, Equipment, or Vehicle "
    "card from among them onto the battlefield. If it's a double-faced card, you may transform it. Put the rest on the bottom of your library in a random order.":
        "Power-up \u2014 {W}{U}{B}{R}{G}: Put two +1/+1 counters on Nick Fury, then look at the top seven cards of your library. You may put a Hero, Equipment, or Vehicle "
        "card from among them onto the battlefield. Put the rest on the bottom of your library in a random order. If it's a double-faced card, you may transform it.",
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


_PLAGUE = ("When enchanted creature dies, its controller chooses target creature one of their opponents controls. "
           "Return this card from its owner's graveyard to the battlefield attached to that creature.")


def _plague(d: Def) -> Def:
    """Necrotic Plague: the dying creature's controller picks the target (603.3d; ``triggers`` host_controller110i), the Aura returns under its owner's control (no "under your control")."""
    return {**d, "target_choice": "host_controller110i", "effects": [{**x, "under": "owner"} if x.get("do") == "return_card" else x for x in d["effects"]]}


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


def _camp(d: Def) -> Def:
    """C.A.M.P.: the Junk token is made only if the counter's creature shares a color with the mana the land produced (``camp_holds``)."""
    *head, last = d["effects"]
    return {**d, "effects": [*head, {"do": "only_if", "cond": {"camp110i": True}, "skip": 1}, last]}


def camp_holds(plan: Plan, ctx: Context) -> bool:
    event = ctx.get("event") or {}
    mask = int(event.get("amount") or 0)
    target = next((plan.state.cards.get(t["id"]) for t in ctx.get("targets") or [] if t and t["id"] in plan.state.cards), None)
    return target is not None and any(mask >> "WUBRG".index(c) & 1 for c in plan.ch(target).colors)


def _letters(letter: str) -> Callable[[Def], Def]:
    """Balls of Fire / Splash: "the number of {letter}'s in name stickers on this enchantment" (values.py ``letters110i``)."""
    n = {"letters110i": letter}

    def fix(d: Def) -> Def:
        es = [{**e, "n": n} if e.get("do") == "damage" else e for e in d["effects"]]
        t = d.get("target") or d.get("targets")
        if isinstance(t, dict) and "max" in t:
            return {**d, "effects": es, "target": {**t, "x_value": n}}
        return {**d, "effects": es}

    return fix


def _flipped(d: Def) -> Def:
    """Homura: 710.2, 110.5 the returned object enters flipped (``flipped`` on the return; it enters under the trigger controller's control, 110.2a)."""
    return {**d, "effects": [{**e, "flipped": True} if e.get("do") == "return_card" else e for e in d["effects"]]}


_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    "When Homura dies, return it to the battlefield flipped.": ("When ~ dies, return this card to the battlefield under your control.", _flipped),
    "Whenever you put a sticker on this enchantment, it deals damage equal to the number of o's in name stickers on this enchantment to any target.":
        ("Whenever you put a sticker on this enchantment, this enchantment deals 2 damage to any target.", _letters("o")),
    "Whenever you put a sticker on this enchantment, tap up to X target creatures, where X is the number of u's in name stickers on this enchantment.":
        ("Whenever you put a sticker on this enchantment, tap up to three target creatures.", _letters("u")),
    "Whenever fortified land is tapped for mana, put a +1/+1 counter on target creature you control. If that creature shares a color with the mana that land produced, "
    "create a Junk token.":
        ("Whenever fortified land is tapped for mana, put a +1/+1 counter on target creature you control. Create a Junk token.", _camp),
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
    _PLAGUE: ("When enchanted creature dies, return this card from your graveyard to the battlefield attached to target creature.", _plague),
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
    if body.strip()[:1].upper() + body.strip()[1:] == _TUNNEL:
        return [{"do": "tunnel110i"}], None, False
    if body.strip() == _DAWN:
        return [{"do": "false_dawn110i"}], None, False
    if body.strip() == _CHANNEL:  # -- cards (wave 110I) -- Yavimaya Bloomsage's Channel
        return [{"do": "channel110i"}], None, False
    if body.strip() == _MEDOMAI:  # 603.7: chapter III creates a delayed trigger for this turn (Scryfall ruling 2018-04-27: with no name chosen it can never trigger)
        parsed = scripts.parse_effects("Whenever you cast a spell with the chosen name this turn, draw two cards.")
        assert parsed is not None
        effects, target, optional = parsed
        effects[0]["when"]["cond"]["first_named110i"] = True
        effects[0]["once"] = True
        return effects, target, optional
    return scripts.parse_effects(same) if (same := REWRITES.get(body.strip())) is not None else None


_SPOILS = ["X is the number of artifact and/or creature cards in an opponent's graveyard as you cast this spell.",
           "Distribute X +1/+1 counters among any number of target creatures."]


def spell(ch: Any, lines: list[Any]) -> Def | None:
    """Whole-spell wordings: Spoils of War's X sentence defines the divided total (107.3c) counted as it is cast (601.2d)."""
    from app.rules import scripts

    if [x.text for x in lines] == [_GLYPH]:
        return glyph(ch)
    if [x.text for x in lines] != _SPOILS:
        return None
    parsed = scripts.parse_effects("Distribute X +1/+1 counters among any number of target creatures, where X is the number of creature cards in your graveyard.")
    assert parsed is not None
    effects, targets, _ = parsed
    targets[0]["divide"]["value"] = {"opp_gy110i": ["Artifact", "Creature"]}
    return {"kind": "spell", "whole110k": True, "effects": effects, **scripts.target_fields(targets)}  # (whole110k: coverage reads both lines as this one definition)


_GLYPH = ("Put X glyph counters on target creature that target Wall blocked this turn, where X is the power of that blocked creature. The creature gains "
          "\"This creature doesn't untap during your untap step if it has a glyph counter on it\" and \"At the beginning of your upkeep, remove a glyph counter from "
          "this creature.\"")


def glyph(ch: Any) -> Def | None:
    """Glyph of Delusion: counters equal to the power of the blocked creature (read as it resolves, 608.2h LKI), the creature gains the two granted lines for good."""
    from app.rules import language, scripts

    parsed = scripts.parse_effects("Put a glyph counter on target creature. That creature gains \"This creature doesn't untap during your untap step if it has a glyph counter on it.\" "
                                   "That creature gains \"At the beginning of your upkeep, remove a glyph counter from this creature.\"")
    creature, wall = language.target_group("target creature"), language.target_group("target Wall")
    if parsed is None or creature is None or wall is None:
        return None
    effects = [{**e, "n": {"power": "target"}} if e.get("do") == "add_counters" else e for e in parsed[0]]
    groups = [{**creature, "blocked_by110i": 1, "role110i": "blocked"}, {**wall, "blocked_by110i": 0, "role110i": "wall"}]
    return {"kind": "spell", "whole110k": True, "effects": effects, **scripts.target_fields(groups)}


def block_options(plan: Plan, spec: dict[str, Any], options: list[str], groups: list[list[str]]) -> list[str]:
    """Glyph of Delusion's two linked groups (``role110i`` "blocked" / "wall", ``blocked_by110i`` the other group's index): a Wall and a creature it blocked this turn
    (509.1g; ruling 2004-10-04: any creature it was assigned to block or blocked through bands or a switched block, all in the turn's block history)."""
    r = plan.state.rules
    if r is None or r.turn_log.turn != plan.state.turn.number:
        return []
    pairs = [(blocker.rsplit(".", 1)[0], attackers) for blocker, attackers in r.turn_log.blocks.items()]
    other = groups[spec["blocked_by110i"]][0] if spec["blocked_by110i"] < len(groups) and groups[spec["blocked_by110i"]] else None
    if spec["role110i"] == "wall":
        return [t for t in options if any(w == t and (other is None or r.object_id(other) in att) for w, att in pairs)]
    walls = {w for w, att in pairs if plan.state.cards.get(w) is not None and "Wall" in plan.ch(plan.state.cards[w]).subtypes}
    return [t for t in options if any(w in walls and (other is None or w == other) and r.object_id(t) in att for w, att in pairs)]


def opp_gy_total(plan: Plan, you: str, types: list[str], x: int | None) -> int:
    """Spoils of War, ruling 2008-08-01: you choose an opponent as you cast it and X ({X}{B}, 107.3c) is the number of those cards in that player's graveyard: the announced X
    names the opponent (as for Bargaining Table); any other X is refused."""
    from app.game.errors import ActionError

    counts = {p: sum(1 for c in plan.state.zones.get(f"{p}:graveyard", []) if set(types) & set(plan.ch(plan.state.cards[c]).types)) for p in plan.live() if p != you}
    if (x or 0) in counts.values() or not counts:
        return int(x or 0)
    raise ActionError(f"X must be the number of artifact and/or creature cards in an opponent's graveyard: {sorted(set(counts.values()))}")


_MEDOMAI = "When you cast a spell with the chosen name for the first time this turn, draw two cards."


def first_named(plan: Plan, source: str, player: str | None) -> bool:
    """The spell just cast is the only one by ``player`` this turn with the Saga's chosen name (601.2i: the log already holds it)."""
    from app.cards.names import normalize_name
    from app.rules import card_names, history

    name = card_names.chosen(plan, source)
    if not name:
        return False
    want = normalize_name(name)
    return sum(1 for n in history.log_for(plan).casts if n.player == player and want in {normalize_name(x) for x in n.names or []}) == 1


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


_TUNNEL = ("Choose an opponent. They choose a creature they control, then you choose a creature you control. You may exile the chosen creatures. If you do, return them "
           "to the battlefield under their owners' control at the beginning of the next end step. Otherwise, the chosen creatures fight each other.")


def _pick(plan: Plan, ctx: Context, who: str, ids: list[str], prompt: str, **resume: Any) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=who, kind="choose_one", prompt=f"{ctx.get('name') or 'Tunnel of Love'}: {prompt}",
           options=[DecisionOption(id=i, label=plan.state.players[i].name if i in plan.state.players else plan.state.cards[i].name or "a creature") for i in ids],
           resume={"step": "tunnel110i", "ctx": ctx, **resume})
    return False


def _creatures(plan: Plan, pid: str) -> list[str]:
    return [c for c in plan.state.zones.get(f"{pid}:battlefield", []) if plan.ch(plan.state.cards[c]).is_creature]


def tunnel(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Tunnel of Love, one visit: the chosen opponent (101.4 nothing to choose with one), their creature, then the visitor's; the visitor may exile both (returned at
    the beginning of the next end step, 603.7), otherwise they fight (701.14). A side with no creature chooses none; only chosen creatures are exiled or fight."""
    me = ctx["controller"]
    opps = [p for p in plan.live() if p != me]
    if len(opps) > 1:
        return _pick(plan, ctx, me, opps, "choose an opponent", phase="opp")
    return _tunnel_theirs(plan, ctx, opps[0]) if opps else True


def _tunnel_theirs(plan: Plan, ctx: Context, opp: str) -> bool:
    theirs = _creatures(plan, opp)
    return _pick(plan, ctx, opp, theirs, "choose a creature you control", phase="theirs") if theirs else _tunnel_mine(plan, ctx, None)


def _tunnel_mine(plan: Plan, ctx: Context, theirs: str | None) -> bool:
    mine = _creatures(plan, ctx["controller"])
    return _pick(plan, ctx, ctx["controller"], mine, "choose a creature you control", phase="mine", theirs=theirs) if mine else _tunnel_exile(plan, ctx, theirs, None)


def _tunnel_exile(plan: Plan, ctx: Context, theirs: str | None, mine: str | None) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    if not (theirs or mine):
        return True
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Tunnel of Love'}: exile the chosen creatures?",
           options=[DecisionOption(id="yes", label="Exile them (they return at the next end step)"), DecisionOption(id="no", label="Don't: they fight each other")],
           resume={"step": "tunnel110i", "ctx": ctx, "phase": "exile", "theirs": theirs, "mine": mine})
    return False


def _tunnel_end(plan: Plan, ctx: Context, theirs: str | None, mine: str | None, exile: bool) -> None:
    from app.rules import context, delayed, effects

    chosen = [c for c in (theirs, mine) if c and c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")]
    if exile:
        effects.exile_cards(plan, ctx, {"do": "exile"}, chosen)
        objs = [r for c in chosen if (r := context.ref_of(plan, c)) is not None and (r.zone or "").endswith(":exile")]
        if objs:
            delayed.create_plain(plan, ctx["controller"], ctx["source_card"], ctx["source_object"], ctx.get("name") or "Tunnel of Love",
                                 {"kind": "step", "step": "end", "whose": "next"},
                                 [{"do": "bind_refs", "refs": {"tl110i": {"kind": "objects", "objects": [r.model_dump(mode="json") for r in objs]}}},
                                  {"do": "return_card", "who": "ref:tl110i", "to": "battlefield", "tapped": False, "under": "owner"}])
    elif theirs and mine:
        context.bind_objects(plan, ctx, "tl_a110i", [theirs])
        context.bind_objects(plan, ctx, "tl_b110i", [mine])
        effects.fight(plan, ctx, {"do": "fight", "who": "ref:tl_a110i", "with": "ref:tl_b110i"})


def resume_tunnel(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    ctx, phase = r["ctx"], r["phase"]
    if phase == "opp":
        done = _tunnel_theirs(plan, ctx, chosen[0])
    elif phase == "theirs":
        done = _tunnel_mine(plan, ctx, chosen[0])
    elif phase == "mine":
        done = _tunnel_exile(plan, ctx, r["theirs"], chosen[0])
    else:
        _tunnel_end(plan, ctx, r["theirs"], r["mine"], chosen == ["yes"])
        done = True
    if done:
        effects.continue_effects(plan, ctx)


PRIMITIVES["tunnel110i"] = tunnel


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


_CHANNEL = "Until end of turn, any time you could activate a mana ability, you may pay 1 life. If you do, add {C}."


CHANNEL_ID = "player:channel110i"  # the pseudo object id ``ActivateAbility.card_id`` names: a player-level mana ability, not a card's


def channel(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Channel (605.3a, 106.12): until end of turn the controller has a mana ability "pay 1 life: add {C}" (a player-level ability, activated with
    ``CHANNEL_ID``: ``channel_activate``) usable whenever they could activate a mana ability, also while paying a cost."""
    from app.rules import tap_mana

    return tap_mana.until_eot(plan, ctx, {"def": {"kind": "static", "static": "channel110i", "effects": []}})


PRIMITIVES["channel110i"] = channel


def channel_activate(plan: Plan) -> None:
    """Pay 1 life (119.4, 118.3: needs 1 life; replacements apply, 118.11) and add {C} to the pool through the ordinary ``rules_mana`` step (106.4):
    plain pool mana, so it floats, counts as mana spent and pays {C}, X and ability costs like any other."""
    from app.game.errors import ActionError
    from app.rules import prohibitions
    from app.rules import replace as replace_

    who = plan.actor
    if not channel_active(plan.state, who):
        raise ActionError("You have no such mana ability")
    if prohibitions.life_banned(plan.state, plan.info, mana_ability=True):
        raise ActionError("You can't pay life")
    if plan.state.players[who].life < 1:
        raise ActionError("You don't have 1 life to pay")
    replace_.lose_life(plan, [(who, 1)], actor=who, paid=True)
    plan.do({"type": "rules_mana", "player": who, "tap": [], "sacrifice": [], "delta": {"C": 1}, "life": 0, "label": "paid 1 life: added {C}"}, actor=who)


def channel_active(state: Any, player: str) -> bool:
    return _dawn(state, player, "channel110i")


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


RESUME = {"tunnel110i": resume_tunnel, "transform_attach110i": resume_transform_attach, "bauble110i": resume_bauble, "skip_may110i": resume_skip, "specter110i": resume_specter, "specter_top110i": resume_specter_top, "raiding_tap110i": resume_raiding_tap, "raiding_plains110i": resume_raiding_plains}


_WHISTLE = ("{3}, {T}: Choose target non-Wall creature the active player has controlled continuously since the beginning of the turn. That player may pay {X}, where X is "
            "that creature's mana value. If they don't pay, the creature attacks this turn if able, and at the beginning of the next end step, destroy it if it didn't attack "
            "this turn. Activate only before attackers are declared.")


_WEE = ("Whenever you place a sticker, this creature gets +1/+1 until end of turn. If it's an art sticker, instead put a +1/+1 counter on this creature.")
_AIRBRUSHER = "Whenever you place a sticker, create a Treasure token. If it's an art sticker, instead create two Treasure tokens."


def letters(plan: Plan, ctx: Context, v: dict[str, Any]) -> int:
    """The number of a letter in the name stickers on the source (Balls of Fire, Splash: 123.2)."""
    c = plan.state.cards.get(ctx.get("source_card") or "")
    return 0 if c is None else sum(p.sticker.text.casefold().count(v["letters110i"]) for p in c.stickers101 if p.sticker.kind == "name")


def holds(plan: Plan, ctx: Context, cond: dict[str, Any]) -> bool:
    """Wee Champion / Goblin Airbrusher: the placed sticker (the trigger event's kind) is an art sticker (123.2)."""
    return (ctx.get("event") or {}).get("sticker") == cond["w110i"]


def sticker_instead(ability: Any, ch: Any) -> Def | None:
    """"Whenever you place a sticker, X. If it's an art sticker, instead Y." (608.2c): the condition is judged once, then exactly one of X and Y."""
    from app.rules import multi100n, scripts

    trig, alt = (_WEE_PARTS if ability.text.strip() == _WEE else _AIR_PARTS)
    d = scripts.define(replace(ability, text=f"Whenever you place a sticker, {trig}."), ch)
    more = scripts.parse_effects(f"{alt}.")
    if d is None or more is None or len(d["effects"]) != len(more[0]):
        return None
    return {**d, "effects": multi100n._instead({"w110i": "art"}, d["effects"], more[0])}


_WEE_PARTS = ("this creature gets +1/+1 until end of turn", "Put a +1/+1 counter on this creature")
_AIR_PARTS = ("create a Treasure token", "Create two Treasure tokens")


_WOLF = ("When this creature enters, you may put a name sticker on it. When you do, up to X target creatures each get -1/-1 until end of turn, where X is the number "
         "of unique vowels on that sticker.")


def wolf(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Wolf in _____ Clothing (603.12): if a name sticker was put on it, a reflexive trigger whose X (its event amount) is the unique vowels of that sticker (A, E, I, O, U, Y)."""
    from app.game.rules_state import TriggerEvent
    from app.rules import scripts
    from app.rules.triggers import _add

    records = (ctx.get("sticker_receipts101") or {}).get("name102") or []
    if not records:
        return True
    base = scripts.parse_effects("Up to three target creatures each get -1/-1 until end of turn.")
    assert base is not None
    ability = {"kind": "triggered", "trigger": "reflexive", "effects": base[0], "optional": False, "target": None,
               "targets": [{**base[1][0], "x_value": {"event_amount": 1}}]}
    n = len(set(records[-1]["sticker"]["text"].casefold()) & set("aeiouy"))
    _add(plan, controller=ctx["controller"], source_card=ctx.get("source_card") or "", source_object=ctx.get("source_object") or "",
         name=str(ctx.get("name") or ""), index=7300, definition=ability, event=TriggerEvent(kind="reflexive", amount=n))
    return True


PRIMITIVES["wolf110i"] = wolf


_CATALYST = ("{1}{R}, {T}: Choose an exiled card used to craft this artifact at random. You may cast that card without paying its mana cost.")


def catalyst(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Cosmium Catalyst (702.167a, random pick as random_choice.choose_random_object): one of the exiled cards used to craft it (still those objects, still in exile)."""
    import secrets

    from app.rules import context

    refs = plan.rules.crafted_materials.get(ctx.get("source_object") or "", [])
    found = sorted(r.card for r in refs if (c := plan.state.cards.get(r.card)) is not None and plan.oid(c) == r.object_id and c.zone.endswith(":exile"))
    pick = (plan.rng or secrets.SystemRandom()).choice(found) if found else None
    if pick is not None:
        plan.note(f"{ctx.get('name') or 'It'}: chosen at random \u2192", [pick], actor=ctx["controller"])
    context.bind_objects(plan, ctx, "crafted110i", [pick] if pick is not None else [])
    return True


PRIMITIVES["catalyst110i"] = catalyst


def whistle(ability: Any, ch: Any) -> Def | None:
    """Arcum's Whistle (118.12a, 508.1d, 603.4): Nettling Imp's targeted forced attack plus end-step destroy (wave110e_imps), all behind the active player's optional {X}
    payment (X the creature's mana value); paid, nothing happens."""
    from app.rules import scripts, selectors
    from app.rules.controller_turn_history69 import EXTRA

    base = scripts.define(replace(ability, text="{3}, {T}: Target non-Wall creature attacks this turn if able. Activate only before attackers are declared."), ch)
    kill = scripts.parse_effects("Target creature attacks this turn if able. At the beginning of the next end step, destroy it.")
    pay = scripts.parse_effects("Target creature attacks this turn if able unless its controller pays {X}, where X is its mana value.")
    if base is None or kill is None or pay is None or len(kill[0]) != 3 or len(pay[0]) != 3:
        return None
    sel = selectors.from_key(base["target"]["what"])
    sel = replace(sel, controller="active", extras=(*sel.extras, EXTRA))
    rest = [*base["effects"], {**kill[0][1], "n": 2}, {"do": "deferred:didnt_attack110e", "who": "target"}, kill[0][2]]
    effects = [pay[0][0], {**pay[0][1], "skip": len(rest)}, *rest]
    return {**base, "effects": effects, "target": {**base["target"], "what": sel.key()}}


_PERFORMER = ("When this creature enters, if you cast it from your hand, choose target spell or ability that targets only a single permanent or player. Copy that spell or "
              "ability for each other permanent or player the spell or ability could target. Each copy targets a different one of those permanents and players.")
_AGRUS = ("Whenever Agrus Kos becomes the target of an ability that targets only it, you may pay {1}{R/W}. If you do, copy that ability for each other creature you control "
          "that ability could target. Each copy targets a different one of those creatures.")
_DAGGER = ("{4}, {T}: Whenever target creature deals combat damage to a non-Wall creature this turn, destroy that non-Wall creature. "
           "When the targeted creature leaves the battlefield this turn, sacrifice this artifact. Activate only before blockers are declared.")
_COFFIN = ("{2}{B}, {T}: Put target creature card from a graveyard onto the battlefield under your control. "
           "When this creature becomes untapped or you lose control of this creature, exile that creature.")


def _coffin(d: Def) -> Def:
    """Coffin Queen: 603.7a — the delayed trigger watches the Queen (untapped, or control of her lost: delayed.on_events) and exiles the creature put onto the battlefield (bound now, 603.7c)."""
    back = {**d["effects"][0], "as": "coffin110i"}
    watch = {"do": "delayed", "when": {"kind": "event", "event": "lose_or_untap110i"}, "n": 1, "who": "self"}
    return {**d, "effects": [back, watch, {"do": "deferred:exile", "who": "ref:coffin110i"}]}


_FLICKER = ("{2}{W}{W}: Exile enchanted creature and all Auras attached to it. At the beginning of the next end step, return that card to the battlefield under its owner's control. "
            "If you do, return the other cards exiled this way to the battlefield under their owners' control attached to that creature.")


def flicker_exile(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Flickerform: the creature and every Aura on it leave together (one move, so the Auras are not put into graveyards by 704.5m first)."""
    from app.rules import context, delayed, effects

    hosts = effects._cards(plan, ctx, "host")
    if not hosts:
        return True
    auras = [c.id for c in plan.state.cards.values() if c.attached_to == hosts[0] and c.zone.endswith(":battlefield") and "Aura" in plan.ch(c).subtypes]
    plan.do({"type": "move", "card_ids": [*hosts, *auras], "to": {"zone": "exile"}}, actor=ctx["controller"])
    context.bind_objects(plan, ctx, "flick_h110i", [c for c in hosts if plan.state.cards[c].zone.endswith(":exile")])
    context.bind_objects(plan, ctx, "flick_a110i", [c for c in auras if plan.state.cards[c].zone.endswith(":exile")])
    ctx["effects"][ctx["next"]:ctx["next"]] = delayed.wrap_when([{"do": "flicker_return110i"}], delayed.WHEN["the next end step"])
    return True


def flicker_return(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The card returns under its owner's control (400.7: a new object); only if it does, the other exiled cards return attached to it (303.4i: an Aura that can't enchant it stays exiled)."""
    back = {"do": "return_card", "to": "battlefield", "tapped": False, "under": "owner"}
    ctx["effects"][ctx["next"]:ctx["next"]] = [{**back, "who": "ref:flick_h110i", "as": "flick_new110i"}, {"do": "flicker_auras110i"}]
    return True


def flicker_auras(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context

    new = [c for c in context.objects(plan, ctx, "flick_new110i") if plan.state.cards[c].zone.endswith(":battlefield")]
    auras = [c for c in context.objects(plan, ctx, "flick_a110i") if plan.state.cards[c].zone.endswith(":exile")]
    if new and auras:
        context.bind_objects(plan, ctx, "flick_a110i", auras)
        ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "return_card", "to": "battlefield", "tapped": False, "under": "owner", "who": "ref:flick_a110i", "host": "ref:flick_new110i"}]
    return True


PRIMITIVES.update({"flicker_exile110i": flicker_exile, "flicker_return110i": flicker_return, "flicker_auras110i": flicker_auras})


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    text = ability.text.strip()
    if text == _PERFORMER:  # 707.10d/e: a copy of the spell or ability for each other permanent or player it could target (the Radiate spread, wave110e_once.radiate)
        native = scripts.define(replace(ability, text="When ~ enters, if you cast it from your hand, copy target spell or ability that targets only a single permanent or player."), ch)
        return None if native is None else {**native, "effects": [{"do": "radiate110e"}]}
    if text == _AGRUS:
        native = scripts.define(replace(ability, text="Whenever ~ becomes the target of an ability, you may pay {1}{R/W}. If you do, draw a card."), ch)
        if native is None:
            return None
        return {**native, "cond": {**native["cond"], "only_self110i": True},
                "effects": [{"do": "spread_copy103", "golem": False, "ability110i": True} if e.get("do") == "draw" else e for e in native["effects"]]}
    if text == _DAGGER:  # 603.7 delayed triggers on the target; the "non-Wall" recipient is a condition of the damage trigger; timing: first combat phase only (ruling 2013-09-20, 506.8d)
        native = scripts.define(replace(ability, text=_DAGGER.replace("a non-Wall creature", "a creature").replace("that non-Wall creature", "that creature").replace(
            "the targeted creature", "that creature").replace("this artifact", "~")), ch)
        watch = next((e for e in (native or {}).get("effects", []) if e.get("do") == "delayed" and e["when"].get("kind") == "watch"), None)
        if native is None or watch is None:
            return None
        watch["when"]["cond"]["to_not_types110i"] = ["Wall"]
        watch["when"]["cond"]["other_side110i"] = True  # "that non-Wall creature" (the event's object) is the creature dealt the damage, not the one that dealt it
        return native
    if text == _COFFIN:
        native = scripts.define(replace(ability, text="{2}{B}, {T}: Put target creature card from a graveyard onto the battlefield under your control."), ch)
        return None if native is None else _coffin(native)
    if text == _FLICKER:
        native = scripts.define(replace(ability, text="{2}{W}{W}: Draw a card."), ch)
        return None if native is None else {**native, "effects": [{"do": "flicker_exile110i"}]}
    if text == "If a Rigger you control would assemble a Contraption, it assembles two Contraptions instead.":
        # 701.45a: assembling is an Unstable mechanic outside these rules; no player has a Contraption deck in a Commander game, so nothing can be assembled and this never applies
        return {"kind": "static", "static": "no_assemble110i", "effects": []}
    if text == _WHISTLE:
        return whistle(ability, ch)
    if text == _CATALYST:
        base = scripts.define(replace(ability, text="{1}{R}, {T}: Draw a card."), ch)
        return None if base is None else {**base, "effects": [{"do": "catalyst110i"},
                                                              {"do": "free_cast", "zone": "that", "who": "ref:crafted110i", "filter": None, "mv": None, "optional": True}]}
    if text == _WOLF:
        native = scripts.define(replace(ability, text="When this creature enters, draw a card."), ch)
        assert native is not None
        return {**native, "effects": [{"do": "put_sticker101", "who": "self", "kind": "name", "n": 1, "as": "name102"}, {"do": "wolf110i"}], "optional": False}
    if text in (_WEE, _AIRBRUSHER):
        return sticker_instead(ability, ch)
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
