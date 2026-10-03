"""Wave 7R: scenario tests for cards that wave 7 promoted to FULL without a dedicated test (the "surprise promotions"),
sampled by wording family. CR 2026-09-25. Every card carries its real Oracle text (the card database, 2026-09)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import attack, combat_step, creature, sandbox, settle, through_combat, until
from tests.test_rules_wave6c_tokens_pumps import card_named, mana, pt, put
from tests.test_rules_wave7r_review import alive, build, check, to_hand, tok

# name -> (mana cost, mana value, type line, text, power, toughness, colors)
ORACLE = {
    'Abattoir Ghoul': ('{3}{B}', 4.0, 'Creature — Zombie',
        "First strike\nWhenever a creature dealt damage by this creature this turn dies, you gain life equal to that creature's toughness.",
        '3', '2', ['B']),
    'Aleatory': ('{1}{R}', 2.0, 'Instant',
        "Cast this spell only during combat after blockers are declared.\nFlip a coin. If you win the flip, target creature gets +1/+1 until end of turn.\nDraw a card at the beginning of the next turn's upkeep.",
        None, None, ['R']),
    'Ascendant Spirit': ('{U}', 1.0, 'Snow Creature — Spirit',
        '{S}{S}: This creature becomes a Spirit Warrior with base power and toughness 2/3.\n{S}{S}{S}: If this creature is a Warrior, put a flying counter on it and it becomes a Spirit Warrior Angel with base power and toughness 4/4.\n{S}{S}{S}{S}: If this creature is an Angel, put two +1/+1 counters on it and it gains "Whenever this creature deals combat damage to a player, draw a card."',
        '1', '1', ['U']),
    "Atraxa's Skitterfang": ('{3}', 3.0, 'Artifact Creature — Phyrexian Insect',
        'This creature enters with three oil counters on it.\nAt the beginning of combat on your turn, you may remove an oil counter from this creature. When you do, target creature you control gains your choice of flying, vigilance, deathtouch, or lifelink until end of turn.',
        '2', '2', []),
    'Blizzard': ('{G}{G}', 2.0, 'Enchantment',
        "Cast this spell only if you control a snow land.\nCumulative upkeep {2} (At the beginning of your upkeep, put an age counter on this permanent, then sacrifice it unless you pay its upkeep cost for each age counter on it.)\nCreatures with flying don't untap during their controllers' untap steps.",
        None, None, ['G']),
    'Bottle of Suleiman': ('{4}', 4.0, 'Artifact',
        '{1}, Sacrifice this artifact: Flip a coin. If you win the flip, create a 5/5 colorless Djinn artifact creature token with flying. If you lose the flip, this artifact deals 5 damage to you.',
        None, None, []),
    'Butcher of the Horde': ('{1}{R}{W}{B}', 4.0, 'Creature — Demon',
        'Flying\nSacrifice another creature: This creature gains your choice of vigilance, lifelink, or haste until end of turn.',
        '5', '4', ['B', 'R', 'W']),
    'Casey Jones, Asphalt Hooligan': ('{2}{R}', 3.0, 'Legendary Creature — Human Berserker',
        "Double strike (This creature deals both first-strike and regular combat damage.)\n{4}: Double Casey Jones's power until end of turn. Any player may activate this ability.",
        '2', '2', ['R']),
    'Chaotic Goo': ('{2}{R}{R}', 4.0, 'Creature — Ooze',
        'This creature enters with three +1/+1 counters on it.\nAt the beginning of your upkeep, you may flip a coin. If you win the flip, put a +1/+1 counter on this creature. If you lose the flip, remove a +1/+1 counter from this creature.',
        '0', '0', ['R']),
    'Charitable Levy': ('{1}{W}', 2.0, 'Enchantment',
        'Noncreature spells cost {1} more to cast.\nWhenever a player casts a noncreature spell, put a collection counter on this enchantment. Then if there are three or more collection counters on it, sacrifice it. If you do, draw a card, then you may search your library for a Plains card, put it onto the battlefield tapped, then shuffle.',
        None, None, ['W']),
    'Chilling Shade': ('{2}{B}', 3.0, 'Snow Creature — Shade',
        'Flying\n{S}: This creature gets +1/+1 until end of turn. ({S} can be paid with one mana from a snow source.)',
        '1', '1', ['B']),
    'Chronatog Totem': ('{3}', 3.0, 'Artifact',
        '{T}: Add {U}.\n{1}{U}: This artifact becomes a 1/2 blue Atog artifact creature until end of turn.\n{0}: This creature gets +3/+3 until end of turn. You skip your next turn. Activate only once each turn and only if this permanent is a creature.',
        None, None, []),
    'Coral Reef': ('{U}{U}', 2.0, 'Enchantment',
        'This enchantment enters with four polyp counters on it.\nSacrifice an Island: Put two polyp counters on this enchantment.\n{U}, Tap an untapped blue creature you control, Remove a polyp counter from this enchantment: Put a +0/+1 counter on target creature.',
        None, None, ['U']),
    'Culvert Ambusher': ('{3}{G}{G}', 5.0, 'Creature — Wurm Horror',
        'When this creature enters or is turned face up, target creature blocks this turn if able.\nDisguise {4}{G} (You may cast this card face down for {3} as a 2/2 creature with ward {2}. Turn it face up any time for its disguise cost.)',
        '4', '5', ['G']),
    'Dread Slaver': ('{3}{B}{B}', 5.0, 'Creature — Zombie Horror',
        'Whenever a creature dealt damage by this creature this turn dies, return it to the battlefield under your control. That creature is a black Zombie in addition to its other colors and types.',
        '3', '5', ['B']),
    'Dwarven Armory': ('{2}{R}{R}', 4.0, 'Enchantment',
        '{2}, Sacrifice a land: Put a +2/+2 counter on target creature. Activate only during any upkeep step.',
        None, None, ['R']),
    "Family's Favor": ('{2}{G}', 3.0, 'Enchantment',
        'Whenever you attack, put a shield counter on target attacking creature. Until end of turn, it gains "Whenever this creature deals combat damage to a player, remove a shield counter from it. If you do, draw a card." (If a creature with a shield counter on it would be dealt damage or destroyed, remove a shield counter from it instead.)',
        None, None, ['G']),
    'Flitterwing Nuisance': ('{U}', 1.0, 'Creature — Faerie Rogue',
        'Flying\nThis creature enters with a -1/-1 counter on it.\n{2}{U}, Remove a counter from this creature: Whenever a creature you control deals combat damage to a player or planeswalker this turn, draw a card.',
        '2', '2', ['U']),
    'Frost Raptor': ('{2}{U}', 3.0, 'Snow Creature — Bird',
        "Flying\n{S}{S}: This creature gains shroud until end of turn. ({S} can be paid with one mana from a snow source. A creature with shroud can't be the target of spells or abilities.)",
        '2', '2', ['U']),
    'Gnawing Crescendo': ('{2}{R}', 3.0, 'Instant',
        'Creatures you control get +2/+0 until end of turn. Whenever a nontoken creature you control dies this turn, create a 1/1 black Rat creature token with "This token can\'t block."',
        None, None, ['R']),
    'Goblin Bomb': ('{1}{R}', 2.0, 'Enchantment',
        'At the beginning of your upkeep, you may flip a coin. If you win the flip, put a fuse counter on this enchantment. If you lose the flip, remove a fuse counter from this enchantment.\nRemove five fuse counters from this enchantment and sacrifice it: It deals 20 damage to target player or planeswalker.',
        None, None, ['R']),
    'Hivis of the Scale': ('{3}{R}{R}', 5.0, 'Legendary Creature — Lizard Shaman',
        'You may choose not to untap Hivis during your untap step.\n{T}: Gain control of target Dragon for as long as you control Hivis and Hivis remains tapped.',
        '3', '4', ['R']),
    'Immortus, Master of Eternity': ('{2}{U}{U}', 4.0, 'Legendary Creature — Human Hero Villain',
        "{T}: Add {U} for each card you've drawn this turn. Spend this mana only to cast noncreature spells.\nPower-up — {5}{U}{U}: Each player shuffles their hand and graveyard into their library, then draws seven cards. Put a +1/+1 counter on Immortus. (Activate each power-up ability only once. Reduce the cost by his mana cost if he entered this turn.)",
        '2', '2', ['U']),
    'Janjeet Sentry': ('{2}{U}', 3.0, 'Creature — Vedalken Soldier',
        'When this creature enters, you get {E}{E} (two energy counters).\n{T}, Pay {E}{E}: You may tap or untap target artifact or creature.',
        '2', '3', ['U']),
    "Jodah's Avenger": ('{5}{U}', 6.0, 'Creature — Shapeshifter',
        '{0}: Until end of turn, this creature gets -1/-1 and gains your choice of double strike, protection from red, vigilance, or shadow. (A creature with shadow can block or be blocked by only creatures with shadow.)',
        '4', '4', ['U']),
    'Jolt': ('{2}{U}', 3.0, 'Instant',
        "You may tap or untap target artifact, creature, or land.\nDraw a card at the beginning of the next turn's upkeep.",
        None, None, ['U']),
    'Kitsa, Otterball Elite': ('{1}{U}', 2.0, 'Legendary Creature — Otter Wizard',
        "Vigilance\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\n{T}: Draw a card, then discard a card.\n{2}, {T}: Copy target instant or sorcery spell you control. You may choose new targets for the copy. Activate only if Kitsa's power is 3 or greater.",
        '1', '3', ['U']),
    'Lurking Arynx': ('{4}{G}', 5.0, 'Creature — Cat Beast',
        'Formidable — {2}{G}: Target creature blocks this creature this turn if able. Activate only if creatures you control have total power 8 or greater.',
        '3', '5', ['G']),
    "Mage Hunters' Onslaught": ('{2}{B}{B}', 4.0, 'Sorcery',
        'Destroy target creature or planeswalker.\nWhenever a creature blocks this turn, its controller loses 1 life.',
        None, None, ['B']),
    'Mercurial Spelldancer': ('{1}{U}', 2.0, 'Creature — Phyrexian Rogue',
        "This creature can't be blocked.\nWhenever you cast a noncreature spell, put an oil counter on this creature.\nWhenever this creature deals combat damage to a player, you may remove two oil counters from it. If you do, when you next cast an instant or sorcery spell this turn, copy that spell. You may choose new targets for the copy.",
        '2', '1', ['U']),
    'Mijae Djinn': ('{R}{R}{R}', 3.0, 'Creature — Djinn',
        'Whenever this creature attacks, flip a coin. If you lose the flip, remove this creature from combat and tap it.',
        '6', '3', ['R']),
    'Multiform Wonder': ('{5}', 5.0, 'Artifact Creature — Construct',
        'When this creature enters, you get {E}{E}{E} (three energy counters).\nPay {E}: This creature gains your choice of flying, vigilance, or lifelink until end of turn.\nPay {E}: This creature gets +2/-2 or -2/+2 until end of turn.',
        '3', '3', []),
    "Oracle's Vault": ('{4}', 4.0, 'Artifact',
        '{2}, {T}: Exile the top card of your library. Until end of turn, you may play that card. Put a brick counter on this artifact.\n{T}: Exile the top card of your library. Until end of turn, you may play that card without paying its mana cost. Activate only if there are three or more brick counters on this artifact.',
        None, None, []),
    'Panic': ('{R}', 1.0, 'Instant',
        "Cast this spell only during combat before blockers are declared.\nTarget creature can't block this turn.\nDraw a card at the beginning of the next turn's upkeep.",
        None, None, ['R']),
    'Peema Aether-Seer': ('{3}{G}', 4.0, 'Creature — Elf Druid',
        'When this creature enters, you get an amount of {E} (energy counters) equal to the greatest power among creatures you control.\nPay {E}{E}{E}: Target creature blocks this turn if able.',
        '3', '2', ['G']),
    'Phyrexian Ironfoot': ('{3}', 3.0, 'Snow Artifact Creature — Phyrexian Construct',
        "This creature doesn't untap during your untap step.\n{1}{S}: Untap this creature. ({S} can be paid with one mana from a snow source.)",
        '3', '4', []),
    'Phyrexian Snowcrusher': ('{6}', 6.0, 'Snow Artifact Creature — Phyrexian Juggernaut',
        'This creature attacks each combat if able.\n{1}{S}: This creature gets +1/+0 until end of turn. ({S} can be paid with one mana from a snow source.)',
        '6', '5', []),
    "Puppet's Verdict": ('{1}{R}{R}', 3.0, 'Instant',
        'Flip a coin. If you win the flip, destroy all creatures with power 2 or less. If you lose the flip, destroy all creatures with power 3 or greater.',
        None, None, ['R']),
    'Rattleback Apothecary': ('{2}{B}', 3.0, 'Creature — Gorgon Warlock',
        'Deathtouch\nWhenever you commit a crime, target creature you control gains your choice of menace or lifelink until end of turn. (Targeting opponents, anything they control, and/or cards in their graveyards is a crime.)',
        '3', '2', ['B']),
    'Rimescale Dragon': ('{5}{R}{R}', 7.0, 'Snow Creature — Dragon',
        "Flying\n{2}{S}: Tap target creature and put an ice counter on it. ({S} can be paid with one mana from a snow source.)\nCreatures with ice counters on them don't untap during their controllers' untap steps.",
        '5', '5', ['R']),
    'Shaper Parasite': ('{1}{U}{U}', 3.0, 'Creature — Illusion',
        'Morph {2}{U} (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)\nWhen this creature is turned face up, target creature gets +2/-2 or -2/+2 until end of turn.',
        '2', '3', ['U']),
    'Shifting Ceratops': ('{2}{G}{G}', 4.0, 'Creature — Dinosaur',
        "This spell can't be countered.\nProtection from blue (This creature can't be blocked, targeted, dealt damage, enchanted, or equipped by anything blue.)\n{G}: This creature gains your choice of reach, trample, or haste until end of turn.",
        '5', '4', ['G']),
    'Silverquill Pledgemage': ('{1}{W/B}{W/B}', 3.0, 'Creature — Vampire Cleric',
        'Magecraft — Whenever you cast or copy an instant or sorcery spell, this creature gains your choice of flying or lifelink until end of turn.',
        '3', '1', ['B', 'W']),
    'Skyclaw Thrash': ('{3}{U}{R}', 5.0, 'Artifact Creature — Lizard Warrior',
        'Whenever this creature attacks, flip a coin. If you win the flip, this creature gets +1/+1 and gains flying until end of turn.',
        '4', '4', ['R', 'U']),
    'Song of Blood': ('{1}{R}', 2.0, 'Sorcery',
        'Mill four cards. Whenever a creature attacks this turn, it gets +1/+0 until end of turn for each creature card put into your graveyard this way.',
        None, None, ['R']),
    "Sorcerer's Strongbox": ('{4}', 4.0, 'Artifact',
        '{2}, {T}: Flip a coin. If you win the flip, sacrifice this artifact and draw three cards.',
        None, None, []),
    'Soul Collector': ('{3}{B}{B}', 5.0, 'Creature — Vampire',
        'Flying\nWhenever a creature dealt damage by this creature this turn dies, return that card to the battlefield under your control.\nMorph {B}{B}{B} (You may cast this card face down as a 2/2 creature for {3}. Turn it face up any time for its morph cost.)',
        '3', '4', ['B']),
    'Tavern Swindler': ('{1}{B}', 2.0, 'Creature — Human Rogue',
        '{T}, Pay 3 life: Flip a coin. If you win the flip, you gain 6 life.',
        '2', '2', ['B']),
    'Tears of Rage': ('{2}{R}{R}', 4.0, 'Instant',
        'Cast this spell only during the declare attackers step.\nAttacking creatures you control get +X/+0 until end of turn, where X is the number of attacking creatures. Sacrifice those creatures at the beginning of the next end step.',
        None, None, ['R']),
    'Triassic Egg': ('{4}', 4.0, 'Artifact',
        '{3}, {T}: Put a hatchling counter on this artifact.\nSacrifice this artifact: Choose one. Activate only if there are two or more hatchling counters on this artifact.\n• You may put a creature card from your hand onto the battlefield.\n• Return target creature card from your graveyard to the battlefield.',
        None, None, []),
    'Veteran Warleader': ('{1}{G}{W}', 3.0, 'Creature — Human Soldier Ally',
        "Veteran Warleader's power and toughness are each equal to the number of creatures you control.\nTap another untapped Ally you control: This creature gains your choice of first strike, vigilance, or trample until end of turn.",
        '*', '*', ['G', 'W']),
    'Volatile Rig': ('{4}', 4.0, 'Artifact Creature — Construct',
        'Trample\nThis creature attacks each combat if able.\nWhenever this creature is dealt damage, flip a coin. If you lose the flip, sacrifice this creature.\nWhen this creature dies, flip a coin. If you lose the flip, it deals 4 damage to each creature and each player.',
        '4', '4', []),
    'Wild Wurm': ('{3}{R}', 4.0, 'Creature — Wurm',
        "When this creature enters, flip a coin. If you lose the flip, return this creature to its owner's hand.",
        '5', '4', ['R']),
    'Wingnut, Bat on the Belfry': ('{1}{R}', 2.0, 'Legendary Creature — Bat Mutant',
        'Alliance — Whenever another creature you control enters, Wingnut gains your choice of flying, menace, or haste until end of turn.\nWhenever Wingnut attacks, each other attacking creature gets +1/+0 until end of turn.',
        '1', '2', ['R']),
}



def real(*names: str) -> list[dict[str, Any]]:
    out = []
    for i, n in enumerate(names):
        cost, cmc, type_line, text, power, toughness, colors = ORACLE[n]
        out.append(card(n, set_code="tst", number=f"P{i}", mana_cost=cost, cmc=cmc, type_line=type_line, oracle_text=text,
                        power=power, toughness=toughness, colors=colors, color_identity=colors))
    return out


EXTRA = real(*ORACLE)


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def cov(name: str) -> str:
    c = next(x for x in EXTRA if x["name"] == name)
    return coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level


def ability_of(s, c, needle):
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
    return next(a.index for a in ch.abilities if needle in a.text)


def decide_first(s, kind="choose_one", index=0):
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None and d.kind == kind:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == kind, d
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[index].id])
    return d


@pytest.mark.parametrize("name", sorted(ORACLE))
def test_still_full(name):
    assert cov(name) == "FULL", name


def flips(monkeypatch, *results):
    """The coins come up as asked, in order (the result is recorded on the step: a replay doesn't flip again)."""
    queue = list(results)

    def coin(rng, lo, hi):
        value = queue.pop(0) if len(queue) > 1 else queue[0]  # (the last result repeats)
        return 1 if value else 0

    monkeypatch.setattr("app.game.resolve._rng_int", coin)


def chars(s, c, pid="p1"):
    from app.rules.plan import Plan

    return Plan(s.state, pid, s.cards, None).ch(s.state.cards[c.id])


def activate(s, c, needle, **kw):
    act(s, "p1", type="activate_ability", card_id=c.id, ability=ability_of(s, c, needle), **kw)
    settle(s)


# -- choice grants with a protection option (608.2d, 702.16) ---------------------------------------------------------
def test_jodahs_avenger_gets_smaller_and_gains_protection_from_red(cards):
    s = build(cards, "Jodah's Avenger")
    av = put(s, "Jodah's Avenger")
    assert pt(s, av) == (4, 4)
    act(s, "p1", type="activate_ability", card_id=av.id, ability=0)
    d = decide_first(s, index=1)
    assert [o.label for o in d.options] == ["Double strike", "Protection from red", "Vigilance", "Shadow"]
    settle(s)
    assert pt(s, av) == (3, 3)
    ch = chars(s, av)
    assert "Protection from red." in [a.text for a in ch.abilities]  # (the keyword line, as printed ones are)
    check(s)


# -- "Double ~'s power" (Casey Jones) ----------------------------------------------------------------------------------
def test_casey_jones_doubles_its_power_and_any_player_may_pay(cards):
    s = build(cards, "Casey Jones, Asphalt Hooligan")
    casey = put(s, "Casey Jones, Asphalt Hooligan")
    assert pt(s, casey) == (2, 2)
    mana(s, C=4)
    activate(s, casey, "Double Casey")
    assert pt(s, casey) == (4, 2)
    mana(s, "p2", C=4)
    act(s, "p1", type="pass_priority")
    act(s, "p2", type="activate_ability", card_id=casey.id, ability=ability_of(s, casey, "Double Casey"))
    top = list(s.state.rules.stack.values())[-1]
    assert top.controller == "p2"
    settle(s)
    assert pt(s, casey) == (8, 2)  # (4 doubled: +4)
    check(s)


# -- "Draw a card at the beginning of the next turn's upkeep" -------------------------------------------------------
def test_jolt_draws_at_the_next_turns_upkeep(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, "Jolt", "Forest", "Forest")
    bear = tok(s, "p2", "Bear", "2/2")
    jolt = to_hand(s, "Jolt")
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=jolt.id, targets=[bear.id])
    settle(s)
    hand = len(s.state.zones["p1:hand"])
    assert s.state.cards[bear.id].tapped
    turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number == turn + 1 and s.state.turn.phase == "upkeep" and s.state.rules.priority is not None)
    until(s, lambda s: s.state.turn.phase == "draw")
    assert len(s.state.zones["p1:hand"]) == hand + 1  # Alice drew in Bob's upkeep (the next turn's); Bob did not draw for it
    check(s)


