"""Wave 100O: changing targets and choosing new targets (CR 115.7a-e, 115.9c), copies with new targets (707.10c).

* "target spell that targets only this creature / a single creature / a player" (115.9c): one different object or player, maybe several times;
  "change the target" then changes every one of them to the same new target, legal for each (Torchling's, Muck Drubb's rulings).
* "The new target must be a player / a creature" (Rebound, Silver Wyvern); "change the targets" all or none (115.7a, Goblin Flectomancer's ruling);
  "change any targets" (115.7c, Sideswipe); "change the target to enchanted creature if able" (Captured by the Consulate); "choose new targets for
  that spell" (Speedball) and "for any number of other spells and/or abilities" (Boltbender).
* Cast triggers that copy their own spell (Malicious Affliction, Bygone Marvels, Ancestral Communion's "while", Banish into Fable, Storm of Forms).
Every scenario checks the replay and a save/load round trip."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, scripts
from tests.game_helpers import act
from tests.test_rules_conditionals import on_field, pick, settle, to_hand, until_asked
from tests.test_rules_effects import mana
from tests.test_rules_wave5b_stack_interaction import alice_casts, build, roundtrip
from tests.test_rules_wave12a_counters_keywords import real

EXTRA = [
    real('Rebound', '{1}{U}', 2, 'Instant',
         'Change the target of target spell that targets only a player. The new target must be a player.', None, 'U'),
    real('Silver Wyvern', '{3}{U}{U}', 5, 'Creature — Drake',
         'Flying\n{U}: Change the target of target spell or ability that targets only this creature. The new target must be a creature.', ("4", "3"), 'U'),
    real('Torchling', '{3}{R}{R}', 5, 'Creature — Shapeshifter',
         '{R}: Untap this creature.\n{R}: Target creature blocks this creature this turn if able.\n{R}: Change the target of target spell that targets only this '
         'creature.\n{1}: This creature gets +1/-1 until end of turn.\n{1}: This creature gets -1/+1 until end of turn.', ("3", "3"), 'R'),
    real('Muck Drubb', '{3}{B}{B}', 5, 'Creature — Beast',
         'Flash\nWhen this creature enters, change the target of target spell that targets only a single creature to this creature.\nMadness {2}{B} (If you '
         'discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your graveyard.)', ("3", "3"), 'B'),
    real('Goblin Flectomancer', '{U}{R}{R}', 3, 'Creature — Goblin Wizard',
         'Sacrifice this creature: You may change the targets of target instant or sorcery spell.', ("2", "2"), 'RU'),
    real('Sideswipe', '{1}{R}', 2, 'Instant', 'You may change any targets of target Arcane spell.', None, 'R'),
    real('Captured by the Consulate', '{3}{W}', 4, 'Enchantment — Aura',
         "Enchant creature you don't control\nEnchanted creature can't attack.\nWhenever an opponent casts a spell, if it has a single target, change the target "
         "to enchanted creature if able.", None, 'W'),
    real('Speedball, New Warrior', '{2}{U/R}', 3, 'Legendary Creature — Human Hero',
         'Whenever a player casts a spell that targets Speedball, he gets +2/+2 until end of turn. You may choose new targets for that spell.', ("2", "2"), 'RU'),
    real('Boltbender', '{3}{R}', 4, 'Creature — Goblin Wizard',
         'Disguise {1}{R} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)\nWhen this '
         'creature is turned face up, you may choose new targets for any number of other spells and/or abilities.', ("4", "2"), 'R'),
    real('Malicious Affliction', '{B}{B}', 2, 'Instant',
         'Morbid — When you cast this spell, if a creature died this turn, you may copy Malicious Affliction and may choose a new target for the copy.\nDestroy '
         'target nonblack creature.', None, 'B'),
    real('Bygone Marvels', '{G}{G}', 2, 'Sorcery',
         'Descend 8 — When you cast this spell, if there are eight or more permanent cards in your graveyard, copy this spell twice. You may choose new targets '
         'for the copies.\nReturn target permanent card from your graveyard to your hand. Exile Bygone Marvels.', None, 'G'),
    real('Ancestral Communion', '{1}{G}', 2, 'Sorcery',
         'When you cast this spell while you control your commander, copy this spell. You may choose a new target for the copy.\nReturn target permanent card '
         'from your graveyard to your hand.', None, 'G'),
    real('Banish into Fable', '{4}{W}{U}', 6, 'Instant',
         "When you cast this spell from your hand, copy it if you control an artifact, then copy it if you control an enchantment. You may choose new targets "
         "for the copies.\nReturn target nonland permanent to its owner's hand. You create a 2/2 white Knight creature token with vigilance.", None, 'UW'),
    real('Storm of Forms', '{3}{U}', 4, 'Instant',
         "When you cast this spell, copy it for each kind of counter among permanents you control. You may choose new targets for the copies.\nReturn target "
         "nonland permanent to its owner's hand.", None, 'U'),
    real('Seeds of Strength', '{G}{W}', 2, 'Instant',
         'Target creature gets +1/+1 until end of turn.\nTarget creature gets +1/+1 until end of turn.\nTarget creature gets +1/+1 until end of turn.', None, 'GW'),
    real('Arc Trail', '{1}{R}', 2, 'Sorcery', 'Arc Trail deals 2 damage to any target and 1 damage to any other target.', None, 'R'),
    real('Glacial Ray', '{1}{R}', 2, 'Instant — Arcane',
         "Glacial Ray deals 2 damage to any target.\nSplice onto Arcane {1}{R} (As you cast an Arcane spell, you may reveal this card from your hand and pay its "
         "splice cost. If you do, add this card's effects to that spell.)", None, 'R'),
    real('Flamehold Grappler', '{U}{R}{W}', 3, 'Creature — Human Monk',
         'First strike\nWhen this creature enters, copy the next spell you cast this turn when you cast it. You may choose new targets for the copy. (A copy of a '
         'permanent spell becomes a token.)', ("3", "3"), 'RUW'),
    real('Tzaangor Shaman', '{2}{U}{R}', 4, 'Creature — Mutant Shaman',
         'Flying\nSorcerous Elixir — Whenever this creature deals combat damage to a player, copy the next instant or sorcery spell you cast this turn when you '
         'cast it. You may choose new targets for the copy.', ("3", "3"), 'RU'),
    real('Sea Gate Stormcaller', '{1}{U}', 2, 'Creature — Human Wizard',
         'Kicker {4}{U}\nWhen this creature enters, copy the next instant or sorcery spell with mana value 2 or less you cast this turn when you cast it. If '
         'this creature was kicked, copy that spell twice instead. You may choose new targets for the copies.', ("2", "1"), 'U'),
    real("Jaya's Phoenix", '{4}{R}', 5, 'Creature — Phoenix',
         'Flying, haste\nWhenever this creature deals combat damage to a player or planeswalker, copy the next loyalty ability you activate this turn when you '
         'activate it. You may choose new targets for the copy.\nWhenever you cast a planeswalker spell, you may return this card from your graveyard to the '
         'battlefield.', ("3", "3"), 'R'),
    real('Repeated Reverberation', '{2}{R}{R}', 4, 'Instant',
         'When you next cast an instant spell, cast a sorcery spell, or activate a loyalty ability this turn, copy that spell or ability twice. You may choose new '
         'targets for the copies.', None, 'R'),
    real('Hive Mind', '{5}{U}', 6, 'Enchantment',
         'Whenever a player casts an instant or sorcery spell, each other player copies that spell. Each of those players may choose new targets for their copy.',
         None, 'U'),
    real('Curse of Echoes', '{4}{U}', 5, 'Enchantment — Aura Curse',
         'Enchant player\nWhenever enchanted player casts an instant or sorcery spell, each other player may copy that spell and may choose new targets for the '
         'copy they control.', None, 'U'),
    real('Spinerock Tyrant', '{3}{R}{R}', 5, 'Creature — Dragon',
         'Flying\nWither (This deals damage to creatures in the form of -1/-1 counters.)\nWhenever you cast an instant or sorcery spell with a single target, '
         'you may copy it. If you do, those spells gain wither. You may choose new targets for the copy.', ("6", "6"), 'R'),
    real('Meletis Charlatan', '{2}{U}', 3, 'Creature — Human Wizard',
         '{2}{U}, {T}: The controller of target instant or sorcery spell copies it. That player may choose new targets for the copy.', ("2", "3"), 'U'),
    real('Tempt with Mayhem', '{1}{R}{R}', 3, 'Instant',
         'Tempting offer — Choose target instant or sorcery spell. Each opponent may copy that spell and may choose new targets for the copy they control. You '
         'copy that spell once plus an additional time for each opponent who copied the spell this way. You may choose new targets for the copies you control.',
         None, 'R'),
    real('Errant, Street Artist', '{U}', 1, 'Legendary Creature — Human Rogue',
         "Flash\nDefender, haste\n{1}{U}, {T}: Copy target spell you control that wasn't cast. You may choose new targets for the copy.", ("0", "3"), 'U'),
    real('Psychic Rebuttal', '{1}{U}', 2, 'Instant',
         'Counter target instant or sorcery spell that targets you.\nSpell mastery — If there are two or more instant and/or sorcery cards in your graveyard, '
         'you may copy the spell countered this way. You may choose new targets for the copy.', None, 'U'),
    real('Glorious Anthem', '{1}{W}{W}', 3, 'Enchantment', 'Creatures you control get +1/+1.', None, 'W'),
    real('Shock', '{R}', 1, 'Instant', 'Shock deals 2 damage to any target.', None, 'R'),
]
FULL = ["Rebound", "Silver Wyvern", "Torchling", "Muck Drubb", "Goblin Flectomancer", "Sideswipe", "Captured by the Consulate", "Speedball, New Warrior",
        "Boltbender", "Malicious Affliction", "Bygone Marvels", "Ancestral Communion", "Banish into Fable", "Storm of Forms", "Flamehold Grappler",
        "Tzaangor Shaman", "Sea Gate Stormcaller", "Jaya's Phoenix", "Repeated Reverberation", "Hive Mind", "Curse of Echoes",
        "Spinerock Tyrant", "Meletis Charlatan", "Tempt with Mayhem", "Errant, Street Artist", "Psychic Rebuttal"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", FULL)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_wordings():
    rebound = scripts.parse_effects("Change the target of target spell that targets only a player. The new target must be a player.")
    assert rebound is not None and rebound[0] == [{"do": "change_target", "who": "target", "to": None, "must": "player"}] and "targets_only:player" in rebound[1]
    drubb = scripts.parse_effects("Change the target of target spell that targets only a single creature to this creature.")
    assert drubb is not None and drubb[0][0]["all"] is True
    for refused in ("Change the target of target spell that targets only a creature card.",  # (not a permanent)
                    "Change a target of target spell that targets only a player.", "Change any targets of target spell to this creature.",
                    "Change the target of target spell that targets only a player. The new target must be an artifact."):
        assert scripts.parse_effects(refused) is None, refused


def targets_of(s, sid):
    return [t.id for t in s.state.rules.stack[sid].targets]


def bob_casts(s, name, targets=(), **pay):
    c = to_hand(s, name, "p2")
    mana(s, "p2", **pay)
    act(s, "p2", type="cast_spell", card_id=c.id, targets=list(targets))
    return c


# -- 115.7a with 115.9c: "change the target" of a spell on one object -------------------------------------------------------------------
def test_rebound_sends_the_bolt_to_the_only_other_player(cards):
    """The new target must be a player: the Bears (a legal target for the Bolt) aren't offered; Alice is the one other player, so it is hers."""
    s = build(cards, p1=("Lightning Bolt", "Grizzly Bears"), p2=("Rebound",))
    bears = on_field(s, "Grizzly Bears")
    bolt = alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    bob_casts(s, "Rebound", [bolt.id], U=1, C=1)
    settle(s)
    assert s.state.players["p1"].life == 37 and s.state.players["p2"].life == 40 and s.state.cards[bears.id].damage == 0
    roundtrip(s)


