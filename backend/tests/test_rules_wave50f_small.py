"""Wave 50F: sole-line commanders (CR 2026-09-25), real Oracle text (tests/fixtures/wave50f_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 118.12, 603.12: "you may have her deal 2 damage to you. When you do, she deals 4 damage to target creature." (Elektra, Femme Fatale) - the damage
  to yourself is the optional cost (paid by the source), the reflexive ability follows only if it was paid.
* 603.12, 115.1, 601.2c: "you may exile it. When you do, for each opponent, exile up to one target creature that player controls." (The Balrog of
  Moria), "you may pay {2}. When you do, for each opponent, destroy up to one target …" (Lich's Relic) - the reflexive ability has a target group per opponent.
* 608.2c: "target creature gets +1/+0 until end of turn for each creature you control and can't be blocked this turn." (Invisible Woman) and
  "destroy target nonbasic land defending player controls, and creatures that player controls without flying can't block this turn." (The Motherlode):
  two instructions, the second about the same target / the defending player.
* 603.3d, 115.1, 601.2c: one group of targets for each player (Nils, Discipline Enforcer: the controller too) or opponent (Tasha, the Witch Queen;
  Sepulchral Primordial: a card in that opponent's graveyard); a sentence before it ("Draw a card.") is carried out once, not once per opponent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, attack, next_turn, stops, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50f_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50f", number=f"F{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["The Balrog of Moria", "Elektra, Femme Fatale", "Invisible Woman", "The Motherlode, Excavator", "Lich's Relic", "Tasha, the Witch Queen", "Sepulchral Primordial", "Sorin, Vengeful Bloodlord", "Chainer, Dementia Master", "Spider-Man, To the Rescue", "Ian the Reckless", "Tekuthal, Inquiry Dominus"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def settle(s, answer="yes", target=None, limit=60):
    """Resolve everything: an optional ability is answered ``answer``, a target choice picks the option named ``target``, any other choice its first option."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [o.id for o in d.options if o.label == target]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[answer] if answer in ids else want or ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast_from_hand(s, name, **m):
    to_hand(s, name)
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=card_named(s, name).id)


def murder_own(s, victim):
    to_hand(s, "Murder")
    mana(s, B=2, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[victim.id])