# -- Chronatog Totem -------------------------------------------------------------------------------------------------------
def test_chronatog_totem_pumps_only_as_a_creature_and_skips_a_turn(cards):
    s = build(cards, "Chronatog Totem")
    totem = put(s, "Chronatog Totem")
    idx = ability_of(s, totem, "+3/+3")
    with pytest.raises(ActionError):  # (an artifact, not a creature)
        act(s, "p1", type="activate_ability", card_id=totem.id, ability=idx)
    mana(s, U=1, C=1)
    activate(s, totem, "becomes a 1/2")
    act(s, "p1", type="activate_ability", card_id=totem.id, ability=idx)
    settle(s)
    assert pt(s, totem) == (4, 5)
    assert [(x["player"], x["what"]) for x in s.state.rules.skips] == [("p1", "turn")]
    with pytest.raises(ActionError):  # (once each turn)
        act(s, "p1", type="activate_ability", card_id=totem.id, ability=idx)
    check(s)


# -- flips -----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("heads", [True, False])
def test_bottle_of_suleiman_wins_a_djinn_or_hurts_its_owner(cards, monkeypatch, heads):
    flips(monkeypatch, heads)
    s = build(cards, "Bottle of Suleiman")
    bottle = put(s, "Bottle of Suleiman")
    mana(s, C=1)
    life = s.state.players["p1"].life
    activate(s, bottle, "Flip a coin")
    djinn = [c for c in s.state.cards.values() if c.name == "Djinn" and c.zone == "p1:battlefield"]
    assert len(djinn) == (1 if heads else 0)
    assert s.state.players["p1"].life == (life if heads else life - 5)
    check(s)