def test_rebound_cant_target_a_bolt_at_a_creature(cards):
    s = build(cards, p1=("Lightning Bolt", "Grizzly Bears"), p2=("Rebound",))
    bears = on_field(s, "Grizzly Bears")
    bolt = alice_casts(s, "Lightning Bolt", targets=[bears.id], R=1)
    with pytest.raises(ActionError):
        bob_casts(s, "Rebound", [bolt.id], U=1, C=1)


def test_torchling_moves_all_three_seeds_to_one_new_creature(cards):
    """Torchling's ruling: Seeds of Strength on Torchling three times targets only it; all three become the same new legal target."""
    s = build(cards, p1=("Seeds of Strength", "Grizzly Bears", "Llanowar Elves"), p2=("Torchling",))
    bears, elves = on_field(s, "Grizzly Bears"), on_field(s, "Llanowar Elves")
    torch = on_field(s, "Torchling", "p2")
    seeds = alice_casts(s, "Seeds of Strength", targets=[torch.id, torch.id, torch.id], counts=[1, 1, 1], G=1, W=1)
    mana(s, "p2", R=1)
    act(s, "p2", type="activate_ability", card_id=torch.id, ability=2, targets=[seeds.id])
    d = until_asked(s)
    assert d is not None and d.player == "p2" and {o.id for o in d.options} == {bears.id, elves.id}  # (creatures only: Seeds' "target creature")
    pick(s, elves.id)
    assert targets_of(s, seeds.id) == [elves.id] * 3
    roundtrip(s)
    settle(s)
    from tests.wave9c_kit import pt
    assert pt(s, "Llanowar Elves") == (4, 4) and pt(s, "Torchling", "p2") == (3, 3)
    roundtrip(s)


