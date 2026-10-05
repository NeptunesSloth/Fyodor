"""Attachments: Auras, Equipment, Fortifications (CR 301.5, 301.6, 303.4, 701.3, 702.5, 702.6).

One model for everything that attaches. An attachment is a permanent (the *source*) attached to
an object or player (the *host*): ``CardInstance.attached_to`` (a permanent) or
``CardInstance.attached_player`` (an Aura with "Enchant player", 702.5d). What may be attached
where is decided by one predicate, :func:`host_problem`, used everywhere:

* casting an Aura spell targets a host its enchant ability allows (303.4a; targeting rules —
  hexproof, shroud, protection — apply because it *targets*), rechecked on resolution (608.2b);
* an Aura put onto the battlefield without being cast doesn't target: its controller chooses a
  host the Aura could enchant (303.4f); with none it stays where it was (303.4g);
* equip targets a creature you control and attaches on resolution (702.6a);
* state-based actions (704.5m / 704.5n, app/rules/sba.py) remove what is no longer legal.

Continuous effects of attachments ("Enchanted creature gets +2/+2", "Equipped creature has
flying", "Enchanted creature can't block") are derived through the relationship each time
(app/rules/layers.py), so they end the moment the source leaves or moves.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal

from app.game.rules_state import DecisionOption
from app.game.state import CardInstance
from app.rules import protection
from app.rules.characteristics import Characteristics

if TYPE_CHECKING:
    from app.rules.plan import Plan

AttachKind = Literal["aura", "equipment", "fortification"]

# "Enchant …" → the target selector (app/rules/targets.py) the Aura spell uses and hosts must match.
ENCHANT_SELECTORS = {
    "creature": "creature",
    "creature you control": "creature_you_control",
    "creature an opponent controls": "creature_opponent_controls",
    "creature you don't control": "creature_opponent_controls",
    "land": "land",
    "land you control": "land_you_control",
    "artifact": "artifact",
    "artifact you control": "artifact_you_control",
    "enchantment": "enchantment",
    "permanent": "permanent",
    "nonland permanent": "nonland_permanent",
    "planeswalker": "planeswalker",
    "creature or planeswalker": "creature_or_planeswalker",
    "artifact or creature": "artifact_or_creature",
    "player": "player",
    "opponent": "opponent",
}
PLAYER_SELECTORS = {"player", "opponent"}

_ENCHANT = re.compile(r"^enchant (?P<what>.+?)\.?$", re.IGNORECASE)
# -- equip (wave 15E) -- 702.6a "Equip [cost]", "Equip [quality] [cost]" (702.6b: only a creature with that quality) and
# "Equip—[non-mana cost]": the cost, the target selector and the ability's own trailing sentences ("Activate only once each
# turn.", "This ability costs {3} less to activate if …")
EQUIP = re.compile(r"^equip(?: (?P<q>[A-Za-z][A-Za-z' -]*?))? (?P<cost>(?:\{[^}]+\})+)(?P<tail>(?:\. .+|\.)?)$|"
                   r"^equip—(?P<cost2>[^.]+)(?P<tail2>\..*)?$", re.IGNORECASE)


def attach_kind(ch: Characteristics) -> AttachKind | None:
    if "Aura" in ch.subtypes:
        return "aura"
    if "Equipment" in ch.subtypes:
        return "equipment"
    if "Fortification" in ch.subtypes:
        return "fortification"
    return None


def enchant_lines(ch: Characteristics) -> list[str]:
    return [ab.text for ab in ch.abilities if ab.kind == "keywords" and "enchant" in ab.keywords]


def enchant_selector_of(line: str) -> str | None:
    m = _ENCHANT.match(re.sub(r"\s*\(.*?\)", "", line).strip())
    if m is None:
        return None
    what = m["what"].strip().replace("’", "'")
    if what.lower() in ENCHANT_SELECTORS:
        return ENCHANT_SELECTORS[what.lower()]
    # -- keywords (wave 15E) -- 702.5a: any object description the selector grammar reads ("Enchant tapped creature",
    # "Enchant red or green creature", "Enchant Forest or Plains", "Enchant artifact an opponent controls")
    from app.rules import selectors

    sel = selectors.parse(what)
    if sel is None or sel.card or sel.zones != ("battlefield",) or sel.player is not None:
        return None
    return sel.key()


def enchant_selector(ch: Characteristics) -> str | None:
    """The selector an Aura targets with and its hosts must match, or None if its enchant ability
    isn't automated (several different enchant abilities must all apply, 702.5c: left manual)."""
    lines = enchant_lines(ch)
    if not lines or "Aura" not in ch.subtypes:
        return None
    found = {enchant_selector_of(line) for line in lines}
    return found.pop() if len(found) == 1 and None not in found else None


