"""Trigger conditions as data: "When/Whenever [subject] [event]" (CR 603.2, 603.6, 603.10).

Researched against the Comprehensive Rules of 2026-09-25 (data/rules/comprehensive_rules/).

A condition is a dict:

* ``event``: "enter" | "die" | "leave" | "attack" | "unblocked" | "block" | "blocked" | "tapped" |
  "untapped" | "dealt_damage" | "deal_combat_damage_player" | "deal_damage_opponent" | "deal_damage" |
  "gain_life" | "lose_life" | "cast" | "draw" | "you_attack" | "sacrifice" | "discard" | "cycle" |
  "create_token" | "counters_put" | "leave_graveyard" | "targeted" | "attached" | "unattached" | "multi";
* ``subject``: "self" (this object), "self_or" (this object or another matching ``sel``), "sel"
  (any object matching ``sel``), "host" (the permanent this Aura / Equipment is attached to:
  "enchanted creature", "equipped creature"), "self_or_host" ("~ or equipped creature"), or "player"
  (a player matching ``player``: "you" / "opponent" / "any");
* ``sel``: a selector key (app/rules/selectors.py); ``spell``: a selector key for cast spells;
  ``obj``: a selector key for the object a player acted on (the permanent sacrificed, the card
  discarded or cycled, the token created); ``other``: the creature on the other side of a block
  (509.3b "blocks a creature", 509.3d "becomes blocked by a creature");
* ``aggregate``: "one or more …" — one trigger per event batch, however many objects (603.2c);
* ``nth``: "your second card / spell each turn" (the Nth such event this turn);
* ``alone``: "attacks alone" (506.5: the only creature declared as an attacker);
* attack / you_attack / unblocked: ``defender`` — whom the attack was declared against (508.3a,
  508.3b, 508.3e, 508.6): "you" (you, the player — not a planeswalker you control), "you_or_pw" ("you
  or a planeswalker you control"), "player" ("attacks a player"), "opponent" ("one of your
  opponents"), "enchanted_player" (702.5d); "unblocked" is "attacks and isn't blocked" (509.3g: no
  creature was declared as a blocker for it, checked as the declare blockers step's blocks are
  done; also for a creature put onto the battlefield attacking); ``first_each_turn``: "attacks for
  the first time each turn"; ``while``: "attacks while you control …" (app/rules/conditions.py) —
  part of the trigger event, read as it triggers (603.2; 603.4's second check is for an "if" that
  follows the trigger condition only);
* ``min_attackers``: "~ and at least two other creatures attack" (3), "you attack with three or
  more creatures" (3): how many creatures were declared as attackers;
* cast only: ``turn`` ("opponent": during an opponent's turn), ``from`` ("exile" | "graveyard" |
  "hand" | "not_hand": the zone the spell was cast from), ``targets`` ("self" or a selector key:
  a spell that targets it, 115.9b), ``kicked``;
* targeted only: ``by`` ("any" | "opponent" | "you": who controls the spell or ability), ``spell_only``
  (a spell, not an ability), ``spell_sel`` (the kind of spell: a selector key, wave 22E), ``first_each_turn`` ("for the first time
  each turn"); its subject may be a player ("you becomes the target": ``subject`` "player");
* enter / land_played only: ``entered_from`` ("exile" | "graveyard" | "your graveyard" | "your hand" | "not_hand": the zone it was put onto
  the battlefield from, 603.6a, 701.18a; wave 22E, 30F);
* counters_put only: ``counter`` (the kind, or None for any);
* deal_damage only: ``to`` ("any" | "player" | "opponent" | "creature" | "you" | "planeswalker" |
  "player_or_pw" | "player_or_battle" | "enchanted_player"), ``combat`` (True: only combat damage, False: only noncombat
  damage, None: any), ``min`` ("deals 6 or more damage to an opponent": the damage one source dealt that one recipient in one event); dealt_damage: ``combat``
  likewise ("~ is dealt combat damage"), with a player subject for damage dealt to a player ("you're dealt combat damage"); ``excess`` (wave 39B, 120.10:
  "is dealt excess [noncombat] damage": the damage event of a permanent has the excess its sources together dealt, the event's amount is that excess);
  ``first_each_turn`` (wave 39B, 603.2: this object's first such damage / combat damage to a player / counters put on it this turn, asked of the turn's log);
* attached / unattached (wave 30S, 603.2e, 701.3d): the Aura / Equipment is the subject; ``other`` the permanent it became attached to / let go of
  (a selector key, the one "on the other side" for "that creature" / "that permanent"), ``to`` "self": it became attached to this object;
* multi: ``events`` (each a trigger event of this object: "When ~ enters or dies", 603.2).

:func:`parse_condition` reads the wording; anything it doesn't read returns None (the ability
stays manual). Matching happens in app/rules/triggers.py against the event log.
"""

from __future__ import annotations

import re
from typing import Any

from app.rules import selectors

Condition = dict[str, Any]


class _Refuse(Exception):
    """A wording this grammar recognizes but doesn't model: the ability stays manual (never a guess)."""


_EVENT_VERBS = [
    (r"enters?", "enter"),
    (r"dies|die", "die"),
    (r"leaves? the battlefield", "leave"),
    (r"is put into a graveyard from the battlefield|are put into a graveyard from the battlefield", "die"),
    (r"attacks?", "attack"),
    (r"blocks?", "block"),
    (r"becomes? blocked", "blocked"),
    (r"(?:is|are) turned face up", "turned_face_up"),  # -- hidden exile (wave 18A) -- 702.37e, 701.40b: a face-down permanent turned face up
    (r"becomes? tapped", "tapped"),
    (r"becomes? untapped", "untapped"),
    (r"(?:is|are) dealt damage", "dealt_damage"),
    (r"deals? combat damage to a player", "deal_combat_damage_player"),
    (r"deals? combat damage to an opponent", "deal_combat_damage_player"),
    (r"deals? damage to an opponent", "deal_damage_opponent"),
]
# "~ deals [combat / noncombat] damage [to a creature / player / you]" (120.1, 510.2)
# ("to a player or battle": a battle is dealt damage like a planeswalker, 120.3h — it can be
# attacked, 310.5, and targeted by "any target" spells)
_DAMAGE_TO = {"": "any", " to a player": "player", " to a creature": "creature", " to an opponent": "opponent",
              " to you": "you", " to a player or planeswalker": "player_or_pw", " to a planeswalker": "planeswalker",
              " to one of your opponents": "opponent", " to enchanted player": "enchanted_player",
              " to a player or battle": "player_or_battle",
              # -- source damage (wave 11F) -- 603.2c: "to one or more players" is one trigger for the whole batch
              " to its owner": "its_owner",  # -- trigger other (wave 44B) -- 120.1: The Beast, "a creature deals combat damage to its owner" (the damage dealer's owner is the player)
              " to one or more players": "players", " to your opponents": "opponents",
              " to one or more of your opponents": "opponents", " to ~": "self", " to one or more creatures": "creatures"}
_ONE_OR_MORE_TO = (" to one or more players", " to your opponents", " to one or more of your opponents")  # (wave 39B)
_DAMAGE_TO_RE = "|".join(re.escape(k) for k in sorted(_DAMAGE_TO, key=len, reverse=True) if k)
# 508.3a / 508.3b / 508.3e / 508.6: whom an attack was declared against
_DEFENDERS = {"you": "you", "you or a planeswalker you control": "you_or_pw", "a player": "player",
              "you and/or one or more planeswalkers you control": "you_or_pw",  # (-- as long as (wave 37A) -- 508.3e: Cunning Rhetoric; once per player attacked)
              "one of your opponents": "opponent", "one or more of your opponents": "opponent_any",
              "another one of your opponents": "other_opponent", "enchanted player": "enchanted_player",
              "the player with the most life or tied for most life": "most_life",  # (wave 15E: dethrone, 702.105a)
              # -- trigger other (wave 36A) -- 508.3a: "attacks one of your opponents or a planeswalker an opponent controls" (Gahiji): any attack on an opponent
              # or on what an opponent controls (a planeswalker's controller is the defending player, 508.5)
              "one of your opponents or a planeswalker an opponent controls": "opponent_or_pw",
              "one of your opponents or a planeswalker they control": "opponent_or_pw",
              "the monarch": "monarch"}  # -- this-turn state (wave 42B) -- 725.1, 508.3a: the player who is the monarch, attacked directly (Okoye, The Spear of Bashenga)
_DEFENDER_RE = "|".join(re.escape(k) for k in sorted(_DEFENDERS, key=len, reverse=True))
_PLAYER_VERBS = [
    (r"gains? life", "gain_life"),
    (r"loses? life", "lose_life"),
    (r"draws? a card", "draw"),
    (r"attacks?", "you_attack"),
]
_PLAYERS = {"you": "you", "an opponent": "opponent", "a player": "any", "each opponent": "opponent",
            "enchanted player": "enchanted"}  # (wave 16F: a Curse's "enchanted player")
_NTH = {"second": 2, "third": 3, "first": 1, "fourth": 4, "fifth": 5}
_COUNT = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}  # (wave 22E: eight …)
_MULTI = {"enters": "enter", "dies": "die", "attacks": "attack", "leaves the battlefield": "leave", "blocks": "block",
          "becomes blocked": "blocked", "becomes tapped": "tapped", "becomes untapped": "untapped",
          "is dealt damage": "dealt_damage",
          "is put into a graveyard from the battlefield": "die",  # (700.4; wave 5D: Ichor Wellspring)
          "deals combat damage to a player": "deal_combat_damage_player",  # (wave 17D: Park Heights Maverick)
          "is turned face up": "turned_face_up",  # -- face up (wave 6D) -- "~ enters or is turned face up" (702.37e)
          # -- trigger other (wave 36A) -- a plural name takes the plural verb ("Whenever Bebop & Rocksteady attack or block", "Krang & Shredder enter
          # or attack"): one object (201.5: the name is the object's own), the same events
          "enter": "enter", "die": "die", "attack": "attack", "block": "block", "deal combat damage to a player": "deal_combat_damage_player"}
_MULTI_RE = "|".join(sorted((re.escape(k) for k in _MULTI), key=len, reverse=True))
_P = r"(?P<p>you|an opponent|a player|enchanted player)"
# -- counters & designations (wave 3E) -- a player getting counters (122.6; one event per player per instruction)
_GETS_COUNTERS = re.compile(r"(?P<p>you|an opponent|a player) gets? (?:one or more (?P<e>\{E\})|(?:one or more|an?) "
                            r"(?P<k>poison|experience|rad) counters?)")
# designations (app/rules/designations.py): "you become the monarch" (725; only a player who wasn't the monarch
# becomes it), "a player takes the initiative" (726.5: also one who had it), "the Ring tempts you" (701.54d),
# "you choose a creature as your Ring-bearer" (701.54a), "you complete a dungeon" (309.7), "day becomes night or
# night becomes day" (731.1a)
_DESIGNATION_EVENTS = [
    (re.compile(r"(?P<p>you|an opponent|a player) becomes? the monarch"), "become_monarch"),
    (re.compile(r"(?P<p>you|an opponent|a player) takes? the initiative"), "take_initiative"),
    (re.compile(r"the ring tempts (?P<p>you)", re.IGNORECASE), "ring_tempts"),
    (re.compile(r"(?P<p>you) choose a creature as your ring-bearer", re.IGNORECASE), "ring_bearer"),
    (re.compile(r"(?P<p>you) complete a dungeon"), "complete_dungeon"),
    (re.compile(r"(?P<p>you) proliferate"), "proliferate"),  # -- trigger tail (wave 15B) -- 701.34a
    (re.compile(r"(?P<p>you) fully unlock a room", re.IGNORECASE), "fully_unlock"),  # -- ability words (wave 20C) -- 709.5i (rooms.unlock)
    (re.compile(r"a spell or ability (?P<p>you) control counters a spell"), "counters_spell"),  # -- counter events (wave 19C) -- 701.6a
    (re.compile(r"(?P<p>you|an opponent|a player) commits? a crime"), "commit_crime"),  # -- crimes (wave 6D) -- 700.13
    (re.compile(r"day becomes night or night becomes day"), "day_night"),
    (re.compile(r"(?P<p>you) forage"), "forage"),  # -- if you do (wave 26C) -- 701.61: the cost was paid (cost_payment.pay)
    (re.compile(r"(?P<p>you) collect evidence"), "collect_evidence"),  # 701.59
    # -- most-played cards (wave 43B) -- 701.23: "Whenever an opponent searches their library" (Archivist of Oghma, Wan Shi Tong, Ob Nixilis, Unshackled): a search of
    # the searcher's OWN library (the rulings: not one of your search of an opponent's library, nor an opponent's of another player's)
    (re.compile(r"(?P<p>an opponent|a player) searches their library"), "search_library"),
]
# "enchanted creature", "equipped creature" …: the permanent the source is attached to (303.4, 301.5)
_HOSTS = ("enchanted creature", "equipped creature", "enchanted permanent", "enchanted land", "enchanted artifact")
_SELF_OR_HOST = ("~ or equipped creature", "~ or enchanted creature")