def test_torchling_cant_target_arc_trail_with_two_targets(cards):
    s = build(cards, p1=("Arc Trail",), p2=("Torchling",))
    torch = on_field(s, "Torchling", "p2")
    trail = alice_casts(s, "Arc Trail", targets=[torch.id, "p2"], counts=[1, 1], R=1, C=1)
    mana(s, "p2", R=1)
    with pytest.raises(ActionError):
        act(s, "p2", type="activate_ability", card_id=torch.id, ability=2, targets=[trail.id])


def test_silver_wyvern_new_target_must_be_a_creature(cards):
    s = build(cards, p1=("Lightning Bolt", "Grizzly Bears", "Llanowar Elves"), p2=("Silver Wyvern",))
    bears, elves = on_field(s, "Grizzly Bears"), on_field(s, "Llanowar Elves")
    wyvern = on_field(s, "Silver Wyvern", "p2")
    bolt = alice_casts(s, "Lightning Bolt", targets=[wyvern.id], R=1)
    mana(s, "p2", U=1)
    act(s, "p2", type="activate_ability", card_id=wyvern.id, ability=1, targets=[bolt.id])
    d = until_asked(s)
    assert d is not None and {o.id for o in d.options} == {bears.id, elves.id}  # (no player, though the Bolt could target one)
    pick(s, bears.id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard" and s.state.cards[wyvern.id].damage == 0
    roundtrip(s)


def test_muck_drubb_takes_every_target_of_the_seeds(cards):
    """Muck Drubb's ruling: all of Seeds' targets on one creature become Muck Drubb (115.7a)."""
    s = build(cards, p1=("Seeds of Strength", "Grizzly Bears"), p2=("Muck Drubb",))
    bears = on_field(s, "Grizzly Bears")
    seeds = alice_casts(s, "Seeds of Strength", targets=[bears.id, bears.id, bears.id], counts=[1, 1, 1], G=1, W=1)
    drubb = bob_casts(s, "Muck Drubb", B=2, C=3)
    d = until_asked(s)  # (Drubb resolves; its trigger targets the Seeds)
    assert d is not None and d.player == "p2" and seeds.id in {o.id for o in d.options}
    pick(s, seeds.id)
    settle(s)
    from tests.wave9c_kit import pt
    assert pt(s, "Muck Drubb", "p2") == (6, 6) and pt(s, "Grizzly Bears") == (2, 2)
    assert s.state.cards[drubb.id].zone == "p2:battlefield"
    roundtrip(s)


# -- 115.7a "change the targets", 115.7c "change any targets" ---------------------------------------------------------------------------------
@pytest.mark.parametrize("leave", [False, True])
def test_goblin_flectomancer_changes_both_or_none(cards, leave):
    """Arc Trail's 2 (Bob) and 1 (Bob's Bears) become Alice and Alice's Elves — or every target is left (the "may")."""
    s = build(cards, p1=("Arc Trail", "Llanowar Elves"), p2=("Goblin Flectomancer", "Grizzly Bears"))
    elves = on_field(s, "Llanowar Elves")
    bears = on_field(s, "Grizzly Bears", "p2")
    flecto = on_field(s, "Goblin Flectomancer", "p2")
    trail = alice_casts(s, "Arc Trail", targets=["p2", bears.id], counts=[1, 1], R=1, C=1)
    act(s, "p2", type="activate_ability", card_id=flecto.id, ability=0, targets=[trail.id])
    d = until_asked(s)
    assert d is not None and d.player == "p2" and "p2" not in {o.id for o in d.options} and "keep" in {o.id for o in d.options}
    if leave:
        pick(s, "keep")
    else:
        pick(s, "p1")
        d = until_asked(s)
        assert "p1" not in {o.id for o in d.options} and bears.id not in {o.id for o in d.options}  # (another target; another than the Bears)
        pick(s, elves.id)
    settle(s)
    if leave:
        assert s.state.players["p2"].life == 38 and s.state.cards[bears.id].damage == 1
    else:
        assert s.state.players["p1"].life == 38 and s.state.cards[elves.id].zone == "p1:graveyard" and s.state.cards[bears.id].damage == 0
    roundtrip(s)


def test_sideswipe_changes_any_targets_of_an_arcane_spell(cards):
    s = build(cards, p1=("Glacial Ray",), p2=("Sideswipe",))
    ray = alice_casts(s, "Glacial Ray", targets=["p2"], R=1, C=1)
    bob_casts(s, "Sideswipe", [ray.id], R=1, C=1)
    d = until_asked(s)
    assert d is not None and d.player == "p2" and "keep" in {o.id for o in d.options}
    pick(s, "p1")
    settle(s)
    assert s.state.players["p1"].life == 38 and s.state.players["p2"].life == 40
    roundtrip(s)


# -- fixed new targets and cast triggers ---------------------------------------------------------------------------------------------------
def test_captured_by_the_consulate_redirects_a_single_target_spell(cards):
    """Bob's Seeds of Strength has three targets (115.9a: one creature three times): no trigger; his Bolt at Alice goes to the Bears."""
    s = build(cards, p1=("Captured by the Consulate", "Shock"), p2=("Lightning Bolt", "Seeds of Strength", "Grizzly Bears", "Llanowar Elves"))
    bears = on_field(s, "Grizzly Bears", "p2")
    elves = on_field(s, "Llanowar Elves", "p2")
    alice_casts(s, "Captured by the Consulate", targets=[bears.id], W=1, C=3)
    settle(s)
    alice_casts(s, "Shock", targets=["p2"], R=1)
    seeds = to_hand(s, "Seeds of Strength", "p2")
    mana(s, "p2", G=1, W=1)
    act(s, "p2", type="cast_spell", card_id=seeds.id, targets=[elves.id] * 3, target_counts=[1, 1, 1])
    from tests.wave9c_kit import pt
    assert s.state.cards[seeds.id].zone == "p2:graveyard" and pt(s, "Llanowar Elves", "p2") == (4, 4)  # (no trigger: it resolved as cast)
    bolt = bob_casts(s, "Lightning Bolt", ["p1"], R=1)
    settle(s)
    assert s.state.players["p1"].life == 40 and s.state.cards[bears.id].zone == "p2:graveyard" and s.state.cards[bolt.id].zone == "p2:graveyard"
    assert s.state.players["p2"].life == 38
    roundtrip(s)


def test_speedball_grows_and_sends_the_shock_back(cards):
    s = build(cards, p1=("Shock",), p2=("Speedball, New Warrior",))
    ball = on_field(s, "Speedball, New Warrior", "p2")
    alice_casts(s, "Shock", targets=[ball.id], R=1)
    d = until_asked(s)
    assert d is not None and d.player == "p2"
    pick(s, "yes")
    d = until_asked(s)
    assert d is not None and "keep" in {o.id for o in d.options}
    pick(s, "p1")
    settle(s)
    from tests.wave9c_kit import pt
    assert s.state.players["p1"].life == 38 and pt(s, "Speedball, New Warrior", "p2") == (4, 4) and s.state.cards[ball.id].damage == 0
    roundtrip(s)


def test_boltbender_turned_face_up_redirects_chosen_spells(cards):
    s = build(cards, p1=("Boltbender", "Shock"), p2=("Lightning Bolt",))
    act(s, "p1", type="set_prefs", response="on")
    bender = to_hand(s, "Boltbender")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=bender.id, face_down=True)
    settle(s)
    shock = alice_casts(s, "Shock", targets=["p2"], R=1)
    bolt = bob_casts(s, "Lightning Bolt", ["p1"], R=1)
    mana(s, R=1, C=1)
    act(s, "p1", type="turn_face_up", card_id=bender.id)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and d.kind == "choose_cards" and {o.id for o in d.options} == {bolt.id, shock.id}
    pick(s, bolt.id)
    d = until_asked(s)
    assert d is not None and "keep" in {o.id for o in d.options}
    pick(s, "p2")
    settle(s)
    assert s.state.players["p1"].life == 40 and s.state.players["p2"].life == 35
    roundtrip(s)


