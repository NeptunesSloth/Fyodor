"""-- Mystery Booster Commander (wave MBC-C) -- the lines of app/rules/mbc_c.py on real Oracle text (Scryfall / data/cards.sqlite) with the
rules engine on; each scenario ends with ``check`` (replay + a save and a load)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import coverage
from app.rules.plan import Plan
from app.rules.view import hints
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import stops, to_phase
from tests.wave9c_kit import check, mana

EXTRA = [
    real("Ashaya's Enduring Bond", '{1}{R}{G}', 3, 'Legendary Sorcery', "(You may cast a legendary sorcery only if you control a legendary creature or planeswalker.)\nDiscover X, where X is the amount of mana spent to cast this spell. (Exile cards from the top of your library until you exile a nonland card with that mana value or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)\nAshaya's Enduring Bond can be your commander.", None, 'GR'),  # noqa: E501
    real('Yume, Chronicler of Valor', '{1}{W}', 2, 'Legendary Creature — Human Druid', "The first spell you cast during each of your turns has assist. When you cast that spell, if another player spent mana to cast it, you and that player each draw a card. (As you cast a spell with assist, you may choose another player. They may pay some or all of the generic mana in the spell's cost.)", ("1", "2"), 'W'),  # noqa: E501
    real('The Weaver King', '{4}{U}{B}', 6, 'Legendary Creature — Horror Wizard', "Shadow (This creature can block or be blocked by only creatures with shadow.)\nWhenever The Weaver King deals combat damage to a player, they mill that many cards. Then for each opponent, put a creature card from that player's graveyard that was put there from their library this turn onto the battlefield under your control.", ("3", "6"), 'BU'),  # noqa: E501
    real("Dragon's Smile", '{5}{R}{R}', 7, 'Legendary Artifact — Vehicle', "Flying\nOnce during each of your turns, you may pay {0} rather than pay the mana cost for a spell you cast from exile.\nWhenever Dragon's Smile deals combat damage to a player, that player exiles that many cards from the top of their library. You may play those cards this turn.\nCrew 3", ("4", "5"), 'R'),  # noqa: E501
    real('Itazura, Lingering Wick', '{2}{U}{R}', 4, 'Legendary Creature — Spirit', "At the beginning of your upkeep, exile the top three cards of your library. Each opponent secretly chooses a number 0 or greater. Then those numbers are revealed. Choose an opponent with the highest number. Itazura deals that much damage to them, then they may cast a spell from among those cards without paying its mana cost. You put a card from among them that wasn't cast this way into your hand.", ("1", "5"), 'RU'),  # noqa: E501
    real('Miss Highwater', '{2}{B}{B}', 4, 'Legendary Creature — Demon Advisor', "Menace\nWhenever Miss Highwater deals combat damage to a player who doesn't have a contract counter, they may discard their hand. If they do, they draw seven cards and get a contract counter. For as long as they have a contract counter, when they lose the game, for each artifact and creature they controlled, create a token that's a copy of it.", ("5", "3"), 'B'),  # noqa: E501
    real('Chira, All In', '{3}{R}', 4, 'Legendary Creature — Human Rogue', 'Whenever you discard one or more cards at random, select one or more targets at random, choose one or more modes at random, flip one or more coins, or roll one or more dice, put a +1/+1 counter on Chira and create a tapped Treasure token.', ("3", "3"), 'R'),  # noqa: E501
    real('Kuroki, Thief of Talents', '{4}{B}', 5, 'Legendary Creature — Spirit', "Menace\nAt the beginning of your end step, target opponent may draw four cards. If they do, look at that player's hand and you may cast a spell from their hand without paying its mana cost. If they don't, put two +1/+1 counters on Kuroki.", ("4", "4"), 'B'),  # noqa: E501
    real('Glava, Five-Advents Mage', '{5}{G}{G}', 7, 'Legendary Creature — Human Wizard', "Whenever you cast a permanent spell with {X} in its mana cost or activate an ability with {X} in its activation cost that isn't a mana ability, you may have the value of X become 5. Do this only once each turn.", ("5", "5"), 'G'),  # noqa: E501
    real('Zagorka, Mother of Sanctum', '{1}{G}{U}{R}', 4, 'Legendary Creature — Human Peasant', 'Vigilance, trample\nAt the beginning of your end step, each player may create a tapped land token named Sanctum with "{T}: Add one mana of any color." Each opponent who does can\'t attack you during their next turn.', ("4", "2"), 'GRU'),  # noqa: E501
    real("Tresserhorn's Lord, Returned", '{2}{U}{B}{R}', 5, 'Legendary Creature — Zombie Noble', "Trample, indestructible\nWhen Tresserhorn's Lord enters, sacrifice him unless you sacrifice three creatures, pay 3 life, and have target opponent draw three cards.\nWhenever you sacrifice a creature, draw a card.", ("10", "4"), 'BRU'),  # noqa: E501
    real('The Madcap Jester', '{1}{U}{B}{R}', 4, 'Legendary Creature — Clown Wizard', "Whenever The Madcap Jester attacks, each opponent exiles the top card of their library.\nWhenever a spell or ability you control causes one or more cards to be exiled from an opponent's library, you may play those cards until the end of your next turn. Mana of any type can be spent to cast spells this way.", ("3", "2"), 'BRU'),  # noqa: E501
    real('Runeclaw Bear', '{1}{G}', 2, 'Creature — Bear', '', ("2", "2"), 'G'),
    real('Craw Wurm', '{4}{G}{G}', 6, 'Creature — Wurm', '', ("6", "4"), 'G'),
    real('Hill Giant', '{3}{R}', 4, 'Creature — Giant', '', ("3", "3"), 'R'),
    real('Divination', '{2}{U}', 3, 'Sorcery', 'Draw two cards.', None, 'U'),
    real('Kessig Wolf Run', '', 0, 'Land', '{T}: Add {C}.\n{X}{R}{G}, {T}: Target creature gets +X/+0 and gains trample until end of turn.', None, ''),
    real('Hangarback Walker', '{X}{X}', 0, 'Artifact Creature — Construct', 'This creature enters with X +1/+1 counters on it.\nWhen this creature dies, create a 1/1 colorless Thopter artifact creature token with flying for each +1/+1 counter on this creature.\n{1}, {T}: Put a +1/+1 counter on this creature.', ("0", "0"), ''),  # noqa: E501
]
REFUSED = ["Miss Highwater", "Chira, All In"]  # (not automated: see the module docstring of app/rules/mbc_c.py)
CARDS = [c["name"] for c in EXTRA[:12] if c["name"] not in REFUSED]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", CARDS)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("name", REFUSED)
def test_refused_stay_by_hand(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "PARTIAL"


# -- table helpers ---------------------------------------------------------------------------------------------------------------------------
def table(cards, mine=(), theirs=(), third=None):
    """Alice (first), Bob and (``third``: Carol's cards) Carol; rules on; Alice's first main phase."""
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (10, "Island")])
    setups = [PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)]
    if third is not None:
        setups.append(PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [*((1, n) for n in third), (10, "Forest")])))
    s = GameSession(enable(new_game(setups, shuffle=False, first_player=0)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def named(s, name, pid):
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def put(s, name, pid="p1"):
    c = named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def place(s, name, pid, zone, position=None):
    c = named(s, name, pid)
    payload = {"type": "move", "card_ids": [c.id], "to": {"player": pid, "zone": zone}}
    if position:
        payload["position"] = position
    act(s, pid, **payload)
    return s.state.cards[c.id]


def drive(s, pick=lambda d: None, limit=120, stop=lambda s: False):
    """Resolve everything; each decision is answered by ``pick(d)`` (a list of option ids) or else with the first options it needs."""
    for _ in range(limit):
        if stop(s):
            return
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            chosen = pick(d)
            if chosen is None:
                chosen = [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def by_label(*words):
    """Pick the options whose label (or card) contains each of ``words`` in turn (the first match each)."""
    def pick(d):
        out = []
        for w in words:
            o = next((o for o in d.options if w in (o.label or "") or w == o.card_id or w == o.id), None)
            if o is not None:
                out.append(o.id)
        return out[: d.max_choices] if len(out) >= d.min_choices and out else None
    return pick


def attack(s, *attackers, target="p2"):
    """From Alice's main phase: declare these attackers at ``target``; nobody blocks; on to the end of combat damage."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": target} for c in attackers])
            return
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never declared attackers")


def through_blocks(s, pick=lambda d: None):
    """Nobody blocks; triggers resolve with ``pick``; until the combat damage step's triggers have resolved (main 2)."""
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
            continue
        if s.state.turn.phase == "main2" and not s.state.zones.get("stack") and d is None:
            return
        drive(s, pick, stop=lambda s: s.state.turn.phase == "main2" and not s.state.zones.get("stack"))
        if s.state.rules.decision is None and not s.state.zones.get("stack") and s.state.turn.phase != "main2":
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("combat never ended")


def ch(s, c):
    return Plan(s.state, c.controller, s.cards, None).ch(s.state.cards[c.id])


# -- Ashaya's Enduring Bond --------------------------------------------------------------------------------------------------------------------
def test_ashaya_discovers_for_the_mana_spent(cards):
    s = table(cards, mine=["Ashaya's Enduring Bond", "Runeclaw Bear", "Craw Wurm"])
    put(s, "Krenko, Mob Boss")  # (a legendary creature: the legendary sorcery may be cast, 205.4d)
    bond = place(s, "Ashaya's Enduring Bond", "p1", "hand")
    place(s, "Runeclaw Bear", "p1", "library", "top")
    place(s, "Craw Wurm", "p1", "library", "top")  # (mana value 6: passed over by discover 3)
    mana(s, R=1, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=bond.id)
    drive(s, by_label("Runeclaw Bear", "Cast"))
    assert s.state.cards[named(s, "Runeclaw Bear", "p1").id].zone in ("p1:battlefield", "p1:hand")
    assert s.state.cards[named(s, "Craw Wurm", "p1").id].zone == "p1:library"
    check(s)


# -- Zagorka -----------------------------------------------------------------------------------------------------------------------------------
def test_zagorka_sanctums_and_the_attack_restriction(cards):
    s = table(cards, mine=["Zagorka, Mother of Sanctum"], theirs=["Hill Giant"], third=[])
    put(s, "Zagorka, Mother of Sanctum")
    giant = put(s, "Hill Giant", "p2")
    stops(s, "main1", "end")
    to_phase(s, "end", turn=1)
    drive(s, lambda d: [d.options[1 if d.player == "p3" else 0].id])  # (Alice and Bob say yes, Carol no)
    sanctums = {c.controller: c for c in s.state.cards.values() if c.name == "Sanctum"}
    assert set(sanctums) == {"p1", "p2"} and all(c.tapped for c in sanctums.values())
    land = ch(s, sanctums["p2"])
    assert land.is_land and not land.subtypes and land.name == "Sanctum" and any(a.kind == "mana" for a in land.abilities)
    to_phase(s, "main1", turn=2)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.kind == "declare_attackers" and d.player == "p2"
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": giant.id, "target": "p1"}])  # (Bob made a Sanctum: not Alice)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": giant.id, "target": "p3"}])
    assert s.state.cards[giant.id].is_attacking
    check(s)


