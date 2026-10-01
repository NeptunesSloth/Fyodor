"""Battles (CR 310, researched against CR 2026-09-25).

* **Defense** (310.4): a battle enters with as many defense counters as its printed defense
  (310.4b: an intrinsic "enters with" replacement — ``replacements.entering_counters``); damage
  dealt to it removes that many (120.3h, 310.6: ``replace.do_damage``).
* **Protector** (310.9): chosen by its controller as it enters (310.9a, an entry choice made
  before it enters like any "as ~ enters" choice, 614.12a) — for a Siege, one of their opponents
  (310.12a); a battle with no battle type, only its controller. Kept per object in
  ``RulesState.protectors`` (a new object gets a new one, 400.7) and shown on the permanent.
  310.11 (a state-based action): a battle that isn't being attacked with no protector, or one who
  can't be, gets a new one chosen by its controller; with nobody to choose it goes to its owner's
  graveyard.
* **Attacking** (310.5, 310.9b, 508.1b): a battle can be attacked by any attacking player whose
  defending players include its protector — never by its protector (a Siege by its own
  controller, notably). The protector is the "defending player" for it (310.9d): they block the
  creatures attacking it (310.9c).
* **Defeat**: a non-Siege battle with no defense is put into its owner's graveyard (704.5w); a
  Siege has "When the last defense counter is removed from this permanent, exile it, then you may
  cast it transformed without paying its mana cost" (310.12b) and is put into the graveyard by
  704.5v only once that trigger has left the stack. Casting a card transformed isn't automated:
  after exiling it, its controller is asked to cast it by hand (then Done).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import CardInstance

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

PROTECTOR = "protector"  # the entry choice's name (answers, ``CHOICE_LABELS``)
DEFEATED = 6200  # the Siege trigger's ability index (an intrinsic ability, not a printed line)


def is_battle(ch: Characteristics) -> bool:
    return "Battle" in ch.types


def defense(ch: Characteristics) -> int:
    """310.4a: the printed defense (0 when it has none or it isn't a number)."""
    value = (ch.defense or "").strip()
    return int(value) if value.isdigit() else 0


def candidates(plan: Plan, ch: Characteristics, controller: str) -> list[str]:
    """Who may protect a battle with these characteristics under ``controller`` (310.9a, 310.12a)."""
    live = plan.live()
    if "Siege" in ch.subtypes:
        return [p for p in plan.apnap() if p != controller]
    return [controller] if controller in live else []


def protector(state: GameState, card: CardInstance) -> str | None:
    rules = state.rules
    return rules.protectors.get(rules.object_id(card.id)) if rules is not None else None


# -- entering (310.4b, 310.9a) ------------------------------------------------------------------------
def entry_choice(plan: Plan, ch: Characteristics, controller: str, answers: dict[str, str], out: dict[str, Any]) -> None:
    """``replacements.entry_plan``'s hook: the protector is chosen as the battle enters (before it
    does, 614.12a). One possible protector: no question."""
    if not is_battle(ch):
        return
    options = candidates(plan, ch, controller)
    if answers.get(PROTECTOR) in options:
        out.setdefault("choices", {})[PROTECTOR] = answers[PROTECTOR]
    elif len(options) == 1:
        out.setdefault("choices", {})[PROTECTOR] = options[0]
    elif options and "choice" not in out:
        out["choice"] = {"what": PROTECTOR}


def choice_options(plan: Plan, controller: str, card: CardInstance) -> list[DecisionOption]:
    probe = card.model_copy(update={"zone": f"{controller}:battlefield", "controller": controller})
    return [DecisionOption(id=p, label=plan.name(p)) for p in candidates(plan, plan.ch(probe), controller)]


def entered(plan: Plan, card_id: str, choices: dict[str, str] | None) -> None:
    """``replacements.after_entry``: record the protector chosen as it entered."""
    who = (choices or {}).get(PROTECTOR)
    card = plan.state.cards.get(card_id)
    if who and card is not None and card.zone.endswith(":battlefield"):
        set_protector(plan, card, who)


def set_protector(plan: Plan, card: CardInstance, who: str) -> None:
    r = plan.rules
    on_battlefield = {r.object_id(c.id) for c in plan.state.cards.values() if c.zone.endswith(":battlefield")}
    r.protectors = {oid: p for oid, p in r.protectors.items() if oid in on_battlefield}  # (gone objects: 400.7)
    r.protectors[plan.oid(card)] = who
    plan.do({"type": "set_choice", "card_id": card.id, "key": "Protector", "value": plan.name(who)}, actor=card.controller)


# -- attacking (310.5, 310.9b-d, 508.1b) --------------------------------------------------------------
def attackable(plan_state: GameState, attacker: str, defenders: list[str], ch_of: Any) -> list[str]:
    """The battles ``attacker`` may attack: their protector is one of ``defenders`` and not the
    attacker (310.9b)."""
    out = []
    for card in plan_state.cards.values():
        if not card.zone.endswith(":battlefield") or not is_battle(ch_of(card)):
            continue
        who = protector(plan_state, card)
        if who is not None and who != attacker and who in defenders:
            out.append(card.id)
    return out


# -- state-based actions (310.11, 704.5v, 704.5w) -----------------------------------------------------
def being_attacked(state: GameState, card: CardInstance) -> bool:
    return any(c.attacking is not None and c.attacking.kind != "player" and c.attacking.id == card.id
               for c in state.cards.values() if c.zone.endswith(":battlefield"))


def waiting_trigger(plan: Plan, card: CardInstance) -> bool:
    """704.5v: is this Siege the source of an ability that has triggered but not left the stack?"""
    oid = plan.oid(card)
    r = plan.rules
    seen = r.trigger_batch  # (its defeat just happened: triggered, though not collected yet, 603.2)
    return any(e.kind == "counters" and e.counter == "defense" and e.amount < 0 and e.object_id == oid and e.batch > seen
               and not e.manual for e in r.events) \
        or any(t.source_object == oid for t in r.pending_triggers) \
        or any(e.kind == "trigger" and e.source_object == oid for e in r.stack.values())


def no_defense(plan: Plan, card: CardInstance, ch: Characteristics) -> bool:
    """704.5v / 704.5w: a battle with no defense is put into its owner's graveyard (a Siege only
    once its defeat trigger has left the stack)."""
    if not is_battle(ch) or card.counters.get("defense", 0) > 0:
        return False
    return "Siege" not in ch.subtypes or not waiting_trigger(plan, card)


def protector_problem(plan: Plan, card: CardInstance, ch: Characteristics) -> list[str] | None:
    """310.11: None when the battle's protector is fine (or it's being attacked); otherwise the
    players its controller may choose from (empty: it goes to the graveyard)."""
    if not is_battle(ch) or being_attacked(plan.state, card) or plan.manual(card):
        return None
    options = candidates(plan, ch, card.controller)
    return None if protector(plan.state, card) in options else options


def ask_protector(plan: Plan, card: CardInstance, options: list[str]) -> None:
    from app.rules.plan import decide

    decide(plan, player=card.controller, kind="choose_one",
           prompt=f"{card.name or 'The battle'} has no protector: choose one (310.11)",
           options=[DecisionOption(id=p, label=plan.name(p)) for p in options],
           resume={"step": "battle_protector", "card": card.id, "object": plan.oid(card)}, source=card)


def resume_protector(plan: Plan, d: Any, chosen: list[str]) -> None:
    card = plan.state.cards.get(d.resume["card"])
    if card is not None and plan.oid(card) == d.resume["object"] and card.zone.endswith(":battlefield"):
        set_protector(plan, card, chosen[0])


# -- the Siege's defeat (310.12b) ---------------------------------------------------------------------
def defeated_triggers(plan: Plan, e: Any) -> None:
    """``triggers.collect``: defense counters were removed — "When the last defense counter is
    removed from this permanent" (310.12b) triggers for a Siege left with none."""
    from app.rules import triggers

    card = plan.state.cards.get(e.card or "")
    if card is None or not card.zone.endswith(":battlefield") or plan.oid(card) != e.object_id or plan.manual(card):
        return
    ch = plan.ch(card)
    if "Siege" not in ch.subtypes or not is_battle(ch) or card.counters.get("defense", 0) > 0:
        return
    triggers._add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                  index=DEFEATED, definition={"kind": "triggered", "trigger": "siege_defeated", "optional": False,
                                              "target": None, "effects": [{"do": "siege_defeated"}]})


def siege_defeated(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """310.12b: "exile it, then you may cast it transformed without paying its mana cost" — the
    exile, then its controller casts it by hand (casting a card transformed isn't automated)."""
    from app.rules.plan import decide

    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is None or not card.zone.endswith(":battlefield") or plan.oid(card) != ctx.get("source_object"):
        return True  # (it left: "it" is gone, 400.7)
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "exile"}}, actor=ctx["controller"])
    exiled = plan.state.cards.get(card.id)
    if exiled is None or not exiled.zone.endswith(":exile") or exiled.is_token:
        return True
    decide(plan, player=ctx["controller"], kind="manual_resolution",
           prompt=f"{card.name or 'The Siege'} was defeated: you may cast it transformed without paying its mana cost "
                  "— do it by hand from exile, then press Done (310.12b)",
           options=[DecisionOption(id="done", label="Done")], resume={"step": "siege_cast", "ctx": ctx}, source=exiled)
    return False


def resume_siege_cast(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    continue_effects(plan, d.resume["ctx"])
