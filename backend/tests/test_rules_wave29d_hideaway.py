"""Wave 29D: Hideaway (702.75, CR 2026-09-25), real Oracle text. Every scenario checks the replay and a save and a load (the pauses mid-choice too).

* 702.75a: when the permanent enters, its controller looks at the top N cards, exiles one face down and puts the rest on the bottom in a random
  order; the exiled card is linked to the permanent (607.2a) and "the player who controls the permanent that exiled this card may look at it".
* 406.3, 406.3a-b: nobody else may look at it; it is turned face up as it is played; it can be played only by a player allowed to look at it.
* 608.2g, 305.2-305.3: "you may play the exiled card without paying its mana cost" is done as the ability resolves; a land only on its
  controller's turn with a land play left.
"""

from __future__ import annotations

import json

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.visibility import SPECTATOR
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until_asked
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_wave9b_exile_permission import put as put9
from tests.wave9c_kit import build, card_named, mana, reloaded

REAL = [
    card('Mosswort Bridge', set_code='t29d', number='D1', type_line='Land', colors=[], color_identity=['G'], keywords=['Hideaway'], oracle_text='Hideaway 4 (When this land enters, look at the top four cards of your library, exile one face down, then put the rest on the bottom in a random order.)\nThis land enters tapped.\n{T}: Add {G}.\n{G}, {T}: You may play the exiled card without paying its mana cost if creatures you control have total power 10 or greater.'),
    card('Shelldock Isle', set_code='t29d', number='D2', type_line='Land', colors=[], color_identity=['U'], keywords=['Hideaway'], oracle_text='Hideaway 4 (When this land enters, look at the top four cards of your library, exile one face down, then put the rest on the bottom in a random order.)\nThis land enters tapped.\n{T}: Add {U}.\n{U}, {T}: You may play the exiled card without paying its mana cost if a library has twenty or fewer cards in it.'),
    card('Howltooth Hollow', set_code='t29d', number='D3', type_line='Land', colors=[], color_identity=['B'], keywords=['Hideaway'], oracle_text='Hideaway 4 (When this land enters, look at the top four cards of your library, exile one face down, then put the rest on the bottom in a random order.)\nThis land enters tapped.\n{T}: Add {B}.\n{B}, {T}: You may play the exiled card without paying its mana cost if each player has no cards in hand.'),
    card('Spinerock Knoll', set_code='t29d', number='D4', type_line='Land', colors=[], color_identity=['R'], keywords=['Hideaway'], oracle_text='Hideaway 4 (When this land enters, look at the top four cards of your library, exile one face down, then put the rest on the bottom in a random order.)\nThis land enters tapped.\n{T}: Add {R}.\n{R}, {T}: You may play the exiled card without paying its mana cost if an opponent was dealt 7 or more damage this turn.'),
    card('Windbrisk Heights', set_code='t29d', number='D5', type_line='Land', colors=[], color_identity=['W'], keywords=['Hideaway'], oracle_text='Hideaway 4 (When this land enters, look at the top four cards of your library, exile one face down, then put the rest on the bottom in a random order.)\nThis land enters tapped.\n{T}: Add {W}.\n{W}, {T}: You may play the exiled card without paying its mana cost if you attacked with three or more creatures this turn.'),
    card("Clive's Hideaway", set_code='t29d', number='D6', type_line='Land — Town', colors=[], color_identity=[], keywords=['Hideaway'], oracle_text='Hideaway 4 (When this land enters, look at the top four cards of your library, exile one face down, then put the rest on the bottom in a random order.)\n{T}: Add {C}.\n{2}, {T}: You may play the exiled card without paying its mana cost if you control four or more legendary creatures.'),
    card('Evercoat Ursine', set_code='t29d', number='D7', mana_cost='{4}{G}', cmc=5.0, type_line='Creature — Elemental Bear', power='6', toughness='5', colors=['G'], color_identity=['G'], keywords=['Trample', 'Hideaway'], oracle_text='Trample\nHideaway 3, hideaway 3 (When this creature enters, look at the top three cards of your library, exile one face down, then put the rest on the bottom in a random order. Then do it again.)\nWhenever this creature deals combat damage to a player, if there are cards exiled with it, you may play one of them without paying its mana cost.'),
    card('Fight Rigging', set_code='t29d', number='D8', mana_cost='{2}{G}', cmc=3.0, type_line='Enchantment', colors=['G'], color_identity=['G'], keywords=['Hideaway'], oracle_text='Hideaway 5 (When this enchantment enters, look at the top five cards of your library, exile one face down, then put the rest on the bottom in a random order.)\nAt the beginning of combat on your turn, put a +1/+1 counter on target creature you control. Then if you control a creature with power 7 or greater, you may play the exiled card without paying its mana cost.'),
    card("Smuggler's Buggy", set_code='t29d', number='D9', mana_cost='{4}', cmc=4.0, type_line='Artifact — Vehicle', power='5', toughness='5', colors=[], color_identity=[], keywords=['Crew', 'Hideaway'], oracle_text="Hideaway 4 (When this artifact enters, look at the top four cards of your library, exile one face down, then put the rest on the bottom in a random order.)\nWhenever this Vehicle deals combat damage to a player, you may cast the exiled card without paying its mana cost. If you do, return this Vehicle to its owner's hand.\nCrew 2"),
    card('Watcher for Tomorrow', set_code='t29d', number='D10', mana_cost='{1}{U}', cmc=2.0, type_line='Creature — Human Wizard', power='2', toughness='1', colors=['U'], color_identity=['U'], keywords=['Hideaway'], oracle_text="Hideaway 4 (When this creature enters, look at the top four cards of your library, exile one face down, then put the rest on the bottom in a random order.)\nThis creature enters tapped.\nWhen this creature leaves the battlefield, put the exiled card into its owner's hand."),
    card("Collector's Cage", set_code='t29d', number='D11', mana_cost='{1}{W}', cmc=2.0, type_line='Artifact', colors=['W'], color_identity=['W'], keywords=['Hideaway'], oracle_text='Hideaway 5 (When this artifact enters, look at the top five cards of your library, exile one face down, then put the rest on the bottom in a random order.)\n{1}, {T}: Put a +1/+1 counter on target creature you control. Then if you control three or more creatures with different powers, you may play the exiled card without paying its mana cost.'),
    card('Rabble Rousing', set_code='t29d', number='D12', mana_cost='{4}{W}', cmc=5.0, type_line='Enchantment', colors=['W'], color_identity=['W'], keywords=['Hideaway'], oracle_text='Hideaway 5 (When this enchantment enters, look at the top five cards of your library, exile one face down, then put the rest on the bottom in a random order.)\nWhenever you attack with one or more creatures, create that many 1/1 green and white Citizen creature tokens. Then if you control ten or more creatures, you may play the exiled card without paying its mana cost.'),
    card('Wiretapping', set_code='t29d', number='D13', mana_cost='{4}{U}', cmc=5.0, type_line='Enchantment', colors=['U'], color_identity=['U'], keywords=['Hideaway'], oracle_text='Hideaway 5 (When this enchantment enters, look at the top five cards of your library, exile one face down, then put the rest on the bottom in a random order.)\nWhenever you draw your first card during each of your draw steps, draw a card. Then if you have nine or more cards in hand, you may play the exiled card without paying its mana cost.'),
    card('Cemetery Tampering', set_code='t29d', number='D14', mana_cost='{2}{B}', cmc=3.0, type_line='Enchantment', colors=['B'], color_identity=['B'], keywords=['Mill', 'Hideaway'], oracle_text='Hideaway 5 (When this enchantment enters, look at the top five cards of your library, exile one face down, then put the rest on the bottom in a random order.)\nAt the beginning of your upkeep, you may mill three cards. Then if there are twenty or more cards in your graveyard, you may play the exiled card without paying its mana cost.'),
    card('Widespread Thieving', set_code='t29d', number='D15', mana_cost='{2}{R}', cmc=3.0, type_line='Enchantment', colors=['R'], color_identity=['B', 'G', 'R', 'U', 'W'], keywords=['Treasure', 'Hideaway'], oracle_text='Hideaway 5 (When this enchantment enters, look at the top five cards of your library, exile one face down, then put the rest on the bottom in a random order.)\nWhenever you cast a multicolored spell, create a Treasure token. Then you may pay {W}{U}{B}{R}{G}. If you do, you may play the exiled card without paying its mana cost.'),
    # cards that read the same new wordings (a library with twenty or fewer cards; "the exiled card" in the middle of an ability)
    card('Isleback Spawn', set_code='t29d', number='D16', mana_cost='{5}{U}{U}', cmc=7.0, type_line='Creature — Kraken', power='4', toughness='8', colors=['U'], color_identity=['U'], keywords=['Shroud'], oracle_text="Shroud (This creature can't be the target of spells or abilities.)\nThis creature gets +4/+8 as long as a library has twenty or fewer cards in it."),
    card('Djeru and Hazoret', set_code='t29d', number='D17', mana_cost='{2}{R}{R}{W}', cmc=5.0, type_line='Legendary Creature — Human God', power='5', toughness='4', colors=['R', 'W'], color_identity=['R', 'W'], oracle_text='As long as you have one or fewer cards in hand, Djeru and Hazoret has vigilance and haste.\nWhenever Djeru and Hazoret attacks, look at the top six cards of your library. You may exile a legendary creature card from among them. Put the rest on the bottom of your library in a random order. Until end of turn, you may cast the exiled card without paying its mana cost.'),
    # what the hidden cards are
    card('Harmless Offering', set_code='t29d', number='F1', mana_cost='{2}{R}', cmc=3.0, type_line='Sorcery', colors=['R'], color_identity=['R'], oracle_text='Target opponent gains control of target permanent you control.'),
    card('Lightning Helix', set_code='t29d', number='F3', mana_cost='{R}{W}', cmc=2.0, type_line='Instant', colors=['R', 'W'], color_identity=['R', 'W'], oracle_text='Lightning Helix deals 3 damage to any target. You gain 3 life.'),
    card('Exploration', set_code='t29d', number='F2', mana_cost='{G}', cmc=1.0, type_line='Enchantment', colors=['G'], color_identity=['G'], oracle_text='You may play an additional land on each of your turns.'),
    card('Trick Probe', set_code='t29d', number='E12', mana_cost='{U}', cmc=1.0, type_line='Instant', colors=['U'], color_identity=['U'], oracle_text='Scry 1.'),
    card('Cub Probe', set_code='t29d', number='E7', mana_cost='{G}', cmc=1.0, type_line='Creature — Bear', colors=['G'], color_identity=['G'], power='1', toughness='1', oracle_text=''),
    card('Legend Probe A', set_code='t29d', number='E8', mana_cost='{G}', cmc=1.0, type_line='Legendary Creature — Bear', colors=['G'], color_identity=['G'], power='1', toughness='1', oracle_text=''),
    card('Legend Probe B', set_code='t29d', number='E9', mana_cost='{G}', cmc=1.0, type_line='Legendary Creature — Bear', colors=['G'], color_identity=['G'], power='1', toughness='1', oracle_text=''),
    card('Legend Probe C', set_code='t29d', number='E10', mana_cost='{G}', cmc=1.0, type_line='Legendary Creature — Bear', colors=['G'], color_identity=['G'], power='1', toughness='1', oracle_text=''),
    card('Legend Probe D', set_code='t29d', number='E11', mana_cost='{G}', cmc=1.0, type_line='Legendary Creature — Bear', colors=['G'], color_identity=['G'], power='1', toughness='1', oracle_text=''),
    card('Brute Probe', set_code='t29d', number='E5', mana_cost='{5}{G}', cmc=6.0, type_line='Creature — Beast', colors=['G'], color_identity=['G'], power='6', toughness='6', oracle_text=''),
    card('Beast Probe', set_code='t29d', number='E6', mana_cost='{3}{G}', cmc=4.0, type_line='Creature — Beast', colors=['G'], color_identity=['G'], power='4', toughness='4', oracle_text=''),
    card('Grizzly Probe', set_code='t29d', number='E1', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Bear', colors=['G'], color_identity=['G'], power='2', toughness='2', oracle_text=''),
    card('Colossus Probe', set_code='t29d', number='E2', mana_cost='{6}{G}{G}', cmc=8.0, type_line='Creature — Beast', colors=['G'], color_identity=['G'], power='8', toughness='8', oracle_text=''),
    card('Volcanic Probe', set_code='t29d', number='E3', mana_cost='{2}{R}', cmc=3.0, type_line='Sorcery', colors=['R'], color_identity=['R'], oracle_text='Volcanic Probe deals 3 damage to each opponent.'),
    card('Quiet Probe', set_code='t29d', number='E4', mana_cost='{1}{U}', cmc=2.0, type_line='Instant', colors=['U'], color_identity=['U'], oracle_text='Draw a card.'),
]
OURS = [c["name"] for c in REAL]
HIDEAWAYS = OURS[:15]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def decision(s):
    d = s.state.rules.decision
    assert d is not None, "no decision"
    return d


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def stack_top(s, *names, pid="p1"):
    """The top of ``pid``'s library, in order (the first name on top)."""
    for name in reversed(names):
        put9(s, name, "library", pid=pid, position="top")


def play_land(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    act(s, pid, type="play_land", card_id=c.id)
    return c


def entered(s, name):
    """The permanent is in play and its hideaway trigger is on the stack (resolve it)."""
    pass_until_stack_empty(s)


def view_blob(s, pid):
    return json.dumps(s.view(pid))


@pytest.mark.parametrize("name", HIDEAWAYS)
def test_every_hideaway_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


PROBES = ("Grizzly Probe", "Colossus Probe", "Volcanic Probe", "Quiet Probe")
BIG = ("Brute Probe", "Beast Probe")  # 6/6 and 4/4: ten power together (Mosswort Bridge)


def private(s, cards, viewers=("p2", SPECTATOR)):
    """Nothing about these cards (their names, their printings) is in what an opponent or a spectator gets, in any form: views, log, decision."""
    for v in viewers:
        blob = json.dumps(s.view(v), default=str)
        for c in cards:
            assert c.name not in blob and c.card_id not in blob, (v, c.name)


def untap(s, c):
    if c.tapped:
        act(s, "p1", type="tap", card_ids=[c.id], tapped=False)


def hideaway(s, land_name, top, pick, ahead=None):
    """Alice plays the land (or any hideaway permanent put there by ``ahead``), looks at the top cards, and exiles ``pick``: returns (the
    permanent, the exiled card). Nothing about the cards leaks while she chooses or after; the choice survives a save and a load."""
    stack_top(s, *top)
    cs = [card_named(s, n) for n in top]
    permanent = ahead(s) if ahead else play_land(s, land_name)
    d = until_asked(s)
    assert d.player == "p1" and d.kind == "choose_cards" and d.min_choices == d.max_choices == 1
    assert sorted(o.label for o in d.options) == sorted(top[: len(d.options)]) and s.state.zones["p1:library"][: len(top)] == [c.id for c in cs]
    private(s, cs)
    other = reloaded(s)  # 3 (a save and a load while the choice is open)
    assert other.state.rules.decision is not None and other.state.rules.decision.id == d.id
    chosen = card_named(s, pick).id  # (the exiled card becomes a new object with a new id, 406.3: take it before)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[chosen])
    act(other, "p1", type="choose", decision_id=d.id, option_ids=[chosen])
    for t in (s, other):  # (the random order of the three is each table's own roll: what is fixed is the same)
        assert card_named(t, pick).zone == "p1:exile" and card_named(t, pick).face_down
        assert {t.state.cards[i].name for i in t.state.zones["p1:library"][-(len(top) - 1):]} == set(top) - {pick}
    check(other)
    exiled = card_named(s, pick)
    assert exiled.zone == "p1:exile" and exiled.face_down
    private(s, cs)
    assert s.view("p1")["cards"][exiled.id].get("name") == pick  # its controller may look at it at any time (406.3)
    return permanent, exiled


def test_mosswort_bridge_exiles_one_face_down_and_buries_the_rest(cards):
    s = build(cards, ("Mosswort Bridge", *PROBES))
    bridge, exiled = hideaway(s, "Mosswort Bridge", PROBES, "Volcanic Probe")
    library = s.state.zones["p1:library"]
    assert {s.state.cards[i].name for i in library[-3:]} == {"Grizzly Probe", "Colossus Probe", "Quiet Probe"}  # 702.75a: the bottom
    assert not {"Grizzly Probe", "Colossus Probe", "Quiet Probe"} & {s.state.cards[i].name for i in library[:3]}
    assert s.state.rules.exiled_with[s.state.rules.object_id(bridge.id)] == [s.state.rules.object_id(exiled.id)]  # 607.2a: linked to it
    assert bridge.tapped  # (this land enters tapped)
    check(s)


# -- the conditions of the lands (702.75: each reads its own, as the ability resolves, 608.2c) --------------------------------------------------
EXTRA = ("Brute Probe", "Beast Probe", "Cub Probe", "Legend Probe A", "Legend Probe B", "Legend Probe C", "Legend Probe D")


def creatures(s, *names, sick=False):
    out = []
    for n in names:
        c = put9(s, n, "battlefield")
        if not sick:
            s.state.rules.controlled_since[c.id].turn = 0
        out.append(c)
    return out


def swing(s, *names):
    """Alice attacks Bob with these creatures (nobody blocks) and plays on to the second main phase."""
    from tests.test_rules_conditionals import attack, through_combat

    cs = creatures(s, *names)
    act(s, "p1", type="pass_priority")  # → declare attackers
    attack(s, *((c, "p2") for c in cs))
    through_combat(s)


def empty_hands(s):
    for pid in ("p1", "p2"):
        hand = list(s.state.zones[f"{pid}:hand"])
        if hand:
            act(s, pid, type="move", card_ids=hand, to={"zone": "graveyard"})


# land: (mana to pay, its ability, makes the condition true, makes it false, a bigger library)
LANDS = {
    "Mosswort Bridge": ({"G": 1}, 3, lambda s: creatures(s, "Brute Probe", "Beast Probe"), lambda s: creatures(s, "Brute Probe"), 9),
    "Shelldock Isle": ({"U": 1}, 3, lambda s: None, lambda s: None, 30),
    "Howltooth Hollow": ({"B": 1}, 3, empty_hands, lambda s: put9(s, "Island", "hand", pid="p2"), 9),
    "Spinerock Knoll": ({"R": 1}, 3, lambda s: swing(s, "Brute Probe", "Beast Probe"), lambda s: None, 9),
    "Windbrisk Heights": ({"W": 1}, 3, lambda s: swing(s, "Brute Probe", "Beast Probe", "Cub Probe"), lambda s: swing(s, "Brute Probe", "Beast Probe"), 9),
    "Clive's Hideaway": ({"C": 2}, 2, lambda s: creatures(s, *EXTRA[3:]), lambda s: creatures(s, *EXTRA[3:6]), 9),
}


def land_scene(cards, name, big=False):
    pay, ability, yes, no, forests = LANDS[name]
    s = build(cards, (name, *PROBES, *EXTRA), forests=forests if big else 9, islands=forests if big else 10)
    land, exiled = hideaway(s, name, PROBES, "Quiet Probe")
    return s, land, exiled, pay, ability, yes, no


def activate(s, land, pay, ability):
    untap(s, land)
    mana(s, **pay)
    act(s, "p1", type="activate_ability", card_id=land.id, ability=ability)
    pass_until_stack_empty(s)


@pytest.mark.parametrize("name", list(LANDS))
def test_each_land_plays_the_exiled_card_only_when_its_condition_holds(cards, name):
    pay, ability, yes, no, forests = LANDS[name]
    # the condition is false: the cost is paid, the ability resolves and does nothing - no question, nothing leaked, the card stays (608.2c)
    s, land, exiled, pay, ability, yes, no = land_scene(cards, name, big=name == "Shelldock Isle")
    no(s)
    activate(s, land, pay, ability)
    assert s.state.rules.decision is None and not s.state.zones.get("stack") and land.tapped and s.state.players["p1"].mana == {}
    assert exiled.zone == "p1:exile" and exiled.face_down
    assert s.state.rules.hideaway  # (still linked, still looked at)
    private(s, [exiled])
    check(s)
    # the condition is true: Alice is asked (she may play it), nobody else sees the card, and the choice survives a save and a load
    s, land, exiled, pay, ability, yes, no = land_scene(cards, name)
    yes(s)
    hand = len(s.state.zones["p1:hand"])
    activate(s, land, pay, ability)
    d = decision(s)
    assert d.player == "p1" and [o.label for o in d.options] == ["Quiet Probe"] and d.min_choices == 0
    private(s, [exiled])
    other = reloaded(s)
    assert other.state.rules.decision.id == d.id
    oid = d.options[0].id
    act(other, "p1", type="choose", decision_id=d.id, option_ids=[oid])
    pass_until_stack_empty(other)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[oid])
    pass_until_stack_empty(s)
    for t in (s, other):
        assert card_named(t, "Quiet Probe").zone == "p1:graveyard"  # cast without paying its mana cost: it drew, and went to the graveyard
        assert t.state.rules.hideaway == {} and t.state.rules.free_casts == [] and t.state.rules.free_cast_then is None
    assert len(s.state.zones["p1:hand"]) == hand + 1
    assert s.state.players["p1"].mana == {}
    check(s)
    check(other)


# -- a land is played, not cast (305.1, 305.2a-b) -------------------------------------------------------------------------------------------------------
TOWER = ("Command Tower", "Grizzly Probe", "Volcanic Probe", "Quiet Probe")


def tower_scene(cards, drop_left):
    """Alice plays Shelldock Isle, which hides Command Tower; with Exploration she has a second land play left (305.2), without it none."""
    s = build(cards, ("Shelldock Isle", "Exploration", *TOWER))
    if drop_left:
        put9(s, "Exploration", "battlefield")
    isle, tower = hideaway(s, "Shelldock Isle", TOWER, "Command Tower")
    return s, isle, tower


def test_the_exiled_land_is_played_with_a_land_play_left(cards):
    s, isle, tower = tower_scene(cards, drop_left=True)
    assert s.state.rules.lands_this_turn("p1", s.state.turn.number) == 1
    activate(s, isle, {"U": 1}, 3)
    d = decision(s)
    assert [o.label for o in d.options] == ["Command Tower (play as a land)"]
    private(s, [tower])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    pass_until_stack_empty(s)
    assert tower.zone == "p1:battlefield" and not tower.face_down  # 406.3a: turned face up as it is played
    assert s.state.rules.lands_this_turn("p1", s.state.turn.number) == 2  # 305.2a: a land play, the second
    assert s.state.rules.hideaway == {} and not s.state.zones.get("stack")
    assert "Command Tower" in json.dumps(s.view("p2"))  # (public now)
    check(s)


def test_with_no_land_play_left_the_question_is_asked_all_the_same_and_leaks_nothing(cards):
    s, isle, tower = tower_scene(cards, drop_left=False)
    assert s.state.rules.lands_this_turn("p1", s.state.turn.number) == 1
    activate(s, isle, {"U": 1}, 3)
    d = decision(s)
    assert d.player == "p1" and d.options == [] and d.min_choices == 0  # 305.2b: it can't be played - and the table can't tell why nothing was offered
    for v in ("p2", SPECTATOR):
        view = s.view(v)
        assert view["rules"]["decision"]["kind"] == "waiting" and "options" not in view["rules"]["decision"]
        assert "nothing to cast" not in json.dumps(view)
    private(s, [tower])
    other = reloaded(s)
    act(other, "p1", type="choose", decision_id=d.id, option_ids=[])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    pass_until_stack_empty(s)
    pass_until_stack_empty(other)
    for t in (s, other):
        assert card_named(t, "Command Tower").zone == "p1:exile" and card_named(t, "Command Tower").face_down  # still hidden, still hers
        assert t.state.rules.hideaway
    private(s, [tower])
    check(s)
    check(other)


def resolve_all(s, picks=()):
    """Resolve the stack; a hideaway question takes the first of ``picks`` it offers, anything else the first option."""
    picks = list(picks)
    for _ in range(60):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            want = next((o for p in picks for o in d.options if o.label == p), None)
            if want is not None:
                picks.remove(want.label)
            ids = [want.id] if want is not None else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    raise AssertionError("never settled")


def to_combat_damage(s, attackers, until_kind="choose_cards"):
    """Alice attacks Bob with ``attackers`` (nobody blocks) and plays on until she is asked a question (returned) or the second main phase."""
    act(s, "p1", type="pass_priority")  # → declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            return d
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return None
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


SIX = ("Grizzly Probe", "Quiet Probe", "Volcanic Probe", "Colossus Probe", "Beast Probe", "Cub Probe")


def ursine_scene(cards, library=True):
    s = build(cards, ("Evercoat Ursine", *SIX))
    if library:
        stack_top(s, *SIX)
    else:
        lib = list(s.state.zones["p1:library"])
        act(s, "p1", type="move", card_ids=lib, to={"zone": "graveyard"})
    ursine = to_hand_card(s, "Evercoat Ursine")
    mana(s, G=5)
    act(s, "p1", type="cast_spell", card_id=ursine.id)
    return s, ursine


def to_hand_card(s, name):
    c = card_named(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def test_evercoat_ursine_hides_two_cards_and_plays_one_of_them_on_combat_damage(cards):
    s, ursine = ursine_scene(cards)
    first = [card_named(s, n) for n in SIX]
    resolve_all(s, picks=("Quiet Probe", "Colossus Probe"))  # 702.75: two instances, two triggers, each looks at the top three in turn
    assert ursine.zone == "p1:battlefield"
    exiled = {c.name for c in s.state.cards.values() if c.zone == "p1:exile" and c.face_down}
    assert exiled == {"Quiet Probe", "Colossus Probe"}, exiled
    assert s.state.rules.exiled_with[s.state.rules.object_id(ursine.id)] and len(s.state.rules.exiled_with[s.state.rules.object_id(ursine.id)]) == 2
    private(s, first)
    s.state.rules.controlled_since[ursine.id].turn = 0
    d = to_combat_damage(s, [ursine])  # 6 trample damage to Bob: "if there are cards exiled with it, you may play one of them"
    assert d is not None and d.player == "p1" and sorted(o.label for o in d.options) == ["Colossus Probe", "Quiet Probe"]
    assert d.min_choices == 0 and d.max_choices == 1
    private(s, first)
    other = reloaded(s)
    pick_id = next(o.id for o in d.options if o.label == "Quiet Probe")
    for t in (s, other):
        act(t, "p1", type="choose", decision_id=d.id, option_ids=[pick_id])
        resolve_all(t)
        assert card_named(t, "Quiet Probe").zone == "p1:graveyard"
        left = card_named(t, "Colossus Probe")
        assert left.zone == "p1:exile" and left.face_down  # the other one stays hidden under it
    private(s, [card_named(s, "Colossus Probe")])
    check(s)
    check(other)


def test_evercoat_ursine_with_nothing_exiled_does_not_trigger(cards):
    s, ursine = ursine_scene(cards, library=False)  # (an empty library: nothing to look at, nothing exiled)
    resolve_all(s)
    assert ursine.zone == "p1:battlefield" and not [c for c in s.state.cards.values() if c.zone == "p1:exile"]
    s.state.rules.controlled_since[ursine.id].turn = 0
    assert to_combat_damage(s, [ursine]) is None  # 603.4: the intervening "if" is false, the trigger never goes on the stack
    assert not s.state.zones.get("stack")
    check(s)


def test_smugglers_buggy_casts_the_exiled_card_and_returns_to_hand(cards):
    s = build(cards, ("Smuggler's Buggy", *PROBES, "Beast Probe"))
    buggy, exiled = hideaway(s, "Smuggler's Buggy", PROBES, "Grizzly Probe",
                             ahead=lambda t: cast_artifact(t, "Smuggler's Buggy", C=4))
    resolve_all(s)
    (crew,) = creatures(s, "Beast Probe")
    s.state.rules.controlled_since[buggy.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=buggy.id, ability=2, crew=[crew.id])
    pass_until_stack_empty(s)
    d = to_combat_damage(s, [buggy])  # 5 damage to Bob
    assert d is not None and [o.label for o in d.options] == ["Grizzly Probe"]
    private(s, [exiled])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    resolve_all(s)
    assert card_named(s, "Grizzly Probe").zone == "p1:battlefield"
    assert buggy.zone == "p1:hand"  # "If you do, return this Vehicle to its owner's hand."
    check(s)


def test_smugglers_buggy_stays_if_the_exiled_card_is_not_cast(cards):
    s = build(cards, ("Smuggler's Buggy", *PROBES, "Beast Probe"))
    buggy, exiled = hideaway(s, "Smuggler's Buggy", PROBES, "Volcanic Probe", ahead=lambda t: cast_artifact(t, "Smuggler's Buggy", C=4))
    resolve_all(s)
    (crew,) = creatures(s, "Beast Probe")
    s.state.rules.controlled_since[buggy.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=buggy.id, ability=2, crew=[crew.id])
    pass_until_stack_empty(s)
    d = to_combat_damage(s, [buggy])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])  # she declines
    resolve_all(s)
    assert exiled.zone == "p1:exile" and exiled.face_down and buggy.zone == "p1:battlefield"
    private(s, [exiled])
    check(s)


