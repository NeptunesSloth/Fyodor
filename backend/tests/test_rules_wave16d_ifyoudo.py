"""Wave 16D: long-tail "this turn" / "instead" wordings (CR 2026-09-25).

* A flavor word that merely begins with a keyword's name ("Toxic Spores — At the beginning of your end step, …") is a
  flavor word like any other (207.2d): the ability is the rest of the line.
* "At the beginning of your end step, if A, X. If B, instead Y." (Tallyman of Nurgle): the intervening "if" (603.4) gates the
  whole ability; the second sentence's condition replaces the first sentence's instructions (608.2c).
* "When target creature dies this turn, …" as a spell's own line (Graceful Reprieve), "When it dies under your control this
  turn" (Desperate Measures: who controlled it as it died, 603.10a), "…deals 3 damage to the creature's controller".
* "If the sacrificed creature's toughness was 4 or greater, … instead" (Witch's Oven: the sacrifice cost's object as it last
  existed, 608.2h), "If that spell's mana value is 5 or greater, … instead" (Prismari Pianist: X on the stack counts, 202.3e).
* "If you put a counter on a creature this turn" (Lasting Tarfire, Sigardian Paladin: the player who put the counters, 122.6).
* "You may cast this card from your graveyard if you gained life this turn" (Oathsworn Vampire), "twice X" / "three times X"
  amounts (Debt to the Deathless, Khaaaaaaaaaaaannn!), "Gain 2 life, surveil 2, then investigate" (Drag the Canal),
  "Attach this Equipment to up to one target creature you control" (Bespoke Battlegarb).

Real Commander cards, their Oracle text transcribed from the card database. Every scenario checks that replaying the
recorded history reproduces the table and that the state survives a save."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_conditionals import build, cast, creature, names_on_field, settle, the_end_step, to_hand
from tests.test_rules_effects import mana, replay_matches

# --EXTRA-BEGIN--
EXTRA = [
    card('Tallyman of Nurgle', set_code='tst', number='A01', mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Astartes Warrior', oracle_text='Lifelink\nThe Seven-fold Chant — At the beginning of your end step, if a creature died this turn, you draw a card and you lose 1 life. If seven or more creatures died this turn, instead you draw seven cards and you lose 7 life.', colors=['B'], color_identity=['B'], keywords=['Lifelink', 'The Seven-fold Chant'], power='2', toughness='3'),  # noqa: E501
    card('Vrock', set_code='tst', number='A02', mana_cost='{3}{B}{B}', cmc=5.0, type_line='Creature — Bird Demon', oracle_text='Flying\nToxic Spores — At the beginning of your end step, if a permanent you controlled left the battlefield this turn, each opponent loses 3 life.', colors=['B'], color_identity=['B'], keywords=['Flying', 'Toxic Spores'], power='3', toughness='3'),  # noqa: E501
    card('Desperate Measures', set_code='tst', number='A03', mana_cost='{B}', cmc=1.0, type_line='Instant', oracle_text='Target creature gets +1/-1 until end of turn. When it dies under your control this turn, draw two cards.', colors=['B'], color_identity=['B'], keywords=[]),  # noqa: E501
    card('Searing Blood', set_code='tst', number='A04', mana_cost='{R}{R}', cmc=2.0, type_line='Instant', oracle_text="Searing Blood deals 2 damage to target creature. When that creature dies this turn, Searing Blood deals 3 damage to the creature's controller.", colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Graceful Reprieve', set_code='tst', number='A05', mana_cost='{1}{W}', cmc=2.0, type_line='Instant', oracle_text="When target creature dies this turn, return that card to the battlefield under its owner's control.", colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card("Witch's Oven", set_code='tst', number='A06', mana_cost='{1}', cmc=1.0, type_line='Artifact', oracle_text='{T}, Sacrifice a creature: Create a Food token. If the sacrificed creature\'s toughness was 4 or greater, create two Food tokens instead. (They\'re artifacts with "{2}, {T}, Sacrifice this token: You gain 3 life.")', colors=[], color_identity=[], keywords=['Food']),  # noqa: E501
    card('Prismari Pianist', set_code='tst', number='A07', mana_cost='{1}{R}{R}', cmc=3.0, type_line='Creature — Djinn Bard', oracle_text="Whenever you cast an instant or sorcery spell, create a 1/1 blue and red Elemental creature token. If that spell's mana value is 5 or greater, create three of those tokens instead.", colors=['R'], color_identity=['R'], keywords=[], power='2', toughness='1'),  # noqa: E501
    card('Lasting Tarfire', set_code='tst', number='A08', mana_cost='{1}{R}', cmc=2.0, type_line='Enchantment', oracle_text='At the beginning of each end step, if you put a counter on a creature this turn, this enchantment deals 2 damage to each opponent.', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Oathsworn Vampire', set_code='tst', number='A09', mana_cost='{1}{B}', cmc=2.0, type_line='Creature — Vampire Knight', oracle_text='This creature enters tapped.\nYou may cast this card from your graveyard if you gained life this turn.', colors=['B'], color_identity=['B'], keywords=[], power='2', toughness='2'),  # noqa: E501
    card('Bespoke Battlegarb', set_code='tst', number='A10', mana_cost='{1}{R}', cmc=2.0, type_line='Artifact — Equipment', oracle_text='Equipped creature gets +2/+0.\nCelebration — At the beginning of combat on your turn, if two or more nonland permanents entered the battlefield under your control this turn, attach this Equipment to up to one target creature you control.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)', colors=['R'], color_identity=['R'], keywords=['Celebration', 'Equip']),  # noqa: E501
    card('Debt to the Deathless', set_code='tst', number='A11', mana_cost='{X}{W}{W}{B}{B}', cmc=4.0, type_line='Sorcery', oracle_text='Each opponent loses two times X life. You gain life equal to the life lost this way.', colors=['B', 'W'], color_identity=['B', 'W'], keywords=[]),  # noqa: E501
    card('Khaaaaaaaaaaaannn!', set_code='tst', number='A12', mana_cost='{X}{R}', cmc=1.0, type_line='Instant', oracle_text='Khaaaaaaaaaaaannn! deals twice X damage to target creature. If that creature would die this turn, exile it instead.', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Drag the Canal', set_code='tst', number='A13', mana_cost='{U}{B}', cmc=2.0, type_line='Instant', oracle_text='Create a 2/2 white and blue Detective creature token. If a creature died this turn, you gain 2 life, surveil 2, then investigate. (Create a Clue token. It\'s an artifact with "{2}, Sacrifice this token: Draw a card.")', colors=['B', 'U'], color_identity=['B', 'U'], keywords=['Surveil', 'Investigate']),  # noqa: E501
    card('Sigardian Paladin', set_code='tst', number='A14', mana_cost='{2}{G}{W}', cmc=4.0, type_line='Creature — Human Knight', oracle_text="As long as you've put one or more +1/+1 counters on a creature this turn, this creature has trample and lifelink.\n{1}{G}{W}: Target creature you control with a +1/+1 counter on it gains trample and lifelink until end of turn.", colors=['G', 'W'], color_identity=['G', 'W'], keywords=[], power='4', toughness='4'),  # noqa: E501
    card('Fire Nation Salvagers', set_code='tst', number='A15', mana_cost='{3}{B}{B}', cmc=5.0, type_line='Creature — Human Soldier', oracle_text="Menace\nWhen this creature enters, put a +1/+1 counter on target creature or Vehicle you control.\nWhenever one or more creatures you control with counters on them deal combat damage to a player, put target creature or Vehicle card from that player's graveyard onto the battlefield under your control.", colors=['B'], color_identity=['B'], keywords=['Menace'], power='3', toughness='3'),  # noqa: E501
    card('Zameck Guildmage', set_code='tst', number='A16', mana_cost='{G}{U}', cmc=2.0, type_line='Creature — Elf Wizard', oracle_text='{G}{U}: This turn, each creature you control enters with an additional +1/+1 counter on it.\n{G}{U}, Remove a +1/+1 counter from a creature you control: Draw a card.', colors=['G', 'U'], color_identity=['G', 'U'], keywords=[], power='2', toughness='2'),  # noqa: E501
]
FULL = ['Tallyman of Nurgle', 'Vrock', 'Desperate Measures', 'Searing Blood', 'Graceful Reprieve', "Witch's Oven",
        'Prismari Pianist', 'Lasting Tarfire', 'Oathsworn Vampire', 'Bespoke Battlegarb', 'Debt to the Deathless',
        'Khaaaaaaaaaaaannn!', 'Drag the Canal', 'Sigardian Paladin', 'Fire Nation Salvagers', 'Zameck Guildmage']
# --EXTRA-END--


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def saved(s):
    """The table saved and loaded again (a restart): play goes on from the loaded one."""
    loaded = GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")
    return loaded


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def put(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def kill(s, *cs):
    """Lethal damage on each (a creature dies: 704.5g), then state-based actions."""
    for c in cs:
        act(s, "p1", type="set_damage", card_ids=[c.id], delta=20)
    act(s, "p1", type="pass_priority")
    settle(s)


def life(s, pid="p1"):
    return s.state.players[pid].life


def hand(s, pid="p1"):
    return len(zone(s.state, pid, "hand"))


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("died", [1, 7])
def test_tallyman_of_nurgle_instead_when_seven_creatures_died(cards, died):
    """"if a creature died this turn, you draw a card and you lose 1 life. If seven or more creatures died this turn, instead
    you draw seven cards and you lose 7 life." (the intervening "if" gates the ability; the instead replaces its instructions)"""
    s = build(cards, "Tallyman of Nurgle")
    put(s, "Tallyman of Nurgle")
    bears = [creature(s, "p2", f"Bear{i}") for i in range(died)]
    kill(s, *bears)
    before, hp = hand(s), life(s)
    s = saved(s)
    the_end_step(s)
    assert hand(s) == before + (7 if died == 7 else 1) and life(s) == hp - (7 if died == 7 else 1)
    replay_matches(s)