def test_elektra_hurts_herself_to_deal_four(cards):
    s = build(cards, ["Elektra, Femme Fatale"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    cast_from_hand(s, "Elektra, Femme Fatale", R=1, G=3)
    settle(s, answer="pay", target="Grizzly Bears")
    assert life(s) == 38 and s.state.cards[bears.id].zone == "p2:graveyard"
    check(s)


def test_elektra_declined_deals_nothing(cards):
    s = build(cards, ["Elektra, Femme Fatale"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    cast_from_hand(s, "Elektra, Femme Fatale", R=1, G=3)
    settle(s, answer="decline", target="Grizzly Bears")
    assert life(s) == 40 and s.state.cards[bears.id].zone == "p2:battlefield"
    check(s)


def test_balrog_exiles_the_opponents_creature_when_it_exiles_itself(cards):
    s = build(cards, ["The Balrog of Moria", "Murder"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    murder_own(s, put(s, "The Balrog of Moria"))
    settle(s, answer="yes")
    assert zone_of(s, "The Balrog of Moria") == "p1:exile" and s.state.cards[bears.id].zone == "p2:exile"
    check(s)


def test_balrog_declined_stays_in_the_graveyard_and_exiles_nothing(cards):
    s = build(cards, ["The Balrog of Moria", "Murder"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    murder_own(s, put(s, "The Balrog of Moria"))
    settle(s, answer="no")
    assert zone_of(s, "The Balrog of Moria") == "p1:graveyard" and s.state.cards[bears.id].zone == "p2:battlefield"
    check(s)


def test_lich_relic_pays_two_then_destroys_one_target_per_opponent(cards):
    s = build(cards, ["Lich's Relic"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    cast_from_hand(s, "Lich's Relic", B=1, G=2)
    settle(s, answer="pay")
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    check(s)


def to_blockers(s, limit=40):
    """Pass priority until Bob is asked to declare blockers."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            return d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no blockers asked")


def test_invisible_woman_pumps_and_makes_the_target_unblockable(cards):
    s = build(cards, ["Invisible Woman", "Grizzly Bears"], ["Grizzly Bears"])
    stops(s)
    woman = put(s, "Invisible Woman")
    put(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", "p2")
    next_turn(s)
    attack(s, woman)
    mana(s, R=1, G=1, W=1, U=1)
    settle(s, answer="pay", target="Invisible Woman")
    assert pt(s, "Invisible Woman") == (5, 3)  # +1/+0 for each of the two creatures Alice controls
    to_blockers(s)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": woman.id}])
    check(s)


def test_invisible_woman_unpaid_changes_nothing(cards):
    s = build(cards, ["Invisible Woman"], ["Grizzly Bears"])
    stops(s)
    woman = put(s, "Invisible Woman")
    theirs = put(s, "Grizzly Bears", "p2")
    next_turn(s)
    attack(s, woman)
    settle(s, answer="decline")
    assert pt(s, "Invisible Woman") == (3, 3)
    to_blockers(s)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": woman.id}])  # nothing stops the block
    check(s)


def test_motherlode_destroys_a_nonbasic_land_and_stops_blockers_without_flying(cards):
    s = build(cards, ["The Motherlode, Excavator"], ["Grizzly Bears", "Command Tower"])
    stops(s)
    lode = put(s, "The Motherlode, Excavator")
    theirs = put(s, "Grizzly Bears", "p2")
    tower = put(s, "Command Tower", "p2")
    next_turn(s)
    act(s, "p1", type="resource", player="p1", key="energy", delta=4)
    attack(s, lode)
    settle(s, answer="pay", target="Command Tower")
    assert s.state.cards[tower.id].zone == "p2:graveyard"
    to_blockers(s)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": lode.id}])
    check(s)


def test_motherlode_without_energy_leaves_the_land_and_the_blockers(cards):
    s = build(cards, ["The Motherlode, Excavator"], ["Grizzly Bears", "Command Tower"])
    stops(s)
    lode = put(s, "The Motherlode, Excavator")
    theirs = put(s, "Grizzly Bears", "p2")
    tower = put(s, "Command Tower", "p2")
    next_turn(s)
    attack(s, lode)
    settle(s, answer="pay")
    assert s.state.cards[tower.id].zone == "p2:battlefield"
    to_blockers(s)
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": lode.id}])
    check(s)


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def test_tasha_draws_once_then_exiles_an_instant_from_the_opponents_graveyard(cards):
    s = build(cards, ["Tasha, the Witch Queen"], ["Lightning Bolt", "Grizzly Bears"])
    tasha = put(s, "Tasha, the Witch Queen")
    bolt = card_named(s, "Lightning Bolt", "p2")
    bears = card_named(s, "Grizzly Bears", "p2")
    for c in (bolt, bears):
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    before = hand(s)
    activate(s, "p1", tasha, "+1")
    settle(s, target="Lightning Bolt")
    assert hand(s) == before + 1 and s.state.cards[bolt.id].zone == "p2:exile" and s.state.cards[bears.id].zone == "p2:graveyard"
    assert s.state.cards[bolt.id].counters.get("page") == 1
    check(s)


def test_tasha_with_no_instant_or_sorcery_still_draws(cards):
    s = build(cards, ["Tasha, the Witch Queen"], ["Grizzly Bears"])
    tasha = put(s, "Tasha, the Witch Queen")
    bears = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    before = hand(s)
    activate(s, "p1", tasha, "+1")
    settle(s)
    assert hand(s) == before + 1 and s.state.cards[bears.id].zone == "p2:graveyard"
    check(s)


def test_nils_puts_a_counter_on_a_creature_of_each_player_including_its_controller(cards):
    s = build(cards, ["Nils, Discipline Enforcer", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Nils, Discipline Enforcer")
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", "p2")
    to_phase(s, "end")
    settle(s, target="Grizzly Bears")
    assert s.state.cards[mine.id].counters.get("+1/+1") == 1 and s.state.cards[theirs.id].counters.get("+1/+1") == 1
    check(s)


def test_sepulchral_primordial_takes_a_creature_from_the_opponents_graveyard(cards):
    s = build(cards, ["Sepulchral Primordial"], ["Grizzly Bears"])
    bears = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    cast_from_hand(s, "Sepulchral Primordial", B=2, G=5)
    settle(s, answer="yes", target="Grizzly Bears")
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def chars(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def test_sorin_minus_x_returns_a_creature_with_exactly_that_mana_value_as_a_vampire(cards):
    s = build(cards, ["Sorin, Vengeful Bloodlord", "Grizzly Bears", "Kitchen Finks"], [])
    sorin = put(s, "Sorin, Vengeful Bloodlord")
    act(s, "p1", type="counter", card_ids=[sorin.id], kind="loyalty", delta=4)  # (put there by hand: no loyalty of its own)
    bears = card_named(s, "Grizzly Bears")
    finks = card_named(s, "Kitchen Finks")
    for c in (bears, finks):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    activate(s, "p1", sorin, "−X", x_value=2, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[finks.id].zone == "p1:graveyard"
    assert "Vampire" in chars(s, s.state.cards[bears.id]).subtypes and s.state.cards[sorin.id].counters.get("loyalty") == 2
    check(s)


def test_sorin_minus_x_refuses_a_creature_of_another_mana_value(cards):
    s = build(cards, ["Sorin, Vengeful Bloodlord", "Kitchen Finks"], [])
    sorin = put(s, "Sorin, Vengeful Bloodlord")
    act(s, "p1", type="counter", card_ids=[sorin.id], kind="loyalty", delta=4)  # (put there by hand: no loyalty of its own)
    finks = card_named(s, "Kitchen Finks")
    act(s, "p1", type="move", card_ids=[finks.id], to={"zone": "graveyard"})
    with pytest.raises(ActionError):
        activate(s, "p1", sorin, "−X", x_value=2, targets=[finks.id])


def test_chainer_returns_a_creature_black_and_a_nightmare(cards):
    s = build(cards, ["Chainer, Dementia Master"], ["Grizzly Bears"])
    chainer = put(s, "Chainer, Dementia Master")
    bears = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    mana(s, B=3)
    activate(s, "p1", chainer, "Pay 3 life", targets=[bears.id])
    settle(s)
    got = s.state.cards[bears.id]
    assert got.zone == "p1:battlefield" and life(s) == 37
    c = chars(s, got)
    assert list(c.colors) == ["B"] and "Nightmare" in c.subtypes and "Bear" in c.subtypes  # black only (105.3), a Nightmare in addition (205.1b)
    check(s)


def test_demonic_junker_destroys_one_creature_per_player_and_grows_only_if_one_of_its_controllers_died(cards):
    s = build(cards, ["Demonic Junker", "Grizzly Bears"], ["Grizzly Bears"])
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", "p2")
    cast_from_hand(s, "Demonic Junker", B=1, G=6)
    settle(s)  # the first option of each group: the Bears of Alice, then Bob's
    assert s.state.cards[mine.id].zone == "p1:graveyard" and s.state.cards[theirs.id].zone == "p2:graveyard"
    assert s.state.cards[card_named(s, "Demonic Junker").id].counters.get("+1/+1") == 2
    check(s)


def test_battle_at_the_helvault_exiles_a_permanent_of_each_player(cards):
    s = build(cards, ["Battle at the Helvault", "Grizzly Bears"], ["Grizzly Bears"])
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", "p2")
    cast_from_hand(s, "Battle at the Helvault", W=2, G=4)
    settle(s, target="Grizzly Bears")
    assert s.state.cards[mine.id].zone == "p1:exile" and s.state.cards[theirs.id].zone == "p2:exile"
    check(s)


def test_spider_man_taps_himself_to_make_another_nonattacking_creature_indestructible(cards):
    s = build(cards, ["Spider-Man, To the Rescue", "Grizzly Bears"], [])
    bears = put(s, "Grizzly Bears")
    cast_from_hand(s, "Spider-Man, To the Rescue", G=3)
    settle(s, answer="yes")
    spidey = card_named(s, "Spider-Man, To the Rescue")
    assert s.state.cards[spidey.id].tapped and "indestructible" in chars(s, s.state.cards[bears.id]).keywords
    assert "indestructible" not in chars(s, s.state.cards[spidey.id]).keywords  # "another"
    check(s)


def test_spider_man_declined_stays_untapped_and_gives_nothing(cards):
    s = build(cards, ["Spider-Man, To the Rescue", "Grizzly Bears"], [])
    bears = put(s, "Grizzly Bears")
    cast_from_hand(s, "Spider-Man, To the Rescue", G=3)
    settle(s, answer="no")
    assert not s.state.cards[card_named(s, "Spider-Man, To the Rescue").id].tapped
    assert "indestructible" not in chars(s, s.state.cards[bears.id]).keywords
    check(s)


def test_ian_modified_deals_his_power_to_you_and_to_any_target(cards):
    s = build(cards, ["Ian the Reckless"], [])
    stops(s)
    ian = put(s, "Ian the Reckless")
    act(s, "p1", type="counter", card_ids=[ian.id], kind="+1/+1", delta=1)  # modified (700.9): power 3
    next_turn(s)
    attack(s, ian)
    settle(s, answer="yes", target="Bob")
    assert life(s) == 37 and life(s, "p2") == 37
    check(s)


def test_ian_not_modified_does_not_trigger(cards):
    s = build(cards, ["Ian the Reckless"], [])
    stops(s)
    ian = put(s, "Ian the Reckless")
    next_turn(s)
    attack(s, ian)
    assert not s.state.zones.get("stack") and s.state.rules.decision is None
    assert life(s) == 40 and life(s, "p2") == 40
    check(s)


def test_tekuthal_makes_one_proliferate_two(cards):
    s = build(cards, ["Tekuthal, Inquiry Dominus", "Steady Progress", "Grizzly Bears"], [])
    put(s, "Tekuthal, Inquiry Dominus")
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    before = hand(s)
    cast_from_hand(s, "Steady Progress", U=1, G=2)
    settle(s)  # each proliferate chooses the Bears (the only permanent with a counter)
    assert s.state.cards[bears.id].counters.get("+1/+1") == 3 and hand(s) == before + 1  # 701.34a twice (614.1a); the draw is no proliferate
    check(s)


def test_one_proliferate_without_tekuthal(cards):
    s = build(cards, ["Steady Progress", "Grizzly Bears"], [])
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    cast_from_hand(s, "Steady Progress", U=1, G=2)
    settle(s)
    assert s.state.cards[bears.id].counters.get("+1/+1") == 2
    check(s)


def test_demonic_junker_destroying_only_the_opponents_creature_adds_no_counters(cards):
    s = build(cards, ["Demonic Junker"], ["Grizzly Bears"])
    theirs = put(s, "Grizzly Bears", "p2")
    cast_from_hand(s, "Demonic Junker", B=1, G=6)
    settle(s)
    assert s.state.cards[theirs.id].zone == "p2:graveyard"
    assert not s.state.cards[card_named(s, "Demonic Junker").id].counters.get("+1/+1")
    check(s)
