"""-- triggers (wave 5D) -- wordings of triggered abilities read as the plainer ones the grammar already knows.
Researched against CR 2026-09-25.

* "they" for the player a trigger is about: "Whenever an opponent draws a card, they lose 2 life." (Sheoldred, the
  Apocalypse) reads as "that player loses 2 life" — only when the trigger event names one player (the player who
  drew / gained / was dealt damage …, or the player whose step it is: "At the beginning of each opponent's upkeep,
  they lose 1 life") and only as the subject that opens the ability.
* "that player draws an additional card" in "At the beginning of each player's draw step, …" (Howling Mine, Kami of
  the Crescent Moon, Dictate of Kruphix): a draw on top of the turn-based draw (504.1), i.e. that player draws a card.
* "you may have [~ / it / target opponent / that player …] [do X]": an optional instruction (603.5: the choice is made
  as it resolves) whose doer is that object or player — the same as "[it] [does X]" with "you may".
"""

from __future__ import annotations

import re
from typing import Any

# third person singular of the verbs read here ("they lose" → "that player loses")
_VERBS = {"lose": "loses", "draw": "draws", "discard": "discards", "sacrifice": "sacrifices", "gain": "gains",
          "mill": "mills", "get": "gets", "create": "creates", "deal": "deals", "exile": "exiles", "reveal": "reveals",
          "shuffle": "shuffles", "return": "returns", "put": "puts", "search": "searches", "scry": "scries"}
_VERB_RE = "|".join(sorted(_VERBS, key=len, reverse=True))
_THEY = re.compile(rf"^(?P<i>if [^,]+, )?they (?P<v>{_VERB_RE})\b")  # (wave 21B: after an intervening "if …, ", 603.4)
_HAVE = re.compile(rf"^have (?P<s>~|it|target (?:player|opponent)|that player|each opponent) (?P<v>{_VERB_RE})\b")


def they_names_event_player(name: str, cond: dict[str, Any] | None, has_player: bool) -> bool:
    from app.rules.scripts import STEP_PLAYER_WHOSE

    if has_player:
        return True
    return name.startswith("step:") and name.rsplit(":", 1)[-1] in STEP_PLAYER_WHOSE


