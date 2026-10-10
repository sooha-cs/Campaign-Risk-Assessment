class ValidationError(ValueError):
    """Bad data (from the user or from the AI). Carries a list of readable messages."""

    def __init__(self, errors):
        self.errors = errors if isinstance(errors, list) else [errors]
        super().__init__("; ".join(self.errors))


class AIOutputError(ValidationError):
    """The AI returned JSON that breaks our rules. Triggers an automatic retry."""


class NotFoundError(LookupError):
    """The requested project or record does not exist (reported to the client as HTTP 404)."""
