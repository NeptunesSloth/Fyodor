"""-- Mystery Booster Commander (wave MBC-B) -- the last lines of fourteen Mystery Booster Commander Edition cards (oval-stamped, Commander-legal), each
read in its exact Oracle wording and built on the engine's own grammar for the nearest native wording. CR 2026-09-25.

* Rikala, Homarid King: "Whenever you tap an Island for mana, if there are three or more tide counters on ~, add an additional {U}." — Crypt
  Ghast's triggered mana ability (605.1b, 605.4a: app/rules/tap_mana.py) with its intervening "if" (603.4) read as the mana ability resolves
  (``self_counters_mbc``: the source's own counters).
* Balefang the Unslayable: "target opponent creates a tapped Baneslayer Angel token. The token is goaded for the rest of the game." — a token
  with Baneslayer Angel's characteristics as the reminder text gives them (111.3: {3}{W}{W} 5/5 white Angel, flying, first strike, lifelink,
  protection from Demons and from Dragons), created tapped by that opponent (111.2: under their control), goaded by Balefang's controller
  for the rest of the game (701.15a-b, as "It's goaded for the rest of the game." natively).
* Venser, Visionary Traveler: "Each nontoken creature you control that wasn't cast from your hand enters with two additional +1/+1 counters on
  it." — the entering-counters replacement (614.1c) whose subject leaves out a creature that was a spell cast from your hand (601.2a: the
  cast record of the spell it was, ``not_cast_from_your_hand_mbc``; 400.3: a card in your hand is yours).
* Selenia, the Cursed Heart: "When ~ dies, create a legendary black Aura Curse enchantment token named Selenia's Curse attached to target
  opponent. The token has enchant player and "If enchanted player would lose life, they lose twice that much life instead."" — the token is
  created and enters attached to that player (303.4f, 303.4c: an Aura with enchant player), as the named Aura tokens are (roles.create_role);
  its replacement (614.1a) doubles the life the player it's attached to would lose (``"who": "enchanted"``).
* Flitwing, Lyev Detective: "If you would create one or more tokens, you may create that many Clue tokens instead." — Jinnie Fay's optional
  token replacement (614.1a, 616.1) with one fixed token: the whole creation event, each part's count kept (``mode`` "fixed_mbc").
* Meatsqueak, Hoard Lord: "For every seven Foods you control, Squirrels you control get +3/+3." — the "for each" anthem (613.4c) with the count
  divided by seven, rounded down (107.1a: Sarek's ``every111b``).
* Ekthi, Contaminator Priest: "Each Equipment you control has living weapon." — a keyword grant (613.1f) of living weapon (702.92a: its whole
  meaning is the Equipment's enters trigger, which looks at the Equipment as it is on the battlefield, 603.6a/603.10).
* Elda, Conjurer of Spectacle: "The first nonlegendary creature spell you cast each turn has demonstrate." — Anhelo's "the first <kind> spell
  you cast each turn" (``first`` "kind", 601.2i) with demonstrate (702.144a).
* The Muckslinger Gang: "Each other creature you control gets +3/+3 as long as it's not attacking or blocking." — the native "not attacking"
  subject with "not blocking" too (506.4, Unlikely Alliance's ``not_blocking``). Its second line ("Creature spells you control and creature
  cards you own in any zone other than the battlefield or the stack get +3/+3.") is a layer-7c change outside the battlefield; see
  ``outside_pt``.
* Jandor, Fortuned Traveler: "Each Beast, Camel, Horse, Elephant, and Wolf creature you control is a Mount in addition to its other types and has
  saddle 2." (layer 4 Mount, 205.3m; layer 6 saddle 2, 702.171a) and "Whenever a saddled creature you control attacks, it gets +2/+2 until end
  of turn. Draw a card. Create a Food token." (702.171b: saddled, this turn's log; ``saddled_mbc``).
* Homer, the Hermit: "any number of target players each mill X cards, where X is twice the number of Crabs, Lobsters, Nautiluses, Starfish,
  and/or Trilobites you control." — the native "any number of target players each mill X" with a count of the five creature types.
* Massimo, the Magician: "exile up to one target instant or sorcery card with mana value 1 from your graveyard. If a card is exiled this way, that
  creature gains "Whenever this creature deals combat damage to a player, copy the exiled card. You may cast the copy without paying its mana
  cost."" — the grant names the exiled card's object (607.2a: linked to this resolution; 400.7: a card that left exile is gone), and
  Spellbinder's "copy the exiled card" / free cast (707.12, 608.2g) resolve against it.
* Matoc, Lavamancer: "Whenever a source you control deals damage, if at least one permanent or player was dealt exactly 2 of that damage, …" —
  one trigger per source per damage event (603.2c, 120.2), when at least one recipient's share was exactly 2 (``exact_mbc``).
* Sahir, Visitor in Darkness: eminence (113.6b: "This ability triggers only if Sahir is in the command zone or on the battlefield.", as Edgar
  Markov's) and "Whenever a source you control deals exactly 1 damage to you and whenever a spell or ability you control causes you to lose
  exactly 1 life, …" — one trigger condition with two halves: the damage one (120.3), and a life loss an effect of a spell or ability you control
  made (119.3; not the life damage causes — that is the first half — nor a cost: ``effect_you_mbc``); "the second time this ability has
  resolved this turn" is the native resolution history.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.plan import Plan

Def = dict[str, Any]

RIKALA = "Whenever you tap an Island for mana, if there are three or more tide counters on Rikala, add an additional {U}."
BALEFANG = "When Balefang enters, target opponent creates a tapped Baneslayer Angel token. The token is goaded for the rest of the game."
VENSER = "Each nontoken creature you control that wasn't cast from your hand enters with two additional +1/+1 counters on it."
SELENIA = ("When Selenia dies, create a legendary black Aura Curse enchantment token named Selenia's Curse attached to target opponent. The token "
           "has enchant player and \"If enchanted player would lose life, they lose twice that much life instead.\"")
CURSE_LINE = "If enchanted player would lose life, they lose twice that much life instead."
FLITWING = "If you would create one or more tokens, you may create that many Clue tokens instead."
MEATSQUEAK = "For every seven Foods you control, Squirrels you control get +3/+3."
EKTHI = "Each Equipment you control has living weapon."
ELDA = "The first nonlegendary creature spell you cast each turn has demonstrate."
MUCK_1 = "Each other creature you control gets +3/+3 as long as it's not attacking or blocking."
MUCK_2 = "Creature spells you control and creature cards you own in any zone other than the battlefield or the stack get +3/+3."
JANDOR_1 = ("Each Beast, Camel, Horse, Elephant, and Wolf creature you control is a Mount in addition to its other types and has saddle 2.")
JANDOR_2 = "Whenever a saddled creature you control attacks, it gets +2/+2 until end of turn. Draw a card. Create a Food token."
HOMER = ("Landfall — Whenever a land you control enters, any number of target players each mill X cards, where X is twice the number of Crabs, "
         "Lobsters, Nautiluses, Starfish, and/or Trilobites you control.")
MASSIMO = ("Whenever Massimo or another creature you control enters, exile up to one target instant or sorcery card with mana value 1 from your "
           "graveyard. If a card is exiled this way, that creature gains \"Whenever this creature deals combat damage to a player, copy the exiled "
           "card. You may cast the copy without paying its mana cost.\"")
MATOC = ("Whenever a source you control deals damage, if at least one permanent or player was dealt exactly 2 of that damage, exile the top card "
         "of your library. You may play it until the end of your next turn.")
SAHIR_1 = ("Eminence — At the beginning of your upkeep, Sahir deals 1 damage to you. This ability triggers only if Sahir is in the command zone "
           "or on the battlefield.")
SAHIR_2 = ("Whenever a source you control deals exactly 1 damage to you and whenever a spell or ability you control causes you to lose exactly 1 "
           "life, put a +1/+1 counter on Sahir. If this is the second time this ability has resolved this turn, draw a card.")

_CARDS = {RIKALA: "Rikala, Homarid King", BALEFANG: "Balefang the Unslayable", VENSER: "Venser, Visionary Traveler",
          SELENIA: "Selenia, the Cursed Heart", MASSIMO: "Massimo, the Magician", MATOC: "Matoc, Lavamancer",
          SAHIR_1: "Sahir, Visitor in Darkness", SAHIR_2: "Sahir, Visitor in Darkness"}

BANESLAYER: Def = {"name": "Baneslayer Angel", "power": "5", "toughness": "5", "colors": ["W"], "type_line": "Token Creature — Angel",
              "text": "Flying, first strike, lifelink, protection from Demons and from Dragons", "mana_cost": "{3}{W}{W}"}
CURSE_TOKEN: Def = {"name": "Selenia's Curse", "power": None, "toughness": None, "colors": ["B"],
               "type_line": "Legendary Token Enchantment — Aura Curse", "text": f"Enchant player\n{CURSE_LINE}"}
CLUE: Def = {"name": "Clue", "power": None, "toughness": None, "colors": [], "type_line": "Token Artifact — Clue",
        "text": "{2}, Sacrifice this token: Draw a card."}
JANDOR_TYPES = ("Beast", "Camel", "Horse", "Elephant", "Wolf")
HOMER_TYPES = ("Crab", "Lobster", "Nautilus", "Starfish", "Trilobite")
# the ability Massimo's trigger gives, bound to the exiled card's object (607.2a): read back by ``definition``
MASSIMO_GRANT = ("Whenever this creature deals combat damage to a player, copy the exiled card ‹massimo#{oid}›. You may cast the copy without paying "
                 "its mana cost.")
_MASSIMO_GRANTED = re.compile(r"^Whenever (?:this creature|this permanent|~) deals combat damage to a player, copy the exiled card ‹massimo#(?P<oid>[^›]+)›\. "
                              r"You may cast the copy without paying its mana cost\.$")


def _native(ability: Any, ch: Characteristics, text: str) -> Def | None:
    from app.rules import scripts

    return scripts.define(replace(ability, text=text), ch)


def _sel(key: str, **changes: Any) -> str:
    from app.rules import selectors

    sel = selectors.from_key(key)
    extras = changes.pop("extras", ())
    return replace(sel, **changes, extras=(*sel.extras, *extras)).key()


def _own(text: str, ch: Characteristics, printed: str) -> bool:
    """Is ``text`` this card's line ``printed`` (its name written as ~, 201.4b)?"""
    from app.rules import scripts

    card = _CARDS.get(printed)
    if card is not None and ch.name != card:
        return False
    return scripts.self_text(text, ch.name) == scripts.self_text(printed, card or ch.name)


