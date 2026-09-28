"""Extension point for incremental rules assistance.

Fyodor is a manual sandbox: the engine never enforces rules. Rules modules may *observe*
applied actions and return advisory suggestions (e.g. "Grizzly Bears has lethal damage")
which the UI can show. They cannot change state. A future module that automates something
must emit ordinary actions through the same validated, logged, undoable path as players.

Planned modules (not implemented): triggers, replacement_effects, continuous_effects,
targeting, state_based_actions, priority, combat, layers.
"""

from app.rules.base import RulesModule, RulesRegistry, Suggestion

__all__ = ["RulesModule", "RulesRegistry", "Suggestion"]
