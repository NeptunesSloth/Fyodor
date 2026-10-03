"""Wave 7R: the independent review of wave 7 (CR 2026-09-25): regressions for what it found, and the seams where
wave-7 features meet. Cards carry their real Oracle text, read from the card database."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave6c_tokens_pumps import card_named, mana, pt, put, reloaded, settle

# Real Oracle text (the card database, Scryfall bulk data of 2026-09): name -> (mana cost, mana value, type line, text, power,
# toughness, colors).
ORACLE = {
    'Lethal Vapors': ('{2}{B}{B}', 4.0, 'Enchantment',
        'Whenever a creature enters, destroy it.\n{0}: Destroy this enchantment. You skip your next turn. Any player may activate this ability.',
        None, None, ['B']),
    'Excavation': ('{1}{U}', 2.0, 'Enchantment',
        '{1}, Sacrifice a land: Draw a card. Any player may activate this ability.',
        None, None, ['U']),
    "Oona's Prowler": ('{1}{B}', 2.0, 'Creature — Faerie Rogue',
        'Flying\nDiscard a card: This creature gets -2/-0 until end of turn. Any player may activate this ability.',
        '3', '1', ['B']),
    'Flailing Soldier': ('{R}', 1.0, 'Creature — Human Soldier',
        '{1}: This creature gets +1/+1 until end of turn. Any player may activate this ability.\n{1}: This creature gets -1/-1 until end of turn. Any player may activate this ability.',
        '2', '2', ['R']),
    'Glimpse of Nature': ('{G}', 1.0, 'Sorcery',
        'Whenever you cast a creature spell this turn, draw a card.',
        None, None, ['G']),
    'Massacre Girl': ('{3}{B}{B}', 5.0, 'Legendary Creature — Human Assassin',
        'Menace\nWhen Massacre Girl enters, each other creature gets -1/-1 until end of turn. Whenever a creature dies this turn, each creature other than Massacre Girl gets -1/-1 until end of turn.',
        '4', '4', ['B']),
    'Heavy Fog': ('{1}{G}', 2.0, 'Instant',
        "Cast this spell only during the declare attackers step and only if you've been attacked this step.\nPrevent all damage that would be dealt to you this turn by attacking creatures.",
        None, None, ['G']),
    'Sceptre of Eternal Glory': ('{4}', 4.0, 'Legendary Artifact',
        '{T}: Add one mana of any color.\n{T}: Add three mana of any one color. Activate only if you control three or more lands with the same name.',
        None, None, []),
    'Ancient Hellkite': ('{4}{R}{R}{R}', 7.0, 'Creature — Dragon',
        'Flying\n{R}: This creature deals 1 damage to target creature defending player controls. Activate only if this creature is attacking.',
        '6', '6', ['R']),
    'Ether': ('{3}{U}', 4.0, 'Artifact',
        '{T}, Exile this artifact: Add {U}. When you next cast an instant or sorcery spell this turn, copy that spell. You may choose new targets for the copy.',
        None, None, ['U']),
    'Dark Fortress': ('', 0.0, 'Land',
        '{T}: Add {C}.\n{T}: Add {B} or {R}. Activate only if this land entered this turn or if you control a basic land.',
        None, None, []),
    'Mirrex': ('', 0.0, 'Land — Sphere',
        '{T}: Add {C}.\n{T}: Add one mana of any color. Activate only if this land entered this turn.\n{3}, {T}: Create a 1/1 colorless Phyrexian Mite artifact creature token with toxic 1 and "This token can\'t block." (Players dealt combat damage by it also get a poison counter.)',
        None, None, []),
    'Grim Wanderer': ('{1}{B}', 2.0, 'Creature — Goblin Warlock',
        'Flash\nTragic Backstory — Cast this spell only if a creature died this turn.',
        '5', '3', ['B']),
    'Hewed Stone Retainers': ('{3}', 3.0, 'Artifact Creature — Golem',
        "Cast this spell only if you've cast another spell this turn.",
        '4', '4', []),
    "Talara's Battalion": ('{1}{G}', 2.0, 'Creature — Elf Warrior',
        "Cast this spell only if you've cast another green spell this turn.\nTrample",
        '4', '3', ['G']),
    'Lure of Prey': ('{2}{G}{G}', 4.0, 'Instant',
        'Cast this spell only if an opponent cast a creature spell this turn.\nYou may put a green creature card from your hand onto the battlefield.',
        None, None, ['G']),
    'Crypt Sliver': ('{1}{B}', 2.0, 'Creature — Sliver',
        'All Slivers have "{T}: Regenerate target Sliver."',
        '1', '1', ['B']),
    'Chaotic Strike': ('{1}{R}', 2.0, 'Instant',
        'Cast this spell only during combat after blockers are declared.\nFlip a coin. If you win the flip, target creature gets +1/+1 until end of turn.\nDraw a card.',
        None, None, ['R']),
    'Master Warcraft': ('{2}{R/W}{R/W}', 4.0, 'Instant',
        'Cast this spell only before attackers are declared.\nYou choose which creatures attack this turn.\nYou choose which creatures block this turn and how those creatures block.',
        None, None, ['R', 'W']),
    'Rapid Fire': ('{3}{W}', 4.0, 'Instant',
        "Cast this spell only before blockers are declared.\nTarget creature gains first strike until end of turn. If it doesn't have rampage, that creature gains rampage 2 until end of turn. (Whenever the creature becomes blocked, it gets +2/+2 until end of turn for each creature blocking it beyond the first.)",
        None, None, ['W']),
    'Angelic Favor': ('{3}{W}', 4.0, 'Instant',
        "If you control a Plains, you may tap an untapped creature you control rather than pay this spell's mana cost.\nCast this spell only during combat.\nCreate a 4/4 white Angel creature token with flying. Exile it at the beginning of the next end step.",
        None, None, ['W']),
    'Necrologia': ('{3}{B}{B}', 5.0, 'Instant',
        'Cast this spell only during your end step.\nAs an additional cost to cast this spell, pay X life.\nDraw X cards.',
        None, None, ['B']),
    'Zelyon Sword': ('{3}', 3.0, 'Artifact',
        'You may choose not to untap this artifact during your untap step.\n{3}, {T}: Target creature gets +2/+0 for as long as this artifact remains tapped.',
        None, None, []),
    'Endling': ('{2}{B}{B}', 4.0, 'Creature — Zombie Shapeshifter',
        "{B}: This creature gains menace until end of turn.\n{B}: This creature gains deathtouch until end of turn.\n{B}: This creature gains undying until end of turn. (When this creature dies, if it had no +1/+1 counters on it, return it to the battlefield under its owner's control with a +1/+1 counter on it.)\n{1}: This creature gets +1/-1 or -1/+1 until end of turn.",
        '3', '3', ['B']),
    'Stature, Size Shifter': ('{U}', 1.0, 'Legendary Creature — Human Hero',
        "Stature can't be blocked if her power is 1 or less.\nPower-up — {X}{U}{U}: Put X +1/+1 counters on Stature. (Activate each power-up ability only once. Reduce the cost by her mana cost if she entered this turn.)",
        '1', '1', ['U']),
    'Wight': ('{1}{B}', 2.0, 'Creature — Zombie Soldier',
        'This creature enters tapped.\nLife Drain — Whenever a creature dealt damage by this creature this turn dies, create a tapped 2/2 black Zombie creature token and exile that card.',
        '3', '2', ['B']),
    'Myth Realized': ('{W}', 1.0, 'Enchantment',
        'Whenever you cast a noncreature spell, put a lore counter on this enchantment.\n{2}{W}: Put a lore counter on this enchantment.\n{W}: Until end of turn, this enchantment becomes a Monk Avatar creature in addition to its other types and gains "This creature\'s power and toughness are each equal to the number of lore counters on it."',
        None, None, ['W']),
    'Rammas Echor, Ancient Shield': ('{3}{W}', 4.0, 'Legendary Artifact',
        'Whenever you cast your second spell each turn, draw a card, then create a 0/3 white Wall creature token with defender.\nAt the beginning of combat on your turn, creatures you control with defender gain exalted until end of turn. (Whenever a creature you control attacks alone, it gets +1/+1 until end of turn for each instance of exalted among permanents you control.)',
        None, None, ['W']),
    'Sphere of the Suns': ('{2}', 2.0, 'Artifact',
        'This artifact enters tapped and with three charge counters on it.\n{T}, Remove a charge counter from this artifact: Add one mana of any color.',
        None, None, []),
    # (made up: Wight's ability on a creature that can deal the damage)
    'Probe Pinger': ('{2}{B}', 3.0, 'Creature — Zombie',
        "{T}: This creature deals 1 damage to target creature.\nWhenever a creature dealt damage by this creature this turn dies, "
        "create a tapped 2/2 black Zombie creature token and exile that card.", '1', '1', ['B']),
}


def real(*names: str) -> list[dict[str, Any]]:
    out = []
    for i, n in enumerate(names):
        cost, cmc, type_line, text, power, toughness, colors = ORACLE[n]
        out.append(card(n, set_code="tst", number=f"R{i}", mana_cost=cost, cmc=cmc, type_line=type_line, oracle_text=text,
                        power=power, toughness=toughness, colors=colors, color_identity=colors))
    return out


EXTRA = real(*ORACLE)


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, *names, p2=(), players=2):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in names), (9, "Forest")])
    seats = [PlayerSetup("Alice", cards=alice),
             PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (10, "Island")]))]
    if players == 3:
        seats.append(PlayerSetup("Cara", cards=deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])))
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    for pid in s.state.players:
        act(s, pid, type="set_prefs", response="on")  # (an action, so the replay has it too)
    return s


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def ability(s, c, needle):
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
    return next(a.index for a in ch.abilities if needle in a.text)


def test_lethal_vapors_the_activator_skips_their_turn(cards):
    """602.2a: whoever activates "Any player may activate this ability" controls it, so "You skip your next turn" is theirs."""
    s = build(cards, "Lethal Vapors")
    vapors = put(s, "Lethal Vapors")
    idx = ability(s, vapors, "Destroy this")
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    act(s, "p2", type="activate_ability", card_id=vapors.id, ability=idx)
    top = list(s.state.rules.stack.values())[-1]
    assert top.controller == "p2"
    settle(s)
    assert s.state.cards[vapors.id].zone == "p1:graveyard"
    assert [(x["player"], x["what"]) for x in s.state.rules.skips] == [("p2", "turn")]  # (Bob, the activator, skips; not Alice)
    check(s)


def to_hand(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def tok(s, pid, name, pt):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": "Token Creature — Test", "power": p,
                                                         "toughness": t, "text": ""})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def alive(s, c):
    return c.id in s.state.cards and s.state.cards[c.id].zone.endswith("battlefield")


def test_massacre_girl_keeps_shrinking_while_creatures_keep_dying(cards):
    """Massacre Girl: the ETB -1/-1 kills the 1/1s, each death (also the later ones) shrinks everything else again (603.7)."""
    s = build(cards, "Massacre Girl")
    a, b, c = tok(s, "p2", "A", "1/1"), tok(s, "p2", "B", "2/2"), tok(s, "p2", "C", "3/3")
    d = tok(s, "p1", "D", "1/1")
    girl = to_hand(s, "Massacre Girl")
    mana(s, B=2, C=3)
    act(s, "p1", type="cast_spell", card_id=girl.id)
    settle(s)
    assert not any(alive(s, x) for x in (a, b, c, d))
    assert s.state.cards[girl.id].zone == "p1:battlefield"
    assert pt(s, girl) == (4, 4)
    check(s)


def test_ancient_hellkite_pings_only_the_defending_players_creatures(cards):
    """508.5: "defending player" is the player it attacks; a creature of the third player is no target."""
    from tests.test_rules_conditionals import attack, combat_step, creature, sandbox

    s = sandbox(cards, "Ancient Hellkite", players=3)
    hk = put(s, "Ancient Hellkite")
    bob = creature(s, "p2", "Bobby", "2/2")
    carol = creature(s, "p3", "Carolyn", "2/2")
    combat_step(s)
    act(s, "p1", type="set_prefs", full_control=True)
    idx = ability(s, hk, "defending player")
    mana(s, R=2)
    with pytest.raises(ActionError):  # (not attacking yet: "Activate only if this creature is attacking")
        act(s, "p1", type="activate_ability", card_id=hk.id, ability=idx, targets=[bob.id])
    attack(s, (hk, "p2"))
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=hk.id, ability=idx, targets=[carol.id])
    act(s, "p1", type="activate_ability", card_id=hk.id, ability=idx, targets=[bob.id])
    settle(s)
    assert s.state.cards[bob.id].damage == 1
    check(s)


def test_sceptre_of_eternal_glory_needs_three_lands_with_the_same_name(cards):
    from app.rules import casting

    s = build(cards, "Sceptre of Eternal Glory")
    sceptre = put(s, "Sceptre of Eternal Glory")
    info = Plan(s.state, "p1", s.cards, None).info
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"]
    for f in forests[:2]:
        act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    assert len(dict(casting.mana_abilities(s.state, s.state.cards[sceptre.id], info))) == 1
    act(s, "p1", type="move", card_ids=[forests[2].id], to={"player": "p1", "zone": "battlefield"})
    assert len(dict(casting.mana_abilities(s.state, s.state.cards[sceptre.id], info))) == 2


def test_dark_fortress_and_mirrex_lose_their_colors_once_they_are_old(cards):
    """"Activate only if this land entered this turn or if you control a basic land" is judged each time (mana ability)."""
    from app.rules import casting
    from tests.test_rules_conditionals import to_turn

    s = build(cards, "Dark Fortress", "Mirrex")
    fortress, mirrex = put(s, "Dark Fortress"), put(s, "Mirrex")

    def options(c):
        info = Plan(s.state, "p1", s.cards, None).info
        return len(dict(casting.mana_abilities(s.state, s.state.cards[c.id], info)))

    assert options(fortress) == 2 and options(mirrex) == 2  # (both entered this turn)
    to_turn(s, 3)
    assert options(fortress) == 1 and options(mirrex) == 1
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    assert options(fortress) == 2 and options(mirrex) == 1  # (a basic land counts for the Fortress only)
    check(s)


def cast_problem(s, c, pid="p1"):
    from app.rules import casting

    plan = Plan(s.state, pid, s.cards, None)
    return casting.cast_problem(s.state, pid, s.state.cards[c.id], plan.ch(s.state.cards[c.id]), info=plan.info)


@pytest.mark.parametrize(("name", "needs"), [("Grim Wanderer", "creature died"), ("Hewed Stone Retainers", "another spell"),
                                              ("Talara's Battalion", "green spell"), ("Lure of Prey", "opponent cast a creature")])
def test_cast_only_if_conditions_are_enforced(cards, name, needs):
    s = build(cards, name)
    act(s, "p1", type="set_prefs", full_control=True)
    c = to_hand(s, name)
    why = cast_problem(s, c)
    assert why is not None and needs in why, why
    check(s)


def test_grim_wanderer_after_a_creature_died(cards):
    s = build(cards, "Grim Wanderer")
    act(s, "p1", type="set_prefs", full_control=True)
    c = to_hand(s, "Grim Wanderer")
    x = tok(s, "p2", "Doomed", "1/1")
    act(s, "p1", type="move", card_ids=[x.id], to={"player": "p2", "zone": "graveyard"})
    assert cast_problem(s, c) is None


def test_crypt_sliver_gives_every_sliver_a_regenerate_ability(cards):
    """"All Slivers have '{T}: Regenerate target Sliver.'": the Sliver taps itself to save itself from Murder."""
    from tests.test_rules_conditionals import to_turn

    s = build(cards, "Crypt Sliver", "Murder")
    sliver = put(s, "Crypt Sliver")
    to_turn(s, 3)
    assert s.state.turn.active_player == "p1"
    act(s, "p1", type="set_prefs", hold_priority=True)
    murder = to_hand(s, "Murder")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[sliver.id])
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[sliver.id])
    idx = next(a.index for a in ch.abilities if a.text.startswith("{T}: Regenerate target Sliver"))
    act(s, "p1", type="activate_ability", card_id=sliver.id, ability=idx, targets=[sliver.id])
    settle(s)
    assert s.state.cards[sliver.id].zone == "p1:battlefield" and s.state.cards[sliver.id].tapped
    check(s)


def test_after_blockers_needs_a_declare_blockers_step(cards):
    """506.8f / 508.8: with no attackers there is no declare blockers step, so "after blockers are declared" never comes."""
    from app.rules import casting

    s = build(cards, "Chaotic Strike")
    c = to_hand(s, "Chaotic Strike")

    def problem():
        plan = Plan(s.state, "p1", s.cards, None)
        return casting.cast_problem(s.state, "p1", s.state.cards[c.id], plan.ch(s.state.cards[c.id]), check_priority=False,
                                    info=plan.info)

    s.state.turn.phase = "end_combat"
    s.state.rules.no_attackers = True
    assert problem() is not None and "after blockers" in problem()
    s.state.rules.no_attackers = False  # (creatures attacked: the step happened)
    assert problem() is None


def test_before_a_point_in_combat_means_the_first_combat_only(cards):
    """506.8d: "Cast this spell only before attackers are declared" (no "during combat") is about the first combat phase."""
    from app.rules import casting

    s = build(cards, "Master Warcraft", "Rapid Fire")
    for name in ("Master Warcraft", "Rapid Fire"):
        c = to_hand(s, name)
        plan = Plan(s.state, "p1", s.cards, None)
        s.state.turn.phase = "begin_combat"
        s.state.rules.combats = 1
        assert casting.cast_problem(s.state, "p1", s.state.cards[c.id], plan.ch(s.state.cards[c.id]), check_priority=False,
                                    info=plan.info) is None, name
        s.state.rules.combats = 2  # (an additional combat phase)
        assert "506.8d" in (casting.cast_problem(s.state, "p1", s.state.cards[c.id], plan.ch(s.state.cards[c.id]),
                                                 check_priority=False, info=plan.info) or ""), name


def test_angelic_favor_taps_a_creature_in_combat_and_the_angel_leaves_at_the_end(cards):
    """Free cast by tapping an untapped creature (118.9, not a {T} cost: a summoning-sick one is fine), during combat only
    (506.8c), and the Angel is exiled at the beginning of the next end step."""
    from app.rules.view import hints
    from tests.test_rules_conditionals import until

    s = build(cards, "Angelic Favor")
    act(s, "p1", type="set_prefs", full_control=True)
    fav = to_hand(s, "Angelic Favor")
    act(s, "p1", type="create_token", player="p1", token={"name": "Plains", "type_line": "Basic Land — Plains", "power": None,
                                                           "toughness": None, "text": ""})
    bear = tok(s, "p1", "Bear", "2/2")
    with pytest.raises(ActionError):  # (main phase: not during combat)
        act(s, "p1", type="cast_spell", card_id=fav.id, alt_cost=f"{fav.id}:0")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[])
    until(s, lambda s: s.state.turn.phase in ("end_combat",) or s.state.rules.priority == "p1" and s.state.turn.phase == "begin_combat")
    found = hints(s.state, "p1", s.cards).get("alt_castable", {}).get(fav.id)
    assert found, "the alternative cost is offered"
    act(s, "p1", type="cast_spell", card_id=fav.id, alt_cost=found[0]["id"])
    settle(s)
    assert s.state.cards[bear.id].tapped
    angel = next(c for c in s.state.cards.values() if c.name == "Angel" and c.zone == "p1:battlefield")
    check(s)
    cast_turn = s.state.turn.number
    until(s, lambda s: s.state.turn.number > cast_turn)
    assert angel.id not in s.state.cards or s.state.cards[angel.id].zone != "p1:battlefield"
    check(s)


def test_heavy_fog_is_not_castable_when_only_a_planeswalker_is_attacked(cards):
    """Heavy Fog ruling (2009-10-01): "If all the attacking creatures attack your planeswalkers, you can't cast Heavy Fog.
    To cast it, a creature needs to have attacked you." """
    from tests.test_rules_conditionals import until

    s = build(cards, "Heavy Fog", "Gideon Jura")
    act(s, "p1", type="set_prefs", full_control=True)
    fog = to_hand(s, "Heavy Fog")
    gideon = put(s, "Gideon Jura")
    act(s, "p1", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    act(s, "p2", type="create_token", player="p2", token={"name": "Raider", "type_line": "Token Creature — Bear", "power": "2",
                                                         "toughness": "2", "text": "Haste"})
    raider = next(c for c in s.state.cards.values() if c.name == "Raider")
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.rules.decision is not None
          and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": raider.id, "target": gideon.id}])
    until(s, lambda s: s.state.rules.priority == "p1" and s.state.turn.phase == "declare_attackers")
    why = cast_problem(s, fog)
    assert why is not None and "attacked" in why, why
    # (and the same Raider attacking Alice herself would allow it: the sibling test in wave 7A)


def test_necrologia_pays_x_life_in_your_end_step_and_draws_x(cards):
    from tests.test_rules_conditionals import until

    s = build(cards, "Necrologia")
    act(s, "p1", type="set_prefs", full_control=True)
    nec = to_hand(s, "Necrologia")
    mana(s, B=2, C=3)
    with pytest.raises(ActionError, match="end step"):
        act(s, "p1", type="cast_spell", card_id=nec.id, x_value=3)
    until(s, lambda s: s.state.turn.phase == "end" and s.state.turn.active_player == "p1" and s.state.rules.priority == "p1")
    life, hand = s.state.players["p1"].life, len(s.state.zones["p1:hand"])
    mana(s, B=2, C=3)
    with pytest.raises(ActionError):  # (more life than she has)
        act(s, "p1", type="cast_spell", card_id=nec.id, x_value=life + 1)
    act(s, "p1", type="cast_spell", card_id=nec.id, x_value=3)
    settle(s)
    assert s.state.players["p1"].life == life - 3 and len(s.state.zones["p1:hand"]) == hand - 1 + 3
    check(s)


@pytest.mark.parametrize("keep", [True, False])
def test_zelyon_sword_pumps_while_it_stays_tapped(cards, keep):
    """611.2b + 502.3: "+2/+0 for as long as this artifact remains tapped"; its controller may keep it tapped (the pump
    stays) or let it untap (the pump ends)."""
    from tests.test_rules_wave7f_untap_choice import play_to

    s = build(cards, "Zelyon Sword")
    sword = put(s, "Zelyon Sword")
    bear = tok(s, "p1", "Bear", "2/2")
    mana(s, C=3)
    idx = ability(s, sword, "+2/+0")
    act(s, "p1", type="activate_ability", card_id=sword.id, ability=idx, targets=[bear.id])
    settle(s)
    assert pt(s, bear) == (4, 2) and s.state.cards[sword.id].tapped
    check(s)
    play_to(s, 3, keep=(sword.id,) if keep else ())
    assert pt(s, bear) == ((4, 2) if keep else (2, 2))
    assert s.state.cards[sword.id].tapped == keep
    check(s)


def test_a_pending_choice_survives_a_save_and_load(cards):
    """"gets +1/-1 or -1/+1" (608.2d): the choice is a decision made as the ability resolves; the table can be saved and
    loaded while it waits, and the choice is the controller's alone."""
    s = build(cards, "Endling")
    endling = put(s, "Endling")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=endling.id, ability=ability(s, endling, "+1/-1"))
    for _ in range(6):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.player == "p1" and [o.label for o in d.options] == ["+1/-1", "-1/+1"]
    loaded = GameSession(type(s.state).model_validate_json(s.state.model_dump_json()), cards=s.cards)
    assert loaded.state.rules.decision.id == d.id
    other = "p2"
    with pytest.raises(ActionError):
        act(loaded, other, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    act(loaded, "p1", type="choose", decision_id=d.id, option_ids=[d.options[1].id])
    settle(loaded)
    assert pt(loaded, endling) == (2, 4)  # (a 3/3 gets -1/+1)


def test_power_up_reduction_keeps_x(cards):
    """702.193a/b: Stature ({U}) entered this turn: {X}{U}{U} costs {X}{U}; the X of the cost stays an X."""
    from app.rules.casting import ability_cost

    s = build(cards, "Stature, Size Shifter")
    stature = put(s, "Stature, Size Shifter")
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[stature.id])
    ab = next(a for a in ch.abilities if a.text.startswith("Power-up"))
    cost = ability_cost(ch, ab, state=s.state, card=s.state.cards[stature.id], info=s.cards)
    assert cost.mana == "{X}{U}"
    mana(s, U=1, G=2)
    act(s, "p1", type="activate_ability", card_id=stature.id, ability=ab.index, x_value=2)
    settle(s)
    assert s.state.cards[stature.id].counters.get("+1/+1") == 2
    check(s)


