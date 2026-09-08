from pathlib import Path
def test_phase25_change_control():
 r=Path(__file__).resolve().parents[1];assert 'down_revision = "0025_phase24_authority"' in (r/'alembic/versions/0026_phase25_change_control.py').read_text();assert 'Self-approval is disabled' in (r/'app/api/v1/change_control.py').read_text()
