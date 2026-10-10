"""Wave 29D head review: real Oracle text, replay and a save and a load in every scenario (CR 2026-09-25).

* 725.2, 120.3a, 119.8: combat damage dealt to the monarch steals the crown even when it makes them lose no life (Platinum Emperion).
* 903.10a, 704.6c: combat damage from a commander still counts against a player whose life total can't change (Platinum Emperion ruling).
* 607.3: a copied hideaway trigger exiles two linked cards, and "you may play the exiled card" plays each (Clive's Hideaway ruling 2025-06-06).
* 113.7a: the land's ability on the stack still plays the card after the land left (its source's removal doesn't affect it).
"""

from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.visibility import SPECTATOR
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import attack, through_combat
from tests.test_rules_effects import pass_until_stack_empty
from tests.test_rules_wave9b_exile_permission import put as put9
from tests.test_rules_wave29d_hideaway import BIG, PROBES, activate, creatures, decision, hideaway, play_land, private, stack_top
from tests.test_rules_wave29d_hideaway import REAL as HIDEAWAY
from tests.test_rules_wave29d_life_lock import REAL as LOCK
from tests.test_rules_wave29d_life_lock import check, lock, table
from tests.wave9c_kit import build, card_named, life, mana, put, to_hand

MORE = [
    card('Skewer the Critics', set_code='r29d', number='R2', mana_cost='{2}{R}', cmc=3.0, type_line='Sorcery', colors=['R'], color_identity=['R'],
         keywords=['Spectacle'], oracle_text='Spectacle {R} (You may cast this spell for its spectacle cost rather than its mana cost if an opponent lost '
                                             'life this turn.)\nSkewer the Critics deals 3 damage to any target.'),
    card('Glistener Elf', set_code='r29d', number='R3', mana_cost='{G}', cmc=1.0, type_line='Creature — Phyrexian Elf Warrior', power='1',
         toughness='1', colors=['G'], color_identity=['G'], keywords=['Infect'],
         oracle_text='Infect (This creature deals damage to creatures in the form of -1/-1 counters and to players in the form of poison counters.)'),
    card('Strionic Resonator', set_code='r29d', number='R1', mana_cost='{2}', cmc=2.0, type_line='Artifact', colors=[], color_identity=[],
         oracle_text='{2}, {T}: Copy target triggered ability you control. You may choose new targets for the copy. (A triggered ability uses the '
                     'words "when," "whenever," or "at.")'),
]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *LOCK, *HIDEAWAY[16:], *MORE], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.fixture()
def hidden(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *HIDEAWAY, *MORE], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def swing(s, c, at="p2"):
    s.state.rules.controlled_since[c.id].turn = 0
    act(s, "p1", type="pass_priority")  # → declare attackers
    attack(s, (c, at))


# -- can't lose life: the damage is still dealt (120.3a) -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("locked", [True, False])
def test_combat_damage_to_a_monarch_who_cant_lose_life_still_takes_the_crown(cards, locked):
    s = table(cards)
    if locked:
        lock(s, "p2")
    s.state.table.monarch = "p2"
    swing(s, put(s, "White Probe"))
    through_combat(s)
    assert life(s, "p2") == (40 if locked else 39)
    assert s.state.table.monarch == "p1"  # 725.2: "Whenever a creature deals combat damage to the monarch, its controller becomes the monarch."
    check(s)


@pytest.mark.parametrize("locked", [True, False])
def test_damage_without_life_loss_gives_poison_and_no_spectacle(cards, locked):
    from app.rules import casting

    s = build(cards, ("Platinum Emperion", "Glistener Elf", "Skewer the Critics", "Lightning Bolt"), ("Platinum Emperion",))
    if locked:
        lock(s, "p2")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert life(s, "p2") == (40 if locked else 37) and s.state.rules.damaged.get("p2") == s.state.turn.number  # dealt damage (bloodthirst)
    skewer = to_hand(s, "Skewer the Critics")
    mana(s, R=1)
    assert bool(casting.alt_castable(s.state, "p1", skewer, s.cards)) is not locked  # 702.137a: spectacle needs an opponent who LOST life
    swing(s, put(s, "Glistener Elf"))
    through_combat(s)
    assert life(s, "p2") == (40 if locked else 37) and s.state.players["p2"].resources.get("poison") == 1  # 120.3b: infect is poison counters, not life loss
    check(s)