# -- Tresserhorn's Lord --------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("pays", [True, False])
def test_tresserhorn_unless(cards, pays):
    s = table(cards, mine=["Tresserhorn's Lord, Returned", "Runeclaw Bear", "Hill Giant", "Craw Wurm"])
    for n in ("Runeclaw Bear", "Hill Giant", "Craw Wurm"):
        put(s, n)
    lord = place(s, "Tresserhorn's Lord, Returned", "p1", "hand")
    hands = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2")}
    mana(s, U=1, B=1, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=lord.id)
    drive(s, lambda d: None if d.kind != "choose_one" or len(d.options) != 2
          else [next(o.id for o in d.options if (o.label == "Don't pay") != pays)])
    lord = s.state.cards[lord.id]
    if pays:
        assert lord.zone == "p1:battlefield"
        assert s.state.players["p1"].life == 37
        assert len(s.state.zones["p2:hand"]) == hands["p2"] + 3
        assert len(s.state.zones["p1:hand"]) == hands["p1"] - 1 + 3  # (the Lord was cast; "whenever you sacrifice a creature": three draws)
        assert all(s.state.cards[named(s, n, "p1").id].zone == "p1:graveyard" for n in ("Runeclaw Bear", "Hill Giant", "Craw Wurm"))
    else:
        assert lord.zone == "p1:graveyard"  # (sacrificed: indestructible doesn't stop it, 701.21a)
        assert s.state.players["p1"].life == 40 and len(s.state.zones["p2:hand"]) == hands["p2"]
    check(s)


