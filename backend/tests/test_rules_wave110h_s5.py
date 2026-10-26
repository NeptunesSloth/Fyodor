"""Wave 110H session 5: one-card builds on real Oracle text (each scenario checks replay and a save/load round trip).

* Bloodfeather Phoenix: damage to an opponent or a battle (120.3, 310.5) by an instant or sorcery you control; {R} returns it from the graveyard.
* The Spot, Living Portal: put on the bottom of its owner's library; if it got there, the exiled cards return to their owners' hands (608.2c).
* Rampaging Raptor: its damage goes to a planeswalker the damaged player controls or a battle that player protects (310.8, 120.3); not a battle another player protects.
* Mysterious Limousine: a new exile sends the older linked cards back to the battlefield under their owners' control; no new exile (no target) leaves them (607.2a).
* Lamplight Phoenix: "exile it and collect evidence 4" is one optional cost (701.59a, 118.12); only if all of it is paid does the card return tapped.
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, check, life, mana, put, to_hand

SIEGE = "Invasion of Pyrulea // Gargantuan Slabhorn"
_FACES = [
    {"object": "card_face", "name": "Invasion of Pyrulea", "mana_cost": "{G}{U}", "type_line": "Battle \u2014 Siege", "defense": "4",
     "oracle_text": "(As a Siege enters, choose an opponent to protect it. You and others can attack it. When it's defeated, exile it, then cast it transformed.)\nWhen this Siege enters, scry 3, then reveal the top card of your library. If it's a land or double-faced card, draw a card."},
    {"object": "card_face", "name": "Gargantuan Slabhorn", "mana_cost": "", "type_line": "Creature \u2014 Beast", "power": "4", "toughness": "4",
     "oracle_text": "Trample, ward {2}\nOther transformed permanents you control have trample and ward {2}."},
]
EXTRA = [
    card(SIEGE, set_code="tst", number="110H-P", layout="transform", mana_cost="{G}{U} // ", cmc=2.0, type_line="Battle \u2014 Siege // Creature \u2014 Beast",
         colors=["G", "U"], color_identity=["G", "U"], card_faces=_FACES,
         oracle_text="\n//\n".join(f["oracle_text"] for f in _FACES), keywords=["Transform", "Trample", "Ward", "Scry"]),
    real("Bloodfeather Phoenix", "{2}{R}", 3, "Creature \u2014 Phoenix",
         "Flying\nThis creature can't block.\nWhenever an instant or sorcery spell you control deals damage to an opponent or battle, you may pay {R}. "
         "If you do, return this card from your graveyard to the battlefield. It gains haste until end of turn.", ("3", "2"), "R"),
    real("The Spot, Living Portal", "{2}{W}{U}{B}", 5, "Legendary Creature \u2014 Human Villain",
         "When The Spot enters, exile up to one other target nonland permanent and up to one target nonland permanent card from a graveyard.\n"
         "When The Spot dies, put him on the bottom of his owner's library. If you do, return the exiled cards to their owners' hands.", ("4", "4"), "WUB"),
    real("Rampaging Raptor", "{2}{R}{R}", 4, "Creature \u2014 Dinosaur",
         "Trample, haste\n{2}{R}: This creature gets +2/+0 until end of turn.\nWhenever this creature deals combat damage to an opponent, it deals that much damage to "
         "target planeswalker that player controls or battle that player protects.", ("4", "4"), "R"),
    {**real("Test Walker", "{3}", 3, "Legendary Planeswalker \u2014 Test", "", None, ""), "loyalty": "5"},
    real("Mysterious Limousine", "{3}{B}", 4, "Artifact \u2014 Vehicle",
         "Whenever this Vehicle enters or attacks, exile up to one other target creature until this Vehicle leaves the battlefield. If a creature is put into "
         "exile this way, return each other card exiled with this Vehicle to the battlefield under its owner's control.\nCrew 2", ("4", "4"), "B"),
    real("Grizzly Bears", "{1}{G}", 2, "Creature \u2014 Bear", "", ("2", "2"), "G"),
    real("Murder", "{1}{B}{B}", 3, "Instant", "Destroy target creature.", None, "B"),
    real("Lightning Bolt", "{R}", 1, "Instant", "Lightning Bolt deals 3 damage to any target.", None, "R"),

    real("Lamplight Phoenix", "{2}{R}{R}", 4, "Creature \u2014 Phoenix Spirit",
         "Flying\nWhen this creature dies, you may exile it and collect evidence 4. If you do, return this card to the battlefield tapped. "
         "(To collect evidence 4, exile cards with total mana value 4 or greater from your graveyard.)", ("4", "3"), "R"),
    real("Wolverine, Fierce Fighter", "{2}{R}{G}", 4, "Legendary Creature \u2014 Mutant Berserker Hero",
         "Haste\nWhen Wolverine enters, he fights up to one other target creature.\nIf damage would be dealt to Wolverine, instead that damage is dealt, "
         "but all other damage already dealt to him is healed.", ("3", "5"), "RG"),
    real("Freyalise's Winds", "{2}{G}{G}", 4, "Enchantment",
         "Whenever a permanent becomes tapped, put a wind counter on it.\nIf a permanent with a wind counter on it would untap during its controller's untap step, "
         "remove all wind counters from it instead.", None, "G"),
    real("Saproling Burst", "{3}{G}{G}", 5, "Enchantment",
         "Fading 7 (This enchantment enters with seven fade counters on it. At the beginning of your upkeep, remove a fade counter from it. If you can't, sacrifice it.)\n"
         "Remove a fade counter from this enchantment: Create a green Saproling creature token. It has \"This token's power and toughness are each equal to the number of "
         "fade counters on Saproling Burst.\"\nWhen this enchantment leaves the battlefield, destroy all tokens created with this enchantment. They can't be regenerated.",
         None, "G"),
    real("Disenchant", "{1}{W}", 2, "Instant", "Destroy target artifact or enchantment.", None, "W"),
    real("Outmaneuver", "{X}{R}", 1, "Instant", "X target blocked creatures assign their combat damage this turn as though they weren't blocked.", None, "R"),
    real("Ulamog's Despoiler", "{6}", 6, "Creature \u2014 Eldrazi Processor",
         "As this creature enters, you may put two cards your opponents own from exile into their owners' graveyards. If you do, this creature enters with four +1/+1 counters on it.",
         ("5", "5"), ""),
    real("Doom Blade", "{1}{B}", 2, "Instant", "Destroy target nonblack creature.", None, "B"),
    real("Hill Giant", "{3}{R}", 4, "Creature \u2014 Giant", "", ("3", "3"), "R"),
    real("Grizzly Bears", "{1}{G}", 2, "Creature \u2014 Bear", "", ("2", "2"), "G"),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn, else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def _phoenix(cards, evidence):
    s = build(cards, ["Lamplight Phoenix", "Doom Blade", *evidence])
    phx = put(s, "Lamplight Phoenix")
    dead = [to_hand(s, n) for n in evidence]
    for c in dead:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, B=1, C=1)
    cast(s, "Doom Blade", [phx.id])
    return s, phx, dead


def test_lamplight_phoenix_returns_tapped(cards):
    """Evidence 4 (the Giant) is exiled with the Phoenix itself (not counted toward it); the Phoenix returns tapped."""
    s, phx, (giant,) = _phoenix(cards, ["Hill Giant"])
    answer(s, "pay", [giant.id])
    assert s.state.cards[giant.id].zone == "p1:exile" and s.state.cards[phx.id].zone == "p1:battlefield" and s.state.cards[phx.id].tapped
    check(s)


def test_lamplight_phoenix_declined(cards):
    """Declining the cost leaves everything where it is (118.12): the Phoenix is not returned."""
    s, phx, (giant,) = _phoenix(cards, ["Hill Giant"])
    answer(s, "decline")
    assert s.state.cards[phx.id].zone == "p1:graveyard" and s.state.cards[giant.id].zone == "p1:graveyard"
    check(s)


def test_lamplight_phoenix_too_little_evidence(cards):
    """Total mana value 2 is not 4 (701.59a): the choice is refused and the Phoenix can still be exiled only with enough."""
    s, phx, (bear,) = _phoenix(cards, ["Grizzly Bears"])
    from app.game.errors import ActionError
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay"])
    d = s.state.rules.decision
    with pytest.raises(ActionError):
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[bear.id])


def _bloodfeather(cards, target, hit_battle=False):
    s = build(cards, ["Bloodfeather Phoenix", "Lightning Bolt", "Hill Giant"], [SIEGE])
    phx = to_hand(s, "Bloodfeather Phoenix")
    act(s, "p1", type="move", card_ids=[phx.id], to={"player": "p1", "zone": "graveyard"})
    giant = put(s, "Hill Giant")
    battle = None
    if hit_battle:
        battle = put(s, SIEGE, "p2")
        act(s, "p2", type="counter", card_ids=[battle.id], kind="defense", delta=4)
        from tests.test_rules_conditionals import settle
        settle(s)
    mana(s, R=2)
    cast(s, "Lightning Bolt", [battle.id if battle else {"opp": "p2", "creature": giant.id, "me": "p1"}[target]])
    return s, phx


@pytest.mark.parametrize("target,returns", [("opp", True), ("creature", False), ("me", False)])
def test_bloodfeather_phoenix_player_targets(cards, target, returns):
    """Only damage to an opponent (not to a creature or to yourself) offers the {R} return."""
    s, phx = _bloodfeather(cards, target)
    answer(s, "pay")
    assert (s.state.cards[phx.id].zone == "p1:battlefield") == returns
    check(s)


def test_bloodfeather_phoenix_battle(cards):
    """Damage to a battle counts too."""
    s, phx = _bloodfeather(cards, None, hit_battle=True)
    answer(s, "pay")
    assert s.state.cards[phx.id].zone == "p1:battlefield"
    check(s)


def test_the_spot_returns_the_exiled_cards_when_it_dies(cards):
    s = build(cards, ["The Spot, Living Portal", "Murder", "Hill Giant"], ["Hill Giant"])
    giant = put(s, "Hill Giant", "p2")
    mine = to_hand(s, "Hill Giant")
    act(s, "p1", type="move", card_ids=[mine.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, W=1, U=1, B=1, C=2)
    spot = cast(s, "The Spot, Living Portal", [giant.id, mine.id], target_counts=[1, 1])
    answer(s)
    assert s.state.cards[giant.id].zone == "p2:exile" and s.state.cards[mine.id].zone == "p1:exile"
    mana(s, B=2, C=1)
    cast(s, "Murder", [spot.id])
    answer(s)
    assert s.state.cards[spot.id].zone == "p1:library" and s.state.zones["p1:library"][-1] == spot.id
    assert s.state.cards[giant.id].zone == "p2:hand" and s.state.cards[mine.id].zone == "p1:hand"
    check(s)


def test_the_spot_exiled_in_response_returns_nothing(cards):
    """608.2c: if The Spot is exiled with its dies trigger on the stack, it never reaches the library, so "If you do" is false and the exiled cards stay."""
    s = build(cards, ["The Spot, Living Portal", "Murder", "Hill Giant"], ["Hill Giant"])
    giant = put(s, "Hill Giant", "p2")
    mana(s, W=1, U=1, B=1, C=2)
    spot = cast(s, "The Spot, Living Portal", [giant.id], target_counts=[1, 0])
    answer(s)
    assert s.state.cards[giant.id].zone == "p2:exile"
    mana(s, B=2, C=1)
    act(s, "p1", type="configure", automation_options={"auto_priority_pass": False})
    cast(s, "Murder", [spot.id])
    for _ in range(10):  # resolve Murder (both pass), stop with the dies trigger on the stack
        if s.state.cards[spot.id].zone == "p1:graveyard" and s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[spot.id].zone == "p1:graveyard"
    act(s, "p1", type="move", card_ids=[spot.id], to={"player": "p1", "zone": "exile"})
    answer(s)
    assert s.state.cards[spot.id].zone == "p1:exile" and s.state.cards[giant.id].zone == "p2:exile"
    check(s)


def _raptor(cards, siege_owner, walker=False):
    s = build(cards, ["Rampaging Raptor", SIEGE], ["Test Walker", SIEGE])
    raptor = put(s, "Rampaging Raptor")
    battle = put(s, SIEGE, siege_owner)
    act(s, siege_owner, type="counter", card_ids=[battle.id], kind="defense", delta=5)
    from tests.test_rules_conditionals import settle
    settle(s)
    pw = put(s, "Test Walker", "p2")
    act(s, "p2", type="set_counter", card_id=pw.id, kind="loyalty", value=5)
    return s, raptor, battle, pw


def _declare(s, raptor):
    from tests.test_rules_wave100f_attached import to_phase

    to_phase(s, "declare_attackers", turn=1)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": raptor.id, "target": "p2"}])


def _hit(s, raptor, pick):
    _declare(s, raptor)
    for _ in range(40):  # the trigger's target, then play on
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        elif s.state.zones.get("stack") or s.state.turn.phase != "main2":
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return


def _counters(s, c, kind):
    return s.state.cards[c.id].counters.get(kind, 0)


def test_rampaging_raptor_hits_the_planeswalker(cards):
    s, raptor, battle, pw = _raptor(cards, "p1")
    _hit(s, raptor, pw.id)
    assert _counters(s, pw, "loyalty") == 1 and life(s, "p2") == 36
    check(s)


def test_rampaging_raptor_hits_a_battle_its_target_protects(cards):
    s, raptor, battle, pw = _raptor(cards, "p1")  # p1's Siege is protected by p2, the damaged player
    _hit(s, raptor, battle.id)
    assert _counters(s, battle, "defense") == 1
    check(s)


def test_rampaging_raptor_cannot_target_a_battle_the_other_player_controls_but_does_not_protect(cards):
    s, raptor, battle, pw = _raptor(cards, "p2")  # p2's own Siege is protected by p1: not a legal target
    from tests.test_rules_wave100f_attached import to_phase
    to_phase(s, "declare_attackers", turn=1)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": raptor.id, "target": "p2"}])
    ids = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            ids = [o.id for o in d.options]
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert pw.id in ids and battle.id not in ids


@pytest.mark.parametrize("second_target", [True, False])
def test_mysterious_limousine_returns_the_older_exile(cards, second_target):
    from tests.test_rules_wave100f_attached import to_phase

    s = build(cards, ["Mysterious Limousine", "Hill Giant"], ["Hill Giant", "Grizzly Bears"])
    a = put(s, "Hill Giant", "p2")
    mana(s, B=1, C=3)
    cast(s, "Mysterious Limousine")
    answer(s, [a.id])
    assert s.state.cards[a.id].zone == "p2:exile"
    pilot = put(s, "Hill Giant")
    to_phase(s, "main1", turn=3)
    limo = next(c for c in s.state.cards.values() if c.name == "Mysterious Limousine")
    b = put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="activate_ability", card_id=limo.id, ability=1, crew=[pilot.id])
    answer(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": limo.id, "target": "p2"}])
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[b.id] if second_target else [])
    while s.state.zones.get("stack") or (s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers"):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert (s.state.cards[b.id].zone == "p2:exile") == second_target
    assert (s.state.cards[a.id].zone == "p2:battlefield") == second_target
    check(s)


@pytest.mark.parametrize("bolts,alive", [(2, True), (1, True)])
def test_wolverine_heals_earlier_damage(cards, bolts, alive):
    """Two Bolts (3 + 3) would kill a 3/5, but the second deals its damage and heals the first: 3 damage stays (the new damage is still dealt)."""
    s = build(cards, ["Wolverine, Fierce Fighter", "Lightning Bolt"])
    wolf = put(s, "Wolverine, Fierce Fighter")
    for _ in range(bolts):
        mana(s, R=1)
        cast(s, "Lightning Bolt", [wolf.id])
        answer(s)
    assert (s.state.cards[wolf.id].zone == "p1:battlefield") == alive and s.state.cards[wolf.id].damage == 3
    check(s)


def test_freyalises_winds_holds_one_untap(cards):
    """614.1a: tapped (wind counter by the trigger), the permanent loses all wind counters instead of untapping once; the next untap is normal."""
    from tests.test_rules_conditionals import until

    s = build(cards, ["Freyalise's Winds", "Sol Ring"])
    bears = put(s, "Sol Ring")
    mana(s, G=2, C=2)
    cast(s, "Freyalise's Winds")
    answer(s)
    act(s, "p1", type="activate_ability", card_id=bears.id, ability=0)
    answer(s)
    assert s.state.cards[bears.id].counters.get("wind", 0) == 1 and s.state.cards[bears.id].tapped
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    got = s.state.cards[bears.id]
    assert (got.tapped, got.counters.get("wind", 0)) == (True, 0)
    until(s, lambda s: s.state.turn.number == 5 and s.state.turn.phase == "main1")
    assert not s.state.cards[bears.id].tapped
    check(s)


def test_saproling_burst(cards):
    """111.2: every Saproling is as big as the fade counters left; when the enchantment leaves, the tokens it made are destroyed (701.8), not other tokens."""
    s = build(cards, ["Saproling Burst", "Disenchant"])
    mana(s, G=2, C=3)
    burst = cast(s, "Saproling Burst")
    answer(s)
    from app.rules.plan import Plan
    for made, left in ((1, 6), (2, 5)):
        act(s, "p1", type="activate_ability", card_id=burst.id, ability=1)
        answer(s)
        tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
        assert len(tokens) == made and s.state.cards[burst.id].counters["fade"] == left
        assert all(Plan(s.state, "p1", s.cards, None).ch(t).pt == (left, left) for t in tokens)
    mana(s, W=1, C=1)
    cast(s, "Disenchant", [burst.id])
    answer(s)
    assert s.state.cards[burst.id].zone == "p1:graveyard"
    assert not [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    check(s)


@pytest.mark.parametrize("cast", [True, False])
def test_outmaneuver(cards, cast):
    """510.1c exception: the blocked 3/3 assigns its damage as though unblocked: all to the player, none to the blocker; without the spell the blocker takes it."""
    from tests.test_rules_conditionals import creature, sandbox
    from tests.wave53c_kit import combat_step, swing, to_postcombat

    s = sandbox(cards, "Outmaneuver")
    atk = creature(s, "p1", "Brute", "3/3")
    blk = creature(s, "p2", "Wall", "1/9")
    combat_step(s)
    swing(s, [atk], [(blk, atk)])
    if cast:
        spell = next(c for c in s.state.cards.values() if c.name == "Outmaneuver")
        act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "hand"})
        act(s, "p1", type="add_mana", player="p1", mana={"R": 1, "C": 1})
        act(s, "p1", type="cast_spell", card_id=spell.id, targets=[atk.id], x_value=1, target_counts=[1])
    to_postcombat(s)
    assert s.state.cards[blk.id].damage == (0 if cast else 3) and life(s, "p2") == (37 if cast else 40)
    check(s)


def _despoiler(cards, exiled):
    s = build(cards, ["Ulamog's Despoiler", "Grizzly Bears", "Hill Giant"], ["Grizzly Bears", "Hill Giant"])
    gone = []
    for n in exiled:
        c = to_hand(s, n, "p2")
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "exile"})
        gone.append(c)
    mana(s, C=6)
    return s, cast(s, "Ulamog's Despoiler"), gone


def test_ulamogs_despoiler_two_cards(cards):
    """Exactly two of the opponents' exiled cards go to their owners' graveyards; then it enters with four +1/+1 counters."""
    s, d, (a, b) = _despoiler(cards, ["Grizzly Bears", "Hill Giant"])
    answer(s, [a.id], [b.id])
    assert s.state.cards[a.id].zone == s.state.cards[b.id].zone == "p2:graveyard"
    assert s.state.cards[d.id].counters.get("+1/+1") == 4
    check(s)


def test_ulamogs_despoiler_declined(cards):
    s, d, (a, b) = _despoiler(cards, ["Grizzly Bears", "Hill Giant"])
    answer(s, ["done"])
    assert s.state.cards[a.id].zone == s.state.cards[b.id].zone == "p2:exile" and not s.state.cards[d.id].counters.get("+1/+1")
    check(s)


def test_ulamogs_despoiler_one_card_is_not_enough(cards):
    """"If you do" needs both cards (608.2c): one card picked, then stopping, leaves the card in exile and no counters; the Despoiler is not offered cards it cannot take."""
    s, d, (a,) = _despoiler(cards, ["Grizzly Bears"])
    answer(s, [a.id], ["done"])
    assert s.state.cards[a.id].zone == "p2:exile" and not s.state.cards[d.id].counters.get("+1/+1")
    check(s)