def test_wight_exiles_the_dead_card_not_its_new_token(cards):
    """"… create a tapped 2/2 black Zombie creature token and exile that card": the card is the creature that died, not the
    token (a token is no card): the pronoun reader used to bind it to the token and exile that. A Pinger with Wight's ability
    kills Llanowar Elves: the Elves card is exiled and the tapped Zombie stays."""
    from app.rules import coverage, scripts
    from tests.test_rules_conditionals import to_turn
    from tests.test_rules_scripts import ch as characteristics

    wight = real("Wight")[0]
    chs = characteristics(wight["name"], wight["type_line"], wight["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL"
    drain = next(d for d in scripts.definitions(chs).values() if d.get("kind") == "triggered")
    assert [e["do"] for e in drain["effects"]] == ["exile", "create_token"] and drain["effects"][0]["who"] == "event.new"
    # a sentence with another verb, or the token as the object, is not read
    assert scripts.parse_effects("Create a 1/1 white Soldier creature token and return that card to its owner's hand.") is None

    s = build(cards, "Probe Pinger", p2=("Llanowar Elves",))
    pinger = put(s, "Probe Pinger")
    elves = put(s, "Llanowar Elves", "p2")
    to_turn(s, 3)
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=ability(s, pinger, "{T}: This creature deals 1"),
        targets=[elves.id])
    settle(s)
    assert s.state.cards[elves.id].zone == "p2:exile"
    zombies = [c for c in s.state.cards.values() if c.name == "Zombie" and c.zone == "p1:battlefield"]
    assert len(zombies) == 1 and zombies[0].tapped
    check(s)


def test_myth_realized_becomes_as_big_as_its_lore_counters(cards):
    """A granted characteristic-defining ability (604.3, 613.4a): 3 lore counters make the animated Enchantment a 3/3."""
    s = build(cards, "Myth Realized")
    myth = put(s, "Myth Realized")
    act(s, "p1", type="counter", card_ids=[myth.id], kind="lore", delta=3)
    mana(s, W=1)
    act(s, "p1", type="activate_ability", card_id=myth.id, ability=ability(s, myth, "becomes a Monk Avatar"))
    settle(s)
    assert s.state.cards[myth.id].zone == "p1:battlefield"
    assert pt(s, myth) == (3, 3)
    act(s, "p1", type="counter", card_ids=[myth.id], kind="lore", delta=1)
    assert pt(s, myth) == (4, 4)
    check(s)


def test_base_power_and_toughness_effect_keeps_everything_else(cards):
    """"target creature you control has base power and toughness 4/4 until end of turn" (Voice of the Vermin): layer 7b only
    (613.4b): the creature keeps its types, colors and abilities, and its counters still apply on top."""
    s = build(cards)
    act(s, "p1", type="create_token", player="p1", token={"name": "Probe Lord", "type_line": "Token Creature — Rat", "power": "1",
                                                           "toughness": "1", "colors": ["B"], "text": "{0}: Target creature you control has base power and toughness 4/4 until end of turn."})
    lord = card_named(s, "Probe Lord")
    act(s, "p1", type="create_token", player="p1", token={"name": "Probe Bear", "type_line": "Token Creature — Bear", "power": "2",
                                                           "toughness": "2", "colors": ["G"], "text": "Flying"})
    bear = card_named(s, "Probe Bear")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=1)
    act(s, "p1", type="activate_ability", card_id=lord.id, ability=0, targets=[bear.id])
    settle(s)
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id])
    assert pt(s, bear) == (5, 5)  # (base 4/4, plus the +1/+1 counter)
    assert ch.subtypes == frozenset({"Bear"}) and ch.colors == frozenset({"G"}) and "flying" in ch.keywords
    check(s)


