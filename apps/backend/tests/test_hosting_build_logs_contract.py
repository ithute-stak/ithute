import pytest
from pydantic import ValidationError

from app.api.v1.hosting_build_logs import (
    MAX_LOG_BATCH,
    MAX_LOG_ENTRIES_PER_BUILD,
    MAX_LOG_MESSAGE_CHARS,
    BuildLogBatch,
    BuildLogEntry,
)


def test_build_log_entry_contract_accepts_safe_stage():
    row = BuildLogEntry(stage="runtime_detected", level="info", message="Detected Python runtime")
    assert row.stage == "runtime_detected"
    assert row.level == "info"


@pytest.mark.parametrize("stage", ["Bad Stage", "../escape", "x/y", "UPPER", ""])
def test_build_log_entry_rejects_unsafe_stage(stage: str):
    with pytest.raises(ValidationError):
        BuildLogEntry(stage=stage, message="x")


def test_build_log_entry_rejects_oversized_message():
    with pytest.raises(ValidationError):
        BuildLogEntry(stage="build", message="x" * (MAX_LOG_MESSAGE_CHARS + 1))


def test_build_log_batch_is_bounded():
    entries = [BuildLogEntry(stage="build", message=str(index)) for index in range(MAX_LOG_BATCH)]
    assert len(BuildLogBatch(entries=entries).entries) == MAX_LOG_BATCH
    with pytest.raises(ValidationError):
        BuildLogBatch(entries=entries + [BuildLogEntry(stage="build", message="overflow")])


def test_build_log_storage_limit_is_deliberately_finite():
    assert MAX_LOG_ENTRIES_PER_BUILD == 500