@pytest.mark.parametrize("heads", [True, False])
def test_puppets_verdict_destroys_by_power_after_the_flip(cards, monkeypatch, heads):
    flips(monkeypatch, heads)
    s = build(cards, "Puppet's Verdict")
    small, big = tok(s, "p2", "Small", "2/2"), tok(s, "p2", "Big", "3/3")
    pv = to_hand(s, "Puppet's Verdict")
    mana(s, R=2, C=1)
    act(s, "p1", type="cast_spell", card_id=pv.id)
    settle(s)
    assert (alive(s, small), alive(s, big)) == ((False, True) if heads else (True, False))
    check(s)


@pytest.mark.parametrize("heads", [True, False])
def test_tavern_swindler_pays_life_first_and_gains_six_on_a_win(cards, monkeypatch, heads):
    flips(monkeypatch, heads)
    s = build(cards, "Tavern Swindler")
    sw = put(s, "Tavern Swindler")
    s.state.rules.controlled_since[sw.id].turn = 0  # (not summoning sick, 302.6)
    life = s.state.players["p1"].life
    activate(s, sw, "Flip a coin")
    assert s.state.players["p1"].life == life - 3 + (6 if heads else 0)
    check(s)


@pytest.mark.parametrize("heads", [True, False])
def test_wild_wurm_returns_when_the_flip_is_lost(cards, monkeypatch, heads):
    flips(monkeypatch, heads)
    s = build(cards, "Wild Wurm")
    wurm = to_hand(s, "Wild Wurm")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=wurm.id)
    settle(s)
    assert s.state.cards[wurm.id].zone == ("p1:battlefield" if heads else "p1:hand")
    check(s)


