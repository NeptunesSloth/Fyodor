"""-- planechase events (wave E2) -- a plane's ordinary event triggers, the planar die's roll triggers and the remaining chaos lines
(app/rules/planar_events.py, app/rules/planar_chaos.py), on real Oracle text with the rules engine on, then ``check`` (replay + save/load
round trip)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings, PlanarCard
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_planechase import script
from tests.test_rules_conditionals import through_combat, to_turn, until
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import card_named, check, life, mana, pt, put, to_hand

# Oracle text exactly as in the card database (data/cards.sqlite)
PLANES = {
    'Krosa': ('Plane — Dominaria', 'All creatures get +2/+2.\nWhenever chaos ensues, you may add {W}{U}{B}{R}{G}.'),
    'Chaotic Aether': ('Phenomenon', 'When you encounter Chaotic Aether, each blank roll of the planar die is a {CHAOS} roll until a player planeswalks away from a plane. (Then planeswalk away from this phenomenon.)'),
    'Goldmeadow': ('Plane — Lorwyn', "Whenever a land enters, that land's controller creates three 0/1 white Goat creature tokens.\nWhenever chaos ensues, create a 0/1 white Goat creature token."),
    'The Dark Barony': ('Plane — Ulgrotha', "Whenever a nonblack card is put into a player's graveyard from anywhere, that player loses 1 life.\nWhenever chaos ensues, each opponent discards a card."),
    'Mirrored Depths': ('Plane — Karsus', "Whenever a player casts a spell, that player flips a coin. If the player loses the flip, counter that spell.\nWhenever chaos ensues, target player reveals the top card of their library. If it's a nonland card, you may cast it without paying its mana cost."),
    'Ten Wizards Mountain': ('Plane — Shenmeng', 'Whenever you roll the planar die, put a +1/+1 counter on up to one target creature.\nWhenever chaos ensues, creatures you control gain flying until end of turn.'),
    'The Drum, Mining Facility': ('Plane — Earth', 'Whenever you roll the planar die, creatures you control get +1/+1 and gain haste until end of turn.\nWhenever chaos ensues, end the turn. (Exile all spells and abilities from the stack. The player whose turn it is discards down to their maximum hand size. Damage wears off, and "this turn" and "until end of turn" effects end.)'),
    'Pompeii': ('Plane — Earth', 'When you planeswalk to Pompeii and at the beginning of your upkeep, put an eruption counter on it.\nWhenever you roll a blank on the planar die, scry 2. Then put an eruption counter on Pompeii.\nWhen chaos ensues, Pompeii deals damage to each creature and each player equal to the number of eruption counters on Pompeii. Each player sacrifices a land of their choice. Then planeswalk.'),
    "Valor's Reach": ('Plane — Kylem', "Whenever your team attacks with exactly two creatures, those creatures gain double strike until end of turn.\nWhenever chaos ensues, untap up to two target creatures your team controls. If it's a main phase, there is an additional combat phase after this phase, followed by an additional main phase."),
    'Izzet Steam Maze': ('Plane — Ravnica', 'Whenever a player casts an instant or sorcery spell, that player copies it. The player may choose new targets for the copy.\nWhenever chaos ensues, instant and sorcery spells you cast this turn cost {3} less to cast.'),
    'Mondassian Colony Ship': ('Plane — Spacecraft', 'Whenever a creature attacks, it gets +1/+1 until end of turn for each other creature its controller controls that shares a creature type with it.\nWhenever chaos ensues, turn target creature face down. It becomes a 2/2 Cyberman artifact creature.'),
    'Stensia': ('Plane — Innistrad', 'Whenever a creature deals damage to one or more players for the first time each turn, put a +1/+1 counter on it.\nWhenever chaos ensues, each creature you control gains "{T}: This creature deals 1 damage to target player or planeswalker" until end of turn.'),
    'Gardens of Tranquil Repose': ('Plane — Necros', 'Suspended Animation — Whenever a creature dies, exile it. Its controller scries 1.\nWhenever chaos ensues, create X 3/3 black Dalek artifact creature tokens with menace, where X is one plus the number of cards exiled with Gardens of Tranquil Repose.'),
    'Ketria': ('Plane — Ikoria', 'When you planeswalk to Ketria and at the beginning of your upkeep, put your choice of a vigilance, menace, or trample counter on target creature you control.\nWhenever chaos ensues, exile cards from the top of your library until you exile a nonland permanent card. Put that card onto the battlefield or into your hand.'),
    'Bad Wolf Bay': ('Plane — Earth', "At the beginning of combat on your turn, exile up to one target creature. Return it to the battlefield under its owner's control at the beginning of the next end step.\nWhen chaos ensues, cards can't enter from exile this turn. Then planeswalk."),
    'The Dining Car': ('Plane — Spacecraft', 'When you planeswalk to The Dining Car, each player creates a Food token.\nSixty-Six Seconds — At the beginning of your upkeep, sacrifice a creature with the least toughness among creatures you control. Then investigate.\nWhenever chaos ensues, activated abilities of artifact tokens you control cost {2} less to activate this turn.'),
    'Nyx': ('Plane — Theros', 'Nontoken creatures are enchantments in addition to their other types.\nConstellation — Whenever an enchantment you control enters, you gain 1 life.\nWhenever chaos ensues, choose a color. Add an amount of mana of that color equal to your devotion to that color.'),
    'Hotel of Fears': ('Plane — Spacecraft', 'At the beginning of your upkeep, exile the top card of your library. You lose life equal to its mana value. You may play that card this turn.\nPraise Him — Whenever chaos ensues, choose a color. Put X +1/+1 counters on target creature you control, where X is your devotion to that color. Then sacrifice another creature. (Your devotion to a color is the number of mana symbols of that color in the mana costs of permanents you control.)'),
    'City of the Daleks': ('Plane — Skaro', 'Whenever you attack, target opponent loses X life, where X is the number of artifacts you control.\nWhenever chaos ensues, for each opponent, you create a 3/3 black Dalek artifact creature token with menace that attacks that opponent this turn if able. Those tokens gain haste. Sacrifice them at the beginning of the next end step.'),
    "Li'l Giri Saves the Day": ('Plane — Secret Lair', "Legendary Food tokens you control have hexproof and indestructible.\nWhen you planeswalk to this plane, create Li'l Giri, a legendary 1/1 colorless Food Warrior artifact creature token.\nWhenever chaos ensues, put X +1/+1 counters on target legendary artifact creature you control, where X is the number of times you've rolled the planar die this turn."),
    'Glimmervoid Basin': ('Plane — Mirrodin', "Whenever a player casts an instant or sorcery spell with a single target, that player copies that spell for each other spell, permanent, card not on the battlefield, and/or player the spell could target. Each copy targets a different one of them.\nWhenever chaos ensues, choose target creature. Each player except that creature's controller creates a token that's a copy of that creature."),
    'The Food Court': ('Plane — Eldraine', 'Artifacts are Foods in addition to their other types (They have "{2}, {T}, Sacrifice this artifact: You gain 3 life.")\nSacrifice three Foods: Add {W}{U}{B}{R}{G}. Activate only once each turn and only during your turn.\nChaos: You become the Monarch. If you are already the Monarch, draw a card.'),
    'Jund': ('Plane — Alara', "Whenever a player casts a creature spell that's black, red, or green, it gains devour 5. (As that creature enters, you may sacrifice any number of creatures. It enters with five times that many +1/+1 counters on it.)\nWhenever chaos ensues, create two 1/1 red Goblin creature tokens."),
    'Grand Ossuary': ('Plane — Ravnica', 'Whenever a creature dies, its controller distributes a number of +1/+1 counters equal to its power among any number of target creatures they control.\nWhenever chaos ensues, each player exiles all creatures they control and creates X 1/1 green Saproling creature tokens, where X is the total power of the creatures they exiled this way. Then planeswalk.'),
    'Stroopwafel Cafe': ('Plane — Amsterdam', 'Players may look at the top card of their library at any time and may play cards from the top of their library.\nThe top card of each player\'s library is a Food artifact. (It\'s an artifact with "{2}, {T}, Sacrifice this artifact: You gain 3 life." Activate this ability from the top of the library.)\nChaos: You may sacrifice a Food. If you do, draw a card, gain three life and each opponent loses 3 life.'),
}
EXTRA = [card(n, set_code="opca", number=f"PE-{i}", layout="planar", type_line=t, oracle_text=o) for i, (n, (t, o)) in enumerate(PLANES.items())]
EXTRA += [real("Runeclaw Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
          real("Craw Wurm", "{4}{G}{G}", 6, "Creature — Wurm", "", ("6", "4"), "G"),
          real("Opt", "{U}", 1, "Instant", "Scry 1.\nDraw a card.", None, "U"),
          real("Serra Angel", "{3}{W}{W}", 5, "Creature — Angel", "Flying, vigilance", ("4", "4"), "W"),
          real("Murder", "{1}{B}{B}", 3, "Instant", "Destroy target creature.", None, "B"),
          real("Duress", "{B}", 1, "Sorcery", "Target opponent reveals their hand. You choose a noncreature, nonland card from it. That player "
               "discards that card.", None, "B")]
FULL = ["Jund", "Li'l Giri Saves the Day", "City of the Daleks", "Goldmeadow", "The Dark Barony", "Mirrored Depths", "Ten Wizards Mountain", "The Drum, Mining Facility", "Pompeii", "Valor's Reach",
        "Izzet Steam Maze", "Mondassian Colony Ship", "Stensia", "Gardens of Tranquil Repose",
        "Ketria", "Bad Wolf Bay", "The Dining Car", "Nyx", "Hotel of Fears"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


class _InOrder:
    def shuffle(self, items: list) -> None:
        pass

    def randint(self, lo: int, hi: int) -> int:
        return lo


def table(cards, planes: list[str], players: int = 2) -> GameSession:
    alice = deck(cards, "Krenko, Mob Boss", [(3, "Runeclaw Bear"), (1, "Opt"), (1, "Craw Wurm"), (1, "Duress"), (1, "Serra Angel"),
                                             (1, "Murder"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Runeclaw Bear"), (1, "Craw Wurm"), (1, "Opt"), (10, "Island")])
    carol = deck(cards, "Krenko, Mob Boss", [(1, "Runeclaw Bear"), (10, "Forest")])
    pool = [PlanarCard(printing_id=cards.resolve(n)["id"], name=n, phenomenon=PLANES[n][0] == "Phenomenon") for n in planes]
    setups = [PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)][:players]
    state = new_game(setups, shuffle=False, first_player=0, settings=GameSettings(planechase=True, planar_deck_size=len(pool)),
                     planar_pool=lambda: pool, rng=_InOrder())
    enable(state)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def resolve(s, picks=()):
    """Everything resolves; a choice takes the ``picks`` (ids, card ids or labels, in this order of preference) when offered, else the
    fewest it may."""
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            chosen = [o.id for p in picks for o in d.options if p in (o.id, o.card_id, o.label)][: d.max_choices]
            if len(chosen) < d.min_choices:
                chosen = [o.id for o in d.options][: d.min_choices]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def roll(s, monkeypatch, value, picks=(), then=()):
    """Alice rolls the planar die for the server's d6 ``value`` (1 planeswalker, 2 chaos, 3-6 blank), paying its cost (901.9); ``then``:
    the server's next random numbers (coins)."""
    from app.game.handlers.planechase import roll_cost

    if cost := roll_cost(s.state):
        mana(s, C=cost)
    script(monkeypatch, [value, *then])
    act(s, "p1", type="roll_planar_die")
    resolve(s, picks)