def definition(ability: Any, ch: Characteristics) -> Def | None:
    from app.rules import scripts

    text = ability.text.strip()
    if text == CURSE_LINE and ability.kind == "static":  # (Selenia's Curse: the player it's attached to, 303.4c)
        return {"kind": "static", "static": "replace", "event": "life_loss", "match": {"who": "enchanted"}, "op": {"do": "mul", "n": 2}, "effects": []}
    if (m := _MASSIMO_GRANTED.match(scripts.self_text(text, ch.name))) is not None and ability.kind == "triggered":
        base = _native(ability, ch, "Whenever ~ deals combat damage to a player, draw a card.")
        if base is None:
            return None
        return {**base, "effects": [{"do": "massimo_bind_mbc", "oid": m["oid"], "as": "mx"},
                                    {"do": "copy_cards", "who": "ref:mx", "as": "e1"},
                                    {"do": "free_cast", "zone": "that", "who": "ref:e1", "filter": None, "optional": True, "mv": None, "n": 1}]}
    if ability.kind == "static":
        return _static(ability, ch, text)
    if ability.kind == "triggered":
        return _triggered(ability, ch, text)
    return None


def _static(ability: Any, ch: Characteristics, text: str) -> Def | None:
    from app.rules import scripts

    plain = scripts.self_text(text, ch.name)
    if plain == VENSER:
        d = _native(ability, ch, "Each nontoken creature you control enters with two additional +1/+1 counters on it.")
        if d is None or d.get("event") != "counters":
            return None
        on = d["match"]["on"]
        return {**d, "match": {**d["match"], "on": {**on, "sel": _sel(on["sel"], extras=("not_cast_from_your_hand_mbc",))}}}
    if plain == FLITWING:
        return {"kind": "static", "static": "replace", "event": "tokens", "match": {"who": "you"},
                "op": {"do": "token_characteristics", "mode": "fixed_mbc", "optional": True, "group_tokens": True, "token": dict(CLUE)}, "effects": []}
    if plain == MEATSQUEAK:
        d = _native(ability, ch, "Squirrels you control get +3/+3 for each Food you control.")
        if d is None or not d.get("each"):
            return None
        return {**d, "each": {**d["each"], "value": {"every111b": [7, d["each"]["value"]]}}}
    if plain == EKTHI:
        d = _native(ability, ch, "Equipment you control have fabricate 1.")
        return None if d is None else {**d, "grants": ["Living weapon"]}
    if plain == ELDA:
        from app.rules import cast_limits

        ok, key = cast_limits._first_filter("nonlegendary creature")
        if not ok or key is None:
            return None
        return {"kind": "static", "static": "spell_keyword", "keyword": "demonstrate", "count": 1, "filter": key, "from": None, "first": "kind",
                "effects": []}
    if plain == MUCK_1:
        d = _native(ability, ch, "Each other creature you control gets +3/+3 as long as it's not attacking.")
        if d is None or "not_attacking" not in d.get("who", ""):
            return None
        return {**d, "who": _sel(d["who"], extras=("not_blocking",))}
    if plain == MUCK_2:
        # 611.3a, 613.4c: a characteristic change of cards outside the battlefield (``outside_pt``, applied by layers._derive)
        return {"kind": "static", "static": "outside_pt_mbc", "p": 3, "t": 3, "effects": []}
    if plain == JANDOR_1:
        d = _native(ability, ch, "Each Beast creature you control is a Mount in addition to its other types.")
        if d is None or not d.get("layer4"):
            return None
        return {**d, "who": _sel(d["who"], subtypes=JANDOR_TYPES), "grants": ["Saddle 2"]}
    return None


