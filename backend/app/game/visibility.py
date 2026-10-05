"""Who can see which card *right now*. The single source of truth for hidden information.

Visibility is computed from current facts only:

* PUBLIC      face-up cards in public zones (battlefield, graveyard, exile, command, stack)
* OWNER       cards in the owner's hand, sideboard and foretell (face-down exile) zones
* CONTROLLER  face-down cards on the battlefield/stack/exile
* REVEALED    an active reveal to everyone or to selected players (``revealed_to``)
* VIEWING     an open search / look-at-top-N context (``state.views``)
* HIDDEN      everything else, e.g. a library

There is no memory of past sightings: a card that was public and moves into a hand is
anonymous to opponents from then on. Historical log lines are separate (``LogPart``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.game.control import controlled_by
from app.game.state import (
    ALL,
    OWNER_VISIBLE_ZONES,
    PUBLIC_ZONES,
    CardInstance,
    GameState,
    split_zone,
)

OMNISCIENT = "__omniscient__"  # local "open table" view (hot-seat goldfishing only)
SPECTATOR = "__spectator__"


def can_see(state: GameState, card: CardInstance, viewer: str) -> bool:
    """True when ``viewer`` may learn this card's identity right now. -- controlling another player (wave 18H) -- 723.4:
    also what a player they control may see (cards outside the game, a sideboard, are only that player's)."""
    return _sees(state, card, viewer) or (
        split_zone(card.zone)[1] != "sideboard" and any(_sees(state, card, p) for p in controlled_by(state, viewer)))


def _sees(state: GameState, card: CardInstance, viewer: str) -> bool:
    if viewer == OMNISCIENT or card.ability is not None:
        return True
    if ALL in card.revealed_to or viewer in card.revealed_to:
        return True
    _, zone = split_zone(card.zone)
    if shown_at_end(state, card, zone):
        return True
    if zone in PUBLIC_ZONES:
        return not card.face_down or (viewer == card.controller and not card.unseen) or looks_at_face_down(state, card, viewer)
    if zone in OWNER_VISIBLE_ZONES and viewer == card.owner:
        return True
    for view in state.views:
        if view.viewer == viewer and view.zone == card.zone and (view.kind == "search" or card.id in view.card_ids):
            return True
    return (zone == "library" and top_revealed(state, card, viewer)) or (zone == "hand" and hand_revealed(state, card))


def shown_at_end(state: GameState, card: CardInstance, zone: str) -> bool:
    """-- review (sys 18A) -- 708.9 / 702.143f: when a player leaves the game, the face-down permanents and spells and the foretold
    cards they own are revealed to all players, and at the end of the game everyone's are (with automation on: the engine knows
    who left and who won)."""
    r = state.rules
    if r is None or not (card.face_down and zone in ("battlefield", "stack") or zone == "foretell"):
        return False
    return r.winner is not None or card.owner in r.lost or card.owner in r.conceded


def hand_revealed(state: GameState, card: CardInstance) -> bool:
    """-- revealed zones (wave 25A) -- "Your opponents play with their hands revealed." / "Players play with their hands revealed." (701.20a: shown to
    every player, spectators too): while a source that has it is on a battlefield, face up and automated, the hands it names are open. The source's
    controller is "you" / "your opponents" (``RulesState.top_reveals``, refreshed by the engine)."""
    rules = state.rules
    if rules is None or not rules.top_reveals:
        return False
    owner = card.owner
    for reveal in rules.top_reveals:
        source = state.cards.get(reveal.source)
        if reveal.zone != "hand" or source is None or source.face_down or not source.zone.endswith(":battlefield") \
                or rules.card_mode(source.id) == "manual":
            continue
        controller = source.controller
        if reveal.whose == "players" or (reveal.whose == "you" and owner == controller) or (reveal.whose == "opponents" and owner != controller):
            return True
    return False


def top_revealed(state: GameState, card: CardInstance, viewer: str) -> bool:
    """"Play with the top card of your library revealed" / "You may look at the top card of your
    library any time" (CR 401.5). The rules engine lists which cards of the game have such an
    ability (``RulesState.top_reveals``: it needs the card database, which the view has not);
    everything else is read from the table itself, here: the source must be on a battlefield
    now, face up and automated, and the library it reveals is its *current* controller's — so a
    source put onto the battlefield, taken or removed by hand is right at once, with no engine
    action in between. Only the top card, as the library is now."""
    rules = state.rules
    if rules is None or not rules.top_reveals:
        return False
    library = state.zones.get(card.zone) or []
    if not library or library[0] != card.id:
        return False
    for reveal in rules.top_reveals:
        source = state.cards.get(reveal.source)
        if source is None or source.face_down or not source.zone.endswith(":battlefield") \
                or rules.card_mode(source.id) == "manual":
            continue
        controller = source.controller
        if reveal.zone != "library":
            continue
        if reveal.to == "none" or (card.zone != f"{controller}:library" and reveal.whose != "players") or (reveal.to == "owner" and viewer != controller):
            continue  # (-- revealed zones (wave 25A) -- "Players play with the top card of their libraries revealed": whose "players": any library)
        return True
    return False


def looks_at_face_down(state: GameState, card: CardInstance, viewer: str) -> bool:
    """-- hidden exile (wave 18A) -- "You may look at face-down creatures you don't control any time." (Found Footage, Keeper of
    the Lens): the source's controller sees the face-down creatures on the battlefield that others control (a static ability
    that works while its source is on the battlefield face up and automated, as ``top_revealed``)."""
    rules = state.rules
    if rules is None or not card.zone.endswith(":battlefield") or card.controller == viewer \
            or (card.face_down_as is not None and "creature" not in card.face_down_as):  # (review sys 18A: a face-down Forest land isn't a creature)
        return False
    for reveal in rules.top_reveals:
        source = state.cards.get(reveal.source)
        if reveal.face_down and reveal.player == viewer and source is not None and not source.face_down \
                and source.zone.endswith(":battlefield") and source.controller == viewer and rules.card_mode(source.id) != "manual":
            return True
    return False


def publicly_visible(state: GameState, card: CardInstance) -> bool:
    """Visible to everyone, including spectators."""
    if card.ability is not None or ALL in card.revealed_to:
        return True
    _, zone = split_zone(card.zone)
    return zone in PUBLIC_ZONES and not card.face_down


def seers(state: GameState, card: CardInstance) -> set[str]:
    """Players who can currently see ``card`` (``{ALL}`` when it is public). Used for log lines."""
    if publicly_visible(state, card):
        return {ALL}
    return {p for p in state.seat_order if can_see(state, card, p)}


# -- keyword actions & face-down (wave 3F) ------------------------------------------------------
def mask_face_down(state: GameState, text: str, viewer: str | None = None, refs: Iterable[str | None] = ()) -> str:
    """708.5: text shown to players (a rules log line, a decision's prompt or option label) never
    names a face-down spell, permanent or exiled card to a player who may not look at it. The
    engine's messages use cached card names; each such name is replaced here (``viewer`` None: a
    line everyone reads). ``refs``: the card ids the text is about. A name stays when the text is
    about as many public cards of that name as it names, and not about the face-down card itself
    (a face-down Mountain doesn't hide the public Mountain a line is about); otherwise it is masked."""
    ref_ids = {r for r in refs if r}
    for card in state.cards.values():
        if not card.face_down or not card.name or card.name not in text:
            continue
        if viewer is not None and can_see(state, card, viewer):
            continue
        pattern = rf"(?<![\w']){re.escape(card.name)}(?![\w'])"
        if card.id not in ref_ids:
            public = sum(1 for r in ref_ids if (o := state.cards.get(r)) is not None and o.name == card.name
                         and not o.face_down)
            if public and len(re.findall(pattern, text)) <= public:
                continue
        text = re.sub(pattern, "a face-down card", text)
    return text
