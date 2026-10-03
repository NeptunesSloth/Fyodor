"""Wave 6R: the independent review of wave 6 (CR 2026-09-25): regressions for what it found, and the seams where
wave-6 features meet. Cards carry their real Oracle text from the card database (made-up cards are named "Probe")."""

from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_conditionals import life, on_field, pick, settle, to_hand, until_asked
from tests.test_rules_effects import replay_matches

EXTRA = [
    card('Impulsive Destruction', set_code='tst', number='W1', mana_cost='', cmc=0.0, type_line='Sorcery',
         oracle_text="Each player may sacrifice an artifact or enchantment. Impulsive Destruction deals 3 damage to each player who didn't sacrifice a permanent this way.", colors=[], color_identity=[], keywords=[]),
    card('Magnetic Mine', set_code='tst', number='W2', mana_cost='{4}', cmc=4.0, type_line='Artifact',
         oracle_text="Whenever another artifact is put into a graveyard from the battlefield, this artifact deals 2 damage to that artifact's controller.", colors=[], color_identity=[], keywords=[]),
    card('Sol Ring', set_code='tst', number='W3', mana_cost='{1}', cmc=1.0, type_line='Artifact',
         oracle_text='{T}: Add {C}{C}.', colors=[], color_identity=[], keywords=[]),
    card('Thalia, Heretic Cathar', set_code='tst', number='W4', mana_cost='{2}{W}', cmc=3.0,
         type_line='Legendary Creature — Human Soldier',
         oracle_text='First strike\nCreatures and nonbasic lands your opponents control enter tapped.', power='3',
         toughness='2', colors=['W'], color_identity=['W'], keywords=['First strike']),
    card('Memnite', set_code='tst', number='W5', mana_cost='{0}', cmc=0.0, type_line='Artifact Creature — Construct',
         power='1', toughness='1'),
    card('Voyager Staff', set_code='tst', number='W6', mana_cost='{1}', cmc=1.0, type_line='Artifact',
         oracle_text="{2}, Sacrifice this artifact: Exile target creature. Return the exiled card to the battlefield under "
                     "its owner's control at the beginning of the next end step.", colors=[], color_identity=[]),
    card('Hide on the Ceiling', set_code='tst', number='W7', mana_cost='{X}{U}', cmc=1.0, type_line='Instant',
         oracle_text="Exile X target artifacts and/or creatures. Return the exiled cards to the battlefield under their "
                     "owners' control at the beginning of the next end step.", colors=['U'], color_identity=['U']),
    card('Sentinel of the Eternal Watch', set_code='tst', number='W8', mana_cost='{5}{W}', cmc=6.0,
         type_line='Creature — Giant Soldier',
         oracle_text="Vigilance (Attacking doesn't cause this creature to tap.)\nAt the beginning of combat on each "
                     "opponent's turn, tap target creature that player controls.", power='4', toughness='6',
         colors=['W'], color_identity=['W'], keywords=['Vigilance']),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def build(cards, p1=(), p2=()):
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in p1), (12, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in p2), (12, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def roundtrip(s):
    replay_matches(s)
    saved = s.state.model_dump_json()
    loaded = GameSession(GameState.model_validate_json(saved), cards=s.cards)
    assert loaded.state.model_dump(mode="json") == s.state.model_dump(mode="json")


# -- each_may: choices in turn order, then the actions simultaneously (101.4) -----------------------------------
def test_each_may_sacrifices_happen_simultaneously(cards):
    """Impulsive Destruction: Alice sacrifices Magnetic Mine and Bob sacrifices Sol Ring. 101.4: both choose (in turn
    order), then both are sacrificed at once — the Mine leaves with Sol Ring, so it looks back and sees Sol Ring go
    (603.10a) and deals 2 damage to Bob. Paid one after the other, the Mine would be gone already."""
    s = build(cards, p1=("Impulsive Destruction", "Magnetic Mine"), p2=("Sol Ring",))
    mine = on_field(s, "Magnetic Mine")
    ring = on_field(s, "Sol Ring", "p2")
    spell = to_hand(s, "Impulsive Destruction")
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = until_asked(s)
    assert d.player == "p1"
    pick(s, "pay")
    if s.state.rules.decision.player == "p1":  # (the artifact to sacrifice, if asked)
        pick(s, mine.id)
    assert s.state.cards[mine.id].zone.endswith("battlefield")  # (not paid yet: Bob still chooses)
    d = s.state.rules.decision
    assert d is not None and d.player == "p2"
    pick(s, "pay")
    if s.state.rules.decision is not None and s.state.rules.decision.player == "p2" and \
            s.state.rules.decision.kind == "choose_cards":
        pick(s, ring.id)
    settle(s)
    assert s.state.cards[mine.id].zone == "p1:graveyard" and s.state.cards[ring.id].zone == "p2:graveyard"
    assert life(s, "p1") == 40 and life(s, "p2") == 38  # (no 3 damage; the Mine's 2 to Bob)
    roundtrip(s)


def test_each_may_a_payment_that_became_unpayable_is_not_made(cards):
    """The choice is checked again as the payments are made (118.3): nothing changes in between here, so both pay."""
    s = build(cards, p1=("Impulsive Destruction", "Sol Ring"), p2=("Sol Ring",))
    on_field(s, "Sol Ring")
    on_field(s, "Sol Ring", "p2")
    spell = to_hand(s, "Impulsive Destruction")
    act(s, "p1", type="cast_spell", card_id=spell.id)
    until_asked(s)
    pick(s, "pay")
    pick(s, "decline")
    settle(s)
    assert life(s, "p1") == 40 and life(s, "p2") == 37
    assert not [c for c in zone(s.state, "p1", "battlefield") if s.state.cards[c].name == "Sol Ring"]
    roundtrip(s)


# -- "[Objects] your opponents control enter tapped": the controller is every item's (614.12) ------------------------
@pytest.mark.parametrize(("text", "n"), [
    ("Creatures and nonbasic lands your opponents control enter tapped.", 2),  # Thalia, Heretic Cathar
    ("Artifacts and creatures your opponents control enter tapped.", 2),  # Blind Obedience (promoted in wave 6)
    ("Artifacts, creatures, and lands your opponents control enter tapped.", 3),  # Frozen Aether, Kismet
])
def test_enters_tapped_items_all_belong_to_opponents(text, n):
    from app.rules import replace_grammar

    d = replace_grammar._enters_tapped(text)
    assert d is not None and len(d["who"]) == n
    assert all('"controller":"opponent"' in k for k in d["who"])


def test_enters_tapped_without_a_controller_is_everyone():
    from app.rules import replace_grammar

    d = replace_grammar._enters_tapped("Artifacts and lands enter tapped.")  # Root Maze
    assert d is not None and not any("controller" in k for k in d["who"])


def test_thalia_heretic_cathar_your_own_creature_enters_untapped(cards):
    s = build(cards, p1=("Thalia, Heretic Cathar", "Memnite"))
    on_field(s, "Thalia, Heretic Cathar")
    mine = to_hand(s, "Memnite")
    act(s, "p1", type="cast_spell", card_id=mine.id)
    settle(s)
    assert s.state.cards[mine.id].zone == "p1:battlefield" and not s.state.cards[mine.id].tapped
    roundtrip(s)


# -- "the exiled card" of the same ability is its own instruction's object, not a 607.2a link (wave 6D seam) ----------
@pytest.mark.parametrize("name", ["Voyager Staff", "Hide on the Ceiling"])
def test_own_exiled_card_stays_full(cards, name):
    from app.rules import coverage

    data = next(x for x in EXTRA if x["name"] == name)
    assert coverage.of_card_data(data).level == "FULL"


def test_voyager_staff_returns_its_own_exiled_creature_at_the_next_end_step(cards):
    from tests.test_rules_conditionals import until
    from tests.test_rules_effects import mana

    s = build(cards, p1=("Voyager Staff", "Memnite"))
    staff = on_field(s, "Voyager Staff")
    mem = on_field(s, "Memnite")
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=staff.id, ability=0, targets=[mem.id])
    settle(s)
    assert s.state.cards[mem.id].zone == "p1:exile" and s.state.cards[staff.id].zone == "p1:graveyard"
    until(s, lambda s: s.state.turn.number == 2, limit=80)
    new = next(c for c in s.state.cards.values() if c.name == "Memnite" and c.owner == "p1")
    assert new.zone == "p1:battlefield"
    roundtrip(s)