def parse_condition(cond: str) -> Condition | None:
    """The part between "When/Whenever" and the comma → a condition, or None."""
    # -- attached events (wave 25D) -- the Genju: "When enchanted Forest is put into a graveyard" — what an Aura is attached to is on the battlefield,
    # so being put into a graveyard is dying (700.4); "enchanted Forest" is the land it's attached to
    cond = re.sub(r"\benchanted (?:Plains|Island|Swamp|Mountain|Forest)\b", "enchanted land", cond)
    cond = re.sub(r"^(enchanted (?:creature|permanent|land|artifact)) is put into a graveyard(?: from the battlefield)?$", r"\1 dies", cond.strip())
    try:
        try:
            found = _parse(cond.strip())
        except _Refuse:  # (a trailing qualifier can be what the plain reading refused: "… a permanent during your turn")
            found = None
        found = found or _qualified(cond.strip())
    except _Refuse:
        return None
    # -- grammar (wave 11C) -- 700.9: "a modified creature you control dies / leaves" would read its Auras and Equipment after
    # they let go of it (704.5n): not modelled, so the ability stays manual (counters alone are kept in its last known info)
    # (-- trigger other (wave 25B) -- a plain "a modified creature you control dies / leaves" is read from the object's last known
    # information: the counters and attachments it had as it left, 603.10a: triggers._was_modified)
    if found is not None and found.get("event") in ("die", "leave", "either", "multi") and re.search(
            r"enchanted_or_equipped" if found.get("event") in ("die", "leave") and found.get("subject") in ("sel", "self_or") and not found.get("aggregate") else
            r"modified|enchanted_or_equipped", str(found)):
        return None
    # -- history (wave 22E) -- 701.15b: a goaded creature is read live, as it attacks; an object that has left (a creature that died as it
    # dealt damage, or dies) is rebuilt from its last known information, which doesn't keep the goad: such triggers stay manual
    if found is not None and "goaded" in str(found) and not (found.get("event") == "attack" and found.get("subject") == "sel"):
        return None
    return found


def _qualified(c: str) -> Condition | None:
    """-- trigger qualifiers (wave 11C) -- "… during your turn" / "during an opponent's turn" / "during their turn" (the acting
    player's own): the turn it happens in is part of the trigger event (603.2), read as it happens (triggers._cond_matches);
    "you gain / lose life", "you create one or more tokens" "for the first time each turn" (also "during each of your
    turns"): the first such event of that player this turn, kept per player per turn whoever is watching, so an object that
    entered later this turn still sees the earlier ones (triggers._generic_events)."""
    during = first = wh = None
    # -- counters (wave 33C) -- "Whenever another creature you control enters while this creature has a -1/-1 counter on it" (Bristlebane Battler,
    # Reluctant Dounguard, Moonshadow), "… becomes tapped while it has a -1/-1 counter on it" (Encumbered Reejerey): part of the trigger event,
    # read as it happens (603.2; not an "if" after the comma, so 603.4's second look on resolution doesn't apply), as ``while`` on an attack
    # (-- counters (wave 41A) -- also "… deal combat damage to you while you're the monarch" (Tamiyo, Upriser Crowned): the watcher's controller's designation as it
    # happens, 724.1)
    m = re.fullmatch(r"(?P<c>.+?) while (?P<w>(?:~|it) has (?:an?|one or more|\w+ or more) (?:\+1/\+1|-1/-1|[a-z]+) counters? on (?:it|~)|you're the monarch)", c)
    if m:
        c, wh = m["c"], m["w"]
    m = re.fullmatch(r"(?P<c>.+?) during (?P<t>your|an opponent's|their) turn", c)
    if m:
        c, during = m["c"], {"your": "you", "an opponent's": "opponent", "their": "their"}[m["t"]]
    m = re.fullmatch(r"(?P<c>.+?) for the first time (?P<w>each turn|during each of your turns|during each of their turns)", c)
    first_each = False
    if m:
        c, first = m["c"], True
        first_each = m["w"] == "each turn"
        if m["w"] != "each turn":
            during = "you" if m["w"].endswith("your turns") else "their"
    if during is None and first is None and wh is None:
        return None
    inner = _parse(c)
    if inner is None and during and re.search(r" (?:second|third|fourth|fifth) ", c):
        inner = _parse(f"{c} each turn")  # ("their second card during their turn": the Nth this turn, as "… each turn")
    if inner is not None and during == "their" and inner.get("subject") != "player":
        return None  # ("their" is the acting player's: only a player subject has one)
    # (-- counters (wave 33C) -- "Whenever an opponent loses life for the first time during each of their turns" (Valgavoth, Harrower of Souls): each such
    # player's first this turn, which must be their own turn)
    # (-- trigger damage (wave 39B) -- 603.2: "~ is dealt damage / deals combat damage to a player / has counters put on it for the first time each turn" (Hercules,
    # Raphael, Axgard Artisan, Danny Pink): this object's first such event this turn, asked of the turn's log (triggers._first_of); a granted ability is its own
    # object's, so only a ``self`` subject, and not "during each of your turns")
    own_first = first and not during and inner is not None and inner.get("subject") == "self" and not inner.get("aggregate") \
        and inner.get("event") in ("dealt_damage", "deal_combat_damage_player", "counters_put")
    # (-- this-turn state (wave 42B) -- 603.2: "Whenever a creature you control becomes tapped / one or more counters are put on a creature you control for the
    # first time each turn" (Captain America, Stalwart Successor): the first such event of THE OBJECT it is about (the event's, not the watcher's), asked the same way;
    # "during your turn" is a separate qualifier of the event)
    obj_first = first and first_each and inner is not None and inner.get("subject") == "sel" and not inner.get("aggregate") \
        and inner.get("event") in ("tapped", "counters_put")
    if inner is None or (first and not own_first and not obj_first and (inner.get("event") not in ("gain_life", "lose_life", "create_token", "discard")
                                                      or inner.get("subject") != "player"
                                                      or inner.get("player") not in (("opponent", "any") if during == "their" else ("you",)))):
        return None
    if first and inner.get("event") == "discard":  # -- trigger other (wave 36A) -- the cards of earlier discards are asked of the turn's log: only what it records
        # (the log records a discarded card's types, subtypes and supertypes: a filter on anything else, a color or a mana value, isn't asked of it)
        plain = selectors.replace(selectors.from_key(inner["obj"]), card=False, zones=selectors.Selector().zones, types=(), not_types=(), subtypes=(), not_subtypes=(),
                                  supertypes=(), not_supertypes=())
        if during or plain != selectors.Selector():
            return None
    holds = None
    if wh is not None:  # ("it" is this creature only when the event is about this creature itself)
        from app.rules import conditions

        holds = conditions.parse(re.sub(r"^it ", "~ ", wh) if inner is not None and inner.get("subject") == "self" else wh, objects=True)
        if holds is None or (holds.get("object") != "self" and (holds.get("value") or {}).get("on") != "self" and holds != {"status": "monarch"}):
            return None
    return {**inner, **({"during": during} if during else {}), **({"first_each_turn": True} if first else {}),
            **({"while": holds} if holds else {})}


def _object_sel(phrase: str, *, card: bool = False) -> str:
    """"a creature" / "another creature" / "a creature card" / "a token" → a selector key (the
    object an action was done to); ``card``: a card in a zone other than the battlefield."""
    p = re.sub(r"^(?:an?|one or more) ", "", phrase.strip())
    if p in ("card", "cards"):
        return selectors.Selector(card=True, zones=()).key()
    sel = _token_or_sel(p) if not card else selectors.parse(p)
    if sel is None or sel.player is not None or sel.card != card:
        raise _Refuse
    return sel.key()


def _count(word: str) -> int:
    if word.isdigit():
        return int(word)
    if word not in _COUNT:
        raise _Refuse
    return _COUNT[word]


# -- trigger from (wave 30F) -- where a played land / an entering permanent came from (history.entered_from's names)
_ENTERED_FROM = {"your graveyard": "your graveyard", "a graveyard": "graveyard", "exile": "exile", "your hand": "your hand",
                 "anywhere other than your hand": "not_hand", "anywhere other than their hand": "not_hand"}
_PLAY_FROM = r" from (?:exile|your graveyard|a graveyard|anywhere other than (?:your|their) hand)"


