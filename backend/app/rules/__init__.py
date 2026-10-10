"""Extension point for incremental rules assistance.

Fyodor is a manual sandbox: the engine never enforces rules. Rules modules may *observe*
applied actions and return advisory suggestions (e.g. "Grizzly Bears has lethal damage")
which the UI can show. They cannot change state. A future module that automates something
must emit ordinary actions through the same validated, logged, undoable path as players.

Planned modules (not implemented): triggers, replacement_effects, continuous_effects,
targeting, state_based_actions, priority, combat, layers.
"""

import re as _re

from app.rules.base import RulesModule, RulesRegistry, Suggestion

# -- speed (wave 29A) -- Oracle text is read with several thousand different regular expressions (the card-text grammar), far more than the
# 512 the ``re`` module keeps: the rest were compiled again, and again, every time a card was parsed (two thirds of a coverage dump, most of
# the time to load a table). Compiling a pattern has no side effects, so keeping more of them can't change a result.
if getattr(_re, "_MAXCACHE", 0) < 8192:
    _re._MAXCACHE = 8192  # type: ignore[attr-defined]

__all__ = ["RulesModule", "RulesRegistry", "Suggestion"]
