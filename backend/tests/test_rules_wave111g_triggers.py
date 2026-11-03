"""Wave 111G: Star Trek (trk, trc) triggers. Oracle text of 2026-10-30 (pre-release; the lead re-checks it at release). Every scenario checks
the replay and a save and a load.

* Star Trek creature types (Officer, Klingon, Romulan: the shared wave 111E block in creature_types.py, 205.3a): token makers (U.S.S.
  Cerritos, U.S.S. Enterprise-A, Worf, Defiant Commander, The Duras Sisters, MACO Strike Team, Sela, Tal Shiar Paradox).
* "Whenever you attack while creatures you control have total power 8 or greater" (La'An Noonien-Singh, Una Chin-Riley, Worf, Honor-Bound
  Warrior): 508.3d, the condition is part of the trigger event, judged as attackers are declared, over every creature you control.
* 201.5c rank + surname short names: "Lieutenant Sulu" on Lieutenant Hikaru Sulu ("he explores", 701.44).
* Whole abilities (app/rules/wave111g_triggers.py): Tuvok (up to two attackers reselected, 508.7), U.S.S. Defiant ("it and up to one target
  creature you control phase out", 702.26a).
* "Sacrifice those lands at the beginning of your next end step" (Will Riker: the lands it put onto the battlefield, 603.7).
* Võx: two "next spell" grants of undaunted (702.125a-c: {1} less per opponent, each instance applies).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import three, to_phase
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand

EXTRA = [
    real("La'An Noonien-Singh, Security", "{2}{R}{R}", 4, "Legendary Creature — Human Soldier", "Whenever you attack while creatures you control have total power 8 or greater, target creature can't block this turn.", ("4", "3"), "R"),
    real("Lieutenant Hikaru Sulu", "{2}{G}", 3, "Legendary Creature — Human Pilot", "Whenever Lieutenant Sulu becomes tapped, he explores. (Reveal the top card of your library. Put that card into your hand if it's a land. Otherwise, put a +1/+1 counter on this creature, then put the card back or put it into your graveyard.)\n{2}{U}: Target creature can't be blocked this turn.", ("3", "3"), "G"),
    real("MACO Strike Team", "{G}", 1, "Creature — Human Soldier", "Whenever a creature you control becomes the target of a spell or ability an opponent controls, create a tapped 1/1 red Officer creature token.", ("2", "1"), "G"),
    real("Sela, Tal Shiar Paradox", "{3}{B}", 4, "Legendary Creature — Romulan Human Rogue", "Whenever Sela attacks, exile up to one target card from a graveyard.\nWhenever one or more cards leave your graveyard, create a tapped 2/2 black Romulan creature token.", ("3", "3"), "B"),
    real("The Duras Sisters", "{B/R}{B/R}", 2, "Legendary Creature — Klingon Warrior", "When The Duras Sisters die, create a 2/1 red Klingon Warrior creature token with haste.", ("3", "2"), "BR"),
    real("U.S.S. Cerritos, Following Up", "{5}", 5, "Legendary Artifact — Spacecraft", "When U.S.S. Cerritos enters, create two 1/1 red Officer creature tokens.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 6+.)\n6+ | Flying", ("4", "4"), ""),
    real("U.S.S. Enterprise-A, Free Spirit", "{3}{W}{W}", 5, "Legendary Artifact — Spacecraft", "Ward {2}\nWhen U.S.S. Enterprise-A enters, create three 1/1 red Officer creature tokens.\nStation (Tap another creature you control: Put charge counters equal to its power on this Spacecraft. Station only as a sorcery. It's an artifact creature at 6+.)\n6+ | Flying, lifelink", ("5", "5"), "W"),
    real("Una Chin-Riley, Number One", "{4}{W}", 5, "Legendary Creature — Illyrian Officer", "Whenever you attack while creatures you control have total power 8 or greater, target attacking creature gets +2/+0 and gains first strike until end of turn.", ("4", "5"), "W"),
    real("Worf, Defiant Commander", "{2}{R}{W}{B}", 5, "Legendary Creature — Klingon Warrior Officer", "When Worf enters, create a 2/1 red Klingon Warrior creature token with haste.\nBattlefront — Whenever you attack, exile the top X cards of your library, where X is the number of opponents you attacked this turn. Until the end of your next turn, you may play those cards.", ("3", "4"), "BRW"),
    real("Worf, Honor-Bound Warrior", "{R/W}{R/W}", 2, "Legendary Creature — Klingon Warrior Officer", "Whenever you attack while creatures you control have total power 8 or greater, double Worf's power until end of turn.\nTap two untapped artifacts and/or creatures you control: Put a +1/+1 counter on Worf. Activate only as a sorcery.", ("1", "1"), "RW"),
    real("Tuvok, Chief Tactical Officer", "{2}{U}", 3, "Legendary Creature — Vulcan Officer", "Flash\nWhen Tuvok enters during the declare attackers step, choose up to two target attacking creatures. For each of them, you may reselect which player or permanent that creature is attacking. (A creature can't attack its controller.)", ("2", "3"), "U"),
    real("U.S.S. Defiant, Mirror Migrant", "{2}", 2, "Legendary Artifact — Spacecraft", "Flash\nWhen U.S.S. Defiant enters, it and up to one target creature you control phase out. (Treat them and anything attached to them as though they don't exist until your next turn.)\nStation\n8+ | Flying", ("5", "5"), ""),
    real("Võx, Child of the Collective", "{4}{U}", 5, "Legendary Artifact Creature — Borg", "When Võx enters and at the beginning of your first main phase, the next artifact creature spell and the next Spacecraft spell you cast this turn have undaunted. (They cost {1} less to cast for each opponent.)", ("3", "3"), "U"),
    real("Will Riker, First in the Field", "{3}{R}", 4, "Legendary Creature — Human Officer", "At the beginning of combat on your turn, reveal cards from the top of your library until you reveal two land cards. Put those land cards onto the battlefield and the rest on the bottom of your library in a random order. Sacrifice those lands at the beginning of your next end step.", ("4", "3"), "R"),
]
NAMES = [c["name"] for c in EXTRA]
EXTRA += [
    real("Hill Giant", "{3}{R}", 4, "Creature — Giant", "", ("3", "3"), "R"),
    real("Bojuka Bog", "", 0, "Land", "This land enters tapped.\nWhen this land enters, exile target player's graveyard.\n{T}: Add {B}.", None, ""),
    real("Shock", "{R}", 1, "Instant", "Shock deals 2 damage to any target.", None, "R"),
]


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
    """Resolve everything; decisions are answered from ``picks`` in turn (a list: several options), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
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


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def tokens(s, pid="p1"):
    return [c for c in s.state.cards.values() if c.is_token and c.zone == f"{pid}:battlefield"]


