from pathlib import Path


def test_phase27_knowledge_and_support_contract_is_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    api = (root / "app/api/v1/knowledge.py").read_text()
    support = (root / "app/api/v1/support.py").read_text()
    models = (root / "app/models/knowledge.py").read_text()
    migration = (root / "alembic/versions/0028_phase27_knowledge.py").read_text()
    frontend = root.parents[0] / "frontend/app/support/page.tsx"
    navigation = root.parents[0] / "frontend/app/components/buildtrack-navigation.tsx"

    assert 'revision = "0028_phase27_knowledge"' in migration
    assert 'down_revision = "0027_phase26_support"' in migration
    for value in ("knowledge_articles", "knowledge_acknowledgements", "knowledge_audit_events", "source_ticket_id", "review_due_date"):
        assert value in models or value in migration
    for value in ("/articles/{article_id:int}/publish", "Self-publication is disabled", "Knowledge source ticket must be a closed ticket", "knowledge.article.acknowledged"):
        assert value in api
    assert '@router.get("/catalog")' in support and "Document" in support
    assert frontend.exists() and "FormDialog" in frontend.read_text() and "Support Centre" in frontend.read_text()
    assert 'href: "/support"' in navigation.read_text()
