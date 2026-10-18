"""Activation costs made of parts other than mana (CR 118, 602.2b → 601.2h) and kicker (702.33).

118.3: a cost that can't be paid fully can't be paid (the activation is refused and the table is
exactly as it was); 601.2h: all parts are paid at once, no partial payments; 107.6: {Q} untaps
the source; 701.21a sacrifice, 701.9a discard; 113.6m: "Exile this card from your graveyard"
works only from the graveyard. Kicker: an additional cost (118.8, 601.2b/f) that doesn't change
mana value (118.8d); "if it was kicked" (702.33d-e); multikicker (702.33c); a copy keeps it
(707.10). Every scenario checks that replaying the history reproduces the table."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.characteristics import Characteristics
from app.rules.costs import SACRIFICE, TAP_OTHER, kicker_line, parse_ability_cost
from app.rules.oracle import parse_abilities
from app.rules.scripts import parse_effects
from tests.game_helpers import act, zone
from tests.test_rules_attachments import build, named, to_hand, token
from tests.test_rules_effects import pass_until_stack_empty, replay_matches


def artifact(s, name, text, pid="p1"):
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Artifact — Test", "text": text})
    return named(s, name)


def mana(s, pid="p1", **m):
    act(s, pid, type="add_mana", player=pid, mana=m)


def use(s, card, **kw):
    act(s, "p1", type="activate_ability", card_id=card.id, ability=kw.pop("ability", 0), **kw)
    pass_until_stack_empty(s)


def refused(s, match, **payload):
    """The action is refused and nothing at all changed (118.3, 601.2h: no partial payments)."""
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match=match):
        act(s, "p1", **payload)
    assert s.state.model_dump(mode="json") == before


def decision(s):
    return s.state.rules.decision


def choose(s, ids, pid="p1"):
    act(s, pid, type="choose", decision_id=decision(s).id, option_ids=list(ids))
    pass_until_stack_empty(s)


def life(s, pid="p1"):
    return s.state.players[pid].life


# -- parsing --------------------------------------------------------------------------------
def test_parse_components():
    cost = parse_ability_cost("{10}, Sacrifice another creature, Tap two untapped Elves you control")
    assert cost.mana == "{10}" and not cost.unsupported
    kinds = [c.kind for c in cost.components]
    assert kinds == ["MANA", SACRIFICE, TAP_OTHER]
    assert '"other":true' in (cost.components[1].selector or "") and cost.components[2].amount == 2
    assert parse_ability_cost("{Q}").untap
    assert parse_ability_cost("{S}").unsupported == () and parse_ability_cost("{S}").mana == "{S}"  # snow mana: wave 7E
    # (wave 4J: the source's chosen creature type, read by selectors.matches from the permanent's enters choice)
    assert '"chosen_type"' in (parse_ability_cost("Sacrifice a creature of the chosen type").components[0].selector or "")
    assert parse_ability_cost("Exile Test Relic from your graveyard", card_name="Test Relic").from_graveyard
    assert kicker_line("Kicker {2}{W}") and kicker_line("Multikicker {1}")
    assert kicker_line("Kicker {1}{U} and/or {2}{B}") and kicker_line("Kicker—Sacrifice a land")  # (wave 43D: paid with the additional costs; wave 50H: 702.33b, two mana kicker costs)
    assert not kicker_line("Kicker {X} and/or {2}{B}")  # (wave 50H: an {X} in either of the two costs is still refused)
    # (a token's creature types are the capitalized words: an enchantment artifact creature Golem, not a "Golem enchantment")
    parsed = parse_effects("Create a 3/3 colorless Golem enchantment artifact creature token.")
    assert parsed is not None and parsed[0][0]["token"]["type_line"] == "Token Enchantment Artifact Creature — Golem"


# -- sacrifice --------------------------------------------------------------------------------
def test_sacrifice_a_creature_is_chosen_privately(cards):
    s = build(cards)
    altar = artifact(s, "Altar", "{1}, Sacrifice a creature: You gain 3 life.")
    bear, wolf = token(s, "p1", "Bear"), token(s, "p1", "Wolf")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=altar.id, ability=0)
    d = decision(s)
    assert d.player == "p1" and d.kind == "choose_cards" and {o.id for o in d.options} == {bear.id, wolf.id}
    assert "options" not in s.view("p2")["rules"]["decision"]
    assert s.state.players["p1"].mana.get("C") == 1  # nothing paid yet
    choose(s, [bear.id])
    assert bear.id not in s.state.cards and wolf.id in s.state.cards and life(s) == 43
    replay_matches(s)


def test_sacrifice_choice_given_up_front(cards):
    s = build(cards)
    altar = artifact(s, "Altar", "{1}, Sacrifice a creature: You gain 3 life.")
    bear, wolf = token(s, "p1", "Bear"), token(s, "p1", "Wolf")
    mana(s, C=1)
    refused(s, "Choose 1", type="activate_ability", card_id=altar.id, ability=0,
            cost_choices=[{"component": 1, "cards": [bear.id, wolf.id]}])
    refused(s, "no such part", type="activate_ability", card_id=altar.id, ability=0,
            cost_choices=[{"component": 0, "cards": [bear.id]}])
    use(s, altar, cost_choices=[{"component": 1, "cards": [wolf.id]}])
    assert wolf.id not in s.state.cards and bear.id in s.state.cards and life(s) == 43
    replay_matches(s)


def test_cancelling_the_choice_pays_nothing(cards):
    s = build(cards)
    altar = artifact(s, "Altar", "{1}, Sacrifice a creature: You gain 3 life.")
    token(s, "p1", "Bear"), token(s, "p1", "Wolf")
    mana(s, C=1)
    before = s.state.model_dump(mode="json")["cards"]
    act(s, "p1", type="activate_ability", card_id=altar.id, ability=0)
    choose(s, [])
    assert decision(s) is None and s.state.model_dump(mode="json")["cards"] == before
    assert s.state.players["p1"].mana.get("C") == 1 and s.state.rules.priority == "p1"
    replay_matches(s)


def test_unpayable_sacrifice_is_refused_and_changes_nothing(cards):
    s = build(cards)
    altar = artifact(s, "Altar", "{1}, Sacrifice a creature: You gain 3 life.")
    mana(s, C=1)
    token(s, "p2", "Their Bear")  # (not yours: 701.21a)
    refused(s, "can't pay", type="activate_ability", card_id=altar.id, ability=0)


def test_sacrifice_another_never_takes_the_source(cards):
    s = build(cards)
    priest = token(s, "p1", "Priest", text="Sacrifice another creature: You gain 2 life.")
    refused(s, "can't pay", type="activate_ability", card_id=priest.id, ability=0)
    bear = token(s, "p1", "Bear")
    refused(s, "Choose 1", type="activate_ability", card_id=priest.id, ability=0,
            cost_choices=[{"component": 0, "cards": [priest.id]}])
    use(s, priest)  # only one choice: no question
    assert bear.id not in s.state.cards and priest.id in s.state.cards and life(s) == 42
    replay_matches(s)


def test_a_sacrificed_permanent_doesnt_also_pay_mana(cards):
    s = build(cards)
    altar = artifact(s, "Altar", "{1}, Sacrifice an artifact: You gain 3 life.")
    treasure = artifact(s, "Relic", "{T}: Add {C}.")
    refused(s, "Not enough mana|can't pay|mana", type="activate_ability", card_id=altar.id, ability=0,
            cost_choices=[{"component": 1, "cards": [treasure.id]}])


# -- discard ---------------------------------------------------------------------------------
def test_discard_is_private_until_it_hits_the_graveyard(cards):
    s = build(cards, "Holy Strength", "Lightning Bolt")
    engine = artifact(s, "Engine", "Discard a card: You gain 1 life.")
    strength, bolt = to_hand(s, "Holy Strength"), to_hand(s, "Lightning Bolt")
    act(s, "p1", type="activate_ability", card_id=engine.id, ability=0)
    d = decision(s)
    assert {strength.id, bolt.id} <= {o.id for o in d.options}
    theirs = s.view("p2")["rules"]["decision"]
    assert "options" not in theirs and "Bolt" not in theirs["prompt"] and "Strength" not in theirs["prompt"]
    choose(s, [bolt.id])
    assert s.state.cards[bolt.id].zone == "p1:graveyard" and life(s) == 41
    theirs = s.view("p2")
    assert bolt.id in theirs["zones"]["p1:graveyard"] and theirs["cards"][bolt.id]["name"] == "Lightning Bolt"  # public now
    assert strength.id not in theirs["cards"]  # (still hidden in the hand)
    replay_matches(s)


def test_discard_a_land_card_needs_one(cards):
    s = build(cards, "Lightning Bolt")
    engine = artifact(s, "Engine", "Discard a land card: You gain 1 life.")
    for cid in list(zone(s.state, "p1", "hand")):
        act(s, "p1", type="move", card_ids=[cid], to={"zone": "library"})
    to_hand(s, "Lightning Bolt")
    refused(s, "can't pay", type="activate_ability", card_id=engine.id, ability=0)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})
    use(s, engine)
    assert s.state.cards[forest.id].zone == "p1:graveyard" and life(s) == 41
    replay_matches(s)


# -- exile from a graveyard ------------------------------------------------------------------
def test_exile_cards_from_your_graveyard(cards):
    s = build(cards, "Holy Strength", "Lightning Bolt")
    engine = artifact(s, "Engine", "Exile two cards from your graveyard: You gain 2 life.")
    strength, bolt = named(s, "Holy Strength"), named(s, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[strength.id], to={"zone": "graveyard"})
    refused(s, "can't pay", type="activate_ability", card_id=engine.id, ability=0)
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "graveyard"})
    use(s, engine)
    assert s.state.cards[strength.id].zone == "p1:exile" and s.state.cards[bolt.id].zone == "p1:exile"
    assert life(s) == 42
    replay_matches(s)


def test_exile_this_card_from_your_graveyard_works_only_there(cards):
    s = build(cards, "Test Ember Relic")
    relic = named(s, "Test Ember Relic")
    mana(s, C=2)
    act(s, "p1", type="move", card_ids=[relic.id], to={"zone": "battlefield"})
    refused(s, "only be activated from your graveyard", type="activate_ability", card_id=relic.id, ability=0)
    act(s, "p1", type="move", card_ids=[relic.id], to={"zone": "graveyard"})
    use(s, relic)
    assert s.state.cards[relic.id].zone == "p1:exile" and life(s) == 42
    replay_matches(s)


# -- tapping and untapping ---------------------------------------------------------------------
def test_tap_untapped_creatures_you_control(cards):
    s = build(cards)
    engine = artifact(s, "Engine", "Tap two untapped creatures you control: You gain 2 life.")
    bear = token(s, "p1", "Bear")  # (summoning sick: tapping it for a cost is fine, 302.6 is about {T})
    refused(s, "can't pay", type="activate_ability", card_id=engine.id, ability=0)
    wolf = token(s, "p1", "Wolf")
    use(s, engine)
    assert s.state.cards[bear.id].tapped and s.state.cards[wolf.id].tapped and life(s) == 42
    refused(s, "can't pay", type="activate_ability", card_id=engine.id, ability=0)  # they're tapped now
    replay_matches(s)


def test_untap_symbol(cards):
    s = build(cards)
    engine = artifact(s, "Engine", "{Q}: You gain 1 life.")
    refused(s, "isn't tapped", type="activate_ability", card_id=engine.id, ability=0)  # 107.6
    act(s, "p1", type="tap", card_ids=[engine.id], tapped=True)
    use(s, engine)
    assert not s.state.cards[engine.id].tapped and life(s) == 41
    replay_matches(s)


def test_untap_symbol_respects_summoning_sickness(cards):
    s = build(cards)
    elf = token(s, "p1", "Elf", text="{Q}: You gain 1 life.")
    act(s, "p1", type="tap", card_ids=[elf.id], tapped=True)
    refused(s, "summoning sickness", type="activate_ability", card_id=elf.id, ability=0)  # 302.6


# -- mana, counters, returning, energy ---------------------------------------------------------
def test_ten_generic_mana(cards):
    s = build(cards)
    engine = artifact(s, "Engine", "{10}: You gain 5 life.")
    mana(s, C=9)
    refused(s, "Not enough mana|mana", type="activate_ability", card_id=engine.id, ability=0)
    mana(s, C=1)
    use(s, engine)
    assert life(s) == 45 and not s.state.players["p1"].mana.get("C")
    replay_matches(s)


def test_remove_a_counter_from_a_creature_you_control(cards):
    s = build(cards)
    engine = artifact(s, "Engine", "Remove a +1/+1 counter from a creature you control: You gain 1 life.")
    bear = token(s, "p1", "Bear")
    refused(s, "can't pay", type="activate_ability", card_id=engine.id, ability=0)
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=2)
    use(s, engine)
    assert s.state.cards[bear.id].counters.get("+1/+1") == 1 and life(s) == 41
    replay_matches(s)


def test_return_a_land_you_control(cards):
    s = build(cards)
    engine = artifact(s, "Engine", "Return a land you control to its owner's hand: You gain 1 life.")
    refused(s, "can't pay", type="activate_ability", card_id=engine.id, ability=0)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone.endswith("library"))
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    use(s, engine)
    assert s.state.cards[forest.id].zone == "p1:hand" and life(s) == 41
    replay_matches(s)


def test_pay_energy(cards):
    s = build(cards)
    engine = artifact(s, "Engine", "Pay {E}{E}: You gain 1 life.")
    act(s, "p1", type="resource", player="p1", key="energy", delta=1)
    refused(s, "energy", type="activate_ability", card_id=engine.id, ability=0)
    act(s, "p1", type="resource", player="p1", key="energy", delta=1)
    use(s, engine)
    assert s.state.players["p1"].resources["energy"] == 0 and life(s) == 41
    replay_matches(s)


def test_hints_know_the_costs(cards):
    from app.rules.casting import activatable

    s = build(cards)
    altar = artifact(s, "Altar", "Sacrifice a creature: You gain 3 life.")
    hints = activatable(s.state, "p1", s.cards)
    assert {"card_id": altar.id, "ability": 0} not in hints
    token(s, "p1", "Bear")
    assert {"card_id": altar.id, "ability": 0} in activatable(s.state, "p1", s.cards)


# -- kicker (702.33) ---------------------------------------------------------------------------
def test_unkicked_spell(cards):
    s = build(cards, "Test Kicked Bolt")
    ogre = token(s, "p2", "Ogre", "5/5")
    bolt = to_hand(s, "Test Kicked Bolt")
    mana(s, R=1)
    hand = len(zone(s.state, "p1", "hand"))
    s.state.rules.prefs_for("p1").hold_priority = True  # (keep priority with it on the stack)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[ogre.id])
    assert s.state.rules.payments[s.state.rules.object_id(bolt.id)].kicked == 0
    pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].damage == 2 and len(zone(s.state, "p1", "hand")) == hand - 1  # no card drawn
    replay_matches(s)


def test_kicked_spell(cards):
    s = build(cards, "Test Kicked Bolt")
    ogre = token(s, "p2", "Ogre", "5/5")
    bolt = to_hand(s, "Test Kicked Bolt")
    hand = len(zone(s.state, "p1", "hand"))
    mana(s, R=2)
    refused(s, "Not enough mana|mana", type="cast_spell", card_id=bolt.id, targets=[ogre.id], kicker=1)
    refused(s, "only once", type="cast_spell", card_id=bolt.id, targets=[ogre.id], kicker=2)
    mana(s, C=1)
    s.state.rules.prefs_for("p1").hold_priority = True
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[ogre.id], kicker=1)
    record = s.state.rules.payments[s.state.rules.object_id(bolt.id)]
    assert record.kicked == 1 and "kicker" in record.additional and record.total_cost == "{1}{R}{R}"
    assert s.state.cards[bolt.id].stack_info.tags == ["Kicked"]
    pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].damage == 2 and len(zone(s.state, "p1", "hand")) == hand  # cast one, drew one
    replay_matches(s)


def test_kicked_instead(cards):
    s = build(cards, "Test Surge")
    bear = token(s, "p1", "Bear")
    surge = to_hand(s, "Test Surge")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=surge.id, targets=[bear.id], kicker=1)
    pass_until_stack_empty(s)
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id])
    assert ch.pt == (7, 7)  # +5/+5 instead of +2/+2 (not both)
    replay_matches(s)


def test_unkicked_instead(cards):
    s = build(cards, "Test Surge")
    bear = token(s, "p1", "Bear")
    surge = to_hand(s, "Test Surge")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=surge.id, targets=[bear.id])
    pass_until_stack_empty(s)
    from app.rules.plan import Plan

    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id]).pt == (4, 4)
    replay_matches(s)


def test_multikicker_counts(cards):
    s = build(cards, "Test Multigift")
    gift = to_hand(s, "Test Multigift")
    mana(s, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=gift.id, kicker=3)
    pass_until_stack_empty(s)
    assert life(s) == 40 + 1 + 6 and not s.state.players["p1"].mana.get("C")
    replay_matches(s)


def test_kicked_creature_enters_with_counters_and_triggers(cards):
    s = build(cards, "Test Kicker Knight")
    knight = to_hand(s, "Test Kicker Knight")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=knight.id, kicker=1)
    pass_until_stack_empty(s)
    assert s.state.cards[knight.id].zone == "p1:battlefield"
    assert s.state.cards[knight.id].counters.get("+1/+1") == 2 and life(s) == 43
    replay_matches(s)


def test_unkicked_creature_doesnt_trigger(cards):
    s = build(cards, "Test Kicker Knight")
    knight = to_hand(s, "Test Kicker Knight")
    mana(s, W=1)
    act(s, "p1", type="cast_spell", card_id=knight.id)
    pass_until_stack_empty(s)
    assert s.state.cards[knight.id].zone == "p1:battlefield"
    assert not s.state.cards[knight.id].counters.get("+1/+1") and life(s) == 40
    assert not s.state.rules.pending_triggers and not s.state.zones.get("stack")  # 603.4: it never triggered
    replay_matches(s)


def test_multikicked_creature(cards):
    s = build(cards, "Test Multikick Beast")
    beast = to_hand(s, "Test Multikick Beast")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=beast.id, kicker=2)
    pass_until_stack_empty(s)
    assert s.state.cards[beast.id].counters.get("+1/+1") == 2
    replay_matches(s)


def test_a_copy_of_a_kicked_spell_is_kicked(cards):
    s = build(cards, "Test Kicked Bolt", "Test Multigift")
    ogre = token(s, "p2", "Ogre", "9/9")
    gift, bolt = to_hand(s, "Test Multigift"), to_hand(s, "Test Kicked Bolt")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=gift.id)
    pass_until_stack_empty(s)
    hand = len(zone(s.state, "p1", "hand"))
    mana(s, R=2, C=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[ogre.id], kicker=1)
    for _ in range(6):  # storm: one copy (707.10: it copies the kicker decision too)
        d = decision(s)
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["same"] if any(o.id == "same" for o in d.options)
                else [d.options[0].id])
        pass_until_stack_empty(s)
    assert s.state.cards[ogre.id].damage == 4
    assert len(zone(s.state, "p1", "hand")) == hand - 1 + 2  # the spell and its copy each drew
    replay_matches(s)


def test_kicker_coverage():
    def ch(text, types=frozenset({"Instant"})):
        return Characteristics(name="Probe", types=types, abilities=tuple(parse_abilities(text, spell=True)))

    assert coverage.of_characteristics(ch("Kicker {1}\nDraw a card. If this spell was kicked, draw a card.")).level == "FULL"
    assert coverage.of_characteristics(ch("Kicker {1}{U} and/or {2}{B}\nDraw a card.")).level == "FULL"  # (wave 50H: 702.33b)
    assert coverage.of_characteristics(ch("Kicker {X} and/or {2}{B}\nDraw a card.")).level != "FULL"
    # 702.33g: a target chosen only if kicked (wave 4G: kicked_instead.applicable, tests/test_rules_wave4g_kicked_instead.py)
    assert coverage.of_characteristics(
        ch("Kicker {1}\nDraw a card. If this spell was kicked, destroy target creature.")).level == "FULL"
    # (but not on a permanent's ability: 702.33g is about a spell's targets)
    assert coverage.of_characteristics(
        ch("Kicker {1}\nWhen this creature enters, draw a card. If it was kicked, destroy target creature.",
           types=frozenset({"Creature"}))).level != "FULL"
