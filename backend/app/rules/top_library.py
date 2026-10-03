"""-- top of library (wave 5I) -- more wordings of "you may cast … from the top of your library", and the private
"look at the top card. If it's a …, you may reveal it and put it into your hand" (Herald's Horn).

Researched against the stored Comprehensive Rules (2026-09-25):

* 601.3 — a permission lets a player begin to cast a spell from somewhere other than their hand; 601.3e: whether the
  card would be a spell of the named kind is read from the card as the spell it would become.
* 401.5 — "you may look at the top card of your library any time" shows that card to its owner alone; a cast from
  the top is offered only for a card the player can see (permissions.define_static keeps that check: the card must
  also reveal the top card or let its owner look at it). Radha's "You may look at the top card of your library any
  time, and you may play lands from the top of your library." is both on one line (``look``: refresh_reveals).
* 701.20e — "look at" is private; a choice that appears only when the hidden card qualifies tells the other players
  what the card is (a leak by omission), so "If it's a creature card of the chosen type, you may reveal it and put it
  into your hand" is asked as a pick from among the one card looked at: the question is asked whatever the card is,
  and only a matching card can be chosen (``private_gate``). A card left on top and a card that didn't qualify look
  the same to the table, as at a real table.
* 205.3m / 614.12a — "of the chosen type" is the source permanent's "As ~ enters, choose a creature type" answer
  (chosen.py); read from the source permanent (``spell``, matched with that source).
* 700.6 — historic: an artifact, a legendary, or a Saga ("historic lands": a legendary or artifact land).

Wordings read (all others stay manual):

* "You may cast Dragon spells / artifact spells and colorless spells / Angel spells and Human spells / historic
  spells / creature spells of the chosen type / spells with mana value 4 or greater / spells with flash or flying
  from the top of your library."
* "You may play historic lands and cast historic spells …", "You may play lands and cast spells with mana value 4
  or greater …".
* "Once each turn, you may cast a creature spell with power 2 or less from the top of your library." (a static
  permission used up by the cast, on any player's turn: ``once_any``).
"""

from __future__ import annotations

import re
from typing import Any

from app.rules import selectors

Definition = dict[str, Any]

_LINE = re.compile(
    r"^(?P<once>once during each of your turns, |once each turn, )?"
    r"(?P<look>you may look at the top card of your library any time, and )?"
    r"you may (?P<what>.+?) from (?P<zone>the top of your library|your graveyard)$")
_LANDS = re.compile(r"^play (?P<hist>historic )?lands(?: and (?P<rest>cast .+))?$")
_CAST = re.compile(r"^cast (?P<art>an? )?(?P<spells>.+)$")
_TWO = re.compile(r"^(?P<a>[A-Za-z][A-Za-z-]*) spells and (?P<b>[A-Za-z][A-Za-z-]*) spells$")
_ONE = re.compile(r"^(?:(?P<sel>[A-Za-z][A-Za-z' -]*?) )?(?P<sp>spells?)(?: (?P<tail>with .+|of the chosen type))?$")
_KEYWORDS_OR = re.compile(r"^with (?P<a>flash|flying|trample|haste|vigilance|deathtouch|lifelink) or "
                          r"(?P<b>flash|flying|trample|haste|vigilance|deathtouch|lifelink)$")


def _key(sel: str | None, tail: str | None) -> str | None:
    from app.rules.permissions import spell_filter

    if tail == "of the chosen type":
        if not sel:
            return None
        parsed = selectors.parse(f"{sel} spell of the chosen type")
        if parsed is None or parsed.player is not None or parsed.zones != ("stack",):
            return None
        return parsed.key()
    if sel is None and tail is None:
        return None
    return spell_filter(sel, tail)


def _spells(text: str, single: bool) -> dict[str, Any] | None:
    """The kinds of spell a permission names: {"filter": key} / {"any_of": [keys]} / {"spell": key with the chosen
    type} / {} (every spell); None when not read."""
    if text == "spells" and not single:
        return {}
    m = _TWO.fullmatch(text)
    if m and not single:
        a, b = _key(m["a"], None), _key(m["b"], None)
        return {"any_of": [a, b]} if a and b else None
    m = _ONE.fullmatch(text)
    if m is None or (m["sp"] == "spell") != single:
        return None
    tail = m["tail"]
    if tail and (k := _KEYWORDS_OR.fullmatch(tail)) is not None and not m["sel"]:
        a, b = _key(None, f"with {k['a']}"), _key(None, f"with {k['b']}")
        return {"any_of": [a, b]} if a and b else None
    if tail and re.search(r" or (?!greater$|less$|more$)", tail):
        return None
    key = _key(m["sel"], tail)
    if key is None:
        return None
    return {"spell": key} if tail == "of the chosen type" else {"filter": key}


