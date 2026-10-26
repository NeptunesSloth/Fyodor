"""Wave 110M: spells that act on other spells, real Oracle text. Every scenario checks the replay and a save and a load.

* 115.7a, 115.9a, 608.2b: "If target spell has only one target and that target is a creature, change that spell's target to another creature." (Meddle):
  any spell may be targeted; the single creature target is judged as Meddle resolves, and the new target must be another legal creature.
"""

from __future__ import annotations

import pytest

from app.cards.importer import build_database
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.test_rules_conditionals import pick, settle, until_asked
from tests.test_rules_wave5b_stack_interaction import EXTRA as _BASE
from tests.test_rules_wave5b_stack_interaction import alice_casts, bob_answers, build, roundtrip
from tests.test_rules_wave5b_stack_interaction import on_field as on_field

EXTRA = [card("Meddle", set_code="tst", number="Y9M01", mana_cost="{1}{U}", cmc=2.0, type_line="Instant",
              oracle_text="If target spell has only one target and that target is a creature, change that spell's target to another creature.",
              colors=["U"], color_identity=["U"])]


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.repository import CardRepository

    settings.ensure_dirs()
    build_database([*fixture_cards(), *_BASE, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_meddle_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Meddle")).level == "FULL"


def meddled(s, spell, **pay):
    bob_answers(s, "Meddle", spell.id, U=1, C=1)


def test_meddle_changes_a_creature_target_to_the_other_creature(cards):
    s = build(cards, p1=("Lightning Bolt", "Grizzly Bears"), p2=("Meddle", "Grizzly Bears"))
    bears, theirs = on_field(s, "Grizzly Bears"), on_field(s, "Grizzly Bears", "p2")
    bolt = alice_casts(s, "Lightning Bolt", targets=[bears.id], R=1)
    meddled(s, bolt)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[theirs.id].zone == "p2:graveyard"  # the Bolt hit Bob's Bears (3 damage: a 2/2 dies, so the damage is on a card in the graveyard)
    roundtrip(s)


def test_meddle_asks_for_the_new_creature_and_never_offers_a_player_or_the_old_target(cards):
    s = build(cards, p1=("Lightning Bolt", "Grizzly Bears"), p2=("Meddle", "Grizzly Bears", "Spellskite"))
    bears, theirs, skite = on_field(s, "Grizzly Bears"), on_field(s, "Grizzly Bears", "p2"), on_field(s, "Spellskite", "p2")
    bolt = alice_casts(s, "Lightning Bolt", targets=[bears.id], R=1)
    meddled(s, bolt)
    d = until_asked(s)
    assert d is not None and d.player == "p2" and {o.id for o in d.options} == {theirs.id, skite.id}
    roundtrip(s)
    pick(s, skite.id)
    settle(s)
    assert s.state.cards[skite.id].damage == 3 and s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[theirs.id].zone == "p2:battlefield"
    roundtrip(s)


def test_meddle_does_nothing_for_a_player_target(cards):
    s = build(cards, p1=("Lightning Bolt",), p2=("Meddle", "Grizzly Bears"))
    theirs = on_field(s, "Grizzly Bears", "p2")
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    meddled(s, bolt)
    settle(s)
    assert s.state.cards[theirs.id].zone == "p2:battlefield" and s.state.players["p2"].life == 37
    roundtrip(s)


def test_meddle_does_nothing_for_a_spell_with_two_targets(cards):
    s = build(cards, p1=("Arc Trail", "Grizzly Bears"), p2=("Meddle", "Grizzly Bears"))
    bears, theirs = on_field(s, "Grizzly Bears"), on_field(s, "Grizzly Bears", "p2")
    trail = alice_casts(s, "Arc Trail", targets=[bears.id, "p2"], counts=[1, 1], R=1, C=1)
    meddled(s, trail)  # (Meddle may target it: 115.9a is judged as it resolves)
    settle(s)
    assert s.state.cards[theirs.id].zone == "p2:battlefield" and s.state.cards[bears.id].zone == "p1:graveyard" and s.state.players["p2"].life == 39
    roundtrip(s)


def test_meddle_leaves_the_target_when_no_other_creature_is_legal(cards):
    s = build(cards, p1=("Murder", "Grizzly Bears"), p2=("Meddle",))
    bears = on_field(s, "Grizzly Bears")
    murder = alice_casts(s, "Murder", targets=[bears.id], B=2, C=1)
    meddled(s, murder)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    roundtrip(s)