# -- Kuroki --------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("draws", [True, False])
def test_kuroki(cards, draws):
    s = table(cards, mine=["Kuroki, Thief of Talents"], theirs=["Divination"])
    kuroki = put(s, "Kuroki, Thief of Talents")
    div = place(s, "Divination", "p2", "hand")
    bob = len(s.state.zones["p2:hand"])
    alice = len(s.state.zones["p1:hand"])
    stops(s, "main1", "end")
    to_phase(s, "end", turn=1)

    def pick(d):
        if d.player == "p2" and d.kind == "choose_one":
            return [d.options[0 if draws else 1].id]
        if d.player == "p1" and any(o.card_id == div.id for o in d.options):
            return [next(o.id for o in d.options if o.card_id == div.id)]
        return None
    drive(s, pick)
    if draws:
        assert s.state.cards[div.id].zone == "p2:graveyard"  # (Alice cast it: it goes to its owner's graveyard)
        assert len(s.state.zones["p2:hand"]) == bob + 4 - 1
        assert len(s.state.zones["p1:hand"]) == alice + 2  # (Alice's Divination: she draws)
        assert s.state.cards[kuroki.id].counters.get("+1/+1", 0) == 0
    else:
        assert s.state.cards[kuroki.id].counters.get("+1/+1", 0) == 2
        assert len(s.state.zones["p2:hand"]) == bob
    check(s)


