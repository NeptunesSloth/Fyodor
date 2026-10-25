"""Wave 100K: "instead" clauses read whole (608.2c). Real Oracle text, every scenario checks the replay and a save and a load.

* "If C, you may Y instead." (Sweep Away, Ether Well, Expel from Orazca, Whirlpool Whelm): C judged once as it resolves, then (only when it
  holds) the controller's choice (608.2d); no: the replaced instruction (Expel's ruling).
* Restated amounts and tokens: "that player mills twice that many cards instead" (Increasing Confusion), "~ deals 4 damage to that creature
  instead if you controlled a Mount as you cast this spell" (Steer Clear: the cast-time snapshot, its ruling), "instead create two of those
  tokens that are tapped and attacking" (Andúril).
* Conditions: "an opponent has at least four more cards in hand than you" inside "If an opponent has more …" (Teachings of the Archaics),
  "it's an enchantment creature or legendary creature" (Regent's Authority), "this creature's spectacle cost was paid" (Rix Maadi Reveler),
  "you have the city's blessing" after ascend (Golden Demise), a full party replacing the whole loot (The Destined Thief's ruling).
* Edicts and targets: "that player sacrifices two of those creatures of their choice instead" (Gideon's Triumph: "that attacked or blocked this
  turn", 508.1, 509.1g), the gift's other target group (Dewdrop Cure, 601.2c), "instead exile the chosen creature" (Turncoat Kunoichi's sneak).
* Promoted by the shared grammar, pinned here: "if you controlled a Faerie as you cast this spell" (Faerie Fencing), "it's an enchanted creature or
  enchantment creature" (Karametra's Blessing), "if that creature is attacking" (Battlefield Improvisation).
* Damage replacements: "to enchanted player" (Curse of Bloodletting, 702.5d), "this turn to an opponent or a permanent an opponent controls"
  (Isengard Unleashed, 611.2a, 614.1a).
* "If it's attacking a battle, put a +1/+1 counter on it instead." (Rampaging Geoderm, 310.5, 506.3).
* "If it has unearth, instead exile it, then return that card to its owner's hand." (Meticulous Excavation: an unearthed creature too, its rulings).
* "Until end of turn, if you would put one or more +1/+1 counters on a creature you control, put that many plus one …" (Prairie Dog: an entering
  creature's counters are put by its controller, 122.6a, its rulings; twice: plus two).
* "If a creature you control that's enchanted would die, return it to its owner's hand instead." (Necromancer's Magemark: 614.1a, it never dies;
  its Auras go to the graveyard, its rulings).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import token_of, until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand

EXTRA = [
    real('Sweep Away', '{2}{U}', 3, 'Instant',
         "Return target creature to its owner's hand. If that creature is attacking, you may put it on top of its owner's library instead.", None, 'U'),
    real('Ether Well', '{3}{U}', 4, 'Instant',
         "Put target creature on top of its owner's library. If that creature is red, you may put it on the bottom of its owner's library instead.", None, 'U'),
    real('Expel from Orazca', '{1}{U}', 2, 'Instant',
         "Ascend (If you control ten or more permanents, you get the city's blessing for the rest of the game.)\nReturn target nonland permanent to its owner's hand. "
         "If you have the city's blessing, you may put that permanent on top of its owner's library instead.", None, 'U'),
    real('Whirlpool Whelm', '{1}{U}', 2, 'Instant',
         "Clash with an opponent, then return target creature to its owner's hand. If you win, you may put that creature on top of its owner's library instead. "
         "(Each clashing player reveals the top card of their library, then puts that card on their choice of the top or bottom. A player wins if their card had "
         "a greater mana value.)", None, 'U'),
    real('Golden Demise', '{1}{B}{B}', 3, 'Sorcery',
         "Ascend (If you control ten or more permanents, you get the city's blessing for the rest of the game.)\nAll creatures get -2/-2 until end of turn. "
         "If you have the city's blessing, instead only creatures your opponents control get -2/-2 until end of turn.", None, 'B'),
    real('Increasing Confusion', '{X}{U}', 1, 'Sorcery',
         'Target player mills X cards. If this spell was cast from a graveyard, that player mills twice that many cards instead.\nFlashback {X}{U} (You may '
         'cast this card from your graveyard for its flashback cost. Then exile it.)', None, 'U'),
    real('Teachings of the Archaics', '{2}{U}', 3, 'Sorcery — Lesson',
         'If an opponent has more cards in hand than you, draw two cards. Draw three cards instead if an opponent has at least four more cards in hand than you.', None, 'U'),
    real('Steer Clear', '{W}', 1, 'Instant',
         'Steer Clear deals 2 damage to target attacking or blocking creature. Steer Clear deals 4 damage to that creature instead if you controlled a Mount as '
         'you cast this spell.', None, 'W'),
    real("Regent's Authority", '{W}', 1, 'Instant',
         "Target creature gets +2/+2 until end of turn. If it's an enchantment creature or legendary creature, instead put a +1/+1 counter on it and it gets "
         "+1/+1 until end of turn.", None, 'W'),
    real('Rix Maadi Reveler', '{1}{R}', 2, 'Creature — Human Shaman',
         "Spectacle {2}{B}{R} (You may cast this spell for its spectacle cost rather than its mana cost if an opponent lost life this turn.)\nWhen this creature "
         "enters, discard a card, then draw a card. If this creature's spectacle cost was paid, instead discard your hand, then draw three cards.", ('2', '2'), 'R'),
    real('Andúril, Flame of the West', '{3}', 3, 'Legendary Artifact — Equipment',
         'Equipped creature gets +3/+1.\nWhenever equipped creature attacks, create two tapped 1/1 white Spirit creature tokens with flying. If that creature is '
         'legendary, instead create two of those tokens that are tapped and attacking.\nEquip {2}', None, ''),
    real('The Destined Thief', '{2}{U}', 3, 'Legendary Creature — Human Rogue',
         "The Destined Thief can't be blocked.\n{U}, {T}: Another target creature you control can't be blocked this turn.\nWhenever one or more creatures you "
         "control deal combat damage to one or more players, draw a card, then discard a card. If you have a full party, instead draw three cards.", ('2', '2'), 'U'),
    real("Gideon's Triumph", '{1}{W}', 2, 'Instant',
         'Target opponent sacrifices a creature of their choice that attacked or blocked this turn. If you control a Gideon planeswalker, that player sacrifices two '
         'of those creatures of their choice instead.', None, 'W'),
    real('Dewdrop Cure', '{2}{W}', 3, 'Sorcery',
         'Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its other effects.)\nReturn up to two target '
         'creature cards each with mana value 2 or less from your graveyard to the battlefield. If the gift was promised, instead return up to three target creature '
         'cards each with mana value 2 or less from your graveyard to the battlefield.', None, 'W'),
    real('Turncoat Kunoichi', '{2}{W}', 3, 'Creature — Mutant Ninja Fox',
         "Sneak {2}{W}{B} (You may cast this spell for {2}{W}{B} if you also return an unblocked attacker you control to hand during the declare blockers step. It "
         "enters tapped and attacking.)\nWhen this creature enters, choose target creature an opponent controls. Exile that creature until this creature leaves the "
         "battlefield. If this creature's sneak cost was paid, instead exile the chosen creature.", ('3', '2'), 'W'),
    real('Faerie Fencing', '{X}{B}', 1, 'Instant',
         'Target creature gets -X/-X until end of turn. That creature gets an additional -3/-3 until end of turn if you controlled a Faerie as you cast this spell.', None, 'B'),
    real("Karametra's Blessing", '{W}', 1, 'Instant',
         'Target creature gets +2/+2 until end of turn. If it\'s an enchanted creature or enchantment creature, it also gains hexproof and indestructible until end '
         'of turn. (It can\'t be the target of spells or abilities your opponents control. Damage and effects that say "destroy" don\'t destroy it.)', None, 'W'),
    real('Battlefield Improvisation', '{1}{W}', 2, 'Instant',
         'Target creature gets +2/+2 until end of turn. If that creature is attacking, you may attach any number of Equipment you control to it.', None, 'W'),
    real('Curse of Bloodletting', '{3}{R}{R}', 5, 'Enchantment — Aura Curse',
         'Enchant player\nIf a source would deal damage to enchanted player, it deals double that damage to that player instead.', None, 'R'),
    real('Isengard Unleashed', '{2}{R}{R}{R}', 5, 'Sorcery',
         "Damage can't be prevented this turn. If a source you control would deal damage this turn to an opponent or a permanent an opponent controls, it deals "
         "triple that damage instead.\nFlashback {4}{R}{R}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)", None, 'R'),
    real('Rampaging Geoderm', '{2}{R}{G}', 4, 'Creature — Dinosaur Beast',
         "Trample, haste\nWhenever you attack, target attacking creature gets +1/+1 until end of turn. If it's attacking a battle, put a +1/+1 counter on it "
         "instead.", ('3', '3'), 'GR'),
    real('Meticulous Excavation', '{W}', 1, 'Enchantment',
         "{2}{W}: Return target permanent you control to its owner's hand. If it has unearth, instead exile it, then return that card to its owner's hand. "
         "Activate only during your turn.", None, 'W'),
    real('Prairie Dog', '{1}{W}', 2, 'Creature — Squirrel',
         "Lifelink\nAt the beginning of your end step, if you haven't cast a spell from your hand this turn, put a +1/+1 counter on this creature.\n{4}{W}: Until "
         "end of turn, if you would put one or more +1/+1 counters on a creature you control, put that many plus one +1/+1 counters on it instead.", ('2', '2'), 'W'),
    real("Necromancer's Magemark", '{2}{B}', 3, 'Enchantment — Aura',
         "Enchant creature\nCreatures you control that are enchanted get +1/+1.\nIf a creature you control that's enchanted would die, return it to its owner's "
         "hand instead.", None, 'B'),
]
NAMES = [c["name"] for c in EXTRA]
STEPS = ["main1", "begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat", "main2", "end"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    from tests.test_rules_review34_head import EXTRA as REVIEW34  # (a Siege: Invasion of Zendikar)

    build_database([*fixture_cards(), *REVIEW34, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn, else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            pick = picks.pop(0) if picks else None
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def asked(s):
    d = s.state.rules.decision
    return d is not None and d.kind == "confirm" and "instead" in d.prompt


def cast(s, name, targets=(), *picks, pid="p1", **pool):
    c = to_hand(s, name, pid)
    mana(s, pid, **pool)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets))
    return c


def bob_attacks(s, *attackers):
    """Bob attacks Alice with these creatures (no summoning sickness); then Alice has priority in his declare attackers step."""
    for c in attackers:
        s.state.rules.controlled_since[c.id].turn = 0
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers" and d.player == "p2")
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p1"} for c in attackers])
    until(s, lambda s: s.state.rules.priority == "p1" and not s.state.zones.get("stack") and s.state.rules.decision is None)


def library_top(s, pid):
    return s.state.zones[f"{pid}:library"][0]


# -- "If C, you may Y instead." ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("attacking, choice, zone", [(True, "yes", "library"), (True, "no", "hand"), (False, None, "hand")])
def test_sweep_away_asks_only_for_an_attacking_creature(cards, attacking, choice, zone):
    s = build(cards, ["Sweep Away"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    if attacking:
        bob_attacks(s, bears)
    cast(s, "Sweep Away", [bears.id], U=1, C=2)
    until(s, lambda s: asked(s) or not s.state.zones.get("stack"))
    assert asked(s) == attacking
    if attacking:
        act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[choice])
    answer(s)
    assert s.state.cards[bears.id].zone == f"p2:{zone}"
    if zone == "library":
        assert library_top(s, "p2") == bears.id
    check(s)


@pytest.mark.parametrize("red, choice", [(True, "yes"), (True, "no"), (False, None)])
def test_ether_well_bottom_only_for_a_red_creature(cards, red, choice):
    s = build(cards, ["Ether Well"], ["Grizzly Bears", "Monastery Swiftspear"])
    target = put(s, "Monastery Swiftspear" if red else "Grizzly Bears", "p2")
    cast(s, "Ether Well", [target.id], U=1, C=3)
    until(s, lambda s: asked(s) or not s.state.zones.get("stack"))
    assert asked(s) == red
    answer(s, *([choice] if choice else []))
    lib = s.state.zones["p2:library"]
    assert s.state.cards[target.id].zone == "p2:library"
    assert (lib[-1] if choice == "yes" else lib[0]) == target.id
    check(s)


def put_many(s, name, n, pid="p1"):
    """Put ``n`` of the player's cards named ``name`` onto the battlefield."""
    for c in [c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith(":battlefield")][:n]:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})


