from types import SimpleNamespace

import pytest

from app.models import SubscriptionStatus
from app.services.commercial_ops_v2 import request_plan_change


def _subscription(status: SubscriptionStatus):
    return SimpleNamespace(status=status)


def _target():
    return SimpleNamespace(lifecycle_state="sellable", is_active=True, customer_visible=True)


def test_past_due_subscription_cannot_change_package():
    with pytest.raises(ValueError, match="outstanding invoice"):
        request_plan_change(None, _subscription(SubscriptionStatus.past_due), _target())


def test_canceled_subscription_cannot_change_package():
    with pytest.raises(ValueError, match="reactivate"):
        request_plan_change(None, _subscription(SubscriptionStatus.canceled), _target())