def test_tallyman_of_nurgle_nothing_died_does_nothing(cards):
    s = build(cards, "Tallyman of Nurgle")
    put(s, "Tallyman of Nurgle")
    before, hp = hand(s), life(s)
    the_end_step(s)
    assert hand(s) == before and life(s) == hp
    replay_matches(s)


@pytest.mark.parametrize("mine", [True, False])
def test_desperate_measures_draws_only_when_it_dies_under_your_control(cards, mine):
    s = build(cards, "Desperate Measures")
    victim = creature(s, "p1" if mine else "p2", "Mouse", pt="1/1")
    spell = to_hand(s, "Desperate Measures")
    mana(s, B=1)
    before = hand(s) - 1  # (the spell itself leaves the hand)
    cast(s, spell, targets=[victim.id])
    assert victim.id not in zone(s.state, "p1" if mine else "p2", "battlefield")
    assert hand(s) == before + (2 if mine else 0)
    replay_matches(s)
    saved(s)


def test_searing_blood_hits_the_creatures_controller_when_it_dies(cards):
    s = build(cards, "Searing Blood")
    bear = creature(s, "p2", "Bear", pt="2/2")
    spell = to_hand(s, "Searing Blood")
    mana(s, R=2)
    cast(s, spell, targets=[bear.id])
    assert bear.id not in zone(s.state, "p2", "battlefield") and life(s, "p2") == 40 - 3
    replay_matches(s)
    saved(s)


