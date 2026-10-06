def _matching_routes(app, method: str, path: str):
    return [
        route
        for route in app.routes
        if getattr(route, "path", None) == path
        and method.upper() in (getattr(route, "methods", None) or set())
    ]


def _assert_owner(app, method: str, path: str, module: str):
    matches = _matching_routes(app, method, path)
    assert len(matches) == 1, (
        f"{method} {path} must have exactly one handler; "
        f"found {[getattr(route.endpoint, '__module__', '?') for route in matches]}"
    )
    assert matches[0].endpoint.__module__ == module


def test_canonical_pricing_and_plan_route_ownership(client):
    app = client.app
    _assert_owner(app, "GET", "/api/v1/public/pricing", "app.api.v1.canonical_pricing")
    _assert_owner(app, "GET", "/api/v1/platform/billing/plans", "app.api.v1.plan_admin")
    _assert_owner(app, "POST", "/api/v1/platform/billing/plans", "app.api.v1.plan_admin")
    _assert_owner(app, "PATCH", "/api/v1/platform/billing/plans/{plan_id}", "app.api.v1.plan_admin")


def test_external_webmail_route_ownership(client):
    app = client.app
    _assert_owner(app, "POST", "/api/v1/webmail/external/session", "app.api.v1.external_webmail_smart")
    _assert_owner(app, "GET", "/api/v1/webmail/external/folder-counts", "app.api.v1.external_webmail_counts")
    _assert_owner(app, "POST", "/api/v1/webmail/external/send", "app.api.v1.external_webmail_rich_alias")
    _assert_owner(app, "POST", "/api/v1/webmail/external/drafts", "app.api.v1.external_webmail_rich_alias")