def _parse(c: str) -> Condition | None:
    # -- trigger other (wave 25B) -- 701.18b: to play a card is to play it as a land or cast it as a spell, whichever is appropriate
    # (-- trigger from (wave 30F) -- "Whenever you play a card from exile" (Prosper): a land played from there or a spell cast from there)
    m = re.fullmatch(rf"(?P<p>you|a player|an opponent) plays? a card(?P<f>{_PLAY_FROM})?", c)
    if m:
        you, f = m["p"] == "you", m["f"] or ""
        return _parse(f"{m['p']} {'play' if you else 'plays'} a land{f} or {'cast' if you else 'casts'} a spell{f}")
    # -- triggers (wave 19B) -- "your commander attacks / enters / deals combat damage to a player" is "a commander you control …"
    # (903.3: a commander its owner's deck names; the selector reads it on the battlefield), "you attack with your commander" /
    # "~ attacks an opponent" (the one of your opponents the attack is declared against, 508.3a)
    m = re.fullmatch(r"your commander (?P<rest>.+)", c)
    if m or c == "you attack with your commander":
        found = _parse(f"a commander you control {m['rest']}" if m else "you attack with one or more commanders you control")
        for part in ([found] if found else []) + list((found or {}).get("conds") or []):  # ("enters or attacks": each half)
            if part.get("sel"):  # (your own: a commander you own, as "you control your commander" reads it; review 19: whoever
                part["sel"] = selectors.replace(selectors.from_key(part["sel"]), owner="you",  # controls it, 903.3 / 903.3d)
                                                controller=None if m else "you").key()
        return found
    if c.endswith(" attacks an opponent"):
        return _parse(c[: -len("an opponent")] + "one of your opponents")
    # -- history (wave 22E) -- "When ~ enters from a graveyard", "Whenever a creature enters from your graveyard": the zone it came from
    # is part of the event (603.2; the engine records it with the entry: rules_state.Entry.from_zone)
    m = re.fullmatch(r"(?P<s>.+?) enters?(?: the battlefield)? from (?P<z>your graveyard|a graveyard|exile|your hand|anywhere other than your hand)", c)
    inner = _parse(f"{m['s']} enters") if m else None
    # (wave 30F: a subject that is no one object but "A or B" — "you cast a spell from exile or a land you control enters from exile" — is read by the split below)
    if m and inner is not None and not (inner["event"] == "either" and any(x["event"] != "enter" for x in inner["conds"])):
        if inner.get("event") not in ("enter", "either") or inner.get("aggregate"):
            return None
        if inner["event"] == "either":
            return {**inner, "conds": [{**x, "entered_from": _ENTERED_FROM[m["z"]]} for x in inner["conds"]]}
        return {**inner, "entered_from": _ENTERED_FROM[m["z"]]}
    # -- entry forms (wave 11F) -- "Whenever a creature enters [the battlefield] under your control" is "a creature you control
    # enters" (603.6a: an object entering the battlefield, under that player's control); "under an opponent's control":
    # "an opponent controls". (A permanent "an opponent owns" is another thing: not read.)
    m = re.fullmatch(r"(?P<s>.+?) (?P<v>enters?) (?:the battlefield )?under (?P<w>your|an opponent's) control", c)
    if m and not re.search(r"\b(?:controls?|owns?)\b", m["s"]):
        return _parse(f"{m['s']} {'you control' if m['w'] == 'your' else 'an opponent controls'} {m['v']}")
    # -- trigger damage (wave 39B) -- 120.10: "Whenever a creature or planeswalker an opponent controls is dealt excess damage" (Aegar), "… excess noncombat
    # damage" (Toralf): a permanent was dealt damage, and the sources of that event together dealt more than was lethal (the excess is on the damage event,
    # replace.do_damage); a player is dealt no excess damage
    m = re.fullmatch(r"(?P<s>.+?) (?:is|are) dealt excess (?P<c>noncombat |combat )?damage", c)
    if m:
        inner = _parse(f"{m['s']} is dealt {m['c'] or ''}damage")
        if inner is None or inner.get("event") != "dealt_damage" or inner.get("subject") in ("player", "host") or inner.get("aggregate"):
            return None
        return {**inner, "excess": True}
    # -- counters (wave 7C) -- "Whenever a creature dealt damage by ~ this turn dies" (Sengir Vampire): it dies, and ~ dealt
    # it damage earlier this turn (the turn's log, history.note_events; 700.4, 120.3)
    m = re.fullmatch(r"(?P<s>an? .+?) dealt damage by ~ this turn dies", c)
    if m:
        inner = _parse(f"{m['s']} dies")
        if inner is None or inner.get("event") != "die" or inner.get("subject") != "sel" or inner.get("aggregate"):
            return None
        return {**inner, "damaged_by_self": True}
    # -- trigger tail (wave 16C) -- "When this creature dies during combat" (Mongrel Pack): it dies while a combat phase is going
    # on (506.1: beginning of combat through end of combat); read as the event happens (triggers._details_ok)
    # (-- spell grants (wave 30T) -- "Whenever a nontoken creature you control enters during combat" (The Blue Spirit, Noctis): the same look at the phase)
    m = re.fullmatch(r"(?P<s>.+?) (?P<v>dies|enters) during combat", c)
    if m:
        inner = _parse(f"{m['s']} {m['v']}")
        if inner is None or inner.get("event") != ("die" if m["v"] == "dies" else "enter") or inner.get("aggregate"):
            return None
        return {**inner, "in_combat": True}
    # -- triggers (wave 17D) -- "Whenever one or more other creatures you control leave the battlefield without dying" (Dour Port-Mage):
    # a leave that isn't a death (700.4: put into a graveyard from the battlefield), read as the event happens
    m = re.fullmatch(r"(?P<s>.+?) leaves? the battlefield without dying", c)
    if m:
        inner = _parse(f"{m['s']} leaves the battlefield")
        if inner is None or inner.get("event") != "leave":
            return None
        return {**inner, "nodie": True}
    # -- triggers (wave 17D) -- "Whenever a creature is exiled from the battlefield" (Soulherder): a leave whose destination is exile
    m = re.fullmatch(r"(?P<s>.+?) (?:is|are) (?:exiled|put into exile) from the battlefield", c)
    if m and " or " not in m["s"] and not m["s"].endswith(" or"):  # ("~ dies or is put into exile from the battlefield": the either-form below)
        inner = _parse(f"{m['s']} leaves the battlefield")
        if inner is None or inner.get("event") != "leave":
            return None
        return {**inner, "dest": "exile"}
    # "When ~ enters or dies", "Whenever ~ attacks or blocks": one ability, each event (603.2)
    m = re.fullmatch(rf"~ (?P<a>{_MULTI_RE}) or (?P<b>{_MULTI_RE})", c)
    if m:
        return {"event": "multi", "events": [_MULTI[m["a"]], _MULTI[m["b"]]]}
    # -- trigger tail (wave 15B) -- "~ dies or is put into exile from the battlefield" (God-Eternal Oketra), "~ or another
    # nontoken artifact you control is put into a graveyard from the battlefield or is put into exile from the battlefield":
    # either event of the same objects (603.2), each its own (a card put into exile from the battlefield: 603.6c, 700.4)
    m = re.fullmatch(r"(?P<s>.+?) (?:dies|(?:is|are) put into a graveyard from the battlefield) or (?:is|are) put into (?:exile"
                     r"(?: from the battlefield)?|(?P<cz>the command zone))", c)  # (wave 20A: "When enchanted permanent dies or is put into exile", Kaya's Ghostform)
    # (-- counters (wave 41A) -- 109.2: "a creature with a coin counter on it dies or is put into exile" (Athreos, Shroud-Veiled): a description with a card type
    # and no "card" is a permanent on the battlefield, so "is put into exile" is from the battlefield too; wave 44D: nor is "~ dies or is put into exile" (Syr Vondam), an ability
    # of a permanent, which functions on the battlefield only)
    if m and not c.endswith("battlefield") and m["s"] != "~" and not m["s"].startswith(("enchanted ", "equipped ")) \
            and not re.match(r"(?:an?|another) (?!.*\bcards?\b)(?:[a-z-]+ )*(?:creature|permanent|artifact|enchantment|land|planeswalker)\b", m["s"]):
        return None  # (a bare "put into exile" is from the battlefield only for what an Aura / Equipment is attached to: it's there)
    if m:
        died, left = _parse(f"{m['s']} dies"), _parse(f"{m['s']} leaves the battlefield")
        if died is None or left is None or died.get("event") != "die" or left.get("event") != "leave" or died.get("aggregate") \
                or left.get("aggregate") or {k: v for k, v in died.items() if k != "event"} != {k: v for k, v in left.items() if k != "event"}:
            return None
        # (-- counters (wave 41A) -- 903.9b: "dies or is put into the command zone" (Reyhan): a commander that would go to its owner's hand or library may go to the
        # command zone instead — it left the battlefield for there without dying; one that died is put there from the graveyard (903.9a), after it died)
        return {"event": "either", "subject": died["subject"], "conds": [died, {**left, "dest": "command" if m["cz"] else "exile"}]}
    # -- attached events (wave 4L) -- "Whenever enchanted creature attacks or blocks" (the object it's attached to)
    # (-- attached events (wave 40B) -- also "becomes tapped or is dealt damage" (Cryoshatter): events of an object that stays on the battlefield, so the creature the
    # source is attached to as it happens is the one, 303.4b — not "dies" / "leaves", which look back, 603.10a)
    m = re.fullmatch(rf"(?:enchanted|equipped) creature (?P<a>{_MULTI_RE}) or (?P<b>{_MULTI_RE})", c)
    if m and {_MULTI[m["a"]], _MULTI[m["b"]]} <= {"attack", "block", "blocked", "tapped", "untapped", "dealt_damage"}:
        return {"event": "multi", "events": [_MULTI[m["a"]], _MULTI[m["b"]]], "subject": "host"}
    # 509.3b / 509.3d: "~ blocks or becomes blocked by a creature" — once per creature on the other side
    # (wave 11E: also "enchanted / equipped creature …", the permanent the source is attached to)
    m = re.fullmatch(r"(?P<s>~|enchanted creature|equipped creature) (?P<v>blocks or becomes blocked by|blocks|becomes blocked by)"
                     r" (?P<o>an? .+|another .+|one or more .+)", c)  # (-- trigger other (wave 36A) -- "one or more black creatures", below)
    if m:
        other = _object_sel(m["o"])
        events = {"blocks or becomes blocked by": ["block", "blocked"], "blocks": ["block"],
                  "becomes blocked by": ["blocked"]}[m["v"]]
        subject = "self" if m["s"] == "~" else "host"
        # -- trigger other (wave 36A) -- 509.3a, 603.2c: "Whenever ~ blocks one or more black creatures" (Rashka the Slayer), "~ blocks or becomes blocked by
        # one or more Orcs" (Dwarven Soldier): once however many of them it blocks / is blocked by (not once for each, as "a creature" is, 509.3b, 509.3d)
        many: Condition = {"aggregate": True} if m["o"].startswith("one or more ") else {}
        if len(events) == 1:
            return {"event": events[0], "subject": subject, "other": other, **many}
        return {"event": "multi", "events": events, "other": other, **many, **({"subject": "host"} if subject == "host" else {})}
    # -- entry forms (wave 5F) -- "When this land enters untapped", "Whenever a permanent you control enters tapped":
    # how it entered is part of the trigger event (603.2; triggers._details_ok reads the turn log's Entry)
    m = re.fullmatch(r"(?P<s>.+?) enters (?P<t>tapped|untapped)", c)
    if m:
        inner = _parse(f"{m['s']} enters")
        if inner is None or inner.get("event") != "enter" or inner.get("aggregate"):
            return None
        return {**inner, "entered_tapped": m["t"] == "tapped"}
    found = _combat(c)
    if found is not None:
        return found
    # -- keywords (wave 15E) -- training (702.149a): "~ and at least one other creature with power greater than ~'s power attack"
    if c == "~ and at least one other creature with power greater than ~'s power attack":
        sel = selectors.parse("creature with power greater than ~'s power")
        return None if sel is None else {"event": "attack", "subject": "self", "min_attackers": 1, "sel": sel.key(),
                                         "others_only": True}
    # battalion: "~ and at least two other creatures attack" (the creatures declared as attackers)
    m = re.fullmatch(r"~ and at least (?P<n>\w+) other creatures? attack", c)
    if m:
        return {"event": "attack", "subject": "self", "min_attackers": _count(m["n"]) + 1}
    # -- trigger qualifiers (wave 11C) -- "~ and at least one other Warrior attack" (attackers other than ~ that are Warriors),
    # "~ and at least two Zombies attack" (Zombies among all the attackers, ~ counting if it is one)
    m = re.fullmatch(r"~ and at least (?P<n>\w+) (?P<o>other )?(?P<w>[A-Z][\w-]*?)s? attack", c)
    if m:
        sel = _token_or_sel(m["w"])
        if sel is None or sel.player is not None or sel.card or sel.types not in ((), ("Creature",)) and not sel.subtypes:
            return None
        return {"event": "attack", "subject": "self", "min_attackers": _count(m["n"]), "sel": sel.key(),
                **({"others_only": True} if m["o"] else {})}
    # "you draw your second card each turn"
    m = re.fullmatch(rf"{_P} draws? (?:their|your) (?P<nth>first|second|third) card each turn", c)
    if m:
        return {"event": "draw", "subject": "player", "player": _PLAYERS[m["p"]], "nth": _NTH[m["nth"]]}
    m = re.fullmatch(rf"{_P} draws? (?:their|your) first or second card each turn", c)  # -- counters (wave 33C) -- Lady Octopus: the first two of the turn
    if m:
        return {"event": "draw", "subject": "player", "player": _PLAYERS[m["p"]], "nth_max": 2}
    # -- triggers (wave 5D) -- "an opponent draws a card except the first one they draw in each of their draw steps"
    # (Orcish Bowmasters): not the first card that player draws during their own draw step (504.1's draw, usually)
    m = re.fullmatch(rf"{_P} draws a card except the first one they draw in each of their draw steps", c)
    if m:
        return {"event": "draw", "subject": "player", "player": _PLAYERS[m["p"]], "not_first_in_draw_step": True}
    # -- hideaway (wave 29D) -- "you draw your first card during each of your draw steps" (Wiretapping): the draw step's own first draw (504.1)
    m = re.fullmatch(rf"{_P} draws? (?:their|your) first card during each of (?:their|your) draw steps", c)
    if m:
        return {"event": "draw", "subject": "player", "player": _PLAYERS[m["p"]], "only_first_in_draw_step": True}
    found = _cast(c)
    if found is not None:
        return found
    found = _player_action(c)
    if found is not None:
        return found
    found = _activate(c)  # -- activation (wave 11F) --
    if found is not None:
        return found
    # -- mana riders (wave 5A) -- "you tap ~ for mana", "a player taps a land for mana"
    from app.rules import tap_mana

    found = tap_mana.condition(c)
    if found is not None:
        return found
    # -- triggers (wave 5D) -- "Whenever another creature you control enters or dies" (Daxos): either event of the
    # same objects (603.2), each read on its own ("~ enters or dies" is the "multi" form above)
    m = re.fullmatch(r"(?P<s>(?!~ (?:enters|dies|attacks|blocks|leaves))(?!one or more ).+?) (?P<a>enters|dies|attacks|blocks|leaves the battlefield) or "
                     r"(?P<b>enters|dies|attacks|blocks|leaves the battlefield|deals combat damage to a player)", c)
    if m:
        a, b = _parse(f"{m['s']} {m['a']}"), _parse(f"{m['s']} {m['b']}")
        if a is None or b is None or a.get("aggregate") or b.get("aggregate") or a.get("subject") != b.get("subject") \
                or a.get("subject") not in ("sel", "self_or"):
            return None
        return {"event": "either", "subject": a["subject"], "conds": [a, b]}
    # -- trigger tail (wave 16C) -- "Whenever a creature dies or a creature card is put into a graveyard from a library" (Dreadhound):
    # two whole conditions, each its own event (603.2c); both halves must read on their own
    m = re.fullmatch(r"(?P<a>(?:an?|another) [^,]+? (?:dies|attacks|enters)|(?:an?|another) [^,]+? (?:is|are) put into [^,]+?) or "
                     r"(?P<b>(?:an?|another) [^,]+? (?:is|are) put into [^,]+?)", c)
    if m:
        a, b = _parse(m["a"]), _parse(m["b"])
        if a is None or b is None or a.get("aggregate") or b.get("aggregate") or a["event"] in ("either", "multi") \
                or b["event"] in ("either", "multi") or a["event"] == b["event"]:
            return None
        return {"event": "either", "subject": a["subject"] if a["subject"] == b["subject"] else "mixed", "conds": [a, b]}
    # -- triggers (wave 5D) -- "Whenever you create or sacrifice a token" (Mirkwood Bats): either action, each one its
    # own event (603.2c) — both halves must read on their own
    m = re.fullmatch(r"(?P<p>you|an opponent|a player) (?P<a>[a-z]+) or (?P<b>[a-z]+) (?P<o>(?:an?) .+)", c)
    if m:
        a, b = _player_action(f"{m['p']} {m['a']} {m['o']}"), _player_action(f"{m['p']} {m['b']} {m['o']}")
        if a is None or b is None or a.get("aggregate") or b.get("aggregate") or a["event"] == b["event"]:
            return None
        return {"event": "either", "subject": "player", "player": a["player"], "conds": [a, b]}
    # -- history (wave 22E) -- "Whenever this creature attacks, blocks, or becomes the target of a spell": a list of verbs for one
    # subject, each its own event (603.2c); every part must read on its own with that subject
    m = re.fullmatch(r"(?P<s>~|this creature|this permanent) (?P<rest>[^,]+(?:, [^,]+)+), or (?P<last>.+)", c)
    if m:
        parts = [_parse(f"{m['s']} {p}") for p in (*m["rest"].split(", "), m["last"])]
        if any(p is None or p.get("aggregate") or p["event"] in ("either", "multi") for p in parts) \
                or len({p["event"] for p in parts if p}) != len(parts):
            return None
        return {"event": "either", "subject": "self", "conds": parts}
    # -- counters (wave 41A) -- "Whenever another creature you control or a land you control is put into a graveyard from the battlefield" (Long Feng, Grand
    # Secretariat): two descriptions of the object the one event (603.2) is about, one trigger however many it matches (a land creature); each reads on its own
    # with the shared predicate and says who controls it ("a creature or a land you control" is a different reading: not taken)
    m = re.fullmatch(r"(?P<a>(?:an?|another) .+? (?:you control|an opponent controls)) or (?P<b>(?:an?|another) .+? (?:you control|an opponent controls)) (?P<p>dies|(?:is|are) put into a graveyard from the battlefield|leaves the battlefield|enters)", c)
    if m:
        a, b = _parse(f"{m['a']} {m['p']}"), _parse(f"{m['b']} {m['p']}")
        if a is None or b is None or a.get("aggregate") or b.get("aggregate") or a["event"] != b["event"] or a["subject"] != "sel" or b["subject"] != "sel":
            return None
        return {"event": "either", "subject": "sel", "conds": [a, b]}
    # -- most-played cards (wave 43B) -- "Whenever another creature dies, or a creature card is put into a graveyard from anywhere other than the battlefield, or a
    # creature card leaves your graveyard" (Syr Konrad, the Grim): a list of whole conditions, each its own event (603.2c); every piece must read on its own
    if c.count(", or ") >= 1:
        pieces = [_parse(piece) for piece in c.split(", or ")]
        if all(p is not None and not p.get("aggregate") and p["event"] not in ("either", "multi") for p in pieces) and len(pieces) >= 2:
            subjects = {p["subject"] for p in pieces if p}
            return {"event": "either", "subject": subjects.pop() if len(subjects) == 1 else "mixed", "conds": [p for p in pieces if p]}
    # -- triggers (wave 17D) -- "Whenever you cast a black spell or a Swamp you control enters" (Staff of the Death Magus): two whole
    # conditions, each its own event (603.2c); split where both halves read on their own
    for part in re.finditer(r" or ", c):
        try:
            a, b = _parse(c[:part.start()]), _parse(c[part.end():])
        except _Refuse:
            continue
        if a is None or b is None or a["event"] in ("either", "multi") or b["event"] in ("either", "multi") \
                or a.get("aggregate") or b.get("aggregate") or (a["event"] == b["event"] and a["subject"] == b["subject"]):
            continue
        return {"event": "either", "subject": a["subject"] if a["subject"] == b["subject"] else "mixed", "conds": [a, b]}
    m = _GETS_COUNTERS.fullmatch(c)  # -- counters & designations (wave 3E): "whenever you get one or more {E}" (122.6) --
    if m:
        return {"event": "player_counters", "subject": "player", "player": _PLAYERS[m["p"]],
                "counter": "energy" if m["e"] else m["k"]}
    # -- looks (wave 8B) -- "Whenever you scry or surveil" (701.22b, 701.25c: a scry / surveil of N > 0), "Whenever you
    # surveil for the first time each turn" (the Nth of that kind this turn, as for "your second card")
    m = re.fullmatch(r"you (?P<k>scry|surveil|scry or surveil)(?P<first> for the first time each turn)?", c)
    if m:
        kinds = ["scry", "surveil"] if m["k"] == "scry or surveil" else [m["k"]]
        if m["first"] and len(kinds) > 1:
            return None  # (the first scry or surveil, or the first of each? the wording doesn't say: manual)
        conds = [{"event": k, "subject": "player", "player": "you", **({"nth": 1} if m["first"] else {})} for k in kinds]
        return conds[0] if len(conds) == 1 else {"event": "either", "subject": "player", "player": "you", "conds": conds}
    if c == "you roll one or more dice":  # -- rolling dice (wave 13E) -- 706: once per roll, however many dice (rules/dice.py)
        return {"event": "roll", "subject": "player", "player": "you"}
    from app.rules import (
        dice,  # -- dice (wave 24B) -- "you roll a 6", "a 4 or higher", "your third die each turn" (one event per die)
    )

    if (rolled := dice.event_condition(c)) is not None:
        return rolled
    for rx, event in _DESIGNATION_EVENTS:  # -- counters & designations (wave 3E) --
        m = rx.fullmatch(c)
        if m:
            return {"event": event, "subject": "player", "player": _PLAYERS[m["p"]] if m.groupdict().get("p") else "any"}
    found = _object_event(c)
    if found is not None:
        return found
    # -- becomes monstrous (wave 6D) -- "When ~ becomes monstrous" (701.37b), "Whenever a creature you control becomes
    # renowned" (702.112b): the permanent got the designation
    m = re.fullmatch(r"(?P<s>.+?) (?P<v>explores|connives)(?P<k> a land card| a nonland card)?", c)  # -- trigger tail (wave 15B) --
    if m and (m["k"] is None or m["v"] == "explores"):  # 701.44a explore (the revealed card), 701.50a connive
        base = _subject(m["s"])
        if base is None or base.get("aggregate"):
            return None
        return {**base, "event": m["v"][:-1] if m["v"] == "explores" else "connive",
                **({"kind": "land" if "nonland" not in m["k"] else "nonland"} if m["k"] else {})}
    # -- transform (wave 16F) -- "When this creature transforms into Avacyn, the Purifier" (701.28, 712.18): this very object turned over
    # and is now the face named (the ability is printed on that face; "~": whichever it is)
    m = re.fullmatch(r"(?P<s>~|this creature|this permanent) enters or transforms into (?P<n>.+)", c)  # -- transform (wave 26D) -- Huntmaster of the Fells: each is its own event (603.2c)
    if m:
        return {"event": "either", "subject": "self", "conds": [{"subject": "self", "event": "enter"}, {"subject": "self", "event": "transform", **({"into": m["n"]} if m["n"] != "~" else {})}]}
    m = re.fullmatch(r"(?P<s>~|this creature|this permanent) transforms into (?P<n>.+)", c)
    if m:
        return {"subject": "self", "event": "transform", **({"into": m["n"]} if m["n"] != "~" else {})}
    m = re.fullmatch(r"(?P<s>~|this creature|this permanent) transforms", c)  # -- transform (wave 26D) -- any face
    if m:
        return {"subject": "self", "event": "transform"}
    m = re.fullmatch(r"(?P<s>(?:a|another) [^,]+? you control) transforms(?: into (?P<d>an? [^,]+))?", c)  # (701.28: the permanent that turned over; its new face is read)
    if m:
        base = _subject(m["s"])
        sel = selectors.parse(re.sub(r"^an? ", "", m["d"])) if m["d"] else None
        if base is None or base.get("aggregate") or (m["d"] and (sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card
                                                              or sel.controller or sel.other)):
            return None
        return {**base, "event": "transform", **({"into_sel": sel.key()} if sel is not None else {})}
    # -- merged permanents (wave 18D) -- 702.140d: "Whenever this creature mutates" (it merged with a mutating creature spell)
    if c in ("~ mutates", "this creature mutates", "this permanent mutates"):
        return {"subject": "self", "event": "mutate"}
    m = re.fullmatch(r"(?P<s>.+?) becomes (?P<d>monstrous|renowned)", c)
    if m:
        base = _subject(m["s"])
        if base is None or base.get("aggregate"):
            return None
        return {**base, "event": f"become_{m['d']}"}
    if c == "you unlock this door":  # -- Rooms (wave 18G) -- 709.5h: when its own door gets the unlocked designation (any way)
        return {"subject": "self", "event": "unlock_door"}
    # -- Class (wave 16A) -- "When this Class becomes level 2" (716.2a): the class level it became (designations.facts)
    m = re.fullmatch(r"(?P<s>.+?) becomes level (?P<n>\d+)", c)
    if m:
        base = _subject(m["s"])
        if base is None or base.get("aggregate"):
            return None
        return {**base, "event": "become_level", "level": int(m["n"])}
    # -- into a graveyard (wave 6D) -- "one or more land cards are put into your graveyard from anywhere" (The Gitrog
    # Monster), "… from your library" (Hedge Shredder): a card put there, as it is there (603.6c: "from anywhere" is never
    # a leaves-the-battlefield ability, so it doesn't look back), whatever zone it came from (or only the library)
    if c == "~ is put into a graveyard from anywhere":  # -- trigger tail (wave 15B) -- 603.6c: not a leaves-the-battlefield ability
        return {"event": "to_graveyard", "subject": "self"}  # (it triggers from the graveyard, on the card's new object)
    if c in ("~ is put into your graveyard from your library", "this card is put into your graveyard from your library"):
        return {"event": "to_graveyard", "subject": "self", "from": "library"}  # -- triggers (wave 19B) -- (Narcomoeba)
    m = re.fullmatch(r"(?P<o>one or more (?:.+? )?cards|an? .+? card|a card) (?:is|are) put into (?P<g>your|an opponent's|a) "
                     r"graveyard from (?P<f>anywhere other than the battlefield|anywhere|your library|a library)", c)  # (wave 43B: Syr Konrad)
    if m:
        gsel = selectors.from_key(_object_sel(m["o"], card=True))
        owner = {"your": "you", "an opponent's": "opponent"}.get(m["g"])
        if gsel.zones or gsel.zone_owner:
            return None
        out: Condition = {"event": "to_graveyard", "subject": "sel", "aggregate": m["o"].startswith("one or more "),
                          "sel": selectors.replace(gsel, zone_owner=owner).key()}
        if m["f"] == "anywhere other than the battlefield":  # -- most-played cards (wave 43B) -- a card put there from any other zone (its dying is the "dies" event)
            out["not_from"] = "battlefield"
        if m["f"] == "your library":
            if owner != "you":
                return None
            out["from"] = "library"
        elif m["f"] == "a library":  # (wave 16C: Dreadhound — any player's library)
            out["from"] = "library"
        return out
    # -- counters (wave 21D) -- "one or more cards are put into exile [from your graveyard / your hand / your library and/or your
    # graveyard]" (Rakshasa Vizier, Laelia), "… into a library from anywhere" (Dutiful Knowledge Seeker): a card (never a token,
    # 111.7) put there, as it is there (603.6c); "during your turn" is the generic qualifier
    m = re.fullmatch(r"(?P<o>one or more (?:.+? )?cards|an? .+? card|a card) (?:is|are) put into (?P<z>exile|a library)"
                     r"(?: from (?P<f>your graveyard|your hand|your library and/or your graveyard|anywhere))?", c)
    if m and (m["z"] == "exile" or m["f"] == "anywhere"):
        gsel = selectors.from_key(_object_sel(m["o"], card=True))
        if gsel.zones or gsel.zone_owner:
            return None
        out = {"event": "to_exile" if m["z"] == "exile" else "to_library", "subject": "sel",
               "aggregate": m["o"].startswith("one or more "), "sel": gsel.key()}
        if m["f"] and m["f"] != "anywhere":
            out["froms"] = ["library", "graveyard"] if "library" in m["f"] else [m["f"].split()[1]]
            out["from_owner"] = "you"
        return out
    # -- graveyard owner (wave 6D) -- "a creature is put into an opponent's graveyard from the battlefield", "a nontoken
    # creature is put into your graveyard from the battlefield", "~ is put into your graveyard from the battlefield": it
    # died (700.4), and a card goes to its OWNER's graveyard (400.3; a token too, 111.7) — whose graveyard is the owner's
    # -- triggers (wave 17D) -- "a permanent you control is put into a graveyard" (Aetherworks Marvel): a permanent is on the battlefield,
    # so it is the same event ("a player's" / "a" graveyard: whoever owns it); a subject that isn't a card only
    m = re.fullmatch(r"(?P<s>.+?) (?P<v>is|are) put into (?P<g>your|an opponent's|a player's|a) graveyard(?P<fb> from the battlefield)?", c)
    if m and (m["fb"] or (m["g"] == "a" and "card" not in m["s"])):
        inner = _parse(f"{m['s']} {'dies' if m['v'] == 'is' else 'die'}")
        if inner is None or inner.get("event") != "die" or inner.get("subject") not in ("self", "sel", "self_or"):  # (wave 25B: "~ or another …")
            return None
        if m["g"] in ("a", "a player's"):
            return inner
        return {**inner, "gy_owner": "you" if m["g"] == "your" else "opponent"}
    # -- counters (wave 41A) -- 109.2, 603.6c: "Whenever another nonland permanent you control is returned to its owner's hand" (Justice, Vance Astrovik): a permanent
    # is on the battlefield, so it left the battlefield for a hand (400.3: its owner's, "its owner's hand" asks nothing of whose)
    # (-- trigger other (wave 44B) -- "Whenever one or more noncreature permanents are returned to hand" (Tameshi): once for the batch that left for a hand, 603.2c)
    m = re.fullmatch(r"(?P<s>(?:an?|another|one or more) [^,]+?) (?:is|are) (?:returned to (?:its owner's )?hand|put into its owner's hand from the battlefield)", c)
    if m:
        inner = _parse(f"{m['s']} {'leave' if m['s'].startswith('one or more') else 'leaves'} the battlefield")
        if inner is None or inner.get("event") != "leave" or inner.get("subject") != "sel" or bool(inner.get("aggregate")) != m["s"].startswith("one or more"):
            return None
        return {**inner, "dest": "hand"}
    m = re.fullmatch(r"(?P<p>you|an opponent|a player|each opponent) gains? or loses? life", c)  # (wave 11C) each event: 603.2
    if m:
        return {"event": "either", "subject": "player", "player": _PLAYERS[m["p"]],
                "conds": [{"event": e, "subject": "player", "player": _PLAYERS[m["p"]]} for e in ("gain_life", "lose_life")]}
    if (m := re.fullmatch(r"one or more (?P<p>opponents|players) lose life", c)) is not None:
        # -- life floor (wave 35C) -- 603.2c "one or more … lose life" (Emet-Selch of the Third Seat): once for everything that happened at the same time
        return {"event": "lose_life", "subject": "player", "player": "opponent" if m["p"] == "opponents" else "any", "aggregate": True}
    for pattern, event in _PLAYER_VERBS:
        m = re.fullmatch(rf"(?P<p>you|an opponent|a player|each opponent|enchanted player) (?:{pattern})", c)
        if m:
            return {"event": event, "subject": "player", "player": _PLAYERS[m["p"]]}
    for pattern, event in _EVENT_VERBS:
        m = re.fullmatch(rf"(?P<s>.+?) (?:{pattern})", c)
        if not m:
            continue
        subject = m["s"]
        if subject in _HOSTS:
            # -- sagas & attached-object triggers (wave 3S) -- after "dies" / "leaves", what was
            # attached to it is read looking back in time (603.10a: ObjectSnapshot.attached)
            return {"event": event, "subject": "host"}
        if subject == "~":
            return {"event": event, "subject": "self"}
        if subject in _SELF_OR_HOST:  # "~ or equipped creature deals combat damage to a player"
            return {"event": event, "subject": "self_or_host"} if event not in ("die", "leave") else None
        m2 = re.fullmatch(r"~ or another (?P<rest>.+)", subject)
        if m2:
            sel = selectors.parse("another " + m2["rest"])
            if sel is None or sel.player is not None:
                return None
            return {"event": event, "subject": "self_or", "sel": sel.key()}
        aggregate = False
        m3 = re.fullmatch(r"one or more (?P<rest>.+)", subject)
        if m3:  # -- triggers (wave 30J) -- "one or more creatures you control each with power greater than its base power" (Kutzil): the filter
            aggregate, subject = True, m3["rest"].replace(" each with ", " with ")  # is every member's own, as "with …" says (603.2c)
        else:
            m4 = re.fullmatch(r"(?:a|an|another) (?P<rest>.+)", subject)
            if not m4:
                return None
            subject = ("another " if subject.startswith("another ") else "") + m4["rest"]
        sel = _token_or_sel(subject)
        if sel is None or sel.player is not None or sel.card:
            return None
        return {"event": event, "subject": "sel", "sel": sel.key(), "aggregate": aggregate}
    return None