def _triggered(ability: Any, ch: Characteristics, text: str) -> Def | None:
    from app.rules import scripts, tap_mana

    plain = scripts.self_text(text, ch.name)
    if _own(text, ch, RIKALA):
        d = tap_mana.definition("Whenever you tap an Island for mana, add an additional {U}.")
        return None if d is None else {**d, "self_counters_mbc": ["tide", 3]}
    if _own(text, ch, BALEFANG):
        d = _native(ability, ch, "When ~ enters, target opponent creates a 5/5 white Angel creature token with flying. It's goaded for the rest of the game.")
        if d is None or [e.get("do") for e in d["effects"]] != ["create_token", "goad"]:
            return None
        made, goad = d["effects"]
        return {**d, "effects": [{**made, "token": dict(BANESLAYER), "tapped": True}, goad]}
    if _own(text, ch, SELENIA):
        d = _native(ability, ch, "When ~ dies, target opponent loses 1 life.")
        return None if d is None else {**d, "effects": [{"do": "curse_token_mbc", "who": "target"}]}
    if plain == scripts.self_text(JANDOR_2, ch.name):
        d = _native(ability, ch, "Whenever a creature you control attacks, it gets +2/+2 until end of turn. Draw a card. Create a Food token.")
        if d is None or (d.get("cond") or {}).get("event") != "attack":
            return None
        return {**d, "cond": {**d["cond"], "sel": _sel(d["cond"]["sel"], extras=("saddled_mbc",))}}
    if plain == scripts.self_text(HOMER, ch.name):
        d = _native(ability, ch, "Whenever a land you control enters, any number of target players each mill X cards, where X is twice the number of "
                                 "Crabs you control.")
        if d is None or [e.get("do") for e in d["effects"]] != ["mill"]:
            return None
        mill = d["effects"][0]
        times = mill["n"]["times"]
        return {**d, "effects": [{**mill, "n": {"times": [times[0], {"count": _sel(times[1]["count"], subtypes=HOMER_TYPES)}]}}]}
    if _own(text, ch, MASSIMO):
        d = _native(ability, ch, "Whenever ~ or another creature you control enters, exile up to one target instant or sorcery card with mana value 1 "
                                 "from your graveyard.")
        if d is None or [e.get("do") for e in d["effects"]] != ["exile"]:
            return None
        return {**d, "effects": [{**d["effects"][0], "as": "mx"}, {"do": "massimo_mbc", "ref": "mx"}]}
    if _own(text, ch, MATOC):
        d = _native(ability, ch, "Whenever a source you control deals damage to one or more permanents and/or players, exile the top card of your "
                                 "library. You may play it until the end of your next turn.")
        if d is None or (d.get("cond") or {}).get("event") != "deal_damage":
            return None
        return {**d, "cond": {**d["cond"], "exact_mbc": 2}}
    if _own(text, ch, SAHIR_1):
        return _native(ability, ch, "At the beginning of your upkeep, if ~ is in the command zone or on the battlefield, ~ deals 1 damage to you.")
    if _own(text, ch, SAHIR_2):
        d = _native(ability, ch, "Whenever a source you control deals damage to you and whenever you lose life, put a +1/+1 counter on ~. If this "
                                 "is the second time this ability has resolved this turn, draw a card.")
        cond = (d or {}).get("cond") or {}
        if d is None or cond.get("event") != "either" or [c.get("event") for c in cond["conds"]] != ["deal_damage", "lose_life"]:
            return None
        hurt, loss = cond["conds"]
        return {**d, "cond": {**cond, "conds": [{**hurt, "exact_mbc": 1}, {**loss, "exact_mbc": 1, "effect_you_mbc": True}]}}
    return None


