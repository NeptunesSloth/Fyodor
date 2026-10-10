"""Wave 20D: the tutor and "exiled with" long tail (CR 2026-09-25).

* 701.23: a search spelled as sentences ("Search your library for two cards. Put one into your hand and the other into your graveyard.
  Then shuffle." Final Parting; "… Reveal those cards, put them into your hand, then shuffle." Prismatic Undercurrents), a number of
  mana value ("mana value 4 or 5" Transit Mage, "mana value 9" Grozoth), "total mana value 6 or less" (Protean Hulk), "third from the
  top" (Long-Term Plans), "a land card with a basic land type" (Nervous Gardener), "a snow permanent card, a legendary card, or a Saga
  card" (alternatives), "where X is the number of players who control more lands than you" (Oreskos Explorer, 107.1).
* 608.2c: "Sacrifice this enchantment, search your library …" (Defense of the Heart): the instructions in order.
* 607.2a / 406.3: "Put all cards exiled with this creature into their owners' hands." (Bomat Courier, Connecting the Dots, Kyren Archive): the
  linked "exile the top card of your library face down" ability.
* Privacy: a search's options and the card chosen for the hand never reach the other players; a face-down exiled card stays hidden
  until it is in its owner's hand, and then it is hidden there.

Real Oracle text; each scenario replays the history and survives a save/load round trip."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.visibility import SPECTATOR
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_conditionals import (
    attack,
    combat_step,
    creature,
    sandbox,
    settle,
    through_combat,
    until,
)
from tests.test_rules_effects import mana as add_mana
from tests.test_rules_wave19c_ifyoudo import build, find, roundtrip, to_zone

# --EXTRA-BEGIN--
EXTRA = [
    card('Final Parting', set_code='tst', number="W20D1", mana_cost='{3}{B}{B}', cmc=5.0, type_line='Sorcery',
         oracle_text='Search your library for two cards. Put one into your hand and the other into your graveyard. Then shuffle.', power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=[]),
    card('Fork in the Road', set_code='tst', number="W20D2", mana_cost='{1}{G}', cmc=2.0, type_line='Sorcery',
         oracle_text='Search your library for up to two basic land cards and reveal them. Put one into your hand and the other into your graveyard. Then shuffle.', power=None, toughness=None, colors=['G'], color_identity=['G'], keywords=[]),
    card("Jarad's Orders", set_code='tst', number="W20D3", mana_cost='{2}{B}{G}', cmc=4.0, type_line='Sorcery',
         oracle_text='Search your library for up to two creature cards and reveal them. Put one into your hand and the other into your graveyard. Then shuffle.', power=None, toughness=None, colors=['B', 'G'], color_identity=['B', 'G'], keywords=[]),
    card('Conflux', set_code='tst', number="W20D4", mana_cost='{3}{W}{U}{B}{R}{G}', cmc=8.0, type_line='Sorcery',
         oracle_text='Search your library for a white card, a blue card, a black card, a red card, and a green card. Reveal those cards, put them into your hand, then shuffle.', power=None, toughness=None, colors=['B', 'G', 'R', 'U', 'W'], color_identity=['B', 'G', 'R', 'U', 'W'], keywords=[]),
    card('Lotuslight Dancers', set_code='tst', number="W20D5", mana_cost='{2}{B}{G}{U}', cmc=5.0, type_line='Creature — Zombie Bard',
         oracle_text='Lifelink\nWhen this creature enters, search your library for a black card, a green card, and a blue card. Put those cards into your graveyard, then shuffle.', power='3', toughness='6', colors=['B', 'G', 'U'], color_identity=['B', 'G', 'U'], keywords=['Lifelink']),
    card('Flourishing Bloom-Kin', set_code='tst', number="W20D6", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Plant Elemental',
         oracle_text='This creature gets +1/+1 for each Forest you control.\nDisguise {4}{G}\nWhen this creature is turned face up, search your library for up to two Forest cards and reveal them. Put one of them onto the battlefield tapped and the other into your hand, then shuffle.', power='0', toughness='0', colors=['G'], color_identity=['G'], keywords=['Disguise']),
    card('Kyoshi Island Plaza', set_code='tst', number="W20D7", mana_cost='{3}{G}', cmc=4.0, type_line='Legendary Enchantment — Shrine',
         oracle_text='When Kyoshi Island Plaza enters, search your library for up to X basic land cards, where X is the number of Shrines you control. Put those cards onto the battlefield tapped, then shuffle.\nWhenever another Shrine you control enters, search your library for a basic land card, put it onto the battlefield tapped, then shuffle.', power=None, toughness=None, colors=['G'], color_identity=['G'], keywords=[]),
    card('Prismatic Undercurrents', set_code='tst', number="W20D8", mana_cost='{3}{G}', cmc=4.0, type_line='Enchantment',
         oracle_text='Vivid — When this enchantment enters, search your library for up to X basic land cards, where X is the number of colors among permanents you control. Reveal those cards, put them into your hand, then shuffle.\nYou may play an additional land on each of your turns.', power=None, toughness=None, colors=['G'], color_identity=['G'], keywords=['Vivid']),
    card('Oreskos Explorer', set_code='tst', number="W20D9", mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Cat Scout',
         oracle_text='When this creature enters, search your library for up to X Plains cards, where X is the number of players who control more lands than you. Reveal those cards, put them into your hand, then shuffle.', power='2', toughness='2', colors=['W'], color_identity=['W'], keywords=[]),
    card("Surveyor's Scope", set_code='tst', number="W20D10", mana_cost='{2}', cmc=2.0, type_line='Artifact',
         oracle_text='{T}, Exile this artifact: Search your library for up to X basic land cards, where X is the number of players who control at least two more lands than you. Put those cards onto the battlefield, then shuffle.', power=None, toughness=None, colors=[], color_identity=[], keywords=[]),
    card('Nervous Gardener', set_code='tst', number="W20D11", mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Dryad',
         oracle_text='Disguise {G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this creature is turned face up, search your library for a land card with a basic land type, reveal it, put it into your hand, then shuffle.', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=['Disguise']),
    card('Perilous Forays', set_code='tst', number="W20D12", mana_cost='{3}{G}{G}', cmc=5.0, type_line='Enchantment',
         oracle_text='{1}, Sacrifice a creature: Search your library for a land card with a basic land type, put it onto the battlefield tapped, then shuffle.', power=None, toughness=None, colors=['G'], color_identity=['G'], keywords=[]),
    card('Search for Glory', set_code='tst', number="W20D13", mana_cost='{2}{W}', cmc=3.0, type_line='Snow Sorcery',
         oracle_text='Search your library for a snow permanent card, a legendary card, or a Saga card, reveal it, put it into your hand, then shuffle. You gain 1 life for each {S} spent to cast this spell. ({S} is mana from a snow source.)', power=None, toughness=None, colors=['W'], color_identity=['W'], keywords=[]),
    card('Long-Term Plans', set_code='tst', number="W20D14", mana_cost='{2}{U}', cmc=3.0, type_line='Instant',
         oracle_text='Search your library for a card, then shuffle and put that card third from the top.', power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=[]),
    card('Defense of the Heart', set_code='tst', number="W20D15", mana_cost='{3}{G}', cmc=4.0, type_line='Enchantment',
         oracle_text='At the beginning of your upkeep, if an opponent controls three or more creatures, sacrifice this enchantment, search your library for up to two creature cards, put those cards onto the battlefield, then shuffle.', power=None, toughness=None, colors=['G'], color_identity=['G'], keywords=[]),
    card('Protean Hulk', set_code='tst', number="W20D16", mana_cost='{5}{G}{G}', cmc=7.0, type_line='Creature — Beast',
         oracle_text='When this creature dies, search your library for any number of creature cards with total mana value 6 or less, put them onto the battlefield, then shuffle.', power='6', toughness='6', colors=['G'], color_identity=['G'], keywords=[]),
    card('Transit Mage', set_code='tst', number="W20D17", mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Human Wizard',
         oracle_text='When this creature enters, you may search your library for an artifact card with mana value 4 or 5, reveal it, put it into your hand, then shuffle.', power='2', toughness='2', colors=['U'], color_identity=['U'], keywords=[]),
    card('Grozoth', set_code='tst', number="W20D18", mana_cost='{6}{U}{U}{U}', cmc=9.0, type_line='Creature — Leviathan',
         oracle_text="Defender (This creature can't attack.)\nWhen this creature enters, you may search your library for any number of cards that have mana value 9, reveal them, put them into your hand, then shuffle.\n{4}: This creature loses defender until end of turn.\nTransmute {1}{U}{U} ({1}{U}{U}, Discard this card: Search your library for a card with the same mana value as this card, reveal it, put it into your hand, then shuffle. Transmute only as a sorcery.)", power='9', toughness='9', colors=['U'], color_identity=['U'], keywords=['Defender', 'Transmute']),
    card('Uncage the Menagerie', set_code='tst', number="W20D19", mana_cost='{X}{G}{G}', cmc=2.0, type_line='Sorcery',
         oracle_text='Search your library for up to X creature cards with different names that each have mana value X, reveal them, put them into your hand, then shuffle.', power=None, toughness=None, colors=['G'], color_identity=['G'], keywords=[]),
    card("Maze's End", set_code='tst', number="W20D20", mana_cost='', cmc=0.0, type_line='Land',
         oracle_text="This land enters tapped.\n{T}: Add {C}.\n{3}, {T}, Return this land to its owner's hand: Search your library for a Gate card, put it onto the battlefield, then shuffle. If you control ten or more Gates with different names, you win the game.", power=None, toughness=None, colors=[], color_identity=[], keywords=[]),
    card('Connecting the Dots', set_code='tst', number="W20D21", mana_cost='{1}{R}', cmc=2.0, type_line='Enchantment',
         oracle_text="Whenever a creature you control attacks, exile the top card of your library face down. (You can't look at it.)\n{1}{R}, Discard your hand, Sacrifice this enchantment: Put all cards exiled with this enchantment into their owners' hands.", power=None, toughness=None, colors=['R'], color_identity=['R'], keywords=[]),
    card('Bomat Courier', set_code='tst', number="W20D22", mana_cost='{1}', cmc=1.0, type_line='Artifact Creature — Construct',
         oracle_text="Haste\nWhenever this creature attacks, exile the top card of your library face down. (You can't look at it.)\n{R}, Discard your hand, Sacrifice this creature: Put all cards exiled with this creature into their owners' hands.", power='1', toughness='1', colors=[], color_identity=['R'], keywords=['Haste']),
    card('Kyren Archive', set_code='tst', number="W20D23", mana_cost='{3}', cmc=3.0, type_line='Artifact — Book',
         oracle_text="At the beginning of your upkeep, you may exile the top card of your library face down.\n{5}, Discard your hand, Sacrifice this artifact: Put all cards exiled with this artifact into their owner's hand.", power=None, toughness=None, colors=[], color_identity=[], keywords=[]),
    card('Plains', set_code='tst', number='W20DP', mana_cost='', cmc=0.0, type_line='Basic Land — Plains', oracle_text='({T}: Add {W}.)', colors=[], color_identity=['W']),
    card('Hill Giant', set_code='tst', number='W20DH', mana_cost='{3}{R}', cmc=4.0, type_line='Creature — Giant', oracle_text='', power='3', toughness='3', colors=['R'], color_identity=['R']),
    card('Runeclaw Bear', set_code='tst', number='W20DB', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Bear', oracle_text='', power='2', toughness='2', colors=['G'], color_identity=['G']),
    card('Three Anvil', set_code='tst', number='W20DA3', mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text='', colors=[], color_identity=[]),
    card('Four Anvil', set_code='tst', number='W20DA4', mana_cost='{4}', cmc=4.0, type_line='Artifact', oracle_text='', colors=[], color_identity=[]),
    card('Five Anvil', set_code='tst', number='W20DA5', mana_cost='{5}', cmc=5.0, type_line='Artifact', oracle_text='', colors=[], color_identity=[]),
    card('Colossus', set_code='tst', number='W20DC', mana_cost='{6}{G}', cmc=7.0, type_line='Creature — Giant', oracle_text='', power='7', toughness='7', colors=['G'], color_identity=['G']),
]
FULL = [c['name'] for c in EXTRA[:-7]]
# --EXTRA-END--


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def ids(s, name, pid="p1"):
    return [c.id for c in s.state.cards.values() if c.name == name and c.owner == pid]


def hidden_from_others(s, *names):
    """Neither the other player nor a spectator can find any of ``names`` anywhere in their view of the table."""
    for viewer in ("p2", SPECTATOR):
        blob = json.dumps(s.view(viewer))
        assert not any(n in blob for n in names), (viewer, names)


def answer(s, *chosen):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(chosen))


def test_final_parting_puts_one_card_into_the_hand_and_one_into_the_graveyard_privately(cards):
    """Final Parting (the three sentences are one search, 701.23): the options and the card chosen for the hand stay private."""
    s = build(cards, p1=("Final Parting", "Lightning Bolt", "Runeclaw Bear"))
    parting = to_zone(s, find(s, "Final Parting"), "hand")
    add_mana(s, "p1", B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=parting.id)
    settle_until_decision(s)
    d = s.state.rules.decision
    assert d.player == "p1" and d.kind == "choose_cards" and d.max_choices == 2 and d.min_choices == 2
    hidden_from_others(s, "Lightning Bolt", "Runeclaw Bear")
    bolt, bear = ids(s, "Lightning Bolt")[0], ids(s, "Runeclaw Bear")[0]
    answer(s, bolt, bear)
    d = s.state.rules.decision  # which of the two goes to the hand
    assert d.player == "p1" and {o.id for o in d.options} == {bolt, bear}
    hidden_from_others(s, "Lightning Bolt", "Runeclaw Bear")
    answer(s, bolt)
    settle(s)
    assert s.state.cards[bolt].zone == "p1:hand" and s.state.cards[bear].zone == "p1:graveyard"
    hidden_from_others(s, "Lightning Bolt")  # the card in the hand stays hidden
    assert "Runeclaw Bear" in json.dumps(s.view("p2"))  # the graveyard is public
    roundtrip(s)


def settle_until_decision(s, limit=20):
    for _ in range(limit):
        if s.state.rules.decision is not None:
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision")


def test_prismatic_undercurrents_reveals_the_found_basic_lands(cards):
    """"Reveal those cards, put them into your hand, then shuffle." after the search sentence (Vivid: the colors among permanents)."""
    s = build(cards, p1=("Prismatic Undercurrents", "Plains", "Plains"))
    pu = to_zone(s, find(s, "Prismatic Undercurrents"), "hand")
    add_mana(s, "p1", G=2, C=2)
    act(s, "p1", type="cast_spell", card_id=pu.id)
    settle_until_decision(s)
    d = s.state.rules.decision
    assert d.max_choices == 1  # one color among the permanents Alice controls (Prismatic Undercurrents itself is green: 1 color)
    plains = ids(s, "Plains")
    answer(s, plains[0])
    settle(s)
    assert s.state.cards[plains[0]].zone == "p1:hand"
    roundtrip(s)


def test_oreskos_explorer_counts_the_players_with_more_lands(cards):
    s = build(cards, p1=("Oreskos Explorer", "Plains", "Plains"), p2=())
    islands = [c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][:2]
    for i in islands:
        to_zone(s, i, "battlefield")
    oe = to_zone(s, find(s, "Oreskos Explorer"), "hand")
    add_mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=oe.id)
    settle_until_decision(s)
    d = s.state.rules.decision
    assert d.max_choices == 1  # one player (Bob) controls more lands than Alice
    answer(s, ids(s, "Plains")[0])
    settle(s)
    assert [s.state.cards[c].name for c in zone(s.state, "p1", "hand")].count("Plains") == 1
    roundtrip(s)


def test_long_term_plans_puts_the_card_third_from_the_top(cards):
    s = build(cards, p1=("Long-Term Plans", "Lightning Bolt"))
    plans = to_zone(s, find(s, "Long-Term Plans"), "hand")
    add_mana(s, "p1", U=2, C=2)
    act(s, "p1", type="cast_spell", card_id=plans.id)
    settle_until_decision(s)
    answer(s, ids(s, "Lightning Bolt")[0])
    settle(s)
    library = zone(s.state, "p1", "library")
    assert s.state.cards[library[2]].name == "Lightning Bolt" and sum(s.state.cards[c].name == "Lightning Bolt" for c in library) == 1
    hidden_from_others(s, "Lightning Bolt")
    roundtrip(s)


def test_protean_hulk_finds_creatures_with_total_mana_value_six_or_less(cards):
    s = build(cards, p1=("Protean Hulk", "Hill Giant", "Runeclaw Bear", "Colossus"))
    hulk = to_zone(s, find(s, "Protean Hulk"), "battlefield")
    act(s, "p1", type="set_damage", card_ids=[hulk.id], value=20)  # lethal damage: the state-based action moves it (704.5g)
    settle_until_decision(s)
    d = s.state.rules.decision
    giant, bear, colossus = ids(s, "Hill Giant")[0], ids(s, "Runeclaw Bear")[0], ids(s, "Colossus")[0]
    assert d.min_choices == 0 and d.max_choices == 3
    with pytest.raises(ActionError):  # 4 + 2 + 7
        answer(s, giant, bear, colossus)
    with pytest.raises(ActionError):  # 7 alone
        answer(s, colossus)
    answer(s, giant, bear)  # 4 + 2
    settle(s)
    assert s.state.cards[giant].zone == s.state.cards[bear].zone == "p1:battlefield"
    assert find(s, "Colossus").zone == "p1:library"  # (the shuffle gave the cards left in the library new ids)
    roundtrip(s)


def test_transit_mage_searches_for_an_artifact_with_mana_value_four_or_five(cards):
    s = build(cards, p1=("Transit Mage", "Three Anvil", "Four Anvil", "Five Anvil"))
    mage = to_zone(s, find(s, "Transit Mage"), "hand")
    add_mana(s, "p1", U=1, C=4)
    act(s, "p1", type="cast_spell", card_id=mage.id)
    settle_until_decision(s)
    answer(s, "yes")
    d = s.state.rules.decision
    assert {s.state.cards[o.id].name for o in d.options} == {"Four Anvil", "Five Anvil"}  # mana value 4 or 5, nothing else
    answer(s, ids(s, "Five Anvil")[0])
    settle(s)
    assert s.state.cards[ids(s, "Five Anvil")[0]].zone == "p1:hand"
    roundtrip(s)


def test_perilous_forays_finds_a_land_with_a_basic_land_type(cards):
    s = build(cards, p1=("Perilous Forays", "Command Tower", "Breeding Pool", "Plains"))
    forays = to_zone(s, find(s, "Perilous Forays"), "battlefield")
    creature(s, "p1", "Fodder")
    add_mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=forays.id, ability=0)
    settle_until_decision(s)
    d = s.state.rules.decision
    names = {s.state.cards[o.id].name for o in d.options}
    assert {"Breeding Pool", "Plains", "Forest"} <= names and "Command Tower" not in names
    answer(s, ids(s, "Breeding Pool")[0])
    settle(s)
    assert s.state.cards[ids(s, "Breeding Pool")[0]].zone == "p1:battlefield"
    roundtrip(s)


def test_defense_of_the_heart_sacrifices_itself_and_searches_when_an_opponent_has_three_creatures(cards):
    s = build(cards, p1=("Defense of the Heart", "Hill Giant", "Runeclaw Bear"))
    heart = to_zone(s, find(s, "Defense of the Heart"), "battlefield")
    for n in ("A", "B", "C"):
        creature(s, "p2", f"Token {n}")
    until(s, lambda st: st.state.rules.decision is not None and st.state.rules.decision.player == "p1"
          and st.state.rules.decision.kind == "choose_cards", limit=200)
    assert s.state.cards[heart.id].zone == "p1:graveyard"  # sacrificed first
    d = s.state.rules.decision
    giant, bear = ids(s, "Hill Giant")[0], ids(s, "Runeclaw Bear")[0]
    assert d.max_choices == 2
    answer(s, giant, bear)
    settle(s)
    assert s.state.cards[giant].zone == s.state.cards[bear].zone == "p1:battlefield"
    roundtrip(s)


def test_bomat_courier_returns_the_cards_it_exiled_face_down_and_they_stay_hidden(cards):
    s = sandbox(cards, "Bomat Courier", "Lightning Bolt", "Runeclaw Bear")
    bomat = next(c for c in s.state.cards.values() if c.name == "Bomat Courier" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[bomat.id], to={"player": "p1", "zone": "battlefield"})
    bolt = next(c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p1", "zone": "library"}, index=0)
    combat_step(s)
    attack(s, (bomat, "p2"))
    settle_until_stack_empty(s)
    assert zone(s.state, "p1", "exile") and s.state.cards[zone(s.state, "p1", "exile")[0]].name == "Lightning Bolt"
    hidden_from_others(s, "Lightning Bolt")  # face down: nobody else knows what it is
    through_combat(s)
    add_mana(s, "p1", R=1)
    act(s, "p1", type="activate_ability", card_id=bomat.id, ability=2)
    settle(s)
    assert s.state.cards[bomat.id].zone == "p1:graveyard" and not zone(s.state, "p1", "exile")
    assert any(s.state.cards[c].name == "Lightning Bolt" for c in zone(s.state, "p1", "hand"))
    hidden_from_others(s, "Lightning Bolt")  # in its owner's hand now
    roundtrip(s)


def settle_until_stack_empty(s, limit=30):
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")
