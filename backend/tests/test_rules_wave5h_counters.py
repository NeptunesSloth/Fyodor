"""Wave 5H: counters, other wordings. Researched against CR 2026-09-25 and the Wizards rulings of the cards named.

* 122.1: "with a counter on it" is any kind; "with +1/+1 counters on them" / "with no counters on them" / "without a
  +1/+1 counter on it" are selectors over the counters an object has now — a dying creature's as it last existed
  (603.10a, 122.2).
* 701.10e: to double the number of a kind of counters on a permanent, give it as many of those counters as it
  already has — a put (122.6), so Hardened Scales and Doubling Season apply (614.16).
* 614.1c, 614.12, 616.1: "Each other creature you control enters with an additional +1/+1 counter on it" modifies
  how a permanent enters — also one that would enter with none (Renata's ruling); a permanent entering at the same
  time doesn't apply it (ruling); ordered against Hardened Scales / Doubling Season by the entering permanent's
  controller.

Every scenario uses real Oracle text and checks the replay and a save/load round trip.
"""

from __future__ import annotations

import pytest

from app.game.session import GameSession
from app.game.state import GameState
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import build, settle, to_hand
from tests.test_rules_effects import mana, replay_matches

EXTRA = [
    card('Damning Verdict', set_code='tst', number='T5H1', mana_cost='{3}{W}{W}', cmc=5.0, type_line='Sorcery', oracle_text='Destroy all creatures with no counters on them.', colors=['W'], color_identity=['W']),
    card('Wave Goodbye', set_code='tst', number='T5H2', mana_cost='{2}{U}{U}', cmc=4.0, type_line='Sorcery', oracle_text="Return each creature without a +1/+1 counter on it to its owner's hand.", colors=['U'], color_identity=['U']),
    card('Herald of Secret Streams', set_code='tst', number='T5H3', mana_cost='{3}{U}', cmc=4.0, type_line='Creature — Merfolk Warrior', oracle_text="Creatures you control with +1/+1 counters on them can't be blocked.", power='2', toughness='3', colors=['U'], color_identity=['U']),
    card('Village Pillagers', set_code='tst', number='T5H4', mana_cost='{3}{R}{R}', cmc=5.0, type_line='Creature — Goblin Warrior', oracle_text='Wither (This deals damage to creatures in the form of -1/-1 counters.)\nWhen this creature enters, it deals 1 damage to each creature your opponents control.\nWhenever a creature an opponent controls with a counter on it dies, you create a tapped Treasure token.', power='5', toughness='5', colors=['R'], color_identity=['R'], keywords=['Treasure', 'Wither']),
    card('Rishkar, Peema Renegade', set_code='tst', number='T5H5', mana_cost='{2}{G}', cmc=3.0, type_line='Legendary Creature — Elf Druid', oracle_text='When Rishkar enters, put a +1/+1 counter on each of up to two target creatures.\nEach creature you control with a counter on it has "{T}: Add {G}."', power='2', toughness='2', colors=['G'], color_identity=['G']),
    card('Hidden Hideout', set_code='tst', number='T5H6', mana_cost='', cmc=0.0, type_line='Land', oracle_text="This land enters tapped.\n{T}: Add one mana of any color in your commander's color identity.\n{2}, {T}: Target creature you control with a counter on it gains lifelink until end of turn."),
    card('Kalonian Hydra', set_code='tst', number='T5H7', mana_cost='{3}{G}{G}', cmc=5.0, type_line='Creature — Hydra', oracle_text='Trample\nThis creature enters with four +1/+1 counters on it.\nWhenever this creature attacks, double the number of +1/+1 counters on each creature you control.', power='0', toughness='0', colors=['G'], color_identity=['G'], keywords=['Trample', 'Double']),
    card('Invigorating Surge', set_code='tst', number='T5H8', mana_cost='{2}{G}', cmc=3.0, type_line='Instant', oracle_text='Put a +1/+1 counter on target creature you control, then double the number of +1/+1 counters on that creature.', colors=['G'], color_identity=['G'], keywords=['Double']),
    card('Vorel of the Hull Clade', set_code='tst', number='T5H9', mana_cost='{1}{G}{U}', cmc=3.0, type_line='Legendary Creature — Human Merfolk', oracle_text='{G}{U}, {T}: Double the number of each kind of counter on target artifact, creature, or land.', power='1', toughness='4', colors=['G', 'U'], color_identity=['G', 'U'], keywords=['Double']),
    card('Renata, Called to the Hunt', set_code='tst', number='T5H10', mana_cost='{2}{G}{G}', cmc=4.0, type_line='Legendary Enchantment Creature — Demigod', oracle_text="Renata's power is equal to your devotion to green. (Each {G} in the mana costs of permanents you control counts toward your devotion to green.)\nEach other creature you control enters with an additional +1/+1 counter on it.", power='*', toughness='3', colors=['G'], color_identity=['G']),
    card('Giada, Font of Hope', set_code='tst', number='T5H11', mana_cost='{1}{W}', cmc=2.0, type_line='Legendary Creature — Angel', oracle_text='Flying, vigilance\nEach other Angel you control enters with an additional +1/+1 counter on it for each Angel you already control.\n{T}: Add {W}. Spend this mana only to cast an Angel spell.', power='2', toughness='2', colors=['W'], color_identity=['W'], keywords=['Flying', 'Vigilance']),
    card('Arwen, Weaver of Hope', set_code='tst', number='T5H12', mana_cost='{1}{G}{G}', cmc=3.0, type_line='Legendary Creature — Elf Noble', oracle_text="Each other creature you control enters with a number of additional +1/+1 counters on it equal to Arwen's toughness.", power='2', toughness='1', colors=['G'], color_identity=['G']),
    card('Hardened Scales', set_code='tst', number='T5H13', mana_cost='{G}', cmc=1.0, type_line='Enchantment', oracle_text='If one or more +1/+1 counters would be put on a creature you control, that many plus one +1/+1 counters are put on it instead.', colors=['G'], color_identity=['G']),
    card('Doubling Season', set_code='tst', number='T5H14', mana_cost='{4}{G}', cmc=5.0, type_line='Enchantment', oracle_text='If an effect would create one or more tokens under your control, it creates twice that many of those tokens instead.\nIf an effect would put one or more counters on a permanent you control, it puts twice that many of those counters on that permanent instead.', colors=['G'], color_identity=['G']),
    card('Oath of Gideon', set_code='tst', number='T5H15', mana_cost='{2}{W}', cmc=3.0, type_line='Legendary Enchantment', oracle_text='When Oath of Gideon enters, create two 1/1 white Kor Ally creature tokens.\nEach planeswalker you control enters with an additional loyalty counter on it.', colors=['W'], color_identity=['W']),
    card('Serra Angel', set_code='tst', number='T5H16', mana_cost='{3}{W}{W}', cmc=5.0, type_line='Creature — Angel', oracle_text="Flying\nVigilance (Attacking doesn't cause this creature to tap.)", power='4', toughness='4', colors=['W'], color_identity=['W'], keywords=['Flying', 'Vigilance']),
    card('Master Biomancer', set_code='tst', number='T5H17', mana_cost='{2}{G}{U}', cmc=4.0, type_line='Creature — Elf Wizard', oracle_text="Each other creature you control enters with a number of additional +1/+1 counters on it equal to this creature's power and as a Mutant in addition to its other types.", power='2', toughness='4', colors=['G', 'U'], color_identity=['G', 'U']),
    card('Tayam, Luminous Enigma', set_code='tst', number='T5H18', mana_cost='{1}{W}{B}{G}', cmc=4.0, type_line='Legendary Creature — Nightmare Beast', oracle_text='Each other creature you control enters with an additional vigilance counter on it.\n{3}, Remove three counters from among creatures you control: Mill three cards, then return a permanent card with mana value 3 or less from your graveyard to the battlefield.', power='3', toughness='3', colors=['B', 'G', 'W'], color_identity=['B', 'G', 'W'], keywords=['Mill']),
    card('Inspiring Call', set_code='tst', number='T5H19', mana_cost='{2}{G}', cmc=3.0, type_line='Instant', oracle_text='Draw a card for each creature you control with a +1/+1 counter on it. Those creatures gain indestructible until end of turn. (Damage and effects that say "destroy" don\'t destroy them.)', colors=['G'], color_identity=['G']),
    card('Replenish', set_code='tst', number='T5H20', mana_cost='{3}{W}', cmc=4.0, type_line='Sorcery', oracle_text='Return all enchantment cards from your graveyard to the battlefield. (Auras with nothing to enchant remain in your graveyard.)', colors=['W'], color_identity=['W']),
    card('Nyxborn Brute', set_code='tst', number='T5H21', mana_cost='{3}{R}{R}', cmc=5.0, type_line='Enchantment Creature — Cyclops', oracle_text='', power='7', toughness='3', colors=['R'], color_identity=['R']),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


# -- helpers ---------------------------------------------------------------------------------------------------
def saved(s):
    """The table saved and loaded again (a restart): play goes on from the loaded one."""
    return GameSession(GameState.model_validate_json(s.state.model_dump_json()), cards=s.cards)


def named(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def put(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def add(s, c, n, kind="+1/+1"):
    act(s, c.controller, type="counter", card_ids=[c.id], kind=kind, delta=n)


def counters(s, c):
    return {k: v for k, v in s.state.cards[c.id].counters.items() if v}


def zone(s, c):
    return s.state.cards[c.id].zone


def cast(s, name, pid="p1", targets=None, **paid):
    c = to_hand(s, name, pid)
    mana(s, pid, **paid)
    act(s, pid, type="cast_spell", card_id=c.id, **({"targets": targets} if targets else {}))
    return c


def cov(name):
    c = next(x for x in EXTRA if x["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


@pytest.mark.parametrize(("name", "level"), [
    ("Damning Verdict", "FULL"), ("Wave Goodbye", "FULL"), ("Herald of Secret Streams", "FULL"),
    ("Village Pillagers", "FULL"), ("Rishkar, Peema Renegade", "FULL"), ("Hidden Hideout", "FULL"),
    ("Kalonian Hydra", "FULL"), ("Invigorating Surge", "FULL"), ("Vorel of the Hull Clade", "FULL"),
    ("Renata, Called to the Hunt", "FULL"), ("Giada, Font of Hope", "FULL"), ("Arwen, Weaver of Hope", "FULL"),
    ("Oath of Gideon", "FULL"),
    # refused: a type change with the counters (layer 4 as it enters), a keyword counter, "those creatures"
    ("Master Biomancer", "PARTIAL"), ("Tayam, Luminous Enigma", "PARTIAL"),
])
def test_counter_wordings_coverage(name, level):
    assert cov(name) == level


# -- selectors (122.1) ------------------------------------------------------------------------------------------
def test_damning_verdict_spares_creatures_with_any_counter(cards):
    s = build(cards, "Damning Verdict", "Grizzly Bears", "Llanowar Elves", "Kitchen Finks", p2=("Grizzly Bears",))
    bears, elves, finks, theirs = put(s, "Grizzly Bears"), put(s, "Llanowar Elves"), put(s, "Kitchen Finks"), \
        put(s, "Grizzly Bears", "p2")
    add(s, bears, 1)
    add(s, finks, 1, "-1/-1")  # any kind counts
    s = saved(s)
    cast(s, "Damning Verdict", W=2, C=3)
    settle(s)
    assert zone(s, bears) == "p1:battlefield" and zone(s, finks) == "p1:battlefield"
    assert zone(s, elves) == "p1:graveyard" and zone(s, theirs) == "p2:graveyard"
    replay_matches(s)


def test_wave_goodbye_returns_creatures_without_a_plus_counter(cards):
    s = build(cards, "Wave Goodbye", "Grizzly Bears", "Kitchen Finks", p2=("Grizzly Bears",))
    bears, finks, theirs = put(s, "Grizzly Bears"), put(s, "Kitchen Finks"), put(s, "Grizzly Bears", "p2")
    add(s, bears, 2)
    add(s, finks, 1, "-1/-1")  # a -1/-1 counter isn't a +1/+1 counter
    s = saved(s)
    cast(s, "Wave Goodbye", U=2, C=2)
    settle(s)
    assert zone(s, bears) == "p1:battlefield"
    assert zone(s, finks) == "p1:hand" and zone(s, theirs) == "p2:hand"
    replay_matches(s)


def test_herald_of_secret_streams_static_follows_the_counters(cards):
    from app.rules import scripts
    from app.rules.plan import Plan

    s = build(cards, "Herald of Secret Streams", "Grizzly Bears", "Llanowar Elves")
    put(s, "Herald of Secret Streams")
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    add(s, bears, 1)
    s = saved(s)

    def unblockable(c):
        return "cant_be_blocked" in scripts.statics(Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]))

    assert unblockable(bears) and not unblockable(elves)
    add(s, bears, -1)
    assert not unblockable(bears)
    replay_matches(s)


def test_village_pillagers_reads_the_dying_creatures_counters(cards):
    """603.10a: who had a counter is read as each creature last existed (its counters cease to exist as it moves,
    122.2) — also for Village Pillagers dying in the same Wrath (a leaves-the-battlefield look back)."""
    s = build(cards, "Village Pillagers", "Wrath of God", p2=("Grizzly Bears", "Llanowar Elves"))
    put(s, "Village Pillagers")
    bears, elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    add(s, bears, 1)
    s = saved(s)
    cast(s, "Wrath of God", W=2, C=2)
    settle(s)
    assert zone(s, bears) == "p2:graveyard" and zone(s, elves) == "p2:graveyard"
    treasures = [c for c in s.state.cards.values() if c.name == "Treasure" and c.controller == "p1"
                 and c.zone.endswith("battlefield")]
    assert len(treasures) == 1 and treasures[0].tapped
    replay_matches(s)


def test_rishkar_grants_its_mana_ability_to_creatures_with_any_counter(cards):
    from app.rules.plan import Plan

    s = build(cards, "Rishkar, Peema Renegade", "Grizzly Bears", "Kitchen Finks")
    bears, finks = put(s, "Grizzly Bears"), put(s, "Kitchen Finks")
    rishkar = put(s, "Rishkar, Peema Renegade")
    settle(s)
    add(s, finks, 1, "-1/-1")
    s = saved(s)

    def has_grant(c):
        ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
        return any(a.index >= 100 and a.text == "{T}: Add {G}." for a in ch.abilities)

    assert has_grant(finks)  # a -1/-1 counter is a counter
    assert not has_grant(bears) and not has_grant(rishkar)
    add(s, bears, 1)
    assert has_grant(bears)
    replay_matches(s)


def test_hidden_hideout_targets_only_a_creature_with_a_counter(cards):
    from app.rules import scripts, selectors
    from app.rules.plan import Plan

    s = build(cards, "Hidden Hideout", "Grizzly Bears", "Llanowar Elves")
    hideout, bears, elves = put(s, "Hidden Hideout"), put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    add(s, bears, 1)
    plan = Plan(s.state, "p1", s.cards, None)
    d = scripts.definitions(plan.ch(s.state.cards[hideout.id]))[2]
    found = selectors.candidates(plan, selectors.from_key(d["target"]["what"]), "p1", hideout.id)
    assert bears.id in found and elves.id not in found


# -- doubling (701.10e) -----------------------------------------------------------------------------------------------
def test_kalonian_hydra_doubles_each_creatures_counters_on_attack(cards):
    from tests.test_rules_suspend import until

    s = build(cards, "Kalonian Hydra", "Grizzly Bears", "Llanowar Elves")
    hydra = cast(s, "Kalonian Hydra", G=2, C=3)
    settle(s)
    assert counters(s, hydra) == {"+1/+1": 4}
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    add(s, bears, 1)
    s = saved(s)
    until(s, lambda s: s.state.turn.number == 3 and s.state.rules.decision is not None
          and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": hydra.id, "target": "p2"}])
    until(s, lambda s: counters(s, hydra) != {"+1/+1": 4})
    assert counters(s, hydra) == {"+1/+1": 8} and counters(s, bears) == {"+1/+1": 2} and not counters(s, elves)
    replay_matches(s)


def test_invigorating_surge_with_hardened_scales(cards):
    """The put and the doubling are each a put (122.6): 0 → 1 + 1 = 2, then 2 more + 1 = 5."""
    s = build(cards, "Invigorating Surge", "Hardened Scales", "Grizzly Bears")
    put(s, "Hardened Scales")
    bears = put(s, "Grizzly Bears")
    s = saved(s)
    cast(s, "Invigorating Surge", targets=[bears.id], G=1, C=2)
    settle(s)
    assert counters(s, bears) == {"+1/+1": 5}
    replay_matches(s)


def test_vorel_doubles_each_kind(cards):
    from tests.test_rules_suspend import until

    s = build(cards, "Vorel of the Hull Clade", "Grizzly Bears")
    vorel = put(s, "Vorel of the Hull Clade")
    bears = put(s, "Grizzly Bears")
    add(s, bears, 2)
    add(s, bears, 1, "charge")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1" and s.state.rules.priority == "p1")
    s = saved(s)
    mana(s, G=1, U=1)
    act(s, "p1", type="activate_ability", card_id=vorel.id, ability=0, targets=[bears.id])
    settle(s)
    assert counters(s, bears) == {"+1/+1": 4, "charge": 2}
    replay_matches(s)


# -- entering with additional counters (614.1c, 614.12, 616.1) ----------------------------------------------------------
def test_renata_gives_a_counter_to_a_creature_entering_with_none(cards):
    s = build(cards, "Renata, Called to the Hunt", "Grizzly Bears", "Spike Feeder")
    renata = put(s, "Renata, Called to the Hunt")
    s = saved(s)
    bears = cast(s, "Grizzly Bears", G=1, C=1)
    settle(s)
    feeder = cast(s, "Spike Feeder", G=2, C=1)
    settle(s)
    assert counters(s, bears) == {"+1/+1": 1} and counters(s, feeder) == {"+1/+1": 3}
    assert not counters(s, renata)
    replay_matches(s)


def test_renata_and_hardened_scales_and_doubling_season(cards):
    """Renata applies to a creature entering with none, then Hardened Scales (616.1f: what applies is checked again):
    0 → 1 → 2. With Doubling Season and Spike Feeder's two counters the order matters (Renata first: 3 × 2 = 6;
    Doubling Season first: 4 + 1 = 5) and is asked before it enters (614.12a)."""
    s = build(cards, "Renata, Called to the Hunt", "Hardened Scales", "Doubling Season", "Grizzly Bears", "Spike Feeder")
    put(s, "Renata, Called to the Hunt")
    put(s, "Hardened Scales")
    bears = cast(s, "Grizzly Bears", G=1, C=1)
    settle(s)
    assert counters(s, bears) == {"+1/+1": 2}
    act(s, "p1", type="move", card_ids=[named(s, "Hardened Scales").id], to={"zone": "graveyard"})
    put(s, "Doubling Season")
    feeder = cast(s, "Spike Feeder", G=2, C=1)
    d = None
    for _ in range(5):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and "616.1" in d.prompt and zone(s, feeder) == "stack"
    renata_first = next(o.id for o in d.options if o.label.startswith("Renata"))
    s = saved(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[renata_first])
    settle(s)
    assert counters(s, feeder) == {"+1/+1": 6}
    replay_matches(s)


def test_a_creature_entering_with_renata_gets_no_counter(cards):
    """Ruling (2020-01-24): a creature entering at the same time as Renata doesn't get one (614.12). Replenish returns
    both at once."""
    s = build(cards, "Renata, Called to the Hunt", "Nyxborn Brute", "Replenish")
    renata, brute = named(s, "Renata, Called to the Hunt"), named(s, "Nyxborn Brute")
    act(s, "p1", type="move", card_ids=[renata.id, brute.id], to={"zone": "graveyard"})
    s = saved(s)
    cast(s, "Replenish", W=1, C=3)
    settle(s)
    assert zone(s, renata) == "p1:battlefield" and zone(s, brute) == "p1:battlefield"
    assert not counters(s, brute) and not counters(s, renata)
    replay_matches(s)
    # with Renata already there, the same Replenish gives the Brute its counter
    s = build(cards, "Renata, Called to the Hunt", "Nyxborn Brute", "Replenish")
    put(s, "Renata, Called to the Hunt")
    brute = named(s, "Nyxborn Brute")
    act(s, "p1", type="move", card_ids=[brute.id], to={"zone": "graveyard"})
    cast(s, "Replenish", W=1, C=3)
    settle(s)
    assert counters(s, brute) == {"+1/+1": 1}
    replay_matches(s)


def test_giada_counts_the_angels_already_there(cards):
    s = build(cards, "Giada, Font of Hope", "Serra Angel", "Serra Angel", "Grizzly Bears")
    put(s, "Giada, Font of Hope")
    first = cast(s, "Serra Angel", W=2, C=3)
    settle(s)
    assert counters(s, first) == {"+1/+1": 1}  # Giada
    second = next(c for c in s.state.cards.values() if c.name == "Serra Angel" and c.id != first.id)
    act(s, "p1", type="move", card_ids=[second.id], to={"zone": "hand"})
    s = saved(s)
    mana(s, W=2, C=3)
    act(s, "p1", type="cast_spell", card_id=second.id)
    settle(s)
    assert counters(s, second) == {"+1/+1": 2}  # Giada and the first Serra Angel, not itself
    bears = cast(s, "Grizzly Bears", G=1, C=1)
    settle(s)
    assert not counters(s, bears)  # not an Angel
    replay_matches(s)


def test_arwen_reads_her_toughness_as_it_enters(cards):
    s = build(cards, "Arwen, Weaver of Hope", "Grizzly Bears", "Llanowar Elves", "Giant Growth")
    arwen = put(s, "Arwen, Weaver of Hope")
    elves = cast(s, "Llanowar Elves", G=1)
    settle(s)
    assert counters(s, elves) == {"+1/+1": 1}
    cast(s, "Giant Growth", targets=[arwen.id], G=1)
    settle(s)
    s = saved(s)
    bears = cast(s, "Grizzly Bears", G=1, C=1)
    settle(s)
    assert counters(s, bears) == {"+1/+1": 4}
    replay_matches(s)


def test_oath_of_gideon_adds_loyalty(cards):
    s = build(cards, "Oath of Gideon", "Gideon Jura")
    put(s, "Oath of Gideon")
    settle(s)
    s = saved(s)
    gideon = cast(s, "Gideon Jura", W=2, C=3)
    settle(s)
    assert counters(s, gideon) == {"loyalty": 7}
    replay_matches(s)