def test_malicious_affliction_copy_after_a_death(cards):
    s = build(cards, p1=("Lightning Bolt", "Malicious Affliction"), p2=("Grizzly Bears", "Llanowar Elves", "Kitchen Finks"))
    bears, elves = on_field(s, "Grizzly Bears", "p2"), on_field(s, "Llanowar Elves", "p2")
    finks = on_field(s, "Kitchen Finks", "p2")
    alice_casts(s, "Lightning Bolt", targets=[elves.id], R=1)
    settle(s)
    alice_casts(s, "Malicious Affliction", targets=[bears.id], B=2)
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    pick(s, "yes")
    d = until_asked(s)
    assert d is not None and "keep" in {o.id for o in d.options}
    pick(s, finks.id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and s.state.cards[finks.id].zone == "p2:battlefield"  # (persist: a new Finks returned)
    assert s.state.cards[finks.id].counters.get("-1/-1") == 1
    roundtrip(s)


def test_ancestral_communion_while_is_judged_as_it_triggers(cards):
    """"while you control your commander": not rechecked as the trigger resolves (603.4 is about "if" only) — the copy still happens."""
    s = build(cards, p1=("Ancestral Communion", "Grizzly Bears", "Llanowar Elves"))
    bears, elves = to_hand(s, "Grizzly Bears"), to_hand(s, "Llanowar Elves")
    for c in (bears, elves):
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss")
    alice_casts(s, "Ancestral Communion", targets=[bears.id], G=1, C=1)  # (no commander: no trigger)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:hand" and s.state.cards[elves.id].zone == "p1:graveyard"
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    comm = next(c for c in s.state.cards.values() if c.name == "Ancestral Communion")
    act(s, "p1", type="move", card_ids=[comm.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p1", "zone": "battlefield"})
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=comm.id, targets=[bears.id])
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "command"})  # (the commander leaves before the trigger resolves)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and elves.id in {o.id for o in d.options}
    pick(s, elves.id)
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:hand" and s.state.cards[elves.id].zone == "p1:hand"
    roundtrip(s)


