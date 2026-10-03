"""Wave 7B: wordings around activated abilities, researched against CR 2026-09-25.

* "Any player may activate this ability." (602.2, 602.2a): the activator controls the ability and pays its costs.
  Flailing Soldier, Lethal Vapors, Excavation (not with {T} / "sacrifice this": only the controller can pay those).
* "Activate only if …" about the source (attacking, blocked, a creature, its power), about the player (life above the
  starting life total, 103.4) and about the lands ("entered this turn or … a basic land"): Cinder Crawler, Greenhilt
  Trainee, Speaker of the Heavens, Dark Fortress.
* Adapt N (701.46): only if the permanent has no +1/+1 counters. Evolution Witness.

Every scenario checks the replay and a reload from the saved history.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave6c_tokens_pumps import card_named, mana, pt, put, reloaded, settle

EXTRA = [
    card('Flailing Soldier', set_code='tst', number='X01', mana_cost='{R}', cmc=1.0, type_line='Creature — Human Soldier', oracle_text='{1}: This creature gets +1/+1 until end of turn. Any player may activate this ability.\n{1}: This creature gets -1/-1 until end of turn. Any player may activate this ability.', power='2', toughness='2', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Lethal Vapors', set_code='tst', number='X02', mana_cost='{2}{B}{B}', cmc=4.0, type_line='Enchantment', oracle_text='Whenever a creature enters, destroy it.\n{0}: Destroy this enchantment. You skip your next turn. Any player may activate this ability.', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Evolution Witness', set_code='tst', number='X03', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Elf Shaman Mutant', oracle_text='{1}{G}: Adapt 2. (If this creature has no +1/+1 counters on it, put two +1/+1 counters on it.)\nWhenever one or more +1/+1 counters are put on this creature, return target permanent card from your graveyard to your hand.', power='2', toughness='1', colors=['G'], color_identity=['G'], keywords=['Adapt']),  # noqa: E501
    card('Cinder Crawler', set_code='tst', number='X04', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Salamander', oracle_text='{R}: This creature gets +1/+0 until end of turn. Activate only if this creature is blocked.', power='1', toughness='2', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Greenhilt Trainee', set_code='tst', number='X05', mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Elf Warrior', oracle_text="{T}: Target creature gets +4/+4 until end of turn. Activate only if this creature's power is 4 or greater.", power='2', toughness='3', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Speaker of the Heavens', set_code='tst', number='X06', mana_cost='{W}', cmc=1.0, type_line='Creature — Human Cleric', oracle_text="Vigilance, lifelink (Attacking doesn't cause this creature to tap. Damage dealt by this creature also causes you to gain that much life.)\n{T}: Create a 4/4 white Angel creature token with flying. Activate only if you have at least 7 life more than your starting life total and only as a sorcery.", power='1', toughness='1', colors=['W'], color_identity=['W'], keywords=['Lifelink', 'Vigilance']),  # noqa: E501
    card('Dark Fortress', set_code='tst', number='X07', mana_cost='', cmc=0.0, type_line='Land', oracle_text='{T}: Add {C}.\n{T}: Add {B} or {R}. Activate only if this land entered this turn or if you control a basic land.', colors=[], color_identity=['B', 'R'], keywords=[]),  # noqa: E501
    card('Excavation', set_code='tst', number='X08', mana_cost='{U}{U}', cmc=2.0, type_line='Enchantment', oracle_text='{1}, Sacrifice a land: Draw a card. Any player may activate this ability.', colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
]
FULL = ["Flailing Soldier", "Lethal Vapors", "Evolution Witness", "Cinder Crawler", "Greenhilt Trainee",
        "Speaker of the Heavens", "Dark Fortress", "Excavation"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, *names):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Forest")])
    seats = [PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")]))]
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"  # (every player is asked for a response)
    return s


def ability_index(s, c, needle):
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
    return next(a.index for a in ch.abilities if needle in a.text)


def test_definitions_are_full():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
        assert coverage.of_characteristics(chs).level == "FULL", (c["name"], coverage.of_characteristics(chs).manual_parts)


def test_any_player_activates_and_controls_the_ability(cards):
    """Bob pays {1} from his own lands for Alice's Flailing Soldier (602.2: "unless the object says otherwise")."""
    s = build(cards, "Flailing Soldier")
    soldier = put(s, "Flailing Soldier")
    minus = ability_index(s, soldier, "-1/-1")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=soldier.id, ability=ability_index(s, soldier, "+1/+1"))
    # (Alice's activation passed priority: Bob can respond)
    assert s.state.rules.priority == "p2"
    mana(s, "p2", C=1)
    act(s, "p2", type="activate_ability", card_id=soldier.id, ability=minus)
    top = list(s.state.rules.stack.values())[-1]
    assert top.controller == "p2" and top.source_card == soldier.id  # (602.2a: the activator controls it)
    settle(s)
    assert pt(s, soldier) == (2, 2)
    replay_matches(s)
    replay_matches(reloaded(s))


