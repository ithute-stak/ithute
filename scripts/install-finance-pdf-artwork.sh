#!/usr/bin/env bash
# Install the user-approved Ithute/iMail JPEG into a local backend checkout.
# Usage: scripts/install-finance-pdf-artwork.sh /path/to/ithute_imail_quotation_header.jpg
set -euo pipefail
if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/approved/ithute_imail_quotation_header.jpg" >&2
  exit 2
fi
SOURCE="$1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/apps/backend/app/assets/ithute_imail_quotation_header.jpg"
SIG="$ROOT/apps/backend/app/assets/koetlisi_theko_mofoka_signature.png"
EXPECTED="36396920cb7ece9688751e51e4636512cd35764bf294e7be06bfc06e307d7531"
ACTUAL="$(sha256sum "$SOURCE" | cut -d' ' -f1)"
if [ "$ACTUAL" != "$EXPECTED" ]; then
  echo "Rejected: source does not match the original approved Ithute/iMail image" >&2
  exit 3
fi
if [ ! -s "$SIG" ]; then
  echo "Rejected: approved signature artwork is missing: $SIG" >&2
  exit 4
fi
install -m 0644 "$SOURCE" "$DEST"
python3 - "$DEST" "$SIG" <<'PY'
import sys
from PIL import Image
for path in sys.argv[1:]:
    with Image.open(path) as image:
        image.verify()
    print(f"Validated finance PDF artwork: {path}")
PY
echo "Artwork installed in checkout. Commit the JPEG and deploy the backend image before claiming a production fix."