@pytest.mark.parametrize("blessed", [False, True])
def test_expel_from_orazca_top_of_library_only_with_the_citys_blessing(cards, blessed):
    """Ascend as it resolves (702.131a), then the blessing decides whether there is a choice."""
    s = build(cards, ["Expel from Orazca"], ["Grizzly Bears"], forests=12)
    bears = put(s, "Grizzly Bears", "p2")
    put_many(s, "Forest", 10 if blessed else 9)
    cast(s, "Expel from Orazca", [bears.id], U=1, C=1)
    until(s, lambda s: asked(s) or not s.state.zones.get("stack"))
    assert asked(s) == blessed and s.state.players["p1"].city_blessing == blessed
    answer(s, *(["yes"] if blessed else []))
    assert s.state.cards[bears.id].zone == ("p2:library" if blessed else "p2:hand")
    check(s)


@pytest.mark.parametrize("win", [False, True])
def test_whirlpool_whelm_clash_first_then_the_choice(cards, win):
    s = build(cards, ["Whirlpool Whelm", "Grizzly Bears"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    top = card_named(s, "Grizzly Bears") if win else next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    # (Alice reveals the Bears, Bob an Island: 2 > 0 wins; a Forest ties, 0 = 0, and a tie isn't a win: 701.30d)
    act(s, "p1", type="move", card_ids=[top.id], to={"player": "p1", "zone": "library"}, position="top")
    cast(s, "Whirlpool Whelm", [bears.id], U=1, C=1)
    for _ in range(20):
        if asked(s) or not s.state.zones.get("stack"):
            break
        d = s.state.rules.decision
        if d is not None:  # (the clashing players keep their cards on top)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert asked(s) == win
    answer(s, *(["yes"] if win else []))
    assert s.state.cards[bears.id].zone == ("p2:library" if win else "p2:hand")
    if win:
        assert library_top(s, "p2") == bears.id
    check(s)


@pytest.mark.parametrize("blessed", [False, True])
def test_golden_demise_spares_your_creatures_with_the_citys_blessing(cards, blessed):
    s = build(cards, ["Golden Demise", "Grizzly Bears"], ["Grizzly Bears"], forests=12)
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    put_many(s, "Forest", 9 if blessed else 7)  # (with the Bears: ten permanents, or eight)
    cast(s, "Golden Demise", (), B=2, C=1)
    answer(s)
    assert s.state.cards[theirs.id].zone == "p2:graveyard"
    assert s.state.cards[mine.id].zone == ("p1:battlefield" if blessed else "p1:graveyard")
    check(s)


def test_increasing_confusion_mills_twice_x_from_the_graveyard(cards):
    s = build(cards, ["Increasing Confusion"])
    library = len(s.state.zones["p2:library"])
    spell = to_hand(s, "Increasing Confusion")
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"], x_value=2)
    answer(s)
    assert len(s.state.zones["p2:library"]) == library - 2 and s.state.cards[spell.id].zone == "p1:graveyard"
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"], x_value=2)  # (flashback, 702.34a)
    answer(s)
    assert len(s.state.zones["p2:library"]) == library - 2 - 4 and s.state.cards[spell.id].zone == "p1:exile"
    check(s)


def hand(s, pid="p1"):
    return s.state.zones[f"{pid}:hand"]


@pytest.mark.parametrize("more, drawn", [(0, 0), (1, 2), (3, 2), (4, 3), (6, 3)])
def test_teachings_of_the_archaics_counts_hands_as_it_resolves(cards, more, drawn):
    s = build(cards, ["Teachings of the Archaics"])
    to_hand(s, "Teachings of the Archaics")
    mine = len(hand(s)) - 1  # (after casting it)
    theirs = list(hand(s, "p2"))
    lib = s.state.zones["p2:library"]
    if len(theirs) > mine + more:
        act(s, "p2", type="move", card_ids=theirs[: len(theirs) - mine - more], to={"player": "p2", "zone": "library"})
    elif len(theirs) < mine + more:
        act(s, "p2", type="move", card_ids=lib[: mine + more - len(theirs)], to={"player": "p2", "zone": "hand"})
    assert len(hand(s, "p2")) == mine + more
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Teachings of the Archaics").id)
    answer(s)
    assert len(hand(s)) == mine + drawn
    check(s)


@pytest.mark.parametrize("mount, gone", [(False, False), (True, False), (True, True)])
def test_steer_clear_reads_the_mount_you_controlled_as_you_cast_it(cards, mount, gone):
    """Its ruling: a Mount you controlled as you finished casting it counts even if it's gone as the spell resolves."""
    s = build(cards, ["Steer Clear"])
    giant = token_of(s, "p2", "Giant", "Token Creature — Giant", pt="3/5")
    horse = token_of(s, "p1", "Steed", "Token Creature — Horse Mount") if mount else None
    bob_attacks(s, giant)
    cast(s, "Steer Clear", [giant.id], W=1)
    if gone:
        act(s, "p1", type="move", card_ids=[horse.id], to={"player": "p1", "zone": "graveyard"})
    answer(s)
    assert s.state.cards[giant.id].damage == (4 if mount else 2)
    check(s)


@pytest.mark.parametrize("legendary", [False, True])
def test_regents_authority_counter_and_smaller_pump_for_a_legendary_creature(cards, legendary):
    s = build(cards, ["Regent's Authority", "Grizzly Bears"])
    target = token_of(s, "p1", "Hero", "Legendary Creature — Human") if legendary else put(s, "Grizzly Bears")
    cast(s, "Regent's Authority", [target.id], W=1)
    answer(s)
    assert s.state.cards[target.id].counters.get("+1/+1", 0) == (1 if legendary else 0)
    assert pt(s, target.name) == (4, 4)  # (a 2/2 with a counter and +1/+1, or with +2/+2)
    check(s)


@pytest.mark.parametrize("spectacle", [False, True])
def test_rix_maadi_reveler_spectacle_discards_the_hand_and_draws_three(cards, spectacle):
    from app.rules import alt_costs
    from app.rules import characteristics as chars

    s = build(cards, ["Rix Maadi Reveler", "Lightning Bolt", "Grizzly Bears", "Giant Growth"])
    if spectacle:  # (an opponent lost life this turn, 702.137a)
        cast(s, "Lightning Bolt", ["p2"], R=1)
        answer(s)
    to_hand(s, "Grizzly Bears")
    to_hand(s, "Giant Growth")
    reveler = to_hand(s, "Rix Maadi Reveler")
    held = [c for c in hand(s) if c != reveler.id]
    offers = [o for o in alt_costs.offers(s.state, "p1", reveler, chars.of(reveler, s.cards), s.cards) if o.tag == "spectacle"]
    assert bool(offers) == spectacle
    if spectacle:
        mana(s, B=1, R=1, C=2)
        act(s, "p1", type="cast_spell", card_id=reveler.id, alt_cost=offers[0].key)
    else:
        mana(s, R=1, C=1)
        act(s, "p1", type="cast_spell", card_id=reveler.id)
    answer(s)
    after = hand(s)
    if spectacle:
        assert len(after) == 3 and not set(after) & set(held)
    else:
        assert len(after) == len(held) and len(set(held) - set(after)) == 1
    check(s)


@pytest.mark.parametrize("legendary", [False, True])
def test_anduril_spirits_attack_only_with_a_legendary_bearer(cards, legendary):
    s = build(cards, ["Andúril, Flame of the West", "Grizzly Bears"])
    sword = put(s, "Andúril, Flame of the West")
    bearer = token_of(s, "p1", "Hero", "Legendary Creature — Human") if legendary else put(s, "Grizzly Bears")
    act(s, "p1", type="attach", card_ids=[sword.id], to=bearer.id)
    s.state.rules.controlled_since[bearer.id].turn = 0
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bearer.id, "target": "p2"}])
    until(s, lambda s: s.state.turn.phase == "main2")
    spirits = [c for c in s.state.cards.values() if c.name == "Spirit" and c.zone == "p1:battlefield"]
    assert len(spirits) == 2 and all(c.tapped for c in spirits)
    assert s.state.players["p2"].life == 40 - 5 - (2 if legendary else 0)  # (the 5/3 bearer, and the two 1/1 Spirits only when they attacked)
    check(s)