def token_is(s, tok, subtypes, colors, pt, keywords=()):
    got = ch(s, tok)
    return (set(got.subtypes) == set(subtypes) and list(got.colors) == list(colors) and got.pt == pt
            and set(keywords) <= set(got.keywords) and "Creature" in got.types)


def declare(s, turn, pairs):
    """Go to the declare attackers step of ``turn`` and attack with ``pairs`` (card, player id or permanent id)."""
    to_phase(s, "declare_attackers", turn)
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_attackers", d
    act(s, d.player, type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in pairs])


# -- Star Trek creature types: token makers ----------------------------------------------------------------------------------------
@pytest.mark.parametrize(("name", "cost", "n"), [("U.S.S. Cerritos, Following Up", {"C": 5}, 2),
                                                 ("U.S.S. Enterprise-A, Free Spirit", {"W": 2, "C": 3}, 3)])
def test_spacecraft_enter_with_red_officers(cards, name, cost, n):
    s = build(cards, [name])
    mana(s, **cost)
    ship = cast(s, name)
    answer(s)
    assert s.state.cards[ship.id].zone == "p1:battlefield"
    made = tokens(s)
    assert len(made) == n and all(token_is(s, t, ["Officer"], ["R"], (1, 1)) for t in made)
    assert all(not t.tapped for t in made)
    check(s)


