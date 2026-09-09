from pathlib import Path
def test_phase32_business_development_contract_is_wired():
 root=Path(__file__).resolve().parents[1];api=(root/"app/api/v1/business_development.py").read_text();models=(root/"app/models/business_development.py").read_text();migration=(root/"alembic/versions/0033_phase32_business_development.py").read_text();ui=root.parents[0]/"frontend/app/business-development/page.tsx"
 assert 'revision="0033_phase32_business_dev"' in migration and 'down_revision="0032_phase31_vendor_portal"' in migration
 for x in ("business_opportunities","business_opportunity_activities","business_development_audit_events"):assert x in models or x in migration
 for x in ("Independent qualification is required","Qualification requires client contact","/link-tender","/activities"):assert x in api
 assert ui.exists() and "FormDialog" in ui.read_text() and "Business Development &amp; Opportunity Pipeline" in ui.read_text()