def _equip_target(q: str | None) -> str | None:
    """The selector key of "target creature you control" narrowed by an equip quality ("legendary creature", "Knight",
    "creature token", "commander"), or None when the quality isn't read."""
    from app.rules import selectors

    if q is None:
        return "creature_you_control"
    for phrase in (f"{q} you control", f"{q} creature you control", f"creature you control that's a {q}"):
        sel = selectors.parse(phrase)
        if sel is not None and sel.player is None and not sel.card and ("Creature" in sel.types or sel.subtypes) \
                and sel.zones == ("battlefield",):
            return sel.key()
    return None


def equip_info(line: str, name: str = "") -> tuple[str, str, str] | None:
    """(cost, target selector, trailing sentences) of an equip line the engine carries out, or None."""
    from app.rules import cost_changes, restrictions
    from app.rules.costs import parse_ability_cost

    m = EQUIP.match(re.sub(r"\s*\(.*?\)", "", line).strip())
    if m is None:
        return None
    cost, tail = (m["cost"], m["tail"]) if m["cost"] else (m["cost2"].strip(), m["tail2"] or "")
    tail = tail.strip().lstrip(".").strip()
    target = _equip_target(m["q"] if m["cost"] else None)
    if target is None or (not m["cost"] and parse_ability_cost(cost, card_name=name).unsupported):
        return None
    if tail:
        text = f"{cost}: Attach ~ to target creature you control. Activate only as a sorcery. {tail}"
        if restrictions.parse(text) is None or cost_changes.ability_change(text) is None:
            return None
        if cost_changes.split_ability(text.split(":", 1)[1])[1] is not None and "{" not in cost:
            return None  # (a reduction of a cost with no mana in it)
    return cost, target, tail


def is_equip_text(text: str) -> bool:
    """Is this the text casting.equip_ability gives an equip ability (702.6a: "[Cost]: Attach … to target creature you control.
    Activate only as a sorcery.")?"""
    return re.search(r": Attach .+? to target creature you control\. Activate only as a sorcery\.", text) is not None


def equip_cost(ch: Characteristics, index: int) -> tuple[str, str, str] | None:
    """The equip ability on ability line ``index`` (702.6a): (cost, target selector, trailing sentences), or None."""
    for ab in ch.abilities:
        if ab.index == index and ab.kind == "keywords" and "equip" in ab.keywords:
            return equip_info(ab.text, ch.name)
    return None


def supported_keyword(kw: str, line: str) -> bool:
    if kw == "enchant":
        return enchant_selector_of(line) is not None
    if kw == "equip":
        return equip_info(line) is not None
    return False