def rewrite_body(body: str, name: str, cond: dict[str, Any] | None, has_player: bool) -> str:
    """The body of a triggered ability with these wordings replaced by the plainer ones (else unchanged)."""
    if they_names_event_player(name, cond, has_player):
        body = _THEY.sub(lambda m: f"{m['i'] or ''}that player {_VERBS[m['v']]}", body)
        # -- damage wordings (wave 6B) -- "At the beginning of each player's upkeep, ~ deals 1 damage to them."
        body = re.sub(r"\b(deals? (?:\d+|X) damage) to them\b", r"\1 to that player", body)
        # -- trigger other (wave 25B) -- "… deals 2 damage to that player unless they control two or more basic lands": they are that player
        body = re.sub(r"\b(unless|if) they (control|have)\b", lambda m: f"{m[1]} that player {'controls' if m[2] == 'control' else 'has'}", body)
    # -- intervening ifs (wave 11F) -- "if you have fewer than seven cards in hand, draw cards equal to the difference": the
    # difference between that number and the cards in hand as it resolves (608.2h; the "if" holds again then, 603.4)
    body = re.sub(r"^(if you have fewer than (\w+) cards in hand, draw cards equal to) the difference\.$",
                  r"\1 \2 minus the number of cards in your hand.", body)
    # -- trigger damage (wave 39B) -- "if a Giant, Wizard, or spell you controlled dealt damage to it this turn" (Aegar): the list's commas would end the
    # condition early; it is "a Giant or Wizard or spell" (conditions._dealt_by_kinds)
    body = re.sub(r"^(if an? [A-Z]\w+(?:, [A-Z]\w+)*), or (spell|[A-Z]\w+)( you controlled dealt damage to )",
                  lambda m: f"{m[1].replace(', ', ' or ')} or {m[2]}{m[3]}", body)
    if (cond or {}).get("excess"):  # -- trigger damage (wave 39B) -- 120.10: "where X is that excess damage" (Fall of Cair Andros): the amount of an "is dealt excess
        body = re.sub(r"\b(?:that excess damage|the excess damage|the excess)\b", "the amount of damage dealt", body)  # damage" event is the excess (triggers._fire_generic)
    if (cond or {}).get("event") == "cast":  # "…, if at least four mana was spent to cast it": the spell cast
        body = re.sub(r"^(if (?:at least \w+|\w+ or more) mana was spent to cast) it,", r"\1 that spell,", body)
        # (-- mana provenance (wave 18B) -- "if mana from a Treasure / three or more mana from creatures was spent to cast it")
        body = re.sub(r"^(if (?:(?:at least )?\w+ (?:or more )?)?mana from [^,]+? (?:was|were) spent to cast) it,", r"\1 that spell,", body)
    # -- trailing & intervening ifs (wave 38A) -- "…, draw a card. Draw another card if you've completed a dungeon." (Imoen): a later sentence's own draw,
    # gated by its trailing "if" (608.2c) — the plain "draw a card"; a name that is two creatures takes a plural verb ("Tokka & Rahzar deal 3 damage")
    body = re.sub(r"(?<=\. )([Dd]raw) (?:another|an additional) card(?= if )", r"\1 a card", body)
    body = re.sub(r"(^|, )~ deal (?=\d|X)", r"\1~ deals ", body)
    if (cond or {}).get("event") == "attack" and (cond or {}).get("subject") == "sel":  # -- trailing & intervening ifs (wave 38A) -- 508.1: "the creature that
        body = body.replace("the creature that attacked", "that creature")  # attacked" (Aradesh) is the object the event is about, "that creature"
    if name == "cast_self":  # -- history (wave 22E) -- "When you cast this spell, … where X is the amount of mana spent to cast it" (Prossh)
        body = re.sub(r"\bthe amount of mana spent to cast it\b", "the amount of mana spent to cast this spell", body)
    if name == "dies_self" or (cond is not None and cond.get("event") == "die" and cond.get("subject") == "self"):
        # -- trigger other (wave 25B) -- "When this creature dies, … return this card to …": the card it is now, in its owner's graveyard (400.7: "it")
        body = re.sub(r"\b(return|put|exile|shuffle) this card\b", r"\1 it", body)
    if cond is not None and cond.get("subject") == "sel" and cond.get("sel"):  # -- trigger other (wave 25B) -- "Whenever another Wizard you
        from app.rules import (
            selectors,  # control enters, … a copy of that Wizard": the object the event is about, "that creature"
        )
        from app.rules.creature_types import CREATURE_TYPES

        for sub in selectors.from_key(cond["sel"]).subtypes:
            body = re.sub(rf"\bthat {re.escape(sub)}\b", "that creature" if sub in CREATURE_TYPES else "that permanent", body)
    if cond is not None and cond.get("subject") == "source":  # -- source damage (wave 11F) -- 609.7: its controller
        body = re.sub(r"\bthat source's controller\b", "that player", body)
    if cond is not None and (cond.get("event") == "targeted" or (cond.get("event") == "either" and all(
            c.get("event") == "targeted" for c in cond.get("conds", [])))):  # -- triggers (wave 21B; wave 22E: also "you or a permanent") -- 115.1: "that spell's controller" is the player whose spell or ability targeted it
        body = re.sub(r"\bthat spell(?: or ability)?'s controller\b", "that player", body)
    if cond is not None and cond.get("event") == "attack" and cond.get("defender") == "player":  # -- review (wave 21) -- "attacks a player,
        body = re.sub(r"^if no opponent has more life than that player,", "if no opponent has more life than defending player,", body)  # if no
        # opponent has more life than that player" (the alliance Backgrounds): the player attacked, its defending player (508.5)
    if name.startswith("step:draw:") and name.rsplit(":", 1)[-1] in ("each", "opponent"):
        # 504.1: the active player draws in the draw step; "an additional card" is one more card
        body = re.sub(r"\bthat player draws an additional card\.$", "that player draws a card.", body)
        body = re.sub(r"\bthat player draws (two|three) additional cards\.$", r"that player draws \1 cards.", body)
    from app.rules import drawn_toll  # -- drawn this turn (wave 18G) --

    body = drawn_toll.rewrite(body)
    # -- counters (wave 7C) -- heroic: "Whenever you cast a spell that targets ~, put a +1/+1 counter on it": the creature
    # that was targeted (the spell is "that spell"), which is ~ itself
    if (cond or {}).get("event") == "cast":  # -- trigger other (wave 25B) -- "If that spell has mana value 5 or greater, …": the spell's mana value
        body = re.sub(r"\b([Ii]f) that spell has mana value (\d+|X) or (greater|less)\b", r"\1 that spell's mana value is \2 or \3", body)
    if (cond or {}).get("event") == "cast":  # -- triggers (wave 21B) -- "Whenever you cast a spell, you lose life equal to its mana value"
        body = re.sub(r"^((?:you )?(?:lose|gain)s? life equal to) its mana value\.$", r"\1 that spell's mana value.", body)
        body = re.sub(r"^(if the amount of mana spent to cast it was less than its mana value, .+? equal to) the difference\.$",
                      r"\1 that spell's mana value minus the amount of mana spent to cast that spell.", body)
    if cond is not None and cond.get("event") == "cast" and cond.get("targets") == "self":
        body = re.sub(r"\b(on|to) it\b", r"\1 ~", body)
    return body