def test_worf_defiant_commander_enters_with_a_hasty_klingon_warrior(cards):
    s = build(cards, ["Worf, Defiant Commander"])
    mana(s, R=1, W=1, B=1, C=2)
    cast(s, "Worf, Defiant Commander")
    answer(s)
    (tok,) = tokens(s)
    assert token_is(s, tok, ["Klingon", "Warrior"], ["R"], (2, 1), ["haste"])
    check(s)


@pytest.mark.parametrize("attacked", [["p2"], ["p2", "p3"]])
def test_worf_defiant_commander_exiles_one_card_per_opponent_attacked(cards, attacked):
    s = three(cards, ["Worf, Defiant Commander", "Grizzly Bears", "Llanowar Elves"])
    worf, bears = put(s, "Worf, Defiant Commander"), put(s, "Grizzly Bears")
    answer(s)
    to_phase(s, "declare_attackers", 4)
    top = list(s.state.zones["p1:library"])[: len(attacked) + 1]
    declare(s, 4, [(worf, attacked[0]), (bears, attacked[-1])])
    answer(s)
    exiled = [c for c in top if s.state.cards[c].zone == "p1:exile"]
    assert exiled == top[: len(attacked)]  # 508.3d: once per combat; X is the opponents attacked (two creatures at one: still one)
    to_phase(s, "main2", 4)
    act(s, "p1", type="play_land", card_id=exiled[0])  # "you may play those cards"
    assert s.state.cards[exiled[0]].zone == "p1:battlefield"
    check(s)


def test_the_duras_sisters_die_into_a_hasty_klingon_warrior(cards):
    s = build(cards, ["The Duras Sisters", "Murder"])
    sisters = put(s, "The Duras Sisters")
    answer(s)
    mana(s, B=2, C=1)
    cast(s, "Murder", [sisters.id])
    answer(s)
    assert s.state.cards[sisters.id].zone == "p1:graveyard"
    (tok,) = tokens(s)
    assert token_is(s, tok, ["Klingon", "Warrior"], ["R"], (2, 1), ["haste"])
    check(s)


@pytest.mark.parametrize(("caster", "target", "made"), [("p2", "bears", 1), ("p3", "maco", 1), ("p1", "bears", 0), ("p2", "p1", 0),
                                                        ("p2", "theirs", 0)])
def test_maco_strike_team_an_opponent_targets_a_creature_you_control(cards, caster, target, made):
    s = three(cards, ["MACO Strike Team", "Grizzly Bears", "Shock"], ["Shock", "Grizzly Bears"], ["Shock"])
    maco, bears, theirs = put(s, "MACO Strike Team"), put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    answer(s)
    turn = {"p1": 4, "p2": 2, "p3": 3}[caster]
    to_phase(s, "main1", turn)
    mana(s, caster, R=1)
    cast(s, "Shock", [{"bears": bears.id, "maco": maco.id, "theirs": theirs.id}.get(target, target)], pid=caster)
    answer(s)
    made_now = tokens(s)
    assert len(made_now) == made  # 603.2: the spell's controller is an opponent, the target a creature you control
    assert all(t.tapped and token_is(s, t, ["Officer"], ["R"], (1, 1)) for t in made_now)
    check(s)