# -- the legality predicate ------------------------------------------------------------
def host_problem(plan: Plan, source: CardInstance, host: str, controller: str | None = None) -> str | None:
    """Why ``source`` can't be attached to ``host`` (a card id or a player id) right now, or None
    if it can. For an Aura with an enchant wording the engine doesn't map, "unknown" (never
    remove an Aura on a guess). Targeting rules (hexproof, shroud) don't apply here: being
    attached isn't being targeted; protection does (702.16c-d)."""
    from app.rules.targets import SELECTORS

    you = controller or source.controller  # (an Aura about to enter under someone: judged as theirs)
    sch = plan.ch(source)
    kind = attach_kind(sch)
    if kind is None:
        return "not an Aura, Equipment or Fortification"
    if host == source.id:
        return "it can't be attached to itself"  # 301.5c, 303.4d
    if host in plan.state.players:
        if kind != "aura":
            return "only an Aura can be attached to a player"
        selector = enchant_selector(sch)
        if selector is None:
            return "unknown"
        if host not in plan.live():
            return "that player left the game"  # 303.4c
        if selector not in PLAYER_SELECTORS:
            return "it can't enchant a player"  # (a described host, wave 15E, is a permanent)
        if selector == "opponent" and host == you:
            return "it can only enchant an opponent"
        # -- player shields (wave 5E) -- 702.16c, 702.16j
        from app.rules import player_shields

        if (shield := player_shields.protected_from(plan, host, sch)) is not None:
            return f"{plan.name(host)} has protection from it ({shield})"
        return None
    card = plan.state.cards.get(host)
    if card is None or not card.zone.endswith(":battlefield"):
        return "it's not on the battlefield"
    hch = plan.ch(card)
    if protection.protected_from(hch, sch):
        return f"{hch.name} has protection from it"
    if kind == "aura":
        if sch.is_creature:
            return "an Aura that's also a creature can't enchant anything"  # 303.4d
        selector = enchant_selector(sch)
        if selector is None:
            return "unknown"
        if selector.startswith("sel:"):  # (wave 15E) a described host, judged for the Aura's controller
            from app.rules import selectors

            if not selectors.matches(plan, selectors.from_key(selector), card, hch, you, source.id):
                return f"it can't enchant {hch.name or 'that'}"
            return None
        players, check = SELECTORS[selector]
        if check is None or not check(plan, you, card, hch):
            return f"it can't enchant {hch.name or 'that'}"
        return None
    if kind == "equipment":
        if sch.is_creature and "reconfigure" not in sch.keywords:  # (301.5c; 702.151: reconfigure, wave 18E)
            return "an Equipment that's also a creature can't equip"
        return None if hch.is_creature else "Equipment can only equip a creature"
    if sch.is_creature:
        return "a Fortification that's also a creature can't fortify"  # 301.6
    return None if hch.is_land else "a Fortification can only fortify a land"


def legal_hosts(plan: Plan, source: CardInstance, controller: str | None = None) -> list[str]:
    """Everything ``source`` could be attached to right now (no targeting involved)."""
    out = [p for p in plan.live() if host_problem(plan, source, p, controller) is None]
    for c in plan.state.cards.values():
        if c.zone.endswith(":battlefield") and c.id != source.id and host_problem(plan, source, c.id, controller) is None:
            out.append(c.id)
    return out


def attach(plan: Plan, source: str, host: str, actor: str) -> bool:
    """701.3a-b: attach ``source`` to ``host`` if it can be; otherwise it doesn't move."""
    card = plan.state.cards.get(source)
    if card is None or host_problem(plan, card, host) is not None:
        return False
    if card.attached_to == host or card.attached_player == host:
        return True  # already there: nothing happens (701.3b)
    plan.do({"type": "attach", "card_ids": [source], "to": host}, actor=actor)
    return True