def test_commander_damage_still_counts_and_a_player_whose_life_total_cant_change_loses_to_it(cards):
    s = table(cards)
    lock(s, "p2")
    krenko = card_named(s, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p2", type="commander_damage", player="p2", commander=krenko.commander_key, delta=18, affect_life=False)
    swing(s, krenko)  # 3 more: 21 combat damage from one commander
    for _ in range(20):
        if s.state.rules.winner is not None:
            break
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p2"].commander_damage[krenko.commander_key] == 21 and life(s, "p2") == 40
    assert s.state.rules.winner == "p1"  # 704.6c / 903.10a (Platinum Emperion ruling: commander damage is still counted)
    check(s)


# -- hideaway: 607.3, 113.7a -----------------------------------------------------------------------------------------------------------------------------
def resolve_answering_first(s):
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("still resolving")


def test_a_copied_hideaway_trigger_hides_two_cards_and_both_are_played(hidden):
    s = build(hidden, ("Mosswort Bridge", "Strionic Resonator", *PROBES, *BIG, "Trick Probe", "Cub Probe", "Exploration"))
    resonator = put9(s, "Strionic Resonator", "battlefield")
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")  # (stop with the hideaway trigger on the stack)
    stack_top(s, *PROBES, "Trick Probe", "Cub Probe", "Exploration")
    bridge = play_land(s, "Mosswort Bridge")
    trigger = next(c for c, e in s.state.rules.stack.items() if e.kind == "trigger")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=resonator.id, ability=0, targets=[trigger])  # a copy: linked to the land too (607.3)
    resolve_answering_first(s)  # each exiles the first card it looked at: Trick Probe (the copy), then Grizzly Probe
    trick, grizzly = card_named(s, "Trick Probe"), card_named(s, "Grizzly Probe")
    assert trick.zone == grizzly.zone == "p1:exile" and trick.face_down and grizzly.face_down
    assert len(s.state.rules.exiled_with[s.state.rules.object_id(bridge.id)]) == 2
    private(s, [trick, grizzly])
    creatures(s, *BIG)
    activate(s, bridge, {"G": 1}, 3)
    d = decision(s)
    assert sorted(o.label for o in d.options) == ["Grizzly Probe", "Trick Probe"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[grizzly.id])
    d = decision(s)  # Grizzly Probe is cast (608.2g: on the stack above the ability); the same instruction offers the other one
    assert [o.label for o in d.options] == ["Trick Probe"] and card_named(s, "Grizzly Probe").zone == "stack"
    private(s, [trick])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[trick.id])
    resolve_answering_first(s)
    assert card_named(s, "Grizzly Probe").zone == "p1:battlefield" and card_named(s, "Trick Probe").zone == "p1:graveyard"
    assert s.state.rules.hideaway == {} and s.state.rules.decision is None and not s.state.zones.get("stack")
    check(s)


def test_one_hidden_card_is_played_with_no_second_question(hidden):
    s = build(hidden, ("Mosswort Bridge", *PROBES, *BIG))
    bridge, exiled = hideaway(s, "Mosswort Bridge", PROBES, "Grizzly Probe")
    creatures(s, *BIG)
    activate(s, bridge, {"G": 1}, 3)
    d = decision(s)
    assert [o.label for o in d.options] == ["Grizzly Probe"] and "one at a time" not in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    pass_until_stack_empty(s)
    assert card_named(s, "Grizzly Probe").zone == "p1:battlefield" and s.state.rules.decision is None
    assert not any("nothing to cast" in str(x) for x in s.view("p1")["log"])
    check(s)


def test_the_land_left_with_its_ability_on_the_stack_and_the_card_is_still_played(hidden):
    s = build(hidden, ("Mosswort Bridge", *PROBES, *BIG))
    bridge, exiled = hideaway(s, "Mosswort Bridge", PROBES, "Quiet Probe")
    creatures(s, *BIG)
    act(s, "p1", type="tap", card_ids=[bridge.id], tapped=False)
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=bridge.id, ability=3)
    act(s, "p1", type="move", card_ids=[bridge.id], to={"zone": "graveyard"})  # in response: the land is gone
    pass_until_stack_empty(s)
    d = decision(s)  # 113.7a: the ability exists independently of its source; 607.2a: "the exiled card" is still the one it hid
    assert d.player == "p1" and [o.label for o in d.options] == ["Quiet Probe"]
    private(s, [exiled], viewers=("p2", SPECTATOR))
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    pass_until_stack_empty(s)
    assert card_named(s, "Quiet Probe").zone == "p1:graveyard"
    check(s)
