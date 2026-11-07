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
        return (not card.face_down or (viewer == card.controller and not card.unseen) or looks_at_face_down(state, card, viewer)
                or hideaway_looks(state, card, viewer))
    if zone in OWNER_VISIBLE_ZONES and viewer == card.owner:
        return True
    for view in state.views:
        if view.viewer == viewer and view.zone == card.zone and (view.kind == "search" or card.id in view.card_ids):
            return True
    # 701.23a / 401.2: a rules decision that offers hidden cards (a search's legal finds) shows them to the one choosing, while
    # they choose; the options already name them to that player only, and the search shuffles them away again afterwards
    d = state.rules.decision if state.rules is not None else None
    if d is not None and d.player == viewer and any(o.card_id == card.id for o in d.options):
        return True
    return (zone == "library" and top_revealed(state, card, viewer)) or (zone == "hand" and hand_revealed(state, card))


def shown_at_end(state: GameState, card: CardInstance, zone: str) -> bool:
    """-- review (sys 18A) -- 708.9 / 702.143f: when a player leaves the game, the face-down permanents and spells and the foretold
    cards they own are revealed to all players, and at the end of the game everyone's are (with automation on: the engine knows
    who left and who won)."""
    r = state.rules
    if r is None or not (card.face_down and zone in ("battlefield", "stack") or zone == "foretell"):
        return False
    return r.winner is not None or r.draw_reason is not None or card.owner in r.lost or card.owner in r.conceded


def hand_revealed(state: GameState, card: CardInstance) -> bool:
    """-- revealed zones (wave 25A) -- "Your opponents play with their hands revealed." / "Players play with their hands revealed." (701.20a: shown to
    every player, spectators too): while a source that has it is on a battlefield, face up and automated, the hands it names are open. The source's
    controller is "you" / "your opponents" (``RulesState.top_reveals``, refreshed by the engine)."""
    rules = state.rules
    if rules is None:
        return False
    if rules.hand_reveal_turn110m.get(card.owner) == state.turn.number:  # (wave 110M) Sen Triplets: "this turn, that player plays with their hand revealed"
        return True
    for grant in rules.source_hand_reveals79:
        source = state.cards.get(grant.source_card)
        if (grant.player == card.owner and source is not None and source.zone.endswith(':battlefield')
                and rules.object_id(source.id) == grant.source_object):
            return True
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
    if rules is None:
        return False
    library = state.zones.get(card.zone) or []
    if not library or library[0] != card.id:
        return False
    # A resolved end-of-turn authority is independent of its original source (611.2a).
    # It reveals only the current top card to its beneficiary, never to spectators.
    if card.zone in (f"{viewer}:library", *(f"{p.library_of}:library" for p in rules.permissions if p.library_of)) and any(
        p.look_top and p.zone == 'library_top' and p.player == viewer and (p.library_of or viewer) == card.zone.split(":")[0]
        and p.until == 'end_of_turn' and p.turn == state.turn.number
        for p in rules.permissions
    ):
        return True
    if any(p.top110j and p.card == card.id for p in rules.permissions):  # -- wave 110J -- Temporal Aperture: "play with the top card of your library revealed" (401.5)
        return True
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
    if any(g["player"] == viewer and g["turn"] == state.turn.number for g in rules.face_down_looks110l):  # -- (wave 110L) -- until end of turn (611.2a)
        return True
    for reveal in rules.top_reveals:
        source = state.cards.get(reveal.source)
        if reveal.face_down and reveal.player == viewer and source is not None and not source.face_down \
                and source.zone.endswith(":battlefield") and source.controller == viewer and rules.card_mode(source.id) != "manual":
            return True
    return False


def hideaway_looks(state: GameState, card: CardInstance, viewer: str) -> bool:
    """-- hideaway (wave 29D) -- 702.75a, 406.3: "The player who controls the permanent that exiled this card may look at this card in the
    exile zone", and a player who was allowed to look may go on looking until it leaves exile (``RulesState.hideaway``, kept by the engine
    from the table; the permanent's controller right now counts at once, whatever the engine last recorded)."""
    r = state.rules
    if r is None or not r.hideaway or not card.face_down or not card.zone.endswith(":exile"):
        return False
    entry = r.hideaway.get(r.object_id(card.id))
    if entry is None:
        return False
    source = state.cards.get(entry.source.rsplit(".", 1)[0])
    return viewer in entry.lookers or (source is not None and source.zone.endswith(":battlefield") and source.controller == viewer
                                       and r.object_id(source.id) == entry.source)


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