def _token_or_sel(phrase: str) -> selectors.Selector | None:
    """A subject phrase; "tokens you control" / "a creature token" name tokens (111.1)."""
    m = re.fullmatch(r"(?P<a>(?:another|other) )?(?P<rest>.*?)(?P<t>\btokens?)(?P<tail> .+)?", phrase)
    if m is None:
        return selectors.parse(phrase) or _kinds_you_control(phrase)
    base = selectors.parse(((m["a"] or "") + ((m["rest"] or "").strip() or ("permanents" if m["t"] == "tokens" else "permanent"))
                            + (m["tail"] or "")).strip())
    return selectors.replace(base, token=True) if base is not None else None


def _kinds_you_control(phrase: str) -> selectors.Selector | None:
    """-- attached events (wave 40B) -- 700.9, 303.4: "enchanted creature or enchantment creature you control" (Kestia, the Cultivator): two kinds of the permanents you
    control, either one — each read on its own with "you control", nothing else shared (a trigger's subject: the selector's ``either``)."""
    both = re.fullmatch(r"(?P<a>[a-z]+(?: [a-z]+)?) or (?P<b>[a-z]+(?: [a-z]+)?) you control", phrase)
    halves = [selectors.parse(f"{both[k]} you control") for k in ("a", "b")] if both else []
    if halves and all(h is not None and h.player is None and not h.card and not h.either and not h.union and h.zones == ("battlefield",)
                      and h.controller == "you" for h in halves):
        return selectors.Selector(either=tuple(h.key() for h in halves if h is not None))
    return None


