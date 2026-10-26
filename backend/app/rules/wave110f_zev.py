"""Zevlor, Elturel Exile (wave 110F): "{2}, {T}: When you next cast an instant or sorcery spell that targets only a single opponent or a single permanent an opponent
controls this turn, for each other opponent, choose that player or a permanent they control, copy that spell, and the copy targets the chosen player or permanent."

603.7: the ability creates a delayed triggered ability that watches this turn for the next such spell (the cast condition is checked as the spell is cast, 115.9b-c:
exactly one object or player is chosen). 707.10: the copies are made as the trigger resolves; "each other opponent" is each opponent of the caster other than the
player who was targeted, or who controls the targeted permanent. The caster chooses, per such opponent, among that player and the permanents they control that are legal
targets of the spell (115.1, 601.2c / 707.10c: a copy cannot target something the spell could not); an opponent with no legal choice gets no copy
(Scryfall ruling 2022-06-10: "if the chosen player or permanent isn't a legal target for the spell, the copy won't be created"; the same ruling: copies are
not cast, X and modes are copied, no additional costs are paid)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game.rules_state import DecisionOption

TEXT = ("When you next cast an instant or sorcery spell that targets only a single opponent or a single permanent an opponent controls this turn, "
        "for each other opponent, choose that player or a permanent they control, copy that spell, and the copy targets the chosen player or permanent.")
WANT = "only_opp110f"


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != "activated" or not scripts.self_text(ability.text, ch.name).endswith(": " + TEXT):
        return None
    cost = ability.text.split(":", 1)[0]
    d = scripts.define(replace(ability, text=f"{cost}: Draw a card."), ch)
    return None if d is None else {**d, "effects": [{"do": "zevlor110f"}]}


def targets_ok(plan: Any, watcher: Any, targets: list[tuple[str, str | None]]) -> bool:
    """115.9c: exactly one object or player is chosen (however many times) and it is an opponent or a permanent an opponent controls."""
    if len({c for c, _ in targets}) != 1:
        return False
    cid, oid = targets[0]
    if cid in plan.state.players:
        return cid != watcher.controller
    card = plan.state.cards.get(cid)
    return card is not None and (oid is None or plan.oid(card) == oid) and card.zone.endswith(":battlefield") and card.controller != watcher.controller


def watch(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import delayed, events

    cond = events.parse_condition("you cast an instant or sorcery spell")
    assert cond is not None
    out = delayed.wrap_when([{"do": "zevlor_copies110f"}], {"kind": "watch", "cond": {**cond, "targets": WANT}, "text": "you next cast a matching spell"}, this_turn=True)
    out[0]["once"] = True
    ctx["effects"][ctx["next"]:ctx["next"]] = out
    return True


def copies(plan: Any, ctx: dict[str, Any], e: dict[str, Any], st: dict[str, Any] | None = None) -> bool:
    from app.rules import copying, spell_copy_replacements, targets
    from app.rules.plan import live_players

    if st is None:
        found = next(iter(copying._copy_sources(plan, ctx, "event_spell")), None)
        card = plan.state.cards.get(found[0]) if found else None
        entry = copying.source_entry102(plan, card, found[1]) if card is not None and found else None
        if found is None or card is None or entry is None or not copying.positions(entry) or copying.uncopyable(plan, card, object_id=found[1]) is not None:
            return True
        first = entry.targets[0].id
        taken = first if first in plan.state.players else (plan.state.cards[first].controller if first in plan.state.cards else None)
        caster = entry.controller
        st = {"spell": found[0], "oid": found[1], "caster": caster, "todo": [p for p in live_players(plan.state) if p != caster and p != taken], "victims": []}
    card = plan.state.cards.get(st["spell"])
    entry = copying.source_entry102(plan, card, st["oid"]) if card is not None else None
    if card is None or entry is None:
        return True
    positions = copying.positions(entry)
    source_ch = targets.source_of(plan, st["spell"], True, object_id=st["oid"])
    while st["todo"]:
        opp = st["todo"][0]
        legal = [opp, *(c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == opp)]
        legal = [t for t in legal if all(t in targets.legal_targets(plan, copying._spec(entry, p).get("what", "any"), st["caster"], source_ch, st["spell"],
                                                                     source_object=st["oid"]) for p in positions)]
        if len(legal) > 1:
            from app.rules.plan import decide

            decide(plan, player=st["caster"], kind="choose_one", prompt=f"Zevlor: choose {plan.name(opp)} or a permanent they control for the copy",
                   options=[DecisionOption(id=t, label=targets.label(plan, t), card_id=t if t in plan.state.cards else None) for t in legal],
                   resume={"step": "zevlor110f", "ctx": ctx, "e": e, "st": st})
            return False
        st["todo"].pop(0)
        st["victims"] += legal
    if not st["victims"]:
        return True
    return copying._each_run(plan, {"ctx": ctx, "spell": st["spell"], "oid": st["oid"], "controller": ctx["controller"], "victims": st["victims"],
                                    "additional": spell_copy_replacements.additional(plan, ctx["controller"])})


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    st = d.resume["st"]
    st["todo"].pop(0)
    st["victims"].append(chosen[0])
    if copies(plan, d.resume["ctx"], d.resume["e"], st):
        effects.continue_effects(plan, d.resume["ctx"])


PRIMITIVES = {"zevlor110f": watch, "zevlor_copies110f": copies}
RESUME = {"zevlor110f": resume}
