"""Review of wave 22B (prohibitions & card names): regressions for what the review fixed. Real Oracle text; replay and save/load."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

EXTRA = [
    real("Devoted Druid", "{1}{G}", 2, "Creature — Elf Druid", "{T}: Add {G}.\nPut a -1/-1 counter on this creature: Untap this creature.", ("0", "2"), "G"),
    real("Solemnity", "{2}{W}", 3, "Enchantment", "Players can't get counters.\nCounters can't be put on artifacts, creatures, enchantments, or lands.", None, "W"),
    real("Angel of Jubilation", "{1}{W}{W}{W}", 4, "Creature — Angel", "Flying\nOther nonblack creatures you control get +1/+1.\nPlayers can't pay life or sacrifice creatures to cast spells or activate abilities.", ("3", "3"), "W"),
    real("Toxic Deluge", "{2}{B}", 3, "Sorcery", "As an additional cost to cast this spell, pay X life.\nAll creatures get -X/-X until end of turn.", None, "B"),
    real("Owlin Shieldmage", "{3}{W}{B}", 5, "Creature — Bird Warlock", "Flying\nWard—Pay 3 life. (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays 3 life.)", ("3", "3"), "WB"),
    real("Tamiyo, Collector of Tales", "{2}{G}{U}", 4, "Legendary Planeswalker — Tamiyo", "Spells and abilities your opponents control can't cause you to discard cards or sacrifice permanents.\n+1: Choose a nonland card name, then reveal the top four cards of your library. Put all cards with the chosen name from among them into your hand and the rest into your graveyard.\n−3: Return target card from your graveyard to your hand.", None, "GU"),
    real("Painful Quandary", "{3}{B}{B}", 5, "Enchantment", "Whenever an opponent casts a spell, that player loses 5 life unless they discard a card.", None, "B"),
    real("Tatterkite", "{3}", 3, "Artifact Creature — Scarecrow", "Flying\nThis creature can't have counters put on it.", ("2", "1")),
    real("Pithing Needle", "{1}", 1, "Artifact", "As this artifact enters, choose a card name.\nActivated abilities of sources with the chosen name can't be activated unless they're mana abilities."),
    real("Censor", "{1}{U}", 2, "Instant", "Counter target spell unless its controller pays {1}.\nCycling {U} ({U}, Discard this card: Draw a card.)", None, "U"),
    real("Meddling Mage", "{W}{U}", 2, "Creature — Human Wizard", "As this creature enters, choose a nonland card name.\nSpells with the chosen name can't be cast.", ("2", "2"), "WU"),
    real("Clone", "{3}{U}", 4, "Creature — Shapeshifter", "You may have this creature enter as a copy of any creature on the battlefield.", ("0", "0"), "U"),
    real("Probe Bolt", "{R}", 1, "Instant", "Probe Bolt deals 1 damage to any target.", None, "R"),
    real("Probe Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def name_it(s, text, who="p1"):
    d = s.state.rules.decision
    assert d is not None and d.options[0].id == "__name__"
    act(s, who, type="choose", decision_id=d.id, name=text)


def resolve_naming(s, name, text, pid="p1"):
    act(s, pid, type="cast_spell", card_id=to_hand(s, name, pid).id)
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    name_it(s, text, pid)


def test_solemnity_a_cost_that_puts_counters_cant_be_paid(cards):
    """614.17b (Solemnity ruling 2017-07-14): Devoted Druid's "Put a -1/-1 counter on this creature:" can't be activated."""
    s = build(cards, ["Solemnity", "Devoted Druid"], [])
    put(s, "Solemnity")
    druid = put(s, "Devoted Druid")
    act(s, "p1", type="tap", card_ids=[druid.id])
    with pytest.raises(ActionError, match="counters can't be put"):
        act(s, "p1", type="activate_ability", card_id=druid.id, ability=1)
    assert s.state.cards[druid.id].tapped and not s.state.cards[druid.id].counters
    check(s)


def test_angel_of_jubilation_stops_pay_x_life_above_0_only(cards):
    """119.4b: 0 life can always be paid; any more can't while players can't pay life to cast spells."""
    s = build(cards, ["Angel of Jubilation", "Toxic Deluge"], [])
    put(s, "Angel of Jubilation")
    mana(s, B=3)
    deluge = to_hand(s, "Toxic Deluge")
    with pytest.raises(ActionError, match="can't pay life"):
        act(s, "p1", type="cast_spell", card_id=deluge.id, x_value=3)
    act(s, "p1", type="cast_spell", card_id=deluge.id, x_value=0)
    answer(s)
    assert s.state.players["p1"].life == 40 and zone_of(s, "Toxic Deluge") == "p1:graveyard"
    check(s)


def test_angel_of_jubilation_doesnt_stop_life_paid_as_an_ability_resolves(cards):
    """Angel ruling 2012-05-01: a resolving spell or ability may still have a player pay life (ward—pay 3 life)."""
    s = build(cards, ["Angel of Jubilation", "Probe Bolt"], ["Owlin Shieldmage"])
    put(s, "Angel of Jubilation")
    mage = put(s, "Owlin Shieldmage", "p2")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Probe Bolt").id, targets=[mage.id])
    answer(s, "pay")
    assert s.state.players["p1"].life == 37 and s.state.cards[mage.id].damage == 1
    check(s)


def test_tamiyo_an_opponents_unless_discard_cant_be_taken(cards):
    """Tamiyo ruling 2019-05-03: "… unless they discard a card" (Painful Quandary): the discard can't be chosen, so the life is lost."""
    s = build(cards, ["Tamiyo, Collector of Tales", "Probe Bolt", "Probe Bear"], ["Painful Quandary"])
    tamiyo = put(s, "Tamiyo, Collector of Tales")
    act(s, "p1", type="counter", card_ids=[tamiyo.id], kind="loyalty", delta=4)
    put(s, "Painful Quandary", "p2")
    to_hand(s, "Probe Bear")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Probe Bolt").id, targets=["p2"])
    answer(s)
    assert zone_of(s, "Probe Bear") == "p1:hand" and s.state.players["p1"].life == 35
    check(s)