def _subject(s: str, *, host: bool = False, many: bool = False) -> Condition | None:
    """The subject of an object event: this object, or any object matching a selector; with
    ``host`` also the permanent this one is attached to ("equipped creature", "~ or equipped
    creature"), with ``many`` also "one or more …" (603.2c: one trigger per event batch)."""
    if s == "~":
        return {"subject": "self"}
    # -- trigger damage (wave 39B) -- "Whenever ~ or an instant or sorcery spell you control deals damage to a player" (Syr Carah): this object or a spell
    # of that kind (120.1: a spell is a source of damage while it's on the stack, where its selector looks)
    m = re.fullmatch(r"~ or an? (?P<rest>[^,]+? spells? you control)", s)
    if m:
        spell = selectors.parse(m["rest"])
        return {"subject": "self_or", "sel": spell.key()} if spell is not None and spell.zones == ("stack",) and spell.player is None else None
    if host and s in _HOSTS:
        return {"subject": "host"}
    if host and s in _SELF_OR_HOST:
        return {"subject": "self_or_host"}
    m = re.fullmatch(r"(?P<q>a|an|another|one or more) (?P<rest>.+)", s)
    if not m or (m["q"] == "one or more" and not many):
        return None
    if (m["q"] == "one or more") != selectors.is_plural(m["rest"]) and not re.search(r"\b(?:Merfolk|Moonfolk)\b", m["rest"]):  # (wave 21B: invariant plurals)
        return None
    phrase = ("another " if m["q"] == "another" else "") + m["rest"]
    sel = selectors.parse(phrase) if not many else _token_or_sel(phrase)
    if sel is None or sel.player is not None or sel.card:
        return None
    return {"subject": "sel", "sel": sel.key(), "aggregate": m["q"] == "one or more"}


def _defender(d: str | None, player_attack: bool = False) -> Condition:
    if d and _DEFENDERS[d] in ("opponent_any", "other_opponent") and not player_attack:
        raise _Refuse  # (review 27B) only "<a player> attacks …" reads these (a creature's attack, a count of attackers: not read)
    if d and _DEFENDERS[d] == "opponent_or_pw" and player_attack:
        raise _Refuse  # (wave 36A) a creature's attack only
    return {"defender": _DEFENDERS[d]} if d else {}


