"""Detect concurrent Alembic heads without importing application settings."""
from __future__ import annotations

import ast
from pathlib import Path

root = Path(__file__).resolve().parent / "alembic" / "versions"
revisions: dict[str, tuple[str, ...]] = {}
for file in root.glob("*.py"):
    parsed = ast.parse(file.read_text(), filename=str(file))
    revision = None
    parents: tuple[str, ...] = ()
    for node in parsed.body:
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if "revision" in names:
                revision = ast.literal_eval(node.value)
            if "down_revision" in names:
                value = ast.literal_eval(node.value)
                parents = (value,) if isinstance(value, str) else tuple(value or ())
    if revision:
        revisions[revision] = parents
parents = {p for values in revisions.values() for p in values}
heads = sorted(set(revisions) - parents)
print("Ithute Auth migration heads:", ", ".join(heads))
if len(heads) != 1:
    raise SystemExit("Expected exactly one migration head; repair revision ancestry before deployment")
