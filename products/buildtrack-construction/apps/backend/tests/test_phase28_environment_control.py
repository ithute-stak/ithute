from pathlib import Path
def test_phase28_environment_contract_is_wired():
 root=Path(__file__).resolve().parents[1];api=(root/"app/api/v1/environment.py").read_text();models=(root/"app/models/environment.py").read_text();migration=(root/"alembic/versions/0029_phase28_environment.py").read_text();ui=root.parents[0]/"frontend/app/environment/page.tsx"
 assert 'revision="0029_phase28_environment"' in migration and 'down_revision="0028_phase27_knowledge"' in migration
 for value in ("environmental_plans","environmental_waste_records","environmental_inspections","environmental_audit_events"):assert value in models or value in migration
 for value in ("Hazardous waste needs controlled evidence","Self-approval is disabled","Self-verification is disabled","/inspections/{i}/remediate"):assert value in api
 assert ui.exists() and "FormDialog" in ui.read_text() and "Environmental &amp; Sustainability Control" in ui.read_text()