# -- putting permanents onto the battlefield (an Aura chooses its host, 303.4f-g) ------------
def enter(plan: Plan, entries: list[dict[str, Any]], ctx: dict[str, Any] | None, *, shuffle: str | None = None) -> bool:
    """Put cards onto the battlefield together (each entry: card, player, actor, tapped): one event
    (603.6a), every choice made before any of them enters (614.12a) — "As ~ enters" choices, and
    what an Aura that isn't being cast enchants (303.4f: something its controller chooses that it
    could enchant; with nothing to enchant it stays in its zone, 303.4g) — then they enter at once
    (``replacements.move_together``: 614.12, 613.7m). Returns False while waiting for a choice (the
    rest continue on resume, then ``shuffle``'s library is shuffled — "put it onto the battlefield,
    then shuffle" — and ``ctx``'s effects go on)."""
    from app.rules import characteristics as chars
    from app.rules import copying, replacements

    for back in (e for e in entries if e.get("to") == "hand"):  # -- resolution memory (wave 22D) -- 610.3: exiled from a hand, returns there
        plan.do({"type": "move", "card_ids": [back["card"]], "to": {"player": back["player"], "zone": "hand"}}, actor=back["actor"])
    entries = [dict(e) for e in entries if e.get("to") != "hand"]
    for i, entry in enumerate(entries):
        card = plan.state.cards.get(entry["card"])
        if card is not None and entry.get("transformed") and not chars.transformable(card, plan.info):
            entry["stays"] = True  # -- transform (wave 11A) -- 712.14a: a card that isn't a double-faced card stays where it is
        if card is None or entry.get("stays"):
            continue
        # -- prohibitions (wave 22B) -- 614.17: "Creature cards in graveyards and libraries can't enter the battlefield."
        from app.rules import prohibitions

        if (barred := prohibitions.cant_enter(plan, card, entry["player"])) is not None:
            if barred[1]:  # (a card in a hidden zone stays silently: a note would show that one was found)
                plan.note(f"{barred[0]}: a card can't enter the battlefield", [card.id])
            entry["stays"] = True
            continue
        # -- entering for a cost (wave 5G) -- what it may pay with: not one entering with it, nor one another of them
        # chose (614.13a-b)
        from app.rules import enter_cost

        entry["reserved"] = sorted({str(e["card"]) for e in entries if e is not entry} | enter_cost.chosen_objects(entries, i))
        if replacements.choice_needed(plan, card, entry) is not None:
            # a shock land: "As ~ enters, you may pay 2 life" is decided before it enters (614.12a)
            replacements.ask_entry_choice(plan, entries, i, ctx, shuffle)
            return False
        # -- enter as copy (wave 5F) -- as it will enter: a permanent entering as a copy of an Aura is one (707.5, 303.4f)
        if attach_kind(plan.ch(card) if copying.entering_as_copy(plan, card) else chars.of(card, plan.info)) != "aura" \
                or entry.get("host"):
            continue
        hosts = _hosts_on_entering(plan, card, entry["player"])
        if not hosts:
            # (no name in the text: the card may still be in a hidden zone; card_ids lets the log
            # name it only to players who can see it)
            plan.note("The Aura has nothing it could enchant: it stays where it is", [card.id])
            entry["stays"] = True
        elif len(hosts) == 1:
            entry["host"] = hosts[0]
        else:
            from app.rules.plan import decide
            from app.rules.targets import label

            decide(plan, player=entry["player"], kind="choose_one", prompt="Choose what the Aura enchants",  # (not named: it may come from a hidden zone)
                   options=[DecisionOption(id=h, label=label(plan, h), card_id=h if h in plan.state.cards else None)
                            for h in hosts],
                   resume={"step": "aura_enters", "entries": entries, "index": i, "ctx": ctx, "shuffle": shuffle},
                   source=card)
            return False
    entering = [e for e in entries if not e.get("stays")]
    replacements.move_together(plan, entering)
    for entry in entering:
        if entry.get("host"):  # it enters attached to what was chosen (303.4f)
            attach(plan, entry["card"], entry["host"], entry["actor"])
    return True


def _hosts_on_entering(plan: Plan, card: CardInstance, controller: str) -> list[str]:
    """What an Aura entering under ``controller`` could enchant (the permanents already on the
    battlefield: not one entering with it)."""
    return legal_hosts(plan, card, controller)


def resume_aura_enters(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects
    from app.rules.replacements import resume_entries

    entries, i = resume_entries(d.resume)
    ctx, shuffle = d.resume.get("ctx"), d.resume.get("shuffle")
    card = plan.state.cards.get(entries[i]["card"])
    if card is not None:
        if chosen[0] not in _hosts_on_entering(plan, card, entries[i]["player"]):
            from app.game.errors import ActionError

            raise ActionError("It can't enchant that")
        entries[i] = {**entries[i], "host": chosen[0]}
    if not enter(plan, entries, ctx, shuffle=shuffle):
        return  # another Aura is choosing
    if shuffle:
        plan.do({"type": "shuffle", "player": shuffle, "zone": "library"}, actor=shuffle)
    if ctx is not None:
        continue_effects(plan, ctx)