@pytest.mark.parametrize("whose", ["p1", "p2"])
def test_sela_attacks_and_exiles_a_card_and_your_graveyard_makes_a_romulan(cards, whose):
    s = build(cards, ["Sela, Tal Shiar Paradox", "Grizzly Bears"], ["Grizzly Bears"])
    sela = put(s, "Sela, Tal Shiar Paradox")
    dead = card_named(s, "Grizzly Bears", whose)
    act(s, whose, type="move", card_ids=[dead.id], to={"player": whose, "zone": "graveyard"})
    declare(s, 3, [(sela, "p2")])
    answer(s, [dead.id])
    assert s.state.cards[dead.id].zone == f"{whose}:exile"
    made = tokens(s)
    assert len(made) == (1 if whose == "p1" else 0)  # only a card leaving your graveyard
    assert all(t.tapped and token_is(s, t, ["Romulan"], ["B"], (2, 2)) for t in made)
    check(s)


def test_sela_one_romulan_for_a_whole_graveyard_leaving_at_once(cards):
    s = build(cards, ["Sela, Tal Shiar Paradox", "Grizzly Bears", "Llanowar Elves", "Bojuka Bog"])
    put(s, "Sela, Tal Shiar Paradox")
    for name in ("Grizzly Bears", "Llanowar Elves"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "graveyard"})
    bog = to_hand(s, "Bojuka Bog")
    act(s, "p1", type="play_land", card_id=bog.id)
    answer(s, ["p1"])
    assert not s.state.zones.get("p1:graveyard")
    assert len(tokens(s)) == 1  # "one or more cards": one batch, one trigger
    check(s)


# -- "Whenever you attack while creatures you control have total power 8 or greater" ----------------------------------------------
def boost(s, c, n):
    act(s, "p1", type="set_counter", card_id=c.id, kind="+1/+1", value=n)


