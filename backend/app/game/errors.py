class ActionError(ValueError):
    """An action that cannot be applied to the current state (reported to the client)."""


class NotAllowed(ActionError):
    """The acting seat is not permitted to perform this action."""
