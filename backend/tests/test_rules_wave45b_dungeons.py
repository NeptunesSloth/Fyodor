"""Wave 45B: dungeons and the initiative (CR 2026-09-25). Real Oracle text (tests/fixtures/wave45b_dungeon_cards.json, from data/cards.sqlite); every
scenario checks the replay and a save and a load.

* 309.4c, 701.49: a venture moves the marker one room (the player chooses at a fork, 701.49b) and the room's ability triggers; the bottommost room
  completes the dungeon once its ability has left the stack (309.6, 309.7). Every room of the four dungeons is automated now: Undercity's Arena,
  "Goad target creature.", was the last one resolved by hand (goad, 701.15, is a combat requirement, 508.1d, since wave 3F).
* 726.2: whoever takes the initiative ventures into Undercity; creatures dealing combat damage to its holder take it (and venture).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.rules_state import DungeonMark
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import attack, three, to_phase
from tests.wave9c_kit import build, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave45b_dungeon_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w45b", number=f"D{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def rules(s):
    return s.state.rules


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def drive(s, want=(), limit=150):
    """Resolve everything: a trigger order as offered, a choice with the next of ``want`` it offers (id or label start) else its first option,
    nobody blocks. A by-hand resolution fails the scenario."""
    for _ in range(limit):
        d = rules(s).decision
        if d is None:
            if not s.state.zones.get("stack"):
                return
            act(s, rules(s).priority, type="pass_priority")
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d.kind == "order":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
        else:
            assert d.kind != "manual_resolution", d.prompt
            pick = next((o.id for w in want for o in d.options if o.id == w or o.label.startswith(w)), None)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never settled")


def test_the_undercity_and_initiative_cards_are_full():
    """The fifteen cards whose only gap was Undercity's Arena (and Secret Door, which ventures into every dungeon)."""
    assert len(DATA) == 16
    for c in DATA:
        assert coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level == "FULL", c["name"]


PATHS = [
    ("Lost Mine of Phandelver", ("Cave Entrance", "Goblin Lair", "Storeroom", "Temple of Dumathoin")),
    ("Lost Mine of Phandelver", ("Cave Entrance", "Mine Tunnels", "Fungi Cavern", "Temple of Dumathoin")),
    ("Lost Mine of Phandelver", ("Cave Entrance", "Goblin Lair", "Dark Pool", "Temple of Dumathoin")),
    ("Dungeon of the Mad Mage", ("Yawning Portal", "Dungeon Level", "Goblin Bazaar", "Lost Level", "Runestone Caverns", "Deep Mines",
                                 "Mad Wizard's Lair")),
    ("Dungeon of the Mad Mage", ("Yawning Portal", "Dungeon Level", "Twisted Caverns", "Lost Level", "Muiral's Graveyard", "Deep Mines",
                                 "Mad Wizard's Lair")),
    ("Tomb of Annihilation", ("Trapped Entry", "Veils of Fear", "Sandfall Cell", "Cradle of the Death God")),
    ("Tomb of Annihilation", ("Trapped Entry", "Oubliette", "Cradle of the Death God")),
    ("Undercity", ("Secret Entrance", "Forge", "Trap!", "Archives", "Throne of the Dead Three")),
    ("Undercity", ("Secret Entrance", "Lost Well", "Arena", "Catacombs", "Throne of the Dead Three")),
    ("Undercity", ("Secret Entrance", "Forge", "Arena", "Archives", "Throne of the Dead Three")),
    ("Undercity", ("Secret Entrance", "Lost Well", "Stash", "Catacombs", "Throne of the Dead Three")),
]


