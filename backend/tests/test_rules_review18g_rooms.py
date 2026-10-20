"""Review of wave 18G (Rooms, CR 709.5): probes with the real Oracle text of the cards involved — copies, a Room leaving and
returning, last known information, a face-down Room, Fractured Realm doubling an unlock trigger. Each scenario is replayed and
round-tripped through a save."""

from __future__ import annotations

import json
import sqlite3

import pytest

from app.config import load_settings
from app.game.errors import ActionError
from app.rules import scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, on_field, settle, to_hand
from tests.test_rules_effects import mana
from tests.test_rules_wave15d_activated import roundtrip

REAL_DB = load_settings().cards_db_path
NAMES = ["Grand Entryway // Elegant Rotunda", "Mirror Room // Fractured Realm", "Funeral Room // Awakening Hall",
         "Copy Enchantment", "Akroma's Vengeance", "Grizzly Bears", "Restricted Office // Lecture Hall",
         "Roaring Furnace // Steaming Sauna"]
pytestmark = pytest.mark.skipif(not REAL_DB.is_file(), reason="the real card database is needed")


def real_cards(names):
    db = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    out = []
    for i, name in enumerate(names):
        r = db.execute("SELECT p.* FROM printings p JOIN oracle_defaults d ON d.printing_id = p.id WHERE p.name = ?", (name,)).fetchone()
        extra = {k: r[k] for k in ("power", "toughness") if r[k] is not None}
        faces = json.loads(r["card_faces"] or "null")
        if faces:
            extra["card_faces"] = [{"object": "card_face", **f} for f in faces]
        out.append(card(name, set_code="tst", number=f"R18G-{i}", layout=r["layout"], mana_cost=r["mana_cost"] or "", cmc=float(r["cmc"] or 0),
                        type_line=r["type_line"], oracle_text=r["oracle_text"] or "", colors=json.loads(r["colors"] or "[]"),
                        color_identity=json.loads(r["color_identity"] or "[]"), keywords=json.loads(r["keywords"] or "[]"), **extra))
    db.close()
    return out


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *real_cards(NAMES)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


GRAND, MIRROR, FUNERAL = NAMES[:3]


def doors(s, c):
    return s.state.rules.unlocked.get(s.state.rules.object_id(c.id), [])


def ch_of(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def glimmers(s):
    return [c for c in s.state.cards.values() if c.name == "Glimmer" and c.zone.endswith(":battlefield")]


def test_copy_enchantment_copying_a_room_has_no_door_unlocked_and_nothing_triggers(cards):
    """709.5c/d: the designations aren't copiable, and the copy wasn't cast as a half: both its doors are locked."""
    s = build(cards, GRAND, "Copy Enchantment")
    room = to_hand(s, GRAND)
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=room.id, face=0)
    settle(s)
    assert len(glimmers(s)) == 1
    copy = to_hand(s, "Copy Enchantment")
    mana(s, "p1", U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=copy.id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        ids = [o.id for o in d.options if room.id in (o.id, o.card_id)] or [o.id for o in d.options if o.id == "yes"] or [d.options[0].id]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    ch = ch_of(s, copy)
    assert "Room" in ch.subtypes, "Copy Enchantment should have copied the Room"
    assert doors(s, copy) == [] and ch.name == "" and ch.mana_value == 0 and not scripts.definitions(ch)
    assert len(glimmers(s)) == 1  # no "When you unlock this door" from the copy
    stats = s.view("p2")["rules"]["stats"][copy.id]  # (the table's unlock menu: the copied halves, public)
    assert stats["doors"] == [] and [h["name"] for h in stats["halves"]] == ["Grand Entryway", "Elegant Rotunda"]
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="unlock_door", card_id=copy.id, door=1)  # its own doors can be unlocked (709.5e)
    settle(s)
    assert doors(s, copy) == [1] and len(glimmers(s)) == 2
    roundtrip(s)


def test_a_room_that_leaves_and_returns_has_its_doors_locked_again(cards):
    """400.7: a new object; 709.5d: it wasn't cast this time."""
    s = build(cards, GRAND)
    room = to_hand(s, GRAND)
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=room.id, face=0)
    settle(s)
    assert doors(s, room) == [1]
    act(s, "p1", type="move", card_ids=[room.id], to={"zone": "hand"})
    assert ch_of(s, room).name == "Grand Entryway // Elegant Rotunda" and ch_of(s, room).mana_value == 5  # 709.4: both halves
    act(s, "p1", type="move", card_ids=[room.id], to={"player": "p1", "zone": "battlefield"})
    settle(s)
    assert doors(s, room) == [] and ch_of(s, room).name == "" and len(glimmers(s)) == 1
    roundtrip(s)


