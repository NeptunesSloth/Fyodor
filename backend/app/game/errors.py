class ActionError(ValueError):
    """An action that cannot be applied to the current state (reported to the client)."""


class NotAllowed(ActionError):
    """The acting seat is not permitted to perform this action."""


class AutomationError(ActionError):
    """The rules engine failed unexpectedly on an intent. Nothing was applied; the table is
    exactly as it was, and the players can resolve it by hand, pause automation, or export a
    rules scenario for a regression test."""

    PREFIX = "AUTOMATION ERROR"