@pytest.mark.parametrize("total", [7, 8])
def test_la_an_needs_total_power_eight_among_all_your_creatures(cards, total):
    s = build(cards, ["La'An Noonien-Singh, Security", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    laan, _bears, elves = put(s, "La'An Noonien-Singh, Security"), put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    theirs = put(s, "Grizzly Bears", "p2")
    boost(s, elves, total - 7)  # 4 + 2 + 1 (+1): the creatures at home count too
    declare(s, 3, [(laan, "p2")])
    answer(s, [theirs.id])
    to_phase(s, "declare_blockers", 3)
    blocks = [{"blocker_id": theirs.id, "attacker_id": laan.id}]
    if total >= 8:
        with pytest.raises(ActionError):
            act(s, "p2", type="declare_blockers", blocks=blocks)
        act(s, "p2", type="declare_blockers", blocks=[])
    else:
        act(s, "p2", type="declare_blockers", blocks=blocks)  # no trigger: it can block
    answer(s)
    check(s)


def test_la_an_the_condition_is_judged_only_as_you_attack(cards):
    """Part of the trigger event (like "attacks while saddled"): once triggered, less power before it resolves changes nothing."""
    s = build(cards, ["La'An Noonien-Singh, Security", "Grizzly Bears", "Llanowar Elves", "Murder"], ["Grizzly Bears"])
    laan, bears, elves = put(s, "La'An Noonien-Singh, Security"), put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    theirs = put(s, "Grizzly Bears", "p2")
    boost(s, elves, 1)
    to_phase(s, "declare_attackers", 3)
    act(s, "p1", type="set_prefs", full_control=True)
    declare(s, 3, [(laan, "p2")])
    d = s.state.rules.decision
    assert d is not None and theirs.id in [o.id for o in d.options]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[theirs.id])  # the target
    assert s.state.zones.get("stack") and s.state.rules.priority == "p1"
    mana(s, B=2, C=1)
    cast(s, "Murder", [bears.id])  # in response: 6 power left
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    to_phase(s, "declare_blockers", 3)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": theirs.id, "attacker_id": laan.id}])
    check(s)


@pytest.mark.parametrize("total", [7, 8])
def test_una_pumps_an_attacker_and_gives_first_strike(cards, total):
    s = build(cards, ["Una Chin-Riley, Number One", "Hill Giant", "Llanowar Elves"])
    _una, giant, elves = put(s, "Una Chin-Riley, Number One"), put(s, "Hill Giant"), put(s, "Llanowar Elves")
    if total == 7:
        act(s, "p1", type="move", card_ids=[elves.id], to={"player": "p1", "zone": "graveyard"})
    declare(s, 3, [(giant, "p2")])
    answer(s, [giant.id])
    got = ch(s, giant)
    if total == 8:
        assert got.pt == (5, 3) and "first strike" in got.keywords
    else:
        assert got.pt == (3, 3) and "first strike" not in got.keywords
    answer(s)
    check(s)


@pytest.mark.parametrize("pumped", [False, True])
def test_worf_honor_bound_doubles_his_power(cards, pumped):
    s = build(cards, ["Worf, Honor-Bound Warrior", "Hill Giant", "Grizzly Bears", "Llanowar Elves"])
    worf, giant = put(s, "Worf, Honor-Bound Warrior"), put(s, "Hill Giant")
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    to_phase(s, "main1", 3)
    if pumped:  # "Tap two untapped artifacts and/or creatures you control": a counter, so 2 + 3 + 2 + 1 = 8
        act(s, "p1", type="activate_ability", card_id=worf.id,
            ability=next(a.index for a in ch(s, worf).abilities if a.text.startswith("Tap two untapped")),
            cost_choices=[{"component": 0, "cards": [bears.id, elves.id]}])
        answer(s)
        assert s.state.cards[worf.id].counters.get("+1/+1") == 1 and s.state.cards[bears.id].tapped
    declare(s, 3, [(worf, "p2"), (giant, "p2")])
    answer(s)
    assert ch(s, worf).pt == ((4, 2) if pumped else (1, 1))  # 701.10b: +X/+0, X its power as the ability resolves
    assert life(s, "p2") == 40 - 3 - (4 if pumped else 1)
    to_phase(s, "main1", 4)
    assert ch(s, worf).pt == ((2, 2) if pumped else (1, 1))  # until end of turn
    check(s)


# -- 201.5c: rank + surname ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("name", "text", "short"), [
    ("Lieutenant Hikaru Sulu", "Whenever Lieutenant Sulu becomes tapped, he explores.", "Lieutenant Sulu"),
    ('Dr. Leonard "Bones" McCoy', "When Dr. McCoy enters, draw a card.", "Dr. McCoy"),
    ("Captain James T. Kirk", "Whenever Captain Kirk attacks, draw a card.", "Captain Kirk"),
    ("Ensign Harry Kim, Operations", "Whenever Ensign Kim attacks, draw a card.", "Ensign Kim"),
    ("Captain Lannery Storm", "Whenever Captain Lannery Storm attacks, create a Treasure token.", None),  # only where the text says it
    ("Captain America's Shield", "Equipped creature gets +1/+1.", None),
])
def test_rank_and_surname_short_names(name, text, short):
    from app.rules.scripts import _short_name

    assert _short_name(name, text) == short


def test_lieutenant_sulu_explores_when_he_becomes_tapped(cards):
    s = build(cards, ["Lieutenant Hikaru Sulu", "Grizzly Bears"])
    sulu, bears = put(s, "Lieutenant Hikaru Sulu"), card_named(s, "Grizzly Bears")
    to_phase(s, "main1", 3)
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "library"}, position="top")
    declare(s, 3, [(sulu, "p2")])  # tapped by attacking: a nonland card, a counter, then the card to the graveyard
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind != "declare_blockers":
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["graveyard"] if "graveyard" in ids else ids[:1])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[sulu.id].counters.get("+1/+1") == 1 and s.state.cards[bears.id].zone == "p1:graveyard"
    to_phase(s, "main1", 5)
    land = s.state.zones["p1:library"][0]
    assert s.state.cards[land].name == "Forest"
    mana(s, U=1, C=2)
    act(s, "p1", type="activate_ability", card_id=sulu.id,
        ability=next(a.index for a in ch(s, sulu).abilities if a.text.startswith("{2}{U}")), targets=[sulu.id])
    answer(s)
    assert not s.state.cards[sulu.id].tapped and s.state.cards[land].zone == "p1:library"  # no {T} in that cost: no explore
    declare(s, 5, [(sulu, "p2")])
    answer(s)
    assert s.state.cards[land].zone == "p1:hand" and s.state.cards[sulu.id].counters.get("+1/+1") == 1  # a land: to the hand
    check(s)


