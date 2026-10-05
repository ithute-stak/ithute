from app.models import BillingPlan
from app.services.billing import calculate_overage


def _plan(**changes) -> BillingPlan:
    values = {
        "code": "metered-unit",
        "name": "Metered Unit",
        "currency": "LSL",
        "monthly_price_minor": 10_000,
        "included_mailboxes": 10,
        "included_domains": 2,
        "included_storage_mb": 1024,
        "max_api_keys": 3,
        "included_hosted_projects": 1,
        "hosting_storage_mb": 1024,
        "hosting_memory_mb_per_project": 512,
        "hosting_cpu_millicores_per_project": 500,
        "hosting_pids_per_project": 128,
        "hosting_database_limit": 2,
        "hosting_database_storage_mb": 1024,
        "hosting_source_storage_mb": 1024,
        "allow_metered_overages": True,
        "overage_mailbox_minor": 500,
        "overage_domain_minor": 1000,
        "overage_storage_gb_minor": 250,
        "overage_api_key_minor": 300,
        "overage_hosted_project_minor": 2500,
        "overage_hosting_storage_gb_minor": 400,
        "overage_database_minor": 1500,
        "overage_database_storage_gb_minor": 350,
        "overage_source_storage_gb_minor": 200,
    }
    values.update(changes)
    return BillingPlan(**values)


def _usage(**changes) -> dict:
    values = {
        "mailboxes": 10,
        "domains": 2,
        "allocated_storage_bytes": 1024 * 1024 * 1024,
        "api_keys": 3,
        "hosted_projects": 1,
        "hosting_storage_bytes": 1024 * 1024 * 1024,
        "hosting_database_count": 2,
        "hosting_database_storage_bytes": 1024 * 1024 * 1024,
        "hosting_source_storage_bytes": 1024 * 1024 * 1024,
    }
    values.update(changes)
    return values


def test_metered_overages_charge_extra_units_and_started_gigabytes():
    plan = _plan()
    usage = _usage(
        mailboxes=12,
        allocated_storage_bytes=(1024 * 1024 * 1024) + 1,
        hosting_database_count=3,
    )

    result = calculate_overage(plan, usage)

    assert result["enabled"] is True
    assert result["fully_priced"] is True
    assert result["unpriced_metrics"] == []
    assert result["estimated_minor"] == 2 * 500 + 250 + 1500
    assert {item["metric"]: item["units"] for item in result["items"]} == {
        "mailboxes": 2,
        "storage_gb": 1,
        "hosting_database_count": 1,
    }


def test_unpriced_excess_is_reported_instead_of_silently_free():
    plan = _plan(overage_domain_minor=0)
    result = calculate_overage(plan, _usage(domains=3))

    assert result["enabled"] is True
    assert result["fully_priced"] is False
    assert result["estimated_minor"] == 0
    assert result["unpriced_metrics"] == ["domains"]
    assert result["items"][0]["amount_minor"] == 0


def test_hard_cap_plan_never_creates_billable_overage_amount():
    plan = _plan(allow_metered_overages=False)
    result = calculate_overage(plan, _usage(mailboxes=20, domains=5))

    assert result["enabled"] is False
    assert result["fully_priced"] is False
    assert result["estimated_minor"] == 0
    assert {item["metric"] for item in result["items"]} == {"mailboxes", "domains"}
