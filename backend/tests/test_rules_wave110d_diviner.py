"""Wave 110D: Twilight Diviner, real Oracle text (tests/fixtures/wave110d_cards.json).

* 603.2c: one trigger for a batch of creatures entering; 603.4: it needs one of them to have entered (or been cast) from a graveyard.
* 707.2, 111.4: its controller picks any ONE of the batch and the token copies it.
* Not from a graveyard (cast from the hand): no token. "Once each turn" is the engine's shared limit "once_each_turn".
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, to_hand
from tests.wave110d_kit import card_db, check, cast_on, full, mana, now, put_new, settle, to_phase  # noqa: F401


def _bears(s):
    return [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:battlefield" and c.token]


def _grave(s, *names):
    out = [to_hand(s, n) for n in names]
    act(s, "p1", type="move", card_ids=[c.id for c in out], to={"player": "p1", "zone": "graveyard"})
    return out


def test_diviner_is_full():
    assert full("Twilight Diviner")


def test_graveyard_entry_copies_it(cards):
    s = build(cards, ["Twilight Diviner", "Grizzly Bears", "Reanimate"])
    put_new(s, "Twilight Diviner")
    (bears,) = _grave(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    cast_on(s, "Reanimate", bears)
    settle(s)
    assert now(s, bears).zone == "p1:battlefield" and len(_bears(s)) == 1
    check(s)


def test_hand_cast_makes_nothing(cards):
    s = build(cards, ["Twilight Diviner", "Grizzly Bears", "Ambush Viper", "Reanimate"])
    put_new(s, "Twilight Diviner")
    (bears,) = _grave(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    cast_on(s, "Ambush Viper")  # from the hand: not from a graveyard (603.4)
    assert not [c for c in s.state.cards.values() if c.token]
    cast_on(s, "Reanimate", bears)
    assert len(_bears(s)) == 1
    check(s)


def test_batch_choice_copies_the_chosen_one(cards):
    s = build(cards, ["Twilight Diviner", "Grizzly Bears", "Ambush Viper", "Rise of the Dark Realms"])
    put_new(s, "Twilight Diviner")
    bears, viper = _grave(s, "Grizzly Bears", "Ambush Viper")
    to_phase(s, "main1", turn=3)
    c = to_hand(s, "Rise of the Dark Realms")
    mana(s, "p1", C=7, B=2)
    act(s, "p1", type="cast_spell", card_id=c.id)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            pick = next((o.id for o in d.options if o.card_id == viper.id), d.options[0].id)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        elif s.state.zones.get("stack"):
            act(s, s.state.turn.priority, type="pass_priority")
        else:
            break
    assert now(s, bears).zone == now(s, viper).zone == "p1:battlefield"
    assert [t.name for t in s.state.cards.values() if t.token and t.zone == "p1:battlefield"] == ["Ambush Viper"]
    check(s)