def test_graceful_reprieve_returns_the_creature_that_dies_this_turn(cards):
    s = build(cards, "Graceful Reprieve", "Tallyman of Nurgle")
    tally = put(s, "Tallyman of Nurgle")
    spell = to_hand(s, "Graceful Reprieve")
    mana(s, W=1, C=1)
    cast(s, spell, targets=[tally.id])
    assert tally.id in zone(s.state, "p1", "battlefield")
    s = saved(s)
    kill(s, tally)
    assert named(s, "Tallyman of Nurgle").zone == "p1:battlefield"
    replay_matches(s)


@pytest.mark.parametrize(("pt", "foods"), [("4/4", 2), ("2/2", 1)])
def test_witchs_oven_makes_two_foods_for_a_big_sacrifice(cards, pt, foods):
    s = build(cards, "Witch's Oven")
    oven = put(s, "Witch's Oven")
    creature(s, "p1", "Ox", pt=pt)
    act(s, "p1", type="activate_ability", card_id=oven.id, ability=0)
    settle(s)
    assert names_on_field(s).count("Food") == foods
    replay_matches(s)
    saved(s)


@pytest.mark.parametrize(("x", "tokens"), [(4, 3), (1, 1)])
def test_prismari_pianist_counts_the_spells_x(cards, x, tokens):
    """"If that spell's mana value is 5 or greater, create three of those tokens instead." (X on the stack counts, 202.3e)"""
    s = build(cards, "Prismari Pianist", "Khaaaaaaaaaaaannn!")
    put(s, "Prismari Pianist")
    bear = creature(s, "p2", "Bear", pt="2/2")
    spell = to_hand(s, "Khaaaaaaaaaaaannn!")
    mana(s, R=1 + x)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id], x_value=x)
    settle(s)
    assert names_on_field(s).count("Elemental") == tokens
    replay_matches(s)
    saved(s)


