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
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Literal

from app.game.rules_state import DecisionOption
from app.game.state import CardInstance, zone_key
from app.rules import protection, wave110e_blade
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
# -- reanimation Auras (wave 51F) -- "Enchant creature card in a graveyard" (Animate Dead: the Aura spell targets that card, 303.4a, 115.1b) and, once its enters
# trigger swaps it, "enchant creature put onto the battlefield with this Aura" (only what that Aura put there: ``RulesState.aura_links``, app/rules/reanimate_auras.py)
GRAVE = 'sel:{"card":true,"types":["Creature"],"zones":["graveyard"]}'
GRAVE_INSTANT = 'sel:{"card":true,"types":["Instant"],"zones":["graveyard"]}'  # -- (wave 110G) -- Spellweaver Volute: the same graveyard-card hosting for "Enchant instant card in a graveyard"
PUT_WITH = "put_with"
_PUT_WITH = re.compile(r"^creature put onto the battlefield with .+$", re.IGNORECASE)

_ENCHANT = re.compile(r"^enchant (?P<what>.+?)\.?$", re.IGNORECASE)
# -- equip (wave 15E) -- 702.6a "Equip [cost]", "Equip [quality] [cost]" (702.6b: only a creature with that quality) and
# "Equip—[non-mana cost]": the cost, the target selector and the ability's own trailing sentences ("Activate only once each
# turn.", "This ability costs {3} less to activate if …")
EQUIP = re.compile(r"^equip(?: (?P<q>[A-Za-z][A-Za-z' ,-]*?))? (?P<cost>(?:\{[^}]+\})+(?: or (?:\{[^}]+\})+)?)(?P<tail>(?:\. .+|\.)?)$|"
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
    if what.lower() == "creature card in a graveyard":  # -- reanimation Auras (wave 51F) --
        return GRAVE
    if what.lower() == "instant card in a graveyard":  # -- (wave 110G) --
        return GRAVE_INSTANT
    if _PUT_WITH.match(what):
        return PUT_WITH
    # -- keywords (wave 15E) -- 702.5a: any object description the selector grammar reads ("Enchant tapped creature",
    # "Enchant red or green creature", "Enchant Forest or Plains", "Enchant artifact an opponent controls")
    from app.rules import selectors

    if what.lower() == "artifact or non-aura enchantment":
        # Each branch keeps its own Aura exclusion; an artifact Aura remains legal.
        artifact = selectors.Selector(types=("Artifact",))
        non_aura = selectors.Selector(types=("Enchantment",), not_subtypes=("Aura",))
        return selectors.Selector(either=(artifact.key(), non_aura.key())).key()
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
    if q.lower() == "planeswalker":  # Luxior's equip planeswalker, 702.6
        selected = selectors.parse("planeswalker you control")
        assert selected is not None
        return selected.key()
    if q.lower() == "worthy":  # -- equip (wave 110D) -- Mjölnir's reminder: worthy = a legendary non-Villain creature that's red and/or white
        q = "legendary non-Villain red or white creature"
    for phrase in (f"{q} you control", f"{q} creature you control", f"creature you control that's a {q}"):
        sel = selectors.parse(phrase)
        if sel is not None and sel.player is None and not sel.card and ("Creature" in sel.types or sel.subtypes) \
                and sel.zones == ("battlefield",):
            return sel.key()
    return None


def equip_sides(cost: str) -> list[str]:
    """-- cast keywords (wave 43D) -- 702.6a: an equip cost written "{2} or {B}" or "Pay {3} or discard a card" is a choice of the cost to pay as the ability
    is activated (601.2b): its sides, each a cost on its own ("Pay {3}" is "{3}"); one side for any other cost."""
    sides = [p.strip() for p in re.split(r" or (?![^{]*\})", cost.strip())]
    return [re.sub(r"^[Pp]ay ((?:\{[^}]+\})+)$", r"\1", p[:1].upper() + p[1:]) for p in sides] if len(sides) > 1 else [cost.strip()]


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
    if target is None or (not m["cost"] and any(parse_ability_cost(side, card_name=name).unsupported for side in equip_sides(cost))):
        return None
    if len(equip_sides(cost)) > 1 and tail:
        return None  # (a choice of costs with a trailing sentence about the cost: not read)
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


FORTIFY = re.compile(r"^fortify (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def fortify_cost(ch: Characteristics, index: int) -> str | None:
    """-- cards (wave 110I) -- 702.67a: "Fortify [cost]" = "[Cost]: Attach this permanent to target land you control. Fortify only as a sorcery." (mana costs only)."""
    for ab in ch.abilities:
        if ab.index == index and ab.kind == "keywords" and "fortify" in ab.keywords and (m := FORTIFY.match(re.sub(r"\s*\(.*?\)", "", ab.text).strip())):
            return m["cost"]
    return None


def supported_keyword(kw: str, line: str) -> bool:
    if kw == "fortify":
        return FORTIFY.match(re.sub(r"\s*\(.*?\)", "", line).strip()) is not None
    if kw == "enchant":
        return enchant_selector_of(line) is not None
    if kw == "equip":
        return equip_info(line) is not None
    return False


# -- the legality predicate ------------------------------------------------------------
def entering_face(plan: Plan, card: CardInstance, entry: dict[str, Any]) -> Characteristics | None:
    """-- block events (wave 53C) -- 712.14a: the back face a double-faced card put onto the battlefield transformed enters with (None: not entering
    transformed, or no printed back face)."""
    from app.rules import characteristics as chars

    data = plan.info.get(card.card_id) if entry.get("transformed") and card.card_id and card.token is None else None
    return chars.printed_from_data(data, 0 if card.face else 1) if data is not None else None


def host_problem(plan: Plan, source: CardInstance, host: str, controller: str | None = None, sba: bool = False,
                 face: Characteristics | None = None, host_card: CardInstance | None = None,
                 host_face: Characteristics | None = None) -> str | None:
    """Why ``source`` can't be attached to ``host`` (a card id or a player id) right now, or None
    if it can. For an Aura with an enchant wording the engine doesn't map, "unknown" (never
    remove an Aura on a guess). Targeting rules (hexproof, shroud) don't apply here: being
    attached isn't being targeted; protection does (702.16c-d)."""
    from app.rules.targets import SELECTORS

    you = controller or source.controller  # (an Aura about to enter under someone: judged as theirs)
    sch = replace(face or plan.ch(source), object_controller=you)  # (face: -- block events (wave 53C) -- the back face an entering double-faced card will have)
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
    card = host_card or plan.state.cards.get(host)
    if card is not None and card.zone.endswith(":graveyard") and kind == "aura" and (grave := enchant_selector(sch)) in (GRAVE, GRAVE_INSTANT):
        # -- reanimation Auras (wave 51F) -- 303.4a: a creature card in a graveyard; protection and hexproof don't function there (Animate Dead's ruling 2016-06-08)
        from app.rules import selectors

        return None if selectors.matches(plan, selectors.from_key(grave), card, plan.ch(card), you, source.id) else f"it can't enchant {card.name}"
    if card is None or (host_face is None and not card.zone.endswith(":battlefield")):
        return "it's not on the battlefield"
    hch = host_face or plan.ch(card)
    if kind == "aura" and any(rule.startswith("only_aura106:") and rule.partition(":")[2] != source.id for rule in hch.imposed):
        return f"{hch.name} can't be enchanted by another Aura"
    if kind == "aura" and "no_aura110h" in hch.imposed:  # -- cards (wave 110H) -- Tetravite: "This token can't be enchanted." (303.4d, 303.4j)
        return f"{hch.name} can't be enchanted"
    # -- attached events (wave 25D) -- 702.16n: a protection that "doesn't remove" this Aura / Auras isn't why an Aura falls off as a
    # state-based action (``sba``); it still keeps an Aura from becoming attached (702.16c: review 25D)
    if protection.protected_from(hch, sch, (lambda k: k == f"self:{source.id}" or (k == "auras" and kind == "aura") or (k == f"yours:{source.controller}" and kind in ("aura", "equipment"))) if sba else None):  # (wave 53B: Benevolent Blessing, 702.16n)
        return f"{hch.name} has protection from it"
    if kind == "aura":
        if sch.is_creature:
            return "an Aura that's also a creature can't enchant anything"  # 303.4d
        selector = enchant_selector(sch)
        if selector is None:
            return "unknown"
        if selector == PUT_WITH:  # -- reanimation Auras (wave 51F) -- only a creature this Aura put onto the battlefield, still that object (400.7)
            ok = hch.is_creature and plan.oid(card) in plan.rules.aura_links.get(plan.oid(source), ())
            return None if ok else f"it can only enchant a creature it put onto the battlefield, not {hch.name or 'that'}"
        if selector in (GRAVE, GRAVE_INSTANT):
            return f"it can't enchant {hch.name or 'that'}"  # (a creature card in a graveyard, not a permanent)
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
        from app.rules import equipment_animation

        if not (hch.is_creature or equipment_animation.makes_host_creature(plan, source, card)):
            return "Equipment can only equip a creature"
        # -- static permanents (wave 100D) -- "can be attached only to …", "can't be equipped" (701.3b, 704.5n)
        from app.rules import static_perm100d

        return static_perm100d.equip_problem(plan, source, card)
    if sch.is_creature:
        return "a Fortification that's also a creature can't fortify"  # 301.6
    return None if hch.is_land else "a Fortification can only fortify a land"


def legal_hosts(plan: Plan, source: CardInstance, controller: str | None = None, face: Characteristics | None = None) -> list[str]:
    """Everything ``source`` could be attached to right now (no targeting involved)."""
    out = [p for p in plan.live() if host_problem(plan, source, p, controller, face=face) is None]
    for c in plan.state.cards.values():
        if c.zone.endswith((":battlefield", ":graveyard")) and c.id != source.id and host_problem(plan, source, c.id, controller, face=face) is None:  # (wave 51F: a graveyard)
            out.append(c.id)
    return out


def enchanted_cards(plan: Plan, source: CardInstance) -> list[str]:
    """-- reanimation Auras (wave 51F) -- the creature cards in a graveyard ``source`` enchants: ``attach`` recorded each as the object it was (400.7)."""
    return [cid for oid in plan.rules.aura_links.get(plan.oid(source), ()) if (cid := oid.rsplit(".", 1)[0]) in plan.state.cards
            and plan.oid(cid) == oid and plan.state.cards[cid].zone.endswith(":graveyard")]


def attach(plan: Plan, source: str, host: str, actor: str) -> bool:
    """701.3a-b: attach ``source`` to ``host`` if it can be; otherwise it doesn't move."""
    card = plan.state.cards.get(source)
    if card is None or host_problem(plan, card, host) is not None:
        return False
    if host in plan.state.cards and plan.state.cards[host].zone.endswith(":graveyard"):  # -- reanimation Auras (wave 51F) -- 303.4a: it enchants a card in a graveyard
        plan.rules.aura_links[plan.oid(card)] = [plan.oid(host)]
        plan.note(f"{card.name} enchants {plan.state.cards[host].name} in a graveyard", [card.id, host])
        return True
    if card.attached_to == host or card.attached_player == host:
        return True  # already there: nothing happens (701.3b)
    plan.do({"type": "attach", "card_ids": [source], "to": host}, actor=actor)
    wave110e_blade.queue(plan, source)  # -- becomes attached, choose (wave 110E) -- asked at the next settle
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
    from app.rules import copying, face_down_entries64, replacements

    face_down_entries64.validate(plan, entries)
    for back in (e for e in entries if e.get("to") in ("hand", "graveyard")):  # -- resolution memory (wave 22D) -- 610.3: exiled from a hand, returns there
        plan.do({"type": "move", "card_ids": [back["card"]], "to": {"player": back["player"], "zone": back["to"]}}, actor=back["actor"])
    entries = [dict(e) for e in entries if e.get("to") not in ("hand", "graveyard")]
    for i, entry in enumerate(entries):
        card = plan.state.cards.get(entry["card"])
        if card is not None:
            card = face_down_entries64.probe(plan, card, entry)
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
        from app.rules import random_entry_choice

        while (choice := replacements.choice_needed(plan, card, entry)) is not None:
            if (value := random_entry_choice.answer(plan, choice, entry['player'], card.id)) is not None:
                entry.update(replacements._answer(entry, choice, value))
                continue
            # A player answers only nonrandom entering choices (614.12a).
            replacements.ask_entry_choice(plan, entries, i, ctx, shuffle)
            return False
        # -- enter as copy (wave 5F) -- as it will enter: a permanent entering as a copy of an Aura is one (707.5, 303.4f)
        # (-- attached events (wave 40B) -- 712.14a: a double-faced card put onto the battlefield transformed enters with its back face up, so it is an Aura
        # only if that face is: "return this card to the battlefield transformed" for Skin Invasion (a creature on the back) is no Aura entering)
        # CR 304.4/307.4: judge the object AS IT WOULD ENTER, after its
        # copy choices and on its requested face. A printed instant manifested
        # face down is a creature; an MDFC may enter on its permanent back face.
        from app.rules import entry_characteristics

        prospective = entry_characteristics.probe(card, entry.get("entry_characteristics"))
        probe = prospective.model_copy(update={"zone": zone_key(entry["player"], "battlefield"),
                                        "controller": entry["player"],
                                        **({"face": 1} if entry.get("transformed") or entry.get("modal_back") else {})})
        if {"Instant", "Sorcery"}.intersection(plan.ch(probe).types):
            entry["stays"] = True
            continue
        as_face = entering_face(plan, card, entry)
        kind = attach_kind(as_face or (plan.ch(card) if copying.entering_as_copy(plan, card) else chars.of(card, plan.info)))
        if kind is None and entry.get("entry_characteristics"):  # -- aura return (wave 110D) -- 205.1a, 303.4f: "It's an Aura enchantment" as it enters
            kind = attach_kind(plan.ch(probe))
        if (kind != "aura" and not (entry.get("host_choice") and kind == "equipment")) or entry.get("host"):
            continue
        hosts = _entry_hosts(plan, card, entry)
        if not hosts and kind == "equipment":
            continue  # 301.5e: Equipment enters unattached when no legal creature exists.
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

            decide(plan, player=entry["player"], kind="choose_one", prompt="Choose what the Aura enchants" if kind == "aura" else "Choose a creature to equip",  # (not named: it may come from a hidden zone)
                   options=[DecisionOption(id=h, label=label(plan, h), card_id=h if h in plan.state.cards else None)
                            for h in hosts],
                   resume={"step": "aura_enters", "entries": entries, "index": i, "ctx": ctx, "shuffle": shuffle},
                   source=card)
            return False
    entering = [e for e in entries if not e.get("stays")]
    replacements.move_together(plan, entering, simultaneous=ctx.get("simultaneous_move") if ctx else None)
    if ctx is not None:
        ctx.pop("simultaneous_move", None)
    for entry in entering:
        if entry.get("host"):  # it enters attached to what was chosen (303.4f)
            attach(plan, entry["card"], entry["host"], entry["actor"])
    return True


def _entry_hosts(plan: Plan, card: CardInstance, entry: dict[str, Any]) -> list[str]:
    face = None
    if entry.get("entry_characteristics"):  # -- aura return (wave 110D) -- 303.4f: judged as the Aura it enters as
        from app.rules import entry_characteristics

        face = plan.ch(entry_characteristics.probe(card, entry["entry_characteristics"]).model_copy(
            update={"zone": zone_key(entry["player"], "battlefield"), "controller": entry["player"]}))
    hosts = legal_hosts(plan, card, entry["player"], face)
    if entry.get("host_choice"):
        from app.rules import selectors

        allowed = selectors.candidates(plan, selectors.from_key(entry["host_choice"]), entry["player"], card.id)
        hosts = [h for h in hosts if h in allowed]
    return hosts


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
        if chosen[0] not in _entry_hosts(plan, card, entries[i]):
            from app.game.errors import ActionError

            raise ActionError("It can't enchant that")
        entries[i] = {**entries[i], "host": chosen[0]}
    if not enter(plan, entries, ctx, shuffle=shuffle):
        return  # another Aura is choosing
    if shuffle:
        plan.do({"type": "shuffle", "player": shuffle, "zone": "library"}, actor=shuffle)
    if ctx is not None:
        continue_effects(plan, ctx)
