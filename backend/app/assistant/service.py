from __future__ import annotations

import json
import logging
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a Magic: The Gathering rules assistant at a casual table. Answer the player's rules "
    "question using the comprehensive rules and the Oracle text provided. Be concise, cite the "
    "relevant rule when you are sure of it, and say when you are unsure. You only see what this "
    "player can see; never guess hidden cards. You cannot take game actions."
)


class AssistantUnavailable(RuntimeError):
    pass


class RulesAssistant(Protocol):
    def ask(self, question: str, context: dict[str, Any]) -> str: ...


class OllamaAssistant:
    """Talks to an Ollama-compatible ``/api/chat`` endpoint on the local machine or LAN."""

    def __init__(self, base_url: str, model: str = "llama3.1", timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def ask(self, question: str, context: dict[str, Any]) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Game context (JSON):\n{json.dumps(context)}\n\nQuestion: {question}"},
            ],
        }
        try:
            res = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
            res.raise_for_status()
            return str(res.json()["message"]["content"]).strip()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("Assistant request failed: %s", exc)
            raise AssistantUnavailable(f"The local assistant did not answer: {exc}") from exc
