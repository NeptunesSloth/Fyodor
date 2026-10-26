"""-- wave 110B final pass -- exact Oracle wordings of single cards, read as a wording the grammar already reads plus the smallest change to its definition.

* Lukka, Coppercoat Outcast: +1 gives each exiled creature card a permission to be cast for as long as it remains exiled and you control a Lukka planeswalker
  (611.2b, 113.6m; the 2020-04-17 rulings: any Lukka planeswalker counts); -2 reveals until a creature card with greater mana value than the exiled creature's, as it last
  existed (608.2h; X is 0 in a card in a library or on the battlefield: 107.3g).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

Def = dict[str, Any]

_LUKKA_PLUS = ('+1: Exile the top three cards of your library. Creature cards exiled this way gain "You may cast this card from exile as long as you control a Lukka planeswalker."')
_LUKKA_MINUS = ("−2: Exile target creature you control, then reveal cards from the top of your library until you reveal a creature card with greater mana value. "
                "Put that card onto the battlefield and the rest on the bottom of your library in a random order.")


def _lukka_plus(d: Def) -> Def:
    from app.rules import conditions, permissions

    cond = conditions.parse("you control a Lukka planeswalker")
    assert cond is not None
    return {**d, "effects": [{**e, "filter": permissions.spell_filter("creature"), "when": cond} if e.get("do") == "grant_play" else e for e in d["effects"]]}


def _lukka_minus(d: Def) -> Def:
    out: list[Def] = []
    for e in d["effects"]:
        if e.get("do") == "exile":
            e = {**e, "as": "gone110b"}
        elif e.get("do") == "look_top":
            e = {"do": "greater_dig110b", "gone": "ref:gone110b", "dig": e}
        out.append(e)
    return {**d, "effects": out}


_BUILD: dict[str, tuple[str, Any]] = {
    _LUKKA_PLUS: ('+1: Exile the top three cards of your library. For as long as they remain exiled, you may cast those cards.', _lukka_plus),
    _LUKKA_MINUS: ("−2: Exile target creature you control. Reveal cards from the top of your library until you reveal a creature card. "
                   "Put that card onto the battlefield and the rest on the bottom of your library in a random order.", _lukka_minus),
}


_SANAR = ("Vivid \u2014 At the beginning of your first main phase, reveal cards from the top of your library until you reveal X nonland cards, where X is the number of colors among "
          "permanents you control. For each of those colors, you may exile a card of that color from among the revealed cards. Then shuffle. You may cast the exiled cards this turn.")
_COLORS = (("W", "white"), ("U", "blue"), ("B", "black"), ("R", "red"), ("G", "green"))


def _sanar(d: Def) -> Def:
    """For each color among your permanents (read as the picks are made: nothing changes in between), one optional pick of a revealed card of that color (a card of two colors may
    be taken for either, not both: it leaves the revealed cards, 608.2d); the cards exiled may be cast this turn."""
    from app.rules import conditions, selectors

    dig, pick, shuffle, grant = d["effects"]
    out: list[Def] = [dig]
    for i, (_letter, word) in enumerate(_COLORS):
        cond = conditions.parse(f"you control a {word} permanent")
        sel = selectors.parse(f"{word} card")
        assert cond is not None and sel is not None
        out += [{"do": "only_if", "cond": cond, "skip": 1}, {**pick, "sel": sel.key(), "as": f"vivid{i}", "prompt": f"Vivid: exile a {word} card from among the revealed cards?"}]
    out.append(shuffle)
    out += [{**grant, "who": f"ref:vivid{i}"} for i in range(len(_COLORS))]
    return {**d, "effects": out}


_BUILD[_SANAR] = ("At the beginning of your first main phase, reveal cards from the top of your library until you reveal X nonland cards, where X is the number of colors among permanents you "
                  "control. You may exile one of them. Then shuffle. You may cast the exiled card this turn.", _sanar)

_KAMI = ("I, II \u2014 You gain 2 life. Look at the top three cards of your library. Exile one of them face down with a hatching counter on it, then put the rest on the bottom of your "
         "library in any order.")
_BUILD[_KAMI] = ("I, II \u2014 You gain 2 life. Look at the top three cards of your library. Exile one of them face down, then put the rest on the bottom of your library in any order. "
                 "Put a hatching counter on the exiled card.", lambda d: d)  # (the counter goes on the card as it is exiled, 122.1: the same exiled object, still face down)
_EGG = ("Whenever this creature or a Dragon you control dies, you may cast a creature spell from among cards you own in exile with hatching counters on them without paying its mana cost.")


def _egg(d: Def) -> Def:
    """"this creature or a Dragon you control" (the Egg is no Dragon): itself or any Dragon of yours, the Egg's own death counted once (603.10a: its last known information)."""
    from dataclasses import replace as _replace

    from app.rules import selectors

    sel = selectors.from_key(d["cond"]["sel"])
    return {**d, "cond": {**d["cond"], "sel": _replace(sel, other=False).key()}}


