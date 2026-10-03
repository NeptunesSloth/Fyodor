"""Wave 10B: static wordings that turned up as the sole blocker of many cards (real Oracle text throughout).

* "Creatures your opponents control lose flying and can't have or gain flying." (the Archetypes, 613.1f; the denial
  holds whatever the timestamps): app/rules/statics.py ``_DENY``, app/rules/layers.py ``_layer6``.
* The Gates ("This land enters tapped." and, on its own line, "As this land enters, choose a color other than green.",
  614.1c, 614.1d, 614.12a): app/rules/entry_forms.py ``standalone_choice``.

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.state import GameState
from app.rules import coverage
from app.rules.casting import mana_sources
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build as build_c
from tests.test_rules_effects import replay_matches
from tests.test_rules_permissions import build, put
from tests.test_rules_wave4j_leftovers import answer, named
from tests.test_rules_wave5f_types_entries import rules

EXTRA = [
    card('Manor Gate', set_code="tst", number="10B100", type_line='Land',
         oracle_text='This land enters tapped.\nAs this land enters, choose a color other than green.\n{T}: Add {G} or one mana of the chosen color.'),  # noqa: E501
    card('Sea Gate', set_code="tst", number="10B101", type_line='Land',
         oracle_text='This land enters tapped.\nAs this land enters, choose a color other than blue.\n{T}: Add {U} or one mana of the chosen color.'),  # noqa: E501
]
EXTRA += [
    card('Archetype of Imagination', set_code="tst", number="10B110", mana_cost='{4}{U}{U}', cmc=6.0, type_line='Enchantment Creature — Human Wizard', oracle_text='Creatures you control have flying.\nCreatures your opponents control lose flying and can\'t have or gain flying.', power='3', toughness='2', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Archetype of Courage', set_code="tst", number="10B111", mana_cost='{1}{W}{W}', cmc=3.0, type_line='Enchantment Creature — Human Soldier', oracle_text='Creatures you control have first strike.\nCreatures your opponents control lose first strike and can\'t have or gain first strike.', power='2', toughness='2', colors=['W'], color_identity=['W']),  # noqa: E501
    card('Serra Angel', set_code="tst", number="10B112", mana_cost='{3}{W}{W}', cmc=5.0, type_line='Creature — Angel', oracle_text="Flying\nVigilance (Attacking doesn't cause this creature to tap.)", power='4', toughness='4', colors=['W'], color_identity=['W'], keywords=['Flying', 'Vigilance']),  # noqa: E501
]
EXTRA += [
    card('Thought Devourer', set_code="tst", number="10B120", mana_cost='{2}{U}{U}', cmc=4.0, type_line='Creature — Beast', oracle_text='Flying\nYour maximum hand size is reduced by four.', power='4', toughness='4', colors=['U'], color_identity=['U'], keywords=['Flying']),  # noqa: E501
    card('Trusted Advisor', set_code="tst", number="10B121", mana_cost='{U}', cmc=1.0, type_line='Creature — Human Advisor', oracle_text='Your maximum hand size is increased by two.\nAt the beginning of your upkeep, return a blue creature you control to its owner\'s hand.', power='1', toughness='2', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Gnat Miser', set_code="tst", number="10B122", mana_cost='{B}', cmc=1.0, type_line='Creature — Rat Shaman', oracle_text="Each opponent's maximum hand size is reduced by one.", power='1', toughness='1', colors=['B'], color_identity=['B']),  # noqa: E501
    card('Price of Knowledge', set_code="tst", number="10B123", mana_cost='{6}{B}', cmc=7.0, type_line='Enchantment', oracle_text="Players have no maximum hand size.\nAt the beginning of each opponent's upkeep, this enchantment deals damage to that player equal to the number of cards in that player's hand.", colors=['B'], color_identity=['B']),  # noqa: E501
]
EXTRA += [
    card('Mirror Box', set_code="tst", number="10B130", mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text='The "legend rule" doesn\'t apply to permanents you control.\nEach legendary creature you control gets +1/+1.\nEach nontoken creature you control gets +1/+1 for each other creature you control with the same name as that creature.'),  # noqa: E501
    card('Cadric, Soul Kindler', set_code="tst", number="10B131", mana_cost='{2}{R}{W}', cmc=4.0, type_line='Legendary Creature — Dwarf Wizard', oracle_text='The "legend rule" doesn\'t apply to tokens you control.\nWhenever another nontoken legendary permanent you control enters, you may pay {1}. If you do, create a token that\'s a copy of it. That token gains haste. Sacrifice it at the beginning of the next end step.', power='4', toughness='3', colors=['R', 'W'], color_identity=['R', 'W']),  # noqa: E501
    card('Mirror Gallery', set_code="tst", number="10B132", mana_cost='{5}', cmc=5.0, type_line='Artifact', oracle_text='The "legend rule" doesn\'t apply.'),  # noqa: E501
]
LEGEND = ["Mirror Box", "Cadric, Soul Kindler", "Mirror Gallery"]
GATES = ["Manor Gate", "Sea Gate"]
HAND_SIZE = ["Thought Devourer", "Trusted Advisor", "Gnat Miser", "Price of Knowledge"]
ARCHETYPES = ["Archetype of Imagination", "Archetype of Courage"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def roundtrip(s):
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


@pytest.mark.parametrize("name", GATES)
def test_gates_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_a_gate_enters_tapped_with_a_color_other_than_its_own(cards):
    s = build(cards, [(1, "Manor Gate")])
    gate = put(s, "Manor Gate", "hand")
    act(s, "p1", type="play_land", card_id=gate.id)
    d = rules(s).decision  # 614.12a: chosen before it enters
    assert d is not None and [o.id for o in d.options] == ["White", "Blue", "Black", "Red"]  # not green
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Blue"])
    gate = s.state.cards[gate.id]
    assert gate.zone == "p1:battlefield" and gate.tapped and gate.choices == {"Chosen color": "Blue"}  # 614.1d
    act(s, "p1", type="tap", card_ids=[gate.id], tapped=False)
    options = {o for src in mana_sources(s.state, "p1", cards) if src.card_id == gate.id for o in src.options}
    assert options == {("G",), ("U",)}
    roundtrip(s)


@pytest.mark.parametrize("name", ARCHETYPES)
def test_archetypes_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def keywords(s, cards, c):
    return set(Plan(s.state, "p1", cards, None).ch(s.state.cards[c.id]).keywords)


def test_an_archetype_takes_flying_from_the_opponents_creatures_and_gives_it_to_yours(cards):
    s = build(cards, [(1, "Archetype of Imagination"), (1, "Grizzly Bears")], [(1, "Serra Angel"), (1, "Grizzly Bears")])
    bears = put(s, "Grizzly Bears", "battlefield", pid="p1")
    theirs = put(s, "Serra Angel", "battlefield", pid="p2")
    assert "flying" in keywords(s, cards, theirs) and "flying" not in keywords(s, cards, bears)
    put(s, "Archetype of Imagination", "battlefield")
    assert "flying" in keywords(s, cards, bears)  # creatures you control have flying
    assert "flying" not in keywords(s, cards, theirs) and "vigilance" in keywords(s, cards, theirs)  # lose flying only
    roundtrip(s)


def test_the_denial_beats_a_later_grant_whatever_the_timestamps(cards):
    """Both players control an Archetype of Imagination: each one's grant of flying to its own creatures comes after
    or before the other's loss, yet neither side's creatures have flying (they "can't have or gain" it)."""
    s = build(cards, [(1, "Archetype of Imagination"), (1, "Grizzly Bears")], [(1, "Archetype of Imagination"), (1, "Grizzly Bears")])
    mine = put(s, "Archetype of Imagination", "battlefield", pid="p1")
    theirs = put(s, "Archetype of Imagination", "battlefield", pid="p2")
    for c in (mine, theirs):
        assert "flying" not in keywords(s, cards, c)
    roundtrip(s)


@pytest.mark.parametrize("name", LEGEND)
def test_legend_rule_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def legends(s, pid, name, n, kind="Legendary Creature — Test"):
    for _ in range(n):
        act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": f"Token {kind}", "power": "1",
                                                            "toughness": "1", "text": ""})
    return [c for c in s.state.cards.values() if c.name == name and c.owner == pid]


def settle_legends(s):
    """Answer the legend rule decisions (keep the first); return how many of them were asked."""
    asked = 0
    for _ in range(10):
        d = s.state.rules.decision
        if d is None:
            break
        assert "Legend rule" in d.prompt
        asked += 1
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    return asked


def on_table(s, cards_):
    return [c for c in cards_ if c.id in s.state.cards and s.state.cards[c.id].zone.endswith(":battlefield")]


def test_without_an_exemption_the_legend_rule_applies(cards):
    s = build(cards, [(1, "Grizzly Bears")], [(1, "Grizzly Bears")])
    mine = legends(s, "p1", "Hero", 2)
    act(s, "p1", type="pass_priority")
    assert settle_legends(s) == 1 and len(on_table(s, mine)) == 1


def test_mirror_box_exempts_only_its_controllers_permanents(cards):
    s = build(cards, [(1, "Mirror Box")], [(1, "Grizzly Bears")])
    put(s, "Mirror Box", "battlefield")
    mine = legends(s, "p1", "Hero", 3)
    theirs = legends(s, "p2", "Villain", 2)
    act(s, "p1", type="pass_priority")
    assert settle_legends(s) == 1  # Bob's two Villains only
    assert len(on_table(s, mine)) == 3 and len(on_table(s, theirs)) == 1
    roundtrip(s)


def test_cadric_exempts_tokens_you_control_not_other_legends(cards):
    s = build(cards, [(1, "Cadric, Soul Kindler")], [(1, "Grizzly Bears")])
    put(s, "Cadric, Soul Kindler", "battlefield")
    tokens = legends(s, "p1", "Hero", 2)
    theirs = legends(s, "p2", "Hero", 2)  # (Bob's tokens: Cadric says "you")
    act(s, "p1", type="pass_priority")
    assert settle_legends(s) == 1
    assert len(on_table(s, tokens)) == 2 and len(on_table(s, theirs)) == 1
    roundtrip(s)


def test_mirror_gallery_turns_the_rule_off_for_everyone(cards):
    s = build(cards, [(1, "Mirror Gallery")], [(1, "Grizzly Bears")])
    put(s, "Mirror Gallery", "battlefield")
    mine = legends(s, "p1", "Hero", 2)
    theirs = legends(s, "p2", "Villain", 2)
    act(s, "p1", type="pass_priority")
    assert settle_legends(s) == 0 and len(on_table(s, mine)) == 2 and len(on_table(s, theirs)) == 2
    roundtrip(s)


@pytest.mark.parametrize("name", HAND_SIZE)
def test_hand_size_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def hand_after_cleanup(s, size=9):
    """Alice ends her turn holding ``size`` cards; how many does she keep?"""
    hand = s.state.zones["p1:hand"]
    library = s.state.zones["p1:library"]
    act(s, "p1", type="move", card_ids=library[: max(0, size - len(hand))], to={"zone": "hand"})
    assert len(s.state.zones["p1:hand"]) == size
    for _ in range(80):
        if s.state.turn.number == 2:
            break
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            answer(s, [o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return len(s.state.zones["p1:hand"])


@pytest.mark.parametrize("mine,theirs,kept", [
    ((), (), 7),
    (("Thought Devourer",), (), 3),  # reduced by four
    (("Trusted Advisor",), (), 9),  # increased by two
    (("Thought Devourer", "Trusted Advisor"), (), 5),
    ((), ("Gnat Miser",), 6),  # each opponent's, by one
    (("Trusted Advisor",), ("Gnat Miser",), 8),
    ((), ("Price of Knowledge",), 9),  # no maximum for players
])
def test_the_cleanup_discard_follows_the_maximum_hand_size(cards, mine, theirs, kept):
    s = build_c(cards, *mine, p2=theirs)
    for name in mine:
        act(s, "p1", type="move", card_ids=[named(s, name).id], to={"player": "p1", "zone": "battlefield"})
    for name in theirs:
        act(s, "p2", type="move", card_ids=[named(s, name, "p2").id], to={"player": "p2", "zone": "battlefield"})
    assert hand_after_cleanup(s) == kept
    replay_matches(s)
