"""-- granted replicate (wave 111R3) -- replicate given to the spells a player casts by a permanent's static ability (702.56a): "Artifact spells
you cast have replicate {2}{U}." (Hugh, First of Many), "Each Sliver spell you cast has replicate. The replicate cost is equal to its mana cost."
(Hatchery Sliver, Ian Chesterton, Djinn Illuminatus: wave110a_grants), "Each spell you cast that's exactly three colors has replicate {3}."
(Threefold Signal: wave110a_final).

Each grant is its own instance of replicate on the spell: 702.56b, "each is paid separately and triggers based on the payments made for it, not
any other instance of replicate" (two Hughs: two instances, two cast triggers). The payments are announced with the other additional costs
(601.2b) in their own slot, ``CastSpell.replicate``: one count per instance, in the order ``instances`` lists them (the view's
``replicate111r3`` hint), apart from the spell's own kicker / multikicker / offspring / replicate (``CastSpell.kicker``), so an artifact spell
with its own multikicker (Everflowing Chalice) pays both, and one with {X} in its mana cost is offered a replicate cost without {X} (Hugh's
{2}{U}: X is the spell's own announcement, 601.2b, and the copies copy it, 707.10). A cost "equal to its mana cost" stays unoffered for a spell
with no mana cost or with {X} in it, as before. Each count joins the total cost (601.2f) like a kicker paid that many times.

Compatibility: a cast that gives only ``kicker`` for a spell with no kicker-like cost of its own pays its first granted instance (the way
wave 110A's grants were paid). As the spell becomes cast (601.2i), each instance still on it triggers once for its own count (603.2): a
source that left the battlefield while the cost was paid (sacrificed for mana) no longer gives the spell replicate, so its payments copy
nothing (613.1f/611.3a: the static no longer applies). A cast without paying its mana cost may still pay them (118.9d): asked with its other
optional costs (``free_offers``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.game.errors import ActionError
from app.rules import mana as M

STATIC = "spell_replicate110a"  # the grants' one static kind (wave110a_grants, wave110a_final)
INDEX = 6300  # the ability index of the cast trigger of the instance i: INDEX + i (casting's own triggers use 6000-6299)
OPTION = "replicate111r3:"  # a free cast's answers: "replicate111r3:<instance>:<count>" or "replicate111r3:<instance>:other"
_KICKERS = frozenset({"kicker", "multikicker", "squad", "replicate", "offspring", "entwine"})

# 702.56a: "Artifact spells you cast have replicate {2}{U}." (Hugh, First of Many: the one printed wording; a cost with {X} isn't read)
_HAVE = re.compile(r"^(?P<sel>artifact) spells you cast have replicate (?P<cost>(?:\{[^}X]+\})+)$", re.IGNORECASE)


def definition(t: str) -> dict[str, Any] | None:
    """The static of "<kind> spells you cast have replicate {cost}" (``permissions.define_static``), or None."""
    from app.rules.permissions import spell_filter

    m = _HAVE.fullmatch(t.strip().rstrip("."))
    if m is None or (key := spell_filter(m["sel"])) is None:
        return None
    return {"kind": "static", "static": STATIC, "filter": key, "kw": f"Replicate {m['cost']}", "effects": []}


def is_replicate(d: dict[str, Any]) -> bool:
    """A grant of replicate (not wave 110A's offspring grant, which stays its own: wave110a_grants.with_replicate)."""
    return not d.get("kw") or str(d["kw"]).lower().startswith("replicate ")


@dataclass(frozen=True)
class Instance:
    source: str  # the permanent whose static gives the spell this instance (its card id)
    cost: str  # the replicate cost (mana symbols)
    label: str


def instances(state: Any, player: str, card: Any, ch: Any, info: Any, *, face_down: bool = False) -> list[Instance]:
    """The instances of replicate the statics of ``player``'s permanents give the spell ``card`` becomes (``ch``, as cast) — one per static
    (702.56b), in the order of their sources. A face-down spell has none (708.2: it has no types the grants name)."""
    from app.rules import cast_limits
    from app.rules.permissions import spell_matches

    if face_down or getattr(ch, "face_down", False) or info is None:
        return []
    out: list[Instance] = []
    for src, d in sorted(cast_limits._statics(state, info, STATIC), key=lambda found: found[0].id):
        if src.controller != player or not is_replicate(d):
            continue
        cost = str(d["kw"]).split(" ", 1)[1] if d.get("kw") else ch.mana_cost  # (Hatchery Sliver: "equal to its mana cost")
        if not cost or "{X}" in cost.upper() or M.parse_cost(cost).unsupported:
            continue
        if not spell_matches(state, player, card, ch, d["filter"], info, src.id):
            continue
        out.append(Instance(src.id, cost, f"Replicate {cost} ({src.name or 'a permanent'})"))
    return out


def times(cost: str, n: int) -> M.ManaCost:
    """The replicate cost paid ``n`` times (601.2f: added to the total cost, as kicker is: casting.kicker_extra)."""
    one = M.parse_cost(cost)
    return M.ManaCost(one.generic * n, one.colored * n, one.hybrid * n, one.phyrexian * n, 0, one.unsupported * n)


def own_kicker(ch: Any) -> bool:
    """Has the spell a kicker-like cost of its own (paid through ``CastSpell.kicker``)?"""
    from app.rules.costs import kicker_cost

    return kicker_cost(ch.abilities) is not None or any(ab.kind == "keywords" and _KICKERS & set(ab.keywords) for ab in ch.abilities)


def announce(plan: Any, a: Any, card: Any, ch: Any, *, legacy: bool = True) -> tuple[list[M.ManaCost], list[tuple[str, int]]]:
    """601.2b: the cast's replicate payments, checked against the instances its spell has now: their mana (601.2f) and the announcement
    [(source, count)] the cast trigger reads. ``legacy``: a lone ``kicker`` count pays the first instance of a spell without a kicker-like
    cost of its own (the intent is changed: the count moves to ``replicate``)."""
    found = instances(plan.state, plan.actor, card, ch, plan.info, face_down=bool(getattr(a, "face_down", False)))
    if legacy and a.kicker and not a.replicate and found and not own_kicker(ch):
        a.replicate, a.kicker = [a.kicker], 0  # (also a payment saved before wave 111R, resumed with its cost locked: its count is read the same way)
    if plan.locked_cost is not None and len(a.replicate_from) == len(a.replicate):
        # 601.2f-h: the payment of this cast resumed after its total cost was locked in (a mana ability was activated meanwhile): the
        # announcement stands, even if the permanent that gave an instance has left since (a creature sacrificed for mana: cast_triggers)
        costs = {inst.source: inst.cost for inst in found}
        announced = [(source, n) for source, n in zip(a.replicate_from, a.replicate, strict=True) if n]
        return [times(costs[source], n) for source, n in announced if source in costs], announced
    if any(n < 0 or n > 1000 for n in a.replicate):
        raise ActionError("Pay each replicate cost 0 to 1000 times (platform numeric range)")
    if any(a.replicate[len(found):]):
        raise ActionError(f"{ch.name or 'That spell'} has {len(found) or 'no'} replicate cost{'s' if len(found) != 1 else ''} given to it to pay")
    a.replicate = list(a.replicate[:len(found)])
    a.replicate_from = [inst.source for inst in found[:len(a.replicate)]]
    paid = [(inst, n) for inst, n in zip(found, a.replicate, strict=False) if n]
    return [times(inst.cost, n) for inst, n in paid], [(inst.source, n) for inst, n in paid]


def cast_triggers(plan: Any, card: Any, ch: Any, announced: list[tuple[str, int]] | None) -> None:
    """702.56a-b, 601.2i: "When you cast this spell, if a replicate cost was paid for it, copy it for each time its replicate cost was paid."
    — one trigger per instance still on the spell, for that instance's own payments (the copies: casting's storm copy, 707.10)."""
    from app.rules.triggers import _add

    if not announced:
        return
    left = [inst.source for inst in instances(plan.state, plan.actor, card, ch, plan.info)]
    for i, (source, n) in enumerate(announced):
        if source not in left:
            plan.note(f"{ch.name}: the permanent that gave it replicate is gone, so its replicate payment copies nothing (702.56a)", [card.id])
            continue
        left.remove(source)
        _add(plan, controller=plan.actor, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=INDEX + i,
             definition={"kind": "triggered", "trigger": "storm", "optional": False, "target": None,
                         "effects": [{"do": "storm", "spell": card.id, "object": plan.oid(card), "n": n, "label": "Replicate"}]})


def tags(announced: list[tuple[str, int]] | None) -> list[str]:
    """The stack tags of the payments ("Replicate paid ×2")."""
    return [f"Replicate paid ×{n}" for _, n in announced or ()]


# -- a cast without paying its mana cost (118.9d): offered with its other optional additional costs (casting.free_optional_offers) --
def free_offers(plan: Any, card: Any, ch: Any, payable: Any, quick: int) -> list[tuple[str, str]]:
    """The answers of the free cast's optional-cost question for these instances: each count from 1 that ``payable(mana)`` still pays (up to
    ``quick``), and a typed count."""
    out: list[tuple[str, str]] = []
    for i, inst in enumerate(instances(plan.state, plan.actor, card, ch, plan.info)):
        for n in range(1, quick + 1):
            if not payable(times(inst.cost, n)):
                break
            out.append((f"{OPTION}{i}:{n}", inst.label if n == 1 else f"{inst.label}, paid {n} times"))
        out.append((f"{OPTION}{i}:other", f"{inst.label}: another count (0–1000)"))
    return out


def take_answers(intent: Any, chosen: list[str]) -> int | None:
    """Read the free cast's replicate answers into ``intent.replicate``; the instance whose count is still to be typed, or None."""
    picked: dict[int, str] = {}
    for c in chosen:
        if not c.startswith(OPTION):
            continue
        index, count = c[len(OPTION):].split(":", 1)
        if not index.isdigit() or int(index) in picked or not (count.isdigit() or count == "other"):
            raise ActionError("Pay each replicate cost one number of times")
        picked[int(index)] = count
    if not picked:
        return None
    counts = [0] * (max(picked) + 1)
    typed = [i for i, n in picked.items() if n == "other"]
    if len(typed) > 1:
        raise ActionError("Choose a typed count for one replicate cost at a time")
    for i, n in picked.items():
        counts[i] = int(n) if n.isdigit() else 0
    intent.replicate = counts
    return typed[0] if typed else None


def ask_count(plan: Any, d: Any, intent: Any, index: int) -> None:
    """The typed count of one instance (platform range 0–1000)."""
    from app.game.rules_state import DecisionOption
    from app.rules.casting import _announcing
    from app.rules.plan import decide

    decide(plan, player=d.player, kind="choose_one", prompt="Choose how many times to pay that replicate cost (platform range 0–1000)",
           options=[DecisionOption(id="__number__", label="Replicate count: 0–1000")],
           resume={**_announcing(plan, "free_replicate111r3", intent, card_object=plan.oid(intent.card_id)), "index": index},
           source=plan.state.cards[intent.card_id])


def resume_free_count(plan: Any, d: Any, chosen: list[str]) -> None:
    """A typed count continues the same native cast; all actual costs remain payable normally."""
    from app.game import actions as A
    from app.rules.engine import INTENTS

    count = int(chosen[0])
    if not 0 <= count <= 1000:
        raise ActionError("Choose a replicate count from 0 to 1000 (platform numeric range)")
    intent = A.parse_action(d.resume["intent"])
    assert isinstance(intent, A.CastSpell)
    if plan.oid(intent.card_id) != d.resume["card_object"]:
        raise ActionError("That spell is a different object now")
    index = int(d.resume["index"])
    counts = list(intent.replicate) + [0] * max(0, index + 1 - len(intent.replicate))
    counts[index] = count
    intent.replicate = counts
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def hint(state: Any, player: str, card: Any, info: Any) -> list[str]:
    """The view's ``replicate111r3`` hint of a castable card: the labels of its instances, in ``CastSpell.replicate``'s order."""
    from app.rules import characteristics as chars

    return [inst.label for inst in instances(state, player, card, chars.of(card, info), info)]
