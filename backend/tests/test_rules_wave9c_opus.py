"""Wave 9C: opus ("Whenever you cast an instant or sorcery spell, [effect]. If five or more mana was spent to cast that
spell, [bigger effect] [instead]."), researched against CR 2026-09-25.

* 601.2h / 700.14-style counting: the mana that paid the total cost of the spell cast is what was spent (an X counts; a
  cost reduction does not; convoke and the like are not mana). Read from the spell while the trigger resolves above it.
* 608.2c: "instead" replaces the first effect with the bigger one (one or the other happens, never both).
* 207.2c: "Opus" is an ability word with no rules meaning.

Every scenario uses real Oracle text and checks the replay and a save and a load.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, card_named, check, life, put, to_hand

EXTRA = [
    card('Tackle Artist', set_code='wo', number='E01', mana_cost='{3}{R}', cmc=4.0, type_line='Creature — Orc Sorcerer', oracle_text='Trample\nOpus — Whenever you cast an instant or sorcery spell, put a +1/+1 counter on this creature. If five or more mana was spent to cast that spell, put two +1/+1 counters on this creature instead.', colors=['R'], color_identity=['R'], keywords=['Trample', 'Opus'], power='4', toughness='3'),  # noqa: E501
    card('Thunderdrum Soloist', set_code='wo', number='E02', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Dwarf Bard', oracle_text='Reach\nOpus — Whenever you cast an instant or sorcery spell, this creature deals 1 damage to each opponent. If five or more mana was spent to cast that spell, this creature deals 3 damage to each opponent instead.', colors=['R'], color_identity=['R'], keywords=['Reach', 'Opus'], power='1', toughness='3'),  # noqa: E501
    card('Muse Seeker', set_code='wo', number='E03', mana_cost='{1}{U}', cmc=2.0, type_line='Creature — Elf Wizard', oracle_text='Opus — Whenever you cast an instant or sorcery spell, draw a card. Then discard a card unless five or more mana was spent to cast that spell.', colors=['U'], color_identity=['U'], keywords=['Opus'], power='1', toughness='2'),  # noqa: E501
    card('Exhibition Tidecaller', set_code='wo', number='E04', mana_cost='{U}', cmc=1.0, type_line='Creature — Djinn Wizard', oracle_text='Opus — Whenever you cast an instant or sorcery spell, target player mills three cards. If five or more mana was spent to cast that spell, that player mills ten cards instead.', colors=['U'], color_identity=['U'], keywords=['Mill', 'Opus'], power='0', toughness='2'),  # noqa: E501
    card('Colorstorm Stallion', set_code='wo', number='E05', mana_cost='{1}{U}{R}', cmc=3.0, type_line='Creature — Elemental Horse', oracle_text="Ward {1}, haste\nOpus — Whenever you cast an instant or sorcery spell, this creature gets +1/+1 until end of turn. If five or more mana was spent to cast that spell, create a token that's a copy of this creature.", colors=['R', 'U'], color_identity=['R', 'U'], keywords=['Haste', 'Ward', 'Opus'], power='3', toughness='3'),  # noqa: E501
    card('Molten-Core Maestro', set_code='wo', number='E06', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Goblin Bard', oracle_text="Menace\nOpus — Whenever you cast an instant or sorcery spell, put a +1/+1 counter on this creature. If five or more mana was spent to cast that spell, add an amount of {R} equal to this creature's power.", colors=['R'], color_identity=['R'], keywords=['Menace', 'Opus'], power='2', toughness='2'),  # noqa: E501
    card('Expressive Firedancer', set_code='wo', number='E07', mana_cost='{1}{R}', cmc=2.0, type_line='Creature — Human Sorcerer', oracle_text='Opus — Whenever you cast an instant or sorcery spell, this creature gets +1/+1 until end of turn. If five or more mana was spent to cast that spell, this creature also gains double strike until end of turn.', colors=['R'], color_identity=['R'], keywords=['Opus'], power='2', toughness='2'),  # noqa: E501
    card('Deluge Virtuoso', set_code='wo', number='E08', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Human Wizard', oracle_text='When this creature enters, tap target creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nOpus — Whenever you cast an instant or sorcery spell, this creature gets +1/+1 until end of turn. If five or more mana was spent to cast that spell, this creature gets +2/+2 until end of turn instead.', colors=['U'], color_identity=['U'], keywords=['Opus'], power='2', toughness='2'),  # noqa: E501
    card('Spectacular Skywhale', set_code='wo', number='E09', mana_cost='{2}{U}{R}', cmc=4.0, type_line='Creature — Elemental Whale', oracle_text='Flying\nOpus — Whenever you cast an instant or sorcery spell, this creature gets +3/+0 until end of turn. If five or more mana was spent to cast that spell, put three +1/+1 counters on this creature instead.', colors=['R', 'U'], color_identity=['R', 'U'], keywords=['Flying', 'Opus'], power='1', toughness='4'),  # noqa: E501
    card('Elemental Mascot', set_code='wo', number='E10', mana_cost='{1}{U}{R}', cmc=3.0, type_line='Creature — Elemental Bird', oracle_text='Flying, vigilance\nOpus — Whenever you cast an instant or sorcery spell, this creature gets +1/+0 until end of turn. If five or more mana was spent to cast that spell, exile the top card of your library. You may play that card until the end of your next turn.', colors=['R', 'U'], color_identity=['R', 'U'], keywords=['Flying', 'Vigilance', 'Opus'], power='1', toughness='4'),  # noqa: E501
    card('Small Sorcery', set_code='wo', number='E20', mana_cost='{1}{G}', cmc=2.0, type_line='Sorcery', oracle_text='You gain 1 life.', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Four Sorcery', set_code='wo', number='E21', mana_cost='{3}{G}', cmc=4.0, type_line='Sorcery', oracle_text='You gain 1 life.', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Big Sorcery', set_code='wo', number='E22', mana_cost='{4}{G}', cmc=5.0, type_line='Sorcery', oracle_text='You gain 1 life.', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
]
FULL = ["Tackle Artist", "Thunderdrum Soloist", "Muse Seeker", "Exhibition Tidecaller", "Colorstorm Stallion",
        "Molten-Core Maestro", "Expressive Firedancer", "Deluge Virtuoso", "Spectacular Skywhale", "Elemental Mascot"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def table(cards, creature, *spells, lands=5):
    s = build(cards, (creature, *spells), (), forests=9)
    c = put(s, creature)
    for f in [x for x in s.state.cards.values() if x.name == "Forest" and x.owner == "p1" and x.zone == "p1:library"][:lands]:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    for spell in spells:
        to_hand(s, spell)
    return s, c


def cast(s, name, **kw):
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id, **kw)
    settle(s)


def settle_at(s, player):
    """Resolve everything; a choice among targets picks ``player`` when offered (the others take the first option)."""
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[player] if player in ids else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("the stack never emptied")


def counters(s, c):
    return s.state.cards[c.id].counters.get("+1/+1", 0)


def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", c["name"]


def test_other_wordings_stay_manual():
    from tests.test_rules_scripts import ch as characteristics

    for text in ("Whenever you cast an instant or sorcery spell, put a +1/+1 counter on this creature. If five or more mana was "
                 "spent to cast it, put two +1/+1 counters on this creature instead.",
                 "Whenever you cast an instant or sorcery spell, put a +1/+1 counter on this creature. If five or more green "
                 "mana was spent to cast that spell, put two +1/+1 counters on this creature instead."):
        assert coverage.of_characteristics(characteristics("Test", "Creature — Orc", text)).level != "FULL", text


@pytest.mark.parametrize(("spell", "want"), [("Small Sorcery", 1), ("Four Sorcery", 1), ("Big Sorcery", 2)])
def test_tackle_artist_puts_two_counters_instead_with_five_mana(cards, spell, want):
    s, artist = table(cards, "Tackle Artist", spell)
    cast(s, spell)
    assert counters(s, artist) == want  # (two instead of one: not three)
    check(s)


@pytest.mark.parametrize(("spell", "dmg"), [("Four Sorcery", 1), ("Big Sorcery", 3)])
def test_thunderdrum_soloist_deals_three_instead_of_one(cards, spell, dmg):
    s, _ = table(cards, "Thunderdrum Soloist", spell)
    cast(s, spell)
    assert life(s, "p2") == 40 - dmg
    check(s)


@pytest.mark.parametrize(("spell", "milled"), [("Four Sorcery", 3), ("Big Sorcery", 10)])
def test_exhibition_tidecaller_mills_the_targeted_player(cards, spell, milled):
    s, _ = table(cards, "Exhibition Tidecaller", spell)
    before = len(s.state.zones["p2:library"])
    act(s, "p1", type="cast_spell", card_id=card_named(s, spell).id)
    settle_at(s, "p2")  # the Tidecaller's target
    assert len(s.state.zones["p2:library"]) == before - milled
    check(s)


@pytest.mark.parametrize(("spell", "discards"), [("Four Sorcery", True), ("Big Sorcery", False)])
def test_muse_seeker_discards_unless_five_mana_was_spent(cards, spell, discards):
    s, _ = table(cards, "Muse Seeker", spell)
    hand = len(s.state.zones["p1:hand"]) - 1  # (the spell leaves it)
    graveyard = len(s.state.zones["p1:graveyard"])
    cast(s, spell)
    assert len(s.state.zones["p1:hand"]) == hand + 1 - (1 if discards else 0)
    assert len(s.state.zones["p1:graveyard"]) == graveyard + 1 + (1 if discards else 0)  # the spell, and the discarded card
    check(s)


def test_the_trigger_reads_the_spell_it_was_about_not_the_next_one(cards):
    """Two spells in one turn: five mana then two. Each trigger sees its own spell's payment."""
    s, artist = table(cards, "Tackle Artist", "Big Sorcery", "Small Sorcery", lands=7)
    cast(s, "Big Sorcery")
    assert counters(s, artist) == 2
    cast(s, "Small Sorcery")
    assert counters(s, artist) == 3  # (+1 only: two mana)
    check(s)