@pytest.mark.parametrize("party", [False, True])
def test_destined_thief_full_party_draws_three_without_discarding(cards, party):
    s = build(cards, ["The Destined Thief"])
    thief = put(s, "The Destined Thief")
    if party:  # (the Thief is the Rogue; a full party is a Cleric, a Rogue, a Warrior and a Wizard: 700.8, 700.8c)
        for kind in ("Cleric", "Warrior", "Wizard"):
            token_of(s, "p1", kind, f"Token Creature — Human {kind}")
    s.state.rules.controlled_since[thief.id].turn = 0
    until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers")
    before = list(hand(s))
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": thief.id, "target": "p2"}])
    until(s, lambda s: s.state.turn.phase == "main2" and not s.state.zones.get("stack") and s.state.rules.decision is None)
    after = hand(s)
    assert set(before) <= set(after) if party else len(set(before) - set(after)) <= 1
    assert len(after) == len(before) + (3 if party else 0)
    assert len(s.state.zones["p1:graveyard"]) == (0 if party else 1)
    check(s)


def keywords(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).keywords


@pytest.mark.parametrize("gideon", [False, True])
def test_gideons_triumph_edicts_one_or_two_of_the_creatures_that_attacked(cards, gideon):
    s = build(cards, ["Gideon's Triumph", "Gideon Jura"], ["Grizzly Bears", "Llanowar Elves", "Monastery Swiftspear"])
    bears, elves, idle = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2"), put(s, "Monastery Swiftspear", "p2")
    if gideon:
        act(s, "p1", type="counter", card_ids=[put(s, "Gideon Jura").id], kind="loyalty", delta=6)
    bob_attacks(s, bears, elves)
    cast(s, "Gideon's Triumph", ["p2"], W=1, C=1)
    answer(s)
    gone = [c for c in (bears, elves) if s.state.cards[c.id].zone == "p2:graveyard"]
    assert len(gone) == (2 if gideon else 1)
    assert s.state.cards[idle.id].zone == "p2:battlefield"  # (it didn't attack or block)
    check(s)