@pytest.mark.parametrize("enchantment", [False, True])
def test_banish_into_fable_one_copy_per_type_you_control(cards, enchantment):
    s = build(cards, p1=("Banish into Fable", "Sol Ring", "Glorious Anthem"), p2=("Grizzly Bears", "Llanowar Elves", "Kitchen Finks"))
    on_field(s, "Sol Ring")
    if enchantment:
        on_field(s, "Glorious Anthem")
    bears, elves, finks = (on_field(s, n, "p2") for n in ("Grizzly Bears", "Llanowar Elves", "Kitchen Finks"))
    alice_casts(s, "Banish into Fable", targets=[bears.id], W=1, U=1, C=4)
    for victim in [elves.id, finks.id][: 1 + enchantment]:
        d = until_asked(s)
        assert d is not None and d.player == "p1" and "keep" in {o.id for o in d.options}
        pick(s, victim)
    settle(s)
    back = [c for c in (bears, elves, finks) if s.state.cards[c.id].zone == "p2:hand"]
    knights = [c for c in s.state.cards.values() if c.name == "Knight" and c.zone == "p1:battlefield"]
    assert len(back) == len(knights) == 2 + enchantment
    roundtrip(s)


def test_storm_of_forms_one_copy_per_kind_of_counter(cards):
    s = build(cards, p1=("Storm of Forms", "Grizzly Bears", "Llanowar Elves"), p2=("Kitchen Finks", "Island"))
    bears, elves = on_field(s, "Grizzly Bears"), on_field(s, "Llanowar Elves")
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    act(s, "p1", type="counter", card_ids=[bears.id], kind="charge", delta=1)
    act(s, "p1", type="counter", card_ids=[elves.id], kind="+1/+1", delta=2)
    finks = on_field(s, "Kitchen Finks", "p2")
    alice_casts(s, "Storm of Forms", targets=[finks.id], U=1, C=3)
    d = until_asked(s)
    assert d is not None and [o.id for o in d.options] == ["same", "choose"]  # (two kinds: two copies)
    pick(s, "same")
    settle(s)
    assert s.state.cards[finks.id].zone == "p2:hand"
    roundtrip(s)