# -- The Weaver King -------------------------------------------------------------------------------------------------------------------------
def test_weaver_king_takes_a_milled_creature_from_each_opponent(cards):
    s = table(cards, mine=["The Weaver King"], theirs=["Craw Wurm", "Hill Giant"], third=["Runeclaw Bear", "Hill Giant"])
    king = put(s, "The Weaver King")
    to_phase(s, "main1", turn=4)
    place(s, "Hill Giant", "p2", "library", "top")
    place(s, "Craw Wurm", "p2", "library", "top")
    bear = place(s, "Runeclaw Bear", "p3", "library", "top")
    act(s, "p3", type="move", card_ids=[bear.id], to={"player": "p3", "zone": "graveyard"})  # (Carol's creature card put there from her library this turn)
    carol_giant = place(s, "Hill Giant", "p3", "graveyard")  # (from elsewhere: not eligible)
    attack(s, king)
    giant = named(s, "Hill Giant", "p2")
    through_blocks(s, lambda d: [o.id for o in d.options if o.card_id == giant.id] or None)
    assert s.state.cards[giant.id].zone == "p1:battlefield" and s.state.cards[giant.id].controller == "p1"
    assert s.state.cards[named(s, "Craw Wurm", "p2").id].zone == "p2:graveyard"
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    assert s.state.cards[carol_giant.id].zone == "p3:graveyard"
    check(s)


# -- The Madcap Jester -------------------------------------------------------------------------------------------------------------------------
def test_madcap_jester_plays_the_exiled_cards_with_any_mana(cards):
    s = table(cards, mine=["The Madcap Jester"], theirs=["Divination"])
    jester = put(s, "The Madcap Jester")
    to_phase(s, "main1", turn=3)
    div = place(s, "Divination", "p2", "library", "top")
    attack(s, jester)
    through_blocks(s)
    div = named(s, "Divination", "p2")
    assert s.state.cards[div.id].zone == "p2:exile"
    hand = len(s.state.zones["p1:hand"])
    mana(s, R=3)  # (mana of any type can be spent: no blue needed)
    act(s, "p1", type="cast_spell", card_id=div.id)
    drive(s)
    assert len(s.state.zones["p1:hand"]) == hand + 2
    check(s)