@pytest.mark.parametrize("heads", [True, False])
def test_sorcerers_strongbox_draws_three_and_goes_on_a_win(cards, monkeypatch, heads):
    flips(monkeypatch, heads)
    s = build(cards, "Sorcerer's Strongbox", "Forest", "Forest", "Forest", "Forest")
    box = put(s, "Sorcerer's Strongbox")
    mana(s, C=2)
    hand = len(s.state.zones["p1:hand"])
    activate(s, box, "Flip a coin")
    assert len(s.state.zones["p1:hand"]) == hand + (3 if heads else 0)
    assert s.state.cards[box.id].zone == ("p1:graveyard" if heads else "p1:battlefield")
    check(s)


# -- "Whenever a creature dealt damage by this creature this turn dies" (Wight's family, 603.7c) ------------------------
def fight(cards, text, blocker="Grizzly Bears", pt_="4/4"):
    """Alice's attacker (a token with ``text``) is blocked by Bob's real ``blocker`` card; combat is played through."""
    s = sandbox(cards, p2=(blocker,))
    attacker = creature(s, "p1", "Hero", pt_, "Token Creature — Test", text)
    victim = put(s, blocker, "p2")
    combat_step(s)
    attack(s, (attacker, "p2"))
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": victim.id, "attacker_id": attacker.id}])
    settle(s)
    return s, attacker, victim


