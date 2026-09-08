from pathlib import Path
def test_phase34_contract_control_contract_is_wired():
 root=Path(__file__).resolve().parents[1];api=(root/"app/api/v1/contract_control.py").read_text();models=(root/"app/models/contract_control.py").read_text();migration=(root/"alembic/versions/0035_phase34_contract_control.py").read_text();ui=root.parents[0]/"frontend/app/contract-control/page.tsx"
 assert 'revision="0035_phase34_contract_ctrl"' in migration and 'down_revision="0034_phase33_client_accounts"' in migration
 for x in ("contract_notices","contract_extensions_of_time","contract_variation_instructions","contract_control_audit_events"):assert x in models or x in migration
 for x in ("Independent notice issue is required","Independent extension review is required","Independent instruction approval is required"):assert x in api
 assert ui.exists() and "FormDialog" in ui.read_text() and "Contract Administration &amp; Variation Control" in ui.read_text()