def face(s):
    return s.state.cards[s.state.planechase.face_id]


def on_battlefield(s, name, pid=None):
    return [c for c in s.state.cards.values() if c.name == name and c.zone.endswith(":battlefield") and (pid is None or c.controller == pid)]


@pytest.mark.parametrize("name", FULL)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- the planar die's roll triggers ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("value", [2, 3, 1])
def test_ten_wizards_mountain_every_roll_puts_a_counter_on_up_to_one_target_creature(cards, monkeypatch, value):
    s = table(cards, ["Ten Wizards Mountain", "Krosa"])
    bear = put(s, "Runeclaw Bear")
    roll(s, monkeypatch, value, picks=[bear.id])
    assert s.state.cards[bear.id].counters.get("+1/+1") == 1
    check(s)


def test_the_drum_pumps_and_hastes_your_creatures_on_a_blank_roll(cards, monkeypatch):
    s = table(cards, ["The Drum, Mining Facility", "Krosa"])
    put(s, "Runeclaw Bear")
    put(s, "Runeclaw Bear", "p2")
    roll(s, monkeypatch, 4)
    assert pt(s, "Runeclaw Bear") == (3, 3) and pt(s, "Runeclaw Bear", "p2") == (2, 2)
    check(s)


def test_pompeii_a_blank_roll_scries_and_adds_an_eruption_counter_but_not_a_chaos_roll(cards, monkeypatch):
    s = table(cards, ["Pompeii", "Krosa"])
    resolve(s)
    assert face(s).name == "Pompeii"
    before = face(s).counters.get("eruption", 0)
    roll(s, monkeypatch, 5)
    assert face(s).counters.get("eruption", 0) == before + 1
    check(s)


