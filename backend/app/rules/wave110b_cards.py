"""-- wave 110B -- exact Oracle wordings of single cards, read as a wording the grammar already reads (``_AS``) or built from parts of it.

Each entry matches one whole ability's Oracle text exactly (plural names and "and/or" included) and nothing else; any other wording stays
unsupported. Researched against the Comprehensive Rules of 2026-09-25.
"""
from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]


def firebending(line: str) -> int | None:
    """702.189a: N of the one "firebending N" piece of a keyword line ("Trample, firebending 4, haste"), else None."""
    pieces = [p.strip() for p in re.split(r"[,;]\s*", re.sub(r"\s*\([^()]*\)", "", line).strip().rstrip("."))]
    found = [re.fullmatch(r"firebending (\d+)", p.lower()) for p in pieces if p.lower().startswith("firebending")]
    return int(found[0][1]) if len(found) == 1 and found[0] else None


# whole ability text -> the wording the grammar reads for it
_AS: dict[str, str] = {
    "Exile Stunning Reversal.": "Exile ~.",
    # Desert Warfare: "that many" is the number of Deserts you control (the "five or more" test, 603.4, counts them); "They gain haste" is the tokens' own
    "At the beginning of combat on your turn, if you control five or more Deserts, create that many 1/1 red, green, and white Sand Warrior creature tokens. "
    "They gain haste.":
        "At the beginning of combat on your turn, if you control five or more Deserts, create a 1/1 red, green, and white Sand Warrior creature token with "
        "haste for each Desert you control.",
    # Saproling Infestation: 702.33d a player "kicks" a spell as they cast it kicked
    "Whenever a player kicks a spell, you create a 1/1 green Saproling creature token.":
        "Whenever a player casts a kicked spell, you create a 1/1 green Saproling creature token.",
    # Kitsune Ace: an attacking Vehicle is a creature (301.7), so "that Vehicle" is "that creature"
    "Whenever a Vehicle you control attacks, That Vehicle gains first strike until end of turn.":
        "Whenever a Vehicle you control attacks, that creature gains first strike until end of turn.",
    # Campsite Cuisine: the enchantment itself is no creature, so "a legendary creature you control" is another one; X Foods are "any number of Foods" and
    # X targets are "that many" (the number sacrificed, set as the reflexive trigger is put on the stack, 603.12)
    "Whenever this enchantment or a legendary creature you control enters, create a Food token.":
        "Whenever this enchantment or another legendary creature you control enters, create a Food token.",
    "Whenever you attack, you may sacrifice X Foods. When you do, up to X target attacking creatures each get +3/+3 and gain trample and indestructible "
    "until end of turn.":
        "Whenever you attack, you may sacrifice any number of Foods. When you do, up to that many target attacking creatures each get +3/+3 and gain "
        "trample and indestructible until end of turn.",
    # Plague Reaver: "each other creature you control" is "all other creatures you control" (701.21a)
    "At the beginning of your end step, sacrifice each other creature you control.":
        "At the beginning of your end step, sacrifice all other creatures you control.",
    # Ran and Shaw: one object with a plural name (201.5); "Dragon and/or Lesson" is a card with either subtype
    "When Ran and Shaw enter, if you cast them and there are three or more Dragon and/or Lesson cards in your graveyard, create a token that's a copy "
    "of Ran and Shaw, except it's not legendary.":
        "When this creature enters, if you cast it and there are three or more Dragon or Lesson cards in your graveyard, create a token that's a copy "
        "of this creature, except it's not legendary.",
    # Longhorn Sharpshooter: "it" is the plotted card itself (a source of damage in exile, 120.1)
    "When this card becomes plotted, it deals 2 damage to any target.": "When this card becomes plotted, this creature deals 2 damage to any target.",
    # Prince of Thralls: "that opponent" is the opponent whose permanent went to the graveyard, as "that player"
    "Whenever a permanent an opponent controls is put into a graveyard, put that card onto the battlefield under your control unless that opponent pays 3 life.":
        "Whenever a permanent an opponent controls is put into a graveyard, put that card onto the battlefield under your control unless that player pays 3 life.",
}