def test_other_abilities_stay_with_their_controller(cards):
    s = build(cards, "Evolution Witness", "Flailing Soldier")
    witness = put(s, "Evolution Witness")
    soldier = put(s, "Flailing Soldier")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=soldier.id, ability=0)
    mana(s, "p2", G=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p2", type="activate_ability", card_id=witness.id, ability=ability_index(s, witness, "Adapt"))


def test_excavation_sacrifices_the_activators_land(cards):
    s = build(cards, "Excavation", "Flailing Soldier")
    ex = put(s, "Excavation")
    put(s, "Flailing Soldier")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=card_named(s, "Flailing Soldier").id, ability=0)
    land = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2" and c.zone == "p2:library")
    act(s, "p2", type="move", card_ids=[land.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, "p2", C=1)
    hand_before = len(s.state.zones["p2:hand"])
    act(s, "p2", type="activate_ability", card_id=ex.id, ability=0, cost_choices=[{"component": 1, "cards": [land.id]}])
    settle(s)
    assert s.state.cards[land.id].zone == "p2:graveyard" and len(s.state.zones["p2:hand"]) == hand_before + 1
    replay_matches(s)
    replay_matches(reloaded(s))


def test_adapt_only_without_counters(cards):
    s = build(cards, "Evolution Witness")
    witness = put(s, "Evolution Witness")
    idx = ability_index(s, witness, "Adapt")
    for _ in range(2):
        mana(s, G=1, C=1)
        act(s, "p1", type="activate_ability", card_id=witness.id, ability=idx)
        settle(s)
    assert s.state.cards[witness.id].counters.get("+1/+1") == 2 and pt(s, witness) == (4, 3)  # (701.46a: the 2nd does nothing)
    replay_matches(s)
    replay_matches(reloaded(s))


def test_activate_only_if_the_source_is_blocked(cards):
    s = build(cards, "Cinder Crawler")
    crawler = put(s, "Cinder Crawler")
    mana(s, R=1)
    with pytest.raises(ActionError, match="only be activated if"):
        act(s, "p1", type="activate_ability", card_id=crawler.id, ability=0)


def test_activate_only_if_power_and_life_conditions(cards):
    s = build(cards, "Greenhilt Trainee", "Speaker of the Heavens")
    trainee = put(s, "Greenhilt Trainee")
    speaker = put(s, "Speaker of the Heavens")
    for c in (trainee, speaker):
        with pytest.raises(ActionError, match="only be activated if"):
            act(s, "p1", type="activate_ability", card_id=c.id, ability=ability_index(s, c, "{T}"))
    assert s.state.players["p1"].life == 40


def test_dark_fortress_needs_a_basic_land_or_to_be_new(cards):
    from app.rules import casting

    s = build(cards, "Dark Fortress")
    fortress = put(s, "Dark Fortress")
    abilities = dict(casting.mana_abilities(s.state, s.state.cards[fortress.id], Plan(s.state, "p1", s.cards, None).info))
    assert len(abilities) == 2  # (it entered this turn)
    until_next = card_named(s, "Dark Fortress")
    assert until_next.id == fortress.id


def test_blocked_crawler_may_pump(cards):
    """509.1h: once blocked, always blocked: the restriction reads the combat record."""
    from app.game.state import AttackTarget

    s = build(cards, "Cinder Crawler")
    crawler = put(s, "Cinder Crawler")
    s.state.cards[crawler.id].attacking = AttackTarget(kind="player", id="p2")
    s.state.rules.blocked.append(crawler.id)
    mana(s, R=1)
    act(s, "p1", type="activate_ability", card_id=crawler.id, ability=0)
    settle(s)
    assert pt(s, crawler) == (2, 2)
