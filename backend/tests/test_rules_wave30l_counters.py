"""Wave 30L: counter wordings (CR 122.1, 122.6, 608.2b, 608.2d, 609.3, 614.1c) — "Remove up to three counters from target creature."
(Glissa Sunslayer, Heartless Act, Mabel), "Remove a counter from target permanent." (Medicine Runner, Thrull Parasite), "Remove X counters
from target permanent, where X is …" (Thornmantle Striker), counts of a kind of counters read from an object or a group ("if it has fewer
than four +1/+1 counters on it", "with three or more level counters on it", "on him"), "… to the battlefield tapped with a +1/+1 counter
on her" (Gallia).

Real Oracle text (tests/fixtures/wave30l_cards.json, from data/cards.sqlite); every scenario checks that the recorded history replays and
that a save and a load keep the table."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import counters, token_of
from tests.wave9c_kit import build, card_named, check, mana, pt, put, reloaded, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave30l_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w30l", number=f"L{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def answer(s, *picks, limit=40):
    """Resolve everything; the decisions that come up are answered from ``picks`` in turn (an id, or a list of ids), else with their
    first options. Returns the option ids of every decision asked, in order."""
    picks, asked = list(picks), []
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            asked.append([o.id for o in d.options])
            pick = picks.pop(0) if picks else None
            ids = [pick] if isinstance(pick, str) else pick or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            assert not picks, f"unused answers {picks}"
            return asked
    raise AssertionError("never settled")


def add(s, c, n, kind="+1/+1"):
    act(s, "p1", type="counter", card_ids=[c.id], kind=kind, delta=n)


def heartless(s, target):
    """Alice casts Heartless Act's second mode ("Remove up to three counters from target creature.") on ``target``."""
    c = to_hand(s, "Heartless Act")
    mana(s, "p1", B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, modes=[1], targets=[target.id])


# (Homarid's state trigger, "Whenever there are four or more tide counters on this creature", 603.8, is read since:
# tests/test_rules_counter_state_thresholds50.py)


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_the_promoted_cards_are_full(name):
    c = next(c for c in EXTRA if c["name"] == name)
    assert coverage.of_card_data({**c, "faces": c.get("card_faces") or []}).level == "FULL", name


def test_the_unread_forms_stay_manual():
    from tests.test_rules_scripts import ch

    for text in (  # unsupported conditional and source-group removals remain manual
        "Remove all counters from up to one target permanent or opponent.",
        "Remove a counter from target permanent. If you do, draw a card.",
        "Remove any number of counters from among permanents on the battlefield.",
    ):
        assert coverage.of_characteristics(ch("T", "Sorcery", text)).level != "FULL", text


# -- "Remove up to three counters from target creature." (Heartless Act, Glissa Sunslayer, Render Inert, Mabel) --------------------------
def test_heartless_act_removes_up_to_three_counters_kind_by_kind(cards):
    """608.2d: its controller chooses how many of each kind; "up to three" is three in all, so the second kind is offered what is left."""
    s = build(cards, ["Heartless Act"], [])
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    add(s, bear, 4)
    add(s, bear, 2, "charge")
    heartless(s, bear)
    asked = answer(s, "2", "1")
    assert asked == [["0", "1", "2", "3"], ["0", "1"]]  # four +1/+1 counters but three at most; one more is the most after two
    assert (counters(s, bear), counters(s, bear, "charge")) == (2, 1)
    check(s)


def test_the_cap_ends_the_questions(cards):
    s = build(cards, ["Heartless Act"], [])
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    add(s, bear, 4)
    add(s, bear, 2, "charge")
    heartless(s, bear)
    asked = answer(s, "3")
    assert len(asked) == 1  # three removed: nothing left to ask about the charge counters
    assert (counters(s, bear), counters(s, bear, "charge")) == (1, 2)
    check(s)


def test_a_question_asked_survives_a_save_and_a_load(cards):
    """The bounds (what is left of "up to three") are part of the saved question: the loaded table offers the same numbers."""
    s = build(cards, ["Heartless Act"], [])
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    add(s, bear, 4)
    add(s, bear, 2, "charge")
    heartless(s, bear)
    loaded = reloaded(s)
    assert [o.id for o in loaded.state.rules.decision.options] == ["0", "1", "2", "3"]
    assert answer(loaded, "2", "1") == [["0", "1", "2", "3"], ["0", "1"]]
    assert (counters(loaded, bear), counters(loaded, bear, "charge")) == (2, 1)
    check(loaded)