def test_bygone_marvels_copies_twice_with_eight_permanent_cards(cards):
    names = ("Grizzly Bears", "Llanowar Elves", "Kitchen Finks", "Sol Ring", "Pacifism", "Forest", "Island", "Ambush Viper", "Young Wolf")
    s = build(cards, p1=("Bygone Marvels", *names))
    gy = [to_hand(s, n) for n in names]
    act(s, "p1", type="move", card_ids=[c.id for c in gy], to={"zone": "graveyard"})
    alice_casts(s, "Bygone Marvels", targets=[gy[0].id], G=2)
    d = until_asked(s)
    assert d is not None and [o.id for o in d.options] == ["same", "choose"]
    pick(s, "choose")
    for c in gy[1:3]:
        pick(s, c.id)
    settle(s)
    assert [s.state.cards[c.id].zone for c in gy[:3]] == ["p1:hand"] * 3 and s.state.cards[gy[3].id].zone == "p1:graveyard"
    assert next(c for c in s.state.cards.values() if c.name == "Bygone Marvels").zone == "p1:exile"
    roundtrip(s)


# -- delayed "copy the next …" (603.7) ----------------------------------------------------------------------------------------------------
def test_flamehold_grappler_copies_only_the_next_spell(cards):
    s = build(cards, p1=("Flamehold Grappler", "Lightning Bolt", "Shock"))
    alice_casts(s, "Flamehold Grappler", U=1, R=1, W=1)
    settle(s)
    alice_casts(s, "Lightning Bolt", targets=["p2"], R=1)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and "keep" in {o.id for o in d.options}
    pick(s, "keep")
    settle(s)
    assert s.state.players["p2"].life == 34
    alice_casts(s, "Shock", targets=["p2"], R=1)
    settle(s)
    assert s.state.players["p2"].life == 32  # (once: 603.7c)
    roundtrip(s)


@pytest.mark.parametrize("kicked", [False, True])
def test_sea_gate_stormcaller_copies_once_or_twice(cards, kicked):
    s = build(cards, p1=("Sea Gate Stormcaller", "Arc Trail", "Shock"))
    c = to_hand(s, "Sea Gate Stormcaller")
    mana(s, U=2 if kicked else 1, C=5 if kicked else 1)
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=1 if kicked else 0)
    settle(s)
    alice_casts(s, "Shock", targets=["p2"], R=1)
    if kicked:
        d = until_asked(s)
        assert d is not None and [o.id for o in d.options] == ["same", "choose"]
        pick(s, "same")
    else:
        d = until_asked(s)
        pick(s, "keep")
    settle(s)
    assert s.state.players["p2"].life == 40 - 2 * (3 if kicked else 2)
    roundtrip(s)