def _swap_value(d: Def, old: Def, new: Def) -> Def:
    """The native definition with the one condition value ``old`` read as ``new``."""
    hit = [c for c in d["conditions"] if c.get("value") == old]
    assert len(hit) == 1
    return {**d, "conditions": [{**c, "value": new} if c is hit[0] else c for c in d["conditions"]]}


def _gated(n: int) -> Callable[[Def], Def]:
    """The one kicked gate (a promised gift is a kicked spell, 702.174k) covers the ``n`` instructions after it."""
    return lambda d: {**d, "effects": [{**e, "n": n} if e["do"] == "kicked_gate" else e for e in d["effects"]]}


def _reaver(d: Def) -> Def:
    return {**d, "effects": [{"do": "reaver110b"}]}


def _quake(d: Def) -> Def:
    """Quakebringer (113.6b-style zones): works on the battlefield, or from the graveyard while its controller controls a Giant (603.4 as it triggers)."""
    here = {"object": "self", "test": "on_battlefield"}
    cond = {"any": [here, d["if"]]}
    return {**d, "if": cond, "gy_watch": True, "gy_bf110b": True, "effects": [{**e, "cond": cond} if e["do"] == "only_if" else e for e in d["effects"]]}


def _skyguard(d: Def) -> Def:
    return {**d, "if": {"skyguard110b": True},
            "effects": [{**e, "duration": "end_of_combat"} if e["do"] == "prevent_all" else e for e in d["effects"]]}


def skyguard_holds(plan: Any, ctx: dict[str, Any]) -> bool:
    """Suppressor Skyguard: the attacking player (the active player, 508.1) has an opponent other than the Skyguard's controller who is not being
    attacked (508.3d: a player is attacked by a creature attacking them or a planeswalker or battle they control)."""
    me, atk = ctx["controller"], plan.active
    attacked = set()
    for c in plan.state.cards.values():
        if c.attacking is not None and c.controller == atk:
            attacked.add(c.attacking.id if c.attacking.kind == "player" else plan.state.cards[c.attacking.id].controller)
    return any(p != atk and p != me and not plan.state.players[p].left and p not in attacked for p in plan.state.players)


def _still_here(d: Def) -> Def:
    """The delayed trigger has an intervening "if" this creature is still on the battlefield (603.4, 603.7)."""
    hit = [e for e in d["effects"] if e["do"] == "delayed"]
    assert len(hit) == 1
    hit[0]["when"] = {**hit[0]["when"], "if": {"object": "self", "test": "on_battlefield"}}
    return d


def _lich(d: Def) -> Def:
    """Lich's Mastery: one exile per life lost (608.2c), of a permanent, a card in hand or a card in the graveyard."""
    return {**d, "effects": [{"do": "repeat", "n": {"event_amount": 1}, "span": 1}, {"do": "exile_own110b"}]}


# whole ability text -> (the wording the grammar reads, what to change in its definition)
def _electro(d: Def) -> Def:
    return {**d, "effects": [d["effects"][0], {**d["effects"][1], "n": {"turn_history": "excess_obj110b", "object": "event"}}]}


def _warriors(d: Def) -> Def:
    """Dalkovan Encampment: the tokens the turn-long trigger makes are sacrificed at the next end step (603.7: that delayed trigger is made when each fires)."""
    watch, make = d["effects"]
    return {**d, "effects": [{**watch, "n": 3}, {**make, "as": "tok110b"}, {"do": "deferred:delayed", "when": {"kind": "step", "step": "end", "whose": "next"}, "n": 1},
                             {"do": "deferred:deferred:sacrifice", "who": "ref:tok110b"}]}


def _inheritance(d: Def) -> Def:
    """Expedited Inheritance: the damaged creature's controller (not the enchantment's) chooses, exiles from their own library and plays those cards (a card's owner, 400.3)."""
    exile, grant = d["effects"]
    ask = {"do": "optional_payment", "who": "ref:event.controller", "ask": "exile that many cards from the top of your library", "cost": "", "bind": "pay110b"}
    return {**d, "optional": False, "effects": [ask, {"do": "only_if", "cond": {"succeeded": "pay110b"}, "skip": 2},
                                                {**exile, "player": "ref:event.controller"}, {**grant, "owner": True, "optional": True}]}