# -- whole abilities (app/rules/wave111g_triggers.py) ------------------------------------------------------------------------------------
def to_decision(s, limit=30):
    """Pass priority until a decision comes up (or the stack is empty)."""
    for _ in range(limit):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            return s.state.rules.decision
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision")


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
    return to_decision(s)


def test_tuvok_reselects_up_to_two_attackers(cards):
    s = three(cards, ["Tuvok, Chief Tactical Officer", "Grizzly Bears", "Llanowar Elves"])
    bears, elves = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    to_phase(s, "declare_attackers", 4)
    act(s, "p1", type="set_prefs", full_control=True)
    declare(s, 4, [(bears, "p2"), (elves, "p2")])
    to_decision(s)
    mana(s, U=1, C=2)
    cast(s, "Tuvok, Chief Tactical Officer")  # flash, in the declare attackers step
    d = to_decision(s)
    assert d is not None and {bears.id, elves.id} <= {o.id for o in d.options}
    d = choose(s, [bears.id, elves.id])  # the two targets
    assert d is not None and {o.id for o in d.options} == {"decline", "p2", "p3"}  # 508.7c: never its controller
    d = choose(s, ["p3"])
    assert d is not None and {o.id for o in d.options} == {"decline", "p2", "p3"}
    choose(s, ["decline"])
    assert s.state.cards[bears.id].attacking.id == "p3" and s.state.cards[elves.id].attacking.id == "p2"
    to_phase(s, "main2", 4)
    assert [life(s, p) for p in ("p2", "p3")] == [39, 38]
    check(s)


def test_tuvok_moves_an_opponents_attacker_to_another_player(cards):
    s = three(cards, ["Tuvok, Chief Tactical Officer"], [], ["Grizzly Bears"])
    theirs = put(s, "Grizzly Bears", "p3")
    act(s, "p1", type="set_prefs", full_control=True)
    declare(s, 3, [(theirs, "p1")])  # Carol attacks Alice
    for _ in range(10):
        if s.state.rules.priority == "p1" and not s.state.zones.get("stack"):
            break
        act(s, s.state.rules.priority, type="pass_priority")
    mana(s, U=1, C=2)
    cast(s, "Tuvok, Chief Tactical Officer")
    to_decision(s)
    d = choose(s, [theirs.id])
    assert {o.id for o in d.options} == {"decline", "p1", "p2"}  # an opponent of Carol's
    choose(s, ["p2"])
    assert s.state.cards[theirs.id].attacking.id == "p2"
    to_phase(s, "main2", 3)
    assert [life(s, p) for p in ("p1", "p2")] == [40, 38]
    check(s)


def test_tuvok_entering_outside_the_declare_attackers_step_does_nothing(cards):
    s = build(cards, ["Tuvok, Chief Tactical Officer"])
    mana(s, U=1, C=2)
    cast(s, "Tuvok, Chief Tactical Officer")
    answer(s)
    assert s.state.rules.decision is None and not s.state.zones.get("stack")
    check(s)