def test_dread_slaver_returns_the_dead_creature_as_a_black_zombie(cards):
    s, hero, bears = fight(cards, ORACLE["Dread Slaver"][3])
    got = s.state.cards[bears.id]
    assert got.zone == "p1:battlefield" and got.controller == "p1"
    ch = chars(s, bears)
    assert "B" in ch.colors and "G" in ch.colors and "Zombie" in ch.subtypes and "Bear" in ch.subtypes
    check(s)


def test_dread_slaver_has_nothing_to_return_for_a_token(cards):
    s = sandbox(cards)
    hero = creature(s, "p1", "Hero", "4/4", "Token Creature — Test", ORACLE["Dread Slaver"][3])
    token = creature(s, "p2", "Pawn", "2/2")
    combat_step(s)
    attack(s, (hero, "p2"))
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": token.id, "attacker_id": hero.id}])
    settle(s)
    assert not [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Pawn"]
    check(s)


def test_soul_collector_returns_the_card_under_its_controller(cards):
    s, hero, bears = fight(cards, ORACLE["Soul Collector"][3].split("\n")[1])
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def test_abattoir_ghoul_gains_the_toughness_the_creature_had(cards):
    s = sandbox(cards, p2=("Grizzly Bears",))
    ghoul = creature(s, "p1", "Ghoul", "5/5", "Token Creature — Zombie", ORACLE["Abattoir Ghoul"][3])
    bears = put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="counter", card_ids=[bears.id], kind="+0/+1", delta=2)  # (toughness 4 when it dies)
    combat_step(s)
    life = s.state.players["p1"].life
    attack(s, (ghoul, "p2"))
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bears.id, "attacker_id": ghoul.id}])
    settle(s)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    assert s.state.players["p1"].life == life + 4
    check(s)


