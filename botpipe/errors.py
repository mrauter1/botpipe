"""Errors and durable suspension signals."""


class BotpipeError(Exception):
    pass


class ReplayMismatch(BotpipeError):
    """Recorded execution and current orchestration disagree."""


class WorkflowChanged(ReplayMismatch):
    pass


class RunBusy(BotpipeError):
    pass


class ActivityFailed(BotpipeError):
    """A recorded custom exception whose original type is unavailable."""


class Suspension(BaseException):
    """Control signal deliberately excluded from application except Exception."""


class InputRequired(Suspension):
    def __init__(self, question, operation_id=None, diagnostic=None):
        self.question = question
        self.operation_id = operation_id
        self.diagnostic = diagnostic
        super().__init__(question)


class UncertainOperation(Suspension):
    def __init__(self, message, operation_id=None):
        self.operation_id = operation_id
        super().__init__(message)


class BudgetExceeded(Suspension):
    pass