def test_up_to_may_remove_none(cards):
    s = build(cards, ["Heartless Act"], [])
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    add(s, bear, 2)
    heartless(s, bear)
    answer(s, "0")
    assert counters(s, bear) == 2
    check(s)


def test_a_target_that_left_takes_nothing(cards):
    """608.2b: the target is gone as Heartless Act resolves (400.7: a new object if it came back), so the spell does nothing."""
    s = build(cards, ["Heartless Act"], [])
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    add(s, bear, 2)
    act(s, "p1", type="set_prefs", hold_priority=True)
    heartless(s, bear)
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p2", "zone": "graveyard"})  # in response
    assert answer(s) == []  # no question: nothing is left to remove from
    assert card_named(s, "Heartless Act").zone.endswith("graveyard")
    check(s)


# -- helpers for combat -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("extra", [None, "Solemnity"])
def test_medicine_runner_removes_one_counter_of_the_kind_you_choose(cards, extra):
    """"Remove a counter": one in all. Declining the first kind forces the second (nothing is asked when it is forced). Removing isn't
    putting (122.6): Solemnity doesn't stop it."""
    s = build(cards, ["Medicine Runner", *([extra] if extra else [])], [])
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    add(s, bear, 2)
    add(s, bear, 1, "charge")
    if extra:
        put(s, extra)
    mana(s, "p1", G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Medicine Runner").id)
    asked = answer(s, bear.id, "yes", "0")
    assert asked[-1] == ["0", "1"] and len(asked) == 3  # the target, may, then +1/+1 (0 or 1); the charge counter was forced
    assert (counters(s, bear), counters(s, bear, "charge")) == (2, 0)
    check(s)


def test_thornmantle_striker_removes_as_many_as_it_can_up_to_x(cards):
    """609.3: X is the Elves Alice controls (Striker and Medicine Runner: two); the target has three counters, so two go, the controller
    choosing the kinds; the last kind is forced when the first gives up fewer."""
    s = build(cards, ["Thornmantle Striker", "Medicine Runner"], [])
    put(s, "Medicine Runner")
    bear = token_of(s, "p2", "Bob Bear", "Creature — Bear", "2/2")
    add(s, bear, 1)
    add(s, bear, 2, "charge")
    mana(s, "p1", B=1, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Thornmantle Striker").id)
    answer(s, "0:0", bear.id, "0")  # the first mode; the +1/+1 counter: none (so both charge counters are forced)
    assert (counters(s, bear), counters(s, bear, "charge")) == (1, 0)
    check(s)


@pytest.mark.parametrize("extra, counters_on, power", [(None, 2, 4), ("Doubling Season", 4, 6)])
def test_lightning_serpent_enters_with_x_plus_one_plus_zero_counters(cards, extra, counters_on, power):
    """614.1c / 122.1a: a +1/+0 counter adds to power only (613.4c); entering with counters is putting them (122.6), so Doubling Season
    doubles them."""
    s = build(cards, ["Lightning Serpent", *([extra] if extra else [])], [])
    if extra:
        put(s, extra)
    mana(s, "p1", R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Serpent").id, x_value=2)
    answer(s)
    serpent = card_named(s, "Lightning Serpent")
    assert counters(s, serpent, "+1/+0") == counters_on and pt(s, "Lightning Serpent") == (power, 1)
    check(s)


def ready(s, *cs):
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0


def attack(s, *attackers):
    act(s, "p1", type="pass_priority")  # → declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in attackers])


def through_combat(s, *picks, limit=60):
    """Play on to the second main phase (nobody blocks); the other decisions that come up are answered from ``picks`` in turn."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            pick = picks.pop(0) if picks else None
            ids = [pick] if isinstance(pick, str) else pick or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def hand_size(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


# -- "if it has fewer than four +1/+1 counters on it … Then if it has exactly four …" (Ayara's Oathsworn) -----------------------------------
def oathsworn(cards, *extra, counters_on=3):
    s = build(cards, ["Ayara's Oathsworn", *extra], [])
    o = put(s, "Ayara's Oathsworn")
    ready(s, o)
    add(s, o, counters_on)
    return s, o


def test_oathsworn_grows_to_four_and_searches(cards):
    """603.4: checked as it triggers and again as it resolves; 3 → 4, and "Then if it has exactly four" is read after the counter."""
    s, o = oathsworn(cards)
    before = hand_size(s)
    attack(s, o)
    through_combat(s)
    assert counters(s, o) == 4 and hand_size(s) == before + 1
    check(s)


def test_oathsworn_with_four_does_not_trigger(cards):
    s, o = oathsworn(cards, counters_on=4)
    before = hand_size(s)
    attack(s, o)
    through_combat(s)
    assert counters(s, o) == 4 and hand_size(s) == before  # fewer than four is false: no ability at all (603.4)
    check(s)


def test_oathsworn_under_doubling_season_has_five_not_exactly_four(cards):
    """614.1: Doubling Season puts two (3 → 5), so the second sentence reads five counters: no search."""
    s, o = oathsworn(cards, "Doubling Season")
    put(s, "Doubling Season")
    before = hand_size(s)
    attack(s, o)
    through_combat(s)
    assert counters(s, o) == 5 and hand_size(s) == before
    check(s)


def test_oathsworn_under_solemnity_puts_nothing(cards):
    """614.17b: Solemnity stops the counter; the creature still has three, which isn't exactly four."""
    s, o = oathsworn(cards, "Solemnity")
    put(s, "Solemnity")
    before = hand_size(s)
    attack(s, o)
    through_combat(s)
    assert counters(s, o) == 3 and hand_size(s) == before
    check(s)


# -- "a creature with three or more level counters on it" / "exactly one tide counter" / "on him" / "among creatures you control" ----------------
def test_champions_drake_reads_level_counters_of_a_creature_you_control(cards):
    s = build(cards, ["Champion's Drake"], [])
    put(s, "Champion's Drake")
    mine = token_of(s, "p1", "Leveler", "Creature — Bear", "2/2")
    theirs = token_of(s, "p2", "Their Leveler", "Creature — Bear", "2/2")
    add(s, theirs, 3, "level")
    add(s, mine, 2, "level")
    assert pt(s, "Champion's Drake") == (1, 1)  # two is not three; an opponent's creature isn't "a creature you control"
    add(s, mine, 1, "level")
    assert pt(s, "Champion's Drake") == (4, 4)
    add(s, mine, -3, "level")
    assert pt(s, "Champion's Drake") == (1, 1)
    check(s)


def test_homarid_has_exactly_one_or_exactly_three_tide_counters(cards):
    s = build(cards, ["Homarid"], [])
    h = put(s, "Homarid")
    seen = {}
    for n in (1, 2, 3, 4):
        add(s, h, n - counters(s, h, "tide"), "tide")
        seen[n] = pt(s, "Homarid")
    assert seen == {1: (1, 1), 2: (2, 2), 3: (3, 3), 4: (2, 2)}  # (the "four or more" reset is a state trigger: still read by hand)
    check(s)


def test_zhao_with_a_conqueror_counter_on_him_makes_nonbasic_lands_mountains(cards):
    s = build(cards, ["Zhao, the Moon Slayer", "Command Tower"], [])
    put(s, "Zhao, the Moon Slayer")
    tower = put(s, "Command Tower")
    from app.rules.plan import Plan

    def subtypes():
        return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[tower.id]).subtypes

    assert "Mountain" not in subtypes()
    zhao = card_named(s, "Zhao, the Moon Slayer")
    add(s, zhao, 1, "conqueror")
    assert "Mountain" in subtypes()
    add(s, zhao, -1, "conqueror")
    assert "Mountain" not in subtypes()
    check(s)


def test_pipsqueak_attacks_alone_only_with_a_counter_on_him(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Pipsqueak, Rebel Strongarm"], [])
    p = put(s, "Pipsqueak, Rebel Strongarm")
    ready(s, p)
    act(s, "p1", type="pass_priority")  # → declare attackers
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": p.id, "target": "p2"}])
    add(s, p, 1)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": p.id, "target": "p2"}])
    check(s)


def name_of(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).name


@pytest.mark.parametrize("extra, before, becomes", [(None, 2, "Winged Temple of Orazca"), (None, 1, "Hadana's Climb"),
                                                    ("Solemnity", 2, "Hadana's Climb")])
def test_hadanas_climb_transforms_when_that_creature_has_three_counters(cards, extra, before, becomes):
    """"Then if that creature has three or more +1/+1 counters on it" is read after the counter (608.2c); under Solemnity (614.17b) none is
    put, so two stay two."""
    s = build(cards, ["Hadana's Climb // Winged Temple of Orazca", *([extra] if extra else [])], [])
    climb = put(s, "Hadana's Climb // Winged Temple of Orazca")
    if extra:
        put(s, extra)
    bear = token_of(s, "p1", "Mine", "Creature — Bear", "2/2")
    add(s, bear, before)
    through_combat(s, bear.id)  # (the trigger's target; combat on the way)
    assert name_of(s, climb) == becomes
    check(s)


@pytest.mark.parametrize("n, keyword, other", [(1, "first strike", "double strike"), (2, "double strike", "first strike")])
def test_urdnan_gives_double_strike_instead_with_two_counters(cards, n, keyword, other):
    """"If that creature has two or more +1/+1 counters on it, it gains double strike until end of turn instead": one counter first strike,
    two double strike (and not the first strike as well)."""
    from app.rules.plan import Plan

    s = build(cards, ["Urdnan, Dromoka Warrior"], [])
    put(s, "Urdnan, Dromoka Warrior")
    bear = token_of(s, "p1", "Bear", "Creature — Bear", "2/2")
    ready(s, bear)
    add(s, bear, n)
    attack(s, bear)
    d = s.state.rules.decision
    while d is not None or s.state.zones.get("stack"):  # the trigger resolves before blockers
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
    kws = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[bear.id]).keywords
    assert keyword in kws and other not in kws
    check(s)


@pytest.mark.parametrize("extra", [None, "Doubling Season"])
def test_gallia_returns_with_a_counter_on_her(cards, extra):
    """"Return this card from your graveyard to the battlefield tapped with a +1/+1 counter on her": it enters with it (122.6, 614.1c),
    so Doubling Season (614.1: twice that many) makes it two."""
    s = build(cards, ["Gallia, Tragic Host", "Grizzly Bears", *([extra] if extra else [])], [])
    gallia, bears = card_named(s, "Gallia, Tragic Host"), card_named(s, "Grizzly Bears")
    if extra:
        put(s, extra)
    for c in (gallia, bears):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    mana(s, "p1", B=1, C=4)
    act(s, "p1", type="activate_ability", card_id=gallia.id, ability=1)
    answer(s)
    g = s.state.cards[gallia.id]
    assert g.zone == "p1:battlefield" and g.tapped and g.counters.get("+1/+1", 0) == (2 if extra else 1)
    assert card_named(s, "Grizzly Bears").zone.endswith("exile")  # (the cost: exile another creature card)
    check(s)


@pytest.mark.parametrize("mine, theirs, attacks", [(1, 3, False), (2, 0, True)])
def test_backstreet_bruiser_attacks_with_two_counters_among_your_creatures(cards, mine, theirs, attacks):
    """A defender can attack "as though it didn't have defender" while there are two or more counters (of any kind) among the creatures
    its controller controls; an opponent's counters aren't among them."""
    from app.game.errors import ActionError

    s = build(cards, ["Backstreet Bruiser"], [])
    b = put(s, "Backstreet Bruiser")
    other = token_of(s, "p1", "Other", "Creature — Bear", "2/2")
    ready(s, b, other)
    add(s, other, 1)
    add(s, b, mine - 1, "charge")
    if theirs:
        add(s, token_of(s, "p2", "Foe", "Creature — Bear", "2/2"), theirs)
    act(s, "p1", type="pass_priority")  # → declare attackers
    if attacks:
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": b.id, "target": "p2"}])
    else:
        with pytest.raises(ActionError):
            act(s, "p1", type="declare_attackers", attackers=[{"card_id": b.id, "target": "p2"}])
    check(s)
