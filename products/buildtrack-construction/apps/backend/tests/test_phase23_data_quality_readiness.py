from pathlib import Path
def test_phase23_data_quality_contract_is_wired() -> None:
 root=Path(__file__).resolve().parents[1];api=(root/"app/api/v1/data_quality.py").read_text();models=(root/"app/models/data_quality.py").read_text();migration=(root/"alembic/versions/0024_phase23_data_quality.py").read_text()
 assert 'revision = "0024_phase23_data_quality"' in migration and 'down_revision = "0023_phase22_compliance"' in migration
 for value in ("data_quality_runs","data_quality_findings","approved_budget","Self-verification is disabled"):assert value in models or value in api or value in migration