_BUILD[_EGG] = ("Whenever this creature or another Dragon you control dies, you may cast a creature spell from among cards you own in exile with hatching counters on them without paying its "
                "mana cost.", _egg)

_RIVER_DRAW = "Meet in Reverse \u2014 You draw cards from the bottom of your library rather than the top."
_RIVER_SPOILERS = ("Spoilers \u2014 Whenever an opponent scries, surveils, or searches their library, put a +1/+1 counter on River Song. "
                   "Then River Song deals damage to that player equal to its power.")


def draws_from_bottom(plan: Any, pid: str) -> bool:
    """River Song (121.1, 614.1): while its controller controls it, they draw from the bottom of their library; several such effects change nothing more."""
    return any(c.zone.endswith(":battlefield") and c.controller == pid and any(a.text.strip() == _RIVER_DRAW for a in plan.ch(c).abilities)
               for c in plan.state.cards.values() if c.name == "River Song")


def _river_spoilers(d: Def) -> Def:
    one = {"subject": "player", "player": "opponent"}
    return {**d, "cond": {"event": "either", **one, "conds": [{"event": k, **one} for k in ("scry", "surveil", "search_library")]}}


_BUILD[_RIVER_SPOILERS] = ("Whenever an opponent searches their library, put a +1/+1 counter on this creature. Then this creature deals damage to that player equal to its power.", _river_spoilers)

_THIEF = ("As this creature enters, remove all counters from all permanents. This creature enters with a +1/+1 counter on it for each counter removed this way.")


def _has_thief(ch: Any) -> bool:
    return any(a.text.strip() == _THIEF for a in ch.abilities)


def thief_total(plan: Any, card: Any, ch: Any) -> int:
    """Thief of Blood (614.12, 122.6): the counters on all permanents now (the look-ahead of what it enters with; nothing is removed here)."""
    if not _has_thief(ch):
        return 0
    return sum(sum(c.counters.values()) for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.id != card.id)


def thief_remove(plan: Any, card: Any, ch: Any, controller: str) -> None:
    """The removal itself, as the Thief really enters (the 2015-11-04 rulings: loyalty counters are removed from planeswalkers, players' experience counters are not)."""
    if not _has_thief(ch):
        return
    for c in list(plan.state.cards.values()):
        if c.zone.endswith(":battlefield") and c.id != card.id:
            for kind, n in list(c.counters.items()):
                if n > 0:
                    plan.do({"type": "counter", "card_ids": [c.id], "kind": kind, "delta": -n}, actor=controller)


_TORRENT_STATIC = ('As long as Torrent of Lava is on the stack, each creature has "{T}: Prevent the next 1 damage that would be dealt to this creature by Torrent of Lava this turn."')
_TORRENT_GRANT = "{T}: Prevent the next 1 damage that would be dealt to this creature by Torrent of Lava this turn."


def stack_grants(state: Any, card: Any, ch: Any) -> Any:
    """Torrent of Lava (113.6, 604.1, 611.3): while it is on the stack every creature has the shield ability (a static ability of the spell works on the stack, 113.6b).
    ponytail: keyed by the name, like Pin Collection; a second card of this kind needs the text read from its static instead."""
    from dataclasses import replace as _replace

    from app.rules.oracle import parse_abilities

    if not ch.is_creature or not any(c.name == "Torrent of Lava" and c.ability is None and c.zone == "stack" for c in state.cards.values()):
        return ch
    ab = parse_abilities(_TORRENT_GRANT)
    return _replace(ch, abilities=ch.abilities + (_replace(ab[0], index=190),)) if len(ab) == 1 else ch