@pytest.mark.parametrize(("dungeon", "path"), PATHS, ids=[f"{d}:{p[1]}-{p[-2]}" for d, p in PATHS])
def test_a_venture_walks_a_path_to_completion_with_every_room_resolved(cards, dungeon, path):
    """Secret Door ({4}{U}: venture into the dungeon) once per room: the first chooses the dungeon (Undercity is entered only by the initiative,
    701.49d, 726.2: Goliath Paladin), each next one a room at a fork; every room ability resolves with no by-hand step, and the bottommost room
    completes the dungeon (309.6, 309.7: it is Alice's, and the marker is gone)."""
    s = build(cards, ["Secret Door"] * 3 + ["Grizzly Bears", "Goliath Paladin"], ["Grizzly Bears"])
    for c in [c for c in s.state.cards.values() if c.name in ("Secret Door", "Grizzly Bears")]:
        act(s, c.owner, type="move", card_ids=[c.id], to={"player": c.owner, "zone": "battlefield"})
    season(s)
    for i, room in enumerate(path):
        if i == 0 and dungeon == "Undercity":
            mana(s, "p1", W=1, C=4)
            act(s, "p1", type="cast_spell", card_id=to_hand(s, "Goliath Paladin").id)
        else:
            door = next(c for c in s.state.cards.values() if c.name == "Secret Door" and c.zone == "p1:battlefield")
            mana(s, "p1", U=1, C=4)
            act(s, "p1", type="activate_ability", card_id=door.id, ability=1)
        drive(s, want=([dungeon] if i == 0 else [room]))
        if room != path[-1]:
            assert rules(s).dungeons["p1"].dungeon == dungeon and rules(s).dungeons["p1"].room == room
    assert "p1" not in rules(s).dungeons and rules(s).completed_dungeons["p1"] == [dungeon]
    check(s)


def season(s):
    """The cards put onto the battlefield by hand have been there since before the turn."""
    for c in s.state.cards.values():
        if c.zone.endswith(":battlefield"):
            rules(s).controlled_since[c.id].turn = 0


def test_undercity_arena_goads_a_creature_until_alices_next_turn(cards):
    """Undercity, Arena: "Goad target creature." Alice (who owns the dungeon and controls the room ability) goads Bob's Bears; on Bob's turn it must
    attack, and not Alice (701.15b-c: a player other than the goading player, if able) -- Carol."""
    s = three(cards, ["Goliath Paladin"], ["Grizzly Bears"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    season(s)
    rules(s).dungeons["p1"] = DungeonMark(dungeon="Undercity", room="Lost Well")  # (a venture away from Arena)
    mana(s, "p1", W=1, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Goliath Paladin").id)
    drive(s, want=["Arena", bears.id])  # she takes the initiative, so she ventures into Undercity: to Arena, then its target
    assert s.state.table.initiative == "p1" and rules(s).dungeons["p1"].room == "Arena"
    assert ch(s, bears).imposed >= {"goaded:p1"}
    to_phase(s, "declare_attackers", turn=2)
    with pytest.raises(ActionError, match="attacks each combat if able"):
        act(s, "p2", type="declare_attackers", attackers=[])
    with pytest.raises(ActionError, match="other than Alice"):
        attack(s, (bears, "p1"), pid="p2")
    attack(s, (bears, "p3"), pid="p2")
    check(s)


def test_combat_damage_to_the_initiative_holder_takes_it_and_ventures_into_undercity(cards):
    """726.2: Alice takes the initiative with Avenging Hunter and ventures (Secret Entrance); Bob's unblocked Bears deal combat damage to her, so he
    takes it and ventures into Undercity himself -- his own Secret Entrance, Alice's marker unmoved."""
    s = build(cards, ["Avenging Hunter"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    season(s)
    mana(s, "p1", G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Avenging Hunter").id)
    drive(s, want=["Forest"])
    assert s.state.table.initiative == "p1" and rules(s).dungeons["p1"].room == "Secret Entrance"
    to_phase(s, "declare_attackers", turn=2)
    attack(s, (bears, "p1"), pid="p2")
    drive(s, want=["Forest"])
    assert s.state.players["p1"].life == 38 and s.state.table.initiative == "p2"
    assert rules(s).dungeons["p2"].dungeon == "Undercity" and rules(s).dungeons["p2"].room == "Secret Entrance"
    assert rules(s).dungeons["p1"].room == "Secret Entrance"
    check(s)
