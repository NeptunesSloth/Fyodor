"""The pod's Zedruu the Greathearted deck (tests/fixtures/soak_decks/zedruu_the_greathearted_grouphug.txt): its plan, with real Oracle text.

Zedruu gives permanents away ({U}{R}{W}: "Target opponent gains control of target permanent you control"), and at the beginning of its
controller's upkeep counts the permanents they own that opponents control (gain X life, draw X cards). The gifts are drawbacks that now fall
on their new controller: "your upkeep" and "you" are the controller's (603.3a, 702.24a), and leaves-the-battlefield triggers look back to who
controlled the permanent as it left (603.10a). In multiplayer, a player who leaves the game takes the control-changing effects with them, so
the gifts come back to Zedruu's player (800.4a). Solemnity keeps cumulative upkeep at zero age counters: the cost is paid zero times (702.24a);
Thought Lash's "Exile the top card" cost paid zero times used to crash the engine (a move of no cards).
"""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import PHASES
from app.rules import coverage
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check

EXTRA = [
    real('Zedruu the Greathearted', '{1}{U}{R}{W}', 4, 'Legendary Creature — Minotaur Monk',
         'At the beginning of your upkeep, you gain X life and draw X cards, where X is the number of permanents you own that your opponents '
         'control.\n{U}{R}{W}: Target opponent gains control of target permanent you control.', ('2', '4'), 'RUW'),
    real('Zidane, Tantalus Thief', '{3}{R}{W}', 5, 'Legendary Creature — Human Mutant Scout',
         'When Zidane enters, gain control of target creature an opponent controls until end of turn. Untap it. It gains lifelink and haste '
         'until end of turn.\nWhenever an opponent gains control of a permanent from you, you create a Treasure token.', ('3', '3'), 'RW'),
    real('Illusions of Grandeur', '{3}{U}', 4, 'Enchantment',
         'Cumulative upkeep {2} (At the beginning of your upkeep, put an age counter on this permanent, then sacrifice it unless you pay its '
         'upkeep cost for each age counter on it.)\nWhen this enchantment enters, you gain 20 life.\nWhen this enchantment leaves the '
         'battlefield, you lose 20 life.', None, 'U'),
    real('Akroan Horse', '{4}', 4, 'Artifact Creature — Horse',
         'Defender\nWhen this creature enters, an opponent gains control of it.\nAt the beginning of your upkeep, each opponent creates a 1/1 '
         'white Soldier creature token.', ('0', '4'), ''),
    real('Transcendence', '{3}{W}{W}{W}', 6, 'Enchantment',
         "You don't lose the game for having 0 or less life.\nWhen you have 20 or more life, you lose the game.\nWhenever you lose life, you "
         "gain 2 life for each 1 life you lost. (Damage dealt to you causes you to lose life.)", None, 'W'),
    real('Nine Lives', '{1}{W}{W}', 3, 'Enchantment',
         'Hexproof\nIf a source would deal damage to you, prevent that damage and put an incarnation counter on this enchantment.\nWhen there '
         'are nine or more incarnation counters on this enchantment, exile it.\nWhen this enchantment leaves the battlefield, you lose the game.',
         None, 'W'),
    real('Austere Command', '{4}{W}{W}', 6, 'Sorcery',
         'Choose two —\n• Destroy all artifacts.\n• Destroy all enchantments.\n• Destroy all creatures with mana value 3 or less.\n• Destroy '
         'all creatures with mana value 4 or greater.', None, 'W'),
    real('Khârn the Betrayer', '{3}{R}', 4, 'Legendary Creature — Astartes Berserker',
         'Berzerker — Khârn the Betrayer attacks or blocks each combat if able.\nSigil of Corruption — When you lose control of Khârn the '
         'Betrayer, draw two cards.\nThe Betrayer — If damage would be dealt to Khârn the Betrayer, prevent that damage and an opponent of '
         'your choice gains control of it.', ('5', '1'), 'R'),
    real('Solemnity', '{2}{W}', 3, 'Enchantment',
         "Players can't get counters.\nCounters can't be put on artifacts, creatures, enchantments, or lands.", None, 'W'),
    real('Thought Lash', '{2}{U}{U}', 4, 'Enchantment',
         "Cumulative upkeep—Exile the top card of your library. (At the beginning of your upkeep, put an age counter on this permanent, then "
         "sacrifice it unless you pay its upkeep cost for each age counter on it.)\nWhen a player doesn't pay this enchantment's cumulative "
         "upkeep, that player exiles all cards from their library.\nExile the top card of your library: Prevent the next 1 damage that would be "
         "dealt to you this turn.", None, 'U'),
    real('Paradox Haze', '{2}{U}', 3, 'Enchantment — Aura',
         "Enchant player\nAt the beginning of enchanted player's first upkeep each turn, that player gets an additional upkeep step after this "
         "step.", None, 'U'),
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


# -- the table --------------------------------------------------------------------------------------------------------------------------------
def build(cards, players=2):
    """Alice (Zedruu's deck), Bob and, with ``players=3``, Carol; Alice is in her first main phase."""
    alice = deck(cards, "Zedruu the Greathearted", [*((1, n) for n in NAMES[1:]), (1, "Sol Ring"), (1, "Lightning Bolt"), (12, "Island")])
    bob = deck(cards, "Krenko, Mob Boss", [(12, "Mountain")])
    carol = deck(cards, "Atraxa, Praetors' Voice", [(12, "Forest")])
    seats = [PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)][:players]
    s = GameSession(enable(new_game(seats, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def card(s, name, pid="p1"):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def put(s, name):
    c = card(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    return c


def where(s, c):
    return s.state.cards[c.id].zone, s.state.cards[c.id].controller


def life(s, pid):
    return s.state.players[pid].life


def hand_size(s, pid):
    return len(s.state.zones[f"{pid}:hand"])


def settle(s, *labels, limit=60):
    """Resolve everything; a choice is answered with the options labelled ``labels`` (as many as it takes), else its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            want = [o.id for o in d.options if (o.label or "") in labels][: max(d.max_choices or 1, 1)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want or [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_step(s, phase, turn, *labels, limit=400):
    """Pass priority (no attackers, no blockers) until ``phase`` of turn ``turn``, answering choices as ``settle`` does."""
    for _ in range(limit):
        d = s.state.rules.decision
        if (s.state.turn.number, PHASES.index(s.state.turn.phase)) >= (turn, PHASES.index(phase)) and not s.state.zones.get("stack") and d is None:
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            want = [o.id for o in d.options if (o.label or "") in labels][: max(d.max_choices or 1, 1)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want or [o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase} of turn {turn}")


def to_decision(s, limit=200):
    """Pass priority (no attackers, no blockers) until someone has a choice to make."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            return d
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no choice came up")


def cast(s, name, *labels, targets=(), **mana):
    c = card(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    act(s, "p1", type="add_mana", player="p1", mana=mana)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=list(targets))
    settle(s, *labels)
    return c


def give(s, permanent, to="p2"):
    """Zedruu's activated ability: ``to`` gains control of ``permanent``."""
    act(s, "p1", type="add_mana", player="p1", mana={"U": 1, "R": 1, "W": 1})
    act(s, "p1", type="activate_ability", card_id=card(s, "Zedruu the Greathearted").id, ability=1, targets=[to, permanent.id],
        target_counts=[1, 1], sources=[])
    settle(s)


# -- the scenarios ----------------------------------------------------------------------------------------------------------------------------
def test_gifts_stay_alices_and_zedruu_counts_them_at_her_upkeep(cards):
    """Zedruu gives Sol Ring to Bob (Zidane: a Treasure), Akroan Horse gives itself away. Alice still owns both; at Bob's upkeep the Horse's
    "your upkeep" is Bob's, so its opponent Alice gets the Soldier; at Alice's upkeep Zedruu counts the two (gain 2, draw 2)."""
    s = build(cards)
    put(s, "Zedruu the Greathearted")
    put(s, "Zidane, Tantalus Thief")
    ring = put(s, "Sol Ring")
    give(s, ring)
    assert where(s, ring) == ("p2:battlefield", "p2") and s.state.cards[ring.id].owner == "p1"
    assert [c.controller for c in s.state.cards.values() if c.name == "Treasure"] == ["p1"]
    horse = cast(s, "Akroan Horse", C=4)
    assert where(s, horse) == ("p2:battlefield", "p2")
    to_step(s, "main1", 2)
    assert [c.controller for c in s.state.cards.values() if c.name == "Soldier"] == ["p1"]
    before_life, before_hand = life(s, "p1"), hand_size(s, "p1")
    to_step(s, "main1", 3)
    assert life(s, "p1") == before_life + 2
    assert hand_size(s, "p1") == before_hand + 2 + 1  # Zedruu's two and the draw step's one
    check(s)


@pytest.mark.parametrize("pays", [False, True])
def test_a_given_illusions_of_grandeur_is_its_new_controllers_upkeep_and_loss(cards, pays):
    """702.24a: the cumulative upkeep is Bob's now; 603.10a: when it leaves, "you" is Bob (he controlled it), and it goes to Alice's
    graveyard. If Bob pays, it stays."""
    s = build(cards)
    put(s, "Zedruu the Greathearted")
    illusions = cast(s, "Illusions of Grandeur", U=1, C=3)
    assert life(s, "p1") == 60
    give(s, illusions)
    assert to_decision(s).player == "p2" and s.state.turn.phase == "upkeep"
    if pays:
        act(s, "p2", type="add_mana", player="p2", mana={"C": 2})
    settle(s, "Pay {2}" if pays else "Sacrifice Illusions of Grandeur")
    assert where(s, illusions) == (("p2:battlefield", "p2") if pays else ("p1:graveyard", "p1"))
    assert (life(s, "p1"), life(s, "p2")) == (60, 40 if pays else 20)
    check(s)


def test_transcendence_given_away_loses_its_new_controller_the_game_and_comes_back(cards):
    """603.8: Bob has 20 or more life while he controls it, so he loses; 800.4a: the control-changing effect ends as he leaves, and
    Transcendence (and anything else Alice gave him) comes back to Alice, who is under 20."""
    s = build(cards, players=3)
    put(s, "Zedruu the Greathearted")
    ring = put(s, "Sol Ring")
    give(s, ring)
    act(s, "p1", type="set_life", player="p1", value=10)
    transcendence = cast(s, "Transcendence", W=3, C=3)
    give(s, transcendence)
    assert "p2" in s.state.rules.lost and "p1" not in s.state.rules.lost and "p3" not in s.state.rules.lost
    assert where(s, transcendence) == ("p1:battlefield", "p1") and where(s, ring) == ("p1:battlefield", "p1")
    check(s)


def test_nine_lives_given_away_then_destroyed_loses_its_controller_the_game(cards):
    """603.10a: "When this enchantment leaves the battlefield, you lose the game" is Bob's when it is destroyed under his control."""
    s = build(cards, players=3)
    put(s, "Zedruu the Greathearted")
    nine = cast(s, "Nine Lives", W=2, C=1)
    give(s, nine)
    cast(s, "Austere Command", "Destroy all artifacts.", "Destroy all enchantments.", W=2, C=4)
    assert where(s, nine) == ("p1:graveyard", "p1")
    assert list(s.state.rules.lost) == ["p2"]
    check(s)


def test_kharn_moves_on_when_damaged_and_its_old_controller_draws_two(cards):
    """Zedruu gives Khârn to Bob (Alice lost control: she draws two). Bolting it: the damage is prevented and an opponent of Bob's choice,
    Carol, gains control; Bob, who lost control, draws two."""
    s = build(cards, players=3)
    put(s, "Zedruu the Greathearted")
    kharn = put(s, "Khârn the Betrayer")
    alice = hand_size(s, "p1")
    give(s, kharn)
    assert where(s, kharn) == ("p2:battlefield", "p2") and hand_size(s, "p1") == alice + 2
    bob = hand_size(s, "p2")
    cast(s, "Lightning Bolt", "Carol", targets=[kharn.id], R=1)
    assert where(s, kharn) == ("p3:battlefield", "p3") and s.state.cards[kharn.id].damage == 0
    assert hand_size(s, "p2") == bob + 2
    check(s)


def test_solemnity_keeps_cumulative_upkeep_at_zero(cards):
    """Solemnity: no age counter is put on Thought Lash or Illusions of Grandeur, so their cumulative upkeep is paid zero times (702.24a):
    nothing is exiled and they stay. (Paying Thought Lash zero times crashed: a move of no cards.)"""
    s = build(cards)
    put(s, "Zedruu the Greathearted")
    put(s, "Solemnity")
    lash = put(s, "Thought Lash")
    illusions = cast(s, "Illusions of Grandeur", U=1, C=3)
    give(s, illusions)
    to_step(s, "draw", 2, "Pay {0}")
    assert where(s, illusions) == ("p2:battlefield", "p2") and s.state.cards[illusions.id].counters.get("age", 0) == 0
    library = len(s.state.zones["p1:library"])
    to_step(s, "draw", 3, "Exile the top 0 cards of your library")
    assert where(s, lash) == ("p1:battlefield", "p1") and s.state.cards[lash.id].counters.get("age", 0) == 0
    assert len(s.state.zones["p1:library"]) == library - 2 and not s.state.zones.get("p1:exile")  # (Zedruu drew one: Bob has the Illusions; the draw step one)
    check(s)


def test_paradox_haze_gives_zedruu_two_upkeeps(cards):
    s = build(cards)
    put(s, "Zedruu the Greathearted")
    give(s, put(s, "Sol Ring"))
    cast(s, "Paradox Haze", targets=["p1"], U=1, C=2)
    before_life, before_hand = life(s, "p1"), hand_size(s, "p1")
    to_step(s, "main1", 3)
    assert life(s, "p1") == before_life + 2 and hand_size(s, "p1") == before_hand + 2 + 1
    check(s)