def test_pompeii_under_chaotic_aether_a_blank_roll_is_a_chaos_roll_not_a_blank(cards, monkeypatch):
    s = table(cards, ["Krosa", "Chaotic Aether", "Pompeii"])
    roll(s, monkeypatch, 1)  # → Chaotic Aether, then (704.6f) Pompeii
    assert face(s).name == "Pompeii" and s.state.rules.planar_walk_pcw == [{"kind": "blank_chaos"}]
    n = face(s).counters.get("eruption", 0)
    roll(s, monkeypatch, 3)  # a chaos roll (Pompeii's chaos line: damage, a land each, then planeswalk): no blank trigger
    rolls = [e.counter for e in s.state.rules.events if e.kind == "planar" and e.counter in ("roll", "roll_blank", "chaos")]
    assert rolls[-2:] == ["roll", "chaos"] and n >= 1 and face(s).name == "Krosa"
    check(s)


# -- ordinary event triggers -----------------------------------------------------------------------------------------------------
def test_goldmeadow_a_land_entering_gives_its_controller_three_goats(cards, monkeypatch):
    s = table(cards, ["Goldmeadow", "Krosa"])
    forest = to_hand(s, "Forest")
    act(s, "p1", type="play_land", card_id=forest.id)
    resolve(s)
    assert len(on_battlefield(s, "Goat", "p1")) == 3 and not on_battlefield(s, "Goat", "p2")
    check(s)


