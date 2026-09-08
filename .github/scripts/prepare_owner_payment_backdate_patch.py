from pathlib import Path

path = Path('.github/scripts/loanhub_owner_payment_backdate.py')
text = path.read_text()
old = '''def replace_once(path: Path, old: str, new: str, label: str) -> None:\n    text = path.read_text()\n    count = text.count(old)\n    if count != 1:\n        raise SystemExit(f'{label}: expected 1 match, found {count}')\n    path.write_text(text.replace(old, new, 1))\n'''
new = '''def replace_once(path: Path, old: str, new: str, label: str) -> None:\n    text = path.read_text()\n    scoped_markers = {\n        "cash repayment service date": "def collect_cash_repayment(",\n        "installment service date": "def pay_installment(",\n    }\n    marker = scoped_markers.get(label)\n    if marker:\n        if text.count(marker) != 1:\n            raise SystemExit(f'{label}: scope marker not unique')\n        before, after = text.split(marker, 1)\n        count = after.count(old)\n        if count < 1:\n            raise SystemExit(f'{label}: expected a match inside scope, found {count}')\n        path.write_text(before + marker + after.replace(old, new, 1))\n        return\n    count = text.count(old)\n    if count != 1:\n        raise SystemExit(f'{label}: expected 1 match, found {count}')\n    path.write_text(text.replace(old, new, 1))\n'''
if text.count(old) != 1:
    raise SystemExit('replace_once helper shape changed unexpectedly')
path.write_text(text.replace(old, new, 1))
print('Made payment patch replacements function-scoped.')