def _combat(c: str) -> Condition | None:
    """Attack conditions with more to them than "~ attacks" (508.3, 509.3g, 506.5)."""
    # -- trigger other (wave 44B) -- 508.1: "you attack with ~ and another legendary creature" (Merry): ~ is declared as an attacker together with another creature
    # of that kind (not necessarily attacking the same player, ruling 2023-06-16); it triggers once, as ~ attacks
    m = re.fullmatch(r"you attack with ~ and another (?P<o>[a-z ]+)", c)
    if m:
        sel = selectors.parse(m["o"])
        if sel is None or sel.player is not None or sel.card:
            return None
        return {"event": "attack", "subject": "self", "min_attackers": 1, "sel": sel.key(), "others_only": True}
    # 508.3d / 508.3e: "a player attacks you", "an opponent attacks you with two or more creatures",
    # "you attack a player", "a player attacks one of your opponents" — once per player attacked
    m = re.fullmatch(rf"(?P<p>you|an opponent|a player) attacks? (?P<d>{_DEFENDER_RE})"
                     r"(?: with (?:(?P<n>\w+) or more )?(?P<o>creatures|creatures with .+))?", c)  # (wave 21B: "creatures with power 4 or greater")
    if m and not (m["p"] == "you" and m["d"] in ("you", "you or a planeswalker you control")):
        kind = _DEFENDERS[m["d"]]  # (review 27B) "one or more of your opponents": the declaration, not a count per player;
        if kind in ("opponent_any", "other_opponent") and (m["n"] or m["o"]) or (kind == "other_opponent" and m["p"] != "an opponent"):
            raise _Refuse  # "another one of your opponents": other than you and the attacking opponent (Karazikar)
        out: Condition = {"event": "you_attack", "subject": "player", "player": _PLAYERS[m["p"]], **_defender(m["d"], True)}
        if m["n"]:
            out["min_attackers"] = _count(m["n"])
        if m["o"] and m["o"] != "creatures":  # -- triggers (wave 21B) -- 508.3c: the creatures declared as attackers, those matching
            sel = selectors.parse(m["o"])
            if sel is None or sel.player is not None or sel.card or m["n"] not in (None, "one"):
                raise _Refuse
            out.update(min_attackers=1, sel=sel.key())
        return out
    # 508.3b: "enchanted player is attacked", "you're attacked"
    m = re.fullmatch(r"(?P<p>enchanted player is|you're|you are) attacked", c)
    if m:
        return {"event": "you_attack", "subject": "player", "player": "any",
                "defender": "enchanted_player" if m["p"].startswith("enchanted") else "you"}
    # 508.3c / 508.3d: "you attack with one or more creatures", "you attack with three or more
    # creatures", "an opponent attacks with creatures" (the creatures declared as attackers)
    m = re.fullmatch(rf"{_P} attacks? with (?:(?P<n>\w+) or more )?(?P<o>.+)", c)
    if m:
        sel = selectors.parse(m["o"])
        if sel is None or sel.player is not None or sel.card or not selectors.is_plural(m["o"]):
            raise _Refuse
        return {"event": "you_attack", "subject": "player", "player": _PLAYERS[m["p"]],
                "min_attackers": _count(m["n"]) if m["n"] else 1, "sel": sel.key()}
    # "three or more creatures attack you", "two or more creatures you control attack a player"
    # (one trigger per player attacked, counting the creatures attacking that player: 508.3e)
    m = re.fullmatch(rf"(?P<n>\w+) or more (?P<o>.+?) attack(?: (?P<d>{_DEFENDER_RE}))?", c)
    if m and m["n"] != "one":
        sel = _token_or_sel(m["o"])
        if sel is None or sel.player is not None or sel.card or not selectors.is_plural(m["o"]):
            raise _Refuse
        return {"event": "you_attack", "subject": "player", "player": "any", "min_attackers": _count(m["n"]),
                "sel": sel.key(), **_defender(m["d"])}
    # 509.3g: "~ attacks and isn't blocked", "a creature you control attacks a player and isn't blocked"
    m = re.fullmatch(rf"(?P<s>.+?) attacks?(?: (?P<d>{_DEFENDER_RE}))? and (?:isn't|aren't) blocked", c)
    if m:
        base = _subject(m["s"], host=True)
        if base is None:
            raise _Refuse
        return {**base, "event": "unblocked", **_defender(m["d"])}
    # 506.5: "~ attacks alone", "a creature you control attacks alone", "… attacks a player alone"
    m = re.fullmatch(rf"(?P<s>.+?) attacks(?: (?P<d>{_DEFENDER_RE}))? alone", c)
    if m:
        base = _subject(m["s"], host=True)
        if base is None:
            raise _Refuse
        return {**base, "event": "attack", "alone": True, **_defender(m["d"])}
    # "~ attacks while you control a creature with power 4 or greater" (read as it triggers)
    # (-- trigger other (wave 25B) -- also "while there are four or more card types among cards in your graveyard" (delirium),
    # "while you have no cards in hand"; and "Whenever you attack while you control …": the player's attack, 508.3c)
    m = re.fullmatch(r"you attack while (?P<w>you control .+|there (?:is|are) .+|you have .+)", c)
    if m:
        from app.rules import conditions

        holds, base = conditions.parse(m["w"]), _parse("you attack")
        if holds is None or base is None:
            raise _Refuse
        return {**base, "while": holds}
    m = re.fullmatch(r"(?P<s>.+?) attacks while (?P<w>you control .+|there (?:is|are) .+|you have .+|saddled)", c)  # (wave 23D: 702.171b "while saddled", ~ itself)
    if m:
        from app.rules import conditions  # (selectors and values only)

        base = _subject(m["s"], host=True)
        holds = {"object": "self", "designation": "saddled"} if m["w"] == "saddled" and m["s"] == "~" else \
            None if m["w"] == "saddled" else conditions.parse(m["w"])
        if base is None or holds is None:
            raise _Refuse
        return {**base, "event": "attack", "while": holds}
    # "~ attacks for the first time each turn"
    m = re.fullmatch(r"(?P<s>.+?) attacks for the first time each turn", c)
    if m:
        base = _subject(m["s"], host=True)
        if base is None:
            raise _Refuse
        return {**base, "event": "attack", "first_each_turn": True}
    # 508.3a: "a creature attacks you or a planeswalker you control", "~ attacks a player", "one or
    # more creatures attack you", "equipped creature attacks", "~ or equipped creature attacks"
    m = re.fullmatch(rf"(?P<s>.+?) attacks?(?: (?P<d>{_DEFENDER_RE}))?", c)
    if m and (m["d"] or m["s"] in _HOSTS or m["s"] in _SELF_OR_HOST):
        base = _subject(m["s"], host=True, many=True)
        if base is None:
            return None
        return {**base, "event": "attack", **_defender(m["d"])}
    return None


_FROM = {"from exile": "exile", "from your graveyard": "graveyard", "from a graveyard": "graveyard", "from your library": "library",  # (-- trigger other (wave 25B) -- Melek)
         "from anywhere other than your hand": "not_hand", "from your hand": "hand",
         "from anywhere other than their hand": "not_hand"}  # (wave 17D: Ghostly Pilferer)


def _cast(c: str) -> Condition | None:
    """601.2i: "you cast a creature spell", "an opponent casts a spell", "you cast your second spell
    each turn", "you cast a spell that targets ~" (heroic), "you cast a spell from exile", "you
    cast a kicked spell", "you cast a spell during an opponent's turn"."""
    # -- trigger from (wave 30F) -- 102.2: with no teams (Commander is free-for-all) every other player is an opponent
    c = re.sub(r"^another player casts\b", "an opponent casts", c)
    # -- refused copy/mana (wave 3R3) -- magecraft: "Whenever you cast or copy an instant or sorcery
    # spell" / "Whenever you copy a spell". 707.10: copying a spell puts a copy onto the stack under the
    # control of the player who copies it; it isn't cast. "copy": "or" also triggers on a copy, "only"
    # only on one (app/rules/triggers.py, the "spell_copied" event). Only the plain spell kinds: an
    # ordinal, a zone or a target condition is about casting (refused with a copy).
    cm = re.fullmatch(rf"{_P} (?:(?P<both>casts? or cop(?:y|ies))|cop(?:y|ies)) (?P<spell>.+)", c)
    if cm is not None:
        verb = "casts" if cm["p"] in ("an opponent", "a player") else "cast"
        base = _cast(f"{cm['p']} {verb} {cm['spell']}")
        if base is None or set(base) != {"event", "subject", "player", "spell"}:
            return None
        return {**base, "copy": "or" if cm["both"] else "only"}
    # -- end refused copy/mana (wave 3R3) --
    # -- trigger other (wave 44B) -- 603.2c: "you cast an Equipment spell or a spell that targets a creature you control" (Danitha), "a Doctor spell or creature spell
    # with doctor's companion" (Rose Noble): two whole conditions, each its own event (one trigger for a spell that is both); each half reads on its own
    ec = re.fullmatch(rf"{_P} casts? (?P<a>an? [^,]+? spell) or (?P<b>(?:an? )?[^,]+? spell(?: that targets [^,]+| with [^,]+))", c)
    if ec is not None:
        verb = "casts" if ec["p"] in ("an opponent", "a player") else "cast"
        a, b = (_cast(f"{ec['p']} {verb} {x}") for x in (ec["a"], ec["b"] if ec["b"].startswith(("a ", "an ")) else "a " + ec["b"]))
        if a is None or b is None or "targets" not in str(a) + str(b) and "keywords" not in str(a) + str(b):
            return None
        return {"event": "either", "subject": "player", "player": a["player"], "conds": [a, b]}
    m = re.fullmatch(rf"{_P} casts? (?P<spell>.+)", c)
    if not m:
        return None
    out: Condition = {"event": "cast", "subject": "player", "player": _PLAYERS[m["p"]]}
    spell = m["spell"]
    t = re.fullmatch(r"(?P<rest>.+?) during (?P<w>an opponent's turn|each opponent's turn|your turn|each of your turns)(?P<tail> other than your first spell that turn)?", spell)
    if t:  # (-- triggers (wave 30J) -- Geralf, Rashmi and Ragavan: "during your turn" is the generic qualifier ``_qualified`` reads, the turn of the one the
        # ability is about; here it comes with the Nth-spell wording the qualifier alone can't read)
        out["during" if "your" in t["w"] else "turn"] = "you" if "your" in t["w"] else "opponent"
        spell = t["rest"] + (t["tail"] or "")  # (Geralf: "a spell during your turn other than your first spell that turn")
    if spell in ("a spell other than your first spell each turn", "a spell other than your first spell that turn"):  # -- counters (wave 21D) -- 601.2i: the second or later (Arcbound Tracker)
        return {**out, "nth_min": 2, "spell": selectors.Selector(zones=("stack",)).key()}
    nth = re.fullmatch(r"(?:your|their) (?P<nth>first|second|third|fourth|fifth) spell(?P<each> each turn| in a turn)?", spell)
    if nth and (nth["each"] or out.get("turn") or out.get("during")):  # (the Nth spell of any kind: counted per player per turn)
        return {**out, "nth": _NTH[nth["nth"]], "spell": selectors.Selector(zones=("stack",)).key()}
    # -- triggers (wave 30J) -- "your fourth noncreature spell each turn" (The Fantasticar), "your first instant or sorcery spell from your graveyard
    # each turn" (Sevinne): the Nth of that kind (and place) among the spells the player cast this turn, as the turn's cast log recorded them
    knth = re.fullmatch(r"(?:your|their) (?P<nth>first|second|third|fourth|fifth) (?P<phrase>[A-Za-z0-9 ,/-]+? spell)"
                        r"(?: (?P<from>from your graveyard|from exile))? each turn", spell)
    if knth and not out.get("turn") and not out.get("during") and (knth["nth"] != "first" or knth["from"]):
        from app.rules import history

        ksel = selectors.parse(knth["phrase"])
        stacked = selectors.replace(ksel, zones=("stack",)) if ksel is not None and ksel.player is None else None
        if stacked is None or not history.note_selector_ok(stacked, spell=True):
            return None
        return {**out, "nth_note": _NTH[knth["nth"]], "spell": stacked.key(), **({"note_from": _FROM[knth["from"]]} if knth["from"] else {})}
    # -- unless pays (wave 4C) -- "their first noncreature spell each turn" (app/rules/unless_pays.py: the kind's marks)
    kind = re.fullmatch(r"(?:your|their) first (?P<phrase>(?:[A-Za-z0-9 ,/-]+? spell|spell with [A-Za-z0-9 {}]+?)) each turn", spell)
    if kind and not out.get("turn") and not out.get("during"):
        from app.rules import unless_pays

        ksel = selectors.parse(kind["phrase"])
        key = selectors.replace(ksel, zones=("stack",)).key() if ksel is not None and ksel.player is None else None
        if key is not None and not unless_pays.first_kind_ok(key):  # -- history (wave 22E) -- "their first multicolored spell each turn": any kind
            from app.rules import (
                history,  # the turn's cast log records (types, subtypes, supertypes, colors, mana value)
            )

            return {**out, "first_note": True, "spell": key} if history.note_selector_ok(selectors.from_key(key), spell=True) else None
        return {**out, "first_kind": True, "spell": key} if key is not None else None
    # -- end unless pays (wave 4C) --
    if spell.startswith(("your ", "their ")) or " each turn" in spell or "copy" in spell or " this turn" in spell:
        return None
    f = re.fullmatch(r"(?P<rest>.+?) (?P<from>from exile|from your graveyard|from a graveyard|"
                     r"from anywhere other than your hand|from your hand|from your library|from anywhere other than their hand)", spell)
    if f:
        out["from"] = _FROM[f["from"]]
        spell = f["rest"]
    only = re.fullmatch(r"(?P<rest>.+?) that targets only ~", spell)  # -- copied abilities (wave 18F) -- Zada, Mirrorwing Dragon
    if only:
        out["targets"] = "self_only"
        spell = only["rest"]
    # -- spell copies (wave 31D) -- 115.9c: "… that targets only a single creature you control" (Leyline of Resonance): one object chosen, however
    # many times, and it is one of those (triggers._targets_ok "only_one:")
    one = re.fullmatch(r"(?P<rest>.+?) that targets only a single (?P<t>.+)", spell)
    if one:
        sel = selectors.parse(one["t"])
        if sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",):
            return None
        out["targets"] = "only_one:" + sel.key()
        spell = one["rest"]
    tg = re.fullmatch(r"(?P<rest>.+?) that targets (?P<t>~|an? .+|one or more .+)", spell)
    if tg:
        opp = re.fullmatch(r"an opponent or (an? .+)", tg["t"])  # -- counters (wave 33C) -- Danitha: a player who is an opponent, or a permanent like that
        if tg["t"] == "~":
            out["targets"] = "self"
        elif opp:
            sel = selectors.parse(re.sub(r"^an? ", "", opp[1]))
            if sel is None or sel.player is not None or sel.card:
                return None
            out["targets"] = "opp_or:" + sel.key()
        else:
            sel = selectors.parse(re.sub(r"^(?:an?|one or more) ", "", tg["t"]))
            if sel is None or sel.player is not None or sel.card:
                return None
            out["targets"] = sel.key()
        spell = tg["rest"]
    k = re.fullmatch(r"an? kicked (?P<rest>.+)", spell)
    if k:
        out["kicked"] = True
        spell = "a " + k["rest"]
    spell = re.sub(r"^an? ", "", spell)
    spell = re.sub(r"^(\w+) spell or an? (\w+) spell$", r"\1 or \2 spell", spell)  # (wave 17D: "a noncreature spell or a Dragon spell")
    sel = selectors.parse(spell) if spell != "spell" else selectors.Selector(zones=("stack",))
    if sel is None:  # -- triggers (wave 17D) -- "a noncreature or Dragon spell": two whole kinds, either one (601.2i)
        alt = re.fullmatch(r"([a-z]+|[A-Z][a-z]+) or ([a-z]+|[A-Z][a-z]+) spell", spell)
        halves = [selectors.parse(f"{w} spell") for w in alt.groups()] if alt else []
        if len(halves) == 2 and all(h is not None and h.player is None for h in halves):
            keys = tuple(selectors.replace(h, zones=("stack",)).key() for h in halves if h is not None)
            return {**out, "spell": selectors.Selector(either=keys).key()}
    if sel is None or sel.player is not None:
        return None
    return {**out, "spell": selectors.replace(sel, zones=("stack",)).key()}