# -- resolution ---------------------------------------------------------------------------------------------------------------------------------
def curse_token(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Selenia: create the curse token, which enters attached to the target opponent (303.4f, 303.4c); with no legal player left (608.2b) or
    a token it can't be attached to (a replacement made something else, 303.4i: a non-Aura isn't attached), nothing is attached."""
    from app.rules import attachments, effects
    from app.rules import replace as repl

    players = [p for p in effects._players(plan, ctx, e.get("who") or "target") if p in plan.live()]
    if not players:
        plan.note(f"{ctx.get('name') or 'Selenia'}: no opponent to attach the curse to", actor=ctx["controller"])
        return True
    source = ctx.get("source_card") if ctx.get("source_card") in plan.state.cards else None
    made = repl.create_tokens(plan, ctx["controller"], dict(CURSE_TOKEN), 1, source=source, ctx=ctx, then=repl.rerun_then(ctx, e))
    if made is None:
        return False
    for tid in made:
        attachments.attach(plan, tid, players[0], ctx["controller"])
    return True


def massimo(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """"If a card is exiled this way, that creature gains …": the card the exile moved, in exile now (400.7), and the creature that entered."""
    from app.rules import context
    from app.rules.effects import PRIMITIVES as EFFECTS

    exiled = [c for c in context.objects(plan, ctx, e["ref"]) if c in plan.state.cards and plan.state.cards[c].zone.endswith(":exile")]
    if not exiled:
        return True
    oid = plan.oid(plan.state.cards[exiled[0]])
    return bool(EFFECTS["grant"](plan, ctx, {"do": "grant", "who": "event", "keywords": [], "duration": "permanent",
                                             "abilities": [MASSIMO_GRANT.format(oid=oid)]}))


def massimo_bind(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """"the exiled card": the card Massimo's trigger exiled, while it is still that object in exile (400.7)."""
    from app.rules import context

    found = [c.id for c in plan.state.cards.values() if c.zone.endswith(":exile") and plan.oid(c) == e["oid"]]
    context.bind_objects(plan, ctx, e["as"], found[:1])
    return True