def test_smugglers_buggy_cannot_cast_a_land_and_leaks_nothing(cards):
    s = build(cards, ("Smuggler's Buggy", "Command Tower", "Grizzly Probe", "Volcanic Probe", "Quiet Probe", "Beast Probe"))
    buggy, tower = hideaway(s, "Smuggler's Buggy", TOWER, "Command Tower", ahead=lambda t: cast_artifact(t, "Smuggler's Buggy", C=4))
    resolve_all(s)
    (crew,) = creatures(s, "Beast Probe")
    s.state.rules.controlled_since[buggy.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=buggy.id, ability=2, crew=[crew.id])
    pass_until_stack_empty(s)
    d = to_combat_damage(s, [buggy])
    assert d is not None and d.options == []  # "cast": a land can't be cast (305.1) - asked all the same, so nothing is told
    for v in ("p2", SPECTATOR):
        assert "nothing to cast" not in json.dumps(s.view(v))
    private(s, [tower])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    resolve_all(s)
    assert buggy.zone == "p1:battlefield" and tower.zone == "p1:exile"
    check(s)


def cast_artifact(s, name, **pay):
    c = to_hand_card(s, name)
    mana(s, **pay)
    act(s, "p1", type="cast_spell", card_id=c.id)
    return c


def test_watcher_for_tomorrow_returns_the_exiled_card_to_its_owners_hand(cards):
    s = build(cards, ("Watcher for Tomorrow", *PROBES, "Lightning Bolt"))
    watcher, exiled = hideaway(s, "Watcher for Tomorrow", PROBES, "Colossus Probe",
                               ahead=lambda t: cast_artifact(t, "Watcher for Tomorrow", U=1, C=1))
    resolve_all(s)
    assert watcher.zone == "p1:battlefield" and watcher.tapped  # (this creature enters tapped)
    bolt = to_hand_card(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[watcher.id])
    resolve_all(s)
    assert watcher.zone == "p1:graveyard"
    colossus = card_named(s, "Colossus Probe")
    assert colossus.zone == "p1:hand" and not colossus.face_down  # "When this creature leaves the battlefield, put the exiled card into its owner's hand."
    assert s.state.rules.hideaway == {}
    private(s, [colossus])  # (it is in a hand now: nobody else knows it)
    check(s)


