"""Optional local rules assistant (disabled by default).

The assistant answers rules questions using an Ollama-compatible local model. It only ever
receives the *asking player's sanitized view* (never hidden information) plus the Oracle
text of visible cards, and it has no reference to the game session, so it cannot change
game state.
"""

from app.assistant.context import build_context
from app.assistant.service import AssistantUnavailable, OllamaAssistant, RulesAssistant

__all__ = ["AssistantUnavailable", "OllamaAssistant", "RulesAssistant", "build_context"]
