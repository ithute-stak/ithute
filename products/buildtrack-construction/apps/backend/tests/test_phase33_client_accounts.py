from pathlib import Path
def test_phase33_client_accounts_contract_is_wired():
 root=Path(__file__).resolve().parents[1];api=(root/"app/api/v1/client_accounts.py").read_text();models=(root/"app/models/client_accounts.py").read_text();migration=(root/"alembic/versions/0034_phase33_client_accounts.py").read_text();ui=root.parents[0]/"frontend/app/client-accounts/page.tsx"
 assert 'revision="0034_phase33_client_accounts"' in migration and 'down_revision="0033_phase32_business_dev"' in migration
 for x in ("client_accounts","client_account_contacts","client_feedback","client_account_audit_events"):assert x in models or x in migration
 for x in ("Independent feedback verification is required","/feedback/{f}/verify","Received feedback with a remediation action plan"):assert x in api
 assert ui.exists() and "FormDialog" in ui.read_text() and "Client Relationship &amp; Account Management" in ui.read_text()