def _battleshaper(d: Def) -> Def:
    """Boros Battleshaper: two "up to one" targets; 508.1d / 509.1c the first must attack or block if able, 508.1c the second can't attack or block, both this combat only."""
    force, = d["effects"]
    return {**d, "effects": [{**force, "rules": ["must_attack", "must_block"]}, {**force, "who": "target:1", "rules": ["cant_attack_or_block"]}],
            "targets": [d["targets"][0], dict(d["targets"][0])]}


def _mirror(d: Def) -> Def:
    """Mirror of Life Trapping (607.2a linked exile): returning the cards exiled with it first is the same as returning "all other" ones after the exile."""
    from app.rules import selectors

    sel = selectors.parse("permanent card")
    assert sel is not None
    key = sel.key()
    back = {"do": "return_card", "who": f"exiled_with:{key}", "to": "battlefield", "tapped": False, "under": "owner"}
    gate, exile = d["effects"]
    return {**d, "effects": [{**gate, "skip": 2}, back, {**exile, "link": True}], "accumulating_link": True}


def _sponsor(d: Def) -> Def:
    """Scholarship Sponsor: the search of "each player who controls fewer lands than you" (a native reading) is sized per player by ``gap_search110b``."""
    where, search = d["effects"]
    assert where["do"] == "players_where" and search["do"] == "search"
    return {**d, "effects": [{"do": "gap_search110b", "search": {k: v for k, v in search.items() if k not in ("who", "max")}}]}