def test_fractured_realm_doubles_an_unlock_trigger(cards):
    """603.2d: "When you unlock this door" of a permanent you control triggers an additional time."""
    s = build(cards, MIRROR, GRAND)
    realm = to_hand(s, MIRROR)
    mana(s, "p1", U=2, C=5)
    act(s, "p1", type="cast_spell", card_id=realm.id, face=1)
    settle(s)
    assert doors(s, realm) == [2]
    room = on_field(s, GRAND)
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="unlock_door", card_id=room.id, door=1)
    settle(s)
    assert len(glimmers(s)) == 2
    roundtrip(s)


def test_a_locked_doors_leaves_trigger_does_not_look_back_into_existence(cards):
    """709.5 + 603.10a: Funeral Room (locked) isn't there when the Room and a creature are destroyed together; Awakening Hall
    (cast) is the only unlocked door, so no one loses or gains life."""
    s = build(cards, FUNERAL, "Grizzly Bears", "Akroma's Vengeance")
    room = to_hand(s, FUNERAL)
    mana(s, "p1", B=2, C=6)
    act(s, "p1", type="cast_spell", card_id=room.id, face=1)
    settle(s)
    assert doors(s, room) == [2]
    on_field(s, "Grizzly Bears")
    wrath = to_hand(s, "Akroma's Vengeance")
    mana(s, "p1", W=2, C=4)
    act(s, "p1", type="cast_spell", card_id=wrath.id)
    settle(s)
    assert s.state.players["p1"].life == 40 and s.state.players["p2"].life == 40
    roundtrip(s)


def test_a_face_down_room_has_no_door_to_unlock(cards):
    """708.2: a face-down permanent has none of the Room's characteristics; 709.5e needs a permanent with a locked half."""
    s = build(cards, GRAND)
    room = on_field(s, GRAND)
    act(s, "p1", type="face_down", card_ids=[room.id], face_down=True)
    mana(s, "p1", W=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="unlock_door", card_id=room.id, door=1)
    assert doors(s, room) == [] and not glimmers(s)


def test_casting_a_room_without_a_half_casts_its_left_half(cards):
    """709.3: a half is chosen; like any split card here, an intent without one casts the left half."""
    s = build(cards, GRAND)
    room = to_hand(s, GRAND)
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=room.id)
    settle(s)
    assert doors(s, room) == [1] and len(glimmers(s)) == 1
    roundtrip(s)


def test_a_locked_doors_statics_are_not_there_until_it_is_unlocked(cards):
    """709.5: Lecture Hall's hexproof grant and Steaming Sauna's "no maximum hand size" apply only once their door is unlocked."""
    from app.rules import hand_size

    s = build(cards, "Restricted Office // Lecture Hall", "Roaring Furnace // Steaming Sauna", "Grizzly Bears")
    bears = on_field(s, "Grizzly Bears")
    office = on_field(s, "Restricted Office // Lecture Hall")
    sauna = on_field(s, "Roaring Furnace // Steaming Sauna")
    plan = Plan.view(s.state, "p1", s.cards)
    assert "hexproof" not in plan.ch(s.state.cards[bears.id]).granted and hand_size.maximum(plan, "p1") == 7
    mana(s, "p1", U=4, C=8)
    act(s, "p1", type="unlock_door", card_id=office.id, door=2)
    act(s, "p1", type="unlock_door", card_id=sauna.id, door=2)
    settle(s)
    plan = Plan.view(s.state, "p1", s.cards)
    assert "hexproof" in plan.ch(s.state.cards[bears.id]).granted and hand_size.maximum(plan, "p1") is None
    assert "hexproof" not in plan.ch(s.state.cards[office.id]).granted  # ("other permanents")
    roundtrip(s)


def test_copying_a_room_spell_is_left_to_the_players(cards):
    """709.5d unlocks the door of the half that was cast; a copy of a spell isn't cast (707.10): not automated (refused)."""
    from app.rules import copying

    s = build(cards, GRAND)
    room = to_hand(s, GRAND)
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=room.id, face=0)
    plan = Plan.view(s.state, "p1", s.cards)
    assert "Room spell" in (copying.uncopyable(plan, s.state.cards[room.id]) or "")