@pytest.mark.parametrize("gift", [False, True])
def test_dewdrop_cure_returns_three_only_when_the_gift_was_promised(cards, gift):
    names = ["Grizzly Bears", "Llanowar Elves", "Monastery Swiftspear"]
    s = build(cards, ["Dewdrop Cure", *names])
    dead = [card_named(s, n) for n in names]
    act(s, "p1", type="move", card_ids=[c.id for c in dead], to={"player": "p1", "zone": "graveyard"})
    spell = to_hand(s, "Dewdrop Cure")
    bob_hand = len(hand(s, "p2"))
    mana(s, W=1, C=2)
    picked = dead if gift else dead[:2]
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[c.id for c in picked], target_counts=[0, 3] if gift else [2, 0],
        optional_costs=[f"{spell.id}:gift"] if gift else [])
    answer(s)
    assert [s.state.cards[c.id].zone for c in dead] == ["p1:battlefield"] * len(picked) + ["p1:graveyard"] * (3 - len(picked))
    assert len(hand(s, "p2")) == bob_hand + int(gift)  # (the gift: Bob draws first, 702.174)
    check(s)


@pytest.mark.parametrize("sneak", [False, True])
def test_turncoat_kunoichi_exiles_for_good_only_when_sneaked(cards, sneak):
    from tests.test_rules_wave30i_sneak import attackers_declared, returned, sneak_of

    s = build(cards, ["Turncoat Kunoichi", "Grizzly Bears"], ["Llanowar Elves"])
    elves = put(s, "Llanowar Elves", "p2")
    ninja = to_hand(s, "Turncoat Kunoichi")
    if sneak:
        bear = put(s, "Grizzly Bears")
        s.state.rules.controlled_since[bear.id].turn = 0
        attackers_declared(s, [(bear, "p2")])
        mana(s, W=1, B=1, C=2)
        act(s, "p1", type="cast_spell", card_id=ninja.id, alt_cost=sneak_of(s, cards, ninja))
        returned(s, bear)
    else:
        mana(s, W=1, C=2)
        act(s, "p1", type="cast_spell", card_id=ninja.id)
    answer(s, elves.id)
    assert s.state.cards[elves.id].zone == "p2:exile"
    act(s, "p1", type="set_damage", card_ids=[ninja.id], value=2)  # (it dies: 704.5g)
    until(s, lambda s: s.state.cards[ninja.id].zone == "p1:graveyard" and not s.state.zones.get("stack"))
    back = next(c for c in s.state.cards.values() if c.name == "Llanowar Elves" and c.owner == "p2" and c.zone in ("p2:battlefield", "p2:exile"))
    assert back.zone == ("p2:exile" if sneak else "p2:battlefield")
    check(s)


