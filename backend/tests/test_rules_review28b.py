"""Review of wave 28B (draw bodies, count-level draw replacements, the life-loss choke point, mill counts): regression tests.

Real Oracle wording (the local card database), replay and save/load for each scenario; CR 2026-09-25.

* 121.2a / 616.1f / 614.5: Alms Collector's "you and that player each draw a card" are instructions of their own: its controller's draw is
  never dropped when the drawing player's first draw is replaced, and a count replacement not yet applied (Quantum Riddler) may still change
  them — the affected player chooses the order.
* 605.3a / 121.6: a mana ability's "Draw a card." is a draw like any other (through the draw replacements; it can't pause, so a replacement
  with instructions of its own is left to the players, and "the next time you would draw" is used up by it).
* 120.3a / 614.1a: the life a mana ability's damage makes an opponent lose is a life-loss event (Bloodletter of Aclazotz).
* 702.15e: two lifelink sources' gains are separate events but simultaneous: "while you have 5 or less life" (Phial of Galadriel) reads the
  life total before both.
* 121.5 / 614.11b: a card a draw replacement put into the hand wasn't drawn: "Draw three cards and reveal them" doesn't reveal it.
* 119.4 / 118.3 / 118.11: a payment of life is checked against the amount the cost says and is a life loss the replacements change.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave9b_exile_permission import build, put, roundtrip
from tests.test_rules_wave28b_replace import EXTRA, settle, zone

MORE = [
    card("Chromatic Sphere", set_code="tst", number="V01", mana_cost="{1}", cmc=1.0, type_line="Artifact",
         oracle_text="{1}, {T}, Sacrifice this artifact: Add one mana of any color. Draw a card. (Activate only as an instant.)"),
    card("Exquisite Blood", set_code="tst", number="V02", mana_cost="{4}{B}", cmc=5.0, type_line="Enchantment", colors=["B"],
         color_identity=["B"], oracle_text="Whenever an opponent loses life, you gain that much life."),
    card("Test Mill Cost", set_code="tst", number="V03", mana_cost="{1}", cmc=1.0, type_line="Artifact",
         oracle_text="Mill a card: You gain 1 life."),
    card("Darkblast", set_code="tst", number="V05", mana_cost="{B}", cmc=1.0, type_line="Instant", colors=["B"], color_identity=["B"],
         oracle_text="Target creature gets -1/-1 until end of turn.\nDredge 3 (If you would draw a card, you may instead mill three "
         "cards and return this card from your graveyard to your hand.)"),
    card("Secret Door", set_code="tst", number="V04", mana_cost="{U}", cmc=1.0, type_line="Artifact Creature — Wall", colors=["U"],
         color_identity=["U"], power="0", toughness="4", keywords=["Defender", "Venture into the dungeon"],
         oracle_text="Defender\n{4}{U}: Venture into the dungeon. Activate only as a sorcery. (Enter the first room or advance to the next "
         "room.)"),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    names = {c["name"] for c in fixture_cards()}
    build_database(fixture_cards() + [c for c in EXTRA + MORE if c["name"] not in names], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_alms_collectors_controller_still_draws_when_the_drawing_players_first_draw_is_replaced(cards):
    s = build(cards, p1=("Divination", "Underrealm Lich"), p2=("Alms Collector",))
    put(s, "Underrealm Lich", "battlefield")
    put(s, "Alms Collector", "battlefield", "p2")
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    theirs, lib = len(zone(s, "hand", "p2")), len(zone(s, "library"))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert len(zone(s, "hand", "p2")) == theirs + 1  # "instead you and that player each draw a card": Bob's draw isn't dropped
    assert len(zone(s, "library")) == lib - 3  # Alice's one draw, replaced by Underrealm Lich's look at three
    roundtrip(s)


def test_alms_collectors_controller_may_dredge_instead_of_the_draw_it_gets(cards):
    s = build(cards, p1=("Divination",), p2=("Alms Collector", "Darkblast"))
    put(s, "Alms Collector", "battlefield", "p2")
    blast = put(s, "Darkblast", "graveyard", "p2")
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and {o.id for o in d.options} == {"o0", "decline"}  # 702.52a: Bob's own draw
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["o0"])
    settle(s)
    assert s.state.cards[blast.id].zone == "p2:hand" and len(zone(s, "graveyard", "p2")) == 3
    roundtrip(s)


@pytest.mark.parametrize("first,theirs", [("Alms Collector", 2), ("Quantum Riddler", 1)])
def test_alms_collector_and_quantum_riddler_are_ordered_by_the_drawing_player(cards, first, theirs):
    s = build(cards, p1=("Alms Collector", "Sign in Blood"), p2=("Quantum Riddler",))
    put(s, "Alms Collector", "battlefield")
    put(s, "Quantum Riddler", "battlefield", "p2")
    c = put(s, "Sign in Blood", "hand")
    mana(s, B=2)
    mine, before = len(zone(s, "hand")), len(zone(s, "hand", "p2"))
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p2"  # 616.1: the results differ (Riddler can still change "draw a card" after Alms Collector)
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.label.startswith(first)])
    settle(s)
    assert len(zone(s, "hand", "p2")) - before == theirs and len(zone(s, "hand")) == mine - 1 + 1
    roundtrip(s)


def test_a_mana_abilitys_draw_goes_through_the_draw_replacements(cards):
    s = build(cards, p1=("Chromatic Sphere", "Phial of Galadriel"))
    put(s, "Phial of Galadriel", "battlefield")
    sphere = put(s, "Chromatic Sphere", "battlefield")
    for x in list(zone(s, "hand")):
        act(s, "p1", type="move", card_ids=[x], to={"player": "p1", "zone": "graveyard"})
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=sphere.id, ability=0, mana_choice="R")
    assert len(zone(s, "hand")) == 2  # an empty hand: "draw two cards instead"
    roundtrip(s)


def test_a_mana_abilitys_draw_leaves_a_replacement_with_instructions_to_the_players_and_uses_up_the_next_time(cards):
    s = build(cards, p1=("Chromatic Sphere", "Words of Worship", "Divination"))
    words = put(s, "Words of Worship", "battlefield")
    sphere = put(s, "Chromatic Sphere", "battlefield")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=words.id, ability=0)
    settle(s)
    hand, life = len(zone(s, "hand")), s.state.players["p1"].life
    act(s, "p1", type="activate_ability", card_id=sphere.id, ability=0, mana_choice="U")
    texts = ["".join(p.t or "" for p in e.parts) for e in s.state.log[-6:]]
    assert any("Words of Worship would replace a draw here" in t for t in texts)  # (a mana ability can't pause: by hand, 121.6)
    assert len(zone(s, "hand")) == hand + 1 and s.state.players["p1"].life == life
    c = put(s, "Divination", "hand")
    mana(s, C=2, U=1)
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    assert s.state.players["p1"].life == life  # "the next time" was that draw: Divination's draws aren't replaced
    roundtrip(s)


def test_bloodletter_doubles_the_life_a_mana_abilitys_damage_makes_an_opponent_lose(cards):
    s = build(cards, p1=("Bloodletter of Aclazotz", "Vampire's Kiss"), p2=("Shivan Reef", "Lightning Bolt"))
    put(s, "Bloodletter of Aclazotz", "battlefield")
    put(s, "Shivan Reef", "battlefield", "p2")
    bolt = put(s, "Lightning Bolt", "hand", "p2")
    c = put(s, "Vampire's Kiss", "hand")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p1"])
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])  # {R} from Shivan Reef: "This land deals 1 damage to you."
    assert s.state.players["p2"].life == 40 - 2  # 120.3a, 614.1a: 1 damage dealt, 2 life lost
    assert any(e.kind == "damage" and e.amount == 1 and e.player == "p2" for e in s.state.rules.events)
    settle(s)
    roundtrip(s)


def build3(cards, p1=(), p2=()):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    seats = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (9, "Forest")])),
             PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (10, "Island")])),
             PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(10, "Mountain")]))]
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def test_an_opponent_with_3_life_may_pay_2_life_on_bloodletters_turn_and_loses_4(cards):
    s = build3(cards, p1=("Vampire's Kiss", "Bloodletter of Aclazotz", "Exquisite Blood"), p2=("Greed",))
    act(s, "p2", type="life", player="p2", delta=-37)
    put(s, "Bloodletter of Aclazotz", "battlefield")
    put(s, "Exquisite Blood", "battlefield")
    greed = put(s, "Greed", "battlefield", "p2")
    c = put(s, "Vampire's Kiss", "hand")
    mana(s, B=1, C=1)
    mana(s, "p2", B=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p1"])
    life = s.state.players["p1"].life
    act(s, "p2", type="activate_ability", card_id=greed.id, ability=0)  # 119.4 / 118.3: 3 life covers "Pay 2 life"; 118.11: 4 are lost
    assert s.state.players["p2"].life == -1
    settle(s)
    assert "p2" in s.state.rules.lost  # 704.5a
    assert s.state.players["p1"].life == life + 4 + 2 - 2  # Exquisite Blood once, for the 4 life lost; then Vampire's Kiss on Alice
    roundtrip(s)


def test_phial_of_galadriel_doubles_two_simultaneous_lifelink_gains(cards):
    from tests.test_rules_wave5c_combat import build as cbuild
    from tests.test_rules_wave5c_combat import declare, old, through_combat, to_attack
    from tests.test_rules_wave5c_combat import put as cput

    s = cbuild(cards, "Phial of Galadriel")
    cput(s, "Phial of Galadriel")
    act(s, "p1", type="life", player="p1", delta=-36)
    a, b = old(s, "p1", "Lifer A", "2/2", "Lifelink"), old(s, "p1", "Lifer B", "2/2", "Lifelink")
    to_attack(s)
    declare(s, (a, "p2"), (b, "p2"))
    through_combat(s)
    assert s.state.players["p1"].life == 4 + 4 + 4  # 702.15e: both gains happen at 4 life, each is doubled
    roundtrip(s)


def test_bruvac_doubles_a_mill_an_opponent_pays_as_a_cost(cards):
    s = build(cards, p1=("Bruvac the Grandiloquent", "Vampire's Kiss"), p2=("Test Mill Cost",))
    put(s, "Bruvac the Grandiloquent", "battlefield")
    m = put(s, "Test Mill Cost", "battlefield", "p2")
    gy = len(zone(s, "graveyard", "p2"))
    c = put(s, "Vampire's Kiss", "hand")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p1"])
    act(s, "p2", type="activate_ability", card_id=m.id, ability=0)
    assert len(zone(s, "graveyard", "p2")) == gy + 2  # 118.11 / 701.17a: "Mill a card" -> two
    settle(s)
    roundtrip(s)


def test_mad_wizards_lair_reveals_no_card_a_draw_replacement_put_into_the_hand(cards):
    import json

    from tests.test_rules_designations import find as dfind
    from tests.test_rules_designations import resolve, table

    s = table(cards, mine=("Secret Door",), hand=("Underrealm Lich", "Lightning Bolt", "Counterspell", "Murder"))
    door = dfind(s, "Secret Door")

    def venture(*answers):
        mana(s, U=1, C=4)
        act(s, "p1", type="activate_ability", card_id=door.id, ability=1)
        resolve(s, *answers)

    for answers in (("Dungeon of the Mad Mage",), ([],), ("Goblin Bazaar",), ([],), ("Muiral's Graveyard",), ([],)):
        venture(*answers)
    assert s.state.rules.dungeons["p1"].room == "Deep Mines"
    act(s, "p1", type="move", card_ids=[dfind(s, "Underrealm Lich").id], to={"player": "p1", "zone": "battlefield"})
    for name in ("Murder", "Counterspell", "Lightning Bolt"):
        act(s, "p1", type="move", card_ids=[dfind(s, name).id], to={"player": "p1", "zone": "library"}, position="top")
    mana(s, U=1, C=4)
    act(s, "p1", type="activate_ability", card_id=door.id, ability=1)
    bolt = dfind(s, "Lightning Bolt")
    offered: list[str] = []
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            offered += [o.card_id for o in d.options if o.card_id]
            ids = [o.id for o in d.options if o.card_id == bolt.id] or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.rules.completed_dungeons["p1"] == ["Dungeon of the Mad Mage"] and offered.count(bolt.id) == 1  # (Lich's look only)
    assert s.state.cards[bolt.id].zone == "p1:hand"  # not cast for free: it wasn't drawn
    assert "Lightning Bolt" not in json.dumps(s.view("p2"))  # 121.5 / 614.11b: put into the hand by Underrealm Lich, not drawn: not revealed
    roundtrip(s)
