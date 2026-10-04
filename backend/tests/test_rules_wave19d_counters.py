"""Wave 19D: the counters long-tail sweep, real Oracle text (CR 2026-09-25).

* 603.10a / 122.2: "if it had no counters on it" / "for each +1/+1 counter on it" in a dies trigger read the object as it last existed.
* 608.2c: "put a ribbon counter on this creature. Then if it has three or more ribbon counters on it, remove those counters …" (the count
  is read after the counter was put); 603.8: "When this artifact has twenty or more charge counters on it" is a state trigger.
* 603.2: "At the beginning of your upkeep and whenever you cast a white spell" triggers on each of the two events.
* 614.1c, 601.2h: "enters with a +1/+1 counter on it for each mana spent to cast it".
* 608.2d / 115.1: "Put a menace counter on a creature you control." is chosen as the effect resolves (no target).
* 115.3: "Put a +1/+1 counter on target creature, two … on another target creature, and three … on a third target creature."
* 608.2c: "Put a -1/-1 counter on each creature target player controls."
Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, settle
from tests.test_rules_effects import mana, replay_matches
from tests.test_rules_suspend import until
from tests.test_rules_wave7c_counters import add, cast, counters, named, put, saved, zone

EXTRA = [
    card('Unstoppable Slasher', set_code='tst', number='T19D1', mana_cost='{2}{B}', cmc=3.0, type_line='Creature — Zombie Assassin', oracle_text="Deathtouch\nWhenever this creature deals combat damage to a player, they lose half their life, rounded up.\nWhen this creature dies, if it had no counters on it, return it to the battlefield tapped under its owner's control with two stun counters on it.", power='2', toughness='3', colors=['B'], color_identity=['B'], keywords=['Deathtouch']),  # noqa: E501
    card("Boss's Chauffeur", set_code='tst', number='T19D2', mana_cost='{4}{W}', cmc=5.0, type_line='Creature — Elf Citizen', oracle_text='This creature enters with a number of +1/+1 counters on it equal to one plus the number of other creatures you control.\nAlliance — Whenever another creature you control enters, put a +1/+1 counter on this creature.\nWhen this creature dies, create a 1/1 green and white Citizen creature token for each +1/+1 counter on it.', power='0', toughness='0', colors=['W'], color_identity=['W'], keywords=['Alliance']),  # noqa: E501
    card('Prize Pig', set_code='tst', number='T19D3', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Boar', oracle_text='Whenever you gain life, put that many ribbon counters on this creature. Then if there are three or more ribbon counters on this creature, remove those counters and untap it.\n{T}: Add one mana of any color.', power='0', toughness='3', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Waterbender Ascension', set_code='tst', number='T19D4', mana_cost='{1}{U}', cmc=2.0, type_line='Enchantment', oracle_text="Whenever a creature you control deals combat damage to a player, put a quest counter on this enchantment. Then if it has four or more quest counters on it, draw a card.\nWaterbend {4}: Target creature can't be blocked this turn. (While paying a waterbend cost, you can tap your artifacts and creatures to help. Each one pays for {1}.)", colors=['U'], color_identity=['U'], keywords=['Waterbend']),  # noqa: E501
    card('Shrine of Loyal Legions', set_code='tst', number='T19D5', mana_cost='{2}', cmc=2.0, type_line='Artifact', oracle_text='At the beginning of your upkeep and whenever you cast a white spell, put a charge counter on this artifact.\n{3}, {T}, Sacrifice this artifact: Create a 1/1 colorless Phyrexian Myr artifact creature token for each charge counter on this artifact.'),  # noqa: E501
    card('Darksteel Reactor', set_code='tst', number='T19D6', mana_cost='{4}', cmc=4.0, type_line='Artifact', oracle_text='Indestructible (Effects that say "destroy" don\'t destroy this artifact.)\nAt the beginning of your upkeep, you may put a charge counter on this artifact.\nWhen this artifact has twenty or more charge counters on it, you win the game.', keywords=['Indestructible']),  # noqa: E501
    card('Verazol, the Split Current', set_code='tst', number='T19D7', mana_cost='{X}{G}{U}', cmc=2.0, type_line='Legendary Creature — Serpent', oracle_text='Verazol enters with a +1/+1 counter on it for each mana spent to cast it.\nWhenever you cast a kicked spell, you may remove two +1/+1 counters from Verazol. If you do, copy that spell. You may choose new targets for the copy. (A copy of a permanent spell becomes a token.)', power='0', toughness='0', colors=['G', 'U'], color_identity=['G', 'U']),  # noqa: E501
    card('Blood Curdle', set_code='tst', number='T19D8', mana_cost='{3}{B}', cmc=4.0, type_line='Instant', oracle_text="Destroy target creature. Put a menace counter on a creature you control. (It can't be blocked except by two or more creatures.)", colors=['B'], color_identity=['B']),  # noqa: E501
    card('Incremental Growth', set_code='tst', number='T19D9', mana_cost='{3}{G}{G}', cmc=5.0, type_line='Sorcery', oracle_text='Put a +1/+1 counter on target creature, two +1/+1 counters on another target creature, and three +1/+1 counters on a third target creature.', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Contagion Engine', set_code='tst', number='T19D10', mana_cost='{6}', cmc=6.0, type_line='Artifact', oracle_text='When this artifact enters, put a -1/-1 counter on each creature target player controls.\n{4}, {T}: Proliferate twice. (Choose any number of permanents and/or players, then give each another counter of each kind already there. Then do it again.)', keywords=['Proliferate']),  # noqa: E501
    card('Sporogenesis', set_code='tst', number='T19D11', mana_cost='{3}{G}', cmc=4.0, type_line='Enchantment', oracle_text='At the beginning of your upkeep, you may put a fungus counter on target nontoken creature.\nWhenever a creature with a fungus counter on it dies, create a 1/1 green Saproling creature token for each fungus counter on that creature.\nWhen this enchantment leaves the battlefield, remove all fungus counters from all creatures.', colors=['G'], color_identity=['G']),  # noqa: E501
]
FULL = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *EXTRA2, *EXTRA3], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def check(s):
    replay_matches(s)
    replay_matches(saved(s))


def on_field(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield"]


@pytest.mark.parametrize("name", FULL)
def test_coverage_is_full(name):
    c = next(x for x in EXTRA if x["name"] == name)
    assert coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level == "FULL"


def test_slasher_returns_only_without_counters(cards):
    s = build(cards, "Unstoppable Slasher", "Murder", "Murder")
    slasher = put(s, "Unstoppable Slasher")
    cast(s, "Murder", targets=[slasher.id], B=2, C=1)
    settle(s)
    back = on_field(s, "Unstoppable Slasher")
    assert len(back) == 1 and back[0].tapped and counters(s, back[0]) == {"stun": 2}  # 603.10a: it had no counters
    add(s, back[0], 1)  # a counter on it: it doesn't return
    cast(s, "Murder", targets=[back[0].id], B=2, C=1)
    settle(s)
    assert not on_field(s, "Unstoppable Slasher") and zone(s, named(s, "Unstoppable Slasher")) == "p1:graveyard"
    check(s)


def test_chauffeur_makes_a_token_for_each_counter_it_had(cards):
    s = build(cards, "Boss's Chauffeur", "Murder")
    chauffeur = put(s, "Boss's Chauffeur")
    have = counters(s, chauffeur).get("+1/+1", 0)
    add(s, chauffeur, 3 - have if have < 3 else 0)
    n = counters(s, chauffeur)["+1/+1"]
    cast(s, "Murder", targets=[chauffeur.id], B=2, C=1)
    settle(s)
    assert zone(s, chauffeur) == "p1:graveyard"
    assert len([c for c in s.state.cards.values() if c.name == "Citizen" and c.zone == "p1:battlefield"]) == n >= 3  # its counters as it was
    check(s)


def test_prize_pig_counts_then_resets_and_untaps(cards):
    s = build(cards, "Prize Pig", "Swords to Plowshares", "Swords to Plowshares", "Grizzly Bears", "Grizzly Bears")
    pig = put(s, "Prize Pig")
    first = put(s, "Grizzly Bears")
    second = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1" and c.id != first.id)
    act(s, "p1", type="move", card_ids=[second.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="tap", card_ids=[pig.id], tapped=True)
    cast(s, "Swords to Plowshares", targets=[first.id], W=1)  # its controller gains life equal to its power: two
    settle(s)
    assert counters(s, pig) == {"ribbon": 2} and s.state.cards[pig.id].tapped
    cast(s, "Swords to Plowshares", targets=[second.id], W=1)
    settle(s)
    assert not counters(s, pig) and not s.state.cards[pig.id].tapped  # four: three or more — remove them all and untap it
    check(s)


def test_shrine_counts_on_a_white_spell_and_at_upkeep(cards):
    s = build(cards, "Shrine of Loyal Legions", "Swords to Plowshares", "Grizzly Bears")
    shrine, bears = put(s, "Shrine of Loyal Legions"), put(s, "Grizzly Bears")
    cast(s, "Swords to Plowshares", targets=[bears.id], W=1)
    settle(s)
    assert counters(s, shrine) == {"charge": 1}
    until(s, lambda s: counters(s, shrine).get("charge", 0) >= 2)  # Alice's next upkeep: the other half of the trigger
    assert counters(s, shrine) == {"charge": 2}
    check(s)


def test_a_state_trigger_on_its_own_counters(cards):
    s = build(cards, "Darksteel Reactor", "Grizzly Bears", "Grizzly Bears")
    reactor = put(s, "Darksteel Reactor")
    add(s, reactor, 19, "charge")  # (a hand-made change: state triggers are looked at after the table changes, as the next spell is cast)
    cast(s, "Grizzly Bears", G=1, C=1)
    settle(s)
    assert s.state.rules.winner is None
    add(s, reactor, 1, "charge")
    cast(s, "Grizzly Bears", G=1, C=1)
    until(s, lambda s: s.state.rules.winner is not None)
    assert s.state.rules.winner == "p1"  # 603.8: twenty or more: Alice wins
    check(s)


def test_verazol_enters_with_a_counter_for_each_mana_spent(cards):
    s = build(cards, "Verazol, the Split Current")
    c = next(c for c in s.state.cards.values() if c.name == "Verazol, the Split Current")
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    mana(s, "p1", G=1, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=2)
    settle(s)
    assert zone(s, c) == "p1:battlefield" and counters(s, c) == {"+1/+1": 4}  # {2}{G}{U}: four mana (601.2h)
    check(s)


def test_a_counter_on_a_creature_you_control_is_chosen_not_targeted(cards):
    s = build(cards, "Blood Curdle", "Grizzly Bears", "Llanowar Elves", p2=("Grizzly Bears",))
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    victim = put(s, "Grizzly Bears", pid="p2")
    cast(s, "Blood Curdle", targets=[victim.id], B=1, C=3)
    d = settle_until_choice(s)
    assert d.kind == "choose_cards" and sorted(o.id for o in d.options) == sorted([bears.id, elves.id])  # not a target: chosen on resolution
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[elves.id])
    settle(s)
    assert zone(s, victim) == "p2:graveyard" and counters(s, elves) == {"menace": 1} and not counters(s, bears)
    check(s)


def settle_until_choice(s):
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            return d
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no choice")


def test_incremental_growth_counters_on_three_different_targets(cards):
    s = build(cards, "Incremental Growth", "Grizzly Bears", "Llanowar Elves", "Grizzly Bears")
    a, b = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    c3 = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.id != a.id and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[c3.id], to={"player": "p1", "zone": "battlefield"})
    cast(s, "Incremental Growth", targets=[a.id, b.id, c3.id], counts=[1, 1, 1], G=2, C=3)
    settle(s)
    assert [counters(s, x).get("+1/+1") for x in (a, b, c3)] == [1, 2, 3]
    check(s)


def test_contagion_engine_puts_a_counter_on_each_creature_the_player_controls(cards):
    s = build(cards, "Contagion Engine", "Grizzly Bears", p2=("Llanowar Elves", "Grizzly Bears"))
    mine = put(s, "Grizzly Bears")
    theirs = [put(s, "Llanowar Elves", pid="p2"), put(s, "Grizzly Bears", pid="p2")]
    cast(s, "Contagion Engine", C=6)
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"] if "p2" in [o.id for o in d.options] else [d.options[0].id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert zone(s, theirs[0]) == "p2:graveyard" and counters(s, theirs[1]) == {"-1/-1": 1} and not counters(s, mine)  # each of that player's (the 1/1 died: 704.5f)
    check(s)


def test_sporogenesis_makes_a_saproling_for_each_fungus_counter_the_creature_had(cards):
    s = build(cards, "Sporogenesis", "Grizzly Bears", "Murder")
    put(s, "Sporogenesis")
    bears = put(s, "Grizzly Bears")
    add(s, bears, 2, "fungus")
    cast(s, "Murder", targets=[bears.id], B=2, C=1)
    settle(s)
    assert zone(s, bears) == "p1:graveyard"
    assert len([c for c in s.state.cards.values() if c.name == "Saproling" and c.zone == "p1:battlefield"]) == 2  # 603.10a: as it was
    check(s)


# -- second batch: selectors and edicts ---------------------------------------------------------------------------------
EXTRA2 = [
    card('Smokestack', set_code='tst', number='T19D12', mana_cost='{4}', cmc=4.0, type_line='Artifact', oracle_text="At the beginning of your upkeep, you may put a soot counter on this artifact.\nAt the beginning of each player's upkeep, that player sacrifices a permanent of their choice for each soot counter on this artifact."),  # noqa: E501
    card('Arcbound Overseer', set_code='tst', number='T19D14', mana_cost='{8}', cmc=8.0, type_line='Artifact Creature — Golem', oracle_text='At the beginning of your upkeep, put a +1/+1 counter on each creature you control with modular.\nModular 6 (This creature enters with six +1/+1 counters on it. When it dies, you may put its +1/+1 counters on target artifact creature.)', power='0', toughness='0', keywords=['Modular']),  # noqa: E501
    card('Quirion Dryad', set_code='tst', number='T19D15', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Dryad', oracle_text="Whenever you cast a spell that's white, blue, black, or red, put a +1/+1 counter on this creature.", power='1', toughness='1', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Legolas Greenleaf', set_code='tst', number='T19D16', mana_cost='{2}{G}', cmc=3.0, type_line='Legendary Creature — Elf Archer', oracle_text="Reach\nLegolas can't be blocked by creatures with power 2 or less.\nWhenever another legendary creature you control enters, put a +1/+1 counter on Legolas.\nWhenever Legolas deals combat damage to a player, draw a card.", power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=['Reach']),  # noqa: E501
]


@pytest.mark.parametrize("name", [c["name"] for c in EXTRA2])
def test_second_batch_is_full(name):
    c = next(x for x in EXTRA2 if x["name"] == name)
    assert coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level == "FULL"


def test_smokestack_sacrifices_a_permanent_for_each_soot_counter(cards):
    s = build(cards, "Smokestack", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears")
    stack = put(s, "Smokestack")
    add(s, stack, 2, "soot")
    for c in [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p1"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})

    def mine():
        return [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:battlefield"]

    assert len(mine()) == 3
    for _ in range(300):  # Alice's upkeep: decline the "may put a soot counter", stop at the sacrifice choice
        d = s.state.rules.decision
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_cards" and "sacrifice" in d.prompt:
            break
        elif d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        else:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids if d.kind == "order" else ["no"] if "no" in ids else ids[:1])
    d = s.state.rules.decision
    assert d.player == "p1" and len(d.options) == 4  # her choice among her permanents (701.21a): two of them, one per soot counter
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[stack.id, mine()[0].id])
    settle(s)
    assert zone(s, stack) == "p1:graveyard" and len(mine()) == 2
    check(s)


def test_arcbound_overseer_counts_the_creatures_with_modular_only(cards):
    s = build(cards, "Arcbound Overseer", "Grizzly Bears")
    bears = put(s, "Grizzly Bears")
    overseer = cast(s, "Arcbound Overseer", C=8)  # (it enters with six +1/+1 counters: modular)
    settle(s)
    before = counters(s, overseer).get("+1/+1", 0)
    assert before == 6
    until(s, lambda s: counters(s, overseer).get("+1/+1", 0) > before)  # Alice's next upkeep
    assert counters(s, overseer).get("+1/+1", 0) == before + 1 and not counters(s, bears)  # 702.43: the printed keyword
    check(s)


def test_quirion_dryad_counts_white_blue_black_or_red_spells_only(cards):
    s = build(cards, "Quirion Dryad", "Giant Growth", "Lightning Bolt", "Grizzly Bears")
    dryad, bears = put(s, "Quirion Dryad"), put(s, "Grizzly Bears")
    cast(s, "Giant Growth", targets=[bears.id], G=1)  # green: no counter
    settle(s)
    assert not counters(s, dryad)
    cast(s, "Lightning Bolt", targets=[bears.id], R=1)  # red: a counter
    settle(s)
    assert counters(s, dryad) == {"+1/+1": 1}
    check(s)


EXTRA3 = [
    card('Aligned Heart', set_code='tst', number='T19D17', mana_cost='{2}{W}', cmc=3.0, type_line='Enchantment', oracle_text='Flurry — Whenever you cast your second spell each turn, put a rally counter on this enchantment. Then create a 1/1 white Monk creature token with prowess for each rally counter on it. (Whenever you cast a noncreature spell, the token gets +1/+1 until end of turn.)', colors=['W'], color_identity=['W'], keywords=['Flurry']),  # noqa: E501
    card('Thoughts of Ruin', set_code='tst', number='T19D18', mana_cost='{2}{R}{R}', cmc=4.0, type_line='Sorcery', oracle_text='Each player sacrifices a land of their choice for each card in your hand.', colors=['R'], color_identity=['R']),  # noqa: E501
]


def test_aligned_heart_makes_a_monk_for_each_rally_counter_on_it(cards):
    s = build(cards, "Aligned Heart", "Lightning Bolt", "Giant Growth", "Grizzly Bears")
    heart, bears = put(s, "Aligned Heart"), put(s, "Grizzly Bears")
    cast(s, "Giant Growth", targets=[bears.id], G=1)
    settle(s)
    cast(s, "Lightning Bolt", targets=[bears.id], R=1)  # the second spell this turn
    settle(s)
    assert counters(s, heart) == {"rally": 1}  # (the enchantment's own counters: "it" is not the spell)
    assert len([c for c in s.state.cards.values() if c.name == "Monk" and c.zone == "p1:battlefield"]) == 1
    check(s)


def test_thoughts_of_ruin_counts_the_cards_in_your_hand_for_every_player(cards):
    from tests.test_rules_conditionals import to_hand

    s = build(cards, "Thoughts of Ruin", "Giant Growth", "Grizzly Bears")
    for pid, n in (("p1", 3), ("p2", 2)):  # Alice has three lands, Bob two
        for c in [c for c in s.state.cards.values() if c.owner == pid and c.name in ("Forest", "Island")][:n]:
            act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    to_hand(s, "Giant Growth")
    to_hand(s, "Grizzly Bears")
    cast(s, "Thoughts of Ruin", R=2, C=2)  # two cards left in her hand: each player sacrifices up to two lands
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.min_choices])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    lands = lambda pid: [c for c in s.state.cards.values() if c.zone == f"{pid}:battlefield" and c.name in ("Forest", "Island")]  # noqa: E731
    assert len(lands("p1")) == 1 and not lands("p2")  # the number counted once, as it resolves (the same for each player)
    check(s)


def test_legolas_is_named_in_its_own_counter_wording(cards):
    s = build(cards, "Legolas Greenleaf", "Krenko, Mob Boss")
    legolas = put(s, "Legolas Greenleaf")
    cast(s, "Krenko, Mob Boss", R=2, C=2)  # another legendary creature entering under Alice's control
    settle(s)
    assert counters(s, legolas) == {"+1/+1": 1}
    check(s)