def test_the_dark_barony_a_nonblack_card_to_a_graveyard_costs_its_owner_one_life(cards, monkeypatch):
    s = table(cards, ["The Dark Barony", "Krosa"])
    mana(s, U=1, B=1)
    opt = to_hand(s, "Opt")
    act(s, "p1", type="cast_spell", card_id=opt.id, targets=[])
    resolve(s)
    assert life(s, "p1") == 39
    duress = to_hand(s, "Duress")
    act(s, "p1", type="cast_spell", card_id=duress.id, targets=["p2"])
    resolve(s)
    assert card_named(s, "Duress").zone == "p1:graveyard" and life(s, "p1") == 39  # (black: no trigger)
    check(s)


@pytest.mark.parametrize("coin,countered", [(1, False), (0, True)])
def test_mirrored_depths_the_caster_flips_and_a_lost_flip_counters_the_spell(cards, monkeypatch, coin, countered):
    s = table(cards, ["Mirrored Depths", "Krosa"])
    mana(s, U=1)
    hand = len(s.state.zones["p1:hand"])
    script(monkeypatch, [coin])
    opt = to_hand(s, "Opt")
    act(s, "p1", type="cast_spell", card_id=opt.id, targets=[])
    resolve(s)
    assert s.state.cards[opt.id].zone == "p1:graveyard"
    assert len(s.state.zones["p1:hand"]) == hand + (0 if countered else 1)
    check(s)