def _player_action(c: str) -> Condition | None:
    """A player sacrifices (701.21), discards (701.9), cycles (702.29) or creates a token (111.2)."""
    # -- entry forms (wave 5F) -- "When you play another land" (City of Traitors), "Whenever a player plays a land": 305.1
    # (playing a land — not putting one onto the battlefield)
    # -- trigger tail (wave 15B) -- "Whenever you expend 4" (700.14: as you spend your fourth total mana to cast spells this turn)
    m = re.fullmatch(rf"(?P<p>you|a player|an opponent) plays? (?P<a>an? [\w ]*?land)(?P<fa>{_PLAY_FROM})? or casts? (?P<b>an? [\w ]*?spell)(?P<fb>{_PLAY_FROM})?", c)
    if m:  # "Whenever you play a land or cast a spell" (305.1: playing a land is no cast): either event, each its own (603.2)
        p = m["p"]
        verb = "play" if p == "you" else "plays"
        # -- trigger from (wave 30F) -- "… a land from exile or cast a spell from exile" (Pia Nalaar); "… a land or cast a spell from anywhere other
        # than your hand" (Shadow of the Goblin): the one place goes with both halves. A land is played from the zone it's in (701.18a)
        land = _parse(f"{p} {verb} {m['a']}{m['fa'] or m['fb'] or ''}")
        spell = _parse(f"{p} {'cast' if p == 'you' else 'casts'} {m['b']}{m['fb'] or ''}")
        if land is None or spell is None or land.get("event") != "land_played" or spell.get("event") != "cast" \
                or land.get("aggregate") or spell.get("aggregate"):
            return None
        return {"event": "either", "subject": "player", "player": land["player"], "conds": [land, spell]}
    m = re.fullmatch(r"you expend (?P<n>\d+)", c)
    if m:
        return {"event": "expend", "subject": "player", "player": "you", "n": int(m["n"])}
    m = re.fullmatch(rf"{_P} plays? (?P<o>another land|an? (?:[a-z]+ )?land)(?P<f>{_PLAY_FROM})?", c)
    if m:
        return {"event": "land_played", "subject": "player", "player": _PLAYERS[m["p"]], "obj": _object_sel(m["o"]),
                "aggregate": False, **({"entered_from": _ENTERED_FROM[m["f"][len(" from "):]]} if m["f"] else {})}
    # -- discard causes (wave 23D) -- 701.9: "a spell or ability an opponent controls causes you to discard this card / a card / cards"
    m = re.fullmatch(r"a spell or ability an opponent controls causes you to discard (?P<o>this card|~|a card|one or more cards|cards)", c)
    if m:
        if m["o"] in ("this card", "~"):
            return {"event": "discard", "subject": "self", "cause": "opponent"}
        return {"event": "discard", "subject": "player", "player": "you", "obj": _object_sel("card", card=True), "cause": "opponent",
                "aggregate": m["o"] != "a card"}
    # -- trigger other (wave 36A) -- 603.2c: "Whenever one or more players sacrifice one or more creatures" (Evin, Waterdeep Opportunist), "… discard one or
    # more cards" (Hostile Investigator): every player's part of one batch is one event (the same players' parts, however many players did it)
    m = re.fullmatch(r"one or more players (?P<v>sacrifice|discard) (?P<o>one or more .+)", c)
    if m:
        found = _player_action(f"a player {m['v']}s {m['o']}")
        return None if found is None or found.get("player") != "any" else {**found, "all_players": True}
    # "Whenever you sacrifice ~ or another creature" (Kingpin, Wilson Fisk): either sacrifice, each its own event (603.2c; ~ is not "another")
    m = re.fullmatch(r"you sacrifice ~ or (?P<o>another .+)", c)
    if m:
        mine, other = _parse("you sacrifice ~"), _parse(f"you sacrifice {m['o']}")
        if mine is None or other is None or other.get("aggregate"):
            return None
        return {"event": "either", "subject": "player", "player": "you", "conds": [mine, other]}
    m = re.fullmatch(rf"{_P} (?P<v>sacrifices?|discards?|cycles? or discards?|cycles?|creates?|mills?) (?P<o>.+)", c)
    if not m:
        # -- triggers (wave 17D) -- "Whenever one or more nonland cards are milled" (701.17a: put from a library into its owner's graveyard)
        m = re.fullmatch(r"(?P<o>one or more .+?) (?:is|are) milled", c)
        if m is None:
            return None
        return {"event": "mill", "subject": "player", "player": "any", "obj": _object_sel(m["o"], card=True), "aggregate": True}
    v = m["v"]
    if " or " in v:  # 702.29d: "cycles or discards" triggers once for a cycled card — it was discarded (702.29a)
        event = "discard"
    else:
        event = next(e for w, e in (("sacrifice", "sacrifice"), ("discard", "discard"), ("cycle", "cycle"),
                                    ("create", "create_token"), ("mill", "mill")) if v.startswith(w))
    o = m["o"]
    if o in ("~", "this card") and event in ("sacrifice", "cycle", "discard") and m["p"] == "you":  # (wave 36A: "When you discard this card", Titanbones)
        # "When you sacrifice ~" (603.10a: looks back in time), "When you cycle ~" (702.29c: from
        # whatever zone the card went to)
        return {"event": event, "subject": "self"}
    aggregate = o.startswith("one or more ")
    if event == "create_token" and not re.search(r"\btokens?$", o):
        return None
    if not re.match(r"^(?:an?|one or more|another) ", o):
        return None
    card = event in ("discard", "cycle", "mill")
    return {"event": event, "subject": "player", "player": _PLAYERS[m["p"]], "obj": _object_sel(o, card=card),
            "aggregate": aggregate}


# -- activation (wave 11F) -- 602.2: "Whenever an opponent activates an ability of an artifact, creature, or land that
# isn't a mana ability", "Whenever you activate a loyalty ability". Mana abilities never use the stack (605.3b), so only
# "that isn't a mana ability" (or a loyalty ability, 606.1: never a mana ability, 605.1a) is read: ``nonmana``
# -- counters (wave 33C) -- "Whenever you activate an exhaust / a boast / a power-up ability" (Adrenaline Jockey, Frenzied Raider, Marvel Boy): the
# activated ability whose text begins with that ability word (702.177a, 702.142a, 702.193a: each is an activated ability, never a mana ability)
_ACTIVATE = re.compile(rf"{_P} activates? (?:(?P<loyalty>a loyalty ability)|an? (?P<word>exhaust|boast|power-up) ability|an ability)(?: of (?P<o>an? .+?)(?P<own> they control)?"
                       r"(?: on the battlefield)?)?(?P<nonmana> that isn't a mana ability)?"
                       r"(?: that targets (?P<tg>an? [a-z]+(?: or [a-z]+)?))?")
# -- stack interaction (wave 23B) -- 602.2, 603.2: "Whenever an ability of equipped creature is activated" (Illusionist's Bracers): an
# ability of what this permanent is attached to, activated by anyone; only abilities that use the stack are activated here (605.3b),
# so "if it isn't a mana ability" adds nothing
_ACTIVATED_HOST = re.compile(r"an ability of (?:equipped creature|enchanted creature|enchanted planeswalker|enchanted permanent) is activated")


def _ability_targets(what: str) -> list[str] | None:
    """"that targets a creature or player": a target of the activated ability that is any of these (selectors.targets_match)."""
    out: list[str] = []
    for part in what.split(" or "):
        part = re.sub(r"^an? ", "", part)
        if part == "player":
            out.append("targets:player|")
            continue
        sel = selectors.parse(part)
        if sel is None or sel.zones != ("battlefield",) or sel.player is not None or sel.extras or sel.ability is not None:
            return None
        out.append(f"targets:|{sel.key()}")
    return out


def _activate(c: str) -> Condition | None:
    if _ACTIVATED_HOST.fullmatch(c) is not None:
        return {"event": "activate", "subject": "host", "nonmana": True, "loyalty": False}
    m = _ACTIVATE.fullmatch(c)
    if m is None:
        return None
    sel = selectors.parse(re.sub(r"^an? ", "", m["o"])) if m["o"] else None
    if m["o"] and (sel is None or sel.player is not None or sel.card or (m["own"] and (sel.controller or sel.owner))):
        raise _Refuse
    tg = _ability_targets(m["tg"]) if m["tg"] else None
    if m["tg"] and (tg is None or m["loyalty"]):
        raise _Refuse
    return {"event": "activate", "subject": "player", "player": _PLAYERS[m["p"]], "nonmana": bool(m["nonmana"] or m["word"]),
            "loyalty": bool(m["loyalty"]), **({"obj": sel.key()} if sel is not None else {}), **({"own": True} if m["own"] else {}),
            **({"ability_targets": tg} if tg else {}), **({"word": m["word"]} if m["word"] else {})}


_PLAIN_COUNTERS = frozenset({"lore", "loyalty", "charge", "oil", "time", "quest", "stun", "flying", "shield"})


