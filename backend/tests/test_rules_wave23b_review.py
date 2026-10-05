"""Review 23B: abilities on the stack and delayed triggers, probed beyond the wave's own scenarios (CR 2026-09-25).

* 603.7e: a delayed trigger a mana ability creates (Barbed Sextant, Astrolabe) is controlled by whoever activated it — not the
  card's owner, who controls it again once it was sacrificed as the cost (fixed).
* Trickbind's lock covers the source's mana abilities too (Trickbind ruling); Tishana's Tidebinder strips nothing from a land, or
  once it left before its trigger resolved (its rulings, 611.2b); Interdict's "from an artifact, creature, enchantment, or land" is a
  permanent (109.2): an ability of a card in a graveyard isn't a legal target, and Trickbind locks nothing then.
* 707.10 / 606.3: a copy of a loyalty ability (Ertha Jo) adds no loyalty and isn't an activation (Rowan's Talent ruling).
* Illusionist's Bracers: an ability whose cost sacrificed the equipped creature isn't copied (its ruling).
* The Pacts: two in one upkeep (the second unpaid loses), paid by tapping lands as the trigger resolves, cast in that upkeep (waits
  for the next one), and none when the Pact doesn't resolve (its ruling). Celestial Sword: a new object isn't sacrificed (603.7c);
  a new controller sacrifices it (701.21a).
Real Oracle text; replay and save/load round trips.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from tests import test_rules_wave23b_delayed as D
from tests import test_rules_wave23b_stack as W
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_suspend import until
from tests.test_rules_wave9b_exile_permission import answer, build, put, roundtrip

EXTRA = [
    card('Slaughter Pact', set_code='tst', number='V01', mana_cost='{0}', cmc=0.0, type_line='Instant', oracle_text="Destroy target nonblack creature.\nAt the beginning of your next upkeep, pay {2}{B}. If you don't, you lose the game.", colors=['B'], color_identity=['B']),  # noqa: E501
    card("Summoner's Pact", set_code='tst', number='V02', mana_cost='{0}', cmc=0.0, type_line='Instant', oracle_text="Search your library for a green creature card, reveal it, put it into your hand, then shuffle.\nAt the beginning of your next upkeep, pay {2}{G}{G}. If you don't, you lose the game.", colors=['G'], color_identity=['G']),  # noqa: E501
    card('Probe Dork Gun', set_code='tst', number='V11', mana_cost='{1}', cmc=1.0, type_line='Creature — Elf', oracle_text='Haste\n{T}: Add {G}.\n{1}: Probe Dork Gun deals 1 damage to any target.', power='1', toughness='1', keywords=['Haste']),  # noqa: E501
    card('Probe Gun Land', set_code='tst', number='V12', type_line='Land', oracle_text='{1}: Probe Gun Land deals 1 damage to any target.'),  # noqa: E501
    card('Probe Returner', set_code='tst', number='V13', mana_cost='{1}', cmc=1.0, type_line='Creature — Elf', oracle_text='{1}: Return this card from your graveyard to your hand.', power='1', toughness='1'),  # noqa: E501
    card('Probe Walker', set_code='tst', number='V14', mana_cost='{3}', cmc=3.0, type_line='Legendary Planeswalker — Test', loyalty='3', oracle_text='+1: Probe Walker deals 1 damage to any target.\n−1: You gain 1 life.'),  # noqa: E501
    card('Probe Kamikaze', set_code='tst', number='V15', mana_cost='{1}', cmc=1.0, type_line='Creature — Elf', oracle_text='Sacrifice this creature: It deals 1 damage to any target.', power='1', toughness='1'),  # noqa: E501
    card('Probe Loyal Watch', set_code='tst', number='V16', mana_cost='{1}', cmc=1.0, type_line='Enchantment', oracle_text='Whenever you activate a loyalty ability, you gain 5 life.'),  # noqa: E501
]
ALL = W.EXTRA + [c for c in D.EXTRA if c["name"] not in {x["name"] for x in W.EXTRA}] + EXTRA


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + ALL, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def st(s):
    return list(s.state.zones.get("stack", []))


def life(s, p):
    return s.state.players[p].life


def _upkeep(s, pid, turn=None):
    until(s, lambda s: s.state.rules.decision is not None or (s.state.turn.phase == "upkeep" and s.state.turn.active_player == pid
                                                              and (turn is None or s.state.turn.number == turn)), limit=200)


def test_trickbind_stops_the_mana_ability_too(cards):
    s = build(cards, p1=("Probe Dork Gun",), p2=("Trickbind",))
    W.prefs(s)
    g = put(s, "Probe Dork Gun", "battlefield")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=g.id, ability=2, targets=["p2"])
    (ab,) = st(s)
    W.cast_at(s, "Trickbind", ab, U=1, C=1)
    answer(s)
    assert life(s, "p2") == 40
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=g.id, ability=1)
    roundtrip(s)


def test_tidebinder_land_keeps_abilities(cards):
    s = build(cards, p1=("Probe Gun Land",), p2=("Tishana's Tidebinder",))
    W.prefs(s)
    land = put(s, "Probe Gun Land", "battlefield")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=land.id, ability=0, targets=["p2"])
    (ab,) = st(s)
    W.enter_and_aim(s, "Tishana's Tidebinder", ab, U=1, C=2)
    answer(s)
    assert life(s, "p2") == 40
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=land.id, ability=0, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 39
    roundtrip(s)


def test_tidebinder_leaves_before_resolution(cards):
    s, rod, ab = W.activate_rod(cards, "Tishana's Tidebinder")
    binder = W.enter_and_aim(s, "Tishana's Tidebinder", ab, U=1, C=2)
    act(s, "p2", type="move", card_ids=[binder.id], to={"player": "p2", "zone": "graveyard"})
    answer(s)
    assert life(s, "p2") == 40
    from app.rules import characteristics as chars
    from app.rules.layers import derive
    c = s.state.cards[rod.id]
    assert [a for a in derive(s.state, c, chars.of(c, s.cards), s.cards).abilities if a.kind == "activated"]
    roundtrip(s)


def test_interdict_cant_target_graveyard_card_ability(cards):
    s = build(cards, p1=("Probe Returner",), p2=("Interdict",))
    W.prefs(s)
    r = put(s, "Probe Returner", "graveyard")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=r.id, ability=0)
    (ab,) = st(s)
    card_ = put(s, "Interdict", "hand", "p2")
    mana(s, "p2", U=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=card_.id, targets=[ab])


def test_ertha_copies_loyalty_ability(cards):
    s = build(cards, p1=("Ertha Jo, Frontier Mentor", "Probe Walker", "Probe Loyal Watch"))
    put(s, "Ertha Jo, Frontier Mentor", "battlefield")
    put(s, "Probe Loyal Watch", "battlefield")
    w = put(s, "Probe Walker", "battlefield")
    act(s, "p1", type="set_counter", card_id=w.id, kind="loyalty", value=3)
    lo = s.state.cards[w.id].counters.get("loyalty")
    l1 = life(s, "p1")
    act(s, "p1", type="activate_ability", card_id=w.id, ability=0, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 38
    assert s.state.cards[w.id].counters.get("loyalty") == lo + 1
    assert life(s, "p1") == l1 + 5  # watch triggers once (copy isn't activated, 707.10)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=w.id, ability=1)
    roundtrip(s)


def test_bracers_sacrificed_creature_not_copied(cards):
    s = build(cards, p1=("Illusionist's Bracers", "Probe Kamikaze"))
    gear = put(s, "Illusionist's Bracers", "battlefield")
    k = put(s, "Probe Kamikaze", "battlefield")
    W._equip(s, gear, k)
    act(s, "p1", type="activate_ability", card_id=k.id, ability=0, targets=["p2"])
    answer(s)
    assert life(s, "p2") == 39
    roundtrip(s)


def test_pawpatch_offers_only_others(cards):
    s = build(cards, p1=("Pawpatch Recruit", "Test Ox", "Test Fodder"), p2=("Lightning Bolt",))
    W.prefs(s)
    rec = put(s, "Pawpatch Recruit", "battlefield")
    ox = put(s, "Test Ox", "battlefield")
    fod = put(s, "Test Fodder", "battlefield")
    W.p2_priority(s)
    W.bolt(s, ox.id)
    seen = []
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            seen.append({o.card_id or o.id for o in d.options})
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if (o.card_id or o.id) == fod.id)])
        elif st(s):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert seen and all(ox.id not in x for x in seen), seen
    assert s.state.cards[fod.id].counters.get("+1/+1") == 1 and not s.state.cards[rec.id].counters
    roundtrip(s)


def test_two_pacts_one_upkeep(cards):
    s = build(cards, p1=("Slaughter Pact", "Pact of the Titan"), p2=("Test Ox",))
    W.prefs(s)
    ox = put(s, "Test Ox", "battlefield", "p2")
    a = put(s, "Slaughter Pact", "hand")
    act(s, "p1", type="cast_spell", card_id=a.id, targets=[ox.id])
    pass_until_stack_empty(s)
    b = put(s, "Pact of the Titan", "hand")
    act(s, "p1", type="cast_spell", card_id=b.id)
    pass_until_stack_empty(s)
    assert s.state.cards[ox.id].zone.endswith("graveyard") and len(s.state.rules.delayed) == 2
    roundtrip(s)
    _upkeep(s, "p1", 3)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
    assert len(st(s)) == 2
    mana(s, B=1, C=2)  # enough for the Slaughter Pact only
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay" if "pay" in ids else ids[0]])
        elif st(s):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert "p1" in s.state.rules.lost, s.state.players["p1"].mana
    roundtrip(s)


def test_pact_paid_with_untapped_lands(cards):
    s = build(cards, p1=("Summoner's Pact",))
    W.prefs(s)
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:4]
    act(s, "p1", type="move", card_ids=[f.id for f in forests], to={"player": "p1", "zone": "battlefield"})
    a = put(s, "Summoner's Pact", "hand")
    act(s, "p1", type="cast_spell", card_id=a.id)
    answer(s)
    _upkeep(s, "p1", 3)
    seen = []
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            seen.append((d.kind, [o.id for o in d.options]))
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay"] if any(o.id == "pay" for o in d.options) else [o.id for o in d.options][:d.min_choices])
        elif st(s):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert "p1" not in s.state.rules.lost, seen
    assert any("pay" in o for _, o in seen), seen
    assert all(s.state.cards[f.id].tapped for f in forests)
    roundtrip(s)


def test_pact_cast_in_upkeep_waits(cards):
    s = build(cards, p1=("Pact of the Titan",))
    W.prefs(s)
    _upkeep(s, "p1", 3)
    assert s.state.turn.number == 3 and s.state.rules.priority == "p1"
    b = put(s, "Pact of the Titan", "hand")
    act(s, "p1", type="cast_spell", card_id=b.id)
    pass_until_stack_empty(s)
    until(s, lambda s: s.state.turn.number == 4, limit=200)
    assert "p1" not in s.state.rules.lost and len(s.state.rules.delayed) == 1
    roundtrip(s)


def test_pact_fizzles_no_trigger(cards):
    s = build(cards, p1=("Slaughter Pact",), p2=("Test Ox",))
    W.prefs(s)
    ox = put(s, "Test Ox", "battlefield", "p2")
    a = put(s, "Slaughter Pact", "hand")
    act(s, "p1", type="cast_spell", card_id=a.id, targets=[ox.id])
    act(s, "p2", type="move", card_ids=[ox.id], to={"player": "p2", "zone": "hand"})
    pass_until_stack_empty(s)
    assert not s.state.rules.delayed
    roundtrip(s)


@pytest.mark.parametrize("how", ["blink", "steal"])
def test_celestial_sword_new_object_or_new_controller(cards, how):
    s = build(cards, p1=("Celestial Sword", "Test Ox"))
    sword = put(s, "Celestial Sword", "battlefield")
    ox = put(s, "Test Ox", "battlefield")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=sword.id, ability=0, targets=[ox.id])
    pass_until_stack_empty(s)
    if how == "blink":
        act(s, "p1", type="move", card_ids=[ox.id], to={"player": "p1", "zone": "hand"})
        act(s, "p1", type="move", card_ids=[ox.id], to={"player": "p1", "zone": "battlefield"})
    else:
        act(s, "p1", type="set_controller", card_ids=[ox.id], player="p2")
    W.prefs(s)
    until(s, lambda s: s.state.turn.number > 1 or not s.state.rules.delayed, limit=200)
    pass_until_stack_empty(s)
    if how == "blink":
        assert s.state.cards[ox.id].zone == "p1:battlefield"
    else:
        assert s.state.cards[ox.id].zone == "p1:graveyard"
    roundtrip(s)


def test_stolen_sextant_draws_for_the_activator(cards):
    s = build(cards, p1=("Barbed Sextant",))
    sx = put(s, "Barbed Sextant", "battlefield")
    W.prefs(s)
    W.p2_priority(s)
    act(s, "p1", type="set_controller", card_ids=[sx.id], player="p2")
    mana(s, "p2", C=1)
    act(s, "p2", type="activate_ability", card_id=sx.id, ability=0)
    d = s.state.rules.decision
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert s.state.cards[sx.id].zone == "p1:graveyard"
    (t,) = s.state.rules.delayed
    assert t.controller == "p2"
    roundtrip(s)