def place(s, name, pid="p1"):
    """One more card named ``name`` of ``pid``'s (not on the battlefield yet) onto the battlefield."""
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith(":battlefield"))
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def stats(s, c):
    from app.rules import sba
    from app.rules.plan import Plan

    card = s.state.cards[c.id]
    ch = Plan(s.state, "p1", s.cards, None).ch(card)
    return sba.power(card, ch), sba.toughness(card, ch)


def attack(s, *creatures, target="p2"):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": target} for c in creatures])


def chars(s, c):
    from app.rules.plan import Plan

    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


@pytest.mark.parametrize("n", [2, 3])
def test_valors_reach_exactly_two_attackers_gain_double_strike(cards, monkeypatch, n):
    s = table(cards, ["Valor's Reach", "Krosa"])
    bears = [place(s, "Runeclaw Bear") for _ in range(n)]
    to_turn(s, 3)
    attack(s, *bears)
    resolve(s)
    assert [("double strike" in chars(s, b).keywords) for b in bears] == [n == 2] * n
    through_combat(s)
    assert life(s, "p2") == 40 - (8 if n == 2 else 6)
    check(s)


def test_valors_reach_chaos_untaps_up_to_two_and_adds_a_combat_after_a_main_phase(cards, monkeypatch):
    s = table(cards, ["Valor's Reach", "Krosa"])
    bear = place(s, "Runeclaw Bear")
    to_turn(s, 3)
    attack(s, bear)
    through_combat(s)
    assert s.state.cards[bear.id].tapped and s.state.turn.phase == "main2"
    roll(s, monkeypatch, 2, picks=[bear.id])
    assert not s.state.cards[bear.id].tapped
    attack(s, bear)  # (the additional combat phase)
    through_combat(s)
    assert life(s, "p2") == 36
    check(s)


def test_izzet_steam_maze_the_caster_copies_the_spell(cards, monkeypatch):
    s = table(cards, ["Izzet Steam Maze", "Krosa"])
    mana(s, U=1)
    hand, theirs = len(s.state.zones["p1:hand"]), len(s.state.zones["p2:hand"])
    opt = to_hand(s, "Opt")
    act(s, "p1", type="cast_spell", card_id=opt.id, targets=[])
    resolve(s)
    assert len(s.state.zones["p1:hand"]) == hand + 2 and len(s.state.zones["p2:hand"]) == theirs  # (Alice's copy, then Opt)
    check(s)


def test_mondassian_colony_ship_counts_the_attackers_controllers_kin(cards, monkeypatch):
    s = table(cards, ["Mondassian Colony Ship", "Krosa"])
    bear = place(s, "Runeclaw Bear")
    place(s, "Runeclaw Bear")
    place(s, "Craw Wurm")
    place(s, "Runeclaw Bear", "p2")
    to_turn(s, 3)
    attack(s, bear)
    resolve(s)
    assert stats(s, bear) == (3, 3)
    check(s)