def test_its_own_cant_have_counters_applies_as_it_enters(cards):
    """614.17d: a "can't" that modifies how the permanent itself enters may come from the permanent (Tatterkite returned with a counter)."""
    from app.rules import prohibitions
    from app.rules.plan import Plan

    s = build(cards, ["Tatterkite", "Probe Bear"], [])
    plan = Plan.view(s.state, "p1", s.cards)
    assert prohibitions.cant_counters(plan, card_named(s, "Tatterkite").id, "p1") == "Tatterkite"
    assert prohibitions.cant_counters(plan, card_named(s, "Probe Bear").id, "p1") is None


def test_pithing_needle_stops_cycling_from_the_hand(cards):
    """Pithing Needle ruling 2005-06-01: it affects cards in any zone (you can't cycle the named card)."""
    s = build(cards, ["Pithing Needle", "Censor"], [])
    act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "U": 1})
    resolve_naming(s, "Pithing Needle", "Censor")
    censor = to_hand(s, "Censor")
    with pytest.raises(ActionError, match="can't be activated"):
        act(s, "p1", type="activate_ability", card_id=censor.id, ability=1)
    assert zone_of(s, "Censor") == "p1:hand"
    check(s)


def test_a_clone_of_meddling_mage_makes_its_own_choice(cards):
    """707.2: the choice isn't copied; the copy has the "As this creature enters, choose …" replacement and answers it itself."""
    s = build(cards, ["Meddling Mage", "Clone", "Probe Bolt"], [])
    act(s, "p1", type="add_mana", player="p1", mana={"W": 1, "U": 1})
    resolve_naming(s, "Meddling Mage", "Probe Bolt")
    mana(s, U=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Clone").id)
    mage = card_named(s, "Meddling Mage")
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[mage.id])
    name_it(s, "Probe Bear")
    clone = card_named(s, "Clone")
    assert s.state.cards[clone.id].choices.get("Chosen card name") == "Probe Bear"
    assert s.state.cards[mage.id].choices.get("Chosen card name") == "Probe Bolt"
    check(s)
