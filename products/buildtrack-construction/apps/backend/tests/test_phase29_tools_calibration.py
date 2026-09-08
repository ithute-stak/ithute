from pathlib import Path
def test_phase29_tools_contract_is_wired():
 root=Path(__file__).resolve().parents[1];api=(root/"app/api/v1/tools.py").read_text();models=(root/"app/models/tools.py").read_text();migration=(root/"alembic/versions/0030_phase29_tools.py").read_text();ui=root.parents[0]/"frontend/app/tools/page.tsx"
 assert 'revision="0030_phase29_tools"' in migration and 'down_revision="0029_phase28_environment"' in migration
 for value in ("tool_assets","tool_issues","tool_calibrations","tool_audit_events"):assert value in models or value in migration
 for value in ("Tool calibration is overdue or missing","Self-verification is disabled","/{i}/issue","/issues/{i}/return"):assert value in api
 assert ui.exists() and "FormDialog" in ui.read_text() and "Tools &amp; Calibration Control" in ui.read_text()
