"""Wave 110B: World at War (500.8 additional phases after the second main phase, 603.7 delayed trigger at its beginning, 701.21 untap)."""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import attack, build, cast, check, mana, put, through_combat

TEXT = ("After the second main phase this turn, there's an additional combat phase followed by an additional main phase. "
        "At the beginning of that combat, untap all creatures that attacked this turn.\n"
        "Rebound (If you cast this spell from your hand, exile it as it resolves. At the beginning of your next upkeep, you may cast this card from exile without paying its mana cost.)")


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository
    from tests.fixtures.cards import fixture_cards
    from tests.test_rules_wave12a_counters_keywords import real

    settings.ensure_dirs()
    build_database([*fixture_cards(), real("World at War", "{3}{R}{R}", 5, "Sorcery", TEXT, None, "R")], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def play_on(s, until_phase_count, limit=120):
    """Pass on (declaring no attackers) and count how many times each phase begins."""
    seen = {}
    last = None
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.turn.number != 1 or s.state.turn.phase == "end":
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
        if s.state.turn.phase != last:
            last = s.state.turn.phase
            seen[last] = seen.get(last, 0) + 1
    return seen


def test_world_at_war_cast_precombat_adds_combat_after_the_second_main(cards):
    """Cast in the first main phase: Bears attack, and when the second main phase begins an extra combat (the Bears untapped by it) and a third main follow."""
    assert coverage.of_card_data(cards.resolve("World at War")).level == "FULL"
    s = build(cards, ["World at War", "Grizzly Bears"], [], forests=30)
    bears = put(s, "Grizzly Bears")
    mana(s, R=5)
    cast(s, "World at War")
    attack(s, bears)
    through_combat(s)  # to the second main phase: its delayed trigger has added the phases
    assert s.state.turn.phase == "main2"
    assert s.state.cards[bears.id].tapped
    for _ in range(20):  # on to the extra combat: its beginning untapped the creature that attacked
        if s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.decision is not None and not s.state.cards[bears.id].tapped
    check(s)


def test_world_at_war_cast_postcombat_adds_combat_now(cards):
    """Cast in the second main phase: the additional combat and main phase follow it directly."""
    s = build(cards, ["World at War", "Grizzly Bears"], [], forests=30)
    s.state.rules.controlled_since[put(s, "Grizzly Bears").id].turn = 0
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[])
    through_combat(s)
    assert s.state.turn.phase == "main2"
    mana(s, R=5)
    cast(s, "World at War")
    seen = play_on(s, None)
    assert seen.get("declare_attackers") == 1
    check(s)
