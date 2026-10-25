"""-- merged permanents (wave 18D) -- merged (730, mutate 702.140) and melded (701.42, 712.4, 712.21) permanents, as table state.

One permanent is one ``CardInstance`` (the *shell*, whose id is the object's identity: attachments, arrows and the rules object
all point at it) representing several cards: ``CardInstance.merged`` lists them topmost first and the instance's own card fields
(``card_id``, ``name``, ``token`` …) are always the topmost one's (730.2a), so everything that reads a permanent's printed
characteristics sees the right card. A melded permanent shows its combined back face instead (712.8g) and its two cards are the
parts. When the permanent leaves the battlefield the pile breaks up (730.3, 712.21): the shell takes one part and a new instance
is made for each other card (a token component ceases to exist, 111.7). Nothing here knows rules; the rules decide (app/rules/merged.py).
"""

from __future__ import annotations

from app.game import ops
from app.game.state import CardInstance, GameState, MergedPart, StickerPlacement101


def part_of(c: CardInstance, part_id: str) -> MergedPart:
    """The card or token ``c`` is, as one component (it gets ``part_id``: the shell keeps ``c.id``)."""
    return MergedPart(id=part_id, card_id=c.card_id, name=c.name, owner=c.owner, is_token=c.is_token,
                      token=c.token.model_copy() if c.token else None, copy_of=c.copy_of.model_copy() if c.copy_of else None,
                      commander_key=c.commander_key, categories=list(c.categories), origin=c.origin, test_object=c.test_object)


def show(c: CardInstance, part: MergedPart) -> None:
    """The shell is this component now (its topmost, 730.2a): its card fields follow it."""
    c.card_id, c.name, c.is_token, c.token, c.copy_of = part.card_id, part.name, part.is_token, part.token, part.copy_of
    c.face = 0
    c.face_down = False
    c.face_down_kind = None
    c.flipped = False
    c.commander_key = next((p.commander_key for p in c.merged if p.commander_key), None)  # 903.3c


def merge(state: GameState, host: CardInstance, spell: CardInstance, over: bool, host_part_id: str) -> None:
    """730.2: ``spell`` goes on top of (or under) ``host`` and becomes part of it, and ceases to be an object of its own
    (it isn't an object entering the battlefield, 730.2b). Counters, damage, status and attachments stay with the permanent (730.2c)."""
    top = [part_of(spell, spell.id)]
    below = host.merged or [part_of(host, host_part_id)]
    host.stickers101 = sorted([*host.stickers101, *spell.stickers101], key=lambda p: (p.object_seq, p.timestamp))
    host.merged = top + below if over else below + top
    ops.remove_from_zone(state, spell)
    del state.cards[spell.id]
    show(host, host.merged[0])


def meld(state: GameState, first: CardInstance, second: CardInstance, result_id: str, result_name: str, first_part_id: str) -> None:
    """701.42a: two cards of a meld pair, put onto the battlefield with their back faces up and combined: one permanent represented
    by both (``first`` is its shell, wearing ``result``'s card: the combined back face)."""
    first.stickers101 = sorted([*first.stickers101, *second.stickers101], key=lambda p: (p.object_seq, p.timestamp))
    first.merged = [part_of(first, first_part_id), part_of(second, second.id)]
    first.melded = True
    ops.remove_from_zone(state, second)
    del state.cards[second.id]
    first.card_id, first.name, first.is_token, first.token, first.copy_of = result_id, result_name, False, None, None
    first.face = 0
    first.commander_key = next((p.commander_key for p in first.merged if p.commander_key), None)


def break_up(state: GameState, c: CardInstance, dest: str) -> tuple[list[MergedPart], MergedPart]:
    """730.3 / 712.21: the permanent ``c`` leaves the battlefield for ``dest``. ``c`` becomes one of its cards (the commander for a
    move to the hand, library or command zone, so the owner's choice there, 903.9b-c, is about that card; else the topmost) and the
    pile is returned with that card, for :func:`place`. ``c`` stops being merged."""
    parts, c.merged, c.melded = c.merged, [], False
    pick = next((p for p in parts if p.commander_key), None) if ops.zone_name(dest) in ("hand", "library", "command") else None
    pick = pick or parts[0]
    c.card_id, c.name, c.is_token, c.token, c.copy_of = pick.card_id, pick.name, pick.is_token, pick.token, pick.copy_of
    c.commander_key, c.categories, c.origin, c.test_object = pick.commander_key, list(pick.categories), pick.origin, pick.test_object
    c.face = 0
    c.face_down = False
    return parts, pick


def place(state: GameState, parts: list[MergedPart], pick: MergedPart, dest: str, rest: str | None, index: int | None,
          position: str | None, *, stickers101: list[StickerPlacement101] | None = None, sticker_recipient101: str | None = None) -> None:
    """The other cards of a broken-up pile go where the permanent went (730.3: each component is put into the zone; a token component
    ceases to exist). Only a commander goes to the command zone (903.9c); the others go to ``rest`` (where the pile was headed:
    hand or library) or the graveyard. 730.3a: the owner may arrange them in any order, here the pile's (topmost on top)."""
    where = ops.zone_name(dest)
    for part in reversed(parts):
        if part is pick or part.is_token:
            continue
        zone = "command" if where == "command" and part.commander_key else (rest or "graveyard") if where == "command" else where
        inst = CardInstance(id=part.id, card_id=part.card_id, name=part.name, owner=part.owner, controller=part.owner, zone="",
                            commander_key=part.commander_key, categories=list(part.categories), origin=part.origin,
                            test_object=part.test_object, copy_of=part.copy_of)
        if part.id == sticker_recipient101 and zone in ('graveyard', 'exile', 'command', 'battlefield', 'stack'):
            inst.stickers101 = list(stickers101 or [])
        state.cards[inst.id] = inst
        ops.insert(state, inst, f"{part.owner}:{zone}", index=index, position=position)