def permission(t: str, lines: tuple[str, ...]) -> Definition | None:
    """The definition of a "you may cast / play … from the top of your library" line in one of the wordings above
    (``t``: the line lowercased at its start, without its period), or None (not one of them: the older grammar,
    permissions.PERMISSION, reads the plain ones)."""
    from app.rules.permissions import TOP_LOOK, TOP_REVEAL, _lower_first

    m = _LINE.fullmatch(t)
    if m is None or m["zone"] != "the top of your library":
        return None
    what = m["what"]
    play, land, cast = False, None, False
    spells: dict[str, Any] | None = {}
    lands = _LANDS.fullmatch(what)
    if lands:
        play, land = True, ("historic" if lands["hist"] else None)
        if lands["rest"]:
            what = lands["rest"]
        else:
            what = ""
    if what:
        c = _CAST.fullmatch(what)
        if c is None:
            return None
        single = bool(c["art"])
        if single != bool(m["once"]):
            return None  # ("you may cast a creature spell from the top": once a turn, or not English)
        spells = _spells(c["spells"], single)
        if spells is None:
            return None
        cast = True
        if lands and land == "historic" and spells != {"filter": _key("historic", None)}:
            return None  # ("play historic lands and cast <other> spells": not a printed wording)
    elif not play:
        return None
    if land and not cast:
        return None
    if not (spells or land or m["look"] or m["once"]):
        return None  # (the plain wordings: permissions.PERMISSION)
    seen = bool(m["look"]) or any(_lower_first(x.strip().rstrip(".")) in (TOP_REVEAL, TOP_LOOK) for x in lines)
    if not seen:
        return None  # (401.5: the player must be able to see the card; see permissions.define_static)
    d: Definition = {"kind": "static", "static": "permission", "zone": "library_top", "once": bool(m["once"]),
                     "flash": False, "self": False, "play": play, "cast": cast, "filter": spells.get("filter"), "effects": []}
    if m["once"] == "once each turn, ":
        d["once_any"] = True  # (any player's turn, not only its controller's)
    if spells.get("any_of"):
        d["any_of"] = spells["any_of"]
    if spells.get("spell"):
        d["spell"] = spells["spell"]
    if land:
        d["land_filter"] = land
    if m["look"]:
        d["look"] = True  # 401.5 on the same line: app/rules/permissions.refresh_reveals
    return d


def historic_land(ch: Any) -> bool:
    """700.6: a historic land card (legendary, or an artifact land; a Saga is never a land)."""
    return "Legendary" in ch.supertypes or "Artifact" in ch.types or "Saga" in ch.subtypes


def static_ok(state: Any, player: str, card: Any, ch: Any, info: Any, d: Definition, src: Any, verb: str) -> bool:
    """The extra tests of a permission read here: kinds of spell ("artifact spells and colorless spells"), the
    source's chosen type, historic lands."""
    from app.rules.permissions import spell_matches

    if verb == "play":
        return not (d.get("land_filter") == "historic" and not historic_land(ch))
    if d.get("any_of") and not any(spell_matches(state, player, card, ch, k, info) for k in d["any_of"]):
        return False
    return not (d.get("spell") and not spell_matches(state, player, card, ch, d["spell"], info, source=src.id))


# -- "If it's a …, you may reveal it and put it into your hand" (701.20e) ------------------------------------------
def private_gate(found: tuple[list[dict[str, Any]], Any, bool] | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """"Look at the top card of your library. If it's a creature card [of the chosen type], you may reveal it and put
    it into your hand.": the same as "you may reveal a creature card from among it and put it into your hand" — asked
    whatever the hidden card is, so nobody learns what it was from whether a question appeared."""
    if found is None:
        return None
    effects = found[0]
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(effects):
        e = effects[i]
        look = out[-1] if out else None
        nxt = effects[i + 1] if i + 1 < len(effects) else None
        if (e.get("do") == "only_if" and look is not None and look.get("do") == "look_top" and look.get("n") == 1
                and not look.get("reveal") and not look.get("until") and look.get("player") == "you"
                and int(e.get("skip", 0)) == 1 and not e.get("bind") and nxt is not None
                and nxt.get("do") == "pick_looked" and nxt.get("which") == "that" and nxt.get("optional")
                and isinstance(e.get("cond"), dict) and set(e["cond"]) == {"object", "is"}
                and e["cond"]["object"] == f"ref:{look.get('as')}"):
            pick = {k: v for k, v in nxt.items() if k != "which"}
            out.append({**pick, "n": 1, "sel": e["cond"]["is"], "optional": True,
                        "prompt": "You may choose the card you looked at if it qualifies"})
            i += 2
            continue
        out.append(e)
        i += 1
    if len(out) == len(effects):
        return found
    return out, found[1], found[2]