def test_wrath_of_god_cannot_regenerate_but_a_shield_counter_still_saves(cards):
    """122.1c: the shield counter is its own replacement effect ("destroyed as the result of an effect, instead remove a shield
    counter"), so "can't be regenerated" doesn't stop it; the creature without one dies."""
    s = build(cards, "Wrath of God")
    shielded, plain = tok(s, "p1", "Shielded", "2/2"), tok(s, "p2", "Plain", "2/2")
    act(s, "p1", type="counter", card_ids=[shielded.id], kind="shield", delta=1)
    wrath = to_hand(s, "Wrath of God")
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=wrath.id)
    settle(s)
    assert alive(s, shielded) and not alive(s, plain)
    assert s.state.cards[shielded.id].counters.get("shield", 0) == 0
    check(s)


def test_rammas_echor_gives_defenders_exalted_that_really_triggers(cards):
    """"creatures you control with defender gain exalted until end of turn": a granted keyword line (702.83a) works like a
    printed one: two Walls = two instances; the lone attacker gets +1/+1 for each (702.83b)."""
    from tests.test_rules_conditionals import until

    s = build(cards, "Rammas Echor, Ancient Shield")
    put(s, "Rammas Echor, Ancient Shield")
    for name in ("Wall A", "Wall B"):
        act(s, "p1", type="create_token", player="p1", token={"name": name, "type_line": "Token Creature — Wall", "power": "0",
                                                                "toughness": "3", "text": "Defender"})
    act(s, "p1", type="create_token", player="p1", token={"name": "Runner", "type_line": "Token Creature — Bear", "power": "2",
                                                            "toughness": "2", "text": "Haste"})
    runner = card_named(s, "Runner")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers"
          and s.state.turn.active_player == "p1")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": runner.id, "target": "p2"}])
    until(s, lambda s: s.state.turn.phase == "declare_blockers")
    assert pt(s, runner) == (4, 4), pt(s, runner)
    check(s)


