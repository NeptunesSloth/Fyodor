"""-- player-relative selectors (wave 53A) -- a player's hand, library or graveyard as the set an instruction acts on: "Exile all cards from target
player's hand and graveyard." (Identity Crisis), "Target player exiles all land cards from their graveyard." (Mudhole), "Exile all cards from target
player's library, then that player shuffles their hand into their library." (Jace, the Mind Sculptor), "Exile all but the bottom card of target player's
library." (Nicol Bolas, the Ravager), "You may have that player shuffle." (Portent).

State: none. The set is read when the instruction is carried out (608.2c), from the player the reference names then: ``zones_of:<zone[,zone]>:<player
reference>|<selector key or empty>`` (effects._cards reads it; the reference is any ``effects._players`` form: "target", "target:1", "tp:0", "event_player",
"that_player" until scripts.resolve_it binds it). A library is read as exile_top's ``player`` (top of the library first); nothing here is hidden: what is exiled
goes to exile face up (406.3 / 400.1: nothing says otherwise), so the filter on a hand or library reveals only what is then public anyway.

Decisions: none for the controller of the spell (the set is "all"); the shuffle "you may have that player shuffle" is the controller's choice (701.24a:
the player whose library it is shuffles it - the choice is whether to have them).

Rules: 400.1 (zones), 401.5 / 402.3 (a library is not looked through by its owner; a hand is private), 406.3, 701.24a (shuffling), 608.2c, 115.10a.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.rules import selectors

if TYPE_CHECKING:
    from app.rules.context import Context
    from app.rules.plan import Plan

PREFIX = "zones_of:"
_WHO = {"target player's": ("target", "player"), "target opponent's": ("target", "opponent"), "that player's": ("that_player", None), "defending player's": ("defending_player", None)}
_P = r"(?P<p>target player's|target opponent's|that player's|defending player's)"
_SEL = r"(?P<sel>cards|[a-z]+(?:, [a-z]+)* cards)"
_ZONES = {"hand": ["hand"], "graveyard": ["graveyard"], "hand and graveyard": ["hand", "graveyard"]}


def key(zones: list[str], ref: str, sel: str = "") -> str:
    return f"{PREFIX}{','.join(zones)}:{ref}|{sel}"


def cards(plan: Plan, ctx: Context, who: str) -> list[str]:
    """The cards of the named zones of the referenced players that the selector (if any) matches, in zone order."""
    from app.rules import effects

    zones, _, rest = who[len(PREFIX):].partition(":")
    ref, _, sel_key = rest.partition("|")
    sel = selectors.from_key(sel_key) if sel_key else None
    out: list[str] = []
    for pid in effects._players(plan, ctx, ref):
        for zone in zones.split(","):
            for cid in plan.state.zones.get(f"{pid}:{zone}", []):
                card = plan.state.cards[cid]
                if sel is None or selectors.matches(plan, sel, card, plan.ch(card), ctx["controller"], ctx.get("source_card")):
                    out.append(cid)
    return out


def _selector(text: str) -> str:
    """"cards" / "land cards" / "noncreature, nonland cards" -> a card selector key without a zone (read per zone by ``cards``), or "" for any card."""
    from app.rules.scripts import _NoMatch  # (scripts imports this module)

    if text == "cards":
        return ""
    sel = selectors.parse(re.sub(r"cards$", "card from a graveyard", text))  # (any one zone parses; the zones are read per zone by ``cards``)
    if sel is None or not sel.card or sel.player is not None or sel.controller is not None or sel.zone_owner is not None or sel.owner is not None:
        raise _NoMatch
    return replace(sel, zones=()).key()


def _target(kind: str | None) -> str | None:
    return kind  # (the legacy target keys "player" / "opponent")


# "Exile all cards from target player's hand and graveyard." / "… noncreature, nonland cards from that player's hand and graveyard."; a graveyard alone with a one-word
# kind is graveyard_exile's (wave 15C)
_EXILE = re.compile(rf"^exile all {_SEL} from {_P} (?P<z>hand|graveyard|hand and graveyard)$")


def _exile(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch

    ref, kind = _WHO[m["p"]]
    if m["z"] == "graveyard" and m["p"] != "that player's" and re.fullmatch(r"(?:[a-z]+ )?cards", m["sel"]):
        raise _NoMatch  # (graveyard_exile's)
    return [{"do": "exile", "who": key(_ZONES[m["z"]], ref, _selector(m["sel"]))}], _target(kind)


# "Target player exiles all land cards from their graveyard." (Mudhole): the same set, named by the subject
_EXILES = re.compile(rf"^(?P<p>target player|target opponent|that player) exiles all {_SEL} from their (?P<z>hand|graveyard|hand and graveyard)$")


def _exiles(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    if m["p"] == "that player":  # (Strategic Betrayal: the player the sentence before named; scripts.resolve_it binds the reference)
        return [{"do": "exile", "who": key(_ZONES[m["z"]], "that_player", _selector(m["sel"]))}], None
    return [{"do": "exile", "who": key(_ZONES[m["z"]], "target", _selector(m["sel"]))}], _target(m["p"].split()[1])


# "Exile all cards from target player's library." (Jace, the Mind Sculptor -12) / "Exile all but the bottom card of target player's library." (Nicol Bolas -12): exile_top
# with everything (or all but the bottom ``keep_bottom``) of that library; the library's order is theirs to keep (401.2), the exiled cards are face up (406.3)
_LIBRARY = re.compile(r"^exile all (?:cards|but the bottom (?P<keep>card|two cards|three cards)) (?:from|of) (?P<p>target player's|target opponent's|that player's) library$")


def _library(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    ref, kind = _WHO[m["p"]]
    keep = {None: 0, "card": 1, "two cards": 2, "three cards": 3}[m["keep"]]
    return [{"do": "exile_top", "keep_bottom": keep, "player": ref}], _target(kind)


# "Shuffle all creature cards from target player's graveyard into that player's library." (Repopulate): effects.shuffle_library with a selector (wave 16C) for the
# graveyard of the player the target is
_SHUFFLE_GY = re.compile(rf"^shuffle all {_SEL} from target player's graveyard into that player's library$")


def _shuffle_gy(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    sel = _selector(m["sel"])
    zoned = replace(selectors.from_key(sel), zones=("graveyard",)).key() if sel else selectors.Selector(card=True, zones=("graveyard",)).key()
    return [{"do": "shuffle_library", "who": "target", "zones": ["graveyard"], "sel": zoned}], _target("player")


# "You may have that player shuffle." / "You may then have that player shuffle that library." (Portent, Visions): the controller decides, the player named shuffles
_SHUFFLE = re.compile(r"^you may (?:then )?have that player shuffle(?: that library| their library)?$")


def _shuffle(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "shuffle_library", "who": "that_player", "zones": [], "optional": True}], None


# "..., then the player shuffles." (Rootwater Thief): the player whose library was searched
_THE_PLAYER = re.compile(r"^(?:then )?the player shuffles(?: their library)?$")


def _the_player(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "shuffle_library", "who": "that_player", "zones": []}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_EXILE, _exile), (_EXILES, _exiles), (_LIBRARY, _library), (_SHUFFLE_GY, _shuffle_gy), (_SHUFFLE, _shuffle),
                                                (_THE_PLAYER, _the_player)]
