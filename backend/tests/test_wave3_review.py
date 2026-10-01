"""Wave 3 final review: regressions for hidden information, cross-merge integration and CR fixes."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches
from tests.test_rules_keywords3f import REAL, build, ch, named, on_top, real, rules, to_hand, token

EXTRA = [
    real("Cryptic Pursuit", "R1", "{2}{U}{R}", 4, "Enchantment", "Whenever you cast an instant or sorcery spell from your hand, "
         "manifest the top card of your library. (Put that card onto the battlefield face down as a 2/2 creature. Turn it face "
         "up any time for its mana cost if it's a creature card.)\nWhenever a face-down creature you control dies, exile it if "
         "it's an instant or sorcery card. You may cast that card until the end of your next turn.", ["U", "R"]),
]


@pytest.fixture()
def cards(settings) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def leaks(s, pid, card):
    blob = json.dumps(s.view(pid))
    return [x for x in blob.split('"') if card.name in x or card.card_id in x]


# -- hidden information (708.5) ---------------------------------------------------------------------------
def test_a_disguised_creatures_ward_trigger_names_nothing_to_the_opponent(cards):
    s = build(cards, "Hunted Bonebrute", players=2)
    brute = to_hand(s, "Hunted Bonebrute")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=brute.id, face_down=True)
    assert not leaks(s, "p2", brute)
    killer = token(s, "p2", "Killer", "1/1", text="{1}: Destroy target creature.")
    pass_until_stack_empty(s)
    mana(s, "p2", C=1)
    gainer = token(s, "p1", "Gainer", "1/1", text="{1}: You gain 1 life.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=gainer.id, ability=0)
    assert rules(s).priority == "p2"
    act(s, "p2", type="activate_ability", card_id=killer.id, ability=0, targets=[brute.id])
    assert len(s.state.zones["stack"]) == 3  # (ward triggered)
    assert not leaks(s, "p2", brute)
    pass_until_stack_empty(s)
    assert not leaks(s, "p2", brute)


def test_a_manifested_creature_attacking_and_goaded_names_nothing_to_the_others(cards):
    from app.game.visibility import SPECTATOR
    from tests.test_rules_keywords3f import until_attackers

    s = build(cards, "Manifest Dread", "Hunted Bonebrute", "Thelonite Hermit", players=3)
    hermit = on_top(s, "Thelonite Hermit")
    on_top(s, "Hunted Bonebrute")  # (the other card: into the graveyard, public)
    to_hand(s, "Manifest Dread")
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=named(s, "Manifest Dread").id)
    pass_until_stack_empty(s)
    d = rules(s).decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[hermit.id])
    pass_until_stack_empty(s)
    assert s.state.cards[hermit.id].face_down
    for pid in ("p2", "p3", SPECTATOR):
        assert not leaks(s, pid, hermit), pid
    until_attackers(s, "p1")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": hermit.id, "target": "p2"}])
    for pid in ("p2", "p3", SPECTATOR):
        assert not leaks(s, pid, hermit), pid
    replay_matches(s)


# -- firebending + kept mana (500.4, 106.4, 702.189a) ---------------------------------------------------------
def _pools_after_step_end(s, phase, pool, combat_mana, kept):
    from app.rules import engine
    from app.rules.plan import Plan

    s.state.turn.phase = phase
    s.state.players["p1"].mana = dict(pool)
    s.state.rules.combat_mana = dict(combat_mana)
    s.state.rules.kept_mana = [{"player": "p1", "mana": m, "until": u, "turn": s.state.turn.number} for m, u in kept]
    plan = Plan(s.state, "p1", s.cards, None)
    engine.empty_pools(plan)
    return {k: v for k, v in plan.state.players["p1"].mana.items() if v}, plan


def test_firebending_and_kept_mana_both_apply_as_a_combat_step_ends(cards):
    s = build(cards, players=2)
    # firebending {R}{R} plus "until end of turn, you don't lose this mana" {G}{R}; one other {U} empties
    got, plan = _pools_after_step_end(s, "declare_attackers", {"R": 3, "G": 1, "U": 1}, {"p1": 2},
                                      [({"G": 1, "R": 1}, "end_of_turn")])
    assert got == {"R": 3, "G": 1}
    assert plan.rules.combat_mana == {"p1": 2}
    # two {R} were spent: what's left is kept (the player spent the other mana first)
    got, _ = _pools_after_step_end(s, "declare_blockers", {"R": 1, "G": 1}, {"p1": 2}, [({"G": 1, "R": 1}, "end_of_turn")])
    assert got == {"R": 1, "G": 1}
    # the combat phase ends: the firebending mana goes, the "until end of turn" mana stays
    got, plan = _pools_after_step_end(s, "end_combat", {"R": 3, "G": 1}, {"p1": 2}, [({"G": 1, "R": 1}, "end_of_turn")])
    assert got == {"R": 1, "G": 1} and not plan.rules.combat_mana
    # "until end of combat" kept mana and firebending end together
    got, _ = _pools_after_step_end(s, "end_combat", {"R": 3}, {"p1": 2}, [({"R": 1}, "end_of_combat")])
    assert got == {}


# -- a face-down permanent that died is a card in the graveyard again (708.9) ------------------------------
def test_cryptic_pursuit_exiles_a_dead_face_down_instant_card(cards):
    s = build(cards, "Cryptic Pursuit", "Soul Summons", "Opt", players=2)
    act(s, "p1", type="move", card_ids=[named(s, "Cryptic Pursuit").id], to={"player": "p1", "zone": "battlefield"})
    opt = on_top(s, "Opt")
    to_hand(s, "Soul Summons")
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=named(s, "Soul Summons").id)
    pass_until_stack_empty(s)
    assert s.state.cards[opt.id].face_down and ch(s, opt).is_creature
    killer = token(s, "p1", "Killer", "1/1", text="{1}: Destroy target creature.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=killer.id, ability=0, targets=[opt.id])
    pass_until_stack_empty(s)
    # "exile it if it's an instant or sorcery card": the card in the graveyard, face up (708.9), not the face-down 2/2
    assert s.state.cards[opt.id].zone == "p1:exile"
    replay_matches(s)