def test_sphere_of_the_suns_enters_tapped_and_runs_out_of_charge(cards):
    """"{T}, Remove a charge counter: Add one mana of any color" as a mana ability: three uses, then nothing (it enters
    tapped with three charge counters)."""
    from tests.test_rules_conditionals import until

    s = build(cards, "Sphere of the Suns")
    act(s, "p1", type="set_prefs", full_control=True)
    sphere = to_hand(s, "Sphere of the Suns")
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=sphere.id)
    settle(s)
    card = s.state.cards[sphere.id]
    assert card.zone == "p1:battlefield" and card.tapped and card.counters.get("charge") == 3
    start = s.state.turn.number
    for expected in (3, 2, 1, 0):
        until(s, lambda s, after=start: s.state.turn.number > after and s.state.turn.active_player == "p1"
              and s.state.turn.phase == "main1")
        start = s.state.turn.number
        assert s.state.cards[sphere.id].counters.get("charge", 0) == expected
        idx = ability(s, sphere, "Remove a charge counter")
        if expected:
            act(s, "p1", type="activate_ability", card_id=sphere.id, ability=idx, mana_choice="G")
            assert s.state.cards[sphere.id].counters.get("charge", 0) == expected - 1
        else:
            with pytest.raises(ActionError):
                act(s, "p1", type="activate_ability", card_id=sphere.id, ability=idx, mana_choice="G")
    check(s)


def test_any_player_activation_taps_the_activators_lands_not_the_controllers(cards):
    """602.2a / 118.3: the player who activates pays; Bob's Island is tapped for Alice's Flailing Soldier, her Forest is not."""
    s = build(cards, "Flailing Soldier")
    soldier = put(s, "Flailing Soldier")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    act(s, "p2", type="activate_ability", card_id=soldier.id, ability=ability(s, soldier, "+1/+1"))
    assert s.state.cards[island.id].tapped and not s.state.cards[forest.id].tapped
    settle(s)
    assert pt(s, soldier) == (3, 3)
    check(s)