_PUT_NUMBER_OF = re.compile(r"\b(?P<c>[Pp])ut a number of (?P<k>\+1/\+1|-1/-1|[a-z]+) counters equal to (?P<v>[^.]+?) on (?P<t>[^.]+?)\.")
_NUMBER_OF = re.compile(r"\b(?P<c>[Cc])reate a number of (?P<what>[^.]+? tokens?(?: with [^.]+?)?) equal to (?P<v>[^.]+)\.")
_SAC_OF = re.compile(r"\bthe (power|toughness|mana value) of the sacrificed (creature|artifact|permanent|land|enchantment)\b")
_SAC_ITS = re.compile(r"(\bthe sacrificed (creature|artifact|permanent|land|enchantment)'s (?:power|toughness|mana value)\b[^.]*? equal to )"
                      r"its (power|toughness|mana value)")
_GAIN_AND_DRAW = re.compile(r"^you gain life and draw cards equal to (?P<v>[^.]+)\.$")


def plain_amounts(body: str) -> str:
    """"create a number of tapped Treasure tokens equal to its power" → "create X tapped Treasure tokens, where X is its
    power" (Goldvein Hydra; 107.3c: one X for the instruction); "you gain life and draw cards equal to its power" →
    both amounts spelled out (Lifeblood Hydra: the same value, read once per instruction from the object as it last
    existed, 608.2h)."""
    # -- amounts (wave 12C) -- the sacrificed object's statistics, worded the way the value grammar reads them (608.2h):
    # "the mana value of the sacrificed permanent" / "…equal to the sacrificed creature's power, then … equal to its toughness"
    body = _SAC_OF.sub(r"the sacrificed \2's \1", body)
    body = _SAC_ITS.sub(r"\1the sacrificed \2's \3", body)
    body = _NUMBER_OF.sub(lambda m: f"{m['c']}reate X {m['what']}, where X is {m['v']}.", body)
    # -- trigger other (wave 25B) -- "put a number of +1/+1 counters equal to its power on up to one target creature": X counters, where X is it
    body = _PUT_NUMBER_OF.sub(lambda m: f"{m['c']}ut X {m['k']} counters on {m['t']}, where X is {m['v']}.", body)
    m = _GAIN_AND_DRAW.match(body.strip())
    if m is not None:
        body = f"you gain life equal to {m['v']}. Draw cards equal to {m['v']}."
    return body


def comma_condition(text: str, m: re.Match[str]) -> re.Match[str]:
    """"Whenever you cast an Aura, Equipment, or Vehicle spell, draw a card.": the trigger condition runs to the first
    comma after which the condition grammar reads it (app/rules/events.py) — the shortest such, so "Whenever X, if Y,
    Z" keeps its intervening "if"; the match unchanged when the plain split reads or no longer one does."""
    from app.rules import events

    # a list in the condition ("an Aura, Equipment, or Vehicle spell"): the whole list, even when its first word alone
    # would read ("you cast an Aura")
    listed = re.match(r"^(?:When|Whenever) (?P<cond>.+?\b(?:[\w-]+, )+(?:or|and|and/or) [^,]+), (?P<body>.+)$", text,
                      re.DOTALL)
    if listed is not None and events.parse_condition(listed["cond"]) is not None:
        return listed
    if events.parse_condition(m["cond"]) is not None:
        return m
    head = re.match(r"^(?:When|Whenever) ", text)
    if head is None:
        return m
    rest = text[head.end():]
    for found in re.finditer(r", ", rest):
        cond = rest[: found.start()]
        if len(cond) <= len(m["cond"]):
            continue
        if events.parse_condition(cond) is not None:
            again = re.match(rf"^(?:When|Whenever) (?P<cond>{re.escape(cond)}), (?P<body>.+)$", text, re.DOTALL)
            return again if again is not None else m
    return m


def have_subject(text: str) -> str:
    """"have ~ deal 1 damage to any target" → "~ deals 1 damage to any target" (after "you may")."""
    # -- grammar (wave 11C) -- "you may have Ally creatures you control gain flying …": a group, so no third-person -s
    text = re.sub(r"^have (?P<s>[A-Z][\w-]* creatures you control|[A-Z][\w-]+s you control) (?P<v>gain|get)\b", r"\g<s> \g<v>", text)
    return _HAVE.sub(lambda m: f"{m['s']} {_VERBS[m['v']]}", text)