def gap_search(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Scholarship Sponsor: each player (in turn order, 101.4) who controls fewer lands than the player who controls the most searches for up to as many
    basic lands as the difference (701.23), put onto the battlefield tapped; counted once, before any search (608.2c)."""
    lands = {p: sum(1 for c in plan.state.cards.values() if c.controller == p and c.zone.endswith(":battlefield") and "Land" in plan.ch(c).types)
             for p in plan.apnap() if not plan.state.players[p].left}
    most = max(lands.values(), default=0)
    at = ctx["next"]
    ctx["effects"][at:at] = [{**e["search"], "who": f"player:{p}", "max": most - lands[p]} for p in plan.apnap() if p in lands and lands[p] < most]
    return True


def _intervention(d: Def) -> Def:
    """Cosmic Intervention: 614.1a the replacement covers every permanent you control (a "die" replacement is the creature case of it)."""
    from app.rules import selectors

    gone, = d["effects"]
    sel = selectors.parse("permanent you control")
    assert gone["do"] == "exile_if_dies" and sel is not None
    return {**d, "effects": [{**gone, "each": sel.key(), "return110b": True}]}


def return_next_end(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Cosmic Intervention (603.7, 400.7): the card the replacement exiled returns under its owner's control at the beginning of the next end step; a token
    ceased to exist in exile (111.7), and a card that has moved again is another object."""
    from app.game.rules_state import ObjectRef
    from app.rules import delayed

    card = plan.state.cards.get(e["card"])
    if card is None or card.is_token or not card.zone.endswith(":exile"):
        return True
    ref = ObjectRef(card=card.id, object_id=plan.oid(card), zone=card.zone).model_dump(mode="json")
    delayed.create_plain(plan, ctx["controller"], ctx.get("source_card") or "", ctx.get("source_object") or "", ctx.get("name") or "",
                         {"kind": "step", "step": "end", "whose": "next"},
                         [{"do": "bind_refs", "refs": {"ret110b": {"kind": "objects", "objects": [ref]}}},
                          {"do": "return_card", "who": "ref:ret110b", "to": "battlefield", "tapped": False, "under": "owner"}])
    return True


_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    # Rendmaw: 701.15a each token is goaded by Rendmaw's controller, "for the rest of the game" (token_copy_sources.permanent_goad, as Nettling Nuisance)
    "When Rendmaw enters and whenever you play a card with two or more card types, each player creates a tapped 2/2 black Bird creature token with flying. "
    "The tokens are goaded for the rest of the game.":
        ("When ~ enters and whenever you play a card with two or more card types, each player creates a tapped 2/2 black Bird creature token with flying.",
         lambda d: {**d, "effects": [{**d["effects"][0], "as": "bird110b"}, {"do": "permanent_copy_goad", "who": "ref:bird110b"}]}),
    # Stunning Reversal: 614.1a the next loss of the game this turn is replaced (wave110c_lose reads the shield)
    "The next time you would lose the game this turn, instead draw seven cards and your life total becomes 1.":
        ("Draw a card.", lambda d: {**d, "effects": [{"do": "lose_shield110b"}]}),
    "If a permanent you control would be put into a graveyard from the battlefield this turn, exile it instead. Return it to the battlefield under its "
    "owner's control at the beginning of the next end step.":
        ("If a creature you control would die this turn, exile it instead.", _intervention),
    "When this creature enters, each player who controls fewer lands than the player who controls the most lands searches their library for a number of "
    "basic land cards less than or equal to the difference, puts those cards onto the battlefield tapped, then shuffles.":
        ("When this creature enters, each player who controls fewer lands than you searches their library for up to two basic land cards, puts them onto "
         "the battlefield tapped, then shuffles.", _sponsor),
    "Whenever a creature enters, if it was cast, exile it, then return all other permanent cards exiled with this artifact to the battlefield under "
    "their owners' control.": ("Whenever a creature enters, if it was cast, exile it.", _mirror),
    "At the beginning of each combat, up to one target creature attacks or blocks this combat if able and up to one target creature can't attack or block this combat.":
        ("At the beginning of each combat, up to one target creature attacks this combat if able.", _battleshaper),
    "At the beginning of combat on your turn, investigate for each goaded creature you control. Then each creature you control is no longer goaded.":
        ("At the beginning of combat on your turn, investigate for each goaded creature you control.", lambda d: {**d, "effects": [*d["effects"], {"do": "ungoad110b"}]}),
    "Whenever a creature is dealt damage, its controller may exile that many cards from the top of their library. They may play those cards until the end of their next turn.":
        ("Whenever a creature is dealt damage, you may exile that many cards from the top of your library. You may play those cards until the end of your next turn.", _inheritance),
    # Dalkovan Encampment (the sacrifice rides on each trigger's tokens)
    "{2}{W}, {T}: Whenever you attack this turn, create two 1/1 red Warrior creature tokens that are tapped and attacking. Sacrifice them at the beginning of the next end step.":
        ("{2}{W}, {T}: Whenever you attack this turn, create two 1/1 red Warrior creature tokens that are tapped and attacking.", _warriors),
    # Taii Wakeen: 120.3, "equal to that creature's toughness" is the amount of this one damage event; "plus X" is the X paid (107.3k)
    "Whenever a source you control deals noncombat damage to a creature equal to that creature's toughness, draw a card.":
        ("Whenever a source you control deals noncombat damage to a creature, draw a card.", lambda d: {**d, "cond": {**d["cond"], "eq_toughness110b": True}}),
    "{X}, {T}: If a source you control would deal noncombat damage to a permanent or player this turn, it deals that much damage plus X instead.":
        ("{X}, {T}: Until end of turn, if a source you control would deal noncombat damage to a permanent or player, it deals that much damage plus 1 instead.",
         lambda d: {**d, "effects": [{**e, "op": {**e["op"], "n": 0, "x110b": True}} if e.get("do") == "replace_record" else e for e in d["effects"]]}),
    # Way of the Mind Sculptor: the activation event carries the loyalty counters its cost removed (606.4, 603.4)
    "Whenever you activate a loyalty ability, if you removed two or more loyalty counters to activate it, draw a card.":
        ("Whenever you activate a loyalty ability, draw a card.", lambda d: {**d, "cond": {**d["cond"], "loyalty_removed110b": 2}}),
    # The Chain Veil: each planeswalker you control may be activated one more time this turn (606.3 as though none were activated)
    "{4}, {T}: For each planeswalker you control, you may activate one of its loyalty abilities once this turn as though none of its loyalty abilities "
    "have been activated this turn.":
        ("{4}, {T}: Draw a card.", lambda d: {**d, "effects": [{"do": "veil110b"}]}),
    # Perch Protection: all three instructions are conditional on the promised gift (608.2c: one sentence)
    "Create four 2/2 blue Bird creature tokens with flying. If the gift was promised, all permanents you control phase out, and until your next turn, "
    "your life total can't change and you gain protection from everything.":
        ("Create four 2/2 blue Bird creature tokens with flying. If the gift was promised, all permanents you control phase out. Until your next turn, "
         "your life total can't change. You gain protection from everything until your next turn.", _gated(3)),
    # Marvo: the clash he won (701.30d), as Entangling Trap's "if you won" reads it
    "Whenever you win a clash, draw a card. Then you may cast a spell from your hand with mana value 8 or less without paying its mana cost.":
        ("Whenever you clash, draw a card. Then you may cast a spell from your hand with mana value 8 or less without paying its mana cost.",
         lambda d: {**d, "if": {"clash_won100a": True}}),
    # Oath of Lim-Dul: one sacrifice-unless-discard for each 1 life lost (the event's amount), each time its own choice (608.2c)
    "Whenever you lose life, for each 1 life you lost, sacrifice a permanent other than this enchantment unless you discard a card.":
        ("Whenever you lose life, sacrifice a permanent other than this enchantment unless you discard a card.",
         lambda d: {**d, "effects": [{"do": "repeat", "n": {"event_amount": 1}, "span": len(d["effects"])}, *d["effects"]]}),
    # Plague Reaver: the chosen opponent's next upkeep returns the sacrificed card under that player's control (603.7, 110.2a)
    "Discard two cards, Sacrifice this creature: Choose target opponent. Return this creature to the battlefield under that player's control at the "
    "beginning of their next upkeep.":
        ("Discard two cards, Sacrifice this creature: Target opponent gains 1 life.", _reaver),
    # Quakebringer: the trigger works from the battlefield, or from the graveyard with a Giant under your control
    "At the beginning of your upkeep, Quakebringer deals 2 damage to each opponent. This ability triggers only if Quakebringer is on the battlefield or "
    "if Quakebringer is in your graveyard and you control a Giant.":
        ("At the beginning of your upkeep, if this card is in your graveyard and you control a Giant, this creature deals 2 damage to each opponent.",
         _quake),
    # Suppressor Skyguard: prevention lasts through this combat only (500.5); the attacker needs another opponent nobody attacks
    "Whenever a player attacks you, if that player has another opponent who isn't being attacked, prevent all combat damage that would be dealt to you "
    "this combat.":
        ("Whenever a player attacks you, prevent all combat damage that would be dealt to you this turn.", _skyguard),
    # Shirei: the delayed return happens only if Shirei is still on the battlefield when the next end step begins
    "Whenever a creature with power 1 or less is put into your graveyard from the battlefield, you may return that card to the battlefield at the "
    "beginning of the next end step if Shirei is still on the battlefield.":
        ("Whenever a creature with power 1 or less is put into your graveyard from the battlefield, you may return that card to the battlefield at the "
         "beginning of the next end step.", _still_here),
    # Lich's Mastery: for each 1 life you lost, exile a permanent you control or a card from your hand or graveyard
    "Whenever you lose life, for each 1 life you lost, exile a permanent you control or a card from your hand or graveyard.":
        ("Whenever you lose life, exile a permanent you control.", _lich),
    # Divine Intervention: the effect states that the game is a draw (104.4c)
    "When you remove the last intervention counter from this enchantment, the game is a draw.":
        ("When the last intervention counter is removed from this enchantment, draw a card.",
         lambda d: {**d, "effects": [{"do": "draw_game110b"}]}),
    # Overclocked Electromancer: X is all the excess damage that creature was dealt this turn (120.10), summed from the turn log
    "Whenever this creature deals combat damage to a creature, if that creature was dealt excess damage this turn, you get X {E}, where X is that excess "
    "damage.":
        ("Whenever this creature deals combat damage to a creature, if that creature was dealt excess damage this turn, you get {E}{E}.", _electro),
    # Firemane Angel: works from the graveyard (as Quakebringer) or on the battlefield (603.4 intervening "if")
    "At the beginning of your upkeep, if Firemane Angel is in your graveyard or on the battlefield, you may gain 1 life.":
        ("At the beginning of your upkeep, if this creature is in your graveyard, you may gain 1 life.", _quake),
    # Goblin Plate Mail: the Army chosen by amassing, whether or not it got counters (701.47c), is what the Equipment attaches to (701.3a)
    "When this Equipment enters, amass Goblins 1, then attach this Equipment to the amassed Army.":
        ("When this Equipment enters, amass Goblins 1.",
         lambda d: {**d, "effects": [{**d["effects"][0], "as": "army110b"}, {"do": "attach_to", "who": "ref:army110b"}]}),
    # Wall of Dust: the blocked creature can't attack in its controller's next turn (a window rule that starts with that turn, as attack_destinations)
    "Whenever this creature blocks a creature, that creature can't attack during its controller's next turn.":
        ("Whenever this creature blocks a creature, that creature doesn't untap during its controller's next untap step.",
         lambda d: {**d, "effects": [{"do": "no_attack_next110b", "who": "event"}]}),
    # Ozai: the mana a player would lose stays in the pool as red mana (614.1a, 500.4)
    "If you would lose unspent mana, that mana becomes red instead.":
        ("If you would lose unspent mana, that mana becomes colorless instead.", lambda d: {**d, "to": "R"}),
    # Ozai: unspent mana of any type, in the pool and in units with restrictions (106.4)
    "Ozai has flying and indestructible as long as you have six or more unspent mana.":
        ("Ozai has flying and indestructible as long as you have six or more cards in your hand.",
         lambda d: _swap_value(d, {"hand": "you"}, {"unspent": ""})),
}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    text = ability.text.strip()
    if (same := _AS.get(text)) is not None:
        return scripts.define(replace(ability, text=same), ch)
    if (built := _BUILD.get(text)) is not None:
        native = scripts.define(replace(ability, text=built[0]), ch)
        return None if native is None else built[1](native)
    return None