def test_stensia_a_counter_only_for_the_first_damage_to_a_player_each_turn(cards, monkeypatch):
    s = table(cards, ["Stensia", "Krosa"])
    angel = place(s, "Serra Angel")
    to_turn(s, 3)
    roll(s, monkeypatch, 2)  # the ping ability, until end of turn
    attack(s, angel)
    through_combat(s)
    assert s.state.cards[angel.id].counters.get("+1/+1") == 1 and life(s, "p2") == 36
    ping = next(a for a in chars(s, angel).abilities if "1 damage" in a.text)
    act(s, "p1", type="activate_ability", card_id=angel.id, ability=ping.index, targets=["p2"])
    resolve(s)
    assert life(s, "p2") == 35 and s.state.cards[angel.id].counters.get("+1/+1") == 1  # (not its first this turn)
    to_turn(s, 5)
    attack(s, angel)
    through_combat(s)
    assert s.state.cards[angel.id].counters.get("+1/+1") == 2  # (a new turn)
    check(s)


def test_gardens_of_tranquil_repose_exiles_the_dead_its_controller_scries_and_chaos_counts_them(cards, monkeypatch):
    s = table(cards, ["Gardens of Tranquil Repose", "Krosa"])
    theirs = place(s, "Runeclaw Bear", "p2")
    mana(s, B=3)
    murder = to_hand(s, "Murder")
    act(s, "p1", type="cast_spell", card_id=murder.id, targets=[theirs.id])
    seen = []
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            seen.append(d.player)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[theirs.id].zone == "p2:exile" and seen == ["p2"]  # (Bob scries)
    roll(s, monkeypatch, 2)
    assert len(on_battlefield(s, "Dalek", "p1")) == 2
    check(s)


def to_top(s, c, pid="p1"):
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "library"}, position="top")
    return c


def pool(s, sym, pid="p1"):
    p = s.state.players[pid]
    return p.mana.get(sym, 0) + sum(u.sym == sym for u in p.mana_units)


def test_nyx_chaos_adds_mana_of_the_chosen_color_equal_to_your_devotion(cards, monkeypatch):
    s = table(cards, ["Nyx", "Krosa"])
    place(s, "Runeclaw Bear")
    place(s, "Craw Wurm")
    place(s, "Runeclaw Bear", "p2")  # (not Alice's devotion)
    roll(s, monkeypatch, 2, picks=["Green"])
    assert pool(s, "G") == 3
    check(s)


def test_hotel_of_fears_counters_by_devotion_then_another_creature_is_sacrificed(cards, monkeypatch):
    s = table(cards, ["Hotel of Fears", "Krosa"])
    resolve(s)  # (its upkeep line isn't this test's: the table starts in the main phase)
    bear, wurm = place(s, "Runeclaw Bear"), place(s, "Craw Wurm")
    roll(s, monkeypatch, 2, picks=[bear.id, "Green", wurm.id])
    assert s.state.cards[bear.id].counters.get("+1/+1") == 3
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[wurm.id].zone == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("where", ["battlefield", "hand"])
def test_ketria_exiles_until_a_nonland_permanent_card_then_battlefield_or_hand(cards, monkeypatch, where):
    s = table(cards, ["Ketria", "Krosa"])
    resolve(s)
    wurm = to_top(s, next(c for c in s.state.cards.values() if c.name == "Craw Wurm"))
    forest = to_top(s, next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"))
    roll(s, monkeypatch, 2, picks=[where, where.title(), "Battlefield" if where == "battlefield" else "Hand"])
    assert s.state.cards[forest.id].zone == "p1:exile" and s.state.cards[wurm.id].zone == f"p1:{where}"
    check(s)


def test_bad_wolf_bay_chaos_cards_cant_enter_from_exile_this_turn_then_planeswalk(cards, monkeypatch):
    s = table(cards, ["Bad Wolf Bay", "Krosa"])
    bear = place(s, "Runeclaw Bear")
    for _ in range(80):  # its beginning-of-combat line exiles the Bear until the next end step
        d = s.state.rules.decision
        if s.state.turn.phase == "main2" and d is None and not s.state.zones.get("stack"):
            break
        if d is not None and d.kind == "declare_attackers":
            act(s, "p1", type="declare_attackers", attackers=[])
        elif d is not None:
            chosen = [o.id for o in d.options if o.card_id == bear.id or o.id == bear.id][:1] or [o.id for o in d.options][: d.min_choices]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen)
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[bear.id].zone == "p1:exile"
    roll(s, monkeypatch, 2)
    assert face(s).name == "Krosa"
    to_turn(s, 2)
    assert s.state.cards[bear.id].zone == "p1:exile"  # (the end step's return: it can't enter from exile this turn)
    check(s)