def test_repeated_reverberation_copies_a_loyalty_ability_twice(cards):
    """The rulings: copying a loyalty ability doesn't change loyalty; the next instant, sorcery or loyalty ability is the one copied."""
    s = build(cards, p1=("Test Walker Card", "Repeated Reverberation"))
    walker = alice_casts(s, "Test Walker Card", U=2, C=2)
    settle(s)
    alice_casts(s, "Repeated Reverberation", R=2, C=2)
    settle(s)
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=0)
    settle(s)
    assert s.state.players["p1"].life == 46 and s.state.cards[walker.id].counters["loyalty"] == 4
    roundtrip(s)


def test_jayas_phoenix_copies_the_next_loyalty_ability(cards):
    s = build(cards, p1=("Test Walker Card", "Jaya's Phoenix"))
    walker = alice_casts(s, "Test Walker Card", U=2, C=2)
    settle(s)
    phoenix = on_field(s, "Jaya's Phoenix")
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": phoenix.id, "target": "p2"}])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            break
        else:
            settle(s, 1) if d is not None else act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.players["p2"].life == 37 and s.state.rules.delayed
    act(s, "p1", type="activate_ability", card_id=walker.id, ability=0)
    settle(s)
    assert s.state.players["p1"].life == 44 and s.state.cards[walker.id].counters["loyalty"] == 4
    roundtrip(s)