PRIMITIVES: dict[str, Any] = {"curse_token_mbc": curse_token, "massimo_mbc": massimo, "massimo_bind_mbc": massimo_bind}


# -- The Muckslinger Gang's second line (613.4c outside the battlefield) ---------------------------------------------------------------------------
# Applied by layers._derive to a card outside the battlefield once its layer 7 is done.
_MUCK_PHRASE = "creature cards you own in any zone other than the battlefield or the stack get +3/+3"


def outside_pt(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None) -> Characteristics:
    """"Creature spells you control and creature cards you own in any zone other than the battlefield or the stack get +3/+3." (611.3a: a static
    ability of a permanent that affects objects outside the battlefield; 613.4c: layer 7c, after the object's own 7a-7c): a creature spell its
    controller controls, a creature card its owner owns in a hand, library, graveyard, exile or the command zone (not face down: 708.2 — no
    characteristics to change), +3/+3 for each such ability of a permanent that player controls (with its abilities now, 613.1f)."""
    if info is None or state.rules is None or ch.pt is None or not ch.is_creature or card.zone.endswith(":battlefield") or card.face_down:
        return ch
    if card.zone == "stack" and card.ability is not None:
        return ch
    who = card.controller if card.zone == "stack" else card.owner
    from app.rules import characteristics as chars
    from app.rules import scripts

    n = 0
    for cid in state.zones.get(f"{who}:battlefield", ()):
        c = state.cards.get(cid)
        if c is None or c.face_down or _MUCK_PHRASE not in chars.of(c, info).oracle_text:
            continue
        from app.rules.layers import derive

        now = derive(state, c, chars.of(c, info), info)  # (with its abilities now: one that lost them gives nothing, 613.1f)
        n += sum(1 for a in now.abilities if a.kind == "static" and scripts.self_text(a.text, now.name) == MUCK_2)
    if not n:
        return ch
    from app.rules.characteristics import evolve

    p, t = ch.pt
    return evolve(ch, pt=(p + 3 * n, t + 3 * n))