def test_khaaaaaaaaaaaannn_deals_twice_x_and_exiles_what_would_die(cards):
    s = build(cards, "Khaaaaaaaaaaaannn!")
    bear = creature(s, "p2", "Bear", pt="4/4")
    spell = to_hand(s, "Khaaaaaaaaaaaannn!")
    mana(s, R=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bear.id], x_value=2)
    settle(s)
    assert bear.id not in zone(s.state, "p2", "battlefield") and bear.id not in zone(s.state, "p2", "graveyard")
    replay_matches(s)


def test_debt_to_the_deathless_two_times_x(cards):
    s = build(cards, "Debt to the Deathless")
    spell = to_hand(s, "Debt to the Deathless")
    mana(s, W=2, B=2, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=2)
    settle(s)
    assert life(s, "p2") == 40 - 4 and life(s) == 40 + 4
    replay_matches(s)
    saved(s)


@pytest.mark.parametrize("counter", [True, False])
def test_lasting_tarfire_and_sigardian_paladin_read_who_put_the_counter(cards, counter):
    s = build(cards, "Lasting Tarfire", "Sigardian Paladin", "Fire Nation Salvagers")
    put(s, "Lasting Tarfire")
    paladin = put(s, "Sigardian Paladin")
    from app.rules.plan import Plan

    def keywords():
        return Plan.view(s.state, "p1", s.cards).ch(s.state.cards[paladin.id]).keywords

    assert "lifelink" not in keywords()
    if counter:
        salvagers = to_hand(s, "Fire Nation Salvagers")
        mana(s, B=2, C=3)
        cast(s, salvagers)  # its enters trigger puts a +1/+1 counter on the one creature (or Vehicle) it can target
    assert ("lifelink" in keywords()) == counter
    s = saved(s)
    the_end_step(s)
    assert life(s, "p2") == 40 - (2 if counter else 0)
    replay_matches(s)


def test_oathsworn_vampire_can_be_cast_from_the_graveyard_after_life_gain(cards):
    s = build(cards, "Oathsworn Vampire")
    vamp = to_hand(s, "Oathsworn Vampire")
    act(s, "p1", type="move", card_ids=[vamp.id], to={"zone": "graveyard"})
    mana(s, B=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=vamp.id)
    act(s, "p1", type="life", player="p1", delta=2)
    s = saved(s)
    act(s, "p1", type="cast_spell", card_id=vamp.id)
    settle(s)
    assert named(s, "Oathsworn Vampire").zone == "p1:battlefield"
    replay_matches(s)


@pytest.mark.parametrize("died", [True, False])
def test_drag_the_canal_gain_surveil_then_investigate(cards, died):
    s = build(cards, "Drag the Canal")
    bear = creature(s, "p2", "Bear")
    if died:
        kill(s, bear)
    spell = to_hand(s, "Drag the Canal")
    mana(s, U=1, B=1)
    hp = life(s)
    cast(s, spell)
    assert life(s) == hp + (2 if died else 0)
    assert names_on_field(s).count("Clue") == (1 if died else 0) and names_on_field(s).count("Detective") == 1
    replay_matches(s)
    saved(s)


def test_zameck_guildmage_this_turn_creatures_enter_with_a_counter(cards):
    """"{G}{U}: This turn, each creature you control enters with an additional +1/+1 counter on it." — your creatures only, and
    only this turn (614.1c, 611.2a)."""
    s = build(cards, "Zameck Guildmage", "Tallyman of Nurgle")
    guild = put(s, "Zameck Guildmage")
    mana(s, G=1, U=1)
    act(s, "p1", type="activate_ability", card_id=guild.id, ability=0)
    settle(s)
    mana(s, B=1, C=2)
    cast(s, to_hand(s, "Tallyman of Nurgle"))
    assert named(s, "Tallyman of Nurgle").counters.get("+1/+1") == 1
    assert creature(s, "p2", "Bear").counters.get("+1/+1", 0) == 0
    s = saved(s)
    replay_matches(s)
    the_end_step(s)
    assert creature(s, "p1", "Mouse").counters.get("+1/+1", 0) == 0