_VINCENT = ('Until end of turn, target creature you control gains "When this creature dies, return it to the battlefield tapped under its owner\'s '
            'control" and has the chosen base power and toughness.')
_TIER = re.compile(r"• (?P<label>[^—{}]+) — (?P<cost>(?:\{[^}]+\})+) — (?P<p>\d+)/(?P<t>\d+)\.")


# Genku: the header's "those characteristics" are each bullet's own token (700.2, "hasn't been chosen this turn" is modal_abilities' memory)
_GENKU = ("Whenever another nontoken permanent you control leaves the battlefield, choose one that hasn't been chosen this turn. Create a creature token with those characteristics.",
          ["• 2/2 white Fox with vigilance.", "• 1/2 blue Moonfolk with flying.", "• 1/1 black Rat with lifelink."],
          ["Create a 2/2 white Fox creature token with vigilance.", "Create a 1/2 blue Moonfolk creature token with flying.",
           "Create a 1/1 black Rat creature token with lifelink."])


def merge_lines(ch: Any, out: dict[int, Any]) -> None:
    from app.rules import modal_abilities

    head, rows, creates = _GENKU
    for offset, ab in enumerate(ch.abilities):
        if ab.text != head or [r.text for r in ch.abilities[offset + 1 : offset + 4]] != rows:
            continue
        new = {ab.index: replace(ab, text=head.split(", choose")[0] + ", choose one that hasn't been chosen this turn —")}
        new.update({r.index: replace(r, text="• " + t) for r, t in zip(ch.abilities[offset + 1 : offset + 4], creates, strict=True)})
        rewritten = replace(ch, abilities=tuple(new.get(a.index, a) for a in ch.abilities))
        out.update(modal_abilities.definitions(new[ab.index], rewritten) or {})


