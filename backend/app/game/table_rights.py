"""-- table permissions -- who may change a player's cards with the manual table tools, under the host's setting.

``GameSettings.card_permissions`` ("Who may change a player's cards"; a lobby setting, then ``configure``; host-only at a LAN
table; it is table state, so saves, undo and replays keep it):

* ``everyone`` (the default): anyone seated may use the table tools on any card, as before. Tabletop freedom stays the default.
* ``owner``: a player's cards may be changed only by that player, and the host can always help (fixing mistakes). A hot-seat
  table ignores it: everyone sits at the host computer (the API passes ``host`` for every seat there, as for undo).

Whose cards they are (``keepers``):

* On the battlefield (and phased out) and on the stack: the **controller**. A permanent I control but you own (a steal effect)
  is mine to tap, move and mark while I control it (108.4, 110.2, 112.2); you get it back from me (Return to owner, Give control) or
  from the host. Its owner can't touch it meanwhile: a permanent steal (Control Magic) would be undone by its victim otherwise.
  A spell I cast from your graveyard or exile is mine on the stack likewise. A merged permanent (mutate, meld) is one object:
  its controller's. An Aura or Equipment I control stays mine wherever it is attached: I may attach my Aura to your creature
  (the host is only referenced, not changed) and only I (or the host) move, tap or detach it; you may still move your
  creature, and attachments follow their host as they always do (a consequence of moving your own card).
* In a public zone (graveyard, exile, command zone, …): the **owner**, and also the player whose zone holds it when that is
  someone else. My card in your exile ("exiled with" your card, a card you may play) can be moved by both of us.
* In a hidden zone (hand, library, sideboard, …): the player whose zone it is, and only them. Other players' views give a card
  there no owner but that zone's player (views.py), so the answer may not depend on who really owns it: a refusal or an
  allowed move would tell a player which hidden card is theirs.
* Tokens, copies and ability objects are cards like any other: their controller's on the battlefield and the stack.

What is checked: only a player's own manual table edits (move, set position, tap, counters, delete, notes, markers, damage,
P/T, face down, flip, attach, control, groups and token stacks, …) on another player's cards, and the actions that change a
player's whole zone or put objects under another player's control (draw, mill, shuffle, discard at random, untap all,
reset deck, a token, copy or spawned card for another player). Moving my own card into your zone (Donate, a card put into
your graveyard by hand) changes only my card and stays allowed.

What is never checked:

* Rules intents (cast, play, activate, choose, pass, declare attackers / blockers, concede, …) and everything the rules
  engine compiles into them (an opponent's creature put into its owner's graveyard as my Murder resolves): the engine
  applies those steps itself, never through this check.
* Resolving the top of the shared stack and the turn structure (phase, next turn and its untap, clearing combat, the
  response helper): procedures of the whole table (400.1: the stack is shared by all players), as are mulligans and undo requests.
* Looking and pointing: look at / reveal the top of a library, reveal until, search, reveal and hide, arrows, chat, dice.
* Player counters (life, poison and other resources, commander damage and tax, mana pools, monarch, initiative): they
  are not cards (a Lightning Bolt to the face is usually entered by its caster).
* Table-wide cleanup (damage wears off, until-end-of-turn markers end, combat, arrows, mana pools: the cleanup step for
  everyone, 514.2). Deleting every token isn't: it is refused while it would delete another player's tokens.
* Server-built actions (``trusted``: snapshots, loading a deck into your own seat) and history replays.

The answer depends only on what every player's view shows (the zone, a public card's owner and controller, a face-down
permanent's controller), so a refusal, or its absence, reveals nothing hidden; ids of cards a player can't see reach the check
only as the placeholders their view gave.
"""

from __future__ import annotations

from app.game import actions as A
from app.game.errors import ActionError
from app.game.state import HIDDEN_ZONES, STACK, CardInstance, GameState, split_zone

# -- the cards each manual action changes (by field) ------------------------------------------------------------------
CARD_IDS = frozenset({
    "move", "tap", "phase_shift", "counter", "delete_card", "face_down", "set_controller", "add_effect", "remove_effect",
    "set_damage", "set_exile_group", "return_to_owner", "rotate", "set_lock", "set_protect", "detach", "group", "ungroup",
    "merge_tokens", "attack",
    "attach",  # the attachments only: the host they go onto is referenced, not changed (my Aura onto your creature)
})
CARD_ID = frozenset({
    "set_counter", "set_face", "flip", "note", "set_choice", "set_stack_info", "set_copy_source", "set_commander",
    "stack_adjust", "split_stack", "expand_stack",
    "block",  # the blocker (the attacker it blocks is referenced, not changed)
})
# whose zone the action changes wholesale, or under whose control it puts new objects (``player``, default: the actor)
PLAYER = frozenset({
    "draw", "mill", "shuffle", "put_top_face_down", "cascade", "fetch_card", "discard_random", "untap_all", "reset_deck",
    "create_token", "copy_card", "spawn_card",  # a token / copy / test object on another player's side (the source is only read)
})
OTHER = frozenset({"set_position", "merge", "meld", "cleanup", "run_macro"})  # see ``_touched``

