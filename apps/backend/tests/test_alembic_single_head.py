from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


LATEST_MIGRATION_HEAD = "0018_domain_verification_method"


def test_alembic_has_one_consolidated_head():
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()

    assert len(heads) == 1, f"Expected exactly one Alembic head, got: {heads}"
    assert heads == [LATEST_MIGRATION_HEAD], f"Expected current Alembic head {LATEST_MIGRATION_HEAD}, got: {heads}"