@pytest.mark.parametrize("with_target", [False, True])
def test_uss_defiant_phases_out_with_up_to_one_creature(cards, with_target):
    s = build(cards, ["U.S.S. Defiant, Mirror Migrant", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    mana(s, C=2)
    ship = cast(s, "U.S.S. Defiant, Mirror Migrant")
    d = to_decision(s)
    assert d is not None and bears.id in {o.id for o in d.options}
    choose(s, [bears.id] if with_target else [o.id for o in d.options if o.card_id is None][:1] or [])
    answer(s)
    assert s.state.cards[ship.id].zone == "p1:phased"
    assert s.state.cards[bears.id].zone == ("p1:phased" if with_target else "p1:battlefield")
    to_phase(s, "main1", 3)  # 702.26a: they phase in as Alice untaps
    assert s.state.cards[ship.id].zone == s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def test_will_riker_puts_two_lands_onto_the_battlefield_until_your_end_step(cards):
    s = build(cards, ["Will Riker, First in the Field", "Grizzly Bears", "Llanowar Elves"])
    put(s, "Will Riker, First in the Field")
    to_phase(s, "main1", 3)
    bears, elves = card_named(s, "Grizzly Bears"), card_named(s, "Llanowar Elves")
    a, b = [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:2]
    for c in (a, elves, b, bears):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"}, position="top")
    assert s.state.zones["p1:library"][:4] == [bears.id, b.id, elves.id, a.id]
    to_phase(s, "main2", 3)
    assert s.state.cards[a.id].zone == s.state.cards[b.id].zone == "p1:battlefield"
    assert not s.state.cards[a.id].tapped and not s.state.cards[b.id].tapped
    assert set(s.state.zones["p1:library"][-2:]) == {bears.id, elves.id}  # the rest on the bottom
    to_phase(s, "main1", 4)  # Bob's turn: Alice's end step has passed
    assert s.state.cards[a.id].zone == s.state.cards[b.id].zone == "p1:graveyard"
    check(s)


# -- Võx: "the next artifact creature spell and the next Spacecraft spell you cast this turn have undaunted" (702.125) -------------------
def grants(s, turn):
    return sorted(g.filter or "" for g in s.state.rules.next_spell_grants if g.keyword == "undaunted" and g.turn == turn)


def test_vox_gives_the_next_artifact_creature_and_spacecraft_spells_undaunted(cards):
    s = three(cards, ["Võx, Child of the Collective", "Perilous Myr", "Grizzly Bears", "U.S.S. Cerritos, Following Up"])
    mana(s, U=1, C=4)
    cast(s, "Võx, Child of the Collective")
    answer(s)
    assert len(grants(s, 1)) == 2
    mana(s, G=1, C=1)
    cast(s, "Grizzly Bears")  # not an artifact creature: no reduction, nothing used up
    answer(s)
    assert len(grants(s, 1)) == 2
    myr = cast(s, "Perilous Myr")  # {2}, less {1} for each of two opponents
    answer(s)
    assert s.state.cards[myr.id].zone == "p1:battlefield"
    mana(s, C=2)
    ship = to_hand(s, "U.S.S. Cerritos, Following Up")
    with pytest.raises(ActionError):  # {5} less {2}: three
        act(s, "p1", type="cast_spell", card_id=ship.id, targets=[])
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=ship.id, targets=[])
    answer(s)
    assert s.state.cards[ship.id].zone == "p1:battlefield" and grants(s, 1) == []  # both used up
    to_phase(s, "main1", 4)  # "and at the beginning of your first main phase": again
    answer(s)
    assert len(grants(s, 4)) == 2
    check(s)


def test_vox_undaunted_counts_each_opponent(cards):
    s = build(cards, ["Võx, Child of the Collective", "Perilous Myr"])  # one opponent: {1} less
    mana(s, U=1, C=4)
    cast(s, "Võx, Child of the Collective")
    answer(s)
    myr = to_hand(s, "Perilous Myr")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=myr.id, targets=[])
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=myr.id, targets=[])
    answer(s)
    assert s.state.cards[myr.id].zone == "p1:battlefield" and len(grants(s, 1)) == 1  # the Spacecraft one is left
    check(s)
