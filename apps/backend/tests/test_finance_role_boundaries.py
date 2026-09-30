from starlette.requests import Request

from app.api.deps import _finance_required_role


def request(method: str, path: str) -> Request:
    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "scheme": "https",
        "server": ("ithute.co.ls", 443),
        "client": ("127.0.0.1", 50000),
    })


def test_finance_reads_are_viewer_level():
    assert _finance_required_role(request("GET", "/api/v1/finance/invoices")) == "viewer"


def test_finance_clerical_posts_are_clerk_level():
    assert _finance_required_role(request("POST", "/api/v1/finance/invoices")) == "clerk"
    assert _finance_required_role(request("POST", "/api/v1/finance/invoices/00000000-0000-0000-0000-000000000000/payments")) == "clerk"


def test_finance_adjustments_require_approver():
    invoice = "00000000-0000-0000-0000-000000000000"
    assert _finance_required_role(request("POST", f"/api/v1/finance/invoices/{invoice}/credit-notes")) == "approver"
    assert _finance_required_role(request("POST", f"/api/v1/finance/invoices/{invoice}/cancel")) == "approver"
    assert _finance_required_role(request("POST", "/api/v1/finance/control/refunds")) == "approver"
    assert _finance_required_role(request("POST", "/api/v1/finance/completion/delivery-events")) == "approver"


def test_finance_configuration_and_deletes_require_admin():
    invoice = "00000000-0000-0000-0000-000000000000"
    assert _finance_required_role(request("PUT", "/api/v1/finance/sender")) == "admin"
    assert _finance_required_role(request("POST", "/api/v1/finance/control/tax-rates")) == "admin"
    assert _finance_required_role(request("POST", "/api/v1/finance/control/periods/2026/9/lock")) == "admin"
    assert _finance_required_role(request("DELETE", f"/api/v1/finance/invoices/{invoice}")) == "admin"