# -- spells with a delayed combat effect -----------------------------------------------------------------------------
def to_main1(s):
    from tests.game_helpers import turn_on

    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1


def test_song_of_blood_counts_the_creature_cards_milled(cards):
    s = sandbox(cards, "Song of Blood", "Grizzly Bears", "Llanowar Elves", "Soul Warden", "Merfolk Looter", "Albino Troll")
    hero = creature(s, "p1", "Hero", "2/2")
    song = to_hand(s, "Song of Blood")
    to_main1(s)
    before = set(s.state.zones["p1:graveyard"])
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=song.id)
    settle(s)
    milled = [c for c in s.state.zones["p1:graveyard"] if c not in before and c != song.id]
    n = len([c for c in milled if s.state.cards[c].name != "Forest"])  # (the creature cards)
    assert len(milled) == 4
    act(s, "p1", type="pass_priority")  # → combat
    attack(s, (hero, "p2"))
    assert pt(s, hero) == (2 + n, 2)
    check(s)


def test_tears_of_rage_pumps_by_the_attackers_and_sacrifices_them_at_the_end(cards):
    s = sandbox(cards, "Tears of Rage")
    a, b = creature(s, "p1", "A", "1/1"), creature(s, "p1", "B", "1/1")
    creature(s, "p2", "Guard", "0/4")  # (a creature of Bob: the declare attackers step is played, not skipped)
    tears = to_hand(s, "Tears of Rage")
    combat_step(s)
    act(s, "p1", type="set_prefs", full_control=True)  # (priority in the declare attackers step)
    attack(s, (a, "p2"), (b, "p2"))
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=tears.id)
    settle(s)
    assert pt(s, a) == (3, 1) and pt(s, b) == (3, 1)
    through_combat(s)
    assert s.state.players["p2"].life == 40 - 6
    until(s, lambda s: s.state.turn.phase == "cleanup" or s.state.turn.number > 1)
    assert not alive(s, a) and not alive(s, b)
    check(s)


def test_mage_hunters_onslaught_makes_each_blocker_cost_its_controller_life(cards):
    s = sandbox(cards, "Mage Hunters' Onslaught")
    hero = creature(s, "p1", "Hero", "2/2")
    victim = creature(s, "p2", "Victim", "2/2")
    guard = creature(s, "p2", "Guard", "3/3")
    onslaught = to_hand(s, "Mage Hunters' Onslaught")
    to_main1(s)
    mana(s, B=2, C=2)
    act(s, "p1", type="cast_spell", card_id=onslaught.id, targets=[victim.id])
    settle(s)
    assert not alive(s, victim)
    act(s, "p1", type="pass_priority")
    attack(s, (hero, "p2"))
    life = s.state.players["p2"].life
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": guard.id, "attacker_id": hero.id}])
    settle(s)
    assert s.state.players["p2"].life == life - 1
    check(s)