def test_the_dining_car_chaos_makes_artifact_token_abilities_cost_two_less_this_turn(cards, monkeypatch):
    s = table(cards, ["Krosa", "The Dining Car"])
    roll(s, monkeypatch, 1)  # → The Dining Car: each player creates a Food
    assert face(s).name == "The Dining Car"
    food = next(c for c in s.state.cards.values() if c.name == "Food" and c.controller == "p1")
    roll(s, monkeypatch, 2)
    act(s, "p1", type="activate_ability", card_id=food.id, ability=0, sources=[])
    resolve(s)
    assert life(s, "p1") == 43 and food.id not in s.state.cards or s.state.cards.get(food.id) is None or \
        not s.state.cards[food.id].zone.endswith(":battlefield")
    check(s)


def test_city_of_the_daleks_a_dalek_for_each_opponent_attacks_that_opponent_then_is_sacrificed(cards, monkeypatch):
    from app.game.errors import ActionError

    s = table(cards, ["City of the Daleks", "Krosa"], players=3)
    roll(s, monkeypatch, 2)
    daleks = on_battlefield(s, "Dalek", "p1")
    assert len(daleks) == 2 and all("haste" in chars(s, d).keywords for d in daleks)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    made = sorted(daleks, key=lambda c: c.id)
    effects = s.state.rules.effects
    wants = {c.id: next(r.split(":")[1] for x in effects for r in x.imposes if r.startswith("attack_player:") and s.state.rules.object_id(c.id) in x.affected)
             for c in made}
    assert sorted(wants.values()) == ["p2", "p3"]
    swapped = {"p2": "p3", "p3": "p2"}
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": swapped[wants[c.id]]} for c in made])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": wants[c.id]} for c in made])
    resolve(s, picks=["p2"])
    to_turn(s, 2)
    assert not on_battlefield(s, "Dalek")
    check(s)


def test_lil_giri_counters_equal_to_your_planar_die_rolls_this_turn(cards, monkeypatch):
    s = table(cards, ["Krosa", "Li'l Giri Saves the Day"])
    roll(s, monkeypatch, 1)  # roll 1: → the plane, Li'l Giri is created
    giri = on_battlefield(s, "Li'l Giri", "p1")
    assert len(giri) == 1
    roll(s, monkeypatch, 2, picks=[giri[0].id])  # roll 2: chaos
    assert s.state.cards[giri[0].id].counters.get("+1/+1") == 2
    check(s)


def test_glimmervoid_basin_chaos_each_player_but_the_controller_copies_the_creature(cards, monkeypatch):
    s = table(cards, ["Glimmervoid Basin", "Krosa"], players=3)
    wurm = place(s, "Craw Wurm", "p2")
    roll(s, monkeypatch, 2, picks=[wurm.id])
    assert len(on_battlefield(s, "Craw Wurm", "p1")) == 1 and len(on_battlefield(s, "Craw Wurm", "p3")) == 1
    assert len(on_battlefield(s, "Craw Wurm", "p2")) == 1
    check(s)