@pytest.mark.parametrize("faerie, gone", [(False, False), (True, False), (True, True)])
def test_faerie_fencing_reads_the_faerie_you_controlled_as_you_cast_it(cards, faerie, gone):
    s = build(cards, ["Faerie Fencing"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    sprite = token_of(s, "p1", "Sprite", "Token Creature — Faerie", "1/1") if faerie else None
    spell = to_hand(s, "Faerie Fencing")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id], x_value=1)
    if gone:
        act(s, "p1", type="move", card_ids=[sprite.id], to={"player": "p1", "zone": "graveyard"})
    answer(s)
    if faerie:
        assert s.state.cards[bears.id].zone == "p2:graveyard"  # (-4/-4)
    else:
        assert pt(s, "Grizzly Bears", "p2") == (1, 1)
    check(s)


@pytest.mark.parametrize("enchanted", [False, True])
def test_karametras_blessing_protects_an_enchanted_creature(cards, enchanted):
    s = build(cards, ["Karametra's Blessing", "Grizzly Bears", "Holy Strength"])
    bears = put(s, "Grizzly Bears")
    if enchanted:
        aura = put(s, "Holy Strength")
        act(s, "p1", type="attach", card_ids=[aura.id], to=bears.id)
    cast(s, "Karametra's Blessing", [bears.id], W=1)
    answer(s)
    assert pt(s, "Grizzly Bears") == ((5, 6) if enchanted else (4, 4))
    assert {"hexproof", "indestructible"} <= set(keywords(s, bears)) if enchanted else not {"hexproof", "indestructible"} & set(keywords(s, bears))
    check(s)