@pytest.mark.parametrize("heads", [True, False])
def test_mijae_djinn_leaves_combat_and_taps_when_the_flip_is_lost(cards, monkeypatch, heads):
    flips(monkeypatch, heads)
    s = sandbox(cards)
    djinn = creature(s, "p1", "Djinn", "5/6", "Token Creature — Djinn", ORACLE["Mijae Djinn"][3])
    combat_step(s)
    attack(s, (djinn, "p2"))
    settle(s)
    if heads:
        assert s.state.players["p2"].life == 40 - 5
    else:
        assert s.state.players["p2"].life == 40 and s.state.cards[djinn.id].tapped and s.state.cards[djinn.id].attacking is None
    check(s)


@pytest.mark.parametrize("heads", [True, False])
def test_skyclaw_thrash_grows_and_flies_only_on_a_win(cards, monkeypatch, heads):
    flips(monkeypatch, heads)
    s = sandbox(cards)
    thrash = creature(s, "p1", "Thrash", "3/3", "Token Artifact Creature — Lizard Warrior", ORACLE["Skyclaw Thrash"][3])
    combat_step(s)
    attack(s, (thrash, "p2"))
    settle(s)
    assert pt(s, thrash) == ((4, 4) if heads else (3, 3))
    assert ("flying" in chars(s, thrash).keywords) == heads
    check(s)


def test_volatile_rig_sacrifices_itself_and_then_blows_up(cards, monkeypatch):
    flips(monkeypatch, False, False)
    s = sandbox(cards)
    rig = creature(s, "p1", "Rig", "4/4", "Token Artifact Creature — Construct",
                   "Trample\nThis creature attacks each combat if able.\n" + ORACLE["Volatile Rig"][3].split("\n", 2)[2])
    guard = creature(s, "p2", "Guard", "1/1")
    bystander = creature(s, "p2", "Bystander", "3/3")
    combat_step(s)
    attack(s, (rig, "p2"))
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": guard.id, "attacker_id": rig.id}])
    settle(s)
    assert not alive(s, rig) and not alive(s, bystander)
    assert s.state.players["p1"].life == 36 and s.state.players["p2"].life == 33  # (3 trampled over, then 4)
    check(s)


# -- activated abilities with restrictions, modes and counters ---------------------------------------------------------
def test_triassic_egg_needs_two_hatchling_counters_and_returns_a_creature(cards):
    s = sandbox(cards, "Triassic Egg", "Grizzly Bears")
    egg = put(s, "Triassic Egg")
    bears = to_hand(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "graveyard"})
    to_main1(s)
    idx = ability_of(s, egg, "Choose one")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=egg.id, ability=idx, modes=[1], targets=[bears.id])
    act(s, "p1", type="counter", card_ids=[egg.id], kind="hatchling", delta=2)
    act(s, "p1", type="activate_ability", card_id=egg.id, ability=idx, modes=[1], targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[egg.id].zone == "p1:graveyard"
    check(s)


def test_oracles_vault_plays_for_free_only_with_three_brick_counters(cards):
    s = sandbox(cards, "Oracle's Vault")
    vault = put(s, "Oracle's Vault")
    to_main1(s)
    s.state.rules.controlled_since[vault.id].turn = 0
    free = ability_of(s, vault, "without paying")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=vault.id, ability=free)
    mana(s, C=2)
    activate(s, vault, "Put a brick counter")
    assert s.state.cards[vault.id].counters.get("brick") == 1 and s.state.cards[vault.id].tapped
    act(s, "p1", type="counter", card_ids=[vault.id], kind="brick", delta=2)
    act(s, "p1", type="tap", card_ids=[vault.id], tapped=False)
    top = s.state.zones["p1:library"][0]
    activate(s, vault, "without paying")
    assert s.state.cards[top].zone == "p1:exile"
    check(s)


def test_family_favor_shields_an_attacker_that_pays_for_a_card(cards):
    s = sandbox(cards, "Family's Favor")
    put(s, "Family's Favor")
    hero = creature(s, "p1", "Hero", "2/2")
    combat_step(s)
    hand = len(s.state.zones["p1:hand"])
    attack(s, (hero, "p2"))
    settle(s)
    through_combat(s)
    assert s.state.players["p2"].life == 38
    assert not s.state.cards[hero.id].counters.get("shield")  # (removed by the granted trigger)
    assert len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_charitable_levy_taxes_noncreature_spells_and_is_sacrificed_on_the_third(cards):
    s = sandbox(cards, "Charitable Levy", "Opt", "Lightning Bolt", "Giant Growth")
    levy = put(s, "Charitable Levy")
    bear = creature(s, "p2", "Bear", "4/4")
    spells = [(to_hand(s, "Opt"), {"U": 1, "C": 1}, []), (to_hand(s, "Lightning Bolt"), {"R": 1, "C": 1}, [bear.id]),
              (to_hand(s, "Giant Growth"), {"G": 1, "C": 1}, [bear.id])]
    to_main1(s)
    for i, (spell, paid, targets) in enumerate(spells):
        mana(s, **paid)
        if i == 0:  # (the tax is real: {U} alone doesn't cast Opt)
            s.state.players["p1"].mana = {"U": 1}
            with pytest.raises(ActionError):
                act(s, "p1", type="cast_spell", card_id=spell.id)
            s.state.players["p1"].mana = paid
        act(s, "p1", type="cast_spell", card_id=spell.id, **({"targets": targets} if targets else {}))
        settle(s)
    assert s.state.cards[levy.id].zone == "p1:graveyard"
    assert s.state.cards[levy.id].counters.get("collection") is None
    check(s)


