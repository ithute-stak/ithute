from pathlib import Path
import re


VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
REVISION_RE = re.compile(r'^revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
DOWN_REVISION_RE = re.compile(r'^down_revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def test_alembic_revision_ids_fit_default_version_column() -> None:
    seen: set[str] = set()
    for path in sorted(VERSIONS.glob("*.py")):
        source = path.read_text()
        match = REVISION_RE.search(source)
        if not match:
            continue
        revision = match.group(1)
        assert len(revision) <= 32, f"{path.name}: revision ID {revision!r} exceeds Alembic VARCHAR(32)"
        assert revision not in seen, f"Duplicate Alembic revision ID: {revision}"
        seen.add(revision)

    assert seen, "No Alembic revisions were discovered"


def test_alembic_down_revisions_reference_existing_ids() -> None:
    files = list(VERSIONS.glob("*.py"))
    revisions = {
        match.group(1)
        for path in files
        if (match := REVISION_RE.search(path.read_text()))
    }
    for path in files:
        source = path.read_text()
        match = DOWN_REVISION_RE.search(source)
        if not match:
            continue
        down_revision = match.group(1)
        assert down_revision in revisions, f"{path.name}: unknown down_revision {down_revision!r}"
