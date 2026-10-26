"""-- chosen objects (wave 110A) -- "As ~ enters, choose another creature you control." (Dauntless Bodyguard, Tyrannical Pitlord).

614.12a / 614.1c: the choice is made as the permanent enters, by its controller, and is public. The chosen object is remembered by its
object id (``RulesState.chosen_objects``: source card id -> chosen object id), so "the chosen creature" is only that same object: if it
left the battlefield and came back it is a new object (400.7) and no longer the chosen one. The memory is kept by card id after the source
leaves, so a leaves-the-battlefield ability or a sacrifice cost still finds it (608.2h); the source entering again chooses anew.
Read by the selector word "chosen" (selectors: extra ``picked110a``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

WHAT = "pick110a"
TEXTS = {"As ~ enters, choose another creature you control.": "other creature you control",
         "As ~ enters, choose a creature.": "creature",  # Metamorphic Alteration (wave110a_chosen)
         # -- enters attached (wave 110I) -- 303.4f / 301.5: chosen as it enters, so it enters attached to it
         "As ~ enters, choose a creature you control it could be attached to. If you do, it enters attached to that creature.": "creature you control"}
LABEL = "Chosen creature"
PAIR = "As ~ enters, choose two players."  # Sower of Discord: one answer "p1,p2", kept in chosen_objects[source] (public, 614.12a)
PAIR_LABEL = "Chosen players"
SIDE = "As ~ enters, choose left or right."  # Pramikon: answer "left"/"right", kept in chosen_objects[source]


def definition(text: str) -> dict[str, Any] | None:
    if text in (PAIR, SIDE):
        return {"kind": "replacement", "replacement": "enters_choice",
                "effects": [{"do": "choose_value", "who": "you", "what": WHAT, "pick110a": "players2" if text == PAIR else "side"}]}
    if (phrase := TEXTS.get(text)) is None:
        return None
    from app.rules import selectors

    sel = selectors.parse(phrase)
    assert sel is not None, phrase
    return {"kind": "replacement", "replacement": "enters_choice",
            "effects": [{"do": "choose_value", "who": "you", "what": WHAT, "pick110a": sel.key(), **({"attach110i": True} if "attached" in text else {})}]}


def prompt(plan: Plan, card: CardInstance, controller: str, choice: dict[str, Any]) -> tuple[str, list[DecisionOption]]:
    from app.rules import selectors

    if choice["pick110a"] == "side":
        return f"{plan.ch(card).name or card.name}: as it enters, choose left or right", [DecisionOption(id=v, label=v.capitalize()) for v in ("left", "right")]
    if choice["pick110a"] == "players2":
        live = plan.live()
        return (f"{plan.ch(card).name or card.name}: as it enters, choose two players",
                [DecisionOption(id=f"{a},{b}", label=f"{plan.name(a)} and {plan.name(b)}") for i, a in enumerate(live) for b in live[i + 1:]])
    sel = selectors.from_key(choice["pick110a"])
    ids = selectors.candidates(plan, sel, controller, card.id)
    if choice.get("attach110i"):  # "it could be attached to": a legal host (protection, Equipment rules)
        from app.rules import attachments

        ids = [c for c in ids if attachments.host_problem(plan, card, c) is None]
    if choice.get("what") == "exile110o":  # -- (wave 110O) -- Living Lore
        return (f"{plan.ch(card).name or card.name}: as it enters, exile an instant or sorcery card from your graveyard",
                [DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in ids])
    return (f"{plan.ch(card).name or card.name}: as it enters, choose {'another' if sel.other else 'a'} creature{' you control' if sel.controller else ''}",
            [DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in ids])


def record(plan: Plan, card_id: str, choices: dict[str, str] | None) -> None:
    """after_entry: remember the object chosen as it entered (none left to choose: nothing is chosen)."""
    if choices is None or WHAT not in choices:
        return
    value, rules = choices[WHAT], plan.rules
    if value in ("left", "right"):  # 508.1d via combat_teyo66: each player may attack only the nearest opponent that way, while the source stays
        from app.rules import combat_teyo66, layers, selectors

        rules.chosen_objects[card_id] = value
        plan.do({"type": "set_choice", "card_id": card_id, "key": "Chosen direction", "value": value.capitalize()}, actor=plan.state.cards[card_id].controller)
        layers.add_effect(plan, affected=[], layer="6", source=plan.oid(card_id), controller=plan.state.cards[card_id].controller,
                          who=selectors.Selector(types=("Creature",)).key(), source_card=card_id, imposes=(combat_teyo66.FIXED + value,),
                          duration="source_on_battlefield", label="Attacks only " + value)  # type: ignore[arg-type]
        return
    if "," in value:  # two players
        rules.chosen_objects[card_id] = value
        plan.do({"type": "set_choice", "card_id": card_id, "key": PAIR_LABEL, "value": " and ".join(plan.name(p) for p in value.split(","))},
                actor=plan.state.cards[card_id].controller)
        return
    if value in plan.state.cards:
        rules.chosen_objects[card_id] = plan.oid(plan.state.cards[value])
        plan.do({"type": "set_choice", "card_id": card_id, "key": LABEL, "value": plan.state.cards[value].name}, actor=plan.state.cards[card_id].controller)
        if any("it enters attached to that creature" in ab.text for ab in plan.ch(plan.state.cards[card_id]).abilities):  # -- wave 110I --
            from app.rules import attachments

            attachments.attach(plan, card_id, value, plan.state.cards[card_id].controller)  # 303.4f
    else:
        rules.chosen_objects.pop(card_id, None)


def is_picked(plan: Plan, card: CardInstance, source: str | None) -> bool:
    """Is ``card`` the permanent the source chose as it entered?"""
    return source is not None and card.zone.endswith(":battlefield") and plan.rules.chosen_objects.get(source) == plan.oid(card)


def pair(plan: Plan, card_id: str) -> list[str]:
    """The two players the source chose as it entered (none: it chose no players)."""
    v = plan.rules.chosen_objects.get(card_id, "")
    return v.split(",") if "," in v else []
