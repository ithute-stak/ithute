# Import endpoint modules for router-registration side effects.
from app.api.v1 import ithute_operating_control, ithute_operating_events, ithute_operating_ops  # noqa: F401
from app.api.v1.ithute_operating_common import router

__all__ = ["router"]
