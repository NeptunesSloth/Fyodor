"""Wave 110G session 11b: Kitsune Mystic // Autumn-Tail, Kitsune Sage (CR 710 flip, 303.4 Auras, 701.3 attach).

* "enchanted by two or more Auras" counts the Auras attached to it at the end step (603.4 intervening if).
* Autumn-Tail targets only the Aura; the creature it moves to is chosen on resolution (115.1) and must be able to be enchanted (701.3b).
"""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand
from tests.wave110b_kit import settle

MYSTIC = card("Kitsune Mystic // Autumn-Tail, Kitsune Sage", set_code="t110g", number="K1", mana_cost="{3}{W}", cmc=4.0, layout="flip",
              type_line="Creature — Fox Wizard // Legendary Creature — Fox Wizard", power="2", toughness="3", colors=["W"], color_identity=["W"],
              oracle_text="At the beginning of the end step, if this creature is enchanted by two or more Auras, flip it.\n//\n{1}: Attach target Aura attached to a creature to another creature.",
              card_faces=[{"name": "Kitsune Mystic", "mana_cost": "{3}{W}", "type_line": "Creature — Fox Wizard", "power": "2", "toughness": "3",
                           "oracle_text": "At the beginning of the end step, if this creature is enchanted by two or more Auras, flip it."},
                          {"name": "Autumn-Tail, Kitsune Sage", "mana_cost": "", "type_line": "Legendary Creature — Fox Wizard", "power": "4", "toughness": "5",
                           "oracle_text": "{1}: Attach target Aura attached to a creature to another creature."}])
NAME = MYSTIC["name"]
EXTRA = [MYSTIC, real("Squire", "{W}", 1, "Creature — Human", "", ("1", "1"), "W"), real("Bear Cub", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
         real("Land Aura", "{1}{G}", 2, "Enchantment — Aura", "Enchant land", None, "G")]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full():
    assert coverage.of_card_data({**MYSTIC, "faces": MYSTIC["card_faces"]}).level == "FULL"


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def aura_on(s, name, host):
    mana(s, "p1", W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, name).id, targets=[host.id])
    settle(s)


def to_end(s, m):
    """Pass priority through the end step of turn 1, stopping as soon as the creature flips."""
    for _ in range(12):
        if s.state.cards[m.id].flipped or s.state.turn.number > 1:
            return
        act(s, s.state.rules.priority, type="pass_priority")


@pytest.mark.parametrize("auras, flips", [(1, False), (2, True)])
def test_flips_at_end_step_only_with_two_auras(cards, auras, flips):
    s = build(cards, [NAME, "Pacifism", "Holy Strength"])
    m = put(s, NAME)
    for n in ("Pacifism", "Holy Strength")[:auras]:
        aura_on(s, n, m)
    assert sum(c.attached_to == m.id for c in s.state.cards.values()) == auras
    to_end(s, m)
    settle(s)
    assert s.state.cards[m.id].flipped is flips
    if flips:
        assert ch(s, m).name == "Autumn-Tail, Kitsune Sage"
    check(s)


def test_autumn_tail_moves_an_aura_to_a_chosen_creature_other_than_its_host(cards):
    s = build(cards, [NAME, "Pacifism", "Holy Strength", "Squire", "Bear Cub"])
    m, squire, cub = put(s, NAME), put(s, "Squire"), put(s, "Bear Cub")
    aura_on(s, "Pacifism", m)
    aura_on(s, "Holy Strength", m)
    to_end(s, m)
    settle(s)
    assert s.state.cards[m.id].flipped
    pac = card_named(s, "Pacifism")
    for _ in range(12):  # on to Alice's next turn, where she has priority
        if s.state.turn.number == 3 and s.state.turn.phase == "main1":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    mana(s, "p1", C=1)
    act(s, "p1", type="activate_ability", card_id=m.id, ability=0, targets=[pac.id], target_counts=[1])
    for _ in range(5):  # (settle() would answer the question itself)
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and sorted(o.id for o in d.options) == sorted([squire.id, cub.id])  # not the creature it is on
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[cub.id])
    settle(s)
    assert s.state.cards[pac.id].attached_to == cub.id
    check(s)