@pytest.mark.parametrize("attacking", [False, True])
def test_battlefield_improvisation_attaches_equipment_only_to_an_attacker(cards, attacking):
    s = build(cards, ["Battlefield Improvisation", "Grizzly Bears", "Bonesplitter"])
    bears, axe = put(s, "Grizzly Bears"), put(s, "Bonesplitter")
    if attacking:
        s.state.rules.controlled_since[bears.id].turn = 0
        act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
        until(s, lambda s: (d := s.state.rules.decision) is not None and d.kind == "declare_attackers")
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}])
        until(s, lambda s: s.state.rules.priority == "p1" and not s.state.zones.get("stack") and s.state.rules.decision is None)
    cast(s, "Battlefield Improvisation", [bears.id], W=1, C=1)
    answer(s, axe.id)
    assert (s.state.cards[axe.id].attached_to == bears.id) == attacking
    assert pt(s, "Grizzly Bears") == ((6, 4) if attacking else (4, 4))
    check(s)


def test_curse_of_bloodletting_doubles_damage_to_the_enchanted_player_only(cards):
    """Its rulings: any damage to that player (not to others, not to their creatures)."""
    s = build(cards, ["Curse of Bloodletting", "Lightning Bolt", "Firebolt", "Stoke the Flames"])
    wall = token_of(s, "p2", "Wall", "Token Creature — Wall", "0/9")
    cast(s, "Curse of Bloodletting", ["p2"], R=2, C=3)
    answer(s)
    assert s.state.cards[card_named(s, "Curse of Bloodletting").id].attached_player == "p2"
    cast(s, "Lightning Bolt", ["p2"], R=1)
    answer(s)
    cast(s, "Firebolt", ["p1"], R=1)
    answer(s)
    cast(s, "Stoke the Flames", [wall.id], R=2, C=2)
    answer(s)
    assert life(s, "p2") == 40 - 6 and life(s, "p1") == 40 - 2 and s.state.cards[wall.id].damage == 4
    check(s)