def test_the_food_court_chaos_shorthand_monarch_then_a_card_if_already_the_monarch(cards, monkeypatch):
    s = table(cards, ["The Food Court", "Krosa"])
    hand = len(s.state.zones["p1:hand"])
    roll(s, monkeypatch, 2)
    assert s.state.table.monarch == "p1" and len(s.state.zones["p1:hand"]) == hand
    roll(s, monkeypatch, 2)
    assert len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_jund_a_green_creature_spell_gains_devour_5(cards, monkeypatch):
    s = table(cards, ["Jund", "Krosa"])
    food = place(s, "Runeclaw Bear")
    mana(s, G=1, C=1)
    bear = next(c for c in s.state.cards.values() if c.name == "Runeclaw Bear" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[bear.id], to={"zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=bear.id, targets=[])
    resolve(s, picks=[food.id, "done"])
    assert s.state.cards[food.id].zone == "p1:graveyard" and s.state.cards[bear.id].counters.get("+1/+1") == 5
    check(s)


def test_grand_ossuary_chaos_exiles_all_creatures_saprolings_by_power_then_planeswalk(cards, monkeypatch):
    s = table(cards, ["Grand Ossuary", "Krosa"])
    bear, wurm = place(s, "Runeclaw Bear"), place(s, "Craw Wurm")
    theirs = place(s, "Runeclaw Bear", "p2")
    roll(s, monkeypatch, 2)
    assert all(s.state.cards[c.id].zone.endswith(":exile") for c in (bear, wurm, theirs))
    assert len(on_battlefield(s, "Saproling", "p1")) == 8 and len(on_battlefield(s, "Saproling", "p2")) == 2
    assert face(s).name == "Krosa"
    check(s)


def test_izzet_steam_maze_an_opponents_copy_is_theirs(cards, monkeypatch):
    s = table(cards, ["Izzet Steam Maze", "Krosa"])
    mana(s, U=1)
    mana(s, "p2", U=1)
    act(s, "p2", type="set_prefs", hold_priority=True)
    mine, theirs = len(s.state.zones["p1:hand"]), len(s.state.zones["p2:hand"])
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Opt").id, targets=[])
    opt = to_hand(s, "Opt", "p2")
    for _ in range(12):  # (Alice's Opt and the maze's trigger on the stack: Alice passes, Bob may respond)
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.rules.priority == "p2":
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.rules.priority == "p2"
    act(s, "p2", type="cast_spell", card_id=opt.id, targets=[])
    resolve(s)
    assert len(s.state.zones["p2:hand"]) == theirs + 2 and len(s.state.zones["p1:hand"]) == mine + 2  # (each copies their own: 707.10)
    check(s)


@pytest.mark.parametrize("sacrifice", [True, False])
def test_stroopwafel_cafe_chaos_shorthand_sacrifice_a_food_to_draw_gain_and_drain(cards, monkeypatch, sacrifice):
    s = table(cards, ["Krosa", "The Dining Car", "Stroopwafel Cafe"])
    roll(s, monkeypatch, 1)  # → The Dining Car: each player creates a Food
    roll(s, monkeypatch, 1)  # → Stroopwafel Cafe
    assert face(s).name == "Stroopwafel Cafe"
    food = on_battlefield(s, "Food", "p1")[0]
    hand = len(s.state.zones["p1:hand"])
    from app.game.handlers.planechase import roll_cost

    mana(s, C=roll_cost(s.state))
    script(monkeypatch, [2])
    act(s, "p1", type="roll_planar_die")
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            wanted = [o.id for o in d.options if (o.card_id == food.id or o.id == food.id) or (o.label.lower() in ("yes", "pay", "sacrifice")
                                                                                                 if sacrifice else o.label.lower() in ("no", "don't", "decline", "skip"))]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=(wanted or [o.id for o in d.options][-1:] if not sacrifice else wanted or [o.id for o in d.options][:1])[:1])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    if sacrifice:
        assert not on_battlefield(s, "Food", "p1") and len(s.state.zones["p1:hand"]) == hand + 1
        assert life(s, "p1") == 43 and life(s, "p2") == 37
    else:
        assert on_battlefield(s, "Food", "p1") and len(s.state.zones["p1:hand"]) == hand and life(s, "p2") == 40
    check(s)
