"""Wave 15E: keywords carried out as their Comprehensive Rules definition (CR 2026-09-25), real Oracle text.

* Mentor 702.134a, training 702.149a, dethrone 702.105a, evolve 702.100a, mobilize N 702.181a, repeated soulshift 702.46.
Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import attack, settle, through_combat, token_of, until
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave6c_tokens_pumps import build, mana, put, reloaded, to_hand, tokens
from tests.test_rules_wave6e_statics import attack_with

EXTRA = [
    card('Tributary Instructor', set_code='tst', number='X00', mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Merfolk Shaman', oracle_text='Mentor (Whenever this creature attacks, put a +1/+1 counter on target attacking creature with lesser power.)\nWhenever a creature you control with a +1/+1 counter on it dies, draw a card.', power='4', toughness='4', colors=['G'], color_identity=['G'], keywords=['Mentor']),  # noqa: E501
    card('Jenny Flint', set_code='tst', number='X01', mana_cost='{1}{U}{R}', cmc=3.0, type_line='Legendary Creature — Human Detective', oracle_text='Partner with Madame Vastra\nFirst strike\nTraining (Whenever this creature attacks with another creature with greater power, put a +1/+1 counter on this creature.)\nWhenever you sacrifice a Clue or Food, put a +1/+1 counter on another target creature you control.', power='2', toughness='2', colors=['R', 'U'], color_identity=['R', 'U'], keywords=['Partner with', 'Training', 'First strike', 'Partner']),  # noqa: E501
    card('Treasonous Ogre', set_code='tst', number='X02', mana_cost='{3}{R}', cmc=4.0, type_line='Creature — Ogre Shaman', oracle_text='Dethrone (Whenever this creature attacks the player with the most life or tied for most life, put a +1/+1 counter on it.)\nPay 3 life: Add {R}.', power='2', toughness='3', colors=['R'], color_identity=['R'], keywords=['Dethrone']),  # noqa: E501
    card('Gyre Sage', set_code='tst', number='X03', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Elf Druid', oracle_text='Evolve (Whenever a creature you control enters, if that creature has greater power or toughness than this creature, put a +1/+1 counter on this creature.)\n{T}: Add {G} for each +1/+1 counter on this creature.', power='1', toughness='2', colors=['G'], color_identity=['G'], keywords=['Evolve']),  # noqa: E501
    card('Voice of Victory', set_code='tst', number='X04', mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Human Bard', oracle_text="Mobilize 2 (Whenever this creature attacks, create two tapped and attacking 1/1 red Warrior creature tokens. Sacrifice them at the beginning of the next end step.)\nYour opponents can't cast spells during your turn.", power='1', toughness='3', colors=['W'], color_identity=['W'], keywords=['Mobilize']),  # noqa: E501
    card('Blackblade Reforged', set_code='tst', number='X06', mana_cost='{1}', cmc=1.0, type_line='Legendary Artifact — Equipment', oracle_text='Equipped creature gets +1/+1 for each land you control.\nEquip legendary creature {3}\nEquip {7}', power=None, toughness=None, colors=[], color_identity=[], keywords=['Equip']),  # noqa: E501
    card('Demonmail Hauberk', set_code='tst', number='X07', mana_cost='{4}', cmc=4.0, type_line='Artifact — Equipment', oracle_text='Equipped creature gets +4/+2.\nEquip—Sacrifice a creature. (Sacrifice a creature: Attach to target creature you control. Equip only as a sorcery.)', power=None, toughness=None, colors=[], color_identity=[], keywords=['Equip']),  # noqa: E501
    card('Bureau Headmaster', set_code='tst', number='X08', mana_cost='{R}{W}', cmc=2.0, type_line='Creature — Human Assassin', oracle_text='Equipment spells you cast cost {1} less to cast.\nEquip abilities you activate cost {1} less to activate.', power='2', toughness='2', colors=['R', 'W'], color_identity=['R', 'W'], keywords=[]),  # noqa: E501
    card('Entangling Vines', set_code='tst', number='X09', mana_cost='{3}{G}', cmc=4.0, type_line='Enchantment — Aura', oracle_text="Enchant tapped creature\nEnchanted creature doesn't untap during its controller's untap step.", power=None, toughness=None, colors=['G'], color_identity=['G'], keywords=['Enchant']),  # noqa: E501
    card('Blastoderm', set_code='tst', number='X10', mana_cost='{2}{G}{G}', cmc=4.0, type_line='Creature — Beast', oracle_text="Shroud (This creature can't be the target of spells or abilities.)\nFading 3 (This creature enters with three fade counters on it. At the beginning of your upkeep, remove a fade counter from it. If you can't, sacrifice it.)", power='5', toughness='5', colors=['G'], color_identity=['G'], keywords=['Shroud', 'Fading']),  # noqa: E501
    card('Calciderm', set_code='tst', number='X11', mana_cost='{2}{W}{W}', cmc=4.0, type_line='Creature — Beast', oracle_text="Shroud (This creature can't be the target of spells or abilities.)\nVanishing 4 (This creature enters with four time counters on it. At the beginning of your upkeep, remove a time counter from it. When the last is removed, sacrifice it.)", power='5', toughness='5', colors=['W'], color_identity=['W'], keywords=['Shroud', 'Vanishing']),  # noqa: E501
    card('Hyena Umbra', set_code='tst', number='X12', mana_cost='{W}', cmc=1.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature gets +1/+1 and has first strike.\nUmbra armor (If enchanted creature would be destroyed, instead remove all damage from it and destroy this Aura.)', power=None, toughness=None, colors=['W'], color_identity=['W'], keywords=['Enchant', 'Umbra armor']),  # noqa: E501
    card('Wayward Swordtooth', set_code='tst', number='X13', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Dinosaur', oracle_text="Ascend (If you control ten or more permanents, you get the city's blessing for the rest of the game.)\nYou may play an additional land on each of your turns.\nThis creature can't attack or block unless you have the city's blessing.", power='5', toughness='5', colors=['G'], color_identity=['G'], keywords=['Ascend']),  # noqa: E501
    card('Secrets of the Golden City', set_code='tst', number='X14', mana_cost='{1}{U}{U}', cmc=3.0, type_line='Sorcery', oracle_text="Ascend (If you control ten or more permanents, you get the city's blessing for the rest of the game.)\nDraw two cards. If you have the city's blessing, draw three cards instead.", power=None, toughness=None, colors=['U'], color_identity=['U'], keywords=['Ascend']),  # noqa: E501
    card('Snake Cult Initiation', set_code='tst', number='X15', mana_cost='{3}{B}', cmc=4.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature has poisonous 3. (Whenever it deals combat damage to a player, that player gets three poison counters. A player with ten or more poison counters loses the game.)', power=None, toughness=None, colors=['B'], color_identity=['B'], keywords=['Enchant']),  # noqa: E501
    card('Forked-Branch Garami', set_code='tst', number='X05', mana_cost='{3}{G}{G}', cmc=5.0, type_line='Creature — Spirit', oracle_text='Soulshift 4, soulshift 4 (When this creature dies, you may return up to two target Spirit cards with mana value 4 or less from your graveyard to your hand.)', power='4', toughness='4', colors=['G'], color_identity=['G'], keywords=['Soulshift']),  # noqa: E501
]
FULL = [c["name"] if isinstance(c, dict) else c.name for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def next_own_turn(s):
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None
          and s.state.turn.active_player == "p1")


def counters(s, c):
    return s.state.cards[c.id].counters.get("+1/+1", 0)


def attack_and_settle(s, *attackers):
    next_own_turn(s)
    attack_with(s, *attackers)
    settle(s)


def test_mentor_puts_a_counter_on_a_lesser_attacker(cards):
    s = build(cards, "Tributary Instructor")
    mentor = put(s, "Tributary Instructor")
    small = token_of(s, "p1", "Squirrel", "Token Creature — Squirrel", "1/1")
    big = token_of(s, "p1", "Ogre", "Token Creature — Ogre", "5/5")
    next_own_turn(s)
    attack_with(s, mentor, small, big)
    until(s, lambda s: counters(s, small) == 1 or s.state.rules.decision is not None and s.state.rules.decision.kind != "declare_blockers")
    d = s.state.rules.decision
    if d is not None and d.kind == "choose_cards":
        assert {o.id for o in d.options} == {small.id}  # only a lesser power: 702.134a
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[small.id])
    settle(s)
    assert counters(s, small) == 1 and counters(s, big) == 0 and counters(s, mentor) == 0
    check(s)


def test_training_counts_a_greater_power_attacker(cards):
    s = build(cards, "Jenny Flint")
    jenny = put(s, "Jenny Flint")
    big = token_of(s, "p1", "Ogre", "Token Creature — Ogre", "5/5")
    attack_and_settle(s, jenny, big)
    assert counters(s, jenny) == 1  # 702.149a
    check(s)


def test_training_alone_does_nothing(cards):
    s = build(cards, "Jenny Flint")
    jenny = put(s, "Jenny Flint")
    attack_and_settle(s, jenny)
    assert counters(s, jenny) == 0
    check(s)


def test_dethrone_needs_the_player_with_the_most_life(cards):
    s = build(cards, "Treasonous Ogre")
    ogre = put(s, "Treasonous Ogre")
    act(s, "p1", type="set_life", player="p2", value=50)  # the most life of the two (Commander starts at 40)
    attack_and_settle(s, ogre)
    assert counters(s, ogre) == 1  # 702.105a
    check(s)


def test_dethrone_does_not_trigger_on_the_lower_life_player(cards):
    s = build(cards, "Treasonous Ogre")
    ogre = put(s, "Treasonous Ogre")
    act(s, "p1", type="set_life", player="p2", value=10)
    attack_and_settle(s, ogre)
    assert counters(s, ogre) == 0
    check(s)


def test_evolve_when_a_bigger_creature_enters(cards):
    s = build(cards, "Gyre Sage", "Tributary Instructor", "Voice of Victory")
    sage = put(s, "Gyre Sage")
    for name, m, counters_after in (("Tributary Instructor", {"G": 1, "C": 3}, 1), ("Voice of Victory", {"W": 1, "C": 1}, 1)):
        spell = to_hand(s, name)
        act(s, "p1", type="add_mana", player="p1", mana=m)
        act(s, "p1", type="cast_spell", card_id=spell.id)
        settle(s)
        # 702.100a: the 4/4 has greater power and toughness than the 1/2; then the 1/3 isn't greater than the 2/3 Sage
        assert counters(s, sage) == counters_after
    check(s)


def test_mobilize_makes_attacking_warriors_that_are_sacrificed(cards):
    s = build(cards, "Voice of Victory")
    voice = put(s, "Voice of Victory")
    attack_and_settle(s, voice)
    warriors = [t for t in tokens(s) if t.name == "Warrior"]
    assert len(warriors) == 2 and all(s.state.cards[w.id].tapped for w in warriors)  # 702.181a
    until(s, lambda s: s.state.turn.phase == "end" or not [t for t in tokens(s) if t.name == "Warrior"])
    settle(s)
    until(s, lambda s: not [t for t in tokens(s) if t.name == "Warrior"] or s.state.turn.number > 3)
    assert not [t for t in tokens(s) if t.name == "Warrior"]  # sacrificed at the next end step
    check(s)


def test_equip_a_quality_limits_the_target(cards):
    s = build(cards, "Blackblade Reforged")
    blade = put(s, "Blackblade Reforged")
    plain = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    legend = token_of(s, "p1", "Hero", "Token Legendary Creature — Human", "2/2")
    mana(s, C=3)
    with pytest.raises(Exception):
        act(s, "p1", type="activate_ability", card_id=blade.id, ability=1, targets=[plain.id])  # 702.6b: legendary only
    act(s, "p1", type="activate_ability", card_id=blade.id, ability=1, targets=[legend.id])
    settle(s)
    assert s.state.cards[blade.id].attached_to == legend.id
    check(s)


def test_equip_with_a_sacrifice_cost(cards):
    s = build(cards, "Demonmail Hauberk")
    hauberk = put(s, "Demonmail Hauberk")
    keep = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    fodder = token_of(s, "p1", "Goat", "Token Creature — Goat", "0/1")
    act(s, "p1", type="activate_ability", card_id=hauberk.id, ability=1, targets=[keep.id])
    d = s.state.rules.decision
    if d is not None:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[fodder.id])
    settle(s)
    assert s.state.cards[hauberk.id].attached_to == keep.id
    assert fodder.id not in s.state.zones["p1:battlefield"]  # sacrificed to pay (a token ceases to exist)
    check(s)


def test_equip_abilities_cost_less_with_bureau_headmaster(cards):
    s = build(cards, "Bureau Headmaster", "Blackblade Reforged")
    put(s, "Bureau Headmaster")
    blade = put(s, "Blackblade Reforged")
    bear = token_of(s, "p1", "Hero", "Token Legendary Creature — Human", "2/2")
    mana(s, C=2)  # Equip legendary creature {3} costs {1} less (601.2f), and not the other equip, nor anything but equip
    act(s, "p1", type="activate_ability", card_id=blade.id, ability=1, targets=[bear.id])
    settle(s)
    assert s.state.cards[blade.id].attached_to == bear.id
    check(s)


def test_enchant_a_described_creature(cards):
    s = build(cards, "Entangling Vines")
    vines = to_hand(s, "Entangling Vines")
    up = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    down = token_of(s, "p1", "Goat", "Token Creature — Goat", "0/1")
    act(s, "p1", type="tap", card_ids=[down.id], tapped=True)
    mana(s, G=1, C=3)
    with pytest.raises(Exception):
        act(s, "p1", type="cast_spell", card_id=vines.id, targets=[up.id])  # 702.5a: only a tapped creature
    act(s, "p1", type="cast_spell", card_id=vines.id, targets=[down.id])
    settle(s)
    assert s.state.cards[vines.id].attached_to == down.id
    check(s)


def _ward_life(cards, answer):
    from tests.test_rules_counter import build as counter_build
    from tests.test_rules_effects import mana as add_mana

    s, bolt, _ = counter_build(cards, "Counterspell")
    act(s, "p2", type="create_token", player="p2", token={"name": "Warden", "type_line": "Token Creature — Test",
                                                         "power": "2", "toughness": "2", "text": "Ward—Pay 3 life."})
    warden = next(c for c in s.state.cards.values() if c.name == "Warden")
    add_mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[warden.id])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.player == "p1")
    d = s.state.rules.decision
    assert "3 life" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[answer])
    until(s, lambda s: not s.state.zones.get("stack"))
    return s, bolt, warden


def test_ward_pay_life_declined_counters_the_spell(cards):
    s, bolt, warden = _ward_life(cards, "decline")
    assert s.state.cards[warden.id].zone == "p2:battlefield" and s.state.players["p1"].life == 40  # 702.21a
    assert s.state.cards[bolt.id].zone == "p1:graveyard" and s.state.cards[warden.id].damage == 0
    check(s)


def test_ward_pay_life_paid_lets_the_spell_resolve(cards):
    s, bolt, warden = _ward_life(cards, "pay")
    assert s.state.players["p1"].life == 37 and warden.id not in s.state.zones["p2:battlefield"]  # paid 3, Bolt killed it
    check(s)


def to_own_turn(s, n):
    until(s, lambda s: s.state.turn.number >= n and s.state.turn.phase == "main1" and s.state.rules.decision is None
          and s.state.turn.active_player == "p1")


def test_fading_counts_down_then_sacrifices(cards):
    s = build(cards, "Blastoderm")
    beast = to_hand(s, "Blastoderm")
    mana(s, G=2, C=2)
    act(s, "p1", type="cast_spell", card_id=beast.id)
    settle(s)
    assert s.state.cards[beast.id].counters.get("fade") == 3  # 702.32a
    for turn, left in ((3, 2), (5, 1), (7, 0)):
        to_own_turn(s, turn)
        assert s.state.cards[beast.id].counters.get("fade", 0) == left and s.state.cards[beast.id].zone == "p1:battlefield"
    to_own_turn(s, 9)  # no counter to remove: sacrificed
    assert s.state.cards[beast.id].zone == "p1:graveyard"
    check(s)


def test_vanishing_sacrifices_when_the_last_counter_goes(cards):
    s = build(cards, "Calciderm")
    beast = to_hand(s, "Calciderm")
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=beast.id)
    settle(s)
    assert s.state.cards[beast.id].counters.get("time") == 4  # 702.63a
    act(s, "p1", type="counter", card_ids=[beast.id], kind="time", delta=-3)  # (by hand: not the last)
    settle(s)
    assert s.state.cards[beast.id].zone == "p1:battlefield"
    to_own_turn(s, 3)  # the upkeep removes the last time counter: sacrificed
    assert s.state.cards[beast.id].zone == "p1:graveyard"
    check(s)


def test_umbra_armor_saves_the_creature_and_destroys_the_aura(cards):
    s = build(cards, "Hyena Umbra", "Lightning Bolt")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    umbra = to_hand(s, "Hyena Umbra")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=umbra.id, targets=[bear.id])
    settle(s)
    assert s.state.cards[umbra.id].attached_to == bear.id
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[bear.id])  # 3 damage to a 3/3: lethal damage (704.5g)
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[bear.id].damage == 0  # 702.89a
    assert s.state.cards[umbra.id].zone == "p1:graveyard"
    check(s)


def test_ascend_permanent_gives_the_blessing_at_ten_permanents(cards):
    s = build(cards, "Wayward Swordtooth")
    for i in range(9):
        token_of(s, "p1", f"T{i}", "Token Creature — Rock", "0/1")
    assert not s.state.players["p1"].city_blessing
    dino = to_hand(s, "Wayward Swordtooth")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=dino.id)  # the tenth permanent
    settle(s)
    assert s.state.players["p1"].city_blessing  # 702.131b
    check(s)


def test_ascend_sorcery_counts_before_the_draw(cards):
    s = build(cards, "Secrets of the Golden City")
    for i in range(10):
        token_of(s, "p1", f"T{i}", "Token Creature — Rock", "0/1")
    spell = to_hand(s, "Secrets of the Golden City")
    hand = len(s.state.zones["p1:hand"])
    mana(s, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    settle(s)
    assert s.state.players["p1"].city_blessing  # 702.131a
    assert len(s.state.zones["p1:hand"]) == hand - 1 + 3  # the card is cast; three cards drawn instead of two
    check(s)


def test_a_granted_triggered_keyword_works(cards):
    s = build(cards, "Snake Cult Initiation")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    aura = to_hand(s, "Snake Cult Initiation")
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[bear.id])
    settle(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.rules.decision is not None
          and s.state.rules.decision.kind == "declare_attackers")
    attack(s, (bear, "p2"))
    through_combat(s)
    assert s.state.players["p2"].resources.get("poison", 0) == 3  # 702.70a, granted by the Aura (613.1f)
    check(s)
