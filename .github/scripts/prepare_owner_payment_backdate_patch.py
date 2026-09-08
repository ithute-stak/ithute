from pathlib import Path

path = Path('.github/scripts/loanhub_owner_payment_backdate.py')
text = path.read_text()
old = '''def replace_once(path: Path, old: str, new: str, label: str) -> None:\n    text = path.read_text()\n    count = text.count(old)\n    if count != 1:\n        raise SystemExit(f'{label}: expected 1 match, found {count}')\n    path.write_text(text.replace(old, new, 1))\n'''
new = '''def replace_once(path: Path, old: str, new: str, label: str) -> None:\n    text = path.read_text()\n    scoped_markers = {\n        "cash repayment service date": "def collect_cash_repayment(",\n        "installment service date": "def pay_installment(",\n    }\n    marker = scoped_markers.get(label)\n    if marker:\n        if text.count(marker) != 1:\n            raise SystemExit(f'{label}: scope marker not unique')\n        before, after = text.split(marker, 1)\n        count = after.count(old)\n        if count < 1:\n            raise SystemExit(f'{label}: expected a match inside scope, found {count}')\n        path.write_text(before + marker + after.replace(old, new, 1))\n        return\n    count = text.count(old)\n    if count != 1:\n        raise SystemExit(f'{label}: expected 1 match, found {count}')\n    path.write_text(text.replace(old, new, 1))\n'''
if text.count(old) != 1:
    raise SystemExit('replace_once helper shape changed unexpectedly')
text = text.replace(old, new, 1)

old_policy = '''from database.config.config import settings\\nfrom database.models.enums import UserRole\\n\\n\\ndef current_payment_date() -> date:\\n    return datetime.now(ZoneInfo(settings.APP_TIMEZONE)).date()\\n'''
new_policy = '''from database.models.enums import UserRole\\n\\n\\ndef _app_timezone() -> ZoneInfo:\\n    from database.config.config import settings\\n    return ZoneInfo(settings.APP_TIMEZONE)\\n\\n\\ndef current_payment_date() -> date:\\n    return datetime.now(_app_timezone()).date()\\n'''
if text.count(old_policy) != 1:
    raise SystemExit('payment policy settings import shape changed unexpectedly')
text = text.replace(old_policy, new_policy, 1)
old_utc = '''    local_midnight = datetime.combine(value, time.min, tzinfo=ZoneInfo(settings.APP_TIMEZONE))\\n'''
new_utc = '''    local_midnight = datetime.combine(value, time.min, tzinfo=_app_timezone())\\n'''
if text.count(old_utc) != 1:
    raise SystemExit('payment UTC helper shape changed unexpectedly')
text = text.replace(old_utc, new_utc, 1)

path.write_text(text)
print('Made payment patch replacements function-scoped and test-isolated.')