# -- who may look (702.75a, 406.3) ---------------------------------------------------------------------------------------------------------------------
def build3(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [(1, "Mosswort Bridge"), (1, "Harmless Offering"), *((1, n) for n in PROBES), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Harmless Offering"), (1, "Brute Probe"), (1, "Beast Probe"), (10, "Island")])
    carol = deck(cards, "Krenko, Mob Boss", [(10, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)],
                                    shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def sees(s, viewer, c):
    return s.view(viewer)["cards"].get(c.id, {}).get("name") == c.name


def give(s, giver, name, to, target_id):
    c = to_hand_card_of(s, giver, name)
    mana(s, giver, R=3)
    act(s, giver, type="cast_spell", card_id=c.id, targets=[to, target_id], target_counts=[1, 1])
    resolve_all(s)


def to_hand_card_of(s, pid, name):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def test_whoever_controls_the_permanent_may_look_and_those_who_looked_go_on_looking(cards):
    s = build3(cards)
    bridge, exiled = hideaway(s, "Mosswort Bridge", PROBES, "Colossus Probe")
    assert sees(s, "p1", exiled) and not sees(s, "p2", exiled) and not sees(s, "p3", exiled) and not sees(s, SPECTATOR, exiled)
    give(s, "p1", "Harmless Offering", "p2", bridge.id)  # Bob now controls the land that hid it
    assert bridge.controller == "p2"
    assert sees(s, "p1", exiled) and sees(s, "p2", exiled)  # 702.75a: its controller; 406.3: Alice keeps looking
    assert not sees(s, "p3", exiled) and not sees(s, SPECTATOR, exiled)
    private(s, [exiled], viewers=("p3", SPECTATOR))
    check(s)
    # Bob gives it to Carol on his turn: Carol may look, and Bob, having been allowed to, may go on looking (406.3)
    from tests.test_rules_conditionals import to_turn

    to_turn(s, 2)
    give(s, "p2", "Harmless Offering", "p3", bridge.id)
    assert bridge.controller == "p3"
    assert all(sees(s, p, exiled) for p in ("p1", "p2", "p3")) and not sees(s, SPECTATOR, exiled)
    check(s)
    # the land leaves the battlefield: nobody controls it any more, and those who looked still may, until the card leaves exile
    act(s, "p3", type="move", card_ids=[bridge.id], to={"zone": "graveyard"})
    act(s, s.state.rules.priority, type="pass_priority")  # (the engine looks at the table again)
    assert all(sees(s, p, exiled) for p in ("p1", "p2", "p3")) and not sees(s, SPECTATOR, exiled)
    check(s)


def test_the_new_controller_plays_the_exiled_card(cards):
    s = build3(cards)
    bridge, exiled = hideaway(s, "Mosswort Bridge", PROBES, "Colossus Probe")
    give(s, "p1", "Harmless Offering", "p2", bridge.id)
    for n in ("Brute Probe", "Beast Probe"):
        c = card_named(s, n, "p2")
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
        s.state.rules.controlled_since[c.id].turn = 0
    from tests.test_rules_conditionals import to_turn

    to_turn(s, 2)  # Bob's first main phase: the land untapped under him
    assert s.state.turn.active_player == "p2" and not bridge.tapped
    mana(s, "p2", G=1)
    act(s, "p2", type="activate_ability", card_id=bridge.id, ability=3)
    pass_until_stack_empty(s)
    d = decision(s)
    assert d.player == "p2" and [o.label for o in d.options] == ["Colossus Probe"]  # 406.3b: he may look at it, so he may play it
    private(s, [exiled], viewers=("p3", SPECTATOR))
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    resolve_all(s)
    colossus = card_named(s, "Colossus Probe")
    assert colossus.zone == "p2:battlefield" and colossus.controller == "p2" and colossus.owner == "p1"
    check(s)


# -- the permanents (not lands) and their conditions ----------------------------------------------------------------------------------------------------
FIVE = ("Grizzly Probe", "Colossus Probe", "Volcanic Probe", "Quiet Probe", "Trick Probe")


def drive(s, stop_turn=None, limit=200):
    """Pass priority, answering whatever else comes up the plain way (no attackers, no blockers, yes to a question, to pay, the first option),
    until the free cast question ("Choose a spell to cast …") is asked: returned. None if the turn ``stop_turn`` is reached first (or all done)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            if d.kind == "choose_cards" and d.prompt.startswith("Choose a spell to cast"):
                return d
            if d.kind == "declare_attackers":
                act(s, d.player, type="declare_attackers", attackers=[])
            elif d.kind == "declare_blockers":
                act(s, d.player, type="declare_blockers", blocks=[])
            else:
                ids = [o.id for o in d.options]
                pick = next((i for i in ("yes", "pay") if i in ids), None)
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick] if pick else ids[: max(1, d.min_choices)])
        elif not s.state.zones.get("stack") and (stop_turn is None or (s.state.turn.number >= stop_turn and s.state.turn.phase == "main1")):
            return None
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never got there")


def plays_it(s, d, label):
    """Alice plays the card (the question's only option) and everything resolves; the same on a table reloaded from the save at the question."""
    other = reloaded(s)
    assert [o.label for o in d.options] == [label]
    for t in (s, other):
        act(t, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        resolve_all(t)
        assert card_named(t, label).zone in ("p1:graveyard", "p1:battlefield") and t.state.rules.hideaway == {}
    check(s)
    check(other)


def test_fight_rigging_plays_it_with_a_power_seven_creature_after_the_counter(cards):
    for body, asked in (("Brute Probe", True), ("Beast Probe", False)):  # 6/6 becomes 7/7; 4/4 becomes 5/5
        s = build(cards, ("Fight Rigging", *FIVE, body))
        creatures(s, body)
        rigging, exiled = hideaway(s, "Fight Rigging", FIVE, "Quiet Probe", ahead=lambda t: cast_artifact(t, "Fight Rigging", G=1, C=2))
        resolve_all(s)
        act(s, "p1", type="pass_priority")  # → beginning of combat: the trigger, with its one target
        d = drive(s)
        assert (d is not None) == asked, body
        assert card_named(s, body).counters == {"+1/+1": 1}
        if asked:
            private(s, [exiled])
            plays_it(s, d, "Quiet Probe")
        else:
            assert exiled.zone == "p1:exile" and exiled.face_down
            private(s, [exiled])
            check(s)


def test_collectors_cage_needs_three_different_powers(cards):
    for names, asked in ((("Brute Probe", "Beast Probe", "Cub Probe"), True), (("Legend Probe A", "Legend Probe B"), False)):
        s = build(cards, ("Collector's Cage", *FIVE, *names))
        creatures(s, *names)
        cage, exiled = hideaway(s, "Collector's Cage", FIVE, "Quiet Probe", ahead=lambda t: cast_artifact(t, "Collector's Cage", W=1, C=1))
        resolve_all(s)
        mana(s, C=1)
        act(s, "p1", type="activate_ability", card_id=cage.id, ability=1, targets=[card_named(s, names[-1]).id])
        pass_until_stack_empty(s)  # (the counter makes the last one's power different: 6, 4, 2 / 1, 2)
        d = s.state.rules.decision
        assert (d is not None) == asked, names
        if asked:
            private(s, [exiled])
            plays_it(s, d, "Quiet Probe")
        else:
            assert exiled.zone == "p1:exile" and exiled.face_down
            check(s)


def test_rabble_rousing_counts_the_tokens_it_just_made(cards):
    names = ("Brute Probe", "Beast Probe", "Cub Probe", "Legend Probe A", "Legend Probe B", "Legend Probe C", "Legend Probe D")
    for attackers, asked in ((names, True), (names[:2], False)):  # 7 + 7 tokens; 2 + 2
        s = build(cards, ("Rabble Rousing", *FIVE, *names))
        cs = creatures(s, *attackers)
        rousing, exiled = hideaway(s, "Rabble Rousing", FIVE, "Quiet Probe", ahead=lambda t: cast_artifact(t, "Rabble Rousing", W=1, C=4))
        resolve_all(s)
        act(s, "p1", type="pass_priority")  # → declare attackers
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in cs])
        d = drive(s)
        citizens = [c for c in s.state.cards.values() if c.name == "Citizen" and c.zone == "p1:battlefield"]
        assert len(citizens) == len(attackers)  # "create that many"
        assert (d is not None) == asked, attackers
        if asked:
            private(s, [exiled])
            plays_it(s, d, "Quiet Probe")
        else:
            assert exiled.zone == "p1:exile" and exiled.face_down
            check(s)


def hand_of(s, n):
    """Alice has exactly n cards in hand."""
    hand = list(s.state.zones["p1:hand"])
    extra = [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][: max(0, n - len(hand))]
    if extra:
        act(s, "p1", type="move", card_ids=extra, to={"zone": "hand"})
    if len(hand) > n:
        act(s, "p1", type="move", card_ids=hand[n:], to={"zone": "graveyard"})


def test_wiretapping_draws_twice_and_asks_with_nine_cards(cards):
    for in_hand, asked in ((7, True), (6, False)):  # the draw step's card and the one Wiretapping draws: 9 / 8
        s = build(cards, ("Wiretapping", *FIVE), forests=20)
        wire, exiled = hideaway(s, "Wiretapping", FIVE, "Quiet Probe", ahead=lambda t: cast_artifact(t, "Wiretapping", U=1, C=4))
        resolve_all(s)
        hand_of(s, in_hand)
        d = drive(s, stop_turn=3)
        assert (d is not None) == asked, in_hand
        assert s.state.turn.number == 3 and len(s.state.zones["p1:hand"]) == in_hand + 2 - (0 if asked else 0)
        if asked:
            private(s, [exiled])
            plays_it(s, d, "Quiet Probe")
        else:
            assert exiled.zone == "p1:exile" and exiled.face_down
            private(s, [exiled])
            check(s)


def test_cemetery_tampering_mills_then_asks_with_twenty_in_the_graveyard(cards):
    for before, asked in ((17, True), (16, False)):  # three milled: 20 / 19
        s = build(cards, ("Cemetery Tampering", *FIVE), forests=40)
        tampering, exiled = hideaway(s, "Cemetery Tampering", FIVE, "Quiet Probe", ahead=lambda t: cast_artifact(t, "Cemetery Tampering", B=1, C=2))
        resolve_all(s)
        forests = [c for c in s.state.zones["p1:library"] if s.state.cards[c].name == "Forest"][:before]
        act(s, "p1", type="move", card_ids=forests, to={"zone": "graveyard"})
        d = drive(s, stop_turn=3)
        assert (d is not None) == asked, before
        assert sum(1 for c in s.state.cards.values() if c.zone == "p1:graveyard") >= before + 3
        if asked:
            private(s, [exiled])
            plays_it(s, d, "Quiet Probe")
        else:
            assert exiled.zone == "p1:exile" and exiled.face_down
            check(s)


def test_widespread_thieving_asks_after_paying_all_five_colors(cards):
    s = build(cards, ("Widespread Thieving", "Lightning Helix", *FIVE))
    thieving, exiled = hideaway(s, "Widespread Thieving", FIVE, "Quiet Probe", ahead=lambda t: cast_artifact(t, "Widespread Thieving", R=1, C=2))
    resolve_all(s)
    helix = to_hand_card(s, "Lightning Helix")
    mana(s, R=2, W=2, U=1, B=1, G=1)
    act(s, "p1", type="cast_spell", card_id=helix.id, targets=["p2"])  # a multicolored spell: a Treasure, then she may pay {W}{U}{B}{R}{G}
    d = drive(s)
    assert any(c.name == "Treasure" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    assert d is not None and s.state.players["p1"].mana == {}  # (the five colors were paid)
    private(s, [exiled])
    plays_it(s, d, "Quiet Probe")


def test_widespread_thieving_without_paying_nothing_is_played(cards):
    s = build(cards, ("Widespread Thieving", "Lightning Helix", *FIVE))
    thieving, exiled = hideaway(s, "Widespread Thieving", FIVE, "Quiet Probe", ahead=lambda t: cast_artifact(t, "Widespread Thieving", R=1, C=2))
    resolve_all(s)
    helix = to_hand_card(s, "Lightning Helix")
    mana(s, R=1, W=1)
    act(s, "p1", type="cast_spell", card_id=helix.id, targets=["p2"])
    assert drive(s) is None  # (she can't pay {W}{U}{B}{R}{G}: it isn't even offered)
    assert exiled.zone == "p1:exile" and exiled.face_down
    check(s)


# -- cards that read the same new wordings ------------------------------------------------------------------------------------------------------------
def test_isleback_spawn_grows_while_any_library_has_twenty_or_fewer_cards(cards):
    from tests.wave9c_kit import pt

    s = build(cards, ("Isleback Spawn",), forests=30, islands=30)
    creatures(s, "Isleback Spawn", sick=True)
    assert pt(s, "Isleback Spawn") == (4, 8)  # (Alice's library and Bob's both hold more than twenty)
    bob = list(s.state.zones["p2:library"])
    act(s, "p2", type="move", card_ids=bob[: len(bob) - 21], to={"zone": "graveyard"})
    assert len(s.state.zones["p2:library"]) == 21 and pt(s, "Isleback Spawn") == (4, 8)
    act(s, "p2", type="move", card_ids=s.state.zones["p2:library"][:1], to={"zone": "graveyard"})
    assert len(s.state.zones["p2:library"]) == 20 and pt(s, "Isleback Spawn") == (8, 16)  # "a library": Bob's counts
    check(s)


def test_djeru_and_hazoret_casts_the_exiled_legend_this_turn_for_free(cards):
    for take in ("Legend Probe A", None):
        s = build(cards, ("Djeru and Hazoret", "Legend Probe A", "Grizzly Probe", "Volcanic Probe", "Quiet Probe", "Trick Probe", "Colossus Probe"))
        (djeru,) = creatures(s, "Djeru and Hazoret")
        top = ("Grizzly Probe", "Volcanic Probe", "Legend Probe A", "Quiet Probe", "Trick Probe", "Colossus Probe")
        stack_top(s, *top)
        cs = [card_named(s, n) for n in top]
        d = to_combat_damage(s, [djeru])  # the attack trigger: look at six, may exile a legendary creature card from among them
        assert d is not None and d.player == "p1" and [o.label for o in d.options] == ["Legend Probe A"] and d.min_choices == 0
        private(s, cs)
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id] if take else [])
        from tests.test_rules_conditionals import through_combat

        through_combat(s)
        legend = card_named(s, "Legend Probe A")
        assert {c.name for c in s.state.cards.values() if c.zone == "p1:library"} >= {"Grizzly Probe", "Volcanic Probe", "Quiet Probe"}  # the rest went to the bottom
        if take:
            assert legend.zone == "p1:exile" and not legend.face_down  # (face up: nothing says "face down")
            assert [p.card for p in s.state.rules.permissions] == [legend.id]
            act(s, "p1", type="cast_spell", card_id=legend.id, free=True)  # main phase 2: free, this turn (118.9)
            pass_until_stack_empty(s)
            assert legend.zone == "p1:battlefield" and s.state.players["p1"].mana == {}
        else:
            assert legend.zone == "p1:library" and s.state.rules.permissions == []
        check(s)


def test_the_older_unnumbered_hideaway_line_is_not_read():
    from app.rules import keyword_triggers

    assert keyword_triggers.supported("hideaway", "Hideaway 4") and keyword_triggers.supported("hideaway", "Hideaway 3, hideaway 3")
    assert not keyword_triggers.supported("hideaway", "Hideaway")  # 702.75b: the Oracle text of those cards is "Hideaway 4" plus "enters tapped"
    assert not keyword_triggers.supported("hideaway", "Hideaway X")


def test_a_hideaway_land_is_not_playable_from_exile_by_the_ordinary_land_play(cards):
    s, isle, tower = tower_scene(cards, drop_left=True)
    hints = s.view("p1")["rules"]["hints"]
    assert tower.id not in hints.get("playable_lands", []) and tower.id not in hints.get("castable", [])  # 406.3a, 305.1: only the ability lets her
    with pytest.raises(ActionError):
        act(s, "p1", type="play_land", card_id=tower.id)