def test_madcap_jester_ignores_cards_exiled_from_your_own_library(cards):
    s = table(cards, mine=["The Madcap Jester", "Divination"])
    put(s, "The Madcap Jester")
    to_phase(s, "main1", turn=3)
    stack_before = len(s.state.rules.events)
    div = place(s, "Divination", "p1", "library", "top")
    act(s, "p1", type="move", card_ids=[div.id], to={"player": "p1", "zone": "exile"})  # (a table move: no spell or ability caused it)
    drive(s)
    assert not s.state.zones.get("stack") and stack_before >= 0
    mana(s, R=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=div.id)
    check(s)


# -- Dragon's Smile ------------------------------------------------------------------------------------------------------------------------------
def test_dragons_smile_exiles_and_casts_one_for_zero_on_your_turn(cards):
    s = table(cards, mine=["Dragon's Smile", "Craw Wurm"], theirs=["Divination", "Hill Giant"])
    smile = put(s, "Dragon's Smile")
    wurm = put(s, "Craw Wurm")
    to_phase(s, "main1", turn=3)
    place(s, "Hill Giant", "p2", "library", "top")
    place(s, "Divination", "p2", "library", "top")
    ab = next(a.index for a in ch(s, smile).abilities if a.kind == "keywords" and "crew" in a.keywords)
    act(s, "p1", type="activate_ability", card_id=smile.id, ability=ab, crew=[wurm.id])
    drive(s)
    attack(s, smile)
    through_blocks(s)
    div, giant = named(s, "Divination", "p2"), named(s, "Hill Giant", "p2")
    assert s.state.cards[div.id].zone == "p2:exile" and s.state.cards[giant.id].zone == "p2:exile"
    offers = hints(s.state, "p1", s.cards).get("alt_castable", {})
    key = next(o["id"] for o in offers[div.id] if o["id"].startswith(smile.id))
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=div.id, alt_cost=key)  # {0}: no mana in the pool
    drive(s)
    assert len(s.state.zones["p1:hand"]) == hand + 2
    assert not any(o["id"].startswith(smile.id) for o in hints(s.state, "p1", s.cards).get("alt_castable", {}).get(giant.id, []))  # (once each turn)
    check(s)


# -- Itazura ------------------------------------------------------------------------------------------------------------------------------------
def test_itazura_secret_numbers_damage_cast_and_keep(cards):
    import json

    s = table(cards, mine=["Itazura, Lingering Wick", "Divination", "Runeclaw Bear", "Hill Giant"], third=[])
    itazura = put(s, "Itazura, Lingering Wick")
    stops(s, "upkeep", "main1")
    to_phase(s, "main1", turn=3)
    for n in ("Hill Giant", "Runeclaw Bear", "Divination"):
        place(s, n, "p1", "library", "top")  # (Divination on top)
    to_phase(s, "upkeep", turn=4)  # (Alice's next turn: 4 with three players)
    drive(s, stop=lambda s: s.state.rules.decision is not None and s.state.rules.decision.options[0].id == "__number__")
    d = s.state.rules.decision
    assert d.player == "p2" and "chose" not in json.dumps(s.view("p3")["log"])
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[], name="3")
    d = s.state.rules.decision
    assert d.player == "p3" and s.view("p1")["rules"]["decision"]["kind"] == "waiting"
    assert "chose" not in json.dumps(s.view("p3")["log"])  # (nothing revealed before every opponent has chosen)
    act(s, "p3", type="choose", decision_id=d.id, option_ids=[], name="3")  # (a tie: Alice chooses Carol)
    div, bear, giant = (named(s, n, "p1") for n in ("Divination", "Runeclaw Bear", "Hill Giant"))
    carol_hand = len(s.state.zones["p3:hand"])

    def pick(d):
        if d.player == "p1" and d.kind == "choose_one" and any(o.id == "p3" for o in d.options):
            return ["p3"]
        if d.player == "p3" and any(o.card_id == div.id for o in d.options):
            return [next(o.id for o in d.options if o.card_id == div.id)]  # (Carol casts Alice's Divination)
        if d.player == "p1" and any(o.card_id == giant.id for o in d.options):
            return [next(o.id for o in d.options if o.card_id == giant.id)]
        return None
    drive(s, pick)
    assert s.state.players["p3"].life == 37 and s.state.players["p2"].life == 40
    assert len(s.state.zones["p3:hand"]) == carol_hand + 2  # (Carol cast it: she draws)
    assert s.state.cards[div.id].zone == "p1:graveyard"
    assert s.state.cards[giant.id].zone == "p1:hand" and s.state.cards[bear.id].zone == "p1:exile"
    assert s.state.cards[itazura.id].zone == "p1:battlefield"
    check(s)