# -- "target creature that player controls" in a step trigger (wave 6B binding, promoted in wave 6) ----------------
def test_sentinel_of_the_eternal_watch_targets_only_the_active_opponents_creatures(cards):
    from tests.test_rules_conditionals import creature, until

    s = build(cards, p1=("Sentinel of the Eternal Watch",))
    on_field(s, "Sentinel of the Eternal Watch")
    mine = creature(s, "p1", "Bear")
    theirs = creature(s, "p2", "Wolf")
    until(s, lambda s: s.state.turn.number == 2 and s.state.rules.decision is not None
          and s.state.rules.decision.player == "p1", limit=80)
    d = s.state.rules.decision
    ids = {o.id for o in d.options}
    assert theirs.id in ids and mine.id not in ids
    pick(s, theirs.id)
    settle(s)
    assert s.state.cards[theirs.id].tapped
    roundtrip(s)


# -- oracle.word_prefix: a flavor word before a static or a spell instruction (wave 6E) ---------------------------
@pytest.mark.parametrize("line", [
    "Each opponent faces a villainous choice — They exile cards from the top of their library until they exile a "
    "nonland card, then you may cast that card without paying its mana cost.",  # Ensnared by the Mara (701.55a)
    "Prize — Create two Treasure tokens, then sacrifice Pick-a-Beeble and open an Attraction.",  # (702.159b)
])
def test_rules_bearing_prefixes_are_not_flavor_words(line):
    from app.rules import oracle

    assert oracle.word_prefix(line) is None


def test_flavor_words_before_statics_still_read():
    from app.rules import oracle

    assert oracle.word_prefix("Devastating Charge — Other creatures you control have trample.") == (
        "Devastating Charge", "Other creatures you control have trample.")