def torrent_prevent(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """The granted ability's effect: the next 1 damage the Torrent (the spell on the stack, as that object) would deal to this creature this turn is prevented (615.7)."""
    from app.rules import source_shields

    spell = next((c for c in plan.state.cards.values() if c.name == "Torrent of Lava" and c.ability is None and c.zone == "stack"), None)
    if spell is None:
        plan.note("Torrent of Lava is no longer on the stack: nothing is prevented", actor=ctx["controller"])
        return True
    source_shields._record(plan, ctx, {"to": "self", "budget": 1, "props": {}}, [plan.oid(spell)], "Torrent of Lava")
    return True


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if ability.text.strip() == _TORRENT_STATIC:
        return {"kind": "static", "static": "stack_grant110b", "effects": []}
    if ability.text.strip() == _TORRENT_GRANT:
        native = scripts.define(replace(ability, text="{T}: You gain 1 life."), ch)
        return None if native is None else {**native, "effects": [{"do": "torrent_prevent110b"}]}

    if ability.text.strip() == _RIVER_DRAW:
        return {"kind": "static", "static": "draw_bottom110b", "effects": []}  # carried out where draws happen (replace.do_draws: draws_from_bottom)
    if ability.text.strip() == _THIEF:
        return {"kind": "static", "static": "thief110b", "effects": []}  # carried out where permanents enter (replacements.entered: thief_remove)
    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def greater_dig(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """The reveal-until instruction with its card required to have greater mana value than the creature the binding names (as it last existed)."""
    from app.rules import context, selectors

    gone = context.info(plan, ctx, e["gone"].removeprefix("ref:"))
    if gone is None:
        return True  # (nothing was exiled: no creature, nothing to compare with: 608.2b)
    dig = e["dig"]
    until = selectors.replace(selectors.from_key(dig["until"]), compare=(("mv", ">", int(gone[1].mana_value)),))
    ctx["effects"][ctx["next"]:ctx["next"]] = [{**dig, "until": until.key()}]
    return True


_SOUND = ("Whenever one or more creature tokens you control deal combat damage to a player, exile target instant or sorcery card with mana value equal to the damage dealt from their "
          "graveyard. Copy it. You may cast the copy without paying its mana cost. If you do, convert Soundwave.")


def _soundwave(d: Def) -> Def:
    """The target's mana value is the damage the batch dealt that player, read as the trigger goes on the stack (triggers.bind_event_stat: ``evt:damage110b``)."""
    from dataclasses import replace as _replace

    from app.rules import selectors

    t = d["target"]
    sel = _replace(selectors.from_key(t["what"]), compare=(("mv", "==", selectors.EVENT_STAT + "damage110b"),))
    return {**d, "target": {**t, "what": sel.key()}}


# 701.28 / the 2022-10-14 ruling: converting a permanent is transforming it, so "transform this creature" is the same action
_BUILD[_SOUND] = ("Whenever one or more creature tokens you control deal combat damage to a player, exile target instant or sorcery card from that player's graveyard. Copy it. "
                  "You may cast the copy without paying its mana cost. If you do, transform this creature.", _soundwave)

_GRIM = ("Whenever The Grim Captain attacks, each opponent sacrifices a nonland permanent of their choice. Then you may put an exiled creature card used to craft The Grim Captain "
         "onto the battlefield under your control tapped and attacking.")
_BUILD[_GRIM] = ("Whenever this creature attacks, each opponent sacrifices a nonland permanent of their choice.", lambda d: {**d, "effects": [*d["effects"], {"do": "crafted_put110b"}]})


def crafted_put(plan: Any, ctx: dict[str, Any], e: Def) -> bool:
    """The Grim Captain (702.167c, 508.4): you may put one of the exiled creature cards used to craft it (still those objects, still in exile) onto the battlefield under your
    control tapped and attacking; what it attacks is chosen as it enters (the 2023-11-10 ruling), and it was never declared as an attacker."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    refs = plan.rules.crafted_materials.get(ctx.get("source_object") or "", [])
    pool = [c for r in refs if (c := plan.state.cards.get(r.card)) is not None and plan.oid(c) == r.object_id and c.zone.endswith(":exile") and plan.ch(c).is_creature]
    if not pool:
        return True
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'The Grim Captain'}: put an exiled creature card used to craft it onto the battlefield tapped and attacking?",
           options=[DecisionOption(id=c.id, label=c.name or "Card", card_id=c.id) for c in pool], min_choices=0, max_choices=1, resume={"step": "crafted_put110b", "ctx": ctx})
    return False


def resume_crafted_put(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    ctx = d.resume["ctx"]
    if len(chosen) > 1 or any(c not in {o.id for o in d.options} for c in chosen):
        raise ActionError("Choose one of the cards offered, or none")
    if chosen:
        context.bind_objects(plan, ctx, "crafted_put110b", chosen)
        if not effects.PRIMITIVES["return_card"](plan, ctx, {"do": "return_card", "who": "ref:crafted_put110b", "to": "battlefield", "tapped": True, "under": "you", "attacking": True}):
            return  # (asked whom it attacks: that answer carries on)
    effects.continue_effects(plan, ctx)


PRIMITIVES: dict[str, Any] = {"torrent_prevent110b": torrent_prevent, "greater_dig110b": greater_dig, "crafted_put110b": crafted_put}
RESUME: dict[str, Any] = {"crafted_put110b": resume_crafted_put}
