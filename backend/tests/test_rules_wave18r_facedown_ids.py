"""Review (face-down ids): 406.3 / 708.5 — a card that opponents saw (battlefield, graveyard, a reveal) and later becomes face down
where they can see it (the battlefield, exile or the stack) is a new object with a new instance id, so the face-down object can't be
matched to the card they saw. Real Oracle text; every opponent's and the spectator's view is built before and after."""

from __future__ import annotations

import json

import pytest

from app.game.visibility import SPECTATOR
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave9b_exile_permission import answer, build, put, roundtrip
from tests.test_rules_wave18a_down import EXTRA, mana, unseen_by
from tests.test_rules_wave18a_hidden import EXTRA as HIDDEN

VIEWERS = ("p2", SPECTATOR)


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *HIDDEN], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def saw_publicly(s, c):
    """Make an opponent see the card (it lies in a public zone), then hide it in a hand: returns the id they learned."""
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    old = c.id
    assert all(old in json.dumps(s.view(v)) for v in VIEWERS)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    assert all(old not in json.dumps(s.view(v)["zones"]["p1:hand"]) for v in VIEWERS)  # (a hand is anonymous)
    return old


def unlinked(s, c, old):
    """The card is a different object for the opponents: its id is not the one they saw, and the old id is nowhere in what they get."""
    assert c.id != old and old not in s.state.cards
    for v in VIEWERS:
        assert old not in json.dumps(s.view(v)), v
        assert c.id in json.dumps(s.view(v)["cards"]) and unseen_by(s, c, v)


def test_a_card_moved_face_down_by_hand_is_a_new_object(cards):
    s = build(cards, p1=("Ambush Viper",))
    viper = put(s, "Ambush Viper", "battlefield")
    old = saw_publicly(s, viper)
    act(s, "p1", type="move", card_ids=[viper.id], to={"zone": "battlefield"}, face_down=True, face_down_kind="manifest")
    unlinked(s, viper, old)
    assert not unseen_by(s, viper, "p1")  # its controller still looks at it
    roundtrip(s)


def test_put_top_face_down_manifests_a_new_object(cards):
    s = build(cards, p1=("Grizzly Bears",))
    bears = put(s, "Grizzly Bears", "graveyard")
    old = bears.id
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "library"}, position="top")
    act(s, "p1", type="put_top_face_down", count=1, kind="manifest")
    assert bears.zone == "p1:battlefield" and bears.face_down
    unlinked(s, bears, old)
    roundtrip(s)


def test_ignorant_bliss_exiles_new_objects_and_the_delayed_return_still_finds_them(cards):
    s = build(cards, p1=("Ignorant Bliss", "Grizzly Bears", "Giant Growth"))
    bears = put(s, "Grizzly Bears", "hand")
    growth = put(s, "Giant Growth", "hand")
    old = {c.name: saw_publicly(s, c) for c in (bears, growth)}
    bliss = put(s, "Ignorant Bliss", "hand")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bliss.id)
    answer(s)
    for c in (bears, growth):
        assert c.zone == "p1:exile" and c.face_down
        unlinked(s, c, old[c.name])
    until(s, lambda s: bears.zone == "p1:hand")  # the delayed trigger (it names the exiled cards) follows the new ids
    assert growth.zone == "p1:hand" and not bears.face_down
    roundtrip(s)


def test_scroll_of_fate_manifests_a_new_object_from_the_hand(cards):
    s = build(cards, p1=("Scroll of Fate", "Giant Growth"))
    scroll = put(s, "Scroll of Fate", "battlefield")
    growth = put(s, "Giant Growth", "hand")
    old = saw_publicly(s, growth)
    act(s, "p1", type="activate_ability", card_id=scroll.id, ability=0)
    answer(s, pick=growth.id)
    assert growth.zone == "p1:battlefield" and growth.face_down
    unlinked(s, growth, old)
    roundtrip(s)


def test_ashcloud_phoenix_returns_face_down_as_a_new_object(cards):
    s = build(cards, p1=("Ashcloud Phoenix", "Lightning Bolt"))
    phoenix = put(s, "Ashcloud Phoenix", "battlefield")
    old = phoenix.id  # (everybody saw it on the battlefield)
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[old])
    answer(s)
    assert phoenix.zone == "p1:battlefield" and phoenix.face_down
    unlinked(s, phoenix, old)
    mana(s, R=2, C=4)
    act(s, "p1", type="turn_face_up", card_id=phoenix.id)  # (its own references, as the object it is now, still work)
    answer(s)
    assert not phoenix.face_down
    roundtrip(s)


def test_a_spell_cast_face_down_is_a_new_object(cards):
    s = build(cards, p1=("Ashcloud Phoenix",))
    phoenix = put(s, "Ashcloud Phoenix", "battlefield")
    old = saw_publicly(s, phoenix)
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=phoenix.id, face_down=True)
    answer(s)
    assert phoenix.zone == "p1:battlefield" and phoenix.face_down
    unlinked(s, phoenix, old)
    roundtrip(s)


def test_a_face_down_permanent_that_changes_controller_keeps_its_id(cards):
    """708: a control change is no zone change — the same object; only a card that became face down gets a new id."""
    s = build(cards, p1=("Ambush Viper",))
    viper = put(s, "Ambush Viper", "battlefield")
    act(s, "p1", type="face_down", card_ids=[viper.id], face_down=True, kind="manifest")  # turned face down in place: same object
    assert viper.face_down
    before = viper.id
    act(s, "p1", type="move", card_ids=[viper.id], to={"player": "p2", "zone": "battlefield"})
    assert viper.id == before and viper.zone == "p2:battlefield"
    roundtrip(s)