def test_isengard_unleashed_triples_your_damage_to_opponents_and_their_permanents(cards):
    s = build(cards, ["Isengard Unleashed", "Lightning Bolt", "Firebolt", "Stoke the Flames"])
    wall = token_of(s, "p2", "Wall", "Token Creature — Wall", "0/20")
    mine = token_of(s, "p1", "Ox", "Token Creature — Ox", "1/9")
    cast(s, "Isengard Unleashed", (), R=3, C=2)
    answer(s)
    cast(s, "Lightning Bolt", ["p2"], R=1)
    answer(s)
    cast(s, "Firebolt", [mine.id], R=1)
    answer(s)
    cast(s, "Stoke the Flames", [wall.id], R=2, C=2)
    answer(s)
    assert life(s, "p2") == 40 - 9 and s.state.cards[mine.id].damage == 2 and s.state.cards[wall.id].damage == 12
    check(s)


@pytest.mark.parametrize("battle", [False, True])
def test_rampaging_geoderm_counter_only_for_an_attacker_on_a_battle(cards, battle):
    from tests.test_rules_review34_head import SIEGE, bobs_attack, drive, seasoned

    s = build(cards, [], [SIEGE, "Rampaging Geoderm", "Grizzly Bears"])
    geoderm, bears = put(s, "Rampaging Geoderm", "p2"), put(s, "Grizzly Bears", "p2")
    siege = put(s, SIEGE, "p2")
    act(s, "p2", type="counter", card_ids=[siege.id], kind="defense", delta=4)
    drive(s, lambda d: "p1" if "p1" in [o.id for o in d.options] else None)  # (Alice protects Bob's Siege, 310.11)
    seasoned(s, geoderm, bears)
    bobs_attack(s, [(bears, siege.id if battle else "p1"), (geoderm, "p1")])
    drive(s, lambda d: bears.id if bears.id in [o.id for o in d.options] else None)  # (the trigger targets the Bears)
    assert s.state.cards[bears.id].counters.get("+1/+1", 0) == (1 if battle else 0)
    assert pt(s, "Grizzly Bears", "p2") == (3, 3)  # (a counter, or +1/+1 until end of turn)
    check(s)