# -- never checked (see the module docstring) -------------------------------------------------------------------------
OPEN = frozenset({
    # rules intents and the engine's own server-built steps
    *A.INTENT_TYPES, *A.SERVER_ONLY_TYPES, "restore_state", "response_open",
    # the table's procedures: resolving, the turn structure, the response helper, mulligans
    "resolve_top", "phase", "next_turn", "clear_combat", "response_pass", "response_respond", "response_auto", "response_close",
    "mulligan", "mulligan_take", "mulligan_keep", "mulligan_bottom", "mulligan_powder", "mulligan_finish", "restart_game",
    # looking, showing and pointing
    "look_top", "reveal_top", "reveal_until", "search_start", "search_end", "end_view", "reveal", "hide", "create_arrow",
    "remove_arrow", "chat", "roll", "coin",
    # -- table toys -- the table's dice cannon and draw bag (app/game/handlers/toys.py): no player's cards
    "cannon", "bag_fill", "bag_draw", "bag_show", "bag_return", "bag_empty",
    # -- planechase -- the table's planar deck and die (app/game/handlers/planechase.py): no player's cards
    "planar_start", "planar_end", "planar_roll", "planeswalk",
    # player counters, not cards
    "life", "set_life", "resource", "set_resource", "commander_damage", "commander_tax", "set_monarch", "set_initiative",
    "city_blessing", "add_mana", "clear_mana",
    # table settings and seats (host-only where it matters: games.HOST_ONLY_ACTIONS), your own look, your own ability object
    "configure", "set_day_night", "set_appearance", "set_table_playmat", "rename_player", "remove_player", "create_ability",
    "add_dummy", "reset_dummy",  # -- target dummy -- (host-only: games.HOST_ONLY_ACTIONS)
})


def keepers(c: CardInstance) -> list[str]:
    """The players who may change ``c`` under the ``owner`` setting (the host aside), most responsible first."""
    holder, zone = split_zone(c.zone)
    if c.zone == STACK or zone in ("battlefield", "phased"):
        return [c.controller]
    if zone in HIDDEN_ZONES and holder:  # whose hand / library it is (a hidden card's owner is not public)
        return [holder]
    return list(dict.fromkeys(p for p in (c.owner, holder) if p))


def _touched(state: GameState, a: A.Action, actor: str) -> tuple[list[str], list[str]]:
    """(card ids, players): what ``a`` changes as a manual table edit."""
    t = a.type
    if t in CARD_IDS:
        return list(getattr(a, "card_ids", None) or []), []
    if t in CARD_ID:
        cid = getattr(a, "card_id", None)
        return ([cid] if cid else []), []
    if t in PLAYER:
        return [], [getattr(a, "player", None) or actor]
    if isinstance(a, A.SetPosition):
        return [m[0] for m in a.moves], []
    if isinstance(a, A.Merge):
        return [a.card_id, a.spell_id], []
    if isinstance(a, A.Meld):
        return [a.card_id, a.other_id], []
    if isinstance(a, A.Cleanup):
        if a.card_ids:
            return list(a.card_ids), []
        if "tokens" in a.what:  # the same tokens the handler deletes (game/handlers/marks.py)
            return [c.id for c in state.cards.values() if c.is_token and not c.protected and c.commander_key is None], []
        return [], []
    return [], []


def _name(state: GameState, pid: str) -> str:
    p = state.players.get(pid)
    return p.name if p is not None else pid


def _message(state: GameState, who: list[str]) -> str:
    names = [_name(state, pid) for pid in who]
    return f"{names[0]}'s cards: only {', '.join(names)} or the host can change them at this table."


def _check_one(state: GameState, a: A.Action, actor: str) -> str | None:
    cards, players = _touched(state, a, actor)
    for pid in players:
        if pid != actor and pid in state.players:
            return _message(state, [pid])
    for cid in cards:
        c = state.cards.get(cid)
        if c is None:  # not a card (an unresolved placeholder, a deleted one): the handler says so
            continue
        who = keepers(c)
        if actor not in who:
            return _message(state, who)
    return None


def refusal(state: GameState, action: A.Action, actor: str, *, host: bool) -> str | None:
    """Why ``actor`` may not perform ``action`` (resolved: placeholders are real ids, a macro's steps are filled in) under the
    table's card permissions, or None. ``host``: the actor counts as the host (always at a hot-seat table)."""
    if host or state.settings.card_permissions != "owner" or action.type in OPEN:
        return None
    if isinstance(action, A.RunMacro):  # its steps are ordinary actions (game/macros.py): each is checked like one
        for step in action.r or []:
            if (why := refusal(state, A.parse_action(step), actor, host=host)) is not None:
                return why
        return None
    return _check_one(state, action, actor)


def check(state: GameState, action: A.Action, actor: str, *, host: bool) -> None:
    if (why := refusal(state, action, actor, host=host)) is not None:
        raise ActionError(why)