# -- each other player copies (707.10, 101.4) ---------------------------------------------------------------------------------------------
def build3(cards, p1=(), p2=(), p3=()):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    seats = (("Alice", "Krenko, Mob Boss", p1), ("Bob", "Atraxa, Praetors' Voice", p2), ("Carol", "Krenko, Mob Boss", p3))
    s = GameSession(enable(new_game([PlayerSetup(n, cards=deck(cards, c, [*((1, x) for x in names), (9, "Island")])) for n, c, names in seats],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    for pid in ("p2", "p3"):
        act(s, pid, type="set_prefs", response="on")
    return s


def test_hive_mind_each_other_player_copies_in_turn_order(cards):
    """The ruling: Alice (active) cast it, so Bob copies first, then Carol; each chooses the targets of their own copy."""
    s = build3(cards, p1=("Lightning Bolt",), p2=("Hive Mind",))
    on_field(s, "Hive Mind", "p2")
    alice_casts(s, "Lightning Bolt", targets=["p3"], R=1)
    for pid in ("p2", "p3"):
        d = until_asked(s)
        assert d is not None and d.player == pid and "keep" in {o.id for o in d.options}
        pick(s, "p1")
    settle(s)
    copies = [c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.zone == "stack"]
    assert not copies and s.state.players["p1"].life == 34 and s.state.players["p3"].life == 37
    roundtrip(s)


def test_curse_of_echoes_each_other_player_may_copy(cards):
    s = build3(cards, p1=("Curse of Echoes", "Shock"), p2=("Lightning Bolt",))
    act(s, "p1", type="set_prefs", response="on")
    alice_casts(s, "Curse of Echoes", targets=["p2"], U=1, C=4)
    settle(s)
    alice_casts(s, "Shock", targets=["p2"], R=1)
    bob_casts(s, "Lightning Bolt", ["p1"], R=1)
    d = until_asked(s)
    assert d is not None and d.player == "p1" and d.kind == "confirm"
    pick(s, "yes")
    d = until_asked(s)
    assert d is not None and d.player == "p1" and "keep" in {o.id for o in d.options}
    pick(s, "p2")
    d = until_asked(s)
    assert d is not None and d.player == "p3" and d.kind == "confirm"
    pick(s, "no")
    settle(s)
    assert s.state.players["p2"].life == 35 and s.state.players["p1"].life == 37 and s.state.players["p3"].life == 40
    roundtrip(s)


def test_spinerock_tyrant_both_spells_gain_wither(cards):
    from tests.test_rules_conditionals import creature

    s = build(cards, p1=("Spinerock Tyrant", "Shock"))
    on_field(s, "Spinerock Tyrant")
    big = creature(s, "p2", "Big", "5/5")
    alice_casts(s, "Shock", targets=[big.id], R=1)
    d = until_asked(s)
    assert d is not None and d.player == "p1"
    pick(s, "yes")
    pick(s, "keep")
    settle(s)
    assert s.state.cards[big.id].counters.get("-1/-1") == 4 and s.state.cards[big.id].damage == 0  # (120.3d: both had wither)
    roundtrip(s)


def test_meletis_charlatan_the_spells_controller_copies_it(cards):
    from tests.game_helpers import turn_on
    from tests.test_rules_conditionals import sandbox

    s = sandbox(cards, "Meletis Charlatan", "Shock", p2=("Lightning Bolt",))
    charlatan = on_field(s, "Meletis Charlatan")  # (there since before the turn: not summoning sick)
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", response="on")
    alice_casts(s, "Shock", targets=["p2"], R=1)
    bolt = bob_casts(s, "Lightning Bolt", ["p1"], R=1)
    mana(s, U=1, C=2)
    act(s, "p1", type="activate_ability", card_id=charlatan.id, ability=0, targets=[bolt.id])
    d = until_asked(s)
    assert d is not None and d.player == "p2" and "keep" in {o.id for o in d.options}  # (the copy and its targets are Bob's: the rulings)
    pick(s, "keep")
    settle(s)
    assert s.state.players["p1"].life == 34 and s.state.players["p2"].life == 38
    roundtrip(s)


def test_tempt_with_mayhem_opponents_then_you_once_plus_each(cards):
    """The ruling: each opponent in turn order may copy (and retarget their copy); then Alice copies once plus once for each who did."""
    s = build3(cards, p1=("Shock", "Tempt with Mayhem"), p2=("Lightning Bolt",))
    act(s, "p1", type="set_prefs", response="on")
    alice_casts(s, "Shock", targets=["p2"], R=1)
    bolt = bob_casts(s, "Lightning Bolt", ["p3"], R=1)
    act(s, "p3", type="pass_priority")
    alice_casts(s, "Tempt with Mayhem", targets=[bolt.id], R=2, C=1)
    d = until_asked(s)
    assert d is not None and d.player == "p2" and d.kind == "confirm"
    pick(s, "yes")
    d = until_asked(s)
    assert d is not None and d.player == "p2" and "keep" in {o.id for o in d.options}
    pick(s, "p1")
    d = until_asked(s)
    assert d is not None and d.player == "p3" and d.kind == "confirm"
    pick(s, "no")
    d = until_asked(s)
    assert d is not None and d.player == "p1" and [o.id for o in d.options] == ["same", "choose"]  # (1 + 1 copies)
    pick(s, "same")
    settle(s)
    assert s.state.players["p1"].life == 37 and s.state.players["p3"].life == 31 and s.state.players["p2"].life == 38
    roundtrip(s)


def test_errant_copies_only_a_spell_that_wasnt_cast(cards):
    s = build(cards, p1=("Flamehold Grappler", "Lightning Bolt", "Errant, Street Artist"))
    act(s, "p1", type="set_prefs", response="on")
    alice_casts(s, "Flamehold Grappler", U=1, R=1, W=1)
    settle(s)
    errant = on_field(s, "Errant, Street Artist")
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    d = until_asked(s)  # (Grappler's delayed trigger resolves: its copy)
    pick(s, "keep")
    copy = next(c for c in s.state.zones["stack"] if c != bolt.id and s.state.cards[c].name == "Lightning Bolt")
    mana(s, U=1, C=1)
    if s.state.rules.priority != "p1":
        act(s, s.state.rules.priority, type="pass_priority")
    with pytest.raises(ActionError):  # (the Bolt itself was cast)
        act(s, "p1", type="activate_ability", card_id=errant.id, ability=2, targets=[bolt.id])
    act(s, "p1", type="activate_ability", card_id=errant.id, ability=2, targets=[copy])
    d = until_asked(s)
    assert d is not None and d.player == "p1" and "keep" in {o.id for o in d.options}
    pick(s, "keep")
    settle(s)
    assert s.state.players["p2"].life == 31
    roundtrip(s)


@pytest.mark.parametrize("mastery", [False, True])
def test_psychic_rebuttal_copies_the_countered_spell_with_spell_mastery(cards, mastery):
    s = build(cards, p1=("Shock", "Psychic Rebuttal", "Opt", "Giant Growth"), p2=("Lightning Bolt",))
    act(s, "p1", type="set_prefs", response="on")
    if mastery:
        act(s, "p1", type="move", card_ids=[to_hand(s, n).id for n in ("Opt", "Giant Growth")], to={"zone": "graveyard"})
    alice_casts(s, "Shock", targets=["p2"], R=1)
    bolt = bob_casts(s, "Lightning Bolt", ["p1"], R=1)
    alice_casts(s, "Psychic Rebuttal", targets=[bolt.id], U=1, C=1)
    if mastery:
        d = until_asked(s)
        assert d is not None and d.player == "p1"
        pick(s, "yes")
        d = until_asked(s)
        assert d is not None and "keep" in {o.id for o in d.options}  # (the copy is Alice's: its "any target" may be Bob)
        pick(s, "p2")
    settle(s)
    assert s.state.cards[bolt.id].zone == "p2:graveyard" and s.state.players["p1"].life == 40
    assert s.state.players["p2"].life == (35 if mastery else 38)
    roundtrip(s)