def tiered(ch: Any, lines: list[Any]) -> Def | None:
    """Vincent's Limit Break (702.183a): the line above the tiers is the spell, each tier gives the base power and toughness it names (613.4b)."""
    from app.rules import scripts

    found = [_TIER.fullmatch(ab.text) for ab in lines[1:]]
    if len(lines) != 4 or lines[0].text != _VINCENT or None in found:
        return None
    modes = []
    for m in found:
        assert m is not None
        parts = [scripts.define(replace(lines[0], text=t), ch) for t in (
            'Until end of turn, target creature you control gains "When this creature dies, return it to the battlefield tapped under its owner\'s control."',
            f"Until end of turn, target creature you control has base power and toughness {m['p']}/{m['t']}.")]
        if None in parts or [d["target"] for d in parts if d] != [parts[0]["target"]] * 2:  # type: ignore[index]
            return None
        assert parts[0] is not None and parts[1] is not None
        modes.append({"text": f"{m['label']} — {m['cost']} — {m['p']}/{m['t']}.", "effects": [*parts[0]["effects"], *parts[1]["effects"]],
                      "target": parts[0]["target"], "cost": m["cost"]})
    return {"kind": "spell", "effects": [], "target": None, "modes": modes, "modal": {"min": 1, "max": 1, "repeat": False, "condition": None}}