# -- Yume ---------------------------------------------------------------------------------------------------------------------------------------
def test_yume_first_spell_has_assist_and_both_draw(cards):
    s = table(cards, mine=["Yume, Chronicler of Valor", "Divination", "Hill Giant"])
    put(s, "Yume, Chronicler of Valor")
    div = place(s, "Divination", "p1", "hand")
    giant = place(s, "Hill Giant", "p1", "hand")
    mana(s, "p2", C=2)
    mana(s, U=1)
    hands = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2")}
    act(s, "p1", type="cast_spell", card_id=div.id)
    asked = []

    def pick(d):
        asked.append((d.player, d.prompt))
        if "assist" in d.prompt and d.player == "p1":
            return ["p2"]
        if "assist" in d.prompt and d.player == "p2":
            return ["2"]
        return None
    drive(s, pick)
    assert [p for p, _ in asked][:2] == ["p1", "p2"]
    assert len(s.state.zones["p2:hand"]) == hands["p2"] + 1
    assert len(s.state.zones["p1:hand"]) == hands["p1"] - 1 + 2 + 1  # (Divination cast; it draws two; Yume's draw)
    asked.clear()
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=giant.id)  # (the second spell this turn: no assist)
    drive(s, pick)
    assert not any("assist" in p for _, p in asked) and s.state.cards[giant.id].zone == "p1:battlefield"
    check(s)


def test_yume_no_draw_when_nobody_helped(cards):
    s = table(cards, mine=["Yume, Chronicler of Valor", "Divination"])
    put(s, "Yume, Chronicler of Valor")
    div = place(s, "Divination", "p1", "hand")
    mana(s, U=1, C=2)
    hands = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2")}
    act(s, "p1", type="cast_spell", card_id=div.id)
    drive(s, lambda d: [""] if "assist" in d.prompt else None)  # (no one)
    assert len(s.state.zones["p2:hand"]) == hands["p2"]
    assert len(s.state.zones["p1:hand"]) == hands["p1"] - 1 + 2
    assert not s.state.zones.get("stack")
    check(s)


# -- Glava ----------------------------------------------------------------------------------------------------------------------------------------
def test_glava_x_becomes_five_once_each_turn(cards):
    s = table(cards, mine=["Glava, Five-Advents Mage", "Hangarback Walker", "Kessig Wolf Run"])
    glava = put(s, "Glava, Five-Advents Mage")
    run = put(s, "Kessig Wolf Run")
    walker = place(s, "Hangarback Walker", "p1", "hand")
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=walker.id, x_value=1)
    drive(s)  # (yes: the first option)
    assert s.state.cards[walker.id].counters.get("+1/+1", 0) == 5
    mana(s, R=1, G=1, C=1)
    ab = next(a.index for a in ch(s, run).abilities if a.kind != "mana" and "{X}" in (a.cost or a.text))
    act(s, "p1", type="activate_ability", card_id=run.id, ability=ab, x_value=1, targets=[glava.id])
    drive(s)  # (Glava's trigger was done this turn already: X stays 1)
    assert ch(s, glava).pt[0] == 6
    to_phase(s, "main1", turn=3)
    mana(s, R=1, G=1, C=1)
    act(s, "p1", type="activate_ability", card_id=run.id, ability=ab, x_value=1, targets=[walker.id])
    drive(s)
    assert ch(s, s.state.cards[walker.id]).pt[0] == 5 + 5  # (5 counters, +5/+0: X became 5 for the ability)
    check(s)