@pytest.mark.parametrize("what", ["Grizzly Bears", "Dregscape Zombie", "unearthed"])
def test_meticulous_excavation_exiles_first_what_has_unearth(cards, what):
    """Its rulings: an unearthed permanent (it would be exiled instead of leaving) is exiled, then returned to its owner's hand."""
    s = build(cards, ["Meticulous Excavation", "Grizzly Bears", "Dregscape Zombie"], forests=6)
    dig = put(s, "Meticulous Excavation")
    if what == "unearthed":
        zombie = card_named(s, "Dregscape Zombie")
        act(s, "p1", type="move", card_ids=[zombie.id], to={"player": "p1", "zone": "graveyard"})
        mana(s, B=1)
        act(s, "p1", type="activate_ability", card_id=zombie.id, ability=0)
        answer(s)
        assert s.state.cards[zombie.id].zone == "p1:battlefield"
        target = zombie
    else:
        target = put(s, what)
    mana(s, W=1, C=2)
    act(s, "p1", type="activate_ability", card_id=dig.id, ability=0, targets=[target.id])
    answer(s)
    assert s.state.cards[target.id].zone == "p1:hand"
    exiled = any("exile" in str(e).lower() and target.name in str(e) for e in s.state.log[-6:])
    assert exiled == (what != "Grizzly Bears")
    check(s)


@pytest.mark.parametrize("times", [0, 1, 2])
def test_prairie_dog_adds_one_more_counter_per_resolution(cards, times):
    s = build(cards, ["Prairie Dog", "Spike Feeder"], ["Spike Feeder"])
    dog = put(s, "Prairie Dog")
    for _ in range(times):
        mana(s, W=1, C=4)
        act(s, "p1", type="activate_ability", card_id=dog.id, ability=2)
        answer(s)
    feeder = to_hand(s, "Spike Feeder")
    mana(s, G=2, C=1)
    act(s, "p1", type="cast_spell", card_id=feeder.id)
    answer(s)
    assert s.state.cards[feeder.id].counters.get("+1/+1") == 2 + times  # (its rulings: it enters with that many plus one, per resolution)
    theirs = put(s, "Spike Feeder", "p2")
    act(s, "p2", type="counter", card_ids=[theirs.id], kind="+1/+1", delta=1)
    assert s.state.cards[theirs.id].counters.get("+1/+1") == 1  # (not a creature Alice controls)
    check(s)


def test_necromancers_magemark_returns_your_enchanted_creatures_instead_of_dying(cards):
    s = build(cards, ["Necromancer's Magemark", "Grizzly Bears", "Llanowar Elves", "Wrath of God"], ["Grizzly Bears", "Holy Strength"])
    mark = put(s, "Necromancer's Magemark")
    bears, elves, theirs = put(s, "Grizzly Bears"), put(s, "Llanowar Elves"), put(s, "Grizzly Bears", "p2")
    act(s, "p1", type="attach", card_ids=[mark.id], to=bears.id)
    strength = put(s, "Holy Strength", "p2")
    act(s, "p2", type="attach", card_ids=[strength.id], to=theirs.id)  # (enchanted, but Alice doesn't control it)
    assert pt(s, "Grizzly Bears") == (3, 3)
    mana(s, W=2, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Wrath of God").id)
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:hand"  # (instead of dying: no dies triggers, 614.6)
    assert s.state.cards[mark.id].zone == "p1:graveyard"  # (the Aura isn't returned, its ruling)
    assert s.state.cards[elves.id].zone == "p1:graveyard" and s.state.cards[theirs.id].zone == "p2:graveyard"
    check(s)