def veil(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The Chain Veil: every planeswalker its controller controls gets one more loyalty activation this turn (the "twice" allowance, cast_limits.loyalty_rule)."""
    for c in plan.state.cards.values():
        if c.controller == ctx["controller"] and c.zone.endswith(":battlefield") and "Planeswalker" in plan.ch(c).types:
            plan.rules.once_per_turn[f"loyalty_veil110b:{c.id}"] = plan.state.turn.number
    return True


def ungoad(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Serene Sleuth: "each creature you control is no longer goaded" - 701.15b goaded is a designation lasting until the goader's next turn; it leaves them now."""
    from app.rules import delayed, keyword_actions

    mine = {plan.oid(c) for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == ctx["controller"]}
    for effect in [x for x in plan.rules.effects if any(i.startswith(keyword_actions.GOADED) for i in x.imposes)]:
        if mine & set(effect.affected):
            delayed._drop(plan, effect, [o for o in effect.affected if o not in mine])
    return True


def draw_game(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """104.4c: "the game is a draw" (a Commander game does not use the limited range of influence option, 104.4e)."""
    plan.rules.draw_reason = "An effect states that the game is a draw (104.4c)"
    plan.rules.priority = None
    plan.rules.decision = None
    plan.note("The game is a draw (104.4c)")
    return False


def reaver(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Plague Reaver: delayed trigger (603.7a) at the chosen opponent's next upkeep returns the sacrificed card (still the same object, 603.7c) to the
    battlefield under that opponent's control (110.2a)."""
    from app.game.rules_state import DelayedTrigger
    from app.rules import context
    from app.rules.effects import _players

    who = _players(plan, ctx, "target")
    card = ctx.get("source_card")
    if len(who) != 1 or card is None or plan.state.cards[card].zone.endswith(":battlefield"):
        return True
    refs: dict[str, Any] = {}
    context.bind_objects(plan, {"refs": refs}, "reaver", [card])
    context.bind_players({"refs": refs}, "opp", who)
    plan.rules.delayed.append(DelayedTrigger(
        id=secrets.token_hex(4), controller=ctx["controller"], source_card=card, source_object=ctx.get("source_object"), name=ctx.get("name") or "",
        when={"kind": "step", "step": "upkeep", "whose": "payer", "player": who[0]},
        effects=[{"do": "return_card", "who": "ref:reaver", "to": "battlefield", "tapped": False, "under": "ref:opp"}], refs=refs,
        turn=plan.state.turn.number, step=plan.state.turn.phase, created_step=plan.rules.step_serial))
    plan.note(f"{ctx.get('name')} will return at {who[0]}'s next upkeep")
    return True


def exile_own(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Exile a permanent you control or a card from your hand or graveyard": the controller picks one as it resolves (608.2d); none: nothing."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    me = ctx["controller"]
    mine = [c for c in plan.state.cards.values() if (c.zone == f"{me}:hand" or c.zone == f"{me}:graveyard" and c.owner == me)
            or (c.zone.endswith(":battlefield") and c.controller == me)]
    if not mine:
        return True
    decide(plan, player=me, kind="choose_cards", prompt=f"{ctx.get('name') or 'Exile'}: exile a permanent you control or a card from your hand or graveyard",
           options=[DecisionOption(id=c.id, label=c.name or "Card", card_id=c.id) for c in mine], min_choices=1, max_choices=1,
           resume={"step": "exile_own110b", "ctx": ctx})
    return False


def resume_exile_own(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx = d.resume["ctx"]
    ok = {o.id for o in d.options}
    if len(chosen) != 1 or chosen[0] not in ok:
        raise ActionError("Choose one of the cards offered")
    plan.note(f"{plan.name(d.player)} exiles {plan.state.cards[chosen[0]].name}", actor=d.player)
    effects.exile_cards(plan, ctx, {}, chosen)
    effects.continue_effects(plan, ctx)


def rebound_or_hand(plan: Any, card_id: str, controller: str) -> bool:
    """614.1a, 616.1: a rebound spell that also goes to its owner's hand as it resolves (buyback, Soulfire Grand Master): two replacements of the same
    event, so its controller picks one. True: the question is open (engine.leave_stack waits for it)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    if plan.oid(card_id) not in plan.rules.buyback or plan.oid(card_id) in plan.rules.flashback:
        return False
    decide(plan, player=controller, kind="choose_one", prompt="Rebound (exile it) or return it to your hand as it resolves?",
           options=[DecisionOption(id="rebound", label="Exile it with rebound"), DecisionOption(id="hand", label="Put it into your hand")],
           resume={"step": "rebound_hand110b", "card": card_id, "oid": plan.oid(card_id), "controller": controller})
    return True


def resume_rebound_hand(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import engine

    r = d.resume
    card = plan.state.cards.get(r["card"])
    if card is None or card.zone != "stack" or plan.oid(card) != r["oid"]:
        return
    plan.rules.buyback = [o for o in plan.rules.buyback if o != r["oid"]]
    if chosen[0] == "hand":
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "hand"}}, actor=r["controller"])
    else:
        engine.leave_stack(plan, card.id, r["controller"])


def no_attack_next(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Wall of Dust: 508.1c-style restriction "can't attack" (a continuous effect, 611.2) from the start of the creature's controller's next turn
    (declaration window "next_turn", engine.begin_window) to its end."""
    from app.rules import effects, layers

    for cid in effects._cards(plan, ctx, e["who"]):
        card = plan.state.cards[cid]
        layers.add_effect(plan, affected=[plan.oid(cid)], layer="6", source=ctx.get("source_object"), controller=ctx["controller"], duration="permanent",
                          imposes=("cant_attack",), declaration_window="next_turn", declaration_player=card.controller)
    return True


def lose_shield(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import turn_log_now

    log = turn_log_now(plan.state)
    if log is not None:
        log.lose_shield110b.append(f"{ctx['controller']}|{ctx['source_card']}")
    return True


RESUME: dict[str, Any] = {"exile_own110b": resume_exile_own, "rebound_hand110b": resume_rebound_hand}
def gift_given(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """702.174c: the gift was given (its instant or sorcery resolved, or its permanent's gift trigger resolved): "Whenever you give a gift"."""
    from app.game.rules_state import emit

    emit(plan.state, "designation", counter="gift_given110b", player=ctx["controller"])
    return True


PRIMITIVES: dict[str, Any] = {"return_next_end110b": return_next_end, "gap_search110b": gap_search, "gift_given110b": gift_given, "ungoad110b": ungoad, "no_attack_next110b": no_attack_next, "draw_game110b": draw_game, "reaver110b": reaver, "veil110b": veil, "exile_own110b": exile_own, "lose_shield110b": lose_shield}
