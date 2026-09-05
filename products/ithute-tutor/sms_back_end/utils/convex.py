from contextvars import ContextVar

current_user_id = ContextVar("current_user_id", default=None)
current_school_id = ContextVar("current_school_id", default=None)
