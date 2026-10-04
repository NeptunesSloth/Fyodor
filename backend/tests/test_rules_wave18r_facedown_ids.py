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


# -- review (face-down ids, head review) --
def test_typed_text_and_the_old_objects_relations_are_not_rewritten(cards):
    """A player can't plant the old id in a note or a counter's name and read the new one back; a copy keeps the old object as its
    source (400.7: the face-down card is a new object); the renamed card is last in the table's card order (no position to match)."""
    s = build(cards, p1=("Ambush Viper",), p2=("Grizzly Bears",))
    viper = put(s, "Ambush Viper", "battlefield")
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    old = viper.id
    act(s, "p2", type="set_copy_source", card_id=bears.id, source_id=old)
    act(s, "p2", type="note", card_id=bears.id, text=f"was {old}")
    act(s, "p2", type="counter", card_ids=[bears.id], kind=old)
    act(s, "p1", type="move", card_ids=[old], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[old], to={"zone": "battlefield"}, face_down=True, face_down_kind="manifest", keep_ids=True)
    assert viper.id != old  # (keep_ids is the rules engine's, never a client's)
    assert bears.copy_of.source_id == old and bears.note == f"was {old}" and old in bears.counters
    assert viper.id not in json.dumps(s.view("p2")["cards"][bears.id])
    assert list(s.state.cards)[-1] == viper.id
    roundtrip(s)


def test_a_manual_move_leaves_no_old_id_in_the_rules_state(cards):
    """A move made by hand renumbers in the step; the rules bookkeeping of that step (last known information) follows the new id."""
    s = build(cards, p1=("Ambush Viper",))
    viper = put(s, "Ambush Viper", "battlefield")
    old = viper.id
    act(s, "p1", type="move", card_ids=[old], to={"zone": "exile"}, face_down=True)
    assert viper.id != old and old not in json.dumps(s.state.rules.model_dump(mode="json"))
    roundtrip(s)


def test_a_face_down_spell_that_resolves_and_then_leaves_in_one_intent_is_renumbered(cards):
    """708.9: it is revealed as it leaves the battlefield, so face down in exile it is a card they saw, whatever it was at the start."""
    import random

    from app.rules.plan import Plan

    s = build(cards, p1=("Ambush Viper",))
    viper = put(s, "Ambush Viper", "hand")
    act(s, "p1", type="move", card_ids=[viper.id], to={"zone": "stack"}, face_down=True, face_down_kind="morph")
    plan = Plan(s.state, "p1", s.cards, random.Random(0))
    for zone in ("battlefield", "exile"):
        plan.do({"type": "move", "card_ids": [viper.id], "to": {"player": "p1", "zone": zone}, "face_down": True})
    plan.do({"type": "rules_sync", "rules": plan.rules.model_dump(mode="json")})
    assert [st["card_ids"] for st in plan.steps if st["type"] == "renumber"] == [[viper.id]]


def test_an_exported_rules_scenario_replays_a_renumbering(cards):
    """The new ids come from the game's salt: a rules scenario (developer export) carries it, or its replay can't follow them."""
    from app.rules import scenario

    s = build(cards, p1=("Ashcloud Phoenix", "Lightning Bolt"))
    phoenix = put(s, "Ashcloud Phoenix", "battlefield")
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[phoenix.id])
    answer(s)
    assert phoenix.face_down
    mana(s, R=2, C=4)
    act(s, "p1", type="turn_face_up", card_id=phoenix.id)  # (an intent naming the new id)
    answer(s)
    data = next(d for n in range(1, 20) if (d := json.loads(json.dumps(scenario.export(s, s.cards, intents=n))))["actions"][0]["type"]
                == "cast_spell")  # (from the Bolt on)
    assert any(st["type"] == "renumber" for a in data["actions"] for st in a.get("r") or [])
    assert scenario.replay(data, s.cards) == []


def test_a_save_from_before_renumbering_keeps_its_history(cards):
    """v6 saves recorded face-down moves that kept their ids: replaying them (load, undo) must not renumber."""
    from app.storage.save_format import decode, encode
    from app.storage.saves import load_payload

    s = build(cards, p1=("Ambush Viper",))
    viper = put(s, "Ambush Viper", "battlefield")
    s.perform("p1", {"type": "move", "card_ids": [viper.id], "to": {"zone": "exile"}, "face_down": True, "keep_ids": True},
              trusted=True)  # (what the v6 engine did)
    history = s.history.to_dict()
    for action in history["actions"]:
        action.pop("keep_ids", None)
    payload = {"format": "fyodor-save", "version": 6, "saved_at": 0, "state": s.state.model_dump(mode="json"), "history": history}
    state, restored = load_payload(decode(encode(payload)))
    assert restored is not None and restored.rebuild().model_dump(mode="json") == state.model_dump(mode="json")