def _object_event(c: str) -> Condition | None:
    """Object events beyond the basic verbs: counters put on (122.6), leaving a graveyard (603.10a),
    becoming the target of a spell or ability (115.9, 603.2e), dealing damage (120.1)."""
    # -- crew & saddle (wave 23D) -- 702.122b / 702.171c: "Whenever ~ crews a Vehicle" / "~ saddles a Mount or crews a Vehicle during your
    # main phase" (a creature tapped to pay the cost; the Vehicle / Mount is the creature "on the other side"), 702.122e: "~ becomes crewed"
    m = re.fullmatch(r"~ (?:(?P<s>saddles a Mount) or )?(?P<c>crews a Vehicle)(?P<d> during your main phase)?", c)
    if m:
        crew = {"event": "crew", "subject": "self", "other": selectors.Selector(types=("Artifact",), subtypes=("Vehicle",)).key()}
        saddle = {"event": "saddle", "subject": "self", "other": selectors.Selector(subtypes=("Mount",)).key()}
        main = {"main_phase": True} if m["d"] else {}
        if not m["s"]:
            return {**crew, **main, **({"during": "you"} if m["d"] else {})}
        return {"event": "either", "subject": "self", "other": crew["other"], "conds": [{**crew, **main}, {**saddle, **main}],
                **({"during": "you"} if m["d"] else {})}  # (``other``: the Vehicle or Mount, for "that Mount or Vehicle")
    if c == "~ becomes crewed":
        return {"event": "crewed", "subject": "self"}
    # -- attachment events (wave 30S) -- 603.2e, 701.3: "Whenever this Equipment becomes attached to a creature" (Enormous Energy Blade),
    # "Whenever an Aura you control becomes attached to a creature you control" (Siona), "Whenever an Aura becomes attached to this
    # creature" (Brood Keeper: ``to`` self); 701.3d, 603.10c: "Whenever this Equipment becomes unattached from a permanent" (Grafted
    # Wargear: it looks back in time; the permanent it let go of is the one "on the other side" while it is still on the battlefield)
    m = re.fullmatch(r"(?P<s>~|an? Aura(?: you control)?) becomes? (?:attached to (?P<h>~|an? .+)|(?P<u>unattached) from a permanent)", c)
    if m:
        base = _subject(m["s"])
        if base is None or (m["u"] and base["subject"] != "self"):
            raise _Refuse
        if m["u"]:
            return {**base, "event": "unattached", "other": selectors.Selector().key()}
        return {**base, "event": "attached", **({"to": "self"} if m["h"] == "~" else {"other": _object_sel(m["h"])})}
    # -- keyword triggers (wave 23D) -- 702.110b: "When ~ exploits a creature", "Whenever a creature you control exploits a non-Human creature"
    m = re.fullmatch(r"(?P<s>~|an? .+?|another .+?) exploits (?P<o>an? .+)", c)
    if m:
        base = _subject(m["s"])
        if base is None or base.get("aggregate"):
            raise _Refuse
        return {**base, "event": "exploit", "exploited": _object_sel(m["o"])}
    # "one or more +1/+1 counters are put on ~", "a +1/+1 counter is put on a creature you control"
    # -- counters (wave 5H) -- "you put one or more +1/+1 counters on a creature you control" (122.6, 122.6a: the player
    # who put them — the step's actor at the counter choke point). Only +1/+1 counters: -1/-1 counters dealt as damage
    # (wither, infect: 120.3d: wave 17D records the source controller who puts them); and "counters"
    # of any kind put at once land in one step per kind (one trigger per step, not per event): both refused.
    # -- counters (wave 7C) -- also "a counter" / "a +1/+1 counter", counters of any kind, "an opponent puts one or more
    # counters on a creature they control", and subjects like "a creature you don't control" / "one or more other Heroes"
    m = re.fullmatch(r"(?P<p>you|an opponent) puts? (?:one or more|an?) (?:(?P<k>\+1/\+1|-1/-1|[a-z]+) )?counters? on (?P<s>.+)", c)
    if m:
        own = m["p"] == "an opponent" and m["s"].endswith(" they control")
        if m["p"] == "an opponent" and not own:
            raise _Refuse
        base = _subject(m["s"][: -len(" they control")] if own else m["s"], many=True)
        if base is None or m["k"] == "counters" or (m["k"] and m["k"] not in _PLAIN_COUNTERS and
                                                                 m["k"] not in ("+1/+1", "-1/-1")):
            raise _Refuse
        return {**base, "event": "counters_put", **({"counter": m["k"]} if m["k"] else {}),
                "by": "you" if m["p"] == "you" else "opponent", **({"own": True} if own else {})}
    # -- end counters (wave 5H) --
    # -- keywords (wave 15E) -- 702.63a vanishing: "When the last time counter is removed from this permanent"
    m = re.fullmatch(r"the last (?P<k>[a-z]+) counter is removed from ~", c)
    if m:
        return {"subject": "self", "event": "counters_removed", "counter": m["k"], "last": True}
    # -- most-played cards (wave 43B) -- "When the twelfth hour counter is put on this artifact" (Midnight Clock), "When the fourth plan counter is put on this
    # enchantment" (the plan-counter enchantments): the ability triggers when counters are put on it and it had fewer than that many before and that many or
    # more after (the ruling, 2019-10-04), however many counters one event put at once
    m = re.fullmatch(r"the (?P<n>second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth) (?P<k>[a-z]+) counter is put on (?:~|this [a-z]+)", c)
    if m:
        return {"subject": "self", "event": "counters_put", "counter": m["k"],
                "nth": ("second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth", "eleventh", "twelfth").index(m["n"]) + 2}
    m = re.fullmatch(r"(?:one or more|an?) (?:(?P<k>\+1/\+1|-1/-1|[a-z]+) )?counters? (?:is|are) put on (?P<s>.+)", c)
    if m:
        base = _subject(m["s"])
        if base is None:
            raise _Refuse
        return {**base, "event": "counters_put", "counter": m["k"]}
    # "one or more creature cards leave your graveyard", "a card leaves your graveyard"
    m = re.fullmatch(r"(?P<o>(?:one or more|an?) .+?) leaves? (?:your|an opponent's) graveyard", c)  # (wave 19C: an opponent's)
    if m:
        sel = selectors.from_key(_object_sel(m["o"], card=True))
        return {"event": "leave_graveyard", "subject": "sel",
                "sel": selectors.replace(sel, zone_owner="opponent" if c.endswith("an opponent's graveyard") else "you").key(),
                "aggregate": m["o"].startswith("one or more ")}
    # "~ becomes the target of a spell or ability an opponent controls [for the first time each turn]"
    # -- history (wave 22E) -- also "you" (115.1: a player is a target too), "you or a permanent you control", and the kind of spell
    # ("an instant or sorcery spell", "an Aura spell": read on the stack as it targeted); "for the first time each turn" is the
    # first of THOSE events this turn (any, or by you / an opponent when named), kept in triggers._targeted_generic
    m = re.fullmatch(r"(?P<s>.+?) becomes? the target of (?P<what>a spell or ability|an ability|an? (?:(?P<adj>[\w ]+?) )?spell)"
                     r"(?: (?P<by>an opponent controls|you control))?(?P<first> for the first time each turn)?", c)
    if m:
        extra: Condition = {"event": "targeted", "by": {"an opponent controls": "opponent", "you control": "you"}.get(m["by"] or "", "any"),
                            "spell_only": m["what"] not in ("a spell or ability", "an ability"), "first_each_turn": bool(m["first"]),
                            **({"ability_only": True} if m["what"] == "an ability" else {})}  # (wave 23B: Loki's "an ability you control")
        if m["adj"]:
            kind = selectors.parse(f"{m['adj']} spell")
            if kind is None or kind.zones != ("stack",) or kind.player is not None:
                raise _Refuse
            extra["spell_sel"] = kind.key()
        if m["s"] == "you":
            return {**extra, "subject": "player", "player": "you"}
        if m["s"] == "a player or permanent" and not m["first"]:  # -- stack interaction (wave 23B) -- 115.1: a player or a permanent (Loki)
            return {"event": "either", "subject": "mixed",
                    "conds": [{**extra, "subject": "player", "player": "any"}, {**extra, **(_subject("a permanent") or {})}]}
        parts = re.fullmatch(r"you or (?P<r>an? permanent you control|another permanent you control|an? creature you control)", m["s"])
        if parts:
            perm = _subject(parts["r"])
            if perm is None or m["first"]:
                raise _Refuse
            return {"event": "either", "subject": "mixed",
                    "conds": [{**extra, "subject": "player", "player": "you"}, {**extra, **perm}]}
        base = _subject(m["s"], host=True)
        if base is None or (m["first"] and base["subject"] != "self"):
            raise _Refuse
        return {**base, **extra}
    # "~ is dealt combat damage" (a creature dealt lethal damage was still dealt it: 510.3a, 603.10a);
    # "you're dealt combat damage", "an opponent is dealt noncombat damage": the player dealt it
    m = re.fullmatch(r"(?P<s>.+?)(?: is|'re| are) dealt (?P<c>combat |noncombat )?damage", c)
    if m and (m["c"] or m["s"] in ("you", "an opponent", "a player", "enchanted player")):  # (wave 25D: a Curse's "enchanted player")
        if m["s"] in ("you", "an opponent", "a player", "enchanted player"):
            dealt: Condition | None = {"subject": "player", "player": _PLAYERS[m["s"]]}
        else:
            dealt = _subject(m["s"], host=True)
        if dealt is None:
            raise _Refuse
        return {**dealt, "event": "dealt_damage", "combat": {"combat ": True, "noncombat ": False}.get(m["c"] or "")}
    # "~ deals damage", "~ deals combat damage to a creature", "~ deals noncombat damage to a player",
    # "~ deals combat damage to a player or planeswalker" (510.2; 120.1), "a creature deals combat
    # damage to one of your opponents", "one or more creatures deal combat damage to one of your opponents"
    # -- source damage (wave 11F) -- "a source [you control | an opponent controls] deals [noncombat] damage [to …]": any
    # source of damage (120.1: a permanent, or a spell), once per source and recipient (603.2); ``ctl``: its controller
    # (-- counters (wave 41A) -- "a red source you control deals damage to one or more permanents and/or players" (The Red Terror): the source's color as it
    # dealt the damage (105.2), and a recipient that is any permanent or player — every recipient there is, so it is "deals damage" (120.1), once per source for
    # the batch (603.2c))
    m = re.fullmatch(rf"a(?P<col> white| blue| black| red| green| colorless)? source(?P<ctl> you control| an opponent controls)? deals? (?:(?P<min>\w+) or more )?(?P<c>combat |noncombat )?"
                     rf"damage(?P<to>{_DAMAGE_TO_RE}|(?P<all> to one or more permanents and/or players))", c)
    # (-- trigger damage (wave 39B) -- "a source you control deals noncombat damage to one or more of your opponents" (Molten Lavamancer): once per source
    # for the batch (603.2c; triggers._fire_generic keys it by the source); a threshold over "one or more" recipients isn't read)
    if m and m["to"] != " to one or more creatures" and (m["to"] or not m["min"]) and not (
            m["min"] and m["to"] in (" to one or more players", " to your opponents", " to one or more of your opponents")) and not (m["all"] and m["min"]):
        return {"event": "deal_damage", "subject": "source", "to": "any" if m["all"] else _DAMAGE_TO[m["to"]],
                **({"color": m["col"].strip()} if m["col"] else {}),
                **({"min": _count(m["min"])} if m["min"] else {}), **({"aggregate": True} if m["to"] in _ONE_OR_MORE_TO else {}),
                "ctl": {" you control": "you", " an opponent controls": "opponent"}.get(m["ctl"] or "", "any"),
                "combat": {"combat ": True, "noncombat ": False}.get(m["c"] or "")}
    # -- trigger tail (wave 15B) -- "Whenever ~ deals damage to a Vampire": a creature of that type (120.1), as it last existed
    m = re.fullmatch(r"(?P<head>.+? deals? (?:(?:combat|noncombat) )?damage) to an? (?P<ty>[A-Z][\w-]+(?: or [A-Z][\w-]+)?)", c)
    if m:
        from app.rules.creature_types import CREATURE_TYPES

        types = m["ty"].split(" or ")
        inner = _parse(f"{m['head']} to a creature")
        if inner is None or not all(t in CREATURE_TYPES for t in types):
            raise _Refuse
        return {**inner, "to_types": types}
    m = re.fullmatch(rf"(?P<s>.+?) deals? (?:(?P<min>\w+) or more )?(?P<c>combat |noncombat )?damage(?P<to>{_DAMAGE_TO_RE}|)", c)
    # (combat damage to a player / an opponent and damage to an opponent: the verbs below)
    if m and not (m["to"] == " to an opponent" and m["c"] != "noncombat " and not m["min"]) and \
            not (m["to"] == " to a player" and m["c"] == "combat " and not m["min"]) and (m["to"] or not m["min"]):  # (wave 39B: a threshold is read here: Deus of Calamity)
        to = _DAMAGE_TO[m["to"]]
        who = _subject(m["s"], host=True, many=to in ("opponent", "player", "player_or_pw", "player_or_battle", "players",
                                                      "opponents", "you"))
        if who is None:
            return None
        # (a "min" is the damage one source dealt one recipient in one event: 120.3; "to one or more creatures": 603.2c)
        return {**who, "event": "deal_damage", "to": to, **({"min": _count(m["min"])} if m["min"] else {}),
                **({"aggregate": True} if to == "creatures" else {}),
                "combat": {"combat ": True, "noncombat ": False}.get(m["c"] or "")}
    return None
