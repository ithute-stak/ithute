#!/usr/bin/env bash
set -Eeuo pipefail

installer="scripts/install-production-pull-command.sh"

grep -F 'Usage: pull {ithute|loanhub} latest' "$installer" >/dev/null
grep -F 'REPO="ithute-stak/ithute"' "$installer" >/dev/null
grep -F 'REPO="ithute-stak/LoanHub"' "$installer" >/dev/null
grep -F 'HELPER_PATH="scripts/deploy-production-latest.sh"' "$installer" >/dev/null
grep -F 'HELPER_PATH="scripts/deploy-production-manual.sh"' "$installer" >/dev/null
grep -F 'exec sudo bash "$helper" latest' "$installer" >/dev/null

bash -n "$installer"

echo "universal production pull launcher checks passed"
