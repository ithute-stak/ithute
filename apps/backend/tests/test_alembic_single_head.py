from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_one_consolidated_head():
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()

    assert heads == ["0012_merge_consolidated_heads"], f"Expected one consolidated Alembic head, got: {heads}"