# -- snow ({S}) activations ------------------------------------------------------------------------------------------------
def snow_table(cards, *names, forests=9, p2=()):
    """A sandbox with ``forests`` Snow-Covered Forests in play for Alice, rules on, in her first main phase."""
    s = sandbox(cards, *names, p2=p2)
    for _ in range(forests):
        act(s, "p1", type="create_token", player="p1", token={
            "name": "Snow-Covered Forest", "type_line": "Basic Snow Land — Forest", "power": None, "toughness": None, "text": "({T}: Add {G}.)"})
    return s


def test_ascendant_spirit_levels_up_with_snow_mana(cards):
    s = snow_table(cards, "Ascendant Spirit")
    spirit = put(s, "Ascendant Spirit")
    to_main1(s)
    activate(s, spirit, "Spirit Warrior with base")
    assert {"Spirit", "Warrior"} <= set(chars(s, spirit).subtypes) and pt(s, spirit) == (2, 3)
    activate(s, spirit, "If this creature is a Warrior")
    assert "Angel" in chars(s, spirit).subtypes and pt(s, spirit) == (4, 4)
    assert s.state.cards[spirit.id].counters.get("flying") == 1
    lands = [c for c in s.state.cards.values() if c.name == "Snow-Covered Forest"]
    assert sum(1 for c in lands if c.tapped) == 5
    check(s)


def test_a_non_snow_source_cannot_pay_snow_mana(cards):
    s = sandbox(cards, "Chilling Shade")
    shade = put(s, "Chilling Shade")
    for _ in range(3):
        act(s, "p1", type="create_token", player="p1", token={
            "name": "Forest", "type_line": "Basic Land — Forest", "power": None, "toughness": None, "text": "({T}: Add {G}.)"})
    to_main1(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=shade.id, ability=ability_of(s, shade, "{S}:"))
    check(s)


# -- energy, ice counters, "you may flip", delayed draws -----------------------------------------------------------------
def test_multiform_wonder_pays_energy_for_its_choices(cards):
    s = build(cards, "Multiform Wonder")
    wonder = to_hand(s, "Multiform Wonder")
    mana(s, C=5)
    act(s, "p1", type="cast_spell", card_id=wonder.id)
    settle(s)
    assert s.state.players["p1"].resources.get("energy") == 3
    act(s, "p1", type="activate_ability", card_id=wonder.id, ability=ability_of(s, wonder, "your choice of flying"))
    decide_first(s, index=2)  # lifelink
    settle(s)
    assert "lifelink" in chars(s, wonder).keywords and s.state.players["p1"].resources.get("energy") == 2
    act(s, "p1", type="activate_ability", card_id=wonder.id, ability=ability_of(s, wonder, "+2/-2"))
    decide_first(s, index=0)
    settle(s)
    assert pt(s, wonder) == (5, 1) and s.state.players["p1"].resources.get("energy") == 1
    check(s)


def test_rimescale_dragon_taps_and_freezes_a_creature(cards):
    s = snow_table(cards, "Rimescale Dragon", p2=())
    dragon = put(s, "Rimescale Dragon")
    bear = creature(s, "p2", "Bear", "2/2")
    to_main1(s)
    activate(s, dragon, "ice counter", targets=[bear.id])
    assert s.state.cards[bear.id].tapped and s.state.cards[bear.id].counters.get("ice") == 1
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1")
    assert s.state.cards[bear.id].tapped  # it didn't untap in its controller's untap step
    check(s)


@pytest.mark.parametrize("heads", [True, False])
def test_goblin_bomb_may_flip_each_upkeep(cards, monkeypatch, heads):
    flips(monkeypatch, heads)
    s = sandbox(cards, "Goblin Bomb")
    bomb = put(s, "Goblin Bomb")
    act(s, "p1", type="counter", card_ids=[bomb.id], kind="fuse", delta=2)
    turn_on_rules(s)
    until(s, lambda s: s.state.turn.number == 2)  # (the first upkeep's "you may flip" is answered: the first option, yes)
    assert s.state.cards[bomb.id].counters.get("fuse") == (3 if heads else 1)
    check(s)


def turn_on_rules(s):
    from tests.game_helpers import turn_on

    turn_on(s)


def test_immortus_adds_blue_per_card_drawn_for_noncreature_spells_only(cards):
    s = sandbox(cards, "Immortus, Master of Eternity", "Opt", "Merfolk Looter")
    im = put(s, "Immortus, Master of Eternity")
    opt, looter = to_hand(s, "Opt"), to_hand(s, "Merfolk Looter")
    to_main1(s)
    s.state.rules.controlled_since[im.id].turn = 0
    act(s, "p1", type="draw", player="p1", count=2)
    with pytest.raises(ActionError):  # (Immortus' mana can't pay for a creature spell)
        act(s, "p1", type="cast_spell", card_id=looter.id)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    settle(s)
    assert s.state.cards[im.id].tapped and s.state.cards[opt.id].zone == "p1:graveyard"
    check(s)
