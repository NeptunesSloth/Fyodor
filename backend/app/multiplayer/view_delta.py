"""-- view deltas -- what changed between two views a connection was sent, instead of the whole view again.

Every action used to send each connection its whole view (60-110 KB late in a game: the cards, the log, the rules prompts), and the
browser parsed and compared all of it. A client that asks for deltas (``?deltas=1`` on the game socket) gets its full view on connect,
reconnect, resync and seat switch, as before; after that, each update is a patch from the last view this connection was sent to the
new one, both built for the connection's own viewer by the usual view builders (``GameHub.view``). Nothing in a patch comes from
anywhere else: its values are parts of the new view, its removals are keys of the old one, so a patch can never show a viewer anything
their own full view would not (tests/test_view_deltas.py checks that against every other viewer's hidden cards).

The patch of two JSON objects (``diff``), keyed by what changed:

* ``set``: keys whose value is new or replaced (the value as the full view has it);
* ``del``: keys gone;
* ``sub``: keys holding an object that changed in part: the patch of that object (down to ``MAX_DEPTH``: the cards by id, each card's
  fields);
* ``tail``: keys holding a list that only lost items at its start and gained items at its end (the log: ``{"drop": n, "add": [...]}``);
* ``keys``: the object's keys in their new order, when applying the rest would leave a different order (JSON objects keep their order,
  and a patched view must be the very view the server built).

Applying it (``apply``; the browser's frontend/src/services/viewDelta.ts) gives exactly the new view. A delta message names the view it
applies to (``base``: the connection's view sequence number, ``vseq``, of the last view message it was sent); a client holding any other
view, or one a patch does not fit, asks for a full view (the resync it already had for missed updates). Views are compared as the
client parsed them (``freeze``: a JSON round trip), so a value that serializes the same is the same, and the kept copy can never change
under the server's feet (a view may share lists with the live table). Every patch is checked before it goes out (``checked``): applied to
the old view it must give the new view's very JSON text, or the whole view is sent instead.
"""

from __future__ import annotations

import json
from typing import Any

MAX_DEPTH = 4  # objects deeper than this are replaced whole when they change (the view's own nesting: view → cards → card → field)


def freeze(view: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """The view as the client parses it (a fresh JSON copy: shares nothing with the table), and its JSON text."""
    text = json.dumps(view, separators=(",", ":"))
    return json.loads(text), text


def checked(old: dict[str, Any], new: dict[str, Any], text: str) -> dict[str, Any] | None:
    """The patch from ``old`` to ``new`` (``text``: ``new``'s JSON), checked: applying it gives that very text, else None (send the whole
    view). ``diff`` compares with Python's ``==``, for which ``True == 1`` and ``0 == False``: a field that went from 1 to true would be
    missed, and the check catches it (as it would any other slip) at the price of one JSON dump of the patched view."""
    patch = diff(old, new)
    try:
        ok = json.dumps(apply(old, patch), separators=(",", ":")) == text
    except PatchError:
        ok = False
    return patch if ok else None


def diff(old: dict[str, Any], new: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    """The patch that turns ``old`` into ``new`` (both JSON objects; {} when they are equal). Its values are ``new``'s own."""
    patch: dict[str, Any] = {}
    sets: dict[str, Any] = {}
    subs: dict[str, Any] = {}
    tails: dict[str, Any] = {}
    added = 0
    for k, v in new.items():
        if k not in old:
            sets[k] = v
            added += 1
            continue
        o = old[k]
        if o == v:
            continue
        if type(o) is dict and type(v) is dict and depth < MAX_DEPTH:
            subs[k] = diff(o, v, depth + 1)
        elif type(o) is list and type(v) is list and (t := _tail(o, v)) is not None:
            tails[k] = t
        else:
            sets[k] = v
    gone = [k for k in old if k not in new] if len(old) > len(new) - added else []  # (every old key still there: none gone)
    if sets:
        patch["set"] = sets
    if gone:
        patch["del"] = gone
    if subs:
        patch["sub"] = subs
    if tails:
        patch["tail"] = tails
    order = list(new)  # (a key can also move: a card the view lists in another place now)
    if order != ([k for k in old if k in new] + [k for k in new if k not in old] if added or gone else list(old)):
        patch["keys"] = order
    return patch


def _tail(old: list[Any], new: list[Any]) -> dict[str, Any] | None:
    """``new`` as ``old`` less its first ``drop`` items plus ``add`` (the most of ``old`` kept), or None when it isn't one, or when that
    saves nothing (the whole list again is as short)."""
    lo, ln = len(old), len(new)
    if not lo or not ln:
        return None
    first = new[0]
    for drop in range(max(0, lo - ln), lo):
        keep = lo - drop
        if old[drop] == first and old[drop:] == new[:keep]:
            return {"drop": drop, "add": new[keep:]}
    return None


class PatchError(ValueError):
    """A patch that does not fit the view it is applied to."""


def apply(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """``patch`` applied to ``base`` (neither is changed): the reference for the client's own apply, and the tests' oracle."""
    if type(base) is not dict or type(patch) is not dict:
        raise PatchError("not an object")
    out = dict(base)
    for k in patch.get("del", ()):
        if k not in out:
            raise PatchError(f"no key {k!r} to remove")
        del out[k]
    for k, sub in patch.get("sub", {}).items():
        if type(base.get(k)) is not dict:
            raise PatchError(f"no object at {k!r}")
        out[k] = apply(base[k], sub)
    for k, t in patch.get("tail", {}).items():
        items = base.get(k)
        drop = t.get("drop") if type(t) is dict else None
        if type(items) is not list or type(drop) is not int or not 0 <= drop <= len(items) or type(t.get("add")) is not list:
            raise PatchError(f"no list to extend at {k!r}")
        out[k] = items[drop:] + t["add"]
    out.update(patch.get("set", {}))
    if "keys" in patch:
        keys = patch["keys"]
        if type(keys) is not list or len(keys) != len(out) or set(keys) != out.keys():
            raise PatchError("the key order names other keys")
        out = {k: out[k] for k in keys}
    return out
