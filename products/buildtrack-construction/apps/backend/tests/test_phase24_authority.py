from pathlib import Path
def test_phase24_authority_contract():
 r=Path(__file__).resolve().parents[1];api=(r/"app/api/v1/authority.py").read_text();m=(r/"alembic/versions/0025_phase24_authority.py").read_text();assert 'down_revision = "0024_phase23_data_quality"' in m and "AUTHORITY_LIMIT" in api and "Self-approval is disabled" in api
